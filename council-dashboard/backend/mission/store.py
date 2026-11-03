"""Transactional snapshots and append-only revisions (PostgreSQL in production)."""
import os
import time
import uuid
from contextlib import contextmanager
from copy import deepcopy
from sqlalchemy import create_engine, Column, String, Integer, Float, JSON, UniqueConstraint, select, event
from sqlalchemy.orm import declarative_base, Session
from .engine import new_state, advance, modify, InvalidAction
from .spec import digest, SOURCES

Base = declarative_base()
# Public mission pacing: real Mars time. One tick = 1/24 sol (D7) of real time, so the public mission's Mars date is
# the real Mars date and live conditions (conditions.py) apply to the tick they were observed in.

class Mission(Base):
    __tablename__ = 'missions'
    id = Column(String, primary_key=True)
    owner = Column(String, nullable=True, index=True)
    state = Column(JSON, nullable=False)
    revision = Column(Integer, nullable=False, default=0)
    pending_ticks = Column(Integer, nullable=False, default=0)
    used_ticks = Column(Integer, nullable=False, default=0)
    next_tick = Column(Float, nullable=False, default=0)
    expires = Column(Float, nullable=True)
    parent = Column(JSON, nullable=True)

class Revision(Base):
    __tablename__ = 'mission_revisions'
    id = Column(String, primary_key=True)
    mission_id = Column(String, nullable=False, index=True)
    revision = Column(Integer, nullable=False)
    operation = Column(JSON, nullable=False)
    state = Column(JSON, nullable=False)
    hash = Column(String, nullable=False)
    created = Column(Float, nullable=False)
    __table_args__ = (UniqueConstraint('mission_id', 'revision'),)

class Owner(Base):
    __tablename__ = 'owners'
    id = Column(String, primary_key=True)

class SourceVersion(Base):
    __tablename__ = 'source_versions'
    id = Column(String, primary_key=True)
    source_id = Column(String, nullable=False, index=True)
    record = Column(JSON, nullable=False)

class Budget(Base):
    __tablename__ = 'inference_budgets'
    id = Column(String, primary_key=True)
    charged = Column(Float, nullable=False, default=0)

class InferenceReceipt(Base):
    __tablename__ = 'inference_receipts'
    id = Column(String, primary_key=True)
    mission_id = Column(String, nullable=False, index=True)
    record = Column(JSON, nullable=False)

class ServiceStatus(Base):
    __tablename__ = 'service_status'
    id = Column(String, primary_key=True)
    record = Column(JSON, nullable=False)

class EnvironmentObservation(Base):
    """Live Mars conditions recorded by the worker whether or not any mission is running (DSN Mars link changes)."""
    __tablename__ = 'environment_observations'
    id = Column(String, primary_key=True)
    kind = Column(String, nullable=False, index=True)
    observed_at = Column(Float, nullable=False, index=True)
    record = Column(JSON, nullable=False)

class EventLog(Base):
    """Append-only record of every status write, receipt change and worker event, from genesis. Rows are never updated or deleted."""
    __tablename__ = 'event_log'
    id = Column(String, primary_key=True)
    at = Column(Float, nullable=False, index=True)
    source = Column(String, nullable=False, index=True)
    kind = Column(String, nullable=False)
    mission_id = Column(String, nullable=True, index=True)
    record = Column(JSON, nullable=False)


@event.listens_for(Session, 'before_flush')
def _append_events(session, flush_context, instances):
    """Every write to a mutable table (service status, inference receipts) is also appended here, so nothing is lost when a row is overwritten."""
    now = time.time()
    for obj in list(session.new) + list(session.dirty):
        if isinstance(obj, ServiceStatus):
            if obj.id == 'worker' and not (obj.record or {}).get('error'):
                continue  # one-second heartbeat; worker starts and errors are logged
            session.add(EventLog(id=str(uuid.uuid4()), at=now, source='status', kind=obj.id, mission_id=None, record=deepcopy(obj.record)))
        elif isinstance(obj, InferenceReceipt):
            session.add(EventLog(id=str(uuid.uuid4()), at=now, source='receipt', kind=(obj.record or {}).get('status', 'update'),
                                 mission_id=obj.mission_id, record={'receipt_id': obj.id, **deepcopy(obj.record)}))


class Store:
    def __init__(self, url=None):
        url = url or os.getenv('DATABASE_URL', 'sqlite:///mission.db')
        if url.startswith('postgres://'): url = url.replace('postgres://', 'postgresql+psycopg://', 1)
        if url.startswith('postgresql://'): url = url.replace('postgresql://', 'postgresql+psycopg://', 1)
        self.engine = create_engine(url, connect_args={'check_same_thread': False, 'timeout': 30} if url.startswith('sqlite') else {}, pool_pre_ping=True)
        self.sqlite = url.startswith('sqlite')
        if self.sqlite: Base.metadata.create_all(self.engine)
        else:
            with self.engine.begin() as connection:
                connection.exec_driver_sql('SELECT pg_advisory_xact_lock(781044)')
                Base.metadata.create_all(connection)

    @contextmanager
    def transaction(self):
        with Session(self.engine) as db:
            if self.sqlite: db.connection().exec_driver_sql('BEGIN IMMEDIATE')
            try:
                yield db
                db.commit()
            except Exception:
                db.rollback()
                raise

    def row(self, db, mid):
        m = db.scalar(select(Mission).where(Mission.id == mid).with_for_update())
        if not m: raise KeyError(mid)
        if m.expires and m.expires < time.time(): raise KeyError(mid)
        return m

    def save(self, db, m, state, operation):
        m.state = deepcopy(state)
        m.revision += 1
        db.add(Revision(id=str(uuid.uuid4()), mission_id=m.id, revision=m.revision,
                        operation=operation, state=deepcopy(state), hash=digest(state), created=time.time()))

    def commit_unclaimed(self, mid, mutate, operation, wait_s=900, poll_s=5):
        """Apply a background update (new evidence) only while no planning claim is open, so a plan in progress is never
        overwritten and never silently made stale. Waits for the claim to close (claims are recovered after 600 s)."""
        deadline = time.time() + wait_s
        while True:
            with self.transaction() as db:
                m = self.row(db, mid)
                if not m.state.get('planning_claim'):
                    s = deepcopy(m.state)
                    mutate(s)
                    self.save(db, m, s, operation)
                    return m.revision
            if time.time() > deadline:
                raise InvalidAction(f"Planning stayed open for {wait_s} s; {operation['kind']} not applied")
            time.sleep(poll_s)

    def initialize(self):
        """Check, then create the public mission if absent. Used by tests and operator tools; the API and worker
        never call this: they only check(), and genesis waits for a user to press Start (genesis())."""
        if not self.check():
            self.genesis()

    def started(self):
        with Session(self.engine) as db:
            return db.get(Mission, 'public') is not None

    def check(self):
        """Validate the database against the current package and engine. Returns True if the public mission exists, False
        if it has not been started. A public mission recorded under another package or engine version came from a build
        that is no longer the tool, so it is discarded (mission, revisions and model receipts); Start then
        begins a new genesis. The append-only event log, which also holds every model receipt and spend, is kept."""
        from .spec import specification
        spec = specification()  # the package must load and every operator decision must be approved before Start is offered
        with self.transaction() as db:
            existing = db.scalar(select(Mission).where(Mission.id == 'public').with_for_update())
            if not existing:
                return False
            stored = existing.state.get('spec', {})
            if stored.get('package_hash') == spec['package_hash'] and stored.get('version') == spec['version']:
                return True
            record = {'package_hash': stored.get('package_hash'), 'engine_version': stored.get('version'), 'revisions': existing.revision,
                      'tick': existing.state.get('tick'), 'replaced_by_package': spec['package_hash'], 'replaced_by_engine': spec['version']}
            for model in (Revision, InferenceReceipt):
                for r in db.scalars(select(model).where(model.mission_id == 'public')).all():
                    db.delete(r)
            db.delete(existing)
            db.add(EventLog(id=str(uuid.uuid4()), at=time.time(), source='store', kind='mission-discarded', mission_id='public', record=record))
        return False

    def genesis(self):
        """Start the public mission (genesis). Called when a user presses Start; does nothing if it already exists."""
        if self.check():
            return False
        genesis_env = self.environment(time.time(), None)
        with self.transaction() as db:
            if not self.sqlite: db.connection().exec_driver_sql('SELECT pg_advisory_xact_lock(781045)')
            if db.get(Mission, 'public'): return False
            mode=os.getenv('MISSION_MODEL_MODE','meta')
            if mode not in ('meta','fixed-priority'):raise InvalidAction('MISSION_MODEL_MODE must be meta or fixed-priority')
            state = new_state(mode)
            pins = {}
            registry = SOURCES + [dict(id=k, title=v['title'], url=v['url'], version=str(v.get('year')), passage=None,
                                       supports='Cited by environment package '+state['spec']['package_id'], classification='published')
                                  for k, v in state['spec']['sources'].items()]
            for source in registry:
                record = {**source, 'retrieved_at': None, 'observation_time': None, 'status': 'registry reference; not retrieved', 'content_hash': digest(source), 'hash_scope': 'registry metadata only', 'transformation_version': 'registry-1'}
                vid = source['id'] + ':' + record['content_hash'][:16]
                db.merge(SourceVersion(id=vid, source_id=source['id'], record=record))
                pins[source['id']] = vid
            package = {'id': state['spec']['package_id'], 'title': 'Environment package '+state['spec']['package_id'], 'url': None,
                       'status': 'local validated package', 'content': state['spec'], 'content_hash': state['spec']['package_hash'],
                       'hash_scope': 'package file bytes', 'retrieved_at': None, 'classification': 'package'}
            vid = package['id'] + ':' + package['content_hash'][:16]
            db.merge(SourceVersion(id=vid, source_id=package['id'], record=package))
            pins[package['id']] = vid
            state['source_pins'] = pins
            now = genesis_env['clock']['unix']
            from .engine import apply_environment
            apply_environment(state, genesis_env)
            m = Mission(id='public', state=state, revision=0, next_tick=now + state['spec']['tick_seconds'], pending_ticks=0, used_ticks=0)
            db.add(m)
            self.save(db, m, state, {'kind':'initialize', 'trigger':'start pressed'})
            # D13: SAM characterizes the site at each genesis. A site analysis recorded for an earlier mission does not
            # belong to this one, so its status is cleared and the worker runs SAM for the new mission.
            old = db.get(ServiceStatus, 'site-analysis')
            if old: db.delete(old)
        # Evidence already downloaded by earlier source refreshes is attached at once (no download), so a new mission
        # starts with its regional products instead of waiting for the next daily refresh.
        from .evidence import attach_stored
        attach_stored(self)
        return True

    def request_replanning(self, mid, reason):
        """Ask the agents to plan again at the next worker pass (new evidence). No model call happens here."""
        with self.transaction() as db:
            m = self.row(db, mid)
            if m.state['mode'] != 'meta' or m.state.get('inference_stopped') or m.state.get('planning_claim') or m.state['status'] != 'active':
                return False
            s = deepcopy(m.state)
            s['planning_needed'] = True
            from .engine import event
            event(s, 'Replanning requested', reason)
            self.save(db, m, s, {'kind': 'replanning-request', 'reason': reason})
            return True

    def refresh_conditions(self):
        """Apply live DSN readings to the running public mission when its applied conditions lack them (e.g. at genesis)."""
        with Session(self.engine) as db:
            p = db.get(Mission, 'public')
            if not p or p.state['status'] != 'active' or p.state.get('planning_claim') or not p.state.get('environment'): return False
            if p.state['environment']['link'].get('dsn') != 'unavailable': return False
            previous = deepcopy(p.state['environment'])
        env = self.environment(time.time(), previous)
        if env['link']['dsn'] != 'live' or env.get('resumed_after_s'): return False
        from .engine import apply_environment
        with self.transaction() as db:
            m = self.row(db, 'public')
            if m.state.get('planning_claim') or m.state['status'] != 'active': return False
            st = deepcopy(m.state)
            apply_environment(st, env)
            self.save(db, m, st, {'kind': 'conditions-refresh'})
        return True

    def snapshot(self, mid, owner=None):
        with Session(self.engine) as db:
            m = self.row(db, mid)
            if m.owner and m.owner != owner: raise PermissionError('This experiment belongs to another visitor')
            return self.payload(m)

    def payload(self, m):
        return {'id':m.id, 'revision':m.revision, 'state':deepcopy(m.state), 'parent':m.parent,
                'remaining_ticks':72-m.used_ticks-m.pending_ticks if m.owner else None,
                'queued_ticks':m.pending_ticks, 'expires_at':m.expires,
                'seconds_per_tick':None if m.owner else m.state['spec']['tick_seconds'], 'next_tick_at':None if m.owner else m.next_tick}

    def environment(self, now, previous):
        """Live conditions for the public mission at `now`, given the previously applied conditions (D10, D11)."""
        from .conditions import snapshot
        if not hasattr(self, '_values'):
            from .package import load
            self._values = load()['values']
        values = self._values
        tick_s = values['mars.sol_s'] / 24
        env = snapshot(now, values['comms.mars_soi_km'], self.status('dsn'),
                       values['comms.conjunction_sun_sep_deg'], tick_s, previous['clock']['unix'] if previous else None)
        env['clock']['dusty_season'] = env['clock']['ls_deg'] >= values['mars.dusty_season_start_ls_deg']
        if previous and now - previous['clock']['unix'] > 1.5 * tick_s:
            env['resumed_after_s'] = now - previous['clock']['unix']
            with Session(self.engine) as db:
                rows = db.scalars(select(EnvironmentObservation).where(EnvironmentObservation.observed_at > previous['clock']['unix'],
                                                                      EnvironmentObservation.observed_at <= now).order_by(EnvironmentObservation.observed_at)).all()
                ups = sum(1 for r in rows if r.kind == 'dsn-reading' and r.record.get('uplink_to_mars'))
                outages = sum(1 for r in rows if r.kind == 'dsn-unavailable')
                craft = sorted({c for r in rows if r.kind == 'dsn-reading' for c in r.record.get('mars_spacecraft', [])})
                env['while_paused'] = (f"While paused: {len(rows)} DSN readings recorded, {ups} with an active uplink to Mars"
                                       + (f" ({', '.join(craft)})" if craft else '') + (f", {outages} feed outages" if outages else '') + '. '
                                       + f"Mars advanced from Ls {previous['clock']['ls_deg']:.2f} to {env['clock']['ls_deg']:.2f} deg; "
                                       + f"Earth-Mars light time {previous['geometry']['one_way_light_s']/60:.1f} to {env['geometry']['one_way_light_s']/60:.1f} min.")
        return env

    def fork(self, revision, owner):
        with self.transaction() as db:
            # Serialize fork creation per owner, including across API processes.
            if self.sqlite:
                if not db.get(Owner, owner): db.add(Owner(id=owner)); db.flush()
            else:
                from sqlalchemy.dialects.postgresql import insert
                db.execute(insert(Owner).values(id=owner).on_conflict_do_nothing())
            db.scalar(select(Owner).where(Owner.id==owner).with_for_update())
            owned = db.scalars(select(Mission).where(Mission.owner==owner, Mission.expires>time.time())).all()
            active = owned[0] if owned else None
            if active: raise InvalidAction('One experiment per visitor; use your existing experiment '+active.id)
            original = db.scalar(select(Revision).where(Revision.mission_id=='public', Revision.revision==revision))
            if not original: raise InvalidAction('Unknown public revision')
            state = deepcopy(original.state)
            state.pop('planning_claim',None)
            if state.get('environment'):
                # D10: experiments keep the environment frozen at the fork point; DSN is not applied.
                link = state['environment']['link']
                link.update(dsn='not applied in experiments', uplink_window=None, links=[], mars_spacecraft=[])
                link['uplink_open'] = not link['conjunction']
            state['status'] = 'paused'
            mid = str(uuid.uuid4())
            state['reliability_seed'] = mid  # D14: an experiment draws its own failures
            m = Mission(id=mid, owner=owner, state=state, revision=0, pending_ticks=0, used_ticks=0,
                        next_tick=0, expires=time.time()+7*86400, parent={'id':'public','revision':revision,'hash':original.hash,'resources':original.state['resources'],'spent_usd':original.state['spent_usd'],'tick':original.state['tick']})
            db.add(m)
            self.save(db,m,state,{'kind':'fork','parent':m.parent})
            return self.payload(m)

    def end_experiment(self, mid, owner):
        """Delete a visitor's own experiment and its revisions. The public mission can never be deleted."""
        if mid == 'public':
            raise PermissionError('The public mission cannot be ended')
        with self.transaction() as db:
            m = db.scalar(select(Mission).where(Mission.id == mid).with_for_update())
            if not m: raise KeyError(mid)
            if not m.owner or m.owner != owner: raise PermissionError('This experiment belongs to another visitor')
            if m.state.get('planning_claim'): raise InvalidAction('Agents are planning in this experiment; end it after they finish')
            for r in db.scalars(select(Revision).where(Revision.mission_id == mid)).all(): db.delete(r)
            db.delete(m)
        self.log('api', 'experiment-ended', {'mission_id': mid})
        return {'ended': mid}

    def control(self, mid, owner, revision, action, changes=None, ticks=0):
        with self.transaction() as db:
            m = self.row(db,mid)
            if not m.owner or m.owner != owner: raise PermissionError('Public mission is read-only; fork it to experiment')
            if m.revision != revision: raise InvalidAction('Revision changed; refresh before retrying')
            s = deepcopy(m.state)
            if s.get('planning_claim'): raise InvalidAction('Planning is in progress; retry after its receipt is recorded')
            if action=='configure':
                s = modify(s,changes or {})
                self.benchmark_logistics(s)
            elif action=='run':
                if not 1<=ticks<=72-m.used_ticks-m.pending_ticks: raise InvalidAction('Experiment limit is three sols (72 ticks) in total')
                m.pending_ticks += ticks; s['status']='active'
            elif action=='pause': s['status']='paused'
            elif action=='resume':
                s['status']='active'
            else: raise InvalidAction('Unknown control')
            m.expires=time.time()+7*86400
            self.save(db,m,s,{'kind':action,'changes':changes,'ticks':ticks})
            return self.payload(m)

    def step(self, s, env=None):
        """One tick of the execution harness shared by the public mission, experiments and the comparison baseline:
        the engine step, then the benchmark's automatic logistics (D12) when the fixed-priority planner is in charge."""
        s = advance(s, env)
        self.benchmark_logistics(s)
        return s

    def benchmark_logistics(self, s):
        """D12: under the fixed-priority planner, replacements for failed robots are ordered automatically."""
        if s['mode'] != 'fixed-priority' or not s.get('environment'):
            return
        from .engine import failed_without_order, place_order, sim_unix
        from .logistics import replacement_order
        if not hasattr(self, '_values'):
            from .package import load
            self._values = load()['values']
        for aid in failed_without_order(s):
            place_order(s, replacement_order(s, aid, sim_unix(s), self._values, 'fixed-priority', 'Automatic replacement (benchmark).', ['nssdc_mars']))

    def tick(self):
        now=time.time()
        public_env=None
        with Session(self.engine) as db:
            p=db.get(Mission,'public')
            due=p is not None and p.state['status']=='active' and not p.state.get('planning_claim') and p.next_tick<=now
            previous=deepcopy(p.state.get('environment')) if due else None
        if due:
            try: public_env=self.environment(now, previous)
            except Exception as exc:
                # Fail loud: the public mission does not tick without live conditions; the reason is visible in service status.
                self.status('conditions',{'failed_at':now,'error':f'{type(exc).__name__}: {exc}'[:400]})
                raise
            self.status('conditions',{'applied_at':now,'error':None})
        with self.transaction() as db:
            # Lock one mission, and commit state + ledger + revision together.
            rows=db.scalars(select(Mission).where((Mission.expires.is_(None)) | (Mission.expires>now)).order_by(Mission.next_tick).with_for_update(skip_locked=True)).all()
            for m in rows:
                if m.state['status']!='active': continue
                if m.state.get('planning_claim'): continue
                if m.owner and m.pending_ticks<=0: continue
                if not m.owner and m.next_tick>now: continue
                if m.owner: s=self.step(m.state)
                elif public_env is None: continue
                else: s=self.step(m.state, public_env)
                if m.owner:
                    m.pending_ticks-=1; m.used_ticks+=1
                    if m.pending_ticks==0 and s['status']=='active': s['status']='paused'
                else: m.next_tick=max(m.next_tick,now)+s['spec']['tick_seconds']
                self.save(db,m,s,{'kind':'tick'})
                return m.id
        return None

    def export(self, mid, owner=None):
        snapshot=self.snapshot(mid,owner)
        with Session(self.engine) as db:
            revisions=db.scalars(select(Revision).where(Revision.mission_id==mid).order_by(Revision.revision)).all()
            sources={key:db.get(SourceVersion,vid).record for key,vid in snapshot['state']['source_pins'].items()}
            receipts=db.scalars(select(InferenceReceipt).where(InferenceReceipt.mission_id==mid)).all()
            pins=set(snapshot['state']['source_pins'].values())
            for revision in revisions: pins.update(revision.state.get('source_pins',{}).values())
            versions={vid:db.get(SourceVersion,vid).record for vid in pins}
            log=db.scalars(select(EventLog).where((EventLog.mission_id==mid)|(EventLog.mission_id.is_(None))).order_by(EventLog.at)).all()
            observations=db.scalars(select(EnvironmentObservation).order_by(EnvironmentObservation.observed_at)).all() if not snapshot['parent'] else []
            return {**snapshot,'sources':sources,'source_versions':versions,'inference_receipts':[{'id':r.id,**r.record} for r in receipts],
                    'history':[{'revision':r.revision,'operation':r.operation,'state':r.state,'hash':r.hash,'created_at':r.created} for r in revisions],
                    'event_log':[{'at':r.at,'source':r.source,'kind':r.kind,'record':r.record} for r in log],
                    'environment_observations':[{'id':r.id,'kind':r.kind,'observed_at':r.observed_at,**r.record} for r in observations]}

    def cleanup(self):
        with self.transaction() as db:
            for m in db.scalars(select(Mission).where(Mission.expires<time.time())).all():
                for r in db.scalars(select(Revision).where(Revision.mission_id==m.id)).all(): db.delete(r)
                db.delete(m)

    def log(self, source, kind, record, mission_id=None):
        """Append one event. Used for worker lifecycle and any event that has no other durable row."""
        with self.transaction() as db:
            db.add(EventLog(id=str(uuid.uuid4()), at=time.time(), source=source, kind=kind, mission_id=mission_id, record=record))

    def events(self, mid=None, after=None, limit=200, source=None):
        with Session(self.engine) as db:
            q = select(EventLog)
            if mid is not None: q = q.where((EventLog.mission_id == mid) | (EventLog.mission_id.is_(None)))
            if after is not None: q = q.where(EventLog.at > after)
            if source: q = q.where(EventLog.source == source)
            rows = db.scalars(q.order_by(EventLog.at).limit(limit)).all()
            return [{'id': r.id, 'at': r.at, 'source': r.source, 'kind': r.kind, 'mission_id': r.mission_id, 'record': r.record} for r in rows]

    def status(self, key, value=None):
        with self.transaction() as db:
            if value is not None: db.merge(ServiceStatus(id=key,record=value)); return value
            row=db.get(ServiceStatus,key)
            return deepcopy(row.record) if row else None

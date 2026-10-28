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

    def initialize(self):
        with self.transaction() as db:
            if not self.sqlite: db.connection().exec_driver_sql('SELECT pg_advisory_xact_lock(781045)')
            if db.get(Mission, 'public'): return
            state = new_state()
            if os.getenv('MISSION_MODEL_MODE')=='meta':
                state.update(mode='meta',planning_needed=True,planning_status='Awaiting initial mission plan')
            pins = {}
            for source in SOURCES + [dict(id='scenario-v1', title='Arcadia scenario assumptions', version=state['spec']['version'], url=None, passage=None, supports='All operational quantities are illustrative scenario assumptions.', classification='scenario assumption')]:
                record = {**source, 'retrieved_at': None, 'observation_time': None, 'status': 'not retrieved', 'content_hash': digest(source), 'hash_scope': 'registry metadata only', 'transformation_version': 'registry-1'}
                if source['id'] == 'scenario-v1':
                    record.update(status='local specification', content=state['spec'], content_hash=state['spec']['hash'], hash_scope='canonical mission specification')
                vid = source['id'] + ':' + record['content_hash'][:16]
                db.merge(SourceVersion(id=vid, source_id=source['id'], record=record))
                pins[source['id']] = vid
            state['source_pins'] = pins
            m = Mission(id='public', state=state, revision=0, next_tick=time.time(), pending_ticks=0, used_ticks=0)
            db.add(m)
            self.save(db, m, state, {'kind':'initialize'})

    def snapshot(self, mid, owner=None):
        with Session(self.engine) as db:
            m = self.row(db, mid)
            if m.owner and m.owner != owner: raise PermissionError('This experiment belongs to another visitor')
            return self.payload(m)

    def payload(self, m):
        return {'id':m.id, 'revision':m.revision, 'state':deepcopy(m.state), 'parent':m.parent,
                'remaining_ticks':72-m.used_ticks-m.pending_ticks if m.owner else None,
                'queued_ticks':m.pending_ticks, 'expires_at':m.expires}

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
            active = next((m for m in owned if m.state['status']!='complete'),None)
            if active: raise InvalidAction('One experiment per visitor; use your existing experiment '+active.id)
            original = db.scalar(select(Revision).where(Revision.mission_id=='public', Revision.revision==revision))
            if not original: raise InvalidAction('Unknown public revision')
            state = deepcopy(original.state)
            state.pop('planning_claim',None)
            state['status'] = 'paused' if state['status'] != 'complete' else 'complete'
            mid = str(uuid.uuid4())
            m = Mission(id=mid, owner=owner, state=state, revision=0, pending_ticks=0, used_ticks=0,
                        next_tick=0, expires=time.time()+7*86400, parent={'id':'public','revision':revision,'hash':original.hash,'water_kg':original.state['resources']['water_kg'],'spent_usd':original.state['spent_usd'],'tick':original.state['tick']})
            db.add(m)
            self.save(db,m,state,{'kind':'fork','parent':m.parent})
            return self.payload(m)

    def control(self, mid, owner, revision, action, changes=None, ticks=0):
        with self.transaction() as db:
            m = self.row(db,mid)
            if not m.owner or m.owner != owner: raise PermissionError('Public mission is read-only; fork it to experiment')
            if m.revision != revision: raise InvalidAction('Revision changed; refresh before retrying')
            s = deepcopy(m.state)
            if s.get('planning_claim'): raise InvalidAction('Planning is in progress; retry after its receipt is recorded')
            if action=='configure': s = modify(s,changes or {})
            elif action=='run':
                if not 1<=ticks<=72-m.used_ticks-m.pending_ticks: raise InvalidAction('Experiment limit is three sols (72 ticks) in total')
                if s['status']=='complete': raise InvalidAction('Mission already complete')
                m.pending_ticks += ticks; s['status']='active'
            elif action=='pause': s['status']='paused'
            elif action=='resume':
                if s['status']=='complete': raise InvalidAction('Mission already complete')
                s['status']='active'
            else: raise InvalidAction('Unknown control')
            m.expires=time.time()+7*86400
            self.save(db,m,s,{'kind':action,'changes':changes,'ticks':ticks})
            return self.payload(m)

    def tick(self):
        with self.transaction() as db:
            now=time.time()
            # Lock one mission, and commit state + ledger + revision together.
            rows=db.scalars(select(Mission).where((Mission.expires.is_(None)) | (Mission.expires>now)).order_by(Mission.next_tick).with_for_update(skip_locked=True)).all()
            for m in rows:
                if m.state['status']!='active': continue
                if m.state.get('planning_claim'): continue
                if m.owner and m.pending_ticks<=0: continue
                if not m.owner and m.next_tick>now: continue
                s=advance(m.state)
                if m.owner:
                    m.pending_ticks-=1; m.used_ticks+=1
                    if s['status']=='complete': m.pending_ticks=0
                    if m.pending_ticks==0 and s['status']=='active': s['status']='paused'
                else: m.next_tick=max(m.next_tick,now)+3600
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
            return {**snapshot,'sources':sources,'source_versions':versions,'inference_receipts':[{'id':r.id,**r.record} for r in receipts],'history':[{'revision':r.revision,'operation':r.operation,'state':r.state,'hash':r.hash,'created_at':r.created} for r in revisions]}

    def cleanup(self):
        with self.transaction() as db:
            for m in db.scalars(select(Mission).where(Mission.expires<time.time())).all():
                for r in db.scalars(select(Revision).where(Revision.mission_id==m.id)).all(): db.delete(r)
                db.delete(m)

    def status(self, key, value=None):
        with self.transaction() as db:
            if value is not None: db.merge(ServiceStatus(id=key,record=value)); return value
            row=db.get(ServiceStatus,key)
            return deepcopy(row.record) if row else None

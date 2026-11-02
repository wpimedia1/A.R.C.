"""Concurrency, comparison and evidence-reference guarantees of the mission store."""
import time
import pytest
import mission.planner as planner
from mission.engine import InvalidAction, event
from mission.store import EnvironmentObservation
from mission.inspection import inspect
from conftest import make_store


def test_background_evidence_waits_for_planning_to_finish(tmp_path, request):
    # Review finding 4: new evidence is never written into a mission while a plan is in progress.
    store = make_store(tmp_path, request); store.initialize()
    with store.transaction() as db:
        m = store.row(db, 'public'); s = dict(m.state); s['planning_claim'] = {'id': 'c', 'time': time.time()}
        store.save(db, m, s, {'kind': 'planning-claim'})
    revision = store.snapshot('public')['revision']
    mark = lambda s: s.__setitem__('evidence_marker', 1)
    with pytest.raises(InvalidAction, match='not applied'):
        store.commit_unclaimed('public', mark, {'kind': 'test-evidence'}, wait_s=0.2, poll_s=0.05)
    assert store.snapshot('public')['revision'] == revision
    with store.transaction() as db:
        m = store.row(db, 'public'); s = dict(m.state); s.pop('planning_claim')
        store.save(db, m, s, {'kind': 'planning-done'})
    store.commit_unclaimed('public', mark, {'kind': 'test-evidence'}, wait_s=0.2, poll_s=0.05)
    assert store.snapshot('public')['state']['evidence_marker'] == 1


def test_plan_made_on_a_stale_view_is_discarded(tmp_path, request, monkeypatch):
    # Review finding 4: the planner's commit is revision-checked; an intervening write is kept, the stale plan is not.
    monkeypatch.setenv('MISSION_MODEL_MODE', 'meta')
    store = make_store(tmp_path, request); store.initialize()

    def concurrent_write_then_fail(store_, mid, *args, **kwargs):
        with store_.transaction() as db:
            m = store_.row(db, mid); s = dict(m.state); s['source_pins'] = {**s['source_pins'], 'new-evidence': 'v2'}
            store_.save(db, m, s, {'kind': 'unexpected-writer'})
        raise InvalidAction('provider unavailable')
    monkeypatch.setattr(planner, 'call', concurrent_write_then_fail)
    assert planner.plan_once(store, mission_id='public')
    s = store.snapshot('public')['state']
    assert s['source_pins']['new-evidence'] == 'v2' and 'planning_claim' not in s
    assert s['planning_needed'] and not s['inference_stopped']
    assert s['activity'][-1]['title'] == 'Plan discarded'


def test_comparison_uses_the_same_harness_seed_and_changes(tmp_path, request, monkeypatch):
    # Review finding 10: with the same planner on both sides, the comparison baseline equals the experiment exactly.
    monkeypatch.setenv('COOKIE_SECURE', 'false')
    store = make_store(tmp_path, request); store.initialize()
    p = store.snapshot('public')
    fork = store.fork(p['revision'], 'owner-a')
    fork = store.control(fork['id'], 'owner-a', fork['revision'], 'configure', {'equipment': {'excavator-2': False}})
    fork = store.control(fork['id'], 'owner-a', fork['revision'], 'run', ticks=30)
    while store.tick():
        pass
    c = inspect(store, fork['id'], 'owner-a')['comparison']
    s = store.snapshot(fork['id'], 'owner-a')['state']
    assert c['elapsed_ticks'] == 30 and c['seed'] == s['reliability_seed'] == fork['id']
    assert c['baseline'] == c['experiment'] and c['changes_not_applicable_to_baseline'] == []


def test_standby_evidence_must_resolve_to_stored_records(tmp_path, request):
    # Review finding 7: references are checked against stored measurements, estimates and checks.
    from mission.nowcast import resolve_basis
    store = make_store(tmp_path, request)
    with store.transaction() as db:
        db.add(EnvironmentObservation(id='msl:4700:abc', kind='weather-obs', observed_at=time.time(),
                                      record={'station': 'msl', 'sol': 4700, 'values': {'air_min_c': -80.0}}))
        db.add(EnvironmentObservation(id='msl:air_min_c:4701:after4700', kind='weather-estimate', observed_at=time.time(),
                                      record={'station': 'msl', 'variable': 'air_min_c', 'value': -81.0, 'low95': -88.0, 'high95': -74.0}))
    ok = resolve_basis(store, [{'observation_id': 'msl:4700:abc', 'variable': 'air_min_c', 'interpretation': 'Cold night measured'},
                               {'observation_id': 'msl:air_min_c:4701:after4700', 'variable': 'air_min_c', 'interpretation': 'Colder tomorrow'}])
    assert [b['value'] for b in ok] == [-80.0, -81.0] and [b['kind'] for b in ok] == ['weather-obs', 'weather-estimate']
    for bad in ([{'observation_id': 'nonexistent-observation-id', 'variable': 'air_min_c', 'interpretation': 'x'}],
                [{'observation_id': 'msl:4700:abc', 'variable': 'pressure', 'interpretation': 'x'}],
                [{'observation_id': 'msl:air_min_c:4701:after4700', 'variable': 'air_max_c', 'interpretation': 'x'}],
                [{'observation_id': 'msl:4700:abc', 'variable': 'air_min_c', 'interpretation': ' '}], []):
        with pytest.raises(InvalidAction):
            resolve_basis(store, bad)

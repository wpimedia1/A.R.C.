"""Planning failure paths that need no network. Live planning is verified by tools/verify_agent_loop.py."""
import mission.provider as provider
from mission.planner import plan_once
from mission.store import InferenceReceipt
from conftest import make_store
from sqlalchemy import select


def test_missing_key_stops_planning_loudly_without_dispatch(tmp_path, request, monkeypatch):
    monkeypatch.setenv('MISSION_MODEL_MODE', 'meta')
    monkeypatch.delenv('MODEL_API_KEY', raising=False)
    monkeypatch.setattr(provider, 'ENV_FILE', tmp_path / 'absent.env')
    store = make_store(tmp_path, request)
    store.initialize()
    assert plan_once(store, mission_id='public')
    s = store.snapshot('public')['state']
    assert s['inference_stopped'] and 'MODEL_API_KEY' in s['planning_status']
    with store.transaction() as db:
        assert db.scalars(select(InferenceReceipt)).all() == []


def test_stopped_mission_is_not_replanned(tmp_path, request, monkeypatch):
    monkeypatch.setenv('MISSION_MODEL_MODE', 'meta')
    monkeypatch.delenv('MODEL_API_KEY', raising=False)
    monkeypatch.setattr(provider, 'ENV_FILE', tmp_path / 'absent.env')
    store = make_store(tmp_path, request)
    store.initialize()
    plan_once(store, mission_id='public')
    assert not plan_once(store, mission_id='public')


def test_oversized_context_sheds_background_evidence_first():
    from mission.planner import fit_context, CONTEXT_LIMIT
    from mission.spec import canonical
    big = {'jobs': [1, 2], 'weather': {'w': 1}, 'evidence': [{'id': f's{i}', 'passages': [{'text': 'x' * 2000} for _ in range(4)]} for i in range(CONTEXT_LIMIT // 8000 + 2)]}
    d, note = fit_context(big)
    assert len(canonical(d).encode()) <= CONTEXT_LIMIT and note and d['jobs'] == [1, 2] and d['weather'] == {'w': 1}
    assert fit_context({'a': 1}) == ({'a': 1}, None)


def test_fit_context_trims_evidence_inside_agent_observations():
    # Agent assessments carry evidence under 'world'; it must be shortened like top-level evidence, never other state.
    from mission.planner import fit_context, CONTEXT_LIMIT
    from mission.spec import canonical
    big = [{'id': f'src{i}', 'passages': [{'text': 'x' * 3000} for _ in range(4)], 'observations': [{'v': 'y' * 2000}] * 3,
            'spatial_summary': {'grid': 'z' * 3000}, 'supports': 'kept'} for i in range(CONTEXT_LIMIT // 15000 + 2)]
    data = {'role': 'power', 'world': {'jobs': [{'id': 'power'}], 'evidence': big}, 'own_memory': ['m']}
    assert len(canonical(data).encode()) > CONTEXT_LIMIT
    out, note = fit_context(data)
    assert len(canonical(out).encode()) <= CONTEXT_LIMIT and note
    assert out['world']['jobs'] == data['world']['jobs'] and out['own_memory'] == ['m']
    assert all(e['supports'] == 'kept' for e in out['world']['evidence'])


def test_malformed_assurance_answer_applies_no_decision():
    # Live runs 2026-11-02: the reviewer dropped a required `approve` boolean. Decisions are now lists (approved / held);
    # the whole answer is checked first and the reason is stated.
    import pytest
    from mission.planner import validate_review
    from mission.engine import InvalidAction
    ok = {'job_id': 'power', 'reason': 'ok', 'acknowledged_conditions': []}
    assert validate_review({'approved': [ok], 'held': [{'job_id': 'survey', 'reason': 'wait'}]}, ['power', 'survey']) == [
        {**ok, 'approve': True}, {'job_id': 'survey', 'approve': False, 'reason': 'wait', 'acknowledged_conditions': []}]
    with pytest.raises(InvalidAction, match='approval for survey is missing acknowledged_conditions; no decision applied'):
        validate_review({'approved': [ok, {'job_id': 'survey', 'reason': 'x'}]}, ['power', 'survey'])
    with pytest.raises(InvalidAction, match='more than once'):
        validate_review({'approved': [ok], 'held': [{'job_id': 'power', 'reason': 'x'}]}, ['power'])
    with pytest.raises(InvalidAction, match='not awaiting review'):
        validate_review({'approved': [{**ok, 'job_id': 'water'}]}, ['power'])


def test_new_evidence_does_not_restart_a_planning_stop(tmp_path, request, monkeypatch):
    # Live run 2026-11-02: evidence adoption set planning_needed on a stopped mission and planning resumed by itself.
    monkeypatch.setenv('MISSION_MODEL_MODE', 'meta')
    monkeypatch.delenv('MODEL_API_KEY', raising=False)
    monkeypatch.setattr(provider, 'ENV_FILE', tmp_path / 'absent.env')
    store = make_store(tmp_path, request)
    store.initialize()
    plan_once(store, mission_id='public')
    assert store.snapshot('public')['state']['inference_stopped']
    store.commit_unclaimed('public', lambda s: s.__setitem__('planning_needed', True), {'kind': 'test-forced-flag'})
    assert not plan_once(store, mission_id='public')  # a stop is cleared only by the owner (mission.cli replan)


def test_assurance_gets_one_correction_turn(monkeypatch):
    # Live runs 2026-11-02 (twice): assurance omitted `approve` for an order with an acknowledged condition. It is now
    # told exactly what was malformed and answers once more; the corrected answer is applied.
    import mission.planner as planner
    from mission.engine import new_state, start, job_by_id
    s = new_state('meta'); s['source_pins'] = {}
    start(s, 'survey', ['rover-1'], 'survey', 'survey / test', [s['spec']['package_id']])
    seen = []
    def fake_call(store, mid, operation, model, instructions, data, tools, transport=None, previous_response_id=None):
        seen.append((operation, previous_response_id, data))
        if operation.endswith(':correction'):
            return [{'name': 'review_work_orders', 'call_id': 'c2', 'arguments': {'approved': [
                {'job_id': 'survey', 'reason': 'ok', 'acknowledged_conditions': ['no-site-imagery']}], 'held': []}}], 'r2'
        return [{'name': 'review_work_orders', 'call_id': 'c1', 'arguments': {'approved': [
            {'job_id': 'survey', 'reason': 'ok'}], 'held': []}}], 'r1'
    monkeypatch.setattr(planner, 'call', fake_call)
    receipts = []
    planner.review_orders(None, 'public', 'c', s, {'assessments': []}, receipts)
    assert job_by_id(s, 'survey')['status'] == 'running'
    assert seen[1][0] == 'c:assurance-review:correction' and seen[1][1] == 'r1' and 'missing acknowledged_conditions' in seen[1][2][0]['output']
    assert [r['validation'][:8] for r in receipts] == ['rejected', 'accepted']

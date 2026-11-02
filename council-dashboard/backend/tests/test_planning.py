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

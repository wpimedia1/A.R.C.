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


def test_director_gets_created_job_ids_before_planning(monkeypatch):
    from mission import planner
    from mission.engine import new_state,instantiate_job
    s=new_state('meta')
    for j in s['jobs']:j['status']='complete'
    jid=instantiate_job(s,'survey-extension','explicit unit-test actor','Unit fixture')
    receipts=[{'role':'director','validation':'accepted','result':{'job_id':jid}}];seen=[]
    def response(store,mid,operation,model,instructions,data,tools,transport=None):
        seen.append(data)
        assert data['required_job_ids']==[jid]
        assert data['completed_tool_results'][0]['result']['job_id']==jid
        return [{'name':'set_mission_plan','arguments':{'priority':[jid],'summary':'Unit-test plan after tool feedback'}}],'explicit-unit-test-only'
    monkeypatch.setattr(planner,'call',response)
    p,priority,operation=planner.finish_director_plan(None,'public','unit-claim',s,[],[jid],receipts)
    assert len(seen)==1 and priority==[jid] and operation.endswith(':plan-after-tools')


def test_director_can_return_empty_plan_without_fabricating_work():
    from mission.planner import finish_director_plan
    from mission.engine import new_state
    s=new_state('meta')
    for j in s['jobs']:j['status']='complete'
    proposal={'name':'set_mission_plan','arguments':{'priority':[],'summary':'No eligible work in this unit scenario'}}
    _,priority,_=finish_director_plan(None,'public','unit-claim',s,[proposal],[],[])
    assert priority==[]


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


def test_specialist_inspection_history_does_not_repeat_large_snapshots():
    from copy import deepcopy
    from mission.planner import specialist_history,fit_context,CONTEXT_LIMIT
    from mission.spec import digest,canonical
    snapshot={'evidence':[{'id':'unit-source','passages':[{'text':'x'*200000}]}],'jobs':[{'id':'unit-job','status':'blocked'}]}
    results=[{'tool':'inspect_state','arguments':{},'result':snapshot},
             {'tool':'estimate_job','arguments':{'job_id':'unit-job'},'result':{'rejected':'No commissioned power'}}]
    before=deepcopy(results)
    history=specialist_history(results)
    body,note=fit_context({'state':snapshot,'tool_results_so_far':history})
    assert len(canonical(body).encode())<CONTEXT_LIMIT and note
    assert history[0]['result']['snapshot_hash']==digest(snapshot)
    assert history[1]==results[1] and results==before
    assert body['state']['jobs']==snapshot['jobs']


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
    def fake_call(store, mid, operation, model, instructions, data, tools, transport=None):
        seen.append((operation, data))
        if operation.endswith(':correction'):
            return [{'name': 'review_work_orders', 'call_id': 'c2', 'arguments': {'approved': [
                {'job_id': 'survey', 'reason': 'ok', 'acknowledged_conditions': ['no-site-imagery']}], 'held': []}}], 'r2'
        return [{'name': 'review_work_orders', 'call_id': 'c1', 'arguments': {'approved': [
            {'job_id': 'survey', 'reason': 'ok'}], 'held': []}}], 'r1'
    monkeypatch.setattr(planner, 'call', fake_call)
    receipts = []
    planner.review_orders(None, 'public', 'c', s, {'assessments': []}, receipts)
    assert job_by_id(s, 'survey')['status'] == 'running'
    assert seen[1][0] == 'c:assurance-review:correction' and 'missing acknowledged_conditions' in seen[1][1]['rejection'] and seen[1][1]['orders']
    assert [r['validation'][:8] for r in receipts] == ['rejected', 'accepted']


def test_full_planning_cycle_with_self_contained_turns(tmp_path, request, monkeypatch):
    # Live runs 2026-11-02: follow-up turns failed on the provider's stored conversations (HTTP 400 "referenced response
    # not found or expired", HTTP 503 "persistence service error"). Every turn is now self-contained. Whole cycle with a
    # scripted provider: assessments -> director -> specialists -> assurance -> recorded work orders.
    import mission.planner as planner
    from mission.engine import job_by_id
    monkeypatch.setenv('MISSION_MODEL_MODE', 'meta')
    store = make_store(tmp_path, request); store.initialize()
    pkg = store.snapshot('public')['state']['spec']['package_id']
    calls = []
    def fake(store_, mid, operation, model, instructions, data, tools, transport=None):
        calls.append(operation)
        tail = operation.split(':', 1)[1]
        if tail.startswith('assessment:'):
            world = data['world']
            return [{'name': 'record_assessment', 'call_id': 'a', 'arguments': {'summary': 'ok', 'recommended_jobs': [],
                     'job_judgements': [{'job_id': j['id'], 'judgement': 'proceed'} for j in world['jobs']],
                     'missing_information': [], 'source_ids': [pkg]}}], 'ra'
        if tail == 'director':
            return [{'name': 'set_mission_plan', 'call_id': 'd', 'arguments': {'priority': data['priority'], 'summary': 'go'}}], 'rd'
        if tail == 'power:0':
            return [{'name': 'estimate_job', 'call_id': 'p0', 'arguments': {'job_id': 'power', 'asset_ids': ['fsp-1']}}], 'rp0'
        if tail == 'power:1':
            assert data['tool_results_so_far'][0]['tool']=='estimate_job'
            assert data['tool_results_so_far'][0]['result']['validation_errors']==[]  # actual prior result restated
            return [{'name': 'submit_work_order', 'call_id': 'p1', 'arguments': {'job_id': 'power', 'asset_ids': ['fsp-1'], 'summary': 'deploy', 'source_ids': [pkg]}}], 'rp1'
        if tail == 'survey:0':
            return [{'name': 'submit_work_order', 'call_id': 's0', 'arguments': {'job_id': 'survey', 'asset_ids': ['rover-1'], 'summary': 'survey', 'source_ids': [pkg]}}], 'rs0'
        if tail == 'assurance-review':
            return [{'name': 'review_work_orders', 'call_id': 'r', 'arguments': {'approved': [
                {'job_id': o['job_id'], 'reason': 'ok', 'acknowledged_conditions': [c['id'] for c in o['open_conditions']]} for o in data['orders']], 'held': []}}], 'rr'
        raise AssertionError('unexpected request ' + operation)
    monkeypatch.setattr(planner, 'call', fake)
    assert planner.plan_once(store, mission_id='public')
    s = store.snapshot('public')['state']
    assert not s['inference_stopped'], s['planning_status']
    assert job_by_id(s, 'power')['status'] == 'running' and job_by_id(s, 'survey')['status'] == 'running'
    assert [c.split(':', 1)[1] for c in calls if ':power:' in c] == ['power:0', 'power:1']


def test_blocked_equipment_reaches_specialist_and_director_without_claiming_work(tmp_path,request,monkeypatch):
    """Injected responses exercise routing, not a live provider run."""
    from copy import deepcopy
    import mission.planner as planner
    monkeypatch.setenv('MISSION_MODEL_MODE','meta')
    store=make_store(tmp_path,request);store.initialize()
    with store.transaction() as db:
        m=store.row(db,'public');s=deepcopy(m.state)
        for j in s['jobs']:
            if j['id']!='survey':j['status']='complete';s['milestones'][j['id']]=True
        next(a for a in s['assets'] if a['id']=='rover-1')['available']=False
        store.save(db,m,s,{'kind':'test-fixture'})
    pkg=s['spec']['package_id'];seen=[]
    def injected(st,mid,operation,model,instructions,data,tools,transport=None):
        tail=operation.split(':',1)[1];seen.append(tail)
        if tail.startswith('assessment:'):
            return [{'name':'record_assessment','arguments':{'summary':'Fixture: equipment unavailable','recommended_jobs':[],
                     'job_judgements':[{'job_id':j['id'],'judgement':'hold'} for j in data['world']['jobs']],
                     'missing_information':[],'source_ids':[pkg]}}],'fixture-assessment'
        if tail in ('director','conflict-director'):
            state=data.get('state',data)
            return [{'name':'set_mission_plan','arguments':{'priority':state['priority'],'summary':'Fixture: wait for replacement'}}],'fixture-director'
        if tail=='survey:0':return [{'name':'request_replanning','arguments':{'summary':'Fixture: rover unavailable'}}],'fixture-specialist'
        if tail=='logistics':return [],'fixture-logistics'
        raise AssertionError(tail)
    monkeypatch.setattr(planner,'call',injected)
    assert planner.plan_once(store,mission_id='public')
    result=store.snapshot('public')['state']
    assert 'survey:0' in seen and 'conflict-director' in seen
    assert not result['inference_stopped']
    assert result['planning_status'].startswith('No executable work authorized')
    assert result['department_conflicts'][-1]['status']=='director reviewed; awaiting feasible execution'

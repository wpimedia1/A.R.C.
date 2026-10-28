import json
import httpx
import pytest
from copy import deepcopy
from mission.store import Store, InferenceReceipt
from mission.planner import plan_once, reserve, execute_tool
from mission.engine import new_state, InvalidAction
from mission.evidence import refresh, adopt_latest

@pytest.fixture
def store(tmp_path):
    s=Store('sqlite:///'+str(tmp_path/'test.db'));s.initialize();return s

def enable(store):
    with store.transaction() as db:
        m=store.row(db,'public');s=deepcopy(m.state);s.update(mode='meta',planning_needed=True)
        store.save(db,m,s,{'kind':'test-enable'})

def test_typed_tool_validation():
    s=new_state()
    with pytest.raises(InvalidAction):execute_tool(s,'submit_work_order',{'job_id':'survey','summary':'Start survey','source_ids':['scenario-v1']},'resources')
    with pytest.raises(InvalidAction):execute_tool(s,'submit_work_order',{'job_id':'survey','summary':'Start survey','source_ids':['invented']},'survey')
    assert s['committed_usd']==0

def test_live_protocol_with_mock_transport(store,monkeypatch):
    monkeypatch.setenv('MODEL_API_KEY','test-key');enable(store)
    def handler(request):
        payload=json.loads(request.content)
        data=json.loads(payload['input'][0]['content']) if isinstance(payload['input'],list) else json.loads(payload['input'])
        if payload['model']=='muse-wonder-1.0':name='set_mission_plan';args={'priority':data['priority'],'summary':'Survey first; respect dependencies.'}
        else:name='submit_work_order';args={'job_id':data['job_id'],'summary':'Inspect landing area before construction.','source_ids':['scenario-v1']}
        return httpx.Response(200,json={'id':'test-response','usage':{'input_tokens':100,'output_tokens':100},'output':[{'type':'function_call','name':name,'arguments':json.dumps(args),'call_id':'test-call'}]})
    assert plan_once(store,httpx.MockTransport(handler))
    snap=store.snapshot('public')['state']
    assert snap['jobs'][0]['status']=='running'
    assert snap['decisions'][0]['actor']=='survey / muse-spark-1.3'
    assert len(store.export('public')['inference_receipts'])==2
    assert not plan_once(store,httpx.MockTransport(handler))

def test_provider_failure_keeps_receipt_and_stops(store,monkeypatch):
    monkeypatch.setenv('MODEL_API_KEY','test-key');enable(store)
    plan_once(store,httpx.MockTransport(lambda _:httpx.Response(503)))
    s=store.snapshot('public')['state']
    assert s['inference_stopped'] and not s['planning_needed']
    receipt=store.export('public')['inference_receipts'][0]
    assert receipt['reserved_usd']>0 and receipt['status'].startswith('uncertain')

def test_global_budget_and_duplicate_claim(store):
    reserve(store,'public','one','muse-wonder-1.0',{'input':'x'})
    with pytest.raises(InvalidAction):reserve(store,'public','one','muse-wonder-1.0',{'input':'x'})
    for i in range(5):reserve(store,'private',str(i),'muse-wonder-1.0',{'input':'x'})
    with pytest.raises(InvalidAction):
        for i in range(100):reserve(store,'another-private','new'+str(i),'muse-wonder-1.0',{'input':'x'})

def test_failed_sources_do_not_overwrite_pins(store):
    original=store.snapshot('public')['state']['source_pins']
    results=refresh(store,httpx.MockTransport(lambda _:httpx.Response(503)))
    assert all('failed' in r['status'] for r in results)
    assert adopt_latest(store)==[]
    assert store.snapshot('public')['state']['source_pins']==original

"""Isolated test scenarios; no provider transport or fabricated app observations."""
from copy import deepcopy
import pytest
from mission.engine import new_state,advance,start,job_by_id,asset_by_id,InvalidAction
from mission.policies import charging_policy


def working():
    s=new_state('meta');s.update(planning_needed=False,failures_enabled=False,power_commissioned=True,power_capacity_kw=40)
    for j in s['jobs']:
        if j['id']!='trench':j['status']='complete';s['milestones'][j['id']]=True
    start(s,'trench',['excavator-1'],'Explicit unit-test setup','fixed-priority',[s['spec']['package_id']])
    return s


def authorize(s,ids=None):
    return charging_policy(s,ids or ['excavator-1'],'Unit-test standing order','unit-test actor',[s['spec']['package_id']])


def test_no_policy_means_no_automatic_meta_charging():
    s=working();asset_by_id(s,'excavator-1')['soc_wh']=0
    r=advance(s)
    assert not asset_by_id(r,'excavator-1')['charging'] and r['planning_needed']


def test_authorized_policy_keeps_working_without_repeated_director_plans():
    s=working();authorize(s)
    for _ in range(40):s=advance(s)
    assert job_by_id(s,'trench')['done']>0 and s['charging_energy_kwh']>0
    assert not s['planning_needed']
    assert not any(e['title'].startswith('Battery low') or e['title'].endswith('behind plan') for e in s['activity'])
    assert all(e['actor']=='unit-test actor' for e in s['charge_log'])


def test_policy_cannot_bypass_grid_loss_or_spam_identical_blockers():
    s=working();authorize(s);s['power_capacity_kw']=0;asset_by_id(s,'excavator-1')['soc_wh']=0
    s=advance(s)
    assert s['planning_needed'] and s['power_used_kw']==0 and not asset_by_id(s,'excavator-1')['charging']
    # The first missed schedule can independently request one replan. After
    # that material alert, the identical standing-order blocker is not repeated.
    s=advance(s);s['planning_needed']=False;s=advance(s)
    assert not s['planning_needed']
    assert len([e for e in s['activity'] if e['title']=='Standing charging order blocked'])==1


def test_policy_command_validates_every_unit_before_mutation():
    s=working();before=deepcopy(s)
    with pytest.raises(InvalidAction):authorize(s,['excavator-1','rover-1'])
    assert s==before


def test_sol_boundary_requests_memory_without_a_new_director_plan():
    s=new_state('meta');s.update(tick=23,planning_needed=False)
    s['agent_memory']={'power':{'working':[{'cycle_id':'unit-cycle','sol':0,'tick':1}], 'lessons':[]}}
    r=advance(s)
    assert r['memory_consolidation_due'] and not r['planning_needed']


def test_memory_only_cycle_calls_spark_without_new_assessments_or_director(tmp_path,request,monkeypatch):
    from conftest import make_store
    from mission import planner
    from mission.provider import SPECIALIST_MODEL
    store=make_store(tmp_path,request);store.initialize()
    with store.transaction() as db:
        m=store.row(db,'public');s=deepcopy(m.state)
        s.update(mode='meta',tick=24,planning_needed=False,memory_consolidation_due=True)
        s['agent_memory']={'power':{'working':[{'cycle_id':'unit-cycle','sol':0,'tick':1}], 'lessons':[]}}
        store.save(db,m,s,{'kind':'explicit unit-test setup'})
    calls=[]
    def answer(store,mid,operation,model,instructions,data,tools,transport=None):
        calls.append((model,[t['name'] for t in tools]))
        return [{'name':'record_lessons','arguments':{'lessons':[]}}],'unit-test-not-a-provider-response'
    monkeypatch.setattr(planner,'call',answer)
    assert planner.plan_once(store,mission_id='public')
    r=store.snapshot('public')['state']
    assert calls==[(SPECIALIST_MODEL,['record_lessons'])]
    assert not r['memory_consolidation_due'] and not r['planning_needed']
    assert not r.get('agent_cycle') and not r['agent_memory']['power']['working']


def test_calculated_experiment_clock_advances_without_rewriting_observation_epoch():
    from mission.conditions import mars_clock
    from mission.engine import effective_clock
    s=new_state('meta');epoch=1793750000
    s['environment']={'clock':mars_clock(epoch),'applied_tick':0,'geometry':{},'link':{}}
    original=deepcopy(s['environment'])
    s['tick']=24
    actual=effective_clock(s)
    assert actual['unix']==pytest.approx(epoch+s['spec']['tick_seconds']*24)
    # The original applied observation epoch remains untouched.
    assert s['environment']==original


def test_director_receives_explicit_policy_rejection_and_can_correct(monkeypatch):
    from mission import planner
    s=working();receipts=[];seen=[]
    bad={'name':'set_charging_policy','arguments':{'asset_ids':['excavator-1'],'reason':'Unit-test proposal','evidence_ids':['fsp-1']}}
    good=deepcopy(bad);good['arguments']['evidence_ids']=[s['spec']['package_id']]
    def correction(store,mid,operation,model,instructions,data,tools,transport=None):
        seen.append(data)
        assert 'fsp-1' not in tools[0]['parameters']['properties']['evidence_ids']['items']['enum']
        assert not s.get('charging_policies')
        return [good],'explicit-unit-test-response'
    monkeypatch.setattr(planner,'call',correction)
    planner.director_charging_orders(None,'public','unit-claim',s,[bad],receipts)
    assert len(seen)==1 and 'known sources' in seen[0]['validation_error']
    assert [r['validation'] for r in receipts]==['rejected','accepted']
    assert s['charging_policies']['excavator-1']['source_ids']==[s['spec']['package_id']]


def test_second_invalid_policy_is_visible_and_does_not_authorize(monkeypatch):
    from mission import planner
    s=working();receipts=[]
    bad={'name':'set_charging_policy','arguments':{'asset_ids':['excavator-1'],'reason':'Unit-test proposal','evidence_ids':['fsp-1']}}
    monkeypatch.setattr(planner,'call',lambda *a,**kw:([bad],'explicit-unit-test-response'))
    with pytest.raises(InvalidAction,match='remains rejected'):
        planner.director_charging_orders(None,'public','unit-claim',s,[bad],receipts)
    assert not s.get('charging_policies') and [r['validation'] for r in receipts]==['rejected','rejected']

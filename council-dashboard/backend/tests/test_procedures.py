"""Execution/physics acceptance using explicit synthetic *test fixtures*, never app defaults.

These tests exercise actual engine transitions, not provider generation or real robots.
"""
from copy import deepcopy
import json
import pytest
from mission.engine import new_state, modify, advance, start, asset_by_id, job_by_id, reasons, InvalidAction
from mission.procedures import create
from mission.physics import solve_temperature


def q(value, unit):
    return dict(value=value,unit=unit,origin='scenario assumption',approved=True,justification='Explicit isolated unit-test input, not a measured/design value')


def base(kind='battery-swap'):
    s=new_state('fixed-priority');s['failures_enabled']=False
    s.update(power_commissioned=True,power_capacity_kw=40)
    for j in s['jobs']:
        j.update(status='complete',done=j['target'],progress=1)
        s['milestones'][j['id']]=True
    target=asset_by_id(s,'excavator-1')
    target['soc_wh']=100
    if kind=='repair':target.update(available=False,failed_component='drive')
    if kind=='offload':target=asset_by_id(s,'habitat-1')
    p=dict(id='fixture-procedure',kind=kind,title='Test '+kind,target_id=target['id'],interface='fixture-compatible-interface',
           stages=[dict(name='Isolate and connect',duration=q(.25,'h'),grid_power=q(1,'kW')),
                   dict(name='Execute and verify',duration=q(.5,'h'),grid_power=q(3,'kW'))])
    if kind=='repair':p['component']='drive'
    if kind=='offload':
        job_by_id(s,'shielding').update(done=0,progress=0,status='pending');s['milestones']['shielding']=False
        p.update(rated_payload=q(target['mass_kg'],'kg'),initial_location='lander',support_verified=True,
                 stability_verified=True,attachment_verified=True,verification_basis='Explicit test fixture, not flight design')
        p['lifting']=dict(gravity=q(3.7,'m/s2'),travel=q(10,'m'),speed=q(.01,'m/s'),reach=q(5,'m'),
             restoring_moment=q(4e6,'N m'),structural_moment_limit=q(4e6,'N m'),cable_load_limit=q(1e6,'N'),
             braking_capacity=q(10000,'W'),safety_factor=q(2,'1'),motion_stage='Execute and verify')
        p['rotation']=dict(initial_angle=q(0,'deg'),final_angle=q(90,'deg'),angular_speed=q(.1,'deg/s'),
             cg_offset=q(2,'m'),torque_limit=q(2e6,'N m'),rotation_stage='Execute and verify')
    spare=dict(id='spare-001',kind='module' if kind=='repair' else 'battery',interface=p['interface'],
               compatible_asset_id=target['id'],manifest_basis='Isolated test manifest',approved=True)
    if kind=='repair':spare['component']='drive'
    else:spare.update(capacity=q(target.get('battery_wh',1410),'Wh'),initial_charge=q(800,'Wh'))
    charge_profile={**deepcopy(p),'id':'fixture-charge','kind':'battery-charge','title':'Charge removed test pack','charge_efficiency':q(1,'1')}
    config=dict(profiles=[p,charge_profile] if kind=='battery-swap' else [p],inventory=[] if kind=='offload' else [spare],
                service_equipment={'fsp-1':dict(interface=p['interface'],approved=True,justification='Test-only service capability; not real reactor hardware')})
    return modify(s,{'procedures':config})


def order(s):
    return create(s,'fixture-procedure',['fsp-1'],None if s['procedure_configuration']['profiles']['fixture-procedure']['kind']=='offload' else 'spare-001','test operator','Explicit fixture procedure')


def run(s,jid):
    start(s,jid,['fsp-1'],'fixture','fixed-priority',[s['spec']['package_id']])
    return advance(s)


def test_swap_preserves_both_packs_and_does_not_create_energy():
    s=base();jid=order(s);r=run(s,jid)
    assert job_by_id(r,jid)['status']=='complete'
    assert asset_by_id(r,'excavator-1')['soc_wh']==800
    old=r['inventory']['initial-pack:excavator-1']
    assert old['soc_wh']==100 and old['status']=='stored'
    assert r['inventory']['spare-001']['soc_wh'] is None
    assert r['energy_used_kwh']==pytest.approx(1.75)
    assert job_by_id(r,jid)['procedure']['result']['verification'].startswith('Deterministic')
    assert 'spare spare-001' in r['capital_unestimated']
    assert next(e for e in r['ledger'] if e['kind']=='spare-manifest')['amount_usd'] is None


def test_repair_installs_spare_records_failed_part_and_keeps_battery():
    s=base('repair');jid=order(s);r=run(s,jid)
    a=asset_by_id(r,'excavator-1')
    assert a['available'] and a['failed_component'] is None and a['soc_wh']==100
    assert a['installed_modules']['drive']=='spare-001'
    assert r['inventory']['spare-001']['status']=='installed'
    assert r['inventory']['initial-module:excavator-1:drive']['status']=='failed'


def test_offload_requires_prepared_trench_and_delays_shielding():
    s=base('offload');jid=order(s)
    assert jid in job_by_id(s,'shielding')['dependencies']
    assert jid in s['additional_readiness_jobs']
    assert not s['milestones']['ready']
    r=run(s,jid)
    assert asset_by_id(r,'habitat-1')['location']=='prepared-site'
    assert asset_by_id(r,'habitat-1')['orientation_deg']==90
    assert asset_by_id(r,'habitat-1')['descent_remaining_m']==0
    assert job_by_id(r,'shielding')['status']=='running'


def test_unordered_offload_cannot_be_bypassed_by_readiness_or_shielding():
    s=base('offload')
    assert any('lander' in x for x in reasons(s,job_by_id(s,'shielding'),['excavator-1']))
    r=advance(s)
    assert not r['milestones']['ready'] and job_by_id(r,'shielding')['done']==0


def test_cannot_spend_spare_twice_or_work_on_locked_target():
    s=base();jid=order(s)
    before=deepcopy(s)
    with pytest.raises(InvalidAction):order(s)
    assert s==before
    j=job_by_id(s,'trench');j['status']='pending'
    assert any('other work' in r for r in reasons(s,j,['excavator-1']))
    with pytest.raises(InvalidAction):start(s,jid,['excavator-2'],'fixture','fixed-priority',[s['spec']['package_id']])
    from mission.engine import place_order
    repair=base('repair');order(repair);before=deepcopy(repair)
    with pytest.raises(InvalidAction,match='reserved for service'):place_order(repair,{'asset_id':'excavator-1'})
    assert repair==before
    repair=base('repair');repair['orders']=[{'asset_id':'excavator-1','status':'in transit'}]
    with pytest.raises(InvalidAction,match='already in transit'):order(repair)


def test_grid_loss_holds_procedure_without_spending_or_consuming_spare():
    s=base();jid=order(s)
    start(s,jid,['fsp-1'],'fixture','fixed-priority',[s['spec']['package_id']])
    s['power_capacity_kw']=0
    r=advance(s)
    assert job_by_id(r,jid)['done']==0 and r['energy_used_kwh']==0
    assert r['inventory']['spare-001']['status']=='stored'
    assert r['inventory']['spare-001']['reserved_by']==jid
    r['power_capacity_kw']=40
    r=run(r,jid)
    assert r['energy_used_kwh']==pytest.approx(1.75)


def test_serialized_restart_does_not_repeat_completed_effects():
    s=base();jid=order(s);r=run(s,jid)
    r=advance(json.loads(json.dumps(r)))
    assert r['energy_used_kwh']==pytest.approx(1.75)
    assert sum(a['kind']=='battery' for a in r['inventory'].values())==2
    assert len(job_by_id(r,jid)['procedure']['execution'])==1


def test_procedure_refuses_unsupported_input_and_undersized_crane():
    s=base('offload')
    config=s['procedure_configuration']
    raw=dict(profiles=list(config['profiles'].values()),inventory=[],service_equipment=config['equipment'])
    raw['profiles'][0]['rated_payload']=q(1,'kg')
    original=new_state('fixed-priority');before=deepcopy(original)
    with pytest.raises(InvalidAction,match='rated below'):modify(original,{'procedures':raw})
    assert original==before
    raw['profiles'][0]['rated_payload']=q(90000,'kg')
    raw['profiles'][0]['stages'][0]['duration']['approved']=False
    with pytest.raises(InvalidAction,match='approval'):modify(original,{'procedures':raw})


def thermal_profile():
    return dict(variable='battery_temperature',heat_capacity=q(10000,'J/K'),conductance=q(1,'W/K'),
                radiating_area=q(1,'m2'),emissivity=q(.8,'1'),initial_temperature=q(273.15,'K'),
                ambient_temperature=q(230,'K'),radiative_temperature=q(200,'K'),housekeeping=q(10,'W'),
                heater_max=q(50,'W'),heater_setpoint=q(273.15,'K'),heat_fraction=q(.2,'1'),absorbed_solar=q(0,'W'))


def test_heat_solver_conserves_balance_and_cools_without_heat():
    t,residual=solve_temperature(300,3600,10000,1,200,1,.8,200,0)
    assert 200<t<300
    assert abs(residual)<1e-6


def test_thermal_energy_is_drawn_from_battery_and_is_not_sensor_data():
    s=new_state('meta');s['planning_needed']=False;s['failures_enabled']=False
    s=modify(s,{'equipment_physics':{'rover-1':thermal_profile()}})
    a=asset_by_id(s,'rover-1');a['generator_w']=0;before=a['soc_wh']
    r=advance(s);a=asset_by_id(r,'rover-1');p=r['equipment_physics']['rover-1']
    receipt=p['history'][-1]
    assert before-a['soc_wh']==pytest.approx(receipt['housekeeping_wh']+receipt['heater_wh'])
    assert abs(receipt['thermal_balance_residual_j'])<1e-5
    assert 'scenario' in r['equipment_conditions']['rover-1']['battery_temperature']['classification']


def test_housekeeping_brownout_cannot_produce_free_heat_or_motion():
    s=new_state('meta');s['planning_needed']=False
    s=modify(s,{'equipment_physics':{'rover-1':thermal_profile()}})
    a=asset_by_id(s,'rover-1');a.update(soc_wh=0,generator_w=0)
    r=advance(s);receipt=r['equipment_physics']['rover-1']['history'][-1]
    assert receipt['housekeeping_wh']==0 and receipt['heater_wh']==0
    assert receipt['housekeeping_unserved_wh']>0
    assert any('housekeeping' in x for x in reasons(r,job_by_id(r,'survey'),['rover-1']))


def test_removed_pack_recharges_from_grid_then_can_be_reused():
    s=base();s=run(s,order(s))
    jid=create(s,'fixture-charge',['fsp-1'],'initial-pack:excavator-1','test','Recharge the removed fixture pack')
    r=run(s,jid)
    old=r['inventory']['initial-pack:excavator-1']
    assert old['soc_wh']==pytest.approx(old['capacity_wh']) and old['reserved_by'] is None
    assert r['energy_used_kwh']==pytest.approx(1.75+(1410-100)/1000)
    assert job_by_id(r,jid)['done']<job_by_id(r,jid)['target']
    jid=create(r,'fixture-procedure',['fsp-1'],old['id'],'test','Reuse recharged pack')
    r=run(r,jid)
    assert asset_by_id(r,'excavator-1')['soc_wh']==pytest.approx(1410)
    assert r['inventory']['spare-001']['soc_wh']==800
    assert len(r['inventory'])==2


def test_unsafe_offload_stability_is_rejected_without_mutation():
    s=base('offload');cfg=s['procedure_configuration']
    raw=dict(profiles=list(cfg['profiles'].values()),inventory=[],service_equipment=cfg['equipment'])
    raw['profiles'][0]['lifting']['restoring_moment']=q(0,'N m')
    source=new_state('fixed-priority');before=deepcopy(source)
    with pytest.raises(InvalidAction,match='moment exceeds'):modify(source,{'procedures':raw})
    assert source==before


def test_persisted_procedure_restart_retains_serials_and_spending(tmp_path,request):
    from conftest import make_store
    store=make_store(tmp_path,request);store.initialize()
    s=base();jid=order(s);s=run(s,jid)
    with store.transaction() as db:
        m=store.row(db,'public');store.save(db,m,s,{'kind':'explicit test fixture'})
    recovered=store.snapshot('public')['state']
    assert recovered['inventory']==s['inventory']
    r=store.step(recovered)
    assert r['energy_used_kwh']==s['energy_used_kwh']
    assert r['inventory']==s['inventory']


def test_actual_usage_reconciles_before_invalid_tool_arguments(tmp_path,request,monkeypatch):
    from conftest import make_store
    from mission import planner
    from mission.provider import cost_usd,SPECIALIST_MODEL
    from mission.store import InferenceReceipt,Budget
    store=make_store(tmp_path,request);store.initialize()
    monkeypatch.setattr(planner,'credential',lambda:('not-a-real-key-test-fixture','explicit unit-test injection'))
    usage={'input_tokens':5,'output_tokens':3}
    monkeypatch.setattr(planner,'send',lambda *args:({'id':'unit-test-response-not-live','model':SPECIALIST_MODEL,'usage':usage,
        'output':[{'type':'function_call','name':'submit_work_order','arguments':'{invalid'}]},{}))
    with pytest.raises(InvalidAction,match='unparseable'):
        planner.call(store,'public','unit-test-invalid-args',SPECIALIST_MODEL,'unit test',{},[])
    with store.transaction() as db:
        r=db.get(InferenceReceipt,'unit-test-invalid-args').record
        assert r['status']=='received; proposal invalid'
        assert r['actual_usd']==pytest.approx(cost_usd(SPECIALIST_MODEL,usage))
        assert r['response_id']=='unit-test-response-not-live'
        for key in r['budget_keys']:assert db.get(Budget,key).charged==pytest.approx(r['actual_usd'])


def test_climate_boundary_requires_pinned_evidence_and_records_interpolation():
    from mission.conditions import mars_clock
    s=new_state('meta');s['planning_needed']=False
    profile=thermal_profile();profile['climate_boundary']={'version_id':'unit-fixture-climate','variable':'air_temperature_k'}
    with pytest.raises(InvalidAction,match='mission-pinned'):modify(s,{'equipment_physics':{'rover-1':profile}})
    unix=1793750000
    s['environment']={'clock':mars_clock(unix),'applied_tick':0}
    s['source_pins']={'arcadia-climate':'unit-fixture-climate'}
    s['physics_evidence']={'unit-fixture-climate':{'content_hash':'unit-test-only','points':[{'local_time_h':0,'value':220},{'local_time_h':24,'value':244}]}}
    s=modify(s,{'equipment_physics':{'rover-1':profile}})
    r=advance(s)
    record=r['equipment_physics']['rover-1']['history'][-1]['climate_boundary']
    assert record['source_version']=='unit-fixture-climate'
    assert record['ambient_temperature_k']==pytest.approx(220+record['local_time_h'])
    assert record['content_hash']=='unit-test-only'


def test_component_fault_injection_is_explicit_and_does_not_fabricate_telemetry():
    s=new_state('fixed-priority')
    r=modify(s,{'component_faults':{'excavator-1':{'component':'drive','basis':'Unit-test fault injection','approved':True}}})
    assert not asset_by_id(r,'excavator-1')['available']
    assert asset_by_id(r,'excavator-1')['failed_component']=='drive'
    assert r['faults'][-1]['classification']=='operator-injected scenario, not telemetry'
    assert asset_by_id(s,'excavator-1')['available']


def test_director_created_procedure_records_actual_director_model_identity():
    from mission.planner import execute_tool
    from mission.provider import DIRECTOR_MODEL
    s=base()
    r=execute_tool(s,'create_procedure',dict(profile_id='fixture-procedure',service_ids=['fsp-1'],spare_id='spare-001',summary='Unit test'),'director')
    assert job_by_id(s,r['job_id'])['procedure']['actor']=='director / '+DIRECTOR_MODEL

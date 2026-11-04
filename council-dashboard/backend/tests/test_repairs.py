"""Regression probes for conservation and provenance. All numeric experiment inputs below are test fixtures."""
from copy import deepcopy
import pytest
from mission.engine import new_state, advance, start, set_standby, modify, job_by_id, asset_by_id, InvalidAction
from mission.agents import remember, recall, due_for_consolidation


def water_state():
    s = new_state('fixed-priority'); s['failures_enabled'] = False
    s.update(power_commissioned=True,power_capacity_kw=s['spec']['assets'][4]['output_kw'])
    for jid in ('survey','power','drill'):
        job_by_id(s,jid)['status'] = 'complete'; s['milestones'][jid] = True
    start(s,'well-establish',['rodwell-1'],'test fixture establishment','fixed-priority',[s['spec']['package_id']])
    s=advance(s)
    assert job_by_id(s,'water')['status']=='running'
    return s


def test_one_tick_standby_pauses_exactly_one_step():
    s=new_state('fixed-priority');s['failures_enabled']=False
    start(s,'survey',['rover-1'],'test fixture','fixed-priority',[s['spec']['package_id']])
    basis=[dict(observation_id='fixture',kind='weather-obs',station='msl',variable='air_min_c',value=-70,record_hash='fixture',interpretation='test only')]
    set_standby(s,['rover-1'],1,'test fixture','test',basis)
    s=advance(s);assert job_by_id(s,'survey')['done']==0
    s=advance(s);assert job_by_id(s,'survey')['done']>0


def test_water_cannot_exceed_feed_or_storage():
    s=modify(water_state(),{'production':{'water_feed_remaining_kg':2,'water_storage_capacity_kg':1}})
    s=advance(s)
    assert s['production']['water_stored_kg']==1
    assert s['production']['water_feed_remaining_kg']==1
    s=advance(s);assert job_by_id(s,'water')['status']=='blocked'
    assert s['resources']['water_kg']==1


def test_operating_allocation_pauses_without_spending():
    s=water_state();s=modify(s,{'operating_spending_limit_usd':s['spent_usd']})
    r=advance(s)
    assert r['status']=='paused' and r['spent_usd']==s['spent_usd'] and job_by_id(r,'water')['done']==0


def test_production_change_rejects_invalid_values_atomically():
    s=water_state();before=deepcopy(s)
    with pytest.raises(InvalidAction):modify(s,{'production':{'rate_multiplier':float('nan')}})
    assert s==before
    with pytest.raises(InvalidAction):modify(s,{'production':{'rate_multiplier':2}})


def test_replacement_has_fresh_state_and_preserves_history():
    s=new_state('meta');s['failures_enabled']=False
    old=asset_by_id(s,'excavator-1');old.update(available=False,soc_wh=12,standby_until_tick=100)
    s['orders']=[dict(id='fixture',asset_id=old['id'],asset_name=old['name'],status='in transit',arrival_tick=1,arrival_utc='2026-11-03T00:00:00Z')]
    r=advance(s);a=asset_by_id(r,'excavator-1')
    assert a['available'] and a['soc_wh']==a['battery_wh'] and 'standby_until_tick' not in a
    assert a['generation']==1 and a['delivered_by']=='fixture'
    assert not old['available'] and old['soc_wh']==12


def test_unknown_power_cannot_be_waived():
    s=water_state();j=job_by_id(s,'water');j['power_per_asset_kw']=None
    s=advance(s)
    assert job_by_id(s,'water')['status']=='blocked' and s['resources']['water_kg']==0


def test_director_retains_and_consolidates_its_plan():
    s=new_state();c={'id':'fixture-cycle','assessments':[],'director':{'priority':s['priority'],'summary':'fixture'}}
    remember(s,c,[])
    assert recall(s,'director')['working'][0]['plan']['summary']=='fixture'
    s['tick']=24;assert due_for_consolidation(s,'director')


def test_rover_reference_battery_energy_is_conserved():
    s=new_state('fixed-priority');s['failures_enabled']=False
    start(s,'survey',['rover-1'],'test fixture','fixed-priority',[s['spec']['package_id']])
    before=asset_by_id(s,'rover-1')['soc_wh'];r=advance(s);a=asset_by_id(r,'rover-1')
    assert before-a['soc_wh']==pytest.approx(job_by_id(r,'survey')['done']*a['energy_wh_per_unit'])


def test_component_envelopes_use_internal_units_and_do_not_accept_biological_dose():
    s=new_state('fixed-priority');s['failures_enabled']=False
    s=modify(s,{'equipment_conditions':{'rover-1':{'battery_temperature':{'value':-30,'unit':'degC','basis':'test fixture'}}}})
    with pytest.raises(InvalidAction,match='outside qualified'):
        start(s,'survey',['rover-1'],'test','fixed-priority',[s['spec']['package_id']])
    with pytest.raises(InvalidAction,match='matching unit'):
        modify(s,{'equipment_conditions':{'rover-1':{'processor_total_dose':{'value':1,'unit':'mSv','basis':'test fixture'}}}})


@pytest.mark.parametrize('package_id',['moon-south-pole-v1','earth-regolith-lab-v1'])
def test_environment_packages_do_not_transplant_mars_jobs(package_id):
    s=new_state('fixed-priority',package_id);s['failures_enabled']=False
    assert {j['id'] for j in s['jobs']}=={'power','excavate'}
    assert s['spec']['environment'] in ('moon','earth') and s['environment'] is None
    for _ in range(180):s=advance(s)
    assert job_by_id(s,'power')['status']=='complete' and job_by_id(s,'excavate')['done']>0


def test_seed_ensemble_is_reproducible_and_records_actual_seeds():
    from mission.robustness import ensemble
    s=new_state('fixed-priority')
    a=ensemble(s,['test-1','test-2'],3)
    assert a==ensemble(s,['test-1','test-2'],3)
    assert [r['seed'] for r in a['results']]==['test-1','test-2']


def test_fault_suite_keeps_identical_start_and_reports_constraints():
    from mission.robustness import fault_suite
    r=fault_suite(new_state('fixed-priority'),['test-1'],8)
    assert set(r['cases'])=={'nominal','power-loss','delayed-excavation','equipment-failure'}
    assert len({c['input_hash'] for c in r['cases'].values()})==1
    assert all(c['results'][0]['inference_calls']==0 for c in r['cases'].values())
    assert all(c['results'][0]['constraint_violations']==[] for c in r['cases'].values())


def test_component_violation_stops_work_with_its_actual_cause():
    s=new_state('fixed-priority');s['failures_enabled']=False
    start(s,'survey',['rover-1'],'test fixture','fixed-priority',[s['spec']['package_id']])
    s=modify(s,{'equipment_conditions':{'rover-1':{'battery_temperature':{'value':-30,'unit':'degC','basis':'test scenario'}}}})
    r=advance(s)
    assert job_by_id(r,'survey')['status']=='blocked'
    assert 'battery_temperature' in job_by_id(r,'survey')['reason']
    assert job_by_id(r,'survey')['done']==0


def test_full_battery_wakes_planning_for_unassigned_work():
    from mission.engine import charge
    s=new_state('meta');s.update(power_commissioned=True,power_capacity_kw=40,planning_needed=False,failures_enabled=False)
    a=asset_by_id(s,'excavator-1');a['soc_wh']=a['battery_wh']-1
    charge(s,['excavator-1'],'test fixture','test fixture')
    result=advance(s)
    assert not asset_by_id(result,'excavator-1')['charging'] and result['planning_needed']

"""Actual deterministic model execution; no provider calls or sensor fixtures."""
from copy import deepcopy
import pytest
from mission.engine import new_state,advance,start,modify,job_by_id,InvalidAction
from mission.water import assert_conservation


def drilled():
    s=new_state('fixed-priority');s['failures_enabled']=False
    for j in s['jobs']:
        if j['id'] in ('power','survey','drill'):
            j.update(status='complete',done=j['target'],progress=1.0)
            s['milestones'][j['id']]=True
    s.update(power_commissioned=True,power_capacity_kw=s['spec']['parameters']['power.fsp_output_kwe']['value'])
    s['priority']=['well-establish','water','trench','shielding','power','survey','drill']
    return s


def test_withdrawal_cannot_skip_establishment_even_if_dependency_is_tampered():
    s=drilled();job_by_id(s,'water')['dependencies']=[]
    with pytest.raises(InvalidAction,match='reserve before withdrawal'):
        start(s,'water',['rodwell-1'],'Unit-test attempt','fixed-priority',[s['spec']['package_id']])


def test_establishment_consumes_real_model_feed_and_power_without_delivering_water():
    s=drilled();initial=s['production']['water_feed_remaining_kg']
    start(s,'well-establish',['rodwell-1'],'Unit-test establishment','fixed-priority',[s['spec']['package_id']])
    s=advance(s);w=s['well']
    assert w['phase']=='established' and w['qualified_liquid_kg']==pytest.approx(w['reserve_kg'])
    assert s['production']['water_stored_kg']==0 and s['resources']['water_kg']==0
    assert s['production']['water_feed_remaining_kg']==pytest.approx(initial-w['contained_kg'])
    energy=sum(e['energy_kwh'] for e in s['physical_ledger']if e['job_id']=='well-establish')
    assert energy==pytest.approx(s['spec']['parameters']['rodwell.establishment_effective_kwh']['value'])
    assert_conservation(s)


def test_heat_loss_keeps_mass_and_reconditioning_uses_energy_not_new_feed():
    s=drilled();start(s,'well-establish',['rodwell-1'],'Unit-test establishment','fixed-priority',[s['spec']['package_id']]);s=advance(s)
    mass=s['well']['contained_kg'];feed=s['production']['water_feed_remaining_kg'];energy=s['energy_used_kwh'];rated=s['power_capacity_kw']
    s=advance(modify(s,{'power_capacity_kw':0}))
    assert s['well']['phase']=='requalification-required' and s['well']['qualified_liquid_kg']==0
    assert s['well']['contained_kg']==mass and s['production']['water_stored_kg']==0
    s=modify(s,{'power_capacity_kw':rated})
    for _ in range(3):
        s=advance(s)
        if s['well']['conditioning_runs']==2:break
    assert s['well']['conditioning_runs']==2 and s['energy_used_kwh']>energy
    assert s['production']['water_feed_remaining_kg']==pytest.approx(feed)
    assert_conservation(s)


def test_restart_replays_establishment_without_duplicate_mass_or_spending():
    s=drilled();start(s,'well-establish',['rodwell-1'],'Unit-test establishment','fixed-priority',[s['spec']['package_id']])
    s=modify(s,{'production':{'rate_multiplier':0.5}});s=advance(s)
    assert s['well']['phase']=='conditioning'
    import json
    reloaded=json.loads(json.dumps(s));expected=advance(deepcopy(s));actual=advance(reloaded)
    assert actual==expected and actual['well']['conditioning_runs']==1
    assert_conservation(actual)


def test_nominal_whole_mission_delivers_target_with_reserve_separate():
    s=new_state('fixed-priority');s['failures_enabled']=False
    for _ in range(2400):
        s=advance(s)
        if s['milestones']['ready']:break
    assert s['milestones']['ready'] and all(j['status']=='complete'for j in s['jobs'])
    assert s['well']['contained_kg']==pytest.approx(s['well']['reserve_kg'])
    assert s['production']['water_stored_kg']==pytest.approx(job_by_id(s,'water')['target'])
    assert s['resources']['water_kg']==s['production']['water_stored_kg']
    assert_conservation(s)
    # A pending extra batch with no feed/storage must not make the controller
    # repeatedly recondition the same reserve or consume useless grid energy.
    from mission.engine import instantiate_job
    instantiate_job(s,'water-batch','explicit unit-test actor','Unit-test exhausted allocation')
    runs=s['well']['conditioning_runs']
    for _ in range(8):s=advance(s)
    assert s['well']['conditioning_runs']==runs
    assert job_by_id(s,'well-establish')['status']=='complete'
    assert not any(j.get('template_id')=='well-recondition'for j in s['jobs'])


def test_upgrade_preserves_old_stock_and_history_without_inventing_reserve(tmp_path,request,monkeypatch):
    from conftest import make_store
    from mission import cli
    store=make_store(tmp_path,request);store.initialize()
    with store.transaction() as db:
        m=store.row(db,'public');old=deepcopy(m.state)
        old.pop('well');old['spec'].pop('water_model')
        old['spec']['hash']='unit-test-legacy-spec'
        old['jobs']=[j for j in old['jobs']if j['id']!='well-establish']
        old['priority'].remove('well-establish');old['milestones'].pop('well-establish')
        job_by_id(old,'water')['dependencies']=['drill','power']
        old['production'].pop('initial_feed_allocation_kg')
        store.save(db,m,old,{'kind':'explicit legacy unit fixture'})
        revision=m.revision;feed=old['production']['water_feed_remaining_kg']
    monkeypatch.setattr(cli,'Store',lambda:store)
    monkeypatch.setattr('sys.argv',['mission.cli','upgrade']);cli.main()
    upgraded=store.snapshot('public')['state']
    assert upgraded['status']=='paused' and upgraded['well']['contained_kg']==0
    assert upgraded['production']['water_feed_remaining_kg']==feed
    assert 'well-establish' in job_by_id(upgraded,'water')['dependencies']
    from mission.store import Revision
    from sqlalchemy import select
    with store.transaction() as db:
        retained=db.scalar(select(Revision).where(Revision.mission_id=='public',Revision.revision==revision))
        assert retained.state==old

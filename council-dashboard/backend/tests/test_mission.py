from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import pytest
from mission.engine import new_state, advance, start, modify, InvalidAction
from mission.spec import digest
from mission.store import Store

def run(s,n=72):
    for _ in range(n): s=advance(s)
    return s

def test_complete_and_physical_conservation():
    original=new_state(); s=run(original)
    assert s['status']=='complete'
    assert s['resources']['water_kg']==125
    assert s['spent_usd']==65000 and s['committed_usd']==0
    for resource,value in original['resources'].items():
        assert s['resources'][resource]==pytest.approx(value+sum(x['amount'] for x in s['physical_ledger'] if x['resource']==resource))
    assert len(s['decisions'])==6
    assert all(d['outcome'] for d in s['decisions'])

def test_inputs_dependencies_and_double_spend():
    s=new_state()
    with pytest.raises(InvalidAction): start(s,'water')
    start(s,'survey')
    with pytest.raises(InvalidAction): start(s,'survey')
    assert s['committed_usd']==3000
    assert s['resources']['energy_kwh']==592

def test_priority_changes_water_timing():
    a=new_state(); b=modify(a,{'priority':['survey','power','excavate','habitat','water','verify','maintenance']})
    a=run(a,15); b=run(b,15)
    assert a['resources']['water_kg']==125 and b['resources']['water_kg']==0
    assert digest(run(new_state()))==digest(run(new_state()))

def test_fault_and_recovery():
    s=run(new_state(),7)
    s=modify(s,{'fault':'equipment-failure'})
    assert run(s)['status']=='complete'
    s=modify(run(new_state(),11),{'fault':'power-loss'})
    stalled=run(s,3)
    assert any(j['reason'].startswith('Execution held') for j in stalled['jobs'])
    assert run(modify(stalled,{'fault':'restore-power'}))['status']=='complete'

def test_low_yield_cannot_claim_readiness():
    s=run(modify(new_state(),{'water_yield':.1}))
    assert not s['milestones']['ready']
    assert s['resources']['water_kg']==50

@pytest.fixture
def store(tmp_path):
    s=Store('sqlite:///'+str(tmp_path/'mission.db')); s.initialize(); return s

def test_fork_isolation_ownership_and_limits(store):
    public=store.snapshot('public')
    fork=store.fork(public['revision'],'alice')
    with pytest.raises(PermissionError): store.snapshot(fork['id'],'bob')
    with pytest.raises(PermissionError): store.control('public','alice',1,'run',ticks=1)
    with pytest.raises(InvalidAction): store.fork(1,'alice')
    updated=store.control(fork['id'],'alice',fork['revision'],'configure',{'water_yield':.1})
    assert store.snapshot('public')==public
    store.control(fork['id'],'alice',updated['revision'],'run',ticks=72)
    with pytest.raises(InvalidAction): store.control(fork['id'],'alice',updated['revision']+1,'run',ticks=1)

def test_concurrent_ticks_and_restart(store):
    with ThreadPoolExecutor(max_workers=4) as pool: list(pool.map(lambda _:store.tick(),range(4)))
    assert store.snapshot('public')['state']['tick']==1
    restarted=Store(str(store.engine.url))
    assert restarted.snapshot('public')==store.snapshot('public')
    exported=store.export('public')
    before=exported['history'][0]['state']; after=exported['history'][1]['state']
    assert advance(before)==after
    assert all(v in exported['sources'] for v in after['source_pins'])

def test_concurrent_forks(store):
    def attempt(_):
        try: return store.fork(1,'alice')['id']
        except InvalidAction: return None
    with ThreadPoolExecutor(max_workers=4) as pool: results=list(pool.map(attempt,range(4)))
    assert len([x for x in results if x])==1

"""Reproducible seed ensembles. Uses the actual simulation harness, never generates model receipts."""
from copy import deepcopy
from statistics import mean
from .engine import advance, modify, InvalidAction
from .spec import digest


def ensemble(snapshot, seeds, max_ticks, faults=()):
    """Matched initial state and scheduled faults for each seed. A benchmark is explicitly fixed-priority.
    faults: [{after_ticks: int, changes: configuration}], applied before the named step.
    A caller can compare these records to provider-backed agent experiments; this function makes no provider claim.
    """
    if not seeds or len(set(map(str,seeds))) != len(seeds):
        raise ValueError('Supply distinct failure seeds')
    if not isinstance(max_ticks,int) or not 1 <= max_ticks <= 24*400:
        raise ValueError('Horizon must be 1 to 9600 ticks')
    for fault in faults:
        if not isinstance(fault,dict) or set(fault)!={'after_ticks','changes'} or type(fault['after_ticks']) is not int or not 0<=fault['after_ticks']<max_ticks:
            raise ValueError('Each fault needs an in-horizon integer after_ticks and validated changes')
    from .store import Store
    harness = Store.__new__(Store)  # step() needs no database; logistics loads the pinned package normally
    rows=[]
    for seed in seeds:
        s=deepcopy(snapshot);s.update(mode='fixed-priority',status='active',planning_needed=False,reliability_seed=str(seed),failures_enabled=True)
        s.pop('planning_claim',None)
        violations=[]
        for elapsed in range(max_ticks):
            for fault in faults:
                if fault['after_ticks']==elapsed:s=modify(s,fault['changes']);s['mode']='fixed-priority'
            if s['milestones']['ready'] or s['status']!='active':break
            s=harness.step(s)
            if s['power_used_kw']>s['power_capacity_kw']+1e-8 or s['power_used_kw']<-1e-8:
                violations.append({'tick':s['tick'],'kind':'power-conservation'})
            if any(a.get('soc_wh',0)<-1e-8 or a.get('soc_wh',0)>a.get('battery_wh',float('inf'))+1e-8 for a in s['assets']):
                violations.append({'tick':s['tick'],'kind':'battery-conservation'})
            if any(j['status']=='complete' and any(not s['milestones'].get(dep) for dep in j['dependencies']) for j in s['jobs']):
                violations.append({'tick':s['tick'],'kind':'prerequisite'})
        rows.append({'seed':str(seed),'ready':s['milestones']['ready'],'readiness_tick':s['readiness_tick'],
                     'elapsed_ticks':s['tick']-snapshot['tick'],'energy_kwh':s['energy_used_kwh']-snapshot['energy_used_kwh'],
                     'operations_usd':s['spent_usd']-snapshot['spent_usd'],'failures':sum(f['kind']=='failure' for f in s['faults']),
                     'resources':deepcopy(s['resources']),'constraint_violations':violations,'inference_calls':0,'inference_usd':0,
                     'state_hash':digest(s),'blocked':{j['id']:j['reason'] for j in s['jobs'] if j['status']=='blocked'}})
    ready=[r['readiness_tick'] for r in rows if r['ready']]
    return {'method':'fixed-priority seeded simulation ensemble; no model calls','input_hash':digest(snapshot),'faults':list(faults),
            'horizon_ticks':max_ticks,'results':rows,'readiness_fraction':sum(r['ready'] for r in rows)/len(rows),
            'mean_readiness_tick':mean(ready) if ready else None,'mean_energy_kwh':mean(r['energy_kwh'] for r in rows)}


def fault_suite(snapshot, seeds, max_ticks=72):
    """Four matched scenarios from a commissioned-power snapshot. This function never invokes an LLM.

    A delay is an explicit six-step equipment hold, not an invented environmental measurement.
    Failure schedules disable a unit; natural random failures remain enabled under each seed.
    """
    if max_ticks<8:raise ValueError('Fault suite needs at least eight steps')
    if snapshot['spec'].get('environment','mars')!='mars':raise InvalidAction('These fault cases target the Mars equipment package')
    s=deepcopy(snapshot);s.update(mode='fixed-priority',failures_enabled=False,status='active')
    from .conditions import snapshot as conditions
    from .engine import apply_environment
    # Fixed reproducible epoch, recorded in output; geometry is computed, not a fabricated feed.
    epoch=1793664000.0
    v=s['spec']['parameters']
    if not s.get('environment'):
        apply_environment(s,conditions(epoch,v['comms.mars_soi_km']['value'],None,v['comms.conjunction_sun_sep_deg']['value'],s['spec']['tick_seconds']))
    for _ in range(24*30):
        if s['power_commissioned']:break
        s=advance(s)
    if not s['power_commissioned']:raise InvalidAction('Cannot prepare a commissioned-power snapshot')
    s['failures_enabled']=True
    rated=s['power_capacity_kw']
    cases={'nominal':[],
           'power-loss':[{'after_ticks':0,'changes':{'power_capacity_kw':0}},{'after_ticks':6,'changes':{'power_capacity_kw':rated}}],
           'delayed-excavation':[{'after_ticks':0,'changes':{'equipment':{'excavator-1':False,'excavator-2':False}}},
                                 {'after_ticks':6,'changes':{'equipment':{'excavator-1':True,'excavator-2':True}}}],
           'equipment-failure':[{'after_ticks':0,'changes':{'equipment':{'excavator-1':False}}}]}
    return {'scope':'Deterministic fixed-priority fault experiments; not live Meta validation or evidence of planning superiority.',
            'package_hash':s['spec']['package_hash'],'starting_tick':s['tick'],'clock_epoch_unix':s['environment']['clock']['unix'],
            'cases':{name:ensemble(s,seeds,max_ticks,faults) for name,faults in cases.items()}}

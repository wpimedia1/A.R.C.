"""Real Meta versus fixed-priority controlled-fault acceptance. No transport doubles.

Faults are explicitly injected experiments, never NASA observations. Both planners
receive identical prepared state, source pins, clock, seed and fault schedule.
"""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import sys
import time
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'council-dashboard/backend'))
from mission.engine import advance,release,stop_charging,modify,event
from mission.store import Store
from mission.planner import plan_once
from mission.spec import digest
from verify_agent_loop import acceptance_store


def prepare(bundle):
    state=deepcopy(bundle['snapshot']['state']);state.update(status='active',mode='fixed-priority',planning_needed=False,failures_enabled=False)
    state.pop('planning_claim',None)
    for job in state['jobs']:
        if job['status'] in ('running','review'):
            release(state,job,'pending','Explicit baseline preparation');job.pop('authorization',None)
    for asset in state['assets']:stop_charging(state,asset,'Explicit baseline preparation')
    for _ in range(720):
        if state['power_commissioned']:break
        state=advance(state)
    if not state['power_commissioned']:raise RuntimeError('Baseline preparation did not commission power')
    for job in state['jobs']:
        if job['status'] in ('running','review'):
            release(state,job,'pending','Common snapshot before the planner comparison');job.pop('authorization',None)
    for asset in state['assets']:stop_charging(state,asset,'Common snapshot before comparison')
    state.update(reliability_seed='controlled-acceptance-1',memory_consolidation_due=False)
    return state


def violations(state):
    rows=[]
    if state['power_used_kw']<0 or state['power_used_kw']>state['power_capacity_kw']+1e-9:rows.append('grid power')
    if any(v<0 for v in state['resources'].values()):rows.append('negative resources')
    if any(a.get('battery_wh') is not None and not -1e-9<=a['soc_wh']<=a['battery_wh']+1e-9 for a in state['assets']):rows.append('battery capacity')
    if any(j['status']=='complete' and any(not state['milestones'].get(d) for d in j['dependencies']) for j in state['jobs']):rows.append('job prerequisites')
    return [{'tick':state['tick'],'kind':kind} for kind in rows]


def metrics(state,initial,checked):
    return {'ready':state['milestones']['ready'],'readiness_tick':state['readiness_tick'],
        'elapsed_ticks':state['tick']-initial['tick'],'resources':state['resources'],
        'grid_energy_kwh':state['energy_used_kwh']-initial['energy_used_kwh'],
        'scenario_operations_usd':state['spent_usd']-initial['spent_usd'],
        'constraint_violations':checked,'blocked':{j['id']:j['reason'] for j in state['jobs'] if j['status']=='blocked'}}


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--snapshot',type=Path,required=True)
    p.add_argument('--ticks',type=int,default=8)
    p.add_argument('--report',type=Path,default=ROOT/'docs/live-operational-scenarios.json')
    p.add_argument('--cases',nargs='+',choices=['nominal','power-loss','delayed-excavation','equipment-failure'])
    args=p.parse_args()
    if not 8<=args.ticks<=72:p.error('Controlled horizon must be 8 to 72 steps')
    bundle=json.loads(args.snapshot.read_text(encoding='utf-8-sig'));common=prepare(bundle)
    rated=common['power_capacity_kw']
    cases={'nominal':{},'power-loss':{0:{'power_capacity_kw':0},6:{'power_capacity_kw':rated}},
       'delayed-excavation':{0:{'equipment':{'excavator-1':False,'excavator-2':False}},6:{'equipment':{'excavator-1':True,'excavator-2':True}}},
       'equipment-failure':{0:{'equipment':{'excavator-1':False}}}}
    if args.cases:cases={name:cases[name] for name in dict.fromkeys(args.cases)}
    report={'scope':'Real Meta calls versus fixed-priority on controlled fault experiments; no claim of actual Mars equipment operation or superiority',
       'engine_version':common['spec']['version'],'input_hash':digest(common),'source_pins':common['source_pins'],
       'clock_epoch_unix':common['environment']['clock']['unix'],'seed':common['reliability_seed'],
       'natural_random_failures':False,'horizon_ticks':args.ticks,'cases':{},'expected_cases':list(cases),'status':'in progress',
       'limits':['Short controlled horizon is not full-mission readiness or long-duration reliability validation.',
                 'Faults are operator-injected scenarios; original observations and source versions remain unchanged.']}
    import hashlib
    code=ROOT/'council-dashboard/backend/mission'
    report['runtime_source_sha256']={p.relative_to(code).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in code.rglob('*') if p.suffix in ('.py','.json')}
    target=args.report
    target.write_text(json.dumps(report,indent=2),encoding='utf-8')
    for name,schedule in cases.items():
        store,path,basis=acceptance_store(args.snapshot)
        with store.transaction() as db:
            m=store.row(db,'public');s=deepcopy(common)
            s.update(mode='meta',status='active',planning_needed=True,inference_stopped=False,
                     acceptance_scope='Controlled real-Meta '+name+' experiment')
            store.save(db,m,s,{'kind':'controlled-fault-common-start','case':name,'input_hash':digest(common)})
        baseline=deepcopy(common);failure=None;cycles=0;started=time.time();meta_violations=[];baseline_violations=[]
        for step in range(args.ticks):
            if step in schedule:
                baseline=modify(baseline,schedule[step]);baseline['mode']='fixed-priority'
                with store.transaction() as db:
                    m=store.row(db,'public');s=modify(m.state,schedule[step]);s['mode']='meta'
                    store.save(db,m,s,{'kind':'controlled-fault-injection','after_ticks':step,'changes':schedule[step],'not_an_observation':True})
            s=store.snapshot('public')['state']
            if s['status']!='active':failure='Mission was paused; comparison stopped without advancing baseline';break
            if s.get('planning_needed') or s.get('memory_consolidation_due'):
                plan_once(store,mission_id='public');cycles+=1;s=store.snapshot('public')['state']
                if s.get('inference_stopped'):failure=s['planning_status'];break
            with store.transaction() as db:
                m=store.row(db,'public');store.save(db,m,store.step(m.state),{'kind':'controlled-agent-step','case':name})
            baseline=store.step(baseline)
            meta_violations.extend(violations(store.snapshot('public')['state']));baseline_violations.extend(violations(baseline))
        s=store.snapshot('public')['state']
        if not failure and s['tick']!=baseline['tick']:failure='Unequal elapsed steps; invalid comparison'
        with store.transaction() as db:
            m=store.row(db,'public');paused=deepcopy(m.state);paused['status']='paused'
            event(paused,'Controlled acceptance paused',name+' ended at its explicit bound')
            store.save(db,m,paused,{'kind':'controlled-acceptance-pause'})
        receipts=store.export('public')['inference_receipts']
        report['cases'][name]={'status':'failed' if failure else 'completed bounded run','failure':failure,
           'database':str(path),'input_hash':digest(common),'fault_schedule':schedule,'duration_s':time.time()-started,
           'planning_passes':cycles,'meta':metrics(s,common,meta_violations),'fixed_priority':metrics(baseline,common,baseline_violations),
           'provider_requests':[{k:r.get(k) for k in ('id','model','status','response_id','http_status','usage','actual_usd')} for r in receipts]}
        report['checked_at']=time.time();target.write_text(json.dumps(report,indent=2),encoding='utf-8')
        print(json.dumps({'case':name,'status':report['cases'][name]['status'],'requests':len(receipts),'meta_tick':s['tick'],'baseline_tick':baseline['tick']}),flush=True)
    report['status']='failed cases present' if any(v['failure'] for v in report['cases'].values()) else 'all controlled runs completed'
    target.write_text(json.dumps(report,indent=2),encoding='utf-8')
    return int(any(v['failure'] for v in report['cases'].values()))


if __name__=='__main__':sys.exit(main())

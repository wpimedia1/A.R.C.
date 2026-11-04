"""Continue a real provider-backed acceptance database. Never supplies mock responses.

Uses the existing work/assurance/planner path with actual pinned evidence. A bounded
failure is reported as failure, not replaced by a fixed-priority run. This tests the
configured software scenario, including its documented preplaced-habitat assumption.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time
from copy import deepcopy

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'council-dashboard/backend'))
from mission.store import Store
from mission.planner import plan_once
from mission.engine import event
from mission.spec import digest


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--database',type=Path,required=True)
    parser.add_argument('--max-ticks',type=int,default=2400)
    parser.add_argument('--post-ready-ticks',type=int,default=24)
    parser.add_argument('--nominal-no-random-failures',action='store_true',help='Explicit controlled nominal study; disable stochastic failures, preserve real evidence and all resource constraints')
    parser.add_argument('--report',type=Path,default=ROOT/'docs/live-mission-acceptance.json')
    args=parser.parse_args()
    path=args.database.resolve()
    if not path.is_relative_to((ROOT/'output/live-acceptance').resolve()) or not path.is_file():
        parser.error('Only an existing isolated acceptance database under output/live-acceptance is allowed')
    if not 1<=args.max_ticks<=9600 or not 1<=args.post_ready_ticks<=72:parser.error('Invalid acceptance horizon')
    store=Store('sqlite:///'+path.as_posix())
    initial=store.snapshot('public')['state']
    if initial['mode']!='meta' or initial.get('inference_stopped') or initial['status']!='active':
        raise SystemExit('Refusing to override a stop or planner mode; inspect the stored failure first')
    input_hash=digest(initial)
    if args.nominal_no_random_failures:
        with store.transaction() as db:
            m=store.row(db,'public');configured=deepcopy(m.state);configured['failures_enabled']=False
            event(configured,'Controlled nominal acceptance','Stochastic faults disabled explicitly; resource limits, engineering assumptions and pinned evidence are unchanged')
            store.save(db,m,configured,{'kind':'nominal-acceptance-setting','failures_enabled':False,'not_an_observation':True})
        initial=store.snapshot('public')['state']
    code=ROOT/'council-dashboard/backend/mission'
    runtime_hashes={p.relative_to(code).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in code.rglob('*') if p.suffix in ('.py','.json')}
    from acceptance_support import heartbeat
    heartbeat_context=heartbeat(store);heartbeat_context.__enter__()
    started=time.time();cycles=[];ready=None;failure=None
    for _ in range(args.max_ticks):
        state=store.snapshot('public')['state']
        if state['milestones']['ready'] and ready is None:
            ready={'tick':state['tick'],'resources':deepcopy(state['resources']),'energy_kwh':state['energy_used_kwh'],
                   'physical_ledger_entries':len(state['physical_ledger']), 'charging_kwh':state.get('charging_energy_kwh',0)}
        if ready and state['tick']>=ready['tick']+args.post_ready_ticks:break
        if state['status']!='active' or state.get('inference_stopped'):
            failure=state['planning_status'];break
        if state.get('planning_needed') or state.get('memory_consolidation_due'):
            material=bool(state.get('planning_needed'))
            plan_once(store,mission_id='public')
            state=store.snapshot('public')['state']
            if state.get('inference_stopped'):
                failure=state['planning_status'];break
            if material:cycles.append({'tick':state['tick'],'id':state['agent_cycle']['id'],'status':state['planning_status']})
            print(json.dumps({'cycle':len(cycles),'memory_only':not material,'tick':state['tick'],'ready':state['milestones']['ready'],'status':state['planning_status']}),flush=True)
        with store.transaction() as db:
            m=store.row(db,'public')
            store.save(db,m,store.step(m.state),{'kind':'provider-backed-acceptance-step','planner':'meta'})
    heartbeat_context.__exit__(None,None,None)
    state=store.snapshot('public')['state']
    delta={} if ready is None else {k:v-ready['resources'].get(k,0) for k,v in state['resources'].items() if v!=ready['resources'].get(k,0)}
    useful_after=bool(delta) or (ready is not None and state.get('charging_energy_kwh',0)>ready['charging_kwh'])
    passed=ready is not None and state['tick']>=ready['tick']+args.post_ready_ticks and useful_after and not failure
    with store.transaction() as db:
        m=store.row(db,'public');paused=deepcopy(m.state);paused['status']='paused'
        event(paused,'Acceptance run paused','Operator-bounded provider acceptance ended; inspect its actual result')
        store.save(db,m,paused,{'kind':'acceptance-review-pause','passed':passed})
    exported=store.export('public');receipts=exported['inference_receipts']
    report={'checked_at':time.time(),'duration_s':time.time()-started,'status':'passed' if passed else 'not passed',
       'scope':'Real Meta calls on a pinned-evidence software mission; not actual Mars robot operation or hardware qualification',
       'database':str(path),'engine_version':state['spec']['version'],'initial_tick':initial['tick'],'final_tick':state['tick'],
       'input_hash':input_hash,'configured_input_hash':digest(initial),'state_hash':digest(state),'source_pins':state['source_pins'],
       'natural_random_failures':initial.get('failures_enabled',True),'nominal_no_random_failures_explicit':args.nominal_no_random_failures,
       'readiness_tick':state['readiness_tick'],'post_ready_resource_delta':delta,'post_ready_useful_operations':useful_after,
       'failure':failure,'blocked':{j['id']:j['reason'] for j in state['jobs'] if j['status']!='complete'},'cycles':cycles,
       'jobs':[{k:j[k] for k in ('id','status','done','target','unit','completed_tick')} for j in state['jobs']],
       'provider_requests':[{k:r.get(k) for k in ('id','model','status','response_id','http_status','usage','actual_usd')} for r in receipts],
       'runtime_source_sha256':runtime_hashes,
       'limits':['Default D4 assumes preplaced habitat; no compatible repair/swap/offload or thermal calibration manifest was invented.',
                 'Pinned evidence/experiment conditions are frozen. This is not a public real-time operations soak.']}
    target=args.report;target.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({'status':report['status'],'readiness_tick':state['readiness_tick'],'post_ready_useful_operations':useful_after,'report':str(target)}),flush=True)
    return int(not passed)


if __name__=='__main__':sys.exit(main())

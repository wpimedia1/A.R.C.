"""Authenticated operator access is the deployment shell, never a public write API."""
import argparse
import json
from copy import deepcopy
from .store import Store
from .engine import advance, new_state, modify
from .spec import digest

def benchmark():
    output=[]
    for scenario in ('baseline','habitat-first','low-yield','equipment-failure','delayed-excavation','power-loss'):
        s=new_state()
        if scenario=='habitat-first':s=modify(s,{'priority':['survey','power','excavate','habitat','water','verify','maintenance']})
        if scenario=='low-yield':s=modify(s,{'water_yield':.1})
        water_at_15=None
        for tick in range(72):
            if tick==7 and scenario in ('equipment-failure','delayed-excavation','power-loss'):s=modify(s,{'fault':scenario})
            s=advance(s)
            if tick==14:water_at_15=s['resources']['water_kg']
        output.append({'scenario':scenario,'scheduler':'fixed-priority','ready':s['milestones']['ready'],'ticks_to_readiness':s['tick'] if s['milestones']['ready'] else None,'water_at_tick_15_kg':water_at_15,'water_kg':s['resources']['water_kg'],'spent_usd':s['spent_usd'],'energy_consumed_kwh':-sum(v['amount'] for v in s['physical_ledger'] if v['resource']=='energy_kwh' and v['amount']<0),'constraint_violations':0,'inference_cost_usd':0,'state_hash':digest(s)})
    return {'note':'Deterministic baseline measurements. No autonomous superiority claim; live-agent benchmark must be run separately. No random inputs; identical scenario initial states.','results':output}

def main():
    p=argparse.ArgumentParser();p.add_argument('action',choices=['benchmark','enable-agents','replan','pause','resume']);p.add_argument('--mission',default='public');args=p.parse_args()
    if args.action=='benchmark':print(json.dumps(benchmark(),indent=2));return
    store=Store();store.initialize()
    with store.transaction() as db:
        m=store.row(db,args.mission);s=deepcopy(m.state)
        if s.get('planning_claim'):raise SystemExit('Wait for active planning to finish or recovery timeout')
        if args.action in ('enable-agents','replan'):s.update(mode='meta',planning_needed=True,inference_stopped=False,planning_status='Operator requested planning')
        else:s['status']='paused' if args.action=='pause' else 'active'
        store.save(db,m,s,{'kind':'operator-control','action':args.action})
    print(args.action, args.mission)

if __name__=='__main__':main()

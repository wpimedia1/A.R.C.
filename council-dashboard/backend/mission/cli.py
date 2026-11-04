"""Operator shell. Run from council-dashboard/backend: python -m mission.cli <action>"""
import argparse
import json
from copy import deepcopy
from .store import Store
from .engine import advance, new_state, modify
from .spec import digest

SCENARIOS = {
    'baseline': {},
    'one-excavator': {'equipment': {'excavator-2': False}},
    'rover-unavailable-at-start': {'equipment': {'rover-1': False}},
}


def benchmark(max_ticks=24 * 400, package_id='arcadia-mars-v1'):
    """Deterministic fixed-priority runs from the package. No model calls."""
    results = []
    scenarios=SCENARIOS if package_id=='arcadia-mars-v1' else {'baseline':{},'one-excavator':{'equipment':{'excavator-2':False}}}
    for name, change in scenarios.items():
        s = new_state('fixed-priority',package_id)
        s['failures_enabled'] = False  # nominal baseline; random failures (D14) need replacement logistics with a real clock
        if change:
            s = modify(s, change)
        for _ in range(max_ticks):
            if s['milestones']['ready']:
                break  # the benchmark measures time to readiness; operations would continue after it
            s = advance(s)
        results.append({'scenario': name, 'changes': change, 'ready': s['milestones']['ready'], 'readiness_tick': s['readiness_tick'],
                        'readiness_sol': None if s['readiness_tick'] is None else s['readiness_tick'] / 24,
                        'completed': {j['id']: j['completed_tick'] for j in s['jobs']}, 'resources': s['resources'],
                        'energy_used_kwh': s['energy_used_kwh'], 'operations_usd': s['spent_usd'], 'capital_usd': s['capital_usd'],
                        'capital_unestimated': s['capital_unestimated'],
                        'blocked': {j['id']: j['reason'] for j in s['jobs'] if j['status'] != 'complete'}, 'state_hash': digest(s)})
    return {'package': s['spec']['package_id'], 'package_hash': s['spec']['package_hash'], 'max_ticks': max_ticks,
            'note': 'Fixed-priority nominal baseline without random failures (D14) and without a mission clock, so the rover daylight rule (D19) is not applied. Not a measure of agent planning quality.', 'results': results}


def main():
    p = argparse.ArgumentParser()
    p.add_argument('action', choices=['benchmark', 'robustness', 'upgrade', 'enable-agents', 'replan', 'pause', 'resume', 'retry-site-analysis'])
    p.add_argument('--seeds',default='1,2,3,4,5')
    p.add_argument('--ticks',type=int,default=72)
    p.add_argument('--fault-suite',action='store_true')
    p.add_argument('--mission', default='public')
    p.add_argument('--package',default='arcadia-mars-v1')
    args = p.parse_args()
    if args.action == 'robustness':
        from .robustness import ensemble, fault_suite
        runner = fault_suite if args.fault_suite else ensemble
        print(json.dumps(runner(new_state('fixed-priority',args.package),args.seeds.split(','),args.ticks),indent=2))
        return
    if args.action == 'benchmark':
        print(json.dumps(benchmark(args.ticks,args.package), indent=2))
        return
    store = Store()
    if args.action == 'upgrade':
        from .engine import event, reserved_kw
        from .store import SourceVersion
        with store.transaction() as db:
            m = store.row(db, args.mission)
            s = deepcopy(m.state)
            if s.get('planning_claim'):
                raise SystemExit('Finish or recover the active planning claim before upgrading')
            fresh = new_state(s['mode'], s['spec']['package_id'])
            before = s['spec']['hash']
            initialized_batteries = []
            for a in s['assets']:
                template = next(x for x in fresh['assets'] if x['id'] == a['id'])
                if 'soc_wh' not in a and 'soc_wh' in template:
                    initialized_batteries.append(a['id'])
                for key, value in template.items():
                    if key not in ('available', 'position', 'soc_wh', 'charging') or key not in a:
                        a[key] = deepcopy(value)
            added_jobs=[]
            for template in fresh['jobs']:
                if not any(j['id']==template['id'] for j in s['jobs']):
                    s['jobs'].append(deepcopy(template));s['priority'].append(template['id'])
                    s['resources'].setdefault(template['output'],0.0);s['milestones'][template['id']]=False
                    added_jobs.append(template['id'])
            for j in s['jobs']:
                template = next((x for x in fresh['jobs'] if x['id'] == j['id']), None)
                if template:
                    for key in ('power_per_asset_kw', 'power_scope', 'basis', 'parameters','dependencies'):
                        if key in template: j[key] = deepcopy(template[key])
            s['spec'] = fresh['spec']
            if 'production' not in s:
                produced=sum(j['done'] for j in s['jobs'] if j['kind']=='water')
                s['production']=deepcopy(fresh['production'])
                s['production'].update(water_stored_kg=produced,
                    water_feed_remaining_kg=max(0.0,s['production']['water_feed_remaining_kg']-produced),
                    water_storage_capacity_kg=max(produced,s['production']['water_storage_capacity_kg']))
            s.setdefault('operating_spending_limit_usd', None)
            if fresh['spec'].get('water_model') and not s.get('well'):
                from .water import initialize
                initialize(s,allocate_reserve=False)
                # New requirements never retroactively certify the old result.
                if s['milestones'].get('ready'):
                    s['previous_readiness']={'tick':s.get('readiness_tick'),'spec_hash':before}
                    s['milestones']['ready']=False;s['readiness_tick']=None
                event(s,'Well model added','No reserve or extra feed was invented. Establish the reservoir using existing or explicitly configured scenario feed; earlier revisions remain unchanged.')
            for sid,source in fresh['spec']['sources'].items():
                prior = db.get(SourceVersion, s['source_pins'].get(sid, ''))
                if prior and prior.record.get('url') == source.get('url'):continue
                vid=sid+':'+digest(source)[:16]
                if not db.get(SourceVersion,vid):db.add(SourceVersion(id=vid,source_id=sid,record={**source,'source_id':sid,'content_hash':digest(source),'hash_scope':'registry metadata only','status':'registry reference; not retrieved','retrieved_at':None}))
                s['source_pins'][sid]=vid
            package_id=fresh['spec']['package_id'];vid=package_id+':'+fresh['spec']['hash'][:16]
            if not db.get(SourceVersion,vid):db.add(SourceVersion(id=vid,source_id=package_id,record={'source_id':package_id,'title':'Upgraded mission specification','content':fresh['spec'],'content_hash':fresh['spec']['hash'],'raw_package_hash':fresh['spec']['package_hash'],'hash_scope':'canonical mission specification excluding its hash field','status':'pinned specification','retrieved_at':None}))
            s['source_pins'][package_id]=vid
            s['power_used_kw'] = sum(reserved_kw(s,j['assigned'],j) for j in s['jobs'] if j['status'] in ('running','review')) + sum(a['charge_kw'] for a in s['assets'] if a.get('charging'))
            s.update(status='paused', planning_needed=s['mode']=='meta')
            event(s, 'Specification upgraded', f'{before} -> {s["spec"]["hash"]}; prior state and receipts retained; operator must resume.')
            if initialized_batteries:
                event(s, 'Battery model initialized', ', '.join(initialized_batteries) + ': full nominal reference capacity is a migration starting assumption, not a measured state of charge.')
            store.save(db,m,s,{'kind':'upgrade','old_spec_hash':before,'new_spec_hash':s['spec']['hash'],
                              'battery_initialization_assumption':initialized_batteries,'added_jobs':added_jobs})
        print('Upgraded without deleting history. Inspect the paused mission, then resume.')
        return
    if not store.check():
        raise SystemExit('The mission has not been started; press Start in the app first')
    if args.action == 'retry-site-analysis':
        # A failed SAM site analysis is recorded and not retried automatically; the operator clears it to run it again.
        failed = store.status('site-analysis') or {}
        if not failed.get('failed_at'):
            raise SystemExit('No failed site analysis to retry: ' + str(failed or 'none recorded'))
        store.status('site-analysis', {'cleared_at': __import__('time').time(), 'previous_failure': failed.get('error')})
        print('site analysis will run again on the next worker pass')
        return
    with store.transaction() as db:
        m = store.row(db, args.mission)
        s = deepcopy(m.state)
        if s.get('planning_claim'):
            raise SystemExit('Wait for active planning to finish or recovery timeout')
        if args.action in ('enable-agents', 'replan'):
            s.update(mode='meta', planning_needed=True, inference_stopped=False, planning_status='Operator requested planning')
        else:
            s['status'] = 'paused' if args.action == 'pause' else 'active'
        store.save(db, m, s, {'kind': 'operator-control', 'action': args.action})
    print(args.action, args.mission)


if __name__ == '__main__':
    main()

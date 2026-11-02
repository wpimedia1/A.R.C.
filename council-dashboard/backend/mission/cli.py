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


def benchmark(max_ticks=24 * 400):
    """Deterministic fixed-priority runs from the package. No model calls."""
    results = []
    for name, change in SCENARIOS.items():
        s = new_state('fixed-priority')
        s['failures_enabled'] = False  # nominal baseline; random failures (D14) need replacement logistics with a real clock
        if change:
            s = modify(s, change)
        for _ in range(max_ticks):
            if s['status'] != 'active':
                break
            s = advance(s)
        results.append({'scenario': name, 'changes': change, 'ready': s['milestones']['ready'], 'readiness_tick': s['readiness_tick'],
                        'readiness_sol': None if s['readiness_tick'] is None else s['readiness_tick'] / 24,
                        'completed': {j['id']: j['completed_tick'] for j in s['jobs']}, 'resources': s['resources'],
                        'energy_used_kwh': s['energy_used_kwh'], 'operations_usd': s['spent_usd'], 'capital_usd': s['capital_usd'],
                        'capital_unestimated': s['capital_unestimated'],
                        'blocked': {j['id']: j['reason'] for j in s['jobs'] if j['status'] != 'complete'}, 'state_hash': digest(s)})
    return {'package': s['spec']['package_id'], 'package_hash': s['spec']['package_hash'], 'max_ticks': max_ticks,
            'note': 'Fixed-priority nominal baseline without random failures (D14). Not a measure of agent planning quality.', 'results': results}


def main():
    p = argparse.ArgumentParser()
    p.add_argument('action', choices=['benchmark', 'enable-agents', 'replan', 'pause', 'resume', 'retry-site-analysis'])
    p.add_argument('--mission', default='public')
    args = p.parse_args()
    if args.action == 'benchmark':
        print(json.dumps(benchmark(), indent=2))
        return
    store = Store()
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

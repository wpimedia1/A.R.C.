"""Real Meta agent-loop acceptance in an isolated SQLite database. No transport doubles.

Run from the repository root:  python tools/verify_agent_loop.py [--cycles 2] [--max-ticks 2400]

Requires MODEL_API_KEY in council-dashboard/backend/.env and every operator decision approved.
Writes docs/live-agent-loop.json with every provider response_id so each request can be matched
in the Meta developer dashboard. Exits non-zero on any failure.
"""
import argparse
import json
import sys
import tempfile
import time
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'council-dashboard' / 'backend'))

from mission.store import Store  # noqa: E402
from mission.planner import plan_once  # noqa: E402
from mission.engine import advance  # noqa: E402
from mission.spec import digest  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--cycles', type=int, default=2)
    ap.add_argument('--max-ticks', type=int, default=24 * 100)
    args = ap.parse_args()
    db = Path(tempfile.mkdtemp()) / 'agent-loop.db'
    store = Store('sqlite:///' + str(db))
    store.initialize()
    cycles, started = [], time.time()
    for tick in range(args.max_ticks):
        state = store.snapshot('public')['state']
        if state['status'] != 'active':
            break
        if state.get('planning_needed'):
            plan_once(store, mission_id='public')
            state = store.snapshot('public')['state']
            if state.get('inference_stopped'):
                report = {'status': 'failed', 'planning_status': state['planning_status'], 'export': store.export('public')}
                (ROOT / 'docs' / 'live-agent-loop-failure.json').write_text(json.dumps(report, indent=1, default=str), encoding='utf-8')
                raise SystemExit('FAIL: ' + state['planning_status'])
            cycles.append(deepcopy(state['agent_cycle']))
            print(f"cycle {len(cycles)} at tick {state['tick']}: {state['planning_status']}", flush=True)
            if len(cycles) >= args.cycles:
                break
        with store.transaction() as session:
            m = store.row(session, 'public')
            store.save(session, m, advance(m.state), {'kind': 'acceptance-tick'})
    if len(cycles) < args.cycles:
        raise SystemExit(f'FAIL: only {len(cycles)} planning cycles occurred within {args.max_ticks} ticks')
    export = store.export('public')
    receipts = export['inference_receipts']
    bad = [r['id'] for r in receipts if r['status'] != 'received' or not r.get('response_id')]
    if bad:
        raise SystemExit('FAIL: requests without a received provider response: ' + ', '.join(bad))
    checks = []
    for cycle in cycles:
        inputs = [json.loads(r['request']['input']) for r in receipts if r['id'].startswith(cycle['id'] + ':assessment:')]
        if len(inputs) != len(cycle['assessments']):
            raise SystemExit('FAIL: assessment requests do not match recorded assessments')
        same = len({i['observation_hash'] for i in inputs}) == 1 and all(digest(i['world']) == i['observation_hash'] for i in inputs)
        withheld = all('priority' not in i['world'] and 'department_conflicts' not in i['world'] for i in inputs)
        if not (same and withheld):
            raise SystemExit('FAIL: assessments did not share one frozen observation with peer proposals withheld')
        checks.append({'cycle_id': cycle['id'], 'roles': [a['role'] for a in cycle['assessments']], 'same_frozen_observation': same,
                       'peer_proposals_withheld': withheld, 'memory_entries_seen': sum(len(i['own_memory']) for i in inputs)})
    if args.cycles > 1 and checks[-1]['memory_entries_seen'] == 0:
        raise SystemExit('FAIL: later cycle received no role memory')
    s = export['state']
    report = {'checked_at': time.time(), 'duration_s': round(time.time() - started, 1), 'package': s['spec']['package_id'],
              'package_hash': s['spec']['package_hash'], 'ticks': s['tick'], 'cycles': checks,
              'decisions': [{k: d[k] for k in ('id', 'job_id', 'actor', 'assets', 'summary', 'source_ids')} for d in s['decisions']],
              'jobs': {j['id']: {'status': j['status'], 'done': j['done'], 'target': j['target']} for j in s['jobs']},
              'provider_requests': [{'id': r['id'], 'model': r['model'], 'response_id': r['response_id'], 'key_fingerprint': r.get('key_fingerprint'),
                                     'http_status': r.get('http_status'), 'response_headers': r.get('response_headers'), 'usage': r.get('usage'),
                                     'actual_usd': r.get('actual_usd')} for r in receipts],
              'total_usd': sum(r.get('actual_usd', 0) for r in receipts),
              'verify': 'Match each response_id in the Meta developer dashboard before treating this report as evidence.'}
    out = ROOT / 'docs' / 'live-agent-loop.json'
    out.write_text(json.dumps(report, indent=1), encoding='utf-8')
    print(json.dumps({k: report[k] for k in ('ticks', 'cycles', 'total_usd')}, indent=1))
    print(f"{len(receipts)} provider requests; response_ids written to {out}")


if __name__ == '__main__':
    main()

"""End-to-end run of the real API and worker processes on an isolated SQLite database.

    cd council-dashboard/backend && python ../../tools/verify_stack_run.py [fixed-priority|meta] [ticks]

Starts `uvicorn mission.api:app` and `python -m mission.worker` as separate processes, then advances the public
mission's real-time clock by moving its scheduled next tick into the past (instead of waiting 61.6 minutes per tick),
and checks through the HTTP API that the mission advances, work progresses, every reading and error lands in the
append-only history, and the interface is served. Writes docs/stack-run.json. Exit code = number of failed checks.
"""
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / 'council-dashboard' / 'backend'
mode = sys.argv[1] if len(sys.argv) > 1 else 'fixed-priority'
ticks = int(sys.argv[2]) if len(sys.argv) > 2 else 30
db = os.path.join(tempfile.mkdtemp(prefix='arcadia-run-'), 'run.db')
import secrets
OPERATOR = secrets.token_hex(16)  # a throwaway operator token for this isolated run
env = {**os.environ, 'DATABASE_URL': 'sqlite:///' + db, 'MISSION_MODEL_MODE': mode, 'COOKIE_SECURE': 'false', 'MISSION_OPERATOR_TOKEN': OPERATOR}
port = 8091
base = f'http://127.0.0.1:{port}'
procs = [subprocess.Popen([sys.executable, '-m', 'uvicorn', 'mission.api:app', '--port', str(port)], cwd=BACKEND, env=env,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT),
         subprocess.Popen([sys.executable, '-m', 'mission.worker'], cwd=BACKEND, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)]
results = []


def check(name, ok, detail):
    results.append({'check': name, 'ok': bool(ok), 'detail': detail})
    print(('[PASS] ' if ok else '[FAIL] ') + name + ': ' + json.dumps(detail, default=str)[:400])


def get(path):
    return httpx.get(base + path, timeout=30).json()


try:
    for _ in range(60):
        try:
            if httpx.get(base + '/api/v1/health', timeout=5).status_code == 200:
                break
        except httpx.HTTPError:
            pass
        time.sleep(1)
    check('mission waits for Start', get('/api/v1/health').get('started') is False, get('/api/v1/health'))
    refused = httpx.post(base + '/api/v1/start', timeout=60)
    check('start refused without the operator token', refused.status_code == 403, refused.status_code)
    started = httpx.post(base + '/api/v1/start', headers={'X-Operator-Token': OPERATOR}, timeout=60)
    check('Start creates genesis', started.status_code == 200 and started.json().get('created') is True, {'status': started.status_code})
    snap = get('/api/v1/missions/public')
    check('genesis served by the API', snap['revision'] >= 1 and snap['state']['tick'] == 0, {'revision': snap['revision'], 'mode': snap['state']['mode']})
    check('interface served', '<html' in httpx.get(base + '/', timeout=10).text.lower(), {'path': '/'})
    sys.path.insert(0, str(BACKEND))
    os.environ['DATABASE_URL'] = env['DATABASE_URL']
    from mission.store import Store, Mission
    store = Store()
    start_tick = snap['state']['tick']
    for i in range(ticks):
        with store.transaction() as d:
            m = d.get(Mission, 'public')
            m.next_tick = time.time() - 1  # simulate elapsed real time; the worker does the tick
        target = start_tick + i + 1
        deadline = time.time() + 60
        while time.time() < deadline and get('/api/v1/missions/public')['state']['tick'] < target:
            time.sleep(0.5)
    snap = get('/api/v1/missions/public')
    s = snap['state']
    check('worker advanced the mission', s['tick'] >= start_tick + ticks, {'tick': s['tick'], 'revision': snap['revision']})
    progressed = {j['id']: round(j['done'], 2) for j in s['jobs'] if j['done'] > 0}
    if mode == 'fixed-priority':
        check('work progressed', bool(progressed), progressed)
        check('operations cost accrued', s['spent_usd'] > 0, {'spent_usd': s['spent_usd']})
    else:
        check('planning outcome is explicit', bool(s['planning_status']), {'planning_status': s['planning_status'], 'inference_stopped': s['inference_stopped'],
                                                                          'progressed': progressed})
    log = get('/api/v1/missions/public/log?limit=1000')['rows']
    kinds = sorted({(r['source'], r['kind']) for r in log})
    check('append-only history recorded', len(log) > ticks and any(r['source'] == 'revision' for r in log) and any(k == ('worker', 'started') for k in kinds),
          {'rows': len(log), 'kinds': kinds[:20]})
    live = get('/api/v1/environment/live')
    check('live Mars conditions served', live['now'] is not None and live['now']['clock']['mars_year'] >= 39, {'clock': live['now']['clock'] if live['now'] else None,
                                                                                                           'dsn': (live['dsn'] or {}).get('error') or 'read'})
    check('activity visible', len(s['activity']) >= 2, [a['title'] for a in s['activity'][-6:]])
finally:
    for p in procs:
        p.terminate()
    for p in procs:
        try:
            p.wait(10)
        except subprocess.TimeoutExpired:
            p.kill()

(ROOT / 'docs' / 'stack-run.json').write_text(json.dumps({'run_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), 'mode': mode, 'ticks': ticks,
                                                          'results': results}, indent=2, default=str))
print('Wrote docs/stack-run.json')
sys.exit(sum(1 for r in results if not r['ok']))

"""Live check of every external integration, on the owner's machine. Real requests; Meta calls are billed
(one Muse Image generation, $0.01; one SAM 3.1 call, $0.0025). Uses an isolated SQLite database, never the mission database.

    cd council-dashboard/backend && python ../../tools/verify_live_integrations.py

Writes docs/live-integrations.json with each check's result, HTTP status, response IDs and errors.
Every check runs even if an earlier one fails; the exit code is the number of failed checks.
"""
import json
import os
import sys
import tempfile
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# Use the project's own environment (backend/.venv) whatever directory or Python this was started from.
_venv = ROOT / 'council-dashboard' / 'backend' / '.venv' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
if _venv.exists() and Path(sys.executable).resolve() != _venv.resolve() and not os.environ.get('ARCADIA_VENV_REEXEC'):
    import subprocess
    sys.exit(subprocess.call([str(_venv), str(Path(__file__).resolve()), *sys.argv[1:]], env={**os.environ, 'ARCADIA_VENV_REEXEC': '1'}))
sys.path.insert(0, str(ROOT / 'council-dashboard' / 'backend'))
os.environ['DATABASE_URL'] = 'sqlite:///' + os.path.join(tempfile.mkdtemp(prefix='arcadia-live-'), 'live.db')
os.environ.setdefault('MISSION_MODEL_MODE', 'meta')

from mission.store import Store  # noqa: E402
from mission.package import load  # noqa: E402

values = load()['values']
results = []


def check(name, fn):
    started = time.time()
    try:
        out = fn()
        results.append({'check': name, 'ok': True, 'seconds': round(time.time() - started, 1), **out})
        print(f'[PASS] {name}: {json.dumps(out)[:300]}')
    except Exception as exc:
        results.append({'check': name, 'ok': False, 'seconds': round(time.time() - started, 1), 'error': f'{type(exc).__name__}: {exc}'[:2000],
                        'trace': traceback.format_exc()[-2000:]})
        print(f'[FAIL] {name}: {type(exc).__name__}: {exc}'[:600])


def dsn():
    from mission.conditions import fetch_dsn, parse_dsn, geometry
    raw = fetch_dsn()
    geo = geometry(time.time())
    Path(ROOT / 'docs' / 'dsn-sample.xml').write_bytes(raw)
    p = parse_dsn(raw, geo['earth_mars_km'], values['comms.mars_soi_km'])
    return {'dishes': p['dishes_in_feed'], 'targets': len(p['targets_seen']), 'mars_spacecraft': p['mars_spacecraft'],
            'nearest_targets': p['targets_seen'][:6], 'feed_shape': p['feed_shape'], 'sample_saved': 'docs/dsn-sample.xml',
            'check_against': 'https://eyes.nasa.gov/dsn/dsn.html'}


def footprints():
    from mission.media import site_image
    from mission.conditions import SITE
    img = site_image(SITE['latitude'], SITE['longitude_east'], values['mars.mean_radius_km'])
    if img['search_errors']:
        raise RuntimeError(f"footprint search errors: {img['search_errors']}")
    return {k: img.get(k) for k in ('product', 'site_relation', 'applies_to_site', 'candidates_found', 'nearby_found', 'site_distance_km', 'browse', 'label')}


def hirise():
    from mission.science import fetch
    from mission.media import HIRISE
    raw, _ = fetch(HIRISE['browse'], 60_000_000)
    return {'url': HIRISE['browse'], 'bytes': len(raw)}


def sam():
    from mission.media import _segment, HIRISE
    st = Store()
    st.initialize()
    seg = _segment(st, 'public', 'boulder', HIRISE['browse'])
    return {'response_id': seg['response_id'], 'objects': len(seg['objects']), 'raw_output_chars': seg['raw_output_chars'],
            'raw_output_head': seg['raw_output'][:400], 'output_types': seg['response_output_types'], 'diagnostics': seg['diagnostics']}


def weather():
    from mission import nowcast
    st = Store()
    out = {}
    for station in nowcast.STATIONS:
        try:
            new = nowcast.ingest(st, station, nowcast.fetch(station))
            newest = max(new, key=lambda o: o['sol']) if new else None
            out[station] = {'sols': len(new), 'newest': newest['sol'] if newest else None, 'newest_date': newest['terrestrial_date'] if newest else None}
        except Exception as exc:
            out[station] = {'sols': 0, 'error': f'{type(exc).__name__}: {exc}'[:300]}
    cyc = nowcast.cycle(st, values['mars.sol_s'])
    out['estimates_made'] = len(cyc['estimates'])
    if not any(v['sols'] for k, v in out.items() if isinstance(v, dict)):
        raise RuntimeError('no weather sols parsed from either feed')
    return out


for name, fn in [('nasa-weather', weather), ('dsn-now', dsn), ('usgs-hirise-footprints', footprints), ('hirise-browse', hirise),
                 ('sam-3.1', sam)]:
    check(name, fn)

out = ROOT / 'docs' / 'live-integrations.json'
out.write_text(json.dumps({'run_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), 'results': results}, indent=2, default=str))
print('Wrote', out)
sys.exit(sum(1 for r in results if not r['ok']))

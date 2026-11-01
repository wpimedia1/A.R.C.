"""Archive every web-only source of the environment package into sources/web/<source-id>.<html|pdf>,
so `python -m mission.verify_sources` can check their quotes word for word.

    cd council-dashboard/backend && python ../../tools/archive_sources.py && python -m mission.verify_sources
"""
import json
import sys
import time
from pathlib import Path
import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'council-dashboard' / 'backend'))
from mission.package import load  # noqa: E402

pkg = load()
out = ROOT / 'sources' / 'web'
out.mkdir(parents=True, exist_ok=True)
used = {p['source'] for p in pkg['parameters'].values() if p['classification'] == 'published'}
report = []
for sid in sorted(used):
    src = pkg['sources'][sid]
    if src.get('local_file'):
        continue
    try:
        r = httpx.get(src['url'], timeout=60, follow_redirects=True, headers={'User-Agent': 'Mozilla/5.0 (archival copy for source verification)'})
        r.raise_for_status()
        ext = 'pdf' if r.content[:4] == b'%PDF' or 'pdf' in r.headers.get('content-type', '') else 'html'
        (out / f'{sid}.{ext}').write_bytes(r.content)
        report.append({'source': sid, 'url': src['url'], 'status': 'archived', 'file': f'sources/web/{sid}.{ext}', 'bytes': len(r.content)})
    except Exception as exc:
        report.append({'source': sid, 'url': src['url'], 'status': f'FAILED: {type(exc).__name__}: {exc}'[:300]})
    print(report[-1])
(out / 'archive-report.json').write_text(json.dumps({'archived_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), 'results': report}, indent=1))
sys.exit(sum(1 for r in report if r['status'] != 'archived'))

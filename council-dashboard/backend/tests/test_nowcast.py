import json
import math
import pytest
from mission import nowcast as nc
from mission.store import Store

SOL_S = 88775.244


def synthetic_feed(n=1400, start_date='2020-01-01'):
    import datetime as dt
    rows = []
    d0 = dt.date.fromisoformat(start_date)
    for sol in range(1, n + 1):
        ls = (sol / 668.6 * 360) % 360
        rows.append({'sol': sol, 'terrestrial_date': (d0 + dt.timedelta(days=int(sol * 1.0275))).isoformat(), 'ls': round(ls, 2),
                     'min_temp': round(-75 + 10 * math.sin(math.radians(ls)) + 3 * math.sin(sol), 1), 'max_temp': round(-10 + 12 * math.sin(math.radians(ls)), 1),
                     'pressure': round(800 + 80 * math.cos(math.radians(ls - 100)), 1), 'min_gts_temp': '--', 'max_gts_temp': None})
    return {'soles': rows}


def test_feed_parsing_fails_loud_on_wrong_shape():
    with pytest.raises(nc.FeedError):
        nc.parse_feed({'data': []}, 'msl')
    obs = nc.parse_feed(synthetic_feed(20), 'msl')
    assert len(obs) == 20 and obs[0]['values']['ground_min_c'] is None and obs[0]['values']['air_min_c'] is not None


def test_measured_estimated_checked_loop(tmp_path):
    st = Store('sqlite:///' + str(tmp_path / 'w.db'))
    feed = synthetic_feed(1400)
    early = {'soles': feed['soles'][:1390]}
    new = nc.ingest(st, 'msl', early)
    assert len(new) == 1390 and nc.ingest(st, 'msl', early) == []  # append-only, idempotent
    import datetime as dt
    last_date = dt.date.fromisoformat(early['soles'][-1]['terrestrial_date'])
    now = dt.datetime(last_date.year, last_date.month, last_date.day, tzinfo=dt.timezone.utc).timestamp() + 5 * 86400
    out = nc.cycle(st, SOL_S, now)
    assert out['estimates'] and not out['checks']
    e = next(x for x in out['estimates'] if x['variable'] == 'air_min_c' and x['target_sol'] == 1391)
    assert e['classification'] == 'estimated' and e['low95'] < e['value'] < e['high95'] and e['basis']['lead_sols'] == 1
    assert e['basis']['newest_measured_sol'] == 1390 and e['basis']['climatology_samples'] >= nc.MIN_SAMPLES
    # Measurements arrive: estimates are checked.
    nc.ingest(st, 'msl', feed)
    out2 = nc.cycle(st, SOL_S, now + 60)
    checks = [c for c in out2['checks'] if c['variable'] == 'air_min_c']
    assert checks and all(c['status'] in ('confirmed', 'corrected') for c in checks)
    summary = nc.summary(st, SOL_S, now + 60)['msl']
    cal = summary['variables']['air_min_c']['calibration']
    assert cal['checked'] == len(checks) and summary['newest_measured_sol'] == 1400 and summary['variables']['air_min_c']['measured']['classification'] == 'measured'


def test_backtest_on_real_rems_history_is_calibrated():
    """Real Curiosity REMS daily summaries (NASA public feed, cached). Skipped when the cache is absent."""
    import os
    from pathlib import Path
    path = Path(os.getenv('MISSION_REMS_HISTORY', str(Path(__file__).resolve().parents[1] / 'data/science/rems-feed.json')))
    if not path.exists():
        pytest.skip('Real NASA REMS feed cache absent; set MISSION_REMS_HISTORY or download to data/science/rems-feed.json')
    obs = sorted(nc.parse_feed(json.loads(path.read_text(encoding='utf-8')), 'msl'), key=lambda o: o['sol'])
    by = {o['sol']: o for o in obs}
    hits = total = 0
    for cut in range(3600, 4900, 100):
        m = nc.model([o for o in obs if o['sol'] <= cut], 'air_min_c')
        for lead in (1, 7, 30):
            o = by.get(m['last'][0] + lead)
            if o and o['values']['air_min_c'] is not None and o['ls'] is not None:
                e = nc.estimate(m, o['sol'], o['ls'], SOL_S)
                hits += e['low95'] <= o['values']['air_min_c'] <= e['high95']; total += 1
    assert total >= 30 and hits / total >= 0.85

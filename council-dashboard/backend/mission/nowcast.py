"""Measured -> Estimated -> Confirmed/Corrected, on real Mars surface weather.

Measured: NASA's public daily weather summaries from Curiosity REMS (Gale crater, 4.6 S) and, when the feed carries
data, Perseverance MEDA (Jezero crater, 18.4 N). Each sol is stored once, append-only, with its source and date.
These stations are not at Arcadia; every record says where it was measured.

Estimated: the data arrive days to months late. For every sol between the newest measurement and today (and three
sols ahead) the worker estimates each variable from the station's own history:
    seasonal climatology  = mean and spread of all past sols within +/- 7.5 deg of the target's solar longitude (Ls)
    persistence           = the newest measured anomaly from climatology, decayed by the lag-1 autocorrelation r of
                            the station's anomaly series: anomaly * r^k for a target k sols after the newest data
    95 % interval         = +/- 1.96 x anomaly s.d. x sqrt(1 - r^(2k))
Every estimate records its basis (window, sample size, Mars years covered, r, lead, newest measurement).

Confirmed/Corrected: when NASA later publishes the measurement for an estimated sol, each estimate made for it is
checked: confirmed if the measurement falls inside the 95 % interval, corrected otherwise, with the error recorded.
Calibration (interval coverage and mean absolute error by lead) is computed from those checks.

The AI agents receive measurements, estimates and calibration and reason over them; this module does the statistics.
"""
import hashlib
import math
import time
from datetime import datetime, timezone
import httpx
import numpy as np
from sqlalchemy import select

STATIONS = {
    'msl': {'name': 'Curiosity REMS', 'location': 'Gale crater, 4.6 S 137.4 E', 'url': 'https://mars.nasa.gov/rss/api/?feed=weather&category=msl&feedtype=json'},
    'm2020': {'name': 'Perseverance MEDA', 'location': 'Jezero crater, 18.4 N 77.5 E', 'url': 'https://mars.nasa.gov/rss/api/?feed=weather&category=mars2020&feedtype=json'},
}
VARIABLES = {'min_temp': ('air_min_c', 'deg C'), 'max_temp': ('air_max_c', 'deg C'), 'pressure': ('pressure_pa', 'Pa'),
             'min_gts_temp': ('ground_min_c', 'deg C'), 'max_gts_temp': ('ground_max_c', 'deg C')}
WINDOW_DEG = 7.5
MIN_SAMPLES = 10
HORIZON_SOLS = 3


class FeedError(RuntimeError):
    pass


def _num(v):
    if v in (None, '', '--'):
        return None
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def parse_feed(payload, station):
    """NASA weather JSON -> per-sol observations. Raises FeedError when the payload is not the expected feed."""
    rows = payload.get('soles') if isinstance(payload, dict) else None
    if rows is None and isinstance(payload, dict):
        rows = payload.get('sols')
    if not isinstance(rows, list):
        raise FeedError(f'{station}: weather feed has no soles/sols list (keys: {sorted(payload)[:12] if isinstance(payload, dict) else type(payload).__name__})')
    out = []
    for r in rows:
        sol = _num(r.get('sol'))
        if sol is None:
            continue
        values = {name: _num(r.get(key)) for key, (name, _) in VARIABLES.items()}
        out.append({'station': station, 'sol': int(sol), 'terrestrial_date': r.get('terrestrial_date'), 'ls': _num(r.get('ls')),
                    'values': values, 'atmo_opacity': r.get('atmo_opacity'), 'uv_index': r.get('local_uv_irradiance_index')})
    if rows and not out:
        raise FeedError(f'{station}: {len(rows)} rows but none with a sol number')
    return out


def fetch(station, transport=None):
    with httpx.Client(timeout=60, follow_redirects=True, transport=transport) as c:
        r = c.get(STATIONS[station]['url'], headers={'User-Agent': 'ArcadiaMission/1.0'})
        r.raise_for_status()
        return r.json()


def _key(o):
    return hashlib.sha256(repr((o['sol'], o['terrestrial_date'], o['ls'], sorted(o['values'].items()))).encode()).hexdigest()[:12]


def ingest(store, station, payload):
    """Append every sol not yet stored (or whose published values changed). Returns the new observation records."""
    from .store import EnvironmentObservation
    obs = parse_feed(payload, station)
    now = time.time()
    new = []
    with store.transaction() as db:
        have = {r.id for r in db.scalars(select(EnvironmentObservation).where(EnvironmentObservation.kind == 'weather-obs',
                                                                          EnvironmentObservation.id.like(f'{station}:%'))).all()}
        for o in obs:
            oid = f"{station}:{o['sol']}:{_key(o)}"
            if oid in have:
                continue
            rec = {**o, 'source': STATIONS[station]['url'], 'station_name': STATIONS[station]['name'], 'location': STATIONS[station]['location'],
                   'classification': 'measured', 'retrieved_at': now}
            db.add(EnvironmentObservation(id=oid, kind='weather-obs', observed_at=now, record=rec))
            new.append(rec)
    return new


def history(store, station):
    """Latest published value per sol (a re-published sol supersedes the older version; both stay stored)."""
    from .store import EnvironmentObservation
    from sqlalchemy.orm import Session
    with Session(store.engine) as db:
        rows = db.scalars(select(EnvironmentObservation).where(EnvironmentObservation.kind == 'weather-obs',
                                                               EnvironmentObservation.id.like(f'{station}:%')).order_by(EnvironmentObservation.observed_at)).all()
    by_sol = {}
    for r in rows:
        by_sol[r.record['sol']] = r.record
    return [by_sol[s] for s in sorted(by_sol)]


def model(obs, variable):
    """Climatology and anomaly persistence for one variable from a station's history."""
    pts = [(o['sol'], o['ls'], o['values'][variable]) for o in obs if o['ls'] is not None and o['values'].get(variable) is not None]
    if len(pts) < 3 * MIN_SAMPLES:
        return None
    sols = np.array([p[0] for p in pts], dtype=float)
    ls = np.array([p[1] for p in pts], dtype=float)
    val = np.array([p[2] for p in pts], dtype=float)

    def clim(target_ls, window=WINDOW_DEG):
        d = np.minimum(np.abs(ls - target_ls) % 360, 360 - np.abs(ls - target_ls) % 360)
        m = d <= window
        if m.sum() < MIN_SAMPLES and window < 4 * WINDOW_DEG:
            return clim(target_ls, window * 2)
        return float(val[m].mean()), float(val[m].std(ddof=1)) if m.sum() > 1 else float('nan'), int(m.sum()), window, sols[m]

    anomalies = np.array([v - clim(l)[0] for l, v in zip(ls, val)])
    consecutive = np.diff(sols) == 1
    a0, a1 = anomalies[:-1][consecutive], anomalies[1:][consecutive]
    r = float(np.corrcoef(a0, a1)[0, 1]) if len(a0) > MIN_SAMPLES else 0.0
    r = max(0.0, min(0.999, r)) if math.isfinite(r) else 0.0
    return {'clim': clim, 'anomaly_sd': float(anomalies.std(ddof=1)), 'r': r, 'last': (int(sols[-1]), float(ls[-1]), float(val[-1]), float(anomalies[-1])),
            'n': len(pts), 'first_sol': int(sols[0])}


def estimate(m, target_sol, target_ls, sol_s):
    last_sol, _, last_val, last_anom = m['last']
    k = max(0, target_sol - last_sol)
    mean, sd, n, window, used = m['clim'](target_ls)
    persistence = last_anom * m['r'] ** k
    spread = m['anomaly_sd'] * math.sqrt(max(0.0, 1 - m['r'] ** (2 * k)))
    return {'value': round(mean + persistence, 2), 'low95': round(mean + persistence - 1.96 * spread, 2), 'high95': round(mean + persistence + 1.96 * spread, 2),
            'basis': {'method': 'Ls climatology + AR(1) anomaly persistence', 'climatology_mean': round(mean, 2), 'climatology_sd': round(sd, 2),
                      'climatology_samples': n, 'ls_window_deg': window, 'span_sols': int(used.max() - used.min()) if len(used) else 0, 'lag1_autocorrelation': round(m['r'], 3),
                      'lead_sols': k, 'newest_measured_sol': last_sol, 'newest_measured_value': last_val, 'newest_anomaly': round(last_anom, 2)}}


def _now_sol(obs, now, sol_s):
    """Station sol number now, from the newest measured sol and its Earth date (Earth date of a sol is approximate to a day)."""
    last = obs[-1]
    t = datetime.fromisoformat(last['terrestrial_date']).replace(tzinfo=timezone.utc).timestamp() + 43200
    return last['sol'] + max(0, int((now - t) // sol_s)), last, t


def cycle(store, sol_s, now=None):
    """Ingest-free step over stored measurements: check pending estimates, then estimate now..now+HORIZON for each station/variable."""
    from .store import EnvironmentObservation
    from .conditions import mars_clock
    now = now or time.time()
    checks, made = [], []
    for station in STATIONS:
        obs = history(store, station)
        if not obs or not obs[-1].get('terrestrial_date'):
            continue
        by_sol = {o['sol']: o for o in obs}
        with store.transaction() as db:
            pending = db.scalars(select(EnvironmentObservation).where(EnvironmentObservation.kind == 'weather-estimate',
                                                                     EnvironmentObservation.id.like(f'{station}:%'))).all()
            done = {r.record['estimate_id'] for r in db.scalars(select(EnvironmentObservation).where(EnvironmentObservation.kind == 'weather-check',
                                                                                                    EnvironmentObservation.id.like(f'{station}:%'))).all()}
            for e in pending:
                rec = e.record
                o = by_sol.get(rec['target_sol'])
                if e.id in done or not o or o['values'].get(rec['variable']) is None:
                    continue
                measured = o['values'][rec['variable']]
                ok = rec['low95'] <= measured <= rec['high95']
                chk = {'estimate_id': e.id, 'station': station, 'variable': rec['variable'], 'target_sol': rec['target_sol'], 'lead_sols': rec['basis']['lead_sols'],
                       'estimated': rec['value'], 'low95': rec['low95'], 'high95': rec['high95'], 'measured': measured, 'error': round(measured - rec['value'], 2),
                       'status': 'confirmed' if ok else 'corrected', 'checked_at': now, 'classification': 'checked against measurement'}
                db.add(EnvironmentObservation(id=f"{station}:check:{e.id}", kind='weather-check', observed_at=now, record=chk))
                checks.append(chk)
        now_sol, last, last_t = _now_sol(obs, now, sol_s)
        for variable in VARIABLES.values():
            name = variable[0]
            m = model(obs, name)
            if m is None:
                continue
            for target in range(m['last'][0] + 1, now_sol + HORIZON_SOLS + 1):
                target_unix = last_t + (target - last['sol']) * sol_s
                eid = f"{station}:{name}:{target}:after{m['last'][0]}"  # re-estimated only when newer measurements arrive
                with store.transaction() as db:
                    if db.get(EnvironmentObservation, eid):
                        continue
                    est = estimate(m, target, mars_clock(target_unix)['ls_deg'], sol_s)
                    rec = {'station': station, 'station_name': STATIONS[station]['name'], 'location': STATIONS[station]['location'],
                           'variable': name, 'unit': variable[1], 'target_sol': target, 'target_utc_approx': datetime.fromtimestamp(target_unix, timezone.utc).strftime('%Y-%m-%d'),
                           'made_at': now, 'classification': 'estimated', **est,
                           'relation_to_now': 'past, not yet received' if target < now_sol else 'today' if target == now_sol else 'forecast'}
                    db.add(EnvironmentObservation(id=eid, kind='weather-estimate', observed_at=now, record=rec))
                    made.append(rec)
    return {'checks': checks, 'estimates': made}


def summary(store, sol_s, now=None):
    """What agents and the interface see: per station and variable, newest measurement, estimate for today, calibration."""
    from .store import EnvironmentObservation
    from sqlalchemy.orm import Session
    now = now or time.time()
    out = {}
    with Session(store.engine) as db:
        est = [r.record for r in db.scalars(select(EnvironmentObservation).where(EnvironmentObservation.kind == 'weather-estimate')
                                            .order_by(EnvironmentObservation.observed_at)).all()]
        chk = [r.record for r in db.scalars(select(EnvironmentObservation).where(EnvironmentObservation.kind == 'weather-check')).all()]
    for station in STATIONS:
        obs = history(store, station)
        if not obs:
            continue
        now_sol, last, _ = _now_sol(obs, now, sol_s)
        st = {'station': STATIONS[station]['name'], 'location': STATIONS[station]['location'], 'source': STATIONS[station]['url'],
              'newest_measured_sol': last['sol'], 'newest_measured_date': last['terrestrial_date'], 'station_sol_now': now_sol,
              'data_delay_sols': now_sol - last['sol'], 'sols_stored': len(obs), 'variables': {}}
        for name, unit in VARIABLES.values():
            measured = next((o for o in reversed(obs) if o['values'].get(name) is not None), None)
            latest = {}
            for e in est:
                if e['station'] == station and e['variable'] == name:
                    latest[e['target_sol']] = e
            c = [x for x in chk if x['station'] == station and x['variable'] == name]
            st['variables'][name] = {
                'unit': unit,
                'measured': None if not measured else {'value': measured['values'][name], 'sol': measured['sol'], 'date': measured['terrestrial_date'], 'classification': 'measured'},
                'estimate_today': latest.get(now_sol),
                'forecast': [latest[s] for s in sorted(latest) if s > now_sol][:HORIZON_SOLS],
                'calibration': {'checked': len(c), 'confirmed': sum(1 for x in c if x['status'] == 'confirmed'),
                                'interval_coverage': round(sum(1 for x in c if x['status'] == 'confirmed') / len(c), 3) if c else None,
                                'mean_abs_error': round(sum(abs(x['error']) for x in c) / len(c), 2) if c else None,
                                'recent': sorted(c, key=lambda x: x['checked_at'])[-5:]}}
        out[station] = st
    return out


def brief(summary_out):
    """Compact form for agent context (bounded size): newest measurement, today's estimate, next-sol estimate, track record."""
    out = {}
    for station, st in summary_out.items():
        vars_ = {}
        for name, v in st['variables'].items():
            if not v['measured']:
                continue
            t, f, c = v['estimate_today'], (v['forecast'] or [None])[0], v['calibration']
            vars_[name] = {'unit': v['unit'],
                           'measured': [v['measured']['value'], v['measured']['sol'], v['measured']['date']],
                           'estimate_today': None if not t else [t['value'], t['low95'], t['high95'], t['basis']['lead_sols']],
                           'estimate_next_sol': None if not f else [f['value'], f['low95'], f['high95']],
                           'track_record': [c['confirmed'], c['checked'], c['mean_abs_error']]}
        out[station] = {'station': st['station'], 'location': st['location'], 'data_delay_sols': st['data_delay_sols'],
                        'station_sol_now': st['station_sol_now'], 'variables': vars_}
    return {'format': 'measured=[value, sol, date]; estimate_today=[value, low95, high95, lead_sols]; estimate_next_sol=[value, low95, high95]; track_record=[confirmed, checked, mean_abs_error]',
            'stations': out}

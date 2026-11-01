"""Replacement logistics (decision D12): next Earth-Mars Hohmann window from real planetary positions.

Positions: ERFA epv00 (Earth) and plan94 (Mars), heliocentric, rotated to the ecliptic of date (erfa.obl06).
The window is the first time Mars leads Earth by logistics.launch_phase_deg; arrival follows after
logistics.hohmann_transfer_days. Both values are derived in the environment package from NSSDC constants.
"""
import math
from .conditions import _tt, _iso

DAY = 86400.0


def _longitudes(unix):
    import erfa
    import numpy as np
    d1, d2 = _tt(unix)
    eps = erfa.obl06(d1, d2)
    rot = np.array([[1, 0, 0], [0, math.cos(eps), math.sin(eps)], [0, -math.sin(eps), math.cos(eps)]])
    pvh, _ = erfa.epv00(d1, d2)
    pm = erfa.plan94(d1, d2, 4)
    out = []
    for p in (np.asarray(pvh['p'], dtype=float), np.asarray(pm['p'], dtype=float)):
        x, y, _z = rot @ p
        out.append(math.degrees(math.atan2(y, x)) % 360)
    return out  # earth, mars


def phase_deg(unix):
    """Heliocentric ecliptic longitude of Mars minus Earth, 0..360 (positive: Mars leads)."""
    earth, mars = _longitudes(unix)
    return (mars - earth) % 360


def next_window(unix, launch_phase_deg, search_days=900):
    """First time at or after `unix` when Mars leads Earth by launch_phase_deg (phase decreases ~0.46 deg/day)."""
    def gap(t):
        return (phase_deg(t) - launch_phase_deg + 180) % 360 - 180
    prev_t, prev_g = unix, gap(unix)
    if abs(prev_g) < 1e-6:
        return unix
    for day in range(1, search_days + 1):
        t = unix + day * DAY
        g = gap(t)
        if prev_g > 0 >= g and prev_g - g < 90:  # crossing from ahead to behind the target phase
            lo, hi = prev_t, t
            for _ in range(40):
                mid = (lo + hi) / 2
                if gap(mid) > 0:
                    lo = mid
                else:
                    hi = mid
            return hi
        prev_t, prev_g = t, g
    raise RuntimeError(f'No Hohmann window found within {search_days} days')


def replacement_order(state, asset_id, now_unix, values, actor, summary, source_ids):
    """Order data for engine.place_order: window, arrival, mass, cost, arrival tick."""
    asset = next(a for a in state['assets'] if a['id'] == asset_id)
    launch = next_window(now_unix, values['logistics.launch_phase_deg'])
    arrival = launch + values['logistics.hohmann_transfer_days'] * DAY
    tick_s = values['mars.sol_s'] / 24
    mass = asset['mass_kg']
    return {'asset_id': asset_id, 'asset_name': asset['name'], 'ordered_utc': _iso(now_unix), 'launch_utc': _iso(launch), 'arrival_utc': _iso(arrival),
            'launch_unix': launch, 'arrival_unix': arrival,
            'arrival_tick': state['tick'] + math.ceil((arrival - now_unix) / tick_s),
            'mass_kg': mass, 'cost_usd': None if mass is None else mass * values['cost.landed_usd_per_kg'],
            'cost_basis': 'mass x cost.landed_usd_per_kg (D5)' if mass is not None else 'not estimated: no published hardware mass',
            'transfer_days': round(values['logistics.hohmann_transfer_days'], 2), 'launch_phase_deg': round(values['logistics.launch_phase_deg'], 3),
            'actor': actor, 'summary': summary, 'source_ids': list(source_ids), 'decision': 'D12'}

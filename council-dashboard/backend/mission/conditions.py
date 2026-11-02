"""Live Mars conditions, independent of the simulation clock.

- Mars date, season and local time at real UTC: Mars24 algorithm (Allison & McEwen 2000) via marstime.
- Earth-Mars geometry at real UTC: ERFA epv00 (Earth) and plan94 (Mars), UTC->TT with ERFA leap seconds;
  one-way light time from the IAU astronomical unit and SI speed of light (erfa.DAU, erfa.CMPS).
- Deep Space Network: the DSN Now live feed. A tracked target counts as a spacecraft at Mars when its range is
  within the Mars sphere of influence (package comms.mars_soi_km) of the computed Earth-Mars distance.

These conditions keep updating while a mission is paused. The worker records every change of the DSN Mars link
as an EnvironmentObservation; the public mission applies the conditions at each tick (decision D10/D11).
"""
import math
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
import httpx

DSN_URL = 'https://eyes.nasa.gov/dsn/data/dsn.xml'
# Scenario site in Arcadia Planitia, chosen so real full-resolution imagery covers it (owner decision, D13): the centre pixel
# of HiRISE ESP_056974_2205_RED (0.5 m/pixel), from its PDS label IMAGE_MAP_PROJECTION (LINES 66625, LINE_SAMPLES 18485,
# MAP_RESOLUTION 118259.58864773 pix/deg, LINE_PROJECTION_OFFSET 4770142.5, SAMPLE_PROJECTION_OFFSET -922911.5, centre 40 N 180 E):
# https://hirise.lpl.arizona.edu/PDS/RDR/ESP/ORB_056900_056999/ESP_056974_2205/ESP_056974_2205_RED.LBL
SITE = {'latitude': 40.05451, 'longitude_east': 190.28958, 'classification': 'scenario assumption',
        'basis': 'centre pixel of HiRISE ESP_056974_2205_RED (PDS label projection)'}
# Spacecraft at Mars, by their DSN abbreviations (JPL DSN Current Mission Set, 7-2020:
# https://deepspace.jpl.nasa.gov/files/DSN_Current_Mission_Set_7-2020.pdf). The live DSN Now feed reports range and
# round-trip light time as -1 (owner's capture 2026-10-31, docs/dsn-sample.xml, which lists MRO and M01O), so the
# feed cannot be matched by distance; spacecraft are identified by these published abbreviations.
MARS_SPACECRAFT = {'EMM': 'Emirates Mars Mission', 'M01O': "Mars '01 Odyssey", 'M20': 'Mars 2020', 'MEX': 'Mars Express',
                   'MOM': 'Mars Orbiter Mission', 'MRO': 'Mars Reconnaissance Orbiter', 'MSL': 'Mars Science Laboratory (Curiosity)',
                   'MVN': 'MAVEN', 'TGO': 'ExoMars Trace Gas Orbiter'}
SEASONS = ('northern spring', 'northern summer', 'northern autumn', 'northern winter')


class ConditionsError(RuntimeError):
    pass


def _iso(unix):
    return datetime.fromtimestamp(unix, timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def _tt(unix):
    import erfa
    t = datetime.fromtimestamp(unix, timezone.utc)
    u1, u2 = erfa.dtf2d('UTC', t.year, t.month, t.day, t.hour, t.minute, t.second + t.microsecond / 1e6)
    a1, a2 = erfa.utctai(u1, u2)
    return erfa.taitt(a1, a2)


def _sun_enu(mt, j):
    """Unit vector to the sun at the site, local east/north/up (hour angle and declination from Mars24)."""
    h = float(mt.hourangle(360 - SITE['longitude_east'], j))  # Mars24 west-longitude convention: positive before local noon
    d = math.radians(float(mt.solar_declination(mt.Mars_Ls(j))))
    p = math.radians(SITE['latitude'])
    return [round(math.cos(d) * math.sin(h), 4), round(math.sin(d) * math.cos(p) - math.cos(d) * math.cos(h) * math.sin(p), 4),
            round(math.sin(d) * math.sin(p) + math.cos(d) * math.cos(h) * math.cos(p), 4)]


def mars_clock(unix):
    import marstime as mt
    j = mt.j2000_offset_tt(mt.julian_tt(mt.julian(unix * 1000)))
    ls = float(mt.Mars_Ls(j))
    return {'utc': _iso(unix), 'unix': unix, 'mars_sol_date': round(float(mt.Mars_Solar_Date(j)), 5),
            'mars_year': int(mt.Mars_Year(j)), 'ls_deg': round(ls, 3), 'season': SEASONS[int(ls // 90) % 4],
            'mtc_h': round(float(mt.Coordinated_Mars_Time(j)), 4),
            'site_lmst_h': round(float(mt.Local_Mean_Solar_Time(360 - SITE['longitude_east'], j)), 4),
            # Sun geometry at the site (Mars24; west longitude): when the sun is up and how high.
            'site_ltst_h': round(float(mt.Local_True_Solar_Time(360 - SITE['longitude_east'], j)), 4),
            'site_solar_elevation_deg': round(float(mt.solar_elevation(360 - SITE['longitude_east'], SITE['latitude'], j)), 2),
            'site_sun_enu': _sun_enu(mt, j),
            'source': 'mars24'}


def geometry(unix):
    import erfa
    import numpy as np
    d1, d2 = _tt(unix)
    pvh, _ = erfa.epv00(d1, d2)
    pm = erfa.plan94(d1, d2, 4)
    earth = np.asarray(pvh['p'], dtype=float)
    mars = np.asarray(pm['p'], dtype=float)
    to_mars, to_sun = mars - earth, -earth
    cos = float(np.dot(to_mars, to_sun) / np.linalg.norm(to_mars) / np.linalg.norm(to_sun))
    distance_m = float(np.linalg.norm(to_mars)) * erfa.DAU
    return {'earth_mars_km': round(distance_m / 1000, 1), 'one_way_light_s': round(distance_m / erfa.CMPS, 2),
            'sun_mars_separation_deg': round(math.degrees(math.acos(max(-1.0, min(1.0, cos)))), 4), 'source': 'erfa'}


def _num(v):
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) and x > 0 else None


def _feed_shape(root):
    """Tag and attribute names present in the feed, recorded so a layout change is visible instead of silent."""
    shape = {}
    for el in root.iter():
        shape.setdefault(el.tag, set()).update(el.attrib)
    return {k: sorted(v) for k, v in shape.items()}


def parse_dsn(raw, earth_mars_km, soi_km):
    """Mars links in one DSN Now snapshot.

    Targets are read from any element named target under a dish; range from downlegRange/uplegRange (km) or, if those
    are absent or non-positive, from the round-trip light time rtlt (s) x c / 2. A spacecraft is at Mars when its range is
    within soi_km of the computed Earth-Mars distance. Raises ConditionsError when the feed has dishes but no readable
    target range (layout not understood): the reading then counts as unavailable and holds nothing (D10)."""
    import erfa
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        raise ConditionsError(f'DSN feed is not XML: {exc}') from exc
    if root.tag.lower() != 'dsn':
        raise ConditionsError('DSN feed root is not <dsn>')
    stamp = root.findtext('timestamp')
    station, links, seen = None, [], []
    dishes = [el for el in root.iter() if el.tag.lower() == 'dish']
    station_of = {}
    for el in root:
        if el.tag.lower() == 'station':
            station = el.get('friendlyName') or el.get('name')
        elif el.tag.lower() == 'dish':
            station_of[id(el)] = station
    for el in dishes:
        st = station_of.get(id(el))
        signals = [(sg, 'up' if sg.tag.lower() == 'upsignal' else 'down') for sg in el.iter() if sg.tag.lower() in ('upsignal', 'downsignal')]
        for t in el.iter():
            if t.tag.lower() != 'target':
                continue
            name, tid = t.get('name'), (t.get('id') or '').lstrip('-')
            if not name:
                continue
            rng = _num(t.get('downlegRange')) or _num(t.get('uplegRange'))
            basis = 'range attribute'
            if rng is None and _num(t.get('rtlt')):
                rng = _num(t.get('rtlt')) * erfa.CMPS / 2 / 1000
                basis = 'round-trip light time'
            if rng is None:
                basis = 'no range published'
            mine = [(sg, d) for sg, d in signals if sg.get('spacecraft') == name or (tid and (sg.get('spacecraftID') or sg.get('spacecraftId') or '').lstrip('-') == tid)]
            by_name = name.upper() in MARS_SPACECRAFT
            by_range = rng is not None and abs(rng - earth_mars_km) < soi_km
            at_mars = by_name or by_range
            seen.append({'dish': el.get('name'), 'station': st, 'target': name, 'mission': MARS_SPACECRAFT.get(name.upper()),
                         'range_km': None if rng is None else round(rng), 'range_basis': basis,
                         'minus_earth_mars_km': None if rng is None else round(rng - earth_mars_km), 'at_mars': at_mars,
                         'identified_by': 'DSN mission abbreviation' if by_name else 'range' if by_range else None,
                         'range_conflict': by_name and rng is not None and not by_range,
                         'up_active': any(d == 'up' and sg.get('active') == 'true' for sg, d in mine),
                         'down_active': any(d == 'down' and sg.get('active') == 'true' for sg, d in mine)})
            if at_mars:
                for sg, d in mine:
                    if sg.get('active') == 'true':
                        links.append({'dish': el.get('name'), 'station': st, 'spacecraft': name, 'direction': d,
                                      'data_rate_bps': _num(sg.get('dataRate')), 'band': sg.get('band'), 'range_km': None if rng is None else round(rng), 'rtlt_s': _num(t.get('rtlt'))})
    if dishes and not seen:
        sample = ET.tostring(dishes[0], encoding='unicode')[:1500]
        raise ConditionsError(f'DSN feed has {len(dishes)} dishes but no named targets; layout not understood. First dish: {sample}')
    return {'feed_timestamp_ms': int(stamp) if stamp and stamp.isdigit() else None,
            'uplink_to_mars': any(l['direction'] == 'up' for l in links),
            'downlink_from_mars': any(l['direction'] == 'down' for l in links),
            'mars_spacecraft': sorted({l['spacecraft'] for l in links}), 'links': links,
            # Everything the feed contained, so the Mars test can be checked against NASA's own DSN Now page.
            'targets_seen': sorted(seen, key=lambda x: (not x['at_mars'], abs(x['minus_earth_mars_km']) if x['minus_earth_mars_km'] is not None else float('inf'))), 'dishes_in_feed': len(dishes),
            'feed_shape': _feed_shape(root)}


def fetch_dsn(transport=None):
    with httpx.Client(timeout=15, follow_redirects=True, transport=transport) as client:
        r = client.get(DSN_URL, params={'r': int(time.time())}, headers={'User-Agent': 'ArcadiaMission/1.0'})
        r.raise_for_status()
        if len(r.content) > 2_000_000:
            raise ConditionsError('DSN feed exceeds 2 MB')
        return r.content


def snapshot(unix, soi_km, dsn_status=None, conjunction_deg=None, tick_seconds=None, previous_tick_unix=None):
    """Conditions applied to the public mission at one tick. dsn_status is the worker's latest DSN record."""
    geo = geometry(unix)
    link = {'conjunction': conjunction_deg is not None and geo['sun_mars_separation_deg'] < conjunction_deg,
            'conjunction_threshold_deg': conjunction_deg,
            'light_ticks': math.ceil(geo['one_way_light_s'] / tick_seconds) if tick_seconds else None}
    if not dsn_status or dsn_status.get('error') or not dsn_status.get('checked_at') or unix - dsn_status['checked_at'] > 900:
        link.update(dsn='unavailable', uplink_window=None,
                    dsn_error=((dsn_status or {}).get('error') or 'No DSN Now reading in the last 15 minutes')[:300])
    elif not dsn_status.get('last_mars_target_seen_at') or unix - dsn_status['last_mars_target_seen_at'] > 86400:
        # The Mars test is only trusted after it has identified a spacecraft at Mars in the last day.
        # Until then an empty result cannot hold work: it is flagged, never treated as "no uplink".
        link.update(dsn='unconfirmed', uplink_window=None,
                    dsn_error='DSN Now is being read, but no tracked spacecraft has matched the Mars distance in the last 24 h; the Mars test is unconfirmed, so orders are not held by DSN')
    else:
        if previous_tick_unix is None and not tick_seconds:
            raise ValueError('Uplink window needs the previous step time or the step length; neither was given')
        since = previous_tick_unix if previous_tick_unix is not None else unix - tick_seconds
        last_up = dsn_status.get('last_mars_uplink_at')
        link.update(dsn='live', uplink_window=bool(last_up and last_up >= since), last_mars_uplink_at=last_up,
                    mars_spacecraft=dsn_status.get('mars_spacecraft', []), links=dsn_status.get('links', []))
    link['uplink_open'] = not link['conjunction'] and link['uplink_window'] is not False
    clock = mars_clock(unix)
    return {'clock': clock, 'geometry': geo, 'link': link, 'site': SITE}


def poll_dsn(store, soi_km, transport=None):
    """One DSN Now reading. Records the Mars link state; appends an observation whenever it changes."""
    from .store import EnvironmentObservation
    now = time.time()
    previous = store.status('dsn') or {}
    try:
        geo = geometry(now)
        parsed = parse_dsn(fetch_dsn(transport), geo['earth_mars_km'], soi_km)
    except Exception as exc:
        record = {**previous, 'checked_at': None, 'failed_at': now, 'error': f'{type(exc).__name__}: {exc}'[:2000]}
        store.status('dsn', record)
        with store.transaction() as db:
            db.add(EnvironmentObservation(id=f'dsn:{now:.3f}', kind='dsn-unavailable', observed_at=now, record={'error': record['error']}))
        return record
    import logging
    logging.info('DSN Now: %d dishes, %d targets; Earth-Mars %.0f km; targets: %s', parsed['dishes_in_feed'], len(parsed['targets_seen']), geo['earth_mars_km'],
                 ', '.join(f"{t['target']}{' (Mars)' if t['at_mars'] else ''}" for t in parsed['targets_seen'][:6]) or 'none')
    record = {'checked_at': now, 'error': None, 'earth_mars_km': geo['earth_mars_km'], **parsed,
              'last_mars_uplink_at': now if parsed['uplink_to_mars'] else previous.get('last_mars_uplink_at'),
              'last_mars_target_seen_at': now if any(t['at_mars'] for t in parsed['targets_seen']) else previous.get('last_mars_target_seen_at')}
    # Every reading is kept, append-only (all records from inception).
    with store.transaction() as db:
        db.add(EnvironmentObservation(id=f'dsn:{now:.3f}', kind='dsn-reading', observed_at=now,
                                      record={k: parsed[k] for k in ('uplink_to_mars', 'downlink_from_mars', 'mars_spacecraft', 'links', 'feed_timestamp_ms',
                                                                     'targets_seen', 'dishes_in_feed')} | {'earth_mars_km': geo['earth_mars_km']}))
    store.status('dsn', record)
    return record

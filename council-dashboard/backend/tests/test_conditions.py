import calendar
from copy import deepcopy
import pytest
from mission.conditions import mars_clock, geometry, parse_dsn, snapshot
from mission.engine import open_conditions, new_state, start, advance, apply_environment, job_by_id, assurance_decision, place_order, modify, asset_by_id
from mission.package import load

V = load()['values']
SOI = V['comms.mars_soi_km']
TICK_S = V['mars.sol_s'] / 24


def utc(*t):
    return calendar.timegm(t + (0,) * (6 - len(t)))


def test_mars_sol_date_matches_mars24_reference():
    # Mars24 technical notes: "MSD 44796.0 is approximately coincident with 2000 January 6.0".
    assert mars_clock(utc(2000, 1, 6))['mars_sol_date'] == pytest.approx(44796.0, abs=0.001)


def test_conjunction_geometry_june_2015():
    # LASP 2015: the Sun within two degrees of Mars during the June 2015 moratorium.
    g = geometry(utc(2015, 6, 14))
    assert g['sun_mars_separation_deg'] < V['comms.conjunction_sun_sep_deg']
    assert g['one_way_light_s'] == pytest.approx(g['earth_mars_km'] * 1000 / 299792458, rel=1e-5)


def dsn_xml(mars_range_km):
    return f'''<dsn><station name="gdscc" friendlyName="Goldstone" timeUTC="1" timeZoneOffset="0"/>
<dish name="DSS14" activity="x"><upSignal active="true" signalType="data" dataRate="2000" band="X" spacecraft="MRO" spacecraftID="-74"/>
<downSignal active="true" signalType="data" dataRate="1000000" band="X" spacecraft="MRO" spacecraftID="-74"/>
<target name="MRO" id="74" uplegRange="{mars_range_km}" downlegRange="{mars_range_km}" rtlt="1400"/></dish>
<dish name="DSS43" activity="x"><upSignal active="true" signalType="data" dataRate="16" band="S" spacecraft="VGR2" spacecraftID="-32"/>
<target name="VGR2" id="32" uplegRange="21000000000" downlegRange="21000000000" rtlt="140000"/></dish>
<timestamp>1793473400000</timestamp></dsn>'''.encode()


def test_dsn_mars_link_by_name_or_range_and_conflicts_flagged():
    d = 214_000_000.0
    parsed = parse_dsn(dsn_xml(d + 1000), d, SOI)
    assert parsed['uplink_to_mars'] and parsed['downlink_from_mars'] and parsed['mars_spacecraft'] == ['MRO']
    assert all(l['spacecraft'] != 'VGR2' for l in parsed['links'])
    far = parse_dsn(dsn_xml(d + 2 * SOI), d, SOI)
    assert far['uplink_to_mars'] and far['targets_seen'][0]['range_conflict']  # named Mars craft, inconsistent range is flagged


def env_at(unix, uplink, conj=None):
    status = {'checked_at': unix, 'error': None, 'last_mars_uplink_at': unix if uplink else None, 'last_mars_target_seen_at': unix, 'mars_spacecraft': ['MRO'] if uplink else [],
              'links': [{'direction': 'up', 'station': 'Goldstone', 'dish': 'DSS14', 'spacecraft': 'MRO'}] if uplink else []}
    e = snapshot(unix, SOI, status, V['comms.conjunction_sun_sep_deg'], TICK_S, unix - TICK_S)
    if conj is not None:
        e['link']['conjunction'] = conj
        e['link']['uplink_open'] = not conj and e['link']['uplink_window'] is not False
    return e


def commissioned_meta_state(env):
    s = new_state('meta')
    s.update(power_capacity_kw=s['spec']['assets'][4]['output_kw'], power_commissioned=True)
    apply_environment(s, env)
    return s


def test_agent_work_order_runs_onboard_without_waiting_for_earth():
    # D10: agents run onboard. No DSN uplink, no light-time wait: approved work starts at once.
    t = utc(2026, 10, 31, 5)  # daytime at the site (sun about 35 deg up), so the rover may drive (D19)
    s = commissioned_meta_state(env_at(t, uplink=False))
    start(s, 'survey', ['rover-1'], 'Survey first.', 'survey / muse-spark-1.3', [s['spec']['package_id']])
    j = job_by_id(s, 'survey')
    assert j['status'] == 'review' and j['authorization']['assurance'] == 'pending' and 'assurance' in j['reason']
    assurance_decision(s, 'survey', True, 'Dependencies and equipment checked.', 'assurance / muse-spark-1.3', [c['id'] for c in open_conditions(s, job_by_id(s, 'survey'))])
    assert job_by_id(s, 'survey')['status'] == 'running'
    s = advance(s, env_at(t + TICK_S, uplink=False))
    assert job_by_id(s, 'survey')['done'] > 0


def test_conjunction_interrupts_earth_contact_but_not_work():
    t = utc(2026, 10, 31, 12)
    s = commissioned_meta_state(env_at(t, uplink=True))
    s['planning_needed'] = False
    s = advance(s, env_at(t + TICK_S, uplink=True, conj=True))
    assert s['planning_needed'] and any(a['title'] == 'Solar conjunction began' for a in s['activity'])
    start(s, 'survey', ['rover-1'], 'Survey.', 'survey / muse-spark-1.3', [s['spec']['package_id']])
    assurance_decision(s, 'survey', True, 'Checked.', 'assurance / muse-spark-1.3', [c['id'] for c in open_conditions(s, job_by_id(s, 'survey'))])
    assert job_by_id(s, 'survey')['status'] == 'running'


def test_assurance_hold_releases_equipment_and_escalates():
    t = utc(2026, 10, 31, 12)
    s = commissioned_meta_state(env_at(t, uplink=True))
    start(s, 'survey', ['rover-1'], 'Survey.', 'survey / muse-spark-1.3', [s['spec']['package_id']])
    assurance_decision(s, 'survey', False, 'Route hazards not yet characterized.', 'assurance / muse-spark-1.3')
    j = job_by_id(s, 'survey')
    assert j['status'] == 'blocked' and j['assigned'] == [] and s['department_conflicts'][-1]['status'] == 'unresolved'
    with pytest.raises(Exception):
        assurance_decision(s, 'survey', True, 'x', 'assurance')


def test_failed_robot_is_replaced_at_next_window():
    from mission.logistics import replacement_order
    t = utc(2026, 10, 31, 12)
    s = commissioned_meta_state(env_at(t, uplink=True))
    s = modify(s, {'equipment': {'excavator-2': False}})
    o = replacement_order(s, 'excavator-2', t, V, 'logistics / muse-spark-1.3', 'Replace failed excavator.', ['nssdc_mars'])
    assert o['launch_utc'].startswith('2026-12') and o['cost_usd'] == pytest.approx(V['excavator.mass_kg'] * V['cost.landed_usd_per_kg'])
    capital = s['capital_usd']
    place_order(s, o)
    assert s['capital_usd'] == pytest.approx(capital + o['cost_usd'])
    with pytest.raises(Exception):
        place_order(s, o)
    s['status'] = 'active'
    s['tick'] = o['arrival_tick'] - 1
    s = advance(s)
    assert asset_by_id(s, 'excavator-2')['available'] and s['orders'][0]['status'] == 'delivered'


def test_resume_after_pause_records_event_and_replans():
    t = utc(2026, 10, 31, 12)
    s = commissioned_meta_state(env_at(t, uplink=True))
    s['planning_needed'] = False
    e = env_at(t + 30 * TICK_S, uplink=True)
    e['resumed_after_s'] = 30 * TICK_S
    e['while_paused'] = 'While paused: 3 DSN observations recorded.'
    s = advance(s, e)
    assert s['planning_needed'] and any(a['title'] == 'Mission resumed' for a in s['activity'])


def test_fixed_priority_is_onboard_and_not_gated():
    t = utc(2026, 10, 31, 12)
    s = new_state('fixed-priority')
    apply_environment(s, env_at(t, uplink=False))
    s = advance(s, env_at(t + TICK_S, uplink=False))
    assert job_by_id(s, 'power')['status'] == 'running'


def test_hazard_route_detours_around_detections():
    from mission.route import plan
    wall = {'prompt': 'boulder', 'objects': [{'left': 480, 'right': 520, 'top': 0, 'bottom': 700, 'object_id': 1}]}
    r = plan(1000, 1000, 0.5, [wall], 0.0)
    assert r['status'] == 'route found' and r['detour_factor'] > 1.0 and r['straight_m'] == pytest.approx(999 * 0.5, rel=0.01)
    blocked = {'prompt': 'crater', 'objects': [{'left': 480, 'right': 520, 'top': 0, 'bottom': 1000, 'object_id': 2}]}
    assert plan(1000, 1000, 0.5, [blocked], 0.0)['detour_factor'] is None
    # Clearance: the rover centre keeps half the rover width from detections, so a gap narrower than the rover is closed.
    # A 2 m gap (4 pixels at 0.5 m/pixel) between two boulders: open for a point, closed for a 2.7 m wide rover.
    gap = {'prompt': 'boulder', 'objects': [{'left': 190, 'right': 210, 'top': 0, 'bottom': 198, 'object_id': 3},
                                            {'left': 190, 'right': 210, 'top': 202, 'bottom': 400, 'object_id': 4}]}
    assert plan(400, 400, 0.5, [gap], 0.0)['status'] == 'route found'
    assert plan(400, 400, 0.5, [gap], V['rover.width_m'] / 2)['detour_factor'] is None
    with_clearance = plan(1000, 1000, 0.5, [wall], V['rover.width_m'] / 2)
    assert with_clearance['clearance_m'] == V['rover.width_m'] / 2 and with_clearance['route_m'] > r['route_m']


def test_route_never_cuts_corners_between_touching_hazards():
    from mission.route import astar
    # Two blocked cells touching at a corner: the diagonal between them is closed.
    blocked = [[False, True], [True, False]]
    assert astar(blocked, (0, 0), (1, 1)) == (None, None)


def test_uncertainty_override_must_stay_in_recorded_range():
    from mission.package import load, PackageError
    assert load(overrides={'regolith.density_g_cm3': 1.0})['values']['habitat.trench_mass_kg'] < V['habitat.trench_mass_kg']
    with pytest.raises(PackageError):
        load(overrides={'regolith.density_g_cm3': 5.0})


def test_mission_from_older_package_or_engine_is_discarded(tmp_path):
    from mission.store import Store, Mission, Revision, EventLog
    from sqlalchemy import select
    st = Store('sqlite:///' + str(tmp_path / 'old.db'))
    for field, old in (('package_hash', 'an-older-package'), ('version', 'arcadia-mars-v1/engine-0')):
        st.initialize()
        with st.transaction() as db:
            m = db.get(Mission, 'public')
            state = deepcopy(m.state)
            state['spec'][field] = old
            m.state = state
        assert st.check() is False  # an earlier build's run is not kept; Start begins a new genesis
        with st.transaction() as db:
            assert db.get(Mission, 'public') is None
            assert db.scalars(select(Revision).where(Revision.mission_id == 'public')).all() == []
            logged = [e.record for e in db.scalars(select(EventLog).where(EventLog.kind == 'mission-discarded')).all()]
            assert any((e['package_hash'] if field == 'package_hash' else e['engine_version']) == old for e in logged)
    st.initialize()
    assert st.check() is True


def test_assurance_cannot_approve_without_acknowledging_open_conditions():
    t = utc(2026, 10, 31, 12)
    s = commissioned_meta_state(env_at(t, uplink=False))
    start(s, 'survey', ['rover-1'], 'Survey.', 'survey / muse-spark-1.3', [s['spec']['package_id']])
    ids = [c['id'] for c in open_conditions(s, job_by_id(s, 'survey'))]
    assert 'no-site-imagery' in ids
    with pytest.raises(Exception, match='acknowledge'):
        assurance_decision(s, 'survey', True, 'No blockers.', 'assurance', [])
    review = assurance_decision(s, 'survey', True, 'Proceeding; the survey itself characterizes the site.', 'assurance', ids)
    assert review['open_conditions'] and review['acknowledged'] == ids


def test_reference_image_is_about_511_km_from_the_mission_site():
    from mission.media import _distance_km, HIRISE
    from mission.conditions import SITE
    d = _distance_km(SITE['latitude'], SITE['longitude_east'], HIRISE['latitude'], HIRISE['longitude_east'], V['mars.mean_radius_km'])
    assert d == pytest.approx(510.9, abs=0.5)


def test_dsn_range_from_round_trip_light_time_and_unreadable_feed_fails_loud():
    from mission.conditions import ConditionsError
    d = 214_000_000.0
    rtlt = 2 * d * 1000 / 299792458
    xml = f'''<dsn><station name="mdscc" friendlyName="Madrid"/><dish name="DSS63"><downSignal active="true" dataRate="2000000" spacecraft="MRO" spacecraftID="-74"/>
<upSignal active="true" dataRate="2000" spacecraft="MRO" spacecraftID="-74"/><target name="MRO" id="74" uplegRange="-1" downlegRange="-1" rtlt="{rtlt}"/></dish></dsn>'''.encode()
    parsed = parse_dsn(xml, d, SOI)
    assert parsed['uplink_to_mars'] and parsed['targets_seen'][0]['range_basis'] == 'round-trip light time'
    with pytest.raises(ConditionsError, match='no named targets'):
        parse_dsn(b'<dsn><dish name="DSS14"><target uplegRange="-1" downlegRange="-1" rtlt="-1"/></dish></dsn>', d, SOI)


def test_unconfirmed_dsn_reading_never_holds_work():
    t = utc(2026, 10, 31, 12)
    status = {'checked_at': t, 'error': None, 'last_mars_uplink_at': None, 'last_mars_target_seen_at': None, 'links': []}
    e = snapshot(t, SOI, status, V['comms.conjunction_sun_sep_deg'], TICK_S, t - TICK_S)
    assert e['link']['dsn'] == 'unconfirmed'
    s = commissioned_meta_state(e)
    start(s, 'survey', ['rover-1'], 'Survey.', 'survey / muse-spark-1.3', [s['spec']['package_id']])
    ids = [c['id'] for c in open_conditions(s, job_by_id(s, 'survey'))]
    assert not any(i.startswith('dsn') for i in ids)
    assurance_decision(s, 'survey', True, 'Proceed.', 'assurance', ids)
    assert job_by_id(s, 'survey')['status'] == 'running'

def test_event_log_keeps_every_status_write_and_receipt_change(tmp_path):
    from mission.store import Store, InferenceReceipt
    st = Store('sqlite:///' + str(tmp_path / 'log.db'))
    st.status('dsn', {'n': 1}); st.status('dsn', {'n': 2}); st.status('worker', {'heartbeat_at': 1})
    with st.transaction() as db:
        db.add(InferenceReceipt(id='r1', mission_id='public', record={'status': 'reserved'}))
    with st.transaction() as db:
        r = db.get(InferenceReceipt, 'r1'); r.record = {'status': 'completed'}
    rows = st.events('public')
    assert [r['record']['n'] for r in rows if r['kind'] == 'dsn'] == [1, 2]
    assert [r['kind'] for r in rows if r['source'] == 'receipt'] == ['reserved', 'completed']
    assert not any(r['kind'] == 'worker' for r in rows)


def test_http_429_retry_wait():
    from mission.provider import retry_wait
    assert retry_wait('2', 0) == 2.0 and retry_wait('600', 0) == 60.0 and [retry_wait(None, a) for a in range(3)] == [5.0, 15.0, 45.0]


def test_real_dsn_now_capture_identifies_mars_spacecraft():
    """Real DSN Now feed captured on the owner's machine (2026-10-31): ranges are -1; MRO and Mars Odyssey (M01O) are tracked."""
    from pathlib import Path
    raw = (Path(__file__).parent / 'data' / 'dsn-now-2026-10-31.xml').read_bytes()
    p = parse_dsn(raw, 214_000_000.0, SOI)
    assert p['dishes_in_feed'] == 14 and set(p['mars_spacecraft']) == {'MRO', 'M01O'}
    assert p['uplink_to_mars'] and all(t['identified_by'] == 'DSN mission abbreviation' for t in p['targets_seen'] if t['at_mars'])
    assert not any(t['at_mars'] for t in p['targets_seen'] if t['target'] in ('JWST', 'ESCB', 'LRO', 'SOHO'))


def test_provider_correlation_is_plain_json():
    import httpx, json
    from mission.provider import correlation_of
    r = httpx.Response(200, headers={'x-request-id': 'abc', 'date': 'Sat'})
    attempts = [correlation_of(r)]
    corr = {**correlation_of(r), 'provider_attempts': [dict(a) for a in attempts]}
    assert json.loads(json.dumps(corr))['provider_attempts'][0]['http_status'] == 200


def test_send_over_real_http_retries_429_and_returns_plain_json():
    """A local HTTP server (real sockets, real httpx client) answers 429 then 200."""
    import json, threading
    from http.server import BaseHTTPRequestHandler, HTTPServer
    from mission.provider import send
    hits = []

    class H(BaseHTTPRequestHandler):
        def do_POST(self):
            hits.append(1)
            self.rfile.read(int(self.headers.get('content-length', 0)))
            code, body = (429, b'{}') if len(hits) == 1 else (200, b'{"id": "resp_local"}')
            self.send_response(code); self.send_header('content-type', 'application/json'); self.send_header('retry-after', '0')
            self.send_header('x-request-id', f'req{len(hits)}'); self.end_headers(); self.wfile.write(body)

        def log_message(self, *a):
            pass
    srv = HTTPServer(('127.0.0.1', 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        body, corr = send({'x': 1}, 'k', url=f'http://127.0.0.1:{srv.server_address[1]}/', sleep=lambda s: None)
    finally:
        srv.shutdown()
    assert body['id'] == 'resp_local' and len(hits) == 2
    assert [a['http_status'] for a in json.loads(json.dumps(corr))['provider_attempts']] == [429, 200]


def test_rover_drives_only_in_daylight_and_keeps_its_distance_per_sol():
    # D19: no progress while the sun is below the horizon; the sol's distance is driven over its daylight steps.
    from mission.engine import start, assurance_decision, open_conditions, job_by_id, advance, sun_elevation_at, daylight_steps
    s = commissioned_meta_state(env_at(utc(2026, 11, 2, 17), uplink=False))
    start(s, 'survey', ['rover-1'], 'survey', 'survey / test', [s['spec']['package_id']])
    assurance_decision(s, 'survey', True, 'ok', 'assurance / test', [c['id'] for c in open_conditions(s, job_by_id(s, 'survey'))])
    s['failures_enabled'] = False
    day = daylight_steps(s, 0)
    assert 0 < day < 24
    moved = 0
    for _ in range(24):
        if job_by_id(s, 'survey')['status'] == 'complete':
            break
        before = job_by_id(s, 'survey')['done']
        s = advance(s)
        up = sun_elevation_at(s, s['tick']) > 0
        progressed = job_by_id(s, 'survey')['done'] > before
        assert progressed == up, (s['tick'], up)
        if not up:
            assert job_by_id(s, 'survey')['reason'].startswith('Night')
        moved += progressed
    sv = job_by_id(s, 'survey')
    assert moved == day and sv['status'] == 'complete' and sv['done'] == pytest.approx(V['rover.max_drive_m_per_sol'])
    assert not any(a['title'].endswith('behind plan') for a in s['activity'])  # night is planned, not a shortfall

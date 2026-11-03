import math
import re
from pathlib import Path
import pytest
from copy import deepcopy
from mission.engine import new_state, advance, start, modify, reasons, job_by_id, InvalidAction
from mission.package import load


def run(s, n, failures=False):
    s['failures_enabled'] = failures  # nominal-rate checks; D14 failures are tested separately
    for _ in range(n):
        if s['milestones']['ready']:
            break
        s = advance(s)
    return s


def test_engine_source_has_no_physical_constants():
    src = Path(__file__).resolve().parents[1].joinpath('mission', 'engine.py').read_text(encoding='utf-8')
    literals = {float(x) for x in re.findall(r'(?<![\w.])\d+\.?\d*(?:e-?\d+)?', src)}
    assert literals <= {0.0, 1.0, 1e-9, 24.0, 6.0, 8.0, 12.0}, literals


def test_state_comes_from_package():
    v = load()['values']
    s = new_state('meta')
    assert s['power_capacity_kw'] == 0 and not s['power_commissioned']
    assert job_by_id(s, 'power')['target'] == v['fsp.deploy_total_h']
    assert job_by_id(s, 'drill')['target'] == v['ice.overburden_max_m']
    assert job_by_id(s, 'water')['target'] == v['water.target_kg']
    assert job_by_id(s, 'trench')['target'] == pytest.approx(v['habitat.trench_mass_kg'])
    assert s['capital_unestimated'] == ['rodwell-1']


def test_readiness_time_matches_published_rates():
    v = load()['values']
    tick_h = v['mars.day_length_h'] / 24
    s = run(new_state('fixed-priority'), 24 * 200)
    assert s['milestones']['ready'] and s['status'] == 'active'  # readiness is a milestone; operations continue
    # D18 + D21: excavators mine on battery; a charged spare is swapped in when a pack runs low while the depleted pack
    # charges, so mining continues at the published mining rate instead of stopping for recharge.
    trench_ticks = math.ceil(v['habitat.trench_mass_kg'] / (2 * v['excavator.mining_rate_kg_h'] * tick_h))
    survey_ticks = math.ceil(v['rover.max_drive_m_per_sol'] / (v['rover.max_drive_m_per_sol'] / v['mars.day_length_h'] * tick_h) - 1e-9)
    sv = job_by_id(s, 'survey')
    assert sv['completed_tick'] - sv['started_tick'] == survey_ticks
    took = job_by_id(s, 'trench')['completed_tick'] - job_by_id(s, 'trench')['started_tick']
    assert abs(took - trench_ticks) <= 0.02 * trench_ticks, (took, trench_ticks)  # whole-step swap timing


def test_resources_equal_physical_ledger_and_energy_matches_power():
    s = run(new_state('fixed-priority'), 24 * 30)
    for r, value in s['resources'].items():
        assert value == pytest.approx(sum(e['amount'] for e in s['physical_ledger'] if e['resource'] == r))
    assert s['energy_used_kwh'] == pytest.approx(sum(e['energy_kwh'] for e in s['physical_ledger'] if e['energy_kwh'] is not None) + s.get('charging_energy_kwh', 0.0))
    assert any(e['energy_kwh'] is None for e in s['physical_ledger'] if e['job_id'] == 'drill')
    assert s['spent_usd'] == pytest.approx(sum(e['amount_usd'] for e in s['ledger'] if e['kind'] == 'operations'))


def test_dependencies_assets_and_power_are_enforced():
    s = new_state('meta')
    assert any('Waiting for' in r for r in reasons(s, job_by_id(s, 'trench'), ['excavator-1']))
    with pytest.raises(InvalidAction):
        start(s, 'survey', ['excavator-1'], 'wrong equipment', 'test', ['arcadia-mars-v1'])
    start(s, 'survey', ['rover-1'], 'survey first', 'test', ['arcadia-mars-v1'])
    s2 = run(s, 25)
    assert any('fission power not yet commissioned' in r or 'Waiting for deploy' in r for r in reasons(s2, job_by_id(s2, 'trench'), ['excavator-1']))
    assert any('Waiting for deploy' in r for r in reasons(s2, job_by_id(s2, 'drill'), ['rodwell-1']))
    start(s2, 'power', ['fsp-1'], 'deploy', 'test', ['oleson2022'])
    with pytest.raises(InvalidAction, match='review'):
        start(s2, 'power', ['fsp-1'], 'again', 'test', ['oleson2022'])


def test_power_commissioning_enables_grid():
    v = load()['values']
    s = new_state('meta')
    with pytest.raises(InvalidAction, match='not commissioned'):
        modify(s, {'power_capacity_kw': 10})
    start(s, 'power', ['fsp-1'], 'deploy', 'test', ['oleson2022'])
    from mission.engine import assurance_decision, open_conditions
    assurance_decision(s, 'power', True, 'Checked.', 'test', [c['id'] for c in open_conditions(s, job_by_id(s, 'power'))])
    s = run(s, 24 * 8)
    assert s['power_commissioned'] and s['power_capacity_kw'] == v['power.fsp_output_kwe']
    assert job_by_id(s, 'power')['completed_tick'] == math.ceil(v['fsp.deploy_total_h'] / (v['mars.day_length_h'] / 24) - 1e-9)


def test_power_loss_stops_work_and_reports_it():
    s = run(new_state('fixed-priority'), 24 * 8)
    assert job_by_id(s, 'water')['status'] == 'running'
    s = modify(s, {'power_capacity_kw': 5})
    s = advance(s)
    w = job_by_id(s, 'water')
    assert w['status'] in ('blocked',) and ('power' in w['reason'] or 'kW' in w['reason'])
    assert s['power_used_kw'] <= s['power_capacity_kw']


def test_equipment_failure_stops_assigned_job():
    s = run(new_state('fixed-priority'), 24 * 8)
    s = modify(s, {'equipment': {'excavator-1': False}})
    s = advance(s)
    t = job_by_id(s, 'trench')
    assert 'excavator-1' not in t['assigned']


def test_unknown_source_reference_rejected():
    s = new_state('meta')
    with pytest.raises(InvalidAction, match='pinned'):
        start(s, 'survey', ['rover-1'], 'x', 'test', ['made-up-source'])


def test_random_failures_follow_published_rate_and_are_reproducible():
    v = load()['values']
    a = run(new_state('fixed-priority'), 24 * 300, failures=True)
    b = run(new_state('fixed-priority'), 24 * 300, failures=True)
    fa = [f for f in a['faults'] if f['kind'] == 'failure']
    assert fa == [f for f in b['faults'] if f['kind'] == 'failure']
    assert fa and all(f['asset_id'] in ('rover-1', 'excavator-1', 'excavator-2') for f in fa)
    assert v['reliability.mobile_robot_failures_per_h'] == pytest.approx(6.551e-4, rel=1e-3)


def test_agents_can_create_work_from_templates():
    from mission.engine import instantiate_job
    s = new_state('meta')
    jid = instantiate_job(s, 'water-batch', 'director', 'More water needed.')
    j = job_by_id(s, jid)
    assert j['status'] == 'pending' and j['dependencies'] == ['drill', 'power'] and jid in s['priority'] and jid not in s['spec']['readiness']['jobs']
    with pytest.raises(InvalidAction):
        instantiate_job(s, 'no-such-template', 'director', 'x')


def test_correlated_error_evaluation_flags_consensus_that_went_wrong():
    from mission.evaluation import evaluate
    s = new_state('meta')
    s['cycle_log'] = [{'cycle_id': 'c1', 'tick': 0, 'director_priority': None, 'authorized': [],
                       'assessments': {'survey': {'recommended_jobs': ['survey'], 'job_judgements': {'survey': 'proceed', 'trench': 'hold'}, 'missing_information': ['Local boulder density']},
                                       'construction': {'recommended_jobs': [], 'job_judgements': {'survey': 'proceed', 'trench': 'hold'}, 'missing_information': ['local boulder density']},
                                       'assurance': {'recommended_jobs': [], 'job_judgements': {'survey': 'proceed', 'trench': 'proceed'}, 'missing_information': []}}}]
    s['activity'].append({'id': 99, 'tick': 3, 'title': 'Survey rover (Perseverance-class) failed', 'detail': '', 'job_id': 'survey'})
    c = evaluate(s)['cycles'][0]
    # Pairs agree on 2/2, 1/2 and 1/2 jobs; the unanimous "proceed" on survey was followed by a failure.
    assert c['mean_pairwise_agreement'] == pytest.approx((1 + 0.5 + 0.5) / 3, abs=1e-3)
    assert c['consensus_jobs'] == {'survey': {'judgement': 'proceed', 'outcome': 'stopped (failure or blocker)'}}
    assert c['possible_correlated_error'] and c['consensus_with_bad_outcome'] == ['survey']
    assert c['shared_missing_information'][0]['roles'] == ['construction', 'survey']
    # Department leads may recommend only their own jobs, yet they share every proposition, so consensus is reachable.
    s['activity'].pop()
    assert not evaluate(s)['cycles'][0]['possible_correlated_error']


def test_standby_pauses_work_and_resumes():
    from mission.engine import set_standby
    s = new_state('fixed-priority'); s['failures_enabled'] = False
    s = advance(s)
    assert job_by_id(s, 'survey')['status'] == 'running'
    done = job_by_id(s, 'survey')['done']
    basis = [{'observation_id': 'msl:air_min_c:5001:after5000', 'kind': 'weather-estimate', 'station': 'msl', 'variable': 'air_min_c',
              'value': -82, 'record_hash': 'h', 'interpretation': 'Estimated night minimum below the recent range'}]
    set_standby(s, ['rover-1'], 3, 'Estimated night minimum below recent range', 'director', basis)
    for _ in range(2):  # standby covers ticks t+1 and t+2
        s = advance(s)
        assert job_by_id(s, 'survey')['done'] == done and job_by_id(s, 'survey')['reason'].startswith('Standby')
    s = advance(s)
    assert job_by_id(s, 'survey')['done'] > done and any(a['title'].endswith('resumed') for a in s['activity'])
    for bad in ('', 'msl air_min_c sol 5001', [{'observation_id': 'x'}], [{**basis[0], 'kind': 'rumour'}], [{**basis[0], 'interpretation': ' '}]):
        with pytest.raises(InvalidAction):
            set_standby(s, ['rover-1'], 2, 'x', 'director', bad)
    before = deepcopy(s)
    with pytest.raises(InvalidAction):
        set_standby(s, ['rover-1', 'no-such-unit'], 2, 'x', 'director', basis)
    assert s == before  # a rejected command changes nothing


def _meta_trench_running():
    # Meta mission with grid power and the trench running on both excavators (dependencies marked done for the test).
    from mission.engine import assurance_decision, open_conditions
    s = new_state('meta')
    s.update(power_capacity_kw=s['spec']['assets'][4]['output_kw'], power_commissioned=True, planning_needed=False)
    for jid in ('power', 'survey'):
        job_by_id(s, jid).update(status='complete', done=job_by_id(s, jid)['target'], progress=1.0)
    start(s, 'trench', ['excavator-1', 'excavator-2'], 'dig', 'construction / test', ['rassor2016'])
    assurance_decision(s, 'trench', True, 'ok', 'assurance / test', [c['id'] for c in open_conditions(s, job_by_id(s, 'trench'))])
    s['failures_enabled'] = False
    return s


def test_batteries_drain_while_working_and_low_battery_asks_agents_to_replan():
    from mission.engine import asset_by_id, step_energy_wh
    v = load()['values']
    s = _meta_trench_running()
    s = advance(s)
    a = asset_by_id(s, 'excavator-1')
    assert a['soc_wh'] == pytest.approx(v['excavator.battery_wh'] - step_energy_wh(s, a))
    while asset_by_id(s, 'excavator-1')['soc_wh'] >= step_energy_wh(s, a):
        s['planning_needed'] = False
        s = advance(s)
    done = job_by_id(s, 'trench')['done']
    s = advance(s)
    assert s['planning_needed'] and any(x['title'].startswith('Battery low') for x in s['activity'])
    assert job_by_id(s, 'trench')['done'] == done and job_by_id(s, 'trench')['reason'].startswith('Paused')


def test_agents_recharge_from_grid_and_work_resumes():
    from mission.engine import asset_by_id, step_energy_wh, charge
    s = _meta_trench_running()
    while asset_by_id(s, 'excavator-1')['soc_wh'] >= step_energy_wh(s, asset_by_id(s, 'excavator-1')):
        s = advance(s)
    used = s['power_used_kw']
    charge(s, ['excavator-1', 'excavator-2'], 'Battery below one step of work.', 'director / test')
    assert s['power_used_kw'] == pytest.approx(used + 2 * asset_by_id(s, 'excavator-1')['charge_kw'])
    with pytest.raises(InvalidAction, match='already charging'):
        charge(s, ['excavator-1'], 'again', 'director / test')
    while asset_by_id(s, 'excavator-1')['charging']:
        s = advance(s)
    assert asset_by_id(s, 'excavator-1')['soc_wh'] == asset_by_id(s, 'excavator-1')['battery_wh'] and s['power_used_kw'] == pytest.approx(used)
    done = job_by_id(s, 'trench')['done']
    s = advance(s)
    assert job_by_id(s, 'trench')['done'] > done


def test_charging_needs_commissioned_grid_power():
    from mission.engine import charge
    s = new_state('meta')
    with pytest.raises(InvalidAction, match='not commissioned'):
        charge(s, ['excavator-1'], 'x', 'director / test')
    with pytest.raises(InvalidAction, match='no battery'):
        s.update(power_capacity_kw=40, power_commissioned=True)
        charge(s, ['rover-1'], 'x', 'director / test')


def test_work_behind_plan_asks_agents_to_replan_once():
    s = _meta_trench_running()
    from mission.engine import asset_by_id
    asset_by_id(s, 'excavator-2')['standby_until_tick'] = s['tick'] + 5  # half the crew idle: behind the authorized rate
    asset_by_id(s, 'excavator-2')['standby'] = {'reason': 'test'}
    for _ in range(4):
        s = advance(s)
    assert len([x for x in s['activity'] if x['title'].endswith('behind plan')]) == 1 and s['planning_needed']


def test_charging_stops_when_grid_supply_disappears():
    # Review finding 1: chargers and jobs book power on one ledger; when supply is gone, charging adds no energy.
    from mission.engine import asset_by_id, charge
    s = _meta_trench_running()
    for _ in range(3):
        s = advance(s)
    charge(s, ['excavator-1'], 'top up', 'director / test')
    soc = asset_by_id(s, 'excavator-1')['soc_wh']
    s = modify(s, {'power_capacity_kw': 0})
    s = advance(s)
    a = asset_by_id(s, 'excavator-1')
    assert not a['charging'] and a['soc_wh'] == soc and s['power_used_kw'] == 0
    assert any(x['title'] == 'Charging ended: ' + a['name'] for x in s['activity'])


def test_rejected_charge_command_changes_nothing():
    # Review finding 2: one valid unit followed by an invalid one: the whole command is rejected, nothing is reserved.
    from mission.engine import charge
    s = _meta_trench_running()
    s = advance(s)
    before = deepcopy(s)
    for ids in (['excavator-1', 'rover-1'], ['excavator-1', 'no-such-unit'], ['excavator-1', 'excavator-1']):
        with pytest.raises(InvalidAction):
            charge(s, ids, 'x', 'director / test')
        assert s == before


def test_planner_tools_commit_only_when_accepted():
    # Review finding 2 at the planner: each tool runs against a copy and is committed only on success.
    from mission.planner import atomic
    s = new_state('meta')
    before = deepcopy(s)
    def partial(t):
        t['jobs'][0]['status'] = 'running'
        raise InvalidAction('rejected after a partial change')
    with pytest.raises(InvalidAction):
        atomic(s, partial)
    assert s == before


def test_unknown_drilling_power_is_not_zero():
    # Review finding 3: an unpublished power draw is unknown; with no capacity it cannot start, and an accepted decision
    # says it was not physically validated for power.
    s = new_state('fixed-priority')
    s.update(power_capacity_kw=0.0, power_commissioned=True)
    for jid in ('power', 'survey'):
        job_by_id(s, jid).update(status='complete', done=job_by_id(s, jid)['target'], progress=1.0)
    errors = reasons(s, job_by_id(s, 'drill'), ['rodwell-1'])
    assert errors and 'not published' in errors[0]
    s['power_capacity_kw'] = 40.0
    assert reasons(s, job_by_id(s, 'drill'), ['rodwell-1']) == []
    did = start(s, 'drill', ['rodwell-1'], 'drill', 'fixed-priority', [s['spec']['package_id']])
    d = next(x for x in s['decisions'] if x['id'] == did)
    assert d['calculation']['power_kw'] is None and not d['calculation']['power_published'] and 'not physically validated' in d['validation']
    # Audit: the unknown draw is never booked as 0 kW. The drill holds all 40 kW that were unallocated, so nothing else
    # can be booked onto the grid while it runs, and the hold is released when it stops.
    j = job_by_id(s, 'drill')
    assert j['reserved_kw'] == 40.0 and s['power_used_kw'] == 40.0 and d['calculation']['reserved_kw'] == 40.0
    from mission.engine import charge, asset_by_id
    asset_by_id(s, 'excavator-1')['soc_wh'] = 0.0
    with pytest.raises(InvalidAction, match='Not enough grid power'):  # no capacity left for other grid work
        charge(s, ['excavator-1'], 'test', 'fixed-priority')
    from mission.engine import release
    release(s, j, 'blocked', 'test')
    assert s['power_used_kw'] == 0.0 and 'reserved_kw' not in j


def test_operations_continue_after_readiness():
    # Review finding 6: readiness is a milestone; added work (a water batch) still runs to completion afterwards.
    from mission.engine import instantiate_job
    s = run(new_state('fixed-priority'), 24 * 200)
    assert s['milestones']['ready'] and s['status'] == 'active'
    jid = instantiate_job(s, 'water-batch', 'test', 'More water')
    for _ in range(24 * 200):
        if job_by_id(s, jid)['status'] == 'complete':
            break
        s = advance(s)
    assert job_by_id(s, jid)['status'] == 'complete' and s['status'] == 'active'


def test_forecast_and_uncertainty_handle_created_work():
    # Review finding 8: work created from a template resolves through its template in the forecast.
    from mission.engine import instantiate_job
    from mission.schedule import forecast, uncertainty
    s = new_state('fixed-priority'); s['failures_enabled'] = False
    s = advance(s)
    for template in ('water-batch', 'survey-extension'):
        jid = instantiate_job(s, template, 'test', 'More work')
        f = forecast(s, 24 * 200)
        assert f['forecast_readiness_tick'] is not None and any(r['job_id'] == jid for r in f['jobs'])
    u = uncertainty(s, 24 * 200)
    assert u['parameters'] and u['readiness_tick_range'] is not None


def test_rover_battery_drains_while_driving_and_the_mmrtg_recharges_it():
    # Register 39: NASA's published 2,408 Wh battery and <200 W slow-driving bound; the 110 W MMRTG covers part of the draw.
    from mission.engine import asset_by_id, rover_drive_net_wh
    s = new_state('fixed-priority'); s['failures_enabled'] = False
    rover = asset_by_id(s, 'rover-1')
    net = rover_drive_net_wh(s, rover)
    assert rover['rtg_battery_wh'] == 2408 and net == pytest.approx((200 - 110) * s['spec']['tick_hours'])
    start(s, 'survey', ['rover-1'], 'Survey.', 'fixed-priority', [s['spec']['package_id']])
    s = advance(s); rover = asset_by_id(s, 'rover-1')
    assert job_by_id(s, 'survey')['done'] > 0 and rover['rtg_soc_wh'] == pytest.approx(2408 - net)
    rover['rtg_soc_wh'] = net / 2  # below one driving step
    done = job_by_id(s, 'survey')['done']
    s = advance(s); rover = asset_by_id(s, 'rover-1')
    assert job_by_id(s, 'survey')['done'] == done and 'Rover battery' in job_by_id(s, 'survey')['reason']
    assert rover['rtg_soc_wh'] == pytest.approx(net / 2 + 110 * s['spec']['tick_hours'])  # MMRTG recharge while waiting
    s = advance(s)
    assert job_by_id(s, 'survey')['done'] > done


def test_battery_swap_keeps_the_excavator_working_and_charges_the_spare():
    # Register 40 / D21: a charged spare is swapped in within the step; the depleted pack charges on the grid as the spare.
    from mission.engine import asset_by_id, swap_battery, step_energy_wh
    s = new_state('fixed-priority'); s['failures_enabled'] = False
    s.update(power_capacity_kw=40.0, power_commissioned=True)
    a = asset_by_id(s, 'excavator-1')
    full = a['battery_wh']
    with pytest.raises(InvalidAction, match='already full'):
        swap_battery(s, ['excavator-1'], 'test', 'test')
    a['soc_wh'] = step_energy_wh(s, a) / 2
    swap_battery(s, ['excavator-1'], 'Battery below one step.', 'test')
    assert a['soc_wh'] == full and a['spare_soc_wh'] < full and a['spare_charging'] and s['power_used_kw'] == a['charge_kw']
    with pytest.raises(InvalidAction, match='spare pack is not charged'):
        a['soc_wh'] = 0.0; swap_battery(s, ['excavator-1'], 'again', 'test')
    a['soc_wh'] = full
    for _ in range(48):
        s = advance(s)
        a = asset_by_id(s, 'excavator-1')
        if not a['spare_charging']:
            break
    assert a['spare_soc_wh'] == full and s['power_used_kw'] == 0.0

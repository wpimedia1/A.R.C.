import math
import re
from pathlib import Path
import pytest
from mission.engine import new_state, advance, start, modify, reasons, job_by_id, InvalidAction
from mission.package import load


def run(s, n, failures=False):
    s['failures_enabled'] = failures  # nominal-rate checks; D14 failures are tested separately
    for _ in range(n):
        if s['status'] != 'active':
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
    assert s['milestones']['ready'] and s['status'] == 'complete'
    trench_ticks = math.ceil(v['habitat.trench_mass_kg'] / (2 * v['excavator.rate_kg_h'] * tick_h))
    survey_ticks = math.ceil(v['rover.max_drive_m_per_sol'] / (v['rover.max_drive_m_per_sol'] / v['mars.day_length_h'] * tick_h) - 1e-9)
    sv = job_by_id(s, 'survey')
    assert sv['completed_tick'] - sv['started_tick'] == survey_ticks
    assert job_by_id(s, 'trench')['completed_tick'] - job_by_id(s, 'trench')['started_tick'] in (trench_ticks, trench_ticks + 1)


def test_resources_equal_physical_ledger_and_energy_matches_power():
    s = run(new_state('fixed-priority'), 24 * 30)
    for r, value in s['resources'].items():
        assert value == pytest.approx(sum(e['amount'] for e in s['physical_ledger'] if e['resource'] == r))
    assert s['energy_used_kwh'] == pytest.approx(sum(e['energy_kwh'] for e in s['physical_ledger'] if e['energy_kwh'] is not None))
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
    with pytest.raises(InvalidAction, match='running'):
        start(s2, 'power', ['fsp-1'], 'again', 'test', ['oleson2022'])


def test_power_commissioning_enables_grid():
    v = load()['values']
    s = new_state('meta')
    with pytest.raises(InvalidAction, match='not commissioned'):
        modify(s, {'power_capacity_kw': 10})
    start(s, 'power', ['fsp-1'], 'deploy', 'test', ['oleson2022'])
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
                       'assessments': {'survey': {'recommended_jobs': ['survey'], 'missing_information': ['Local boulder density']},
                                       'construction': {'recommended_jobs': ['survey'], 'missing_information': ['local boulder density']},
                                       'assurance': {'recommended_jobs': [], 'missing_information': []}}}]
    s['activity'].append({'id': 99, 'tick': 3, 'title': 'Survey rover (Perseverance-class) failed', 'detail': '', 'job_id': 'survey'})
    c = evaluate(s)['cycles'][0]
    assert c['mean_pairwise_agreement'] == 1.0 and c['possible_correlated_error'] and c['shared_missing_information'][0]['roles'] == ['construction', 'survey']


def test_standby_pauses_work_and_resumes():
    from mission.engine import set_standby
    s = new_state('fixed-priority'); s['failures_enabled'] = False
    s = advance(s)
    assert job_by_id(s, 'survey')['status'] == 'running'
    done = job_by_id(s, 'survey')['done']
    set_standby(s, ['rover-1'], 3, 'Estimated night minimum below recent range', 'director', 'msl air_min_c sol 5001 est -82 [-88..-76]')
    for _ in range(2):  # standby covers ticks t+1 and t+2
        s = advance(s)
        assert job_by_id(s, 'survey')['done'] == done and job_by_id(s, 'survey')['reason'].startswith('Standby')
    s = advance(s)
    assert job_by_id(s, 'survey')['done'] > done and any(a['title'].endswith('resumed') for a in s['activity'])
    with pytest.raises(InvalidAction):
        set_standby(s, ['rover-1'], 2, 'x', 'director', '')

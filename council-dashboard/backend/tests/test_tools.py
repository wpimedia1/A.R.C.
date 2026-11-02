"""Agent tool execution against real state; no model or network involved."""
import pytest
from mission.engine import new_state, job_by_id, InvalidAction
from mission.planner import execute_tool, context, TOOLS
from mission.agents import validate_assessment, observe


def test_tool_schemas_are_strict():
    for t in TOOLS:
        assert t['strict'] and t['parameters']['additionalProperties'] is False
        assert set(t['parameters']['required']) == set(t['parameters']['properties'])


def test_estimate_then_submit():
    s = new_state('meta')
    est = execute_tool(s, 'estimate_job', {'job_id': 'survey', 'asset_ids': ['rover-1']}, 'survey')
    assert est['validation_errors'] == [] and est['ticks_to_complete'] == 24
    out = execute_tool(s, 'submit_work_order', {'job_id': 'survey', 'asset_ids': ['rover-1'], 'summary': 'Survey', 'source_ids': ['autonav2021']}, 'survey')
    assert out['accepted'] and job_by_id(s, 'survey')['status'] == 'review'  # onboard assurance approves before it runs (D10)


def test_other_department_cannot_submit():
    s = new_state('meta')
    with pytest.raises(InvalidAction, match='department'):
        execute_tool(s, 'submit_work_order', {'job_id': 'survey', 'asset_ids': ['rover-1'], 'summary': 'x', 'source_ids': ['autonav2021']}, 'resources')


def test_inspect_parameter_returns_provenance():
    s = new_state('meta')
    p = execute_tool(s, 'inspect_parameter', {'name': 'rodwell.power_kw'}, 'resources')
    assert p['source'] == 'hoffman2016' and p['quote'] and p['source_detail']['url']


def test_observation_withholds_priority_and_conflicts():
    s = new_state('meta')
    s['source_pins'] = {'arcadia-mars-v1': 'x', 'autonav2021': 'y'}
    o = observe(s, 'survey', context(s))
    assert 'priority' not in o['world'] and 'department_conflicts' not in o['world']


def test_assessment_validation():
    s = new_state('meta')
    s['source_pins'] = {'arcadia-mars-v1': 'x'}
    judge = [{'job_id': j['id'], 'judgement': 'proceed' if j['id'] == 'survey' else 'hold'} for j in s['jobs']]
    base = {'summary': 'go', 'recommended_jobs': ['survey'], 'job_judgements': judge, 'missing_information': [], 'source_ids': ['arcadia-mars-v1']}
    ok = validate_assessment(s, 'survey', base)
    assert ok['recommended_jobs'] == ['survey']
    for bad in ({**base, 'recommended_jobs': ['water']},           # another department's job
                {**base, 'job_judgements': judge[:-1]},           # every open job must be judged
                {**base, 'job_judgements': judge + judge[:1]},    # exactly once
                {**base, 'job_judgements': [{**judge[0], 'judgement': 'maybe'}] + judge[1:]},
                {k: v for k, v in base.items() if k != 'job_judgements'}):
        with pytest.raises(InvalidAction):
            validate_assessment(s, 'survey', bad)

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
    assert out['accepted'] and job_by_id(s, 'survey')['status'] == 'running'


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
    ok = validate_assessment(s, 'survey', {'summary': 'go', 'recommended_jobs': ['survey'], 'missing_information': [], 'source_ids': ['arcadia-mars-v1']})
    assert ok['recommended_jobs'] == ['survey']
    with pytest.raises(InvalidAction):
        validate_assessment(s, 'survey', {'summary': 'go', 'recommended_jobs': ['water'], 'missing_information': [], 'source_ids': ['arcadia-mars-v1']})

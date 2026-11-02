"""Independent assessments and outcome memory; no authority to change balances."""
from copy import deepcopy
from .engine import InvalidAction
from .spec import digest

PROTOCOL = 'observe-think-act-remember-1'


def observe(state, role, shared):
    """One frozen world, private role memory, no peer proposals or old priorities."""
    world = deepcopy(shared)
    world.pop('priority', None)
    world.pop('department_conflicts', None)
    for job in world['jobs']:
        job.pop('reason', None)
    return {'role': role, 'observation_hash': digest(world), 'world': world,
            'own_memory': deepcopy(state.get('agent_memory', {}).get(role, [])[-4:]),
            'own_work_outcomes': [
                {k: j.get(k) for k in ('id', 'status', 'progress', 'started_tick', 'completed_tick', 'reason')}
                for j in state['jobs'] if j['owner'] == role][-12:]}


def validate_assessment(state, role, args):
    if set(args) != {'summary', 'recommended_jobs', 'job_judgements', 'missing_information', 'source_ids'}:
        raise InvalidAction('Assessment requires summary, recommended jobs, job judgements, information gaps and sources')
    if not isinstance(args['summary'], str) or not 1 <= len(args['summary']) <= 600:
        raise InvalidAction('Assessment needs a bounded public summary')
    allowed = {j['id'] for j in state['jobs'] if j['status'] not in ('complete', 'dormant')
               and (role == 'assurance' or j['owner'] == role)}
    jobs = args['recommended_jobs']
    if not isinstance(jobs, list) or any(not isinstance(j, str) or j not in allowed for j in jobs) or len(set(jobs)) != len(jobs):
        raise InvalidAction('Assessment recommended unknown or another department work')
    # Shared propositions: every agent judges every active job (proceed or hold), so agreement between agents is measurable.
    active = {j['id'] for j in state['jobs'] if j['status'] not in ('complete', 'dormant')}
    judged = args['job_judgements']
    if (not isinstance(judged, list) or any(not isinstance(x, dict) or set(x) != {'job_id', 'judgement'} or x['judgement'] not in ('proceed', 'hold') for x in judged)
            or sorted(x['job_id'] for x in judged) != sorted(active)):
        raise InvalidAction('Assessment must judge every active job exactly once (proceed or hold)')
    gaps = args['missing_information']
    if not isinstance(gaps, list) or len(gaps) > 8 or any(not isinstance(g, str) or not 1 <= len(g) <= 400 for g in gaps):
        raise InvalidAction('Information gaps must be bounded public descriptions')
    sources = args['source_ids']
    if not isinstance(sources, list) or not 1 <= len(sources) <= 6 or any(not isinstance(k, str) or k not in state['source_pins'] for k in sources):
        raise InvalidAction('Assessment citations must resolve to pinned evidence')
    return deepcopy(args)


def remember(state, cycle, receipts):
    memory = state.setdefault('agent_memory', {})
    for assessment in cycle.get('assessments', []):
        role = assessment['role']
        entry = {'cycle_id': cycle['id'], 'tick': state['tick'],
                 'observation_hash': assessment['observation_hash'],
                 'assessment': assessment['assessment'],
                 'actions': [{'tool': item['tool'], 'accepted': item.get('result',{}).get('accepted'),
                              'rejected': item.get('result',{}).get('rejected')}
                             for r in receipts if r.get('role') == role for item in r.get('receipts',[])],
                 'work_outcomes': [{k: j.get(k) for k in ('id', 'status', 'progress', 'reason')}
                                   for j in state['jobs'] if j['owner'] == role][-12:]}
        memory.setdefault(role, []).append(entry)
        # Complete history is retained in immutable mission revisions.
        memory[role] = memory[role][-12:]
    # Compact, complete per-cycle record used by the correlated-error evaluation (evaluation.py).
    state.setdefault('cycle_log', []).append({
        'cycle_id': cycle['id'], 'tick': state['tick'],
        'assessments': {a['role']: {'recommended_jobs': a['assessment'].get('recommended_jobs', []),
                                    'job_judgements': {x['job_id']: x['judgement'] for x in a['assessment'].get('job_judgements', [])},
                                    'missing_information': a['assessment'].get('missing_information', [])} for a in cycle.get('assessments', [])},
        'director_priority': (cycle.get('director') or {}).get('priority'),
        'authorized': sorted({d['job_id'] for d in state['decisions'] if d['tick'] == state['tick']})})
    cycle['status'] = 'needs attention' if state.get('inference_stopped') else 'work authorized'
    cycle['planning_status'] = state['planning_status']
    state['agent_cycle'] = cycle
    state['agent_protocol'] = PROTOCOL

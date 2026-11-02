"""Do independent assessments reduce correlated errors? (gap 27)

Every planning cycle, each agent (department leads and assurance) independently judges the same propositions: for every
active job, should it proceed now or be held. Agreement is the share of jobs on which two agents gave the same judgement,
averaged over all pairs. A job is consensus when every agent judged it the same way. Each consensus is then compared
with what happened: a unanimous "proceed" on work that was later held by assurance or stopped (failure or blocker) is
flagged as a possible correlated error, the agents sharing the same mistaken view. Missing-information items raised by
several agents together are listed.
"""
from itertools import combinations

BAD = ('held by assurance', 'stopped (failure or blocker)')


def evaluate(state):
    jobs = {j['id']: j for j in state['jobs']}
    cycles = []
    for c in state.get('cycle_log', []):
        judged = {r: a['job_judgements'] for r, a in c['assessments'].items() if a.get('job_judgements')}
        after = c['tick']
        held = {d['job_id'] for d in state['decisions'] if (d.get('assurance') or {}).get('approved') is False and d['tick'] >= after}
        stopped = {e['job_id'] for e in state['activity'] if e.get('job_id') and e['tick'] >= after
                   and (' stopped' in e['title'] or ' failed' in e['title'])}

        def outcome(j):
            if j not in jobs: return 'unknown job'
            if j in held: return 'held by assurance'
            if j in stopped: return 'stopped (failure or blocker)'
            return jobs[j]['status']
        props = sorted(set.intersection(*(set(v) for v in judged.values()))) if judged else []
        pairs = [sum(x[p] == y[p] for p in props) / len(props) for x, y in combinations(judged.values(), 2)] if props else []
        consensus = {p: next(iter(judged.values()))[p] for p in props
                     if len(judged) >= 2 and len({v[p] for v in judged.values()}) == 1}
        outcomes = {p: {'judgement': v, 'outcome': outcome(p)} for p, v in consensus.items()}
        bad = [p for p, o in outcomes.items() if o['judgement'] == 'proceed' and o['outcome'] in BAD]
        gaps = {}
        for r, a in c['assessments'].items():
            for g in a['missing_information']:
                gaps.setdefault(g.strip().lower(), set()).add(r)
        shared_gaps = sorted([{'item': g, 'roles': sorted(r)} for g, r in gaps.items() if len(r) >= 2], key=lambda x: -len(x['roles']))
        agreement = round(sum(pairs) / len(pairs), 3) if pairs else None
        cycles.append({'cycle_id': c['cycle_id'], 'tick': c['tick'], 'agents': sorted(judged), 'propositions': len(props),
                       'mean_pairwise_agreement': agreement, 'consensus_jobs': outcomes,
                       'shared_missing_information': shared_gaps[:8],
                       'possible_correlated_error': bool(bad), 'consensus_with_bad_outcome': bad})
    measured = [c for c in cycles if c['mean_pairwise_agreement'] is not None]
    return {'method': __doc__.strip(), 'cycles': cycles,
            'summary': {'cycles': len(cycles), 'flagged': sum(1 for c in cycles if c['possible_correlated_error']),
                        'mean_agreement': round(sum(c['mean_pairwise_agreement'] for c in measured) / len(measured), 3) if measured else None}}

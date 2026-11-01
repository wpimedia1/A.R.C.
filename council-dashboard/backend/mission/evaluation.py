"""Do independent assessments reduce correlated errors? (gap 27)

For every planning cycle: how much the independent agents agreed (pairwise Jaccard of recommended jobs), which jobs had
consensus, what later happened to them (completed, running, held by assurance, stopped by failure or blocker), and which
missing-information items several agents raised together. High agreement followed by a bad outcome is flagged as a possible
correlated error: the agents shared the same mistaken view.
"""
from itertools import combinations


def _jaccard(a, b):
    a, b = set(a), set(b)
    return 1.0 if not a and not b else len(a & b) / len(a | b)


def evaluate(state):
    jobs = {j['id']: j for j in state['jobs']}
    held = {d['job_id'] for d in state['decisions'] if (d.get('assurance') or {}).get('approved') is False}
    stopped = {e['job_id'] for e in state['activity'] if e.get('job_id') and (' stopped' in e['title'] or ' failed' in e['title'] or 'could not start' in e['title'])}
    cycles = []
    for c in state.get('cycle_log', []):
        specialists = {r: a for r, a in c['assessments'].items() if r != 'assurance'}
        pairs = [_jaccard(x['recommended_jobs'], y['recommended_jobs']) for x, y in combinations(specialists.values(), 2)]
        counts = {}
        for a in specialists.values():
            for j in set(a['recommended_jobs']):
                counts[j] = counts.get(j, 0) + 1
        consensus = sorted(j for j, n in counts.items() if n >= 2)
        def outcome(j):
            if j not in jobs: return 'unknown job'
            if j in held: return 'held by assurance'
            if j in stopped: return 'stopped (failure or blocker)'
            return jobs[j]['status']
        gaps = {}
        for r, a in c['assessments'].items():
            for g in a['missing_information']:
                gaps.setdefault(g.strip().lower(), set()).add(r)
        shared_gaps = sorted([{'item': g, 'roles': sorted(r)} for g, r in gaps.items() if len(r) >= 2], key=lambda x: -len(x['roles']))
        outcomes = {j: outcome(j) for j in consensus}
        agreement = round(sum(pairs) / len(pairs), 3) if pairs else None
        bad = [j for j, o in outcomes.items() if o in ('held by assurance', 'stopped (failure or blocker)')]
        cycles.append({'cycle_id': c['cycle_id'], 'tick': c['tick'], 'mean_pairwise_agreement': agreement, 'consensus_jobs': outcomes,
                       'shared_missing_information': shared_gaps[:8],
                       'possible_correlated_error': bool(bad) and agreement is not None and agreement >= 0.5, 'consensus_with_bad_outcome': bad})
    return {'method': __doc__.strip(), 'cycles': cycles,
            'summary': {'cycles': len(cycles), 'flagged': sum(1 for c in cycles if c['possible_correlated_error']),
                        'mean_agreement': round(sum(c['mean_pairwise_agreement'] for c in cycles if c['mean_pairwise_agreement'] is not None) /
                                                max(1, sum(1 for c in cycles if c['mean_pairwise_agreement'] is not None)), 3) if cycles else None}}

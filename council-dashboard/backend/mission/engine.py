"""Pure deterministic state transitions. Agents propose; this module executes."""
from copy import deepcopy
from .spec import specification, digest

class InvalidAction(ValueError):
    pass

def new_state():
    spec = specification()
    jobs = [dict(deepcopy(j), status='pending', progress=0, reason='', decision_id=None) for j in spec['jobs']]
    jobs[-1]['status'] = 'dormant'
    return {'spec': spec, 'tick': 0, 'sol': 0, 'status': 'active', 'mode': 'fixed-priority',
            'resources': {'energy_kwh': 600., 'materials_kg': 200., 'feedstock_kg': 0., 'regolith_kg': 0., 'water_kg': 0., 'spares': 3.},
            'power_kw': 4., 'spent_usd': 0., 'committed_usd': 0., 'budget_usd': 250000.,
            'jobs': jobs, 'assets': [dict(id=a, name=n, condition=1., available=True) for a, n in [('rover','Survey rover'), ('utility','Utility robot'), ('excavator','Excavation robot'), ('processor','Water processor'), ('builder','Assembly robot')]],
            'priority': ['survey','power','excavate','water','habitat','verify','maintenance'],
            'water_yield': .25, 'reservations': [], 'ledger': [], 'physical_ledger': [], 'decisions': [], 'activity': [],
            'milestones': {'survey': False, 'power': False, 'water': False, 'habitat': False, 'ready': False},
            'planning_needed': False, 'planning_status': 'Fixed-priority scheduler; no AI calls', 'faults': []}

def event(s, title, detail, job_id=None):
    s['activity'].append({'id': len(s['activity'])+1, 'tick': s['tick'], 'title': title, 'detail': detail, 'job_id': job_id})

def job_by_id(s, jid):
    job=next((j for j in s['jobs'] if j['id'] == jid),None)
    if job is None: raise InvalidAction('Unknown job')
    return job

def reasons(s, j):
    if j['status'] not in ('pending','blocked'): return ['Job is not pending']
    out = []
    for dependency in j['dependencies']:
        if job_by_id(s, dependency)['status'] != 'complete': out.append('Waiting for '+job_by_id(s,dependency)['title'].lower())
    a = next(a for a in s['assets'] if a['id'] == j['asset'])
    if not a['available'] or a['condition'] < .25: out.append('Assigned equipment is unavailable')
    if any(x['status']=='running' and x['asset']==j['asset'] for x in s['jobs']): out.append('Assigned equipment is busy')
    active = sum(x['power_kw'] for x in s['jobs'] if x['status']=='running')
    if active+j['power_kw'] > s['power_kw']+.00001: out.append('Waiting for power; active jobs have reserved the supply')
    for k,v in j['inputs'].items():
        if s['resources'].get(k,0) < v: out.append(f'Insufficient {k.replace("_", " ")}')
    if s['spent_usd']+s['committed_usd']+j['cost'] > s['budget_usd']: out.append('Operating spending limit would be exceeded')
    if j['id']=='verify' and s['resources']['water_kg'] < s['spec']['parameters']['water_target']['value']: out.append('Water reserve is below the 100 kg readiness target')
    return out

def decision(s, j, rationale, actor, source_ids):
    d = {'id': f'D{len(s["decisions"])+1}', 'tick': s['tick'], 'job_id': j['id'], 'actor': actor,
         'summary': rationale, 'source_ids': source_ids, 'source_versions': {key:s.get('source_pins',{}).get(key) for key in source_ids}, 'spec_hash': s['spec']['hash'],
         'input_snapshot': {'resources': deepcopy(s['resources']), 'power_kw': s['power_kw'], 'spent_usd': s['spent_usd'], 'committed_usd': s['committed_usd']},
         'calculation': {'required_inputs': j['inputs'], 'power_kw': j['power_kw'], 'cost_usd': j['cost'], 'duration_ticks': j['duration']},
         'validation': 'accepted', 'outcome': None}
    s['decisions'].append(d)
    return d['id']

def start(s, jid, rationale=None, actor='fixed-priority', source_ids=None):
    j=job_by_id(s,jid)
    errors=reasons(s,j)
    if errors: raise InvalidAction('; '.join(errors))
    if rationale is None:
        rationale=f"{j['title']} is next in the fixed-priority schedule. Prerequisites passed; reserving {j['power_kw']} kW and ${j['cost']:,} of scenario spending authority."
    source_ids=source_ids or ['scenario-v1']
    reverse_pins={v:k for k,v in s.get('source_pins',{}).items()}
    source_ids=[reverse_pins.get(key,key) for key in source_ids]
    if any(key not in ['scenario-v1','nasa-dra','nasa-m2m','swim','mola','rems'] for key in source_ids): raise InvalidAction('Unknown evidence reference')
    j['decision_id']=decision(s,j,rationale,actor,source_ids)
    for k,v in j['inputs'].items():
        s['resources'][k]-=v
        s['physical_ledger'].append({'tick':s['tick'],'job_id':jid,'resource':k,'amount':-v,'kind':'input consumed'})
    s['committed_usd']+=j['cost']
    s['reservations'].append({'job_id':jid,'decision_id':j['decision_id'],'inputs':deepcopy(j['inputs']),'cost_usd':j['cost'],'power_kw':j['power_kw'],'status':'reserved'})
    s['ledger'].append({'tick':s['tick'],'kind':'commitment','job_id':jid,'amount_usd':j['cost'],'currency_year':2026,'origin':'scenario assumption'})
    j.update(status='running',reason='',started_tick=s['tick'])
    event(s,j['title']+' started',rationale,jid)

def advance(state):
    s=deepcopy(state)
    if s['status']!='active': return s
    s['tick']+=1; s['sol']=round(s['tick']/24,4)
    before=s['resources']['energy_kwh']
    s['resources']['energy_kwh']=round(min(800.,before+s['power_kw']*88775.244/24/3600),6)
    s['physical_ledger'].append({'tick':s['tick'],'job_id':None,'resource':'energy_kwh','amount':s['resources']['energy_kwh']-before,'kind':'generation after curtailment'})
    for j in s['jobs']:
        if j['status']!='running': continue
        asset=next(a for a in s['assets'] if a['id']==j['asset'])
        active_power=sum(x['power_kw'] for x in s['jobs'] if x['status']=='running')
        if not asset['available'] or active_power > s['power_kw']+.00001:
            if not j['reason'].startswith('Execution held') and not s.get('inference_stopped'): s['planning_needed']=True
            j['reason']='Execution held: equipment or power constraint'
            continue
        j['reason']=''; j['progress']+=1
        if j['progress'] < j['duration']: continue
        for k,v in j['outputs'].items():
            s['resources'][k]+=v
            s['physical_ledger'].append({'tick':s['tick'],'job_id':j['id'],'resource':k,'amount':v,'kind':'output measured'})
        if j['id']=='power': s['power_kw']=18.
        if j['id']=='water':
            produced=j['inputs']['feedstock_kg']*s['water_yield']
            s['resources']['water_kg']+=produced
            s['physical_ledger'].append({'tick':s['tick'],'job_id':j['id'],'resource':'water_kg','amount':produced,'kind':'output measured','process_residue_kg':j['inputs']['feedstock_kg']-produced})
        if j['id']=='maintenance':
            for a in s['assets']:
                if a['id']=='excavator': a['available']=True; a['condition']=1.
        asset['condition']=max(.25,asset['condition']-.02)
        s['committed_usd']-=j['cost']; s['spent_usd']+=j['cost']
        for r in s['reservations']:
            if r['job_id']==j['id']: r['status']='consumed'
        s['ledger'].append({'tick':s['tick'],'kind':'expenditure','job_id':j['id'],'amount_usd':j['cost'],'currency_year':2026,'origin':'scenario assumption'})
        j['status']='complete'; j['completed_tick']=s['tick']
        if j['id'] in s['milestones']: s['milestones'][j['id']]=True
        if j['id']=='water': s['milestones']['water']=s['resources']['water_kg']>=100
        for d in s['decisions']:
            if d['id']==j['decision_id']: d['outcome']={'completed_tick':s['tick'],'resources':deepcopy(s['resources']),'spent_usd':s['spent_usd']}
        event(s,j['title']+' completed','Inputs and expenditure reconciled; result recorded.',j['id'])
        s['planning_needed']=s['mode']=='meta' and not s.get('inference_stopped')
    if job_by_id(s,'verify')['status']=='complete':
        s['milestones']['ready']=all(s['milestones'][k] for k in ('survey','power','water','habitat'))
        if s['milestones']['ready']: s['status']='complete'; event(s,'Outpost readiness verified','All four scenario requirements passed. This is simulation readiness, not engineering certification.')
    if s['status']=='active' and s['mode']=='fixed-priority':
        for jid in s['priority']:
            j=job_by_id(s,jid)
            if j['status'] not in ('pending','blocked'): continue
            errors=reasons(s,j)
            if not errors: start(s,jid)
            else:
                reason='; '.join(errors)
                if j['reason']!=reason and 'power' in reason and all(job_by_id(s,d)['status']=='complete' for d in j['dependencies']): event(s,j['title']+' waiting',reason,jid)
                j['status']='blocked';j['reason']=reason
    if s['mode']=='meta':
        for j in s['jobs']:
            if j['status'] in ('pending','blocked'): j['reason']='; '.join(reasons(s,j)) or 'Awaiting an agent work order'
    assert all(v>=-1e-6 for v in s['resources'].values())
    assert s['spent_usd']+s['committed_usd']<=s['budget_usd']+1e-6
    return s

def modify(state, changes):
    s=deepcopy(state)
    if set(changes)-{'priority','water_yield','budget_usd','fault'}: raise InvalidAction('Unsupported scenario change')
    if 'priority' in changes:
        if not isinstance(changes['priority'],list) or any(not isinstance(v,str) for v in changes['priority']): raise InvalidAction('Priority must be a list of job IDs')
        if sorted(changes['priority'])!=sorted(s['priority']): raise InvalidAction('Priority must contain every job exactly once')
        s['priority']=changes['priority']
    if 'water_yield' in changes:
        if job_by_id(s,'water')['status'] not in ('pending','blocked'): raise InvalidAction('Water processing has already started')
        v=changes['water_yield']
        if isinstance(v,bool) or not isinstance(v,(int,float)) or not .1<=v<=.5: raise InvalidAction('Water yield must be between 0.1 and 0.5')
        s['water_yield']=v
    if 'budget_usd' in changes:
        v=changes['budget_usd']
        if isinstance(v,bool) or not isinstance(v,(int,float)) or not s['spent_usd']+s['committed_usd']<=v<=1000000: raise InvalidAction('Budget cannot be below existing commitments or exceed $1M')
        s['budget_usd']=v
    if 'fault' in changes:
        fault=changes['fault']
        if fault=='power-loss': s['power_kw']=max(0,s['power_kw']/2)
        elif fault=='restore-power': s['power_kw']=18 if s['milestones']['power'] else 4
        elif fault=='equipment-failure':
            if job_by_id(s,'maintenance')['status']!='dormant': raise InvalidAction('This scenario has one maintenance work order; it is already activated')
            next(a for a in s['assets'] if a['id']=='excavator')['available']=False
            job_by_id(s,'maintenance')['status']='pending';s['priority'].remove('maintenance');s['priority'].insert(0,'maintenance')
        elif fault=='delayed-excavation':
            if job_by_id(s,'excavate')['status']=='complete': raise InvalidAction('Excavation already completed')
            job_by_id(s,'excavate')['duration']+=4
        else: raise InvalidAction('Unknown fault')
        s['faults'].append({'tick':s['tick'],'fault':fault})
        event(s,'Scenario changed',fault.replace('-',' '))
    s['planning_needed']=s['mode']=='meta'
    event(s,'Sandbox assumptions updated','Changes apply only to this mission; recorded as scenario assumptions.')
    return s

def state_hash(s): return digest(s)

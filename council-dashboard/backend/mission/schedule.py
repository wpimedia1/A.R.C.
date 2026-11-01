"""Inspectable forecasts from persisted work, with explicit architectural boundaries."""
from copy import deepcopy
from .spec import digest

SICSA_URL='https://sicsa.egr.uh.edu/sites/sicsa/files/files/publications/first-mars-outpost-compressed.pdf'
CONSTRAINTS=[
 {'id':'precursor-power-isru','title':'Power and resource production before crew arrival','source_url':SICSA_URL,'source_id':'sicsa-outpost','page':10,'printed_page':'17',
  'interpretation':'Uncrewed precursor logistics deploy power and ISRU before crew arrival.',
  'jobs':['water'],'enforcement':'Fission power is operational before work starts (D8); readiness requires the water target.'},
 {'id':'surface-power-reliability','title':'Reliable power and recoverable failures','source_url':'https://ntrs.nasa.gov/api/citations/20250010956/downloads/ADD%20Revision%20C%20-%2020260115.pdf','source_id':'nasa-m2m','page':251,'printed_page':'245','source_requirement':'Technology gap 0902',
  'interpretation':'Mars surface power needs reliable availability under hazardous environmental conditions.',
  'jobs':['trench','shielding','water'],'enforcement':'Work requires allocated grid power; a capacity loss stops running work until it is re-authorized.'},
 {'id':'modular-growth','title':'Build on completed infrastructure','source_url':SICSA_URL,'source_id':'sicsa-outpost','page':9,'printed_page':'14',
  'interpretation':'Stage infrastructure so later development can build on it; provide contingency and maintenance capability.',
  'jobs':['trench','shielding'],'enforcement':'Shielding depends on the completed trench; readiness requires both.'}]

def forecast(state,horizon=24*400):
    """Fixed-priority projection from the current state. Actual agent decisions may differ."""
    from .engine import advance
    s=deepcopy(state);s.update(mode='fixed-priority',status='active',planning_needed=False,failures_enabled=False)
    s.pop('planning_claim',None)
    for _ in range(horizon):
        if s['status']!='active':break
        s=advance(s)
    rows=[]
    for original in state['jobs']:
        projected=next(j for j in s['jobs'] if j['id']==original['id'])
        rows.append({'job_id':original['id'],'title':original['title'],'owner':original['owner'],'dependencies':original['dependencies'],
            'target':original['target'],'unit':original['unit'],'done':original['done'],
            'actual_start_tick':original.get('started_tick'),'actual_finish_tick':original.get('completed_tick'),
            'forecast_start_tick':projected.get('started_tick'),'forecast_finish_tick':projected.get('completed_tick'),
            'blocker':original.get('reason') or (projected.get('reason') if projected['status']!='complete' else None),
            'status':original['status'],'parameters':original['parameters'],'basis':original['basis'],
            'constraint_ids':[c['id'] for c in CONSTRAINTS if original['id'] in c['jobs']]})
    return {'version':'resource-schedule-2','input_state_hash':digest(state),'as_of_tick':state['tick'],'horizon_ticks':horizon,
        'method':'Deterministic fixed-priority projection using all compatible free equipment, without random failures (D14) or uplink delays. Actual Meta decisions and failures will differ.',
        'time_basis':f"24 ticks per sol; one tick = {state['spec']['tick_hours']:.4f} h (D7)",
        'forecast_readiness_tick':s.get('readiness_tick'),
        'jobs':rows,'constraints':[{**c,'source_version':state.get('source_pins',{}).get(c['source_id'])} for c in CONSTRAINTS],
        'conflicts':state['spec']['conflicts'],'decisions':state['spec']['decisions']}

def _with_spec(state, spec):
    """Current progress with targets and rates from an alternative specification."""
    s=deepcopy(state)
    by_id={j['id']:j for j in spec['jobs']};assets={a['id']:a for a in spec['assets']}
    for j in s['jobs']:
        alt=by_id[j['id']]
        for k in ('target','rate_per_asset_h','power_per_asset_kw'):
            if k in alt:j[k]=alt[k]
        if j['done']>j['target']:j['done']=j['target']
    for a in s['assets']:
        for k in ('rate_per_h','grid_power_kw'):a[k]=assets[a['id']][k]
    s['spec']=spec
    return s


def uncertainty(state,horizon=24*400):
    """Readiness forecast at both ends of every recorded parameter range, one parameter at a time."""
    from .package import load
    from .spec import specification
    pkg=load(state['spec']['package_id'])
    rows=[]
    for name,p in pkg['parameters'].items():
        rng=p.get('range')
        if not rng:continue
        out={'parameter':name,'nominal':pkg['values'][name],'minimum':rng['minimum'],'maximum':rng['maximum'],'note':rng.get('note')}
        for bound in ('minimum','maximum'):
            spec=specification(state['spec']['package_id'],{name:rng[bound]})
            out[bound+'_readiness_tick']=forecast(_with_spec(state,spec),horizon)['forecast_readiness_tick']
        rows.append(out)
    ticks=[t for r in rows for t in (r['minimum_readiness_tick'],r['maximum_readiness_tick']) if t is not None]
    return {'method':'One-at-a-time sensitivity over each recorded parameter range; fixed-priority continuation from current progress.',
            'parameters':rows,'readiness_tick_range':[min(ticks),max(ticks)] if ticks else None,
            'unbounded':[r['parameter'] for r in rows if r['minimum_readiness_tick'] is None or r['maximum_readiness_tick'] is None]}


def ingest_architecture(store):
    from .science import fetch,pin
    raw,retrieved=fetch(SICSA_URL)
    passages=[{'page':c['page'],'printed_page':c['printed_page'],'topic':c['id'],
               'text':c['interpretation'],'extraction':'Paraphrase verified against the scanned source page; not a verbatim transcript',
               'interpretation':c['enforcement'],'url':SICSA_URL+'#page='+str(c['page'])}
              for c in CONSTRAINTS if c['source_id']=='sicsa-outpost']
    return pin(store,'sicsa-outpost',{'title':'SICSA First Mars Outpost: Planning and Concepts','url':SICSA_URL,
        'version':'2002 conceptual study','retrieved_at':retrieved,'status':'scanned source visually verified',
        'passages':passages,'transformation_version':'sicsa-visual-interpretation-1',
        'supports':'Precursor sequencing and staged surface development; no verified robotic throughput',
        'design_context':{'crew_count':8,'surface_stay_max_days':500,'classification':'published conceptual design bound',
                          'pdf_page':6,'printed_page':8,'application':'Future crew context only; not applied to current robotic job capacities'}},raw)

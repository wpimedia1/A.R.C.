"""Unit-safe equipment envelopes. Ambient climate is never substituted for internal component telemetry."""
import math


def blockers(state, asset):
    reading=state.get('equipment_conditions',{}).get(asset['id'],{})
    out=[]
    if state.get('equipment_physics',{}).get(asset['id'],{}).get('housekeeping_unserved_wh',0)>1e-9:
        out.append('Onboard housekeeping energy was not supplied; recharge is required')
    profile=asset.get('operating_envelope',{})
    for variable,limit in profile.items():
        r=reading.get(variable)
        if r is None:continue
        if r['unit']!=limit['unit']:
            out.append(variable+' unit mismatch')
        elif not limit['minimum']<=r['value']<=limit['maximum']:
            out.append(f"{variable} {r['value']} {r['unit']} outside qualified {limit['minimum']}–{limit['maximum']} {limit['unit']}; source {limit['source']}")
    return out


def configure(state, observations):
    """Private experiment inputs are explicitly scenarios. Real sensor ingestion must use a separate signed source path."""
    from .engine import InvalidAction, asset_by_id
    if not isinstance(observations,dict):raise InvalidAction('Equipment conditions must map asset IDs to readings')
    staged={}
    for aid, readings in observations.items():
        asset=asset_by_id(state,aid)
        if not isinstance(readings,dict):raise InvalidAction('Readings must be an object')
        staged[aid]={}
        for name,r in readings.items():
            profile=asset.get('operating_envelope',{}).get(name)
            if not profile:raise InvalidAction('No published equipment envelope for '+aid+'/'+name)
            if r is None:staged[aid][name]=None;continue
            if not isinstance(r,dict) or set(r)!={'value','unit','basis'}:raise InvalidAction('Each reading needs value, unit and basis')
            value=r['value']
            if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or r['unit']!=profile['unit']:
                raise InvalidAction('Finite equipment reading with matching unit required')
            if not isinstance(r['basis'],str) or not r['basis'].strip():raise InvalidAction('State the scenario input basis')
            staged[aid][name]={**r,'classification':'scenario','configured_tick':state['tick']}
    for aid,readings in staged.items():state.setdefault('equipment_conditions',{}).setdefault(aid,{}).update(readings)

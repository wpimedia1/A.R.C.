"""Agent-authorized standing orders. Absent authorization means no policy execution.

Thresholds use the existing rated per-step demand; no new engineering quantities
or automatic fixed-priority substitution are introduced.
"""
from copy import deepcopy


def charging_policy(s, asset_ids, reason, actor, source_ids):
    from .engine import asset_by_id, InvalidAction, event
    if not isinstance(asset_ids,list) or not asset_ids or len(set(asset_ids))!=len(asset_ids):
        raise InvalidAction('Charging policy requires distinct equipment IDs')
    if not isinstance(reason,str) or not reason.strip():raise InvalidAction('Public policy rationale required')
    allowed=set(s.get('source_pins',{}))|set(s['spec']['sources'])|{s['spec']['package_id']}
    if not source_ids or any(k not in allowed for k in source_ids):raise InvalidAction('Policy citations must resolve to known sources')
    for aid in asset_ids:
        a=asset_by_id(s,aid)
        if not a.get('battery_wh') or a.get('generator_w') or not a.get('charge_kw'):
            raise InvalidAction('Standing grid charging is unsupported for '+aid)
    record={'id':'charging-policy-'+str(len(s.get('charging_policy_log',[]))+1),'assets':list(asset_ids),
            'actor':actor,'reason':reason,'source_ids':list(source_ids),
            'source_versions':{k:s.get('source_pins',{}).get(k) for k in source_ids},
            'tick':s['tick'],'rule':'Charge when stored energy cannot supply one source-rated work interval; respect all existing grid/equipment validators'}
    s.setdefault('charging_policy_log',[]).append(deepcopy(record))
    for aid in asset_ids:s.setdefault('charging_policies',{})[aid]=deepcopy(record)
    event(s,'Standing charging order authorized',reason+' · '+actor)
    return record


def execute(s):
    from .engine import asset_by_id, charge, step_energy_wh, InvalidAction, event
    from .procedures import locks
    if s['mode']!='meta':return
    for aid,policy in s.get('charging_policies',{}).items():
        a=asset_by_id(s,aid)
        if not a['available'] or a.get('charging') or aid in locks(s) or a['soc_wh']>=step_energy_wh(s,a)-1e-9:
            continue
        try:
            charge(s,[aid],'Standing order '+policy['id']+': '+policy['reason'],policy['actor'])
            policy.pop('last_blocker',None)
        except InvalidAction as exc:
            # A changed constraint requests reasoning; repeated identical blockers
            # do not manufacture repeated agent activity or inference requests.
            blocker=str(exc)
            if policy.get('last_blocker')!=blocker:
                policy['last_blocker']=blocker
                event(s,'Standing charging order blocked',aid+': '+blocker)
                s['planning_needed']=not s.get('inference_stopped')

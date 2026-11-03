"""Owner-scoped, read-only mission projections for the operational interface."""
from copy import deepcopy
from sqlalchemy import select
from .store import Revision, InferenceReceipt, SourceVersion
from .engine import modify, InvalidAction
from .spec import ROLES

def inspect(store,mid,owner=None):
    snap=store.snapshot(mid,owner);s=snap['state']
    with store.transaction() as db:
        receipts=[{'id':r.id,**r.record} for r in db.scalars(select(InferenceReceipt).where(InferenceReceipt.mission_id==mid)).all()]
        history=db.scalars(select(Revision).where(Revision.mission_id==mid).order_by(Revision.revision)).all()
        series={r.state['tick']:{'tick':r.state['tick'],**r.state['resources'],'energy_used_kwh':r.state['energy_used_kwh'],'spent_usd':r.state['spent_usd']} for r in history}
        evidence=[{'source_id':k,'version_id':v,**db.get(SourceVersion,v).record} for k,v in s['source_pins'].items()]
        for row in evidence:
            row.pop('raw_content_hex',None);row.pop('content',None)
            # The segmented site image is served by /api/v1/site/segmented.jpg, not inlined here.
            if isinstance(row.get('image_source'),dict) and row['image_source'].get('segmented_jpeg_b64'):
                row['image_source']={k:v for k,v in row['image_source'].items() if k!='segmented_jpeg_b64'};row['segmented_image']='/api/v1/site/segmented.jpg'
        comparison=None
        if snap['parent'] and history:
            baseline,skipped=replay_baseline(store,history,s['tick'])
            comparison={'elapsed_ticks':s['tick']-history[0].state['tick'],'baseline_label':'Fixed-priority benchmark through the same harness: fork snapshot, failure seed, frozen conditions and experiment changes',
                        'seed':baseline.get('reliability_seed'),'changes_not_applicable_to_baseline':skipped,'baseline':outcome(baseline),'experiment':outcome(s)}
    return {'revision':snap['revision'],'roles':ROLES,'receipts':receipts,'tool_results':s.get('last_agent_receipts',[]),
            'agent_cycle':s.get('agent_cycle'),'agent_memory':s.get('agent_memory',{}),'agent_protocol':s.get('agent_protocol'),
            'inference_usd':sum(r.get('actual_usd',0) for r in receipts),'provider_response_ids':[r['response_id'] for r in receipts if r.get('response_id')],'reserved_usd':sum(r.get('reserved_usd',0) for r in receipts if r.get('status')!='received'),
            'series':list(series.values()),'evidence':evidence,'comparison':comparison}

def outcome(x):
    return {'resources':x['resources'],'energy_used_kwh':x['energy_used_kwh'],'spent_usd':x['spent_usd'],'ready':x['milestones']['ready'],'readiness_tick':x['readiness_tick']}

def replay_baseline(store,history,until_tick,seed=None):
    """One harness for both planners (store.step): same fork snapshot, same failure seed (the fork's unless `seed` is
    given), same frozen conditions, same experiment changes at the same ticks, same benchmark logistics. Only the planner
    differs. Returns the baseline state at `until_tick` and the changes it could not apply."""
    baseline=deepcopy(history[0].state);baseline.update(mode='fixed-priority',planning_needed=False,status='active')
    baseline.pop('planning_claim',None)
    if seed is not None:baseline['reliability_seed']=seed
    changes={}
    for r in history[1:]:
        if r.operation.get('kind')=='configure':
            c={k:v for k,v in (r.operation.get('changes') or {}).items() if k!='planner'}
            if c:changes.setdefault(r.state['tick'],[]).append(c)
    skipped=[]
    for tick in range(history[0].state['tick'],until_tick):
        for c in changes.get(tick,[]):
            try:baseline=modify(baseline,c);baseline.update(mode='fixed-priority',planning_needed=False)
            except InvalidAction as exc:skipped.append({'tick':tick,'changes':c,'reason':str(exc)})
        baseline=store.step(baseline)
    return baseline,skipped

def robustness(store,mid,owner,seeds,ticks):
    """D14 robustness: the experiment's fork snapshot and changes replayed through the benchmark harness under `seeds`
    different failure seeds for `ticks` steps. Each run's outcome and failures are reported, plus the spread; no seed is
    favoured and no run is dropped."""
    if not 1<=seeds<=50:raise InvalidAction('seeds must be 1-50')
    if not 1<=ticks<=24*400:raise InvalidAction('ticks must be 1-9600')
    snap=store.snapshot(mid,owner)
    if not snap['parent']:raise InvalidAction('Robustness runs are for experiments; create an experiment first')
    with store.transaction() as db:
        history=db.scalars(select(Revision).where(Revision.mission_id==mid).order_by(Revision.revision)).all()
        runs=[]
        for i in range(seeds):
            seed=f'{mid}:seed-{i+1}'
            end,skipped=replay_baseline(store,history,history[0].state['tick']+ticks,seed)
            failures=sum(1 for f in end['faults'] if f['kind']=='failure' and f['tick']>=history[0].state['tick'])
            runs.append({'seed':seed,'failures':failures,'changes_not_applied':len(skipped),**outcome(end)})
    ready=sorted(r['readiness_tick'] for r in runs if r['ready'] and r['readiness_tick'] is not None)
    keys=sorted(runs[0]['resources'])
    spread={k:{'min':min(r['resources'][k] for r in runs),'max':max(r['resources'][k] for r in runs)} for k in keys}
    return {'mission':mid,'seeds':seeds,'ticks':ticks,'planner':'fixed-priority benchmark (no model calls)',
            'ready_runs':len(ready),'readiness_tick':{'min':ready[0],'median':ready[len(ready)//2],'max':ready[-1]} if ready else None,
            'failures':{'min':min(r['failures'] for r in runs),'max':max(r['failures'] for r in runs)},'resources':spread,'runs':runs}

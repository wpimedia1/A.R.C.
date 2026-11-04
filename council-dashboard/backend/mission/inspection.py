"""Owner-scoped, read-only mission projections for the operational interface."""
from copy import deepcopy
from sqlalchemy import select
from .store import Revision, InferenceReceipt, SourceVersion
from .engine import modify, InvalidAction
from .spec import ROLES


def records(store,mid,owner=None):
    """Read record metadata without constructing the complete mission export.

    Historical source pins and full request receipts remain available. Full world
    snapshots belong to the explicitly requested export, not every page load.
    """
    snap=store.snapshot(mid,owner)
    with store.transaction() as db:
        pins=set(snap['state']['source_pins'].values())
        for prior in db.scalars(select(Revision.state['source_pins']).where(Revision.mission_id==mid)):
            pins.update((prior or {}).values())
        versions={vid:db.get(SourceVersion,vid).record for vid in pins}
        sources={key:versions[vid] for key,vid in snap['state']['source_pins'].items()}
        receipts=[{'id':r.id,**r.record} for r in db.scalars(select(InferenceReceipt).where(InferenceReceipt.mission_id==mid))]
    return {'sources':sources,'source_versions':versions,'state':snap['state'],'inference_receipts':receipts}

def inspect(store,mid,owner=None):
    snap=store.snapshot(mid,owner);s=snap['state']
    with store.transaction() as db:
        # The live panel needs receipts, not repeated request contexts. Complete
        # requests remain inspectable in records/export. Do not deserialize every
        # historical world merely to draw a four-column resource chart.
        receipt_fields=('model','status','created_at','actual_usd','reserved_usd','response_id','key_fingerprint',
                        'http_status','response_headers','provider_error_message','usage','tool_calls')
        receipts=[{'id':r.id,**{k:r.record[k] for k in receipt_fields if k in r.record}} for r in db.scalars(select(InferenceReceipt).where(InferenceReceipt.mission_id==mid)).all()]
        cols=[Revision.state[k] for k in ('tick','resources','energy_used_kwh','spent_usd')]
        samples=db.execute(select(*cols).where(Revision.mission_id==mid).order_by(Revision.revision)).all()
        series={tick:{'tick':tick,**resources,'energy_used_kwh':energy,'spent_usd':spent} for tick,resources,energy,spent in samples}
        evidence=[{'source_id':k,'version_id':v,**db.get(SourceVersion,v).record} for k,v in s['source_pins'].items()]
        for row in evidence:
            row.pop('raw_content_hex',None);row.pop('content',None)
            row.pop('browse_png_hex',None)
            if row['source_id']=='swim' and row.get('image_url'):
                row['image_url']=f'/api/v1/missions/{mid}/evidence/swim.png'
            if row['source_id']=='hirise-ground':
                row['image_url']=f'/api/v1/missions/{mid}/evidence/ground.jpg'
            # The segmented site image is served by /api/v1/site/segmented.jpg, not inlined here.
            if isinstance(row.get('image_source'),dict) and row['image_source'].get('segmented_jpeg_b64'):
                row['image_source']={k:v for k,v in row['image_source'].items() if k!='segmented_jpeg_b64'};row['segmented_image']='/api/v1/site/segmented.jpg'
        comparison=None
        if snap['parent'] and samples:
            # Private bounded comparisons need their actual configuration history;
            # the public mission does not. Preserve the same baseline semantics.
            history=db.scalars(select(Revision).where(Revision.mission_id==mid).order_by(Revision.revision)).all()
            # One harness for both planners (store.step): same fork snapshot, same failure seed (the fork's), same frozen
            # conditions, same experiment changes at the same ticks, same benchmark logistics. Only the planner differs.
            baseline=deepcopy(history[0].state);baseline.update(mode='fixed-priority',planning_needed=False,status='active')
            baseline.pop('planning_claim',None)
            changes={}
            for r in history[1:]:
                if r.operation.get('kind')=='configure':
                    c={k:v for k,v in (r.operation.get('changes') or {}).items() if k!='planner'}
                    if c:changes.setdefault(r.state['tick'],[]).append((c,r.state.get('physics_evidence',{})))
            skipped=[]
            for tick in range(history[0].state['tick'],s['tick']):
                for c,physics_evidence in changes.get(tick,[]):
                    try:
                        baseline.setdefault('physics_evidence',{}).update(deepcopy(physics_evidence))
                        baseline=modify(baseline,c);baseline.update(mode='fixed-priority',planning_needed=False)
                    except InvalidAction as exc:skipped.append({'tick':tick,'changes':c,'reason':str(exc)})
                baseline=store.step(baseline)
            pick=lambda x:{'resources':x['resources'],'energy_used_kwh':x['energy_used_kwh'],'spent_usd':x['spent_usd'],'ready':x['milestones']['ready'],'readiness_tick':x['readiness_tick']}
            comparison={'elapsed_ticks':s['tick']-history[0].state['tick'],'baseline_label':'Fixed-priority benchmark through the same harness: fork snapshot, failure seed, frozen conditions and experiment changes',
                        'seed':baseline.get('reliability_seed'),'changes_not_applicable_to_baseline':skipped,'baseline':pick(baseline),'experiment':pick(s)}
    return {'revision':snap['revision'],'roles':ROLES,'receipts':receipts,'tool_results':s.get('last_agent_receipts',[]),
            'agent_cycle':s.get('agent_cycle'),'agent_memory':s.get('agent_memory',{}),'agent_protocol':s.get('agent_protocol'),
            'inference_usd':sum(r.get('actual_usd',0) for r in receipts),'provider_response_ids':[r['response_id'] for r in receipts if r.get('response_id')],'reserved_usd':sum(r.get('reserved_usd',0) for r in receipts if r.get('actual_usd') is None),
            'series':list(series.values()),'evidence':evidence,'comparison':comparison}

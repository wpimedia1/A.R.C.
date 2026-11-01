"""Owner-scoped, read-only mission projections for the operational interface."""
from copy import deepcopy
from sqlalchemy import select
from .store import Revision, InferenceReceipt, SourceVersion
from .engine import advance
from .spec import ROLES

def inspect(store,mid,owner=None):
    snap=store.snapshot(mid,owner);s=snap['state']
    with store.transaction() as db:
        receipts=[{'id':r.id,**r.record} for r in db.scalars(select(InferenceReceipt).where(InferenceReceipt.mission_id==mid)).all()]
        history=db.scalars(select(Revision).where(Revision.mission_id==mid).order_by(Revision.revision)).all()
        series={r.state['tick']:{'tick':r.state['tick'],**r.state['resources'],'energy_used_kwh':r.state['energy_used_kwh'],'spent_usd':r.state['spent_usd']} for r in history}
        evidence=[{'source_id':k,'version_id':v,**db.get(SourceVersion,v).record} for k,v in s['source_pins'].items()]
        for row in evidence:row.pop('raw_content_hex',None);row.pop('content',None)
        comparison=None
        if snap['parent']:
            parent=db.scalar(select(Revision).where(Revision.mission_id=='public',Revision.revision==snap['parent']['revision']))
            baseline=deepcopy(parent.state);baseline.update(mode='fixed-priority',planning_needed=False,status='active')
            baseline.pop('planning_claim',None)
            elapsed=s['tick']-parent.state['tick']
            for _ in range(max(0,elapsed)):baseline=advance(baseline)
            pick=lambda x:{'resources':x['resources'],'energy_used_kwh':x['energy_used_kwh'],'spent_usd':x['spent_usd'],'ready':x['milestones']['ready']}
            comparison={'elapsed_ticks':elapsed,'baseline_label':'Fixed-priority replay from the exact fork snapshot','baseline':pick(baseline),'experiment':pick(s)}
    return {'revision':snap['revision'],'roles':ROLES,'receipts':receipts,'tool_results':s.get('last_agent_receipts',[]),
            'agent_cycle':s.get('agent_cycle'),'agent_memory':s.get('agent_memory',{}),'agent_protocol':s.get('agent_protocol'),
            'inference_usd':sum(r.get('actual_usd',0) for r in receipts),'provider_response_ids':[r['response_id'] for r in receipts if r.get('response_id')],'reserved_usd':sum(r.get('reserved_usd',0) for r in receipts if r.get('status')!='received'),
            'series':list(series.values()),'evidence':evidence,'comparison':comparison}

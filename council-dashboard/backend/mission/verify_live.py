"""Explicit, bounded live acceptance run in a separate validation database."""
import json
import os
from pathlib import Path
from .store import Store
from .planner import plan_once
from .engine import advance
from .spec import digest

def main():
    if os.getenv('DATABASE_URL')!='sqlite:///live-validation.db':raise SystemExit('Use DATABASE_URL=sqlite:///live-validation.db; never run against the public deployment')
    store=Store();store.initialize()
    for _ in range(72):
        s=store.snapshot('public')['state']
        if s['status']=='complete' or s.get('inference_stopped'):break
        if s.get('planning_needed'):plan_once(store)
        with store.transaction() as db:
            m=store.row(db,'public')
            store.save(db,m,advance(m.state),{'kind':'tick'})
    e=store.export('public');s=e['state']
    result={'status':s['status'],'planning_status':s['planning_status'],'ticks':s['tick'],'water_kg':s['resources']['water_kg'],'spent_usd':s['spent_usd'],
            'actual_inference_usd':sum(r.get('actual_usd',0) for r in e['inference_receipts']),
            'unreconciled_reservations_usd':sum(r['reserved_usd'] for r in e['inference_receipts'] if 'actual_usd' not in r),
            'state_hash':digest(s),'decisions':s['decisions'],'inference_receipts':e['inference_receipts'],
            'note':'Includes integration-debug requests. This is a live acceptance run, not a controlled scheduler superiority comparison.'}
    target=Path(__file__).resolve().parents[3]/'docs'/'live-acceptance.json';target.parent.mkdir(exist_ok=True);target.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k not in ('decisions','inference_receipts')},indent=2))

if __name__=='__main__':main()

"""Authenticate existing response records with GET only. Never generates a model response.

Run from repository root with the selected local API container running:
  council-dashboard/backend/.venv/Scripts/python.exe tools/verify_stored_responses.py

The configured Meta key stays local. Private reasoning/output text is never written to the report.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
from urllib.parse import quote
import httpx

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'council-dashboard/backend'))
from mission.provider import credential,fingerprint


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--container',default='meta-hackathon-review-api')
    parser.add_argument('--database',type=Path,help='Read an isolated SQLite acceptance database instead of a container')
    parser.add_argument('--report',type=Path,default=ROOT/'docs/historical-response-check.json')
    args=parser.parse_args()
    script="""from mission.store import Store,InferenceReceipt
from sqlalchemy import select
import json
s=Store()
with s.transaction() as db:
 rows=[{'record_id':r.id,**{k:r.record.get(k) for k in ('model','status','response_id','usage','key_fingerprint','tool_calls')}} for r in db.scalars(select(InferenceReceipt)).all()]
 print(json.dumps(rows))
"""
    if args.database:
        import sqlite3
        with sqlite3.connect(args.database.resolve().as_uri()+'?mode=ro',uri=True) as db:
            records=[{'record_id':rid,**{k:record.get(k) for k in ('model','status','response_id','usage','key_fingerprint','tool_calls')}}
                     for rid,raw in db.execute('SELECT id,record FROM inference_receipts') for record in [json.loads(raw)]]
    else:
        records=json.loads(subprocess.check_output(['docker','exec',args.container,'python','-c',script],text=True))
    selected=[r for r in records if r['status']=='received' and isinstance(r.get('response_id'),str)]
    excluded=[{'record_id':r['record_id'],'model':r['model'],'status':r['status'],
               'reason':'No received response ID; cannot authenticate through response retrieval'} for r in records if r not in selected]
    key,source=credential()
    with httpx.Client(timeout=30) as client:
        def check(old):
            row={'record_id':old['record_id'],'stored_response_id':old['response_id'],'stored_model':old['model'],
                 'stored_key_matches_current':old['key_fingerprint']==fingerprint(key)}
            try:
                response=client.get('https://api.meta.ai/v1/responses/'+quote(old['response_id'],safe=''),headers={'Authorization':'Bearer '+key})
                row.update(http_status=response.status_code,request_id=response.headers.get('x-request-id'),
                           response_sha256=hashlib.sha256(response.content).hexdigest())
                try:data=response.json()
                except ValueError:data={}
                if response.status_code==200:
                    calls=[{'name':c['name'],'arguments':json.loads(c['arguments']),'call_id':c.get('call_id')}
                           for c in data.get('output',[]) if c.get('type')=='function_call']
                    row.update(provider_response_id=data.get('id'),provider_model=data.get('model'),provider_status=data.get('status'),
                               identity_matches=data.get('id')==old['response_id'],model_matches=data.get('model')==old['model'],
                               usage_matches=data.get('usage')==old['usage'],usage=data.get('usage'),
                               public_tool_calls_match=calls==old['tool_calls'] if old['tool_calls'] is not None else None)
                else:row['error']=str(data.get('error',{})).replace(key,'[redacted]')[:300]
            except Exception as exc:row['error']=(type(exc).__name__+': '+str(exc)).replace(key,'[redacted]')[:300]
            return row
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(check,selected))
    verified=[r for r in results if r.get('identity_matches') and r.get('model_matches') and r.get('usage_matches') and r.get('public_tool_calls_match') is not False]
    path=args.report
    previous=json.loads(path.read_text(encoding='utf-8')) if path.exists() else None
    prior=(previous.get('previous_checks',[])+[{k:v for k,v in previous.items() if k!='previous_checks'}]) if previous else []
    report={'checked_at':time.time(),'method':'Authenticated GET of existing Meta response IDs only; no inference request',
            'key_fingerprint':fingerprint(key),'credential_source':source,'stored_records':len(records),
            'attempted':len(selected),'verified':len(verified),'not_verified':len(selected)-len(verified),
            'results':results,'excluded_records':excluded,'previous_checks':prior,
            'scope':'Historical identity/model/usage/public-tool-output comparison, not current-code planning acceptance or physical validity. A failed retrieval alone cannot establish fabrication.'}
    path.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({k:report[k] for k in ('stored_records','attempted','verified','not_verified','excluded_records')}))
    return int(report['not_verified']>0)


if __name__=='__main__':sys.exit(main())

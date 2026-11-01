"""Real localhost, PostgreSQL, worker restart and Meta fork acceptance. No transport doubles."""
import json
import subprocess
import time
from pathlib import Path
import httpx

ROOT=Path(__file__).resolve().parents[1]
BASE='http://127.0.0.1:8020/api/v1/'

def main():
    client=httpx.Client(base_url=BASE,timeout=30,headers={'Origin':'http://127.0.0.1:8020'})
    def get(path):
        r=client.get(path);r.raise_for_status();return r.json()
    def post(path,body):
        r=client.post(path,json=body);r.raise_for_status();return r.json()
    public=get('missions/public')
    fork=post('forks',{'revision':public['revision']});mid=fork['id']
    def control(action,**kwargs):
        current=get('missions/'+mid)
        return post('missions/'+mid+'/control',{'revision':current['revision'],'action':action,**kwargs})
    def wait_paused(timeout=600):
        deadline=time.monotonic()+timeout;last=None
        while time.monotonic()<deadline:
            s=get('missions/'+mid)
            state=s['state'];signal=(state['tick'],state.get('planning_status'))
            if signal!=last:print(json.dumps({'mission':mid,'tick':state['tick'],'status':state['planning_status']}),flush=True);last=signal
            if state.get('inference_stopped'):raise RuntimeError(state['planning_status'])
            if s['queued_ticks']==0 and not state.get('planning_claim'):return s
            time.sleep(2)
        raise TimeoutError('Live fork did not finish its bounded run')
    control('run',ticks=3)
    before=wait_paused()
    if before['state']['status']!='paused':raise RuntimeError('Restart check requires a paused fork')
    subprocess.run(['docker','compose','restart','api','worker'],cwd=ROOT,check=True,capture_output=True)
    for _ in range(30):
        try:
            after=get('missions/'+mid);break
        except httpx.HTTPError:time.sleep(1)
    else:raise RuntimeError('API did not recover')
    if before!=after:raise RuntimeError('Paused mission changed across service restart')
    unauthorized=httpx.get(BASE+'missions/'+mid,timeout=15).status_code
    if unauthorized!=403:raise RuntimeError('Fork ownership not enforced')
    control('run',ticks=24)
    final=wait_paused()
    operations=get('missions/'+mid+'/operations')
    if not operations['receipts']:raise RuntimeError('No actual Meta receipts recorded')
    if any(not r.get('response_id') for r in operations['receipts'] if r['status']=='received'):raise RuntimeError('Received receipt without provider response_id')
    if not any(j['done']>0 for j in final['state']['jobs']):raise RuntimeError('No work progressed in the live fork')
    later=get('missions/public')
    physical_keys=('resources','spent_usd','energy_used_kwh','jobs')
    isolated=all(public['state'][k]==later['state'][k] for k in physical_keys)
    if not isolated:raise RuntimeError('Public physical state changed during fork test; investigate before claiming isolation')
    report={'checked_at':time.time(),'mission_id':mid,'public_start_revision':public['revision'],
        'restart_preserved_snapshot':before==after,'unauthorized_read_status':unauthorized,'public_physical_state_unchanged':isolated,
        'ready':final['state']['milestones']['ready'],'final_tick':final['state']['tick'],
        'resources':final['state']['resources'],'jobs':{j['id']:[j['status'],j['done'],j['target']] for j in final['state']['jobs']},
        'provider_response_ids':operations['provider_response_ids'],
        'actual_provider_requests':len(operations['receipts']),'provider_receipts':operations['receipts'],
        'source_pins_preserved':fork['state']['source_pins']==final['state']['source_pins'],'queued_ticks':final['queued_ticks']}
    (ROOT/'docs/live-stack-acceptance.json').write_text(json.dumps(report,indent=2))
    print(json.dumps({k:v for k,v in report.items() if k!='provider_receipts'}),flush=True)

if __name__=='__main__':main()

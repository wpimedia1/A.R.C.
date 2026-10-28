"""Local end-to-end recovery check; never points at a hosted deployment."""
import json
import time
import subprocess
from pathlib import Path
import httpx
from .spec import digest

def main():
    root=Path(__file__).resolve().parents[3]
    base='http://127.0.0.1:8020/api/v1/'
    with httpx.Client(timeout=10) as client:
        before=client.get(base+'missions/public').json()
        subprocess.run(['docker','compose','up','-d','api','worker'],cwd=root,check=True)
        deadline=time.time()+45
        while True:
            try:
                r=client.get(base+'missions/public');r.raise_for_status();after=r.json();break
            except httpx.HTTPError:
                if time.time()>deadline:raise
                time.sleep(1)
        assert before==after,'Public revision changed during service replacement'
        response=client.post(base+'forks',json={'revision':after['revision']});response.raise_for_status();fork=response.json();mid=fork['id']
        response=client.post(base+f'missions/{mid}/control',json={'revision':fork['revision'],'action':'run','ticks':24});response.raise_for_status()
        time.sleep(5)
        during=client.get(base+f'missions/{mid}').json()
        subprocess.run(['docker','compose','restart','api','worker'],cwd=root,check=True)
        deadline=time.time()+50
        while True:
            try:
                response=client.get(base+f'missions/{mid}');response.raise_for_status();final=response.json()
                if final['state']['status']=='complete':break
            except httpx.HTTPError:pass
            if time.time()>deadline:raise AssertionError('Experiment did not recover and finish')
            time.sleep(1)
        s=final['state'];assert s['resources']['water_kg']==125 and s['spent_usd']==65000 and s['committed_usd']==0
        assert len(s['decisions'])==6 and len({d['id'] for d in s['decisions']})==6
        current=client.get(base+'missions/public').json();assert current==before,'Private run changed public mission'
        result={'public_revision_preserved':current['revision'],'public_hash':digest(current['state']),'experiment_id':mid,
                'tick_at_worker_restart':during['state']['tick'],'final_tick':s['tick'],'water_kg':s['resources']['water_kg'],
                'spent_usd':s['spent_usd'],'unique_decisions':len(s['decisions']),'restart_recovered':True,'public_unchanged':True}
        (root/'docs'/'stack-verification.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result,indent=2))

if __name__=='__main__':main()

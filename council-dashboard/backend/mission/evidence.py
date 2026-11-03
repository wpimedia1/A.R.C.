"""Version source catalog responses without treating catalog dates as observations."""
import hashlib
import time
from html.parser import HTMLParser
import httpx
from sqlalchemy import select
from .store import SourceVersion
from .spec import SOURCES

class Text(HTMLParser):
    def __init__(self): super().__init__(); self.parts=[]; self.hidden=0
    def handle_starttag(self,tag,attrs):
        if tag in ('script','style'): self.hidden+=1
    def handle_endtag(self,tag):
        if tag in ('script','style'): self.hidden=max(0,self.hidden-1)
    def handle_data(self,data):
        if not self.hidden and data.strip(): self.parts.append(data.strip())

def refresh(store, transport=None):
    results=[]
    for source in SOURCES:
        try:
            with httpx.Client(timeout=25,follow_redirects=True,transport=transport) as client:
                with client.stream('GET',source['url'],headers={'User-Agent':'MarsMissionEvidence/1.0'}) as response:
                    response.raise_for_status(); chunks=[]; size=0
                    for chunk in response.iter_bytes():
                        size+=len(chunk)
                        if size>2_000_000: raise ValueError('Catalog response exceeds 2 MB limit')
                        chunks.append(chunk)
                    raw=b''.join(chunks)
            parser=Text(); parser.feed(raw.decode('utf-8',errors='replace'))
            content='\n'.join(parser.parts)
            if len(content)<100: raise ValueError('No substantive catalog text')
            sha=hashlib.sha256(raw).hexdigest(); vid=source['id']+':'+sha[:16]
            record={**source,'retrieved_at':time.time(),'observation_time':None,'observation_location':None,
                    'status':'retrieved catalog; not a current site measurement','content':content,'content_hash':sha,
                    'hash_scope':'raw HTTP response bytes','transformation_version':'html-text-1','raw_content_hex':raw.hex(),
                    'passage':source.get('passage') if source.get('passage') and source['passage'] in content else None}
            with store.transaction() as db:
                if not db.get(SourceVersion,vid): db.add(SourceVersion(id=vid,source_id=source['id'],record=record))
            results.append({'source':source['id'],'status':'retrieved','version_id':vid})
        except Exception as exc:
            # Existing source versions and mission pins remain immutable.
            results.append({'source':source['id'],'status':'stale / fetch failed','error':type(exc).__name__})
    return results

def adopt_latest(store, mid='public'):
    """Explicit evidence adoption; forks keep their original source versions."""
    with store.transaction() as db:
        latest_pins={}
        for source in SOURCES:
            versions=db.scalars(select(SourceVersion).where(SourceVersion.source_id==source['id'])).all()
            valid=[v for v in versions if v.record.get('retrieved_at')]
            if not valid: continue
            scientific=[v for v in valid if v.record.get('passages') or v.record.get('observations') or v.record.get('image_url')]
            if scientific:valid=scientific
            latest_pins[source['id']]=max(valid,key=lambda v:v.record['retrieved_at']).id
        current=store.row(db,mid).state['source_pins']
        changed=[k for k,v in latest_pins.items() if current.get(k)!=v]
    if changed:
        def adopt(state):
            state['source_pins'].update({k:latest_pins[k] for k in changed})
            # A planning stop needs the owner (mission.cli replan); new evidence never restarts it.
            state['planning_needed']=state['mode']=='meta' and not state.get('inference_stopped')
        # Applied only between planning cycles: a plan in progress is never overwritten.
        store.commit_unclaimed(mid,adopt,{'kind':'adopt-evidence','sources':changed,'note':'Catalog context only; no physical parameter changed'})
    return changed

def attach_stored(store, mid='public'):
    """Pin the newest already-downloaded version of every retrieved source (regional MOLA and SWIM products, REMS,
    NASA documents) to a mission that lacks it, e.g. a new mission after Start. No download happens here. The site
    image is excluded: it belongs to the mission's own SAM analysis (D13)."""
    with store.transaction() as db:
        rows=[(v.id,v.source_id,v.record) for v in db.scalars(select(SourceVersion)).all()]
        state=store.row(db,mid).state
    newest={}
    for vid,source_id,record in rows:
        if not record.get('retrieved_at') or source_id in ('hirise-site',state['spec']['package_id']):continue
        scientific=bool(record.get('passages') or record.get('observations') or record.get('image_url') or record.get('spatial') or record.get('heights_m'))
        key=(scientific,record['retrieved_at'])
        if source_id not in newest or key>newest[source_id][0]:newest[source_id]=(key,vid)
    changed={k:vid for k,(_,vid) in newest.items() if state['source_pins'].get(k)!=vid}
    if changed:
        def attach(s):
            s['source_pins'].update(changed)
            s['planning_needed']=s['mode']=='meta' and not s.get('inference_stopped')
        store.commit_unclaimed(mid,attach,{'kind':'attach-stored-evidence','sources':sorted(changed),'note':'Already-downloaded versions; nothing fetched'})
    return sorted(changed)

if __name__=='__main__':
    import json
    from .store import Store
    s=Store();s.initialize(); print(json.dumps(refresh(s),indent=2)); print('Adopted:',adopt_latest(s))

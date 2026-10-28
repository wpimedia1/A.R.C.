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
    from copy import deepcopy
    with store.transaction() as db:
        m=store.row(db,mid); state=deepcopy(m.state); changed=[]
        for source in SOURCES:
            versions=db.scalars(select(SourceVersion).where(SourceVersion.source_id==source['id'])).all()
            valid=[v for v in versions if v.record.get('retrieved_at')]
            if not valid: continue
            latest=max(valid,key=lambda v:v.record['retrieved_at'])
            if state['source_pins'][source['id']]!=latest.id:
                state['source_pins'][source['id']]=latest.id; changed.append(source['id'])
        if changed:
            state['planning_needed']=state['mode']=='meta'
            store.save(db,m,state,{'kind':'adopt-evidence','sources':changed,'note':'Catalog context only; no physical parameter changed'})
    return changed

if __name__=='__main__':
    import json
    from .store import Store
    s=Store();s.initialize(); print(json.dumps(refresh(s),indent=2)); print('Adopted:',adopt_latest(s))

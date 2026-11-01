"""Bounded scientific source ingestion. Raw downloads stay outside Git."""
import hashlib
import io
import json
import time
import re
import math
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
import httpx
from .store import Store,SourceVersion

ROOT=Path(__file__).resolve().parents[1]
CACHE=ROOT/'data'/'science'
NS={'p':'http://pds.nasa.gov/pds4/pds/v1'}
REMS='https://atmos.nmsu.edu/PDS/data/PDS4/msl_rems_bundle/data_calibrated/SOL_04710_04843/SOL04710/RME_815573925RMD47100000000_______P1'
DOCS={'nasa-dra':'https://ntrs.nasa.gov/api/citations/20090012109/downloads/20090012109.pdf',
      'nasa-m2m':'https://ntrs.nasa.gov/api/citations/20250010956/downloads/ADD%20Revision%20C%20-%2020260115.pdf'}

def fetch(url,limit=40_000_000):
    CACHE.mkdir(parents=True,exist_ok=True)
    path=CACHE/hashlib.sha256(url.encode()).hexdigest()
    meta_path=path.with_suffix('.json')
    meta=json.loads(meta_path.read_text()) if meta_path.exists() else {}
    if path.exists() and time.time()-meta.get('checked_at',path.stat().st_mtime)<86400:
        return path.read_bytes(),path.stat().st_mtime
    headers={}
    if path.exists():
        if meta.get('etag'):headers['If-None-Match']=meta['etag']
        if meta.get('last_modified'):headers['If-Modified-Since']=meta['last_modified']
    with httpx.stream('GET',url,headers=headers,timeout=90,follow_redirects=True) as r:
        if r.status_code==304 and path.exists():
            meta['checked_at']=time.time();meta_path.write_text(json.dumps(meta))
            return path.read_bytes(),path.stat().st_mtime
        r.raise_for_status();parts=[];size=0
        for part in r.iter_bytes():
            size+=len(part)
            if size>limit:raise ValueError('Source exceeds bounded download size')
            parts.append(part)
        meta={'checked_at':time.time(),'etag':r.headers.get('etag'),'last_modified':r.headers.get('last-modified')}
    raw=b''.join(parts)
    if not path.exists() or path.read_bytes()!=raw:path.write_bytes(raw)
    meta_path.write_text(json.dumps(meta));return raw,path.stat().st_mtime

def pin(store,key,record,raw):
    sha=hashlib.sha256(raw).hexdigest()
    # A corrected transformation is a new version even when upstream bytes match.
    identity=sha+':'+record.get('transformation_version','original')
    vid=key+':'+hashlib.sha256(identity.encode()).hexdigest()[:16]
    record.update(content_hash=sha,hash_scope='raw source bytes',source_id=key)
    with store.transaction() as db:
        if not db.get(SourceVersion,vid):db.add(SourceVersion(id=vid,source_id=key,record=record))
    return vid

def parse_rems(label,raw):
    root=ET.fromstring(label);fields={}
    for f in root.findall('.//p:Field_Character',NS):
        name=f.findtext('p:name',namespaces=NS);start=int(f.findtext('p:field_location',namespaces=NS))-1
        fields[name]=(start,int(f.findtext('p:field_length',namespaces=NS)))
    def value(row,name):
        start,length=fields[name];return row[start:start+length].decode('ascii').strip().strip('"')
    points=[]
    for index,row in enumerate(raw.splitlines()):
        if index%300:continue
        p=float(value(row,'PRESSURE'));unc=float(value(row,'PRESSURE_UNCERTAINTY'));flag=value(row,'PS_CONFIDENCE_LEVEL')
        if p<=0 or unc<0:continue
        points.append({'row':index+1,'lmst':value(row,'LMST'),'pressure_pa':p,'uncertainty_pa':unc,
                       'quality_flag':flag,'quality':'no shadow effect' if len(flag)>1 and flag[1]=='1' else 'shadow effect or unknown'})
    return {'observations':points,'observation_time':root.findtext('.//p:start_date_time',namespaces=NS),
            'coverage_end':root.findtext('.//p:stop_date_time',namespaces=NS),
            'product_id':root.findtext('.//p:logical_identifier',namespaces=NS),
            'quality_definition':'PS byte 0 selects oscillator; byte 1: 1=no shadow effect, 0=shadow effect. Unknown flags retained.',
            'transformation_version':'pds4-fixed-fields-every-300th-row-1','units':'Pa','observation_location':'Curiosity, Gale crater; exact rover coordinates not extracted',
            'use':'Off-site context only; no Arcadia weather transfer applied'}

def latest_rems():
    base='https://atmos.nmsu.edu/PDS/data/PDS4/msl_rems_bundle/data_calibrated/'
    raw,_=fetch(base,2_000_000)
    ranges=sorted(re.findall(r'href="(SOL_\d+_\d+/)"',raw.decode()))
    if not ranges:raise ValueError('No published REMS range found')
    base+=ranges[-1];raw,_=fetch(base,2_000_000)
    sols=sorted(re.findall(r'href="(SOL\d+/)"',raw.decode()))
    if not sols:raise ValueError('No published REMS sol found')
    base+=sols[-1];raw,_=fetch(base,2_000_000)
    products=sorted(re.findall(r'href="([A-Z0-9_]*RMD[A-Z0-9_]*\.xml)"',raw.decode()))
    if not products:raise ValueError('Latest published sol has no calibrated RMD product; retaining old version')
    return base+products[-1][:-4],sols[-1].strip('/')

def parse_swim(raw,member_name='Ci.tif'):
    import tifffile
    import numpy as np
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        member=archive.getinfo(member_name)
        if member.file_size>20_000_000:raise ValueError('SWIM decompressed product exceeds bound')
        raster=archive.read(member)
    with tifffile.TiffFile(io.BytesIO(raster)) as tif:
        meta=tif.geotiff_metadata;grid=tif.asarray()
        scale=meta['ModelPixelScale'];tie=meta['ModelTiepoint'];radius=meta['GeogSemiMajorAxisGeoKey']
        x=radius*math.radians(-170);y=radius*math.radians(40)
        col=int((x-tie[3])/scale[0]);row=int((tie[4]-y)/scale[1])
        if not (0<=row<grid.shape[0] and 0<=col<grid.shape[1]):raise ValueError('Scenario site outside SWIM raster')
        cells=[]
        for r in range(max(0,row-12),min(grid.shape[0],row+13)):
            for c in range(max(0,col-12),min(grid.shape[1],col+13)):
                v=float(grid[r,c])
                cells.append({'row':r,'column':c,'value':v if np.isfinite(v) and -1<=v<=1 else None})
        from .region import sample_swim_region
        return {'region':sample_swim_region(grid,meta),'grid':cells,'site_row':row,'site_column':col,'site_value':next(c['value'] for c in cells if c['row']==row and c['column']==col),
                'pixel_size_m':scale[:2],'projection':'Mars 2000 spherical Plate Carree, central meridian 0°, meters',
                'raster_shape':list(grid.shape),'raster_hash':hashlib.sha256(raster).hexdigest(),
                'transform':'swim-geotiff-arcadia-2','site':{'latitude':40,'longitude':-170,'classification':'scenario assumption'},
                'interpretation':'Consistency index [-1,1], not ice fraction or recoverable yield. 3 km projected pixels; effective instrument resolution varies. No rover-scale inference.'}

def ingest(store):
    results={}
    from .telemetry import ingest_weather
    results['msl-weather']=ingest_weather(store)
    from .schedule import ingest_architecture
    results['sicsa-outpost']=ingest_architecture(store)
    for key,url in DOCS.items():
        from pypdf import PdfReader
        raw,retrieved=fetch(url);reader=PdfReader(io.BytesIO(raw));passages=[]
        terms=('pre-deploy','predeploy','surface power','in-situ resource','autonom','logistics','maintenance')
        for n,page in enumerate(reader.pages):
            text=' '.join((page.extract_text() or '').split())
            for term in terms:
                pos=text.lower().find(term)
                if pos>=0:
                    passages.append({'page':n+1,'topic':term,'text':text[max(0,pos-180):pos+650],
                                     'url':url+'#page='+str(n+1),'interpretation':'Architectural context; does not establish our scenario equipment capacities or prices.'});break
        results[key]=pin(store,key,{'title':'NASA DRA 5.0' if key=='nasa-dra' else 'NASA Moon to Mars Architecture Revision C',
            'url':url,'version':'2009' if key=='nasa-dra' else 'Revision C, 2026-01-15 file','retrieved_at':retrieved,
            'status':'document extracted','supports':'Robotic predeployment, surface operations and architectural tradeoffs',
            'passages':passages,'transformation_version':'pypdf-page-extract-1','page_count':len(reader.pages)},raw)
    rems,sol=latest_rems()
    label,_=fetch(rems+'.xml');raw,retrieved=fetch(rems+'.TAB',15_000_000)
    record=parse_rems(label,raw);record.update(title='REMS calibrated pressure · '+sol,url=rems+'.TAB',label_url=rems+'.xml',label_hash=hashlib.sha256(label).hexdigest(),
        version='PDS4 product 1.0',retrieved_at=retrieved,status='archived observations',supports='Measured off-site atmospheric context; not live Arcadia weather')
    results['rems']=pin(store,'rems',record,raw)
    url='https://swim.psi.edu/output/PilotStudy/Arcadia/Composite/Ci_Browse.png';raw,retrieved=fetch(url,15_000_000)
    # The browse product preserves its published legend; no invented per-pixel ice yields.
    frontend=ROOT.parent/'frontend'
    target=frontend/('out' if (frontend/'out').exists() else 'public')/'evidence'/'swim-arcadia.png'
    target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
    product_url='https://swim.psi.edu/PilotStudyProducts.php?C_i-GeoTIFF=True&DL-Sel=True'
    numeric,numeric_retrieved=fetch(product_url,5_000_000);spatial=parse_swim(numeric)
    results['swim']=pin(store,'swim',{'title':'SWIM Arcadia combined ice consistency · pilot study','url':product_url,'version':'2018 pilot / updated 2019-01-08',
        'retrieved_at':retrieved,'status':'published regional browse product','supports':'Regional consistency with ice over combined sensing depth ~5 m; preliminary, not extraction yield',
        'image_url':'/evidence/swim-arcadia.png','resolution':'3,000 m projected raster spacing, read from GeoTIFF. Effective sensing resolution varies by instrument. Not used for rover routes.',
        'spatial':spatial,'browse_hash':hashlib.sha256(raw).hexdigest(),'numeric_retrieved_at':numeric_retrieved,
        'uncertainty':'Preliminary multi-instrument consistency index, not an ice concentration measurement','transformation_version':'swim-geotiff-arcadia-2'},numeric)
    radar_url='https://swim.psi.edu/PilotStudyProducts.php?C_rdr-GeoTIFF=True&DL-Sel=True'
    radar,retrieved=fetch(radar_url,5_000_000)
    with zipfile.ZipFile(io.BytesIO(radar)) as archive:
        member=next(n for n in archive.namelist() if n.lower().endswith('.tif'))
    radar_spatial=parse_swim(radar,member)
    radar_spatial['interpretation']='Mapped SHARAD subsurface reflectors: 1 mapped reflector; 0 absent or excluded clutter/lava; null outside valid coverage. Not ice thickness or recoverable yield.'
    results['swim-radar']=pin(store,'swim-radar',{'title':'SWIM Arcadia deep radar reflectors','url':radar_url,
        'version':'2018 pilot / 2019-01-08','retrieved_at':retrieved,'status':'published radar interpretation',
        'supports':'Spatially mapped SHARAD subsurface reflector evidence','spatial':radar_spatial,
        'transformation_version':'swim-geotiff-arcadia-2','use':radar_spatial['interpretation']},radar)
    from .terrain import arcadia
    results['mola-arcadia']=arcadia(store)
    # Adopt only these explicit versions; retain earlier catalog and mission revisions.
    from copy import deepcopy
    with store.transaction() as db:
        m=store.row(db,'public')
        if m.state.get('planning_claim'):raise RuntimeError('Scientific products downloaded; adoption deferred until planning finishes')
        s=deepcopy(m.state)
        if any(s['source_pins'].get(k)!=v for k,v in results.items()):
            s['source_pins'].update(results)
            from .region import local_sensors
            s['local_sensors']=local_sensors()
            s['planning_needed']=s['mode']=='meta' and not s.get('inference_stopped')
            store.save(db,m,s,{'kind':'adopt-scientific-products','versions':results})
    return results

if __name__=='__main__':
    store=Store();store.initialize();print(json.dumps(ingest(store),indent=2))

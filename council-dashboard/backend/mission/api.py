"""Versioned mission API. Public reads; cookie-owned, isolated experiments."""
import asyncio
import hashlib
import json
import os
import secrets
import time
from pathlib import Path
from fastapi import FastAPI, Request, Response, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ConfigDict
from .store import Store
from .engine import InvalidAction

def deepcopy_or_none(value):
    import copy
    return copy.deepcopy(value) if value is not None else None

def operator_token():
    """The operator's start token: the process environment (Docker), else backend/.env (local launcher)."""
    token=(os.getenv('MISSION_OPERATOR_TOKEN') or '').strip()
    if token:return token
    from .provider import ENV_FILE
    if ENV_FILE.exists():
        from dotenv import dotenv_values
        return (dotenv_values(ENV_FILE).get('MISSION_OPERATOR_TOKEN') or '').strip()
    return ''

def create_app(store=None):
    store=store or Store()
    from .package import PackageError
    try:
        store.check();init_error=None  # never creates the mission: genesis waits for a user to press Start
    except (PackageError,InvalidAction) as exc:
        # Fail loud: the service starts so the reason is visible, every mission endpoint returns 503.
        init_error=str(exc)
    app=FastAPI(title='Mars Mission',version='2.0')
    app.state.store=store
    app.state.init_error=init_error

    def owner(request):
        token=request.cookies.get('mars_session','')
        return hashlib.sha256(token.encode()).hexdigest() if token else None

    @app.middleware('http')
    async def boundaries(request, call_next):
        if request.method not in ('GET','HEAD','OPTIONS'):
            if os.getenv('ACCEPTANCE_READ_ONLY')=='1':return Response('This isolated acceptance view is read-only; use the review app for experiments',403)
            origin=request.headers.get('origin')
            # Same-origin means the page was served by this host (localhost or 127.0.0.1), or the configured public origin.
            allowed={str(request.base_url).rstrip('/')}|({os.getenv('PUBLIC_ORIGIN').rstrip('/')} if os.getenv('PUBLIC_ORIGIN') else set())
            if origin and origin not in allowed: return Response('Cross-origin writes are not allowed',403)
            if request.headers.get('sec-fetch-site')=='cross-site': return Response('Cross-site writes are not allowed',403)
        if app.state.init_error and request.url.path.startswith('/api/v1/missions') or app.state.init_error and request.url.path.startswith('/api/v1/forks'):
            return Response('Mission not initialized: '+app.state.init_error,503)
        response=await call_next(request)
        response.headers['X-Content-Type-Options']='nosniff'
        response.headers['Referrer-Policy']='same-origin'
        if request.url.path.startswith('/api/'): response.headers['Cache-Control']='no-store'
        return response

    @app.exception_handler(InvalidAction)
    async def invalid(request, exc): return Response(str(exc),409)
    @app.exception_handler(PermissionError)
    async def denied(request, exc): return Response(str(exc),403)
    @app.exception_handler(KeyError)
    async def missing(request, exc): return Response('Mission or record not found',404)

    @app.get('/api/v1/health')
    def health():
        if app.state.init_error:
            return Response(json.dumps({'status':'not initialized','error':app.state.init_error}),503,media_type='application/json')
        heartbeat=store.status('worker')
        if not store.started():
            return {'status':'ok','started':False,'worker':heartbeat,'worker_stale':not heartbeat or time.time()-heartbeat['heartbeat_at']>600,
                    'operator_token_configured':bool(operator_token())}
        s=store.snapshot('public')['state']
        return {'status':'ok','started':True,'planner':s['mode'],'model_calls_enabled':s['mode']=='meta','planning_status':s['planning_status'],
                'worker':heartbeat,'worker_stale':not heartbeat or time.time()-heartbeat['heartbeat_at']>600,'sources':store.status('source-refresh')}

    @app.get('/api/v1/missions/{mid}')
    def mission(mid:str,request:Request): return store.snapshot(mid,owner(request))

    @app.get('/api/v1/missions/{mid}/records')
    def compact_records(mid:str,request:Request):
        from .inspection import records
        result=records(store,mid,owner(request))
        sources={key:{k:v for k,v in source.items() if k not in ('raw_content_hex','content')} for key,source in result['sources'].items()}
        for source in sources.values():
            source['age_seconds']=time.time()-source['retrieved_at'] if source.get('retrieved_at') else None
            if source['age_seconds'] and source['age_seconds']>172800:source['status']='stale catalog snapshot; last valid evidence retained'
        versions={vid:{k:v for k,v in record.items() if k not in ('raw_content_hex','content')} for vid,record in result['source_versions'].items()}
        return {'sources':sources,'source_versions':versions,'decisions':result['state']['decisions'],'inference_receipts':result['inference_receipts'],'source_checks':store.status('source-refresh')}

    @app.get('/api/v1/missions/{mid}/log')
    def mission_log(mid:str,request:Request,after:float|None=None,limit:int=200,source:str|None=None):
        # Full append-only history from genesis: revisions plus every logged event, in time order.
        store.snapshot(mid,owner(request))
        limit=max(1,min(limit,1000))
        from sqlalchemy import select
        from sqlalchemy.orm import Session
        from .store import Revision
        with Session(store.engine) as db:
            q=select(Revision).where(Revision.mission_id==mid)
            if after is not None:q=q.where(Revision.created>after)
            revs=[{'at':r.created,'source':'revision','kind':r.operation.get('kind','revision'),'record':{'revision':r.revision,'operation':r.operation,'hash':r.hash,'tick':r.state.get('tick')}}
                  for r in db.scalars(q.order_by(Revision.created).limit(limit)).all()]
        events=[] if source=='revision' else store.events(mid,after,limit,source)
        rows=sorted((revs if source in (None,'revision') else [])+events,key=lambda r:r['at'])[:limit]
        return {'rows':rows,'next_after':rows[-1]['at'] if len(rows)==limit else None}

    @app.get('/api/v1/missions/{mid}/evaluation')
    def evaluation(mid:str,request:Request):
        from .evaluation import evaluate
        return evaluate(store.snapshot(mid,owner(request))['state'])

    @app.get('/api/v1/missions/{mid}/revisions')
    def revisions(mid:str,request:Request):
        # Replay index: every stored revision (append-only), lightweight.
        store.snapshot(mid,owner(request))
        from sqlalchemy import select
        from sqlalchemy.orm import Session
        from .store import Revision
        with Session(store.engine) as db:
            rows=db.execute(select(Revision.revision,Revision.created,Revision.operation).where(Revision.mission_id==mid).order_by(Revision.revision)).all()
        return {'revisions':[{'revision':r[0],'at':r[1],'kind':(r[2] or {}).get('kind')} for r in rows]}

    @app.get('/api/v1/missions/{mid}/revisions/{n}')
    def revision_state(mid:str,n:int,request:Request):
        store.snapshot(mid,owner(request))
        from sqlalchemy import select
        from sqlalchemy.orm import Session
        from .store import Revision
        with Session(store.engine) as db:
            r=db.scalar(select(Revision).where(Revision.mission_id==mid,Revision.revision==n))
            if not r:raise HTTPException(404,'No such revision')
            from .engine import effective_clock
            return {'revision':r.revision,'at':r.created,'operation':r.operation,'state':r.state,'simulation_clock':effective_clock(r.state)}

    @app.get('/api/v1/missions/{mid}/operations')
    def operations(mid:str,request:Request):
        from .inspection import inspect
        return inspect(store,mid,owner(request))

    @app.get('/api/v1/missions/{mid}/schedule')
    def schedule(mid:str,request:Request):
        from .schedule import forecast
        state=store.snapshot(mid,owner(request))['state']
        cached=store.status('uncertainty') if mid=='public' else None
        return {**forecast(state),'uncertainty':cached or {'status':'computed by the worker for the public mission once per sol; not computed for experiments' if mid!='public' else 'not yet computed'}}

    @app.get('/api/v1/missions/{mid}/region')
    def region(mid:str,request:Request):
        from .store import SourceVersion
        from .region import BOUNDS,local_sensors
        s=store.snapshot(mid,owner(request))['state']
        with store.transaction() as db:
            sources={key:{'version_id':vid,**v.record} for key,vid in s['source_pins'].items()
                     if key in ('mola-arcadia','swim','swim-radar') and (v:=db.get(SourceVersion,vid))}
        return {'bounds':BOUNDS,'local_sensors':s.get('local_sensors',local_sensors()),'sources':sources}

    @app.get('/api/v1/site/analysis')
    def site_analysis_status():
        # SAM site analysis progress for the Evidence tab: started, pinned (with version) or failed (with the reason).
        return store.status('site-analysis') or {'status':'not started'}

    @app.get('/api/v1/environment/live')
    def live_environment():
        # Live Mars conditions now, independent of whether the mission is running.
        from sqlalchemy import select
        from .store import EnvironmentObservation, Mission
        from sqlalchemy.orm import Session
        with Session(store.engine) as db:
            p=db.get(Mission,'public')
            applied=deepcopy_or_none(p.state.get('environment')) if p else None
            status=p.state['status'] if p else None
            rows=db.scalars(select(EnvironmentObservation).order_by(EnvironmentObservation.observed_at.desc()).limit(40)).all()
            observations=[{'id':r.id,'kind':r.kind,'observed_at':r.observed_at,**r.record} for r in rows]
        now=time.time()
        try: live=store.environment(now, None); error=None
        except Exception as exc: live=None; error=f'{type(exc).__name__}: {exc}'[:400]
        return {'now':live,'error':error,'conditions_status':store.status('conditions'),'dsn':store.status('dsn'),
                'worker':store.status('worker'),'applied':applied,'mission_status':status,'observations':observations}

    @app.get('/api/v1/environment/weather')
    def weather():
        # Measured -> estimated -> checked, per station and variable, plus the feed status.
        from .nowcast import summary
        from .package import load
        return {'stations':summary(store,load()['values']['mars.sol_s']),'feeds':store.status('weather-feeds')}

    @app.get('/api/v1/site/ground.jpg')
    @app.get('/api/v1/missions/{mid}/evidence/ground.jpg')
    def ground_texture(request:Request,mid:str='public',version:str|None=None):
        # Require pinned imagery covering the site. A remote reference image must not impersonate local ground.
        from .science import fetch
        from .store import SourceVersion
        s=store.snapshot(mid,owner(request))['state']
        si=s.get('site_imagery')
        independent=s['source_pins'].get('hirise-ground')
        if not independent and (not si or not si.get('applies_to_site')):
            raise HTTPException(404,'No site-covering imagery is pinned; no reference ground substituted')
        selected=independent or s['source_pins'].get(si['source_id'],'')
        if version is not None and version!=selected:raise HTTPException(409,'Evidence pin changed; refresh the mission snapshot before rendering')
        version=selected
        with store.transaction() as db:
            v=db.get(SourceVersion,version)
            record=v.record if v else {}
            url=record.get('browse')
            product=v.record.get('product') if v else None
        if not record.get('applies_to_site'):raise HTTPException(404,'Pinned imagery does not cover the site')
        if not url:raise HTTPException(404,'Pinned site imagery has no browse image; no reference ground substituted')
        try:raw,_=fetch(url,60_000_000)
        except Exception as exc:raise HTTPException(502,f'HiRISE image unavailable: {type(exc).__name__}: {exc}')
        if independent and hashlib.sha256(raw).hexdigest()!=record.get('content_hash'):
            raise HTTPException(502,'HiRISE image differs from the pinned source; no replacement ground shown')
        if record.get('display_kind')!='unannotated-full-rdr-browse':
            raise HTTPException(409,'Pinned browse is not a verified map raster; inspect the source image in Evidence or adopt the corrected source version')
        from .media import browse_site_crop,MediaError
        try:cropped,transform=browse_site_crop(raw,record['coverage_verification'])
        except (MediaError,KeyError,ValueError) as exc:raise HTTPException(502,'Site image mapping unavailable: '+str(exc))
        return Response(cropped,media_type='image/jpeg',headers={'Cache-Control':'no-cache','X-Source-URL':url,'X-Product':product or 'unspecified','X-Source-Version':version,
            'X-Source-Raw-SHA256':record['content_hash'],'X-Image-Transform':json.dumps(transform,separators=(',',':'))})

    @app.get('/api/v1/site/segmented.jpg')
    def segmented_image():
        # The exact image SAM 3.1 segmented for the mission site (full-resolution window), so detections overlay correctly.
        import base64
        from .store import SourceVersion
        s=store.snapshot('public')['state'];si=s.get('site_imagery')
        if not si:raise HTTPException(404,'Site imagery has not been analysed yet')
        with store.transaction() as db:
            v=db.get(SourceVersion,s['source_pins'].get(si['source_id'],''))
            b64=(v.record.get('image_source') or {}).get('segmented_jpeg_b64') if v else None
        if not b64:raise HTTPException(404,'The segmented image is the browse JPEG; see image_url')
        return Response(base64.b64decode(b64),media_type='image/jpeg',headers={'Cache-Control':'public, max-age=86400'})

    @app.get('/api/v1/missions/{mid}/evidence/swim.png')
    def swim_image(mid:str,request:Request):
        # API and worker use separate filesystems. Serve the mission's pinned image from shared evidence,
        # not a PNG written into the worker's private frontend directory.
        from .store import SourceVersion
        from .science import fetch,SWIM_BROWSE
        s=store.snapshot(mid,owner(request))['state']
        vid=s['source_pins'].get('swim')
        if not vid:raise HTTPException(404,'No SWIM product is pinned to this mission')
        with store.transaction() as db:
            version=db.get(SourceVersion,vid);record=deepcopy_or_none(version.record) if version else None
        if not record:raise HTTPException(404,'Pinned SWIM source version is missing')
        expected=record.get('browse_hash')
        if not expected:raise HTTPException(409,'Pinned SWIM source has no browse-image hash')
        try:
            raw=bytes.fromhex(record['browse_png_hex']) if record.get('browse_png_hex') else fetch(SWIM_BROWSE,15_000_000)[0]
        except Exception as exc:raise HTTPException(502,f'Pinned SWIM image unavailable: {type(exc).__name__}')
        if not raw.startswith(b'\x89PNG\r\n\x1a\n') or hashlib.sha256(raw).hexdigest()!=expected:
            raise HTTPException(502,'SWIM image differs from the pinned hash; no replacement image shown')
        return Response(raw,media_type='image/png',headers={'Cache-Control':'private, max-age=86400','X-Source-Version':vid,'X-Content-SHA256':expected})

    @app.get('/api/v1/missions/{mid}/export')
    def records(mid:str,request:Request): return store.export(mid,owner(request))

    @app.post('/api/v1/start')
    def start(request:Request):
        # Genesis: the operator presses Start. The public mission is created once; pressing again changes nothing.
        # Only the operator may start it: the request must carry MISSION_OPERATOR_TOKEN (visitors only fork experiments).
        if app.state.init_error: return Response('Mission cannot start: '+app.state.init_error,503)
        expected=operator_token()
        if not expected: return Response('Mission cannot start: MISSION_OPERATOR_TOKEN is not set on the server',503)
        given=request.headers.get('x-operator-token','')
        if not secrets.compare_digest(given.encode(),expected.encode()): return Response('Only the operator can start the public mission (operator token missing or wrong)',403)
        created=store.genesis()
        return {'started':True,'created':created,'mission':store.snapshot('public')}

    @app.delete('/api/v1/missions/{mid}')
    def end_experiment(mid:str,request:Request):
        # The visitor ends their own experiment; the copy and its history are deleted. Never the public mission.
        return store.end_experiment(mid,owner(request))

    @app.post('/api/v1/forks')
    def fork(body:ForkRequest,request:Request,response:Response):
        token=request.cookies.get('mars_session') or secrets.token_urlsafe(32)
        result=store.fork(body.revision,hashlib.sha256(token.encode()).hexdigest())
        response.set_cookie('mars_session',token,httponly=True,secure=os.getenv('COOKIE_SECURE','true')=='true',samesite='strict',max_age=7*86400,path='/')
        return result

    @app.post('/api/v1/missions/{mid}/control')
    def control(mid:str,body:Control,request:Request):
        return store.control(mid,owner(request),body.revision,body.action,body.changes,body.ticks)

    @app.get('/api/v1/missions/{mid}/events')
    async def events(mid:str,request:Request):
        identity=owner(request)
        store.snapshot(mid,identity)
        async def stream():
            last=request.headers.get('last-event-id','')
            while not await request.is_disconnected():
                snap=await asyncio.to_thread(store.snapshot,mid,identity)
                current=str(snap['revision'])
                if current!=last:
                    yield f'id: {current}\nevent: snapshot\ndata: {json.dumps(snap)}\n\n'
                    last=current
                else: yield ': heartbeat\n\n'
                await asyncio.sleep(3)
        return StreamingResponse(stream(),media_type='text/event-stream',headers={'X-Accel-Buffering':'no','Cache-Control':'no-cache'})

    frontend=Path(__file__).resolve().parents[2]/'frontend'/'out'
    if frontend.exists():
        app.mount('/',StaticFiles(directory=frontend,html=True),name='frontend')
    return app

class ForkRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    revision:int=Field(ge=1)

class Control(BaseModel):
    model_config=ConfigDict(extra='forbid')
    revision:int=Field(ge=1)
    action:str
    changes:dict|None=None
    ticks:int=Field(default=0,ge=0,le=72)

app=create_app()

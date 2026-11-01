"""Versioned mission API. Public reads; cookie-owned, isolated experiments."""
import asyncio
import hashlib
import json
import os
import secrets
import time
from pathlib import Path
from fastapi import FastAPI, Request, Response, HTTPException
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ConfigDict
from .store import Store
from .engine import InvalidAction

def deepcopy_or_none(value):
    import copy
    return copy.deepcopy(value) if value is not None else None

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
            return {'status':'ok','started':False,'worker':heartbeat,'worker_stale':not heartbeat or time.time()-heartbeat['heartbeat_at']>600}
        s=store.snapshot('public')['state']
        return {'status':'ok','started':True,'planner':s['mode'],'model_calls_enabled':s['mode']=='meta','planning_status':s['planning_status'],
                'worker':heartbeat,'worker_stale':not heartbeat or time.time()-heartbeat['heartbeat_at']>600,'sources':store.status('source-refresh')}

    @app.get('/api/v1/missions/{mid}')
    def mission(mid:str,request:Request): return store.snapshot(mid,owner(request))

    @app.get('/api/v1/missions/{mid}/records')
    def compact_records(mid:str,request:Request):
        result=store.export(mid,owner(request))
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

    @app.get('/api/v1/missions/{mid}/landing')
    def landing(mid:str,request:Request):
        # D17: landing at the mission site on NASA's published Mars 2020 EDL timeline, replayed after Start.
        # Every number is a package parameter with its source and quote; unpublished values are null, never filled in.
        store.snapshot(mid,owner(request))
        from sqlalchemy import select
        from sqlalchemy.orm import Session
        from .store import Revision
        from .package import load
        from .conditions import SITE
        pkg=load();v=pkg['values'];P=pkg['parameters'];S=pkg['sources']
        with Session(store.engine) as db:
            r=db.scalar(select(Revision).where(Revision.mission_id==mid).order_by(Revision.revision).limit(1))
            if not r:raise HTTPException(404,'Mission has no genesis revision')
            genesis,assets=r.created,r.state['assets']
        def cite(*names):
            out=[]
            for n in names:
                p=P[n];src=S.get(p.get('source'),{})
                out.append({'parameter':n,'value':v[n],'unit':p.get('unit'),'classification':p['classification'],
                            'quote':p.get('quote'),'source':src.get('title'),'url':src.get('url'),'formula':p.get('formula')})
            return out
        def ev(key,title,t,alt_m,speed_kph,names,note=None):
            return {'key':key,'title':title,'t_s':t,'altitude_m':alt_m,'speed_kph':speed_kph,'evidence':cite(*names),'note':note}
        td=v['edl.touchdown_time_s']
        events=[
            ev('cruise-separation','Cruise stage separates',-v['edl.cruise_sep_before_entry_min']*60,None,None,['edl.cruise_sep_before_entry_min'],'Altitude and speed not published for this event.'),
            ev('entry','Atmospheric entry',0,None,v['edl.entry_speed_kph'],['edl.entry_speed_kph'],'Entry altitude not published in the cited source.'),
            ev('parachute','Parachute deploys',v['edl.parachute_time_s'],v['edl.parachute_altitude_km']*1000,v['edl.parachute_speed_kph'],['edl.parachute_time_s','edl.parachute_altitude_km','edl.parachute_speed_kph','edl.under_chute_speed_kph']),
            ev('heat-shield','Heat shield separates',v['edl.heatshield_time_s'],None,None,['edl.heatshield_time_s','edl.heatshield_time_conflict_min'],pkg['conflicts']['edl_heatshield_time']['note']),
            ev('backshell','Backshell and parachute separate',None,v['edl.backshell_altitude_m'],None,['edl.backshell_altitude_m'],'Time not published; placed where the interpolated altitude reaches 2,100 m.'),
            ev('skycrane','Skycrane lowers the payload',td-v['edl.skycrane_before_touchdown_s'],v['edl.skycrane_altitude_m'],None,['edl.skycrane_before_touchdown_s','edl.skycrane_altitude_m','edl.bridle_length_m']),
            ev('touchdown','Touchdown at the mission site',td,0,v['edl.final_descent_speed_kph'],['edl.duration_min','edl.final_descent_speed_kph']),
        ]
        return {'decision':pkg['decisions']['D17_landing'],
                'site':SITE,'genesis_unix':genesis,
                'edl':{'reference':'Mars 2020 Perseverance EDL, NASA/JPL captions','events':events,
                       'conflict':pkg['conflicts']['edl_heatshield_time']},
                'payload':[{'id':a['id'],'name':a['name'],'kind':a['kind'],'position':a['position']} for a in assets]}

    @app.get('/api/v1/missions/{mid}/revisions/{n}')
    def revision_state(mid:str,n:int,request:Request):
        store.snapshot(mid,owner(request))
        from sqlalchemy import select
        from sqlalchemy.orm import Session
        from .store import Revision
        with Session(store.engine) as db:
            r=db.scalar(select(Revision).where(Revision.mission_id==mid,Revision.revision==n))
            if not r:raise HTTPException(404,'No such revision')
            return {'revision':r.revision,'at':r.created,'operation':r.operation,'state':r.state}

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

    @app.get('/api/v1/missions/{mid}/visuals')
    def visuals(mid:str,request:Request):
        from sqlalchemy import select
        from .store import Visual
        store.snapshot(mid,owner(request))
        with store.transaction() as db:
            rows=db.scalars(select(Visual).where(Visual.mission_id==mid).order_by(Visual.created)).all()
            visuals=[{'trigger':v.trigger,'created_at':v.created,'has_image':v.image is not None,**v.record} for v in rows]
        return {'visuals':visuals,'site_analysis':store.status('site-analysis')}

    @app.get('/api/v1/missions/{mid}/visuals/{trigger}/image')
    def visual_image(mid:str,trigger:str,request:Request):
        from sqlalchemy import select
        from .store import Visual
        store.snapshot(mid,owner(request))
        with store.transaction() as db:
            v=db.scalar(select(Visual).where(Visual.mission_id==mid,Visual.trigger==trigger))
            if not v or v.image is None:raise HTTPException(404,'No image for this trigger')
            return Response(v.image,media_type='image/'+v.record.get('output_format','webp'),headers={'Cache-Control':'public, max-age=31536000, immutable'})

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
                'applied':applied,'mission_status':status,'observations':observations}

    @app.get('/api/v1/environment/weather')
    def weather():
        # Measured -> estimated -> checked, per station and variable, plus the feed status.
        from .nowcast import summary
        from .package import load
        return {'stations':summary(store,load()['values']['mars.sol_s']),'feeds':store.status('weather-feeds')}

    @app.get('/api/v1/site/ground.jpg')
    def ground_texture():
        # Ground texture for the 3D scene: centre crop of the HiRISE image nearest the mission site (or the reference image).
        import io
        from PIL import Image
        from .media import HIRISE
        from .science import fetch
        from .store import SourceVersion
        s=store.snapshot('public')['state']
        url,product=HIRISE['browse'],HIRISE['product']
        si=s.get('site_imagery')
        if si:
            with store.transaction() as db:
                v=db.get(SourceVersion,s['source_pins'].get(si['source_id'],''))
                if v:url,product=v.record.get('image_url',url),v.record.get('product',product)
        try:raw,_=fetch(url,60_000_000)
        except Exception as exc:raise HTTPException(502,f'HiRISE image unavailable: {type(exc).__name__}: {exc}')
        with Image.open(io.BytesIO(raw)) as im:
            im=im.convert('L');w,h=im.size;side=min(w,h,1600)
            crop=im.crop(((w-side)//2,(h-side)//2,(w+side)//2,(h+side)//2)).resize((1024,1024))
            out=io.BytesIO();crop.save(out,format='JPEG',quality=85)
        return Response(out.getvalue(),media_type='image/jpeg',headers={'Cache-Control':'public, max-age=86400','X-Source-URL':url,'X-Product':product})

    @app.get('/api/v1/site/hirise.jpg')
    def hirise_photo():
        # Real HiRISE photograph for the launch view, fetched by the server and cached on disk.
        from .media import HIRISE
        from .science import fetch
        last=None
        for url in (HIRISE['hero'],HIRISE['browse']):
            try:
                raw,_=fetch(url,60_000_000)
                return Response(raw,media_type='image/jpeg',headers={'Cache-Control':'public, max-age=86400','X-Source-URL':url,'X-Credit':HIRISE['credit']})
            except Exception as exc:last=f'{url}: {exc}'
        raise HTTPException(502,f'HiRISE image unavailable: {last}')

    @app.get('/api/v1/missions/{mid}/export')
    def records(mid:str,request:Request): return store.export(mid,owner(request))

    @app.post('/api/v1/start')
    def start():
        # Genesis: the user presses Start. The public mission is created once; pressing again changes nothing.
        if app.state.init_error: return Response('Mission cannot start: '+app.state.init_error,503)
        created=store.genesis()
        return {'started':True,'created':created,'mission':store.snapshot('public')}

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

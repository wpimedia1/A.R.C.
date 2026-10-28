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

def create_app(store=None):
    store=store or Store()
    store.initialize()
    app=FastAPI(title='Mars Mission',version='1.0')
    app.state.store=store

    def owner(request):
        token=request.cookies.get('mars_session','')
        return hashlib.sha256(token.encode()).hexdigest() if token else None

    @app.middleware('http')
    async def boundaries(request, call_next):
        if request.method not in ('GET','HEAD','OPTIONS'):
            origin=request.headers.get('origin')
            expected=os.getenv('PUBLIC_ORIGIN',str(request.base_url).rstrip('/'))
            if origin and origin!=expected: return Response('Cross-origin writes are not allowed',403)
            if request.headers.get('sec-fetch-site')=='cross-site': return Response('Cross-site writes are not allowed',403)
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
        s=store.snapshot('public')['state']
        heartbeat=store.status('worker')
        return {'status':'ok','planner':s['mode'],'model_calls_enabled':s['mode']=='meta','planning_status':s['planning_status'],
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
        return {'sources':sources,'decisions':result['state']['decisions'],'inference_receipts':result['inference_receipts'],'source_checks':store.status('source-refresh')}

    @app.get('/api/v1/missions/{mid}/export')
    def records(mid:str,request:Request): return store.export(mid,owner(request))

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

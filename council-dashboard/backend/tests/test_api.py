import asyncio
import httpx
from mission.api import create_app
from mission.store import Store
from conftest import make_store

def test_api_permissions_revision_and_cookie(tmp_path,monkeypatch,request):
    monkeypatch.setenv('COOKIE_SECURE','false')
    store=make_store(tmp_path,request);store.initialize();app=create_app(store)
    async def exercise():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
            p=(await client.get('/api/v1/missions/public')).json()
            denied=await client.post('/api/v1/missions/public/control',json={'revision':p['revision'],'action':'pause'})
            assert denied.status_code==403
            origin=await client.post('/api/v1/forks',json={'revision':p['revision']},headers={'Origin':'https://attacker.example'})
            assert origin.status_code==403
            response=await client.post('/api/v1/forks',json={'revision':p['revision']})
            assert response.status_code==200
            assert 'HttpOnly' in response.headers['set-cookie'] and 'SameSite=strict' in response.headers['set-cookie']
            fork=response.json()
            response=await client.post('/api/v1/missions/'+fork['id']+'/control',json={'revision':fork['revision'],'action':'run','ticks':24})
            assert response.status_code==200
            stale=await client.post('/api/v1/missions/'+fork['id']+'/control',json={'revision':fork['revision'],'action':'pause'})
            assert stale.status_code==409
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as outsider:
                assert (await outsider.get('/api/v1/missions/'+fork['id']+'/export')).status_code==403
    asyncio.run(exercise())


def test_same_host_origin_allowed_and_foreign_origin_rejected(tmp_path, monkeypatch, request):
    monkeypatch.setenv('COOKIE_SECURE', 'false')
    monkeypatch.setenv('PUBLIC_ORIGIN', 'http://127.0.0.1:8020')
    store = make_store(tmp_path, request); store.initialize(); app = create_app(store)
    async def exercise():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://localhost:8020') as client:
            p = (await client.get('/api/v1/missions/public')).json()
            ok = await client.post('/api/v1/forks', json={'revision': p['revision']}, headers={'Origin': 'http://localhost:8020'})
            assert ok.status_code == 200
            bad = await client.post('/api/v1/forks', json={'revision': p['revision']}, headers={'Origin': 'http://evil.example'})
            assert bad.status_code == 403
    asyncio.run(exercise())


def test_mission_waits_for_start(tmp_path, request):
    # The API and worker never create the mission; genesis happens when a user presses Start, once.
    store=make_store(tmp_path,request);app=create_app(store)
    async def exercise():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
            h=(await client.get('/api/v1/health')).json()
            assert h['status']=='ok' and h['started'] is False
            assert (await client.get('/api/v1/missions/public')).status_code==404
            first=await client.post('/api/v1/start')
            assert first.status_code==200 and first.json()['created'] is True
            again=await client.post('/api/v1/start')
            assert again.status_code==200 and again.json()['created'] is False
            assert again.json()['mission']['revision']==first.json()['mission']['revision']
            assert (await client.post('/api/v1/start',headers={'Origin':'https://attacker.example'})).status_code==403
            return (await client.get('/api/v1/missions/public/revisions')).json()['revisions']
    revs=asyncio.run(exercise())
    assert revs[0]['kind']=='initialize'


def test_visitor_ends_own_experiment_only(tmp_path, monkeypatch, request):
    monkeypatch.setenv('COOKIE_SECURE','false')
    store=make_store(tmp_path,request);store.initialize();app=create_app(store)
    async def exercise():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
            p=(await client.get('/api/v1/missions/public')).json()
            fork=(await client.post('/api/v1/forks',json={'revision':p['revision']})).json()
            assert (await client.delete('/api/v1/missions/public')).status_code==403
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as outsider:
                assert (await outsider.delete('/api/v1/missions/'+fork['id'])).status_code==403
            assert (await client.delete('/api/v1/missions/'+fork['id'])).status_code==200
            assert (await client.get('/api/v1/missions/'+fork['id'])).status_code==404
            again=await client.post('/api/v1/forks',json={'revision':p['revision']})
            assert again.status_code==200  # a fresh experiment can start once the old one is ended
            assert (await client.get('/api/v1/missions/public')).status_code==200
    asyncio.run(exercise())

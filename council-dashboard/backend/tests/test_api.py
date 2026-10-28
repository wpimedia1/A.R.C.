import asyncio
import httpx
from mission.api import create_app
from mission.store import Store

def test_api_permissions_revision_and_cookie(tmp_path,monkeypatch):
    monkeypatch.setenv('COOKIE_SECURE','false')
    store=Store('sqlite:///'+str(tmp_path/'api.db'));app=create_app(store)
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

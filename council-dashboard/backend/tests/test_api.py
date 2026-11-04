import asyncio
import httpx
from mission.api import create_app
from conftest import make_store


def test_records_reads_pins_without_constructing_full_export(tmp_path,request,monkeypatch):
    store=make_store(tmp_path,request);store.initialize();app=create_app(store)
    def forbidden(*args,**kwargs):raise AssertionError('A normal page load must not materialize the full mission history')
    monkeypatch.setattr(store,'export',forbidden)
    async def exercise():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
            response=await client.get('/api/v1/missions/public/records')
            assert response.status_code==200
            result=response.json();pins=store.snapshot('public')['state']['source_pins']
            assert set(pins)==set(result['sources']) and set(pins.values())<=set(result['source_versions'])
            assert 'history' not in result and 'inference_receipts' in result
    asyncio.run(exercise())


def test_live_operations_compacts_context_without_losing_export_or_history(tmp_path,request):
    """Isolated fixture receipt; explicitly not evidence of a provider call."""
    from mission.store import InferenceReceipt
    from mission.inspection import inspect
    store=make_store(tmp_path,request);store.initialize()
    expected={}
    with store.transaction() as db:
        db.add(InferenceReceipt(id='unit-test-only',mission_id='public',record={
            'status':'unit-test-only','model':'no-provider','created_at':0,
            'request':{'instructions':'Unit fixture context'},'actual_usd':0,
            'tool_calls':[{'name':'unit-test-only','arguments':{}}]}))
        m=store.row(db,'public')
        for _ in range(3):
            s=store.step(m.state);store.save(db,m,s,{'kind':'unit-test-step'})
            expected[s['tick']]={**s['resources'],'energy_used_kwh':s['energy_used_kwh'],'spent_usd':s['spent_usd']}
    panel=inspect(store,'public')
    receipt=next(r for r in panel['receipts'] if r['id']=='unit-test-only')
    assert 'request' not in receipt and receipt['tool_calls'][0]['name']=='unit-test-only'
    exported=next(r for r in store.export('public')['inference_receipts'] if r['id']=='unit-test-only')
    assert exported['request']['instructions']=='Unit fixture context'
    import pytest
    for row in panel['series']:
        # SQLite JSON projections serialize numeric display values to 15 digits;
        # the full immutable state/export retains the original float precision.
        if row['tick'] in expected:assert {k:v for k,v in row.items() if k!='tick'}==pytest.approx(expected[row['tick']],rel=1e-12,abs=1e-9)


def test_ground_never_substitutes_remote_reference_for_site(tmp_path,request,monkeypatch):
    from copy import deepcopy
    from mission import science
    store=make_store(tmp_path,request);store.initialize();app=create_app(store)
    def forbid_fetch(*args,**kwargs):raise AssertionError('No image may be fetched without site-covering pinned evidence')
    monkeypatch.setattr(science,'fetch',forbid_fetch)
    async def exercise():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
            absent=await client.get('/api/v1/site/ground.jpg')
            assert absent.status_code==404 and 'no reference ground substituted' in absent.text
            with store.transaction() as db:
                m=store.row(db,'public');s=deepcopy(m.state)
                s['site_imagery']={'source_id':'test-proxy','applies_to_site':False}
                store.save(db,m,s,{'kind':'test-fixture'})
            proxy=await client.get('/api/v1/site/ground.jpg')
            assert proxy.status_code==404
    asyncio.run(exercise())


def test_ground_checks_exact_pinned_image_hash(tmp_path,request,monkeypatch):
    from copy import deepcopy
    from mission.store import SourceVersion
    from mission import science
    store=make_store(tmp_path,request);store.initialize();app=create_app(store)
    with store.transaction() as db:
        db.add(SourceVersion(id='test-ground:1',source_id='hirise-ground',record={
            'applies_to_site':True,'browse':'https://test.invalid/image','product':'test-only',
            'content_hash':'not-the-returned-image-hash'}))
        m=store.row(db,'public');s=deepcopy(m.state);s['source_pins']['hirise-ground']='test-ground:1'
        store.save(db,m,s,{'kind':'test-fixture'})
    monkeypatch.setattr(science,'fetch',lambda *args:(b'changed source bytes',0))
    async def exercise():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
            response=await client.get('/api/v1/missions/public/evidence/ground.jpg')
            assert response.status_code==502 and 'differs from the pinned source' in response.text
    asyncio.run(exercise())

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


def test_mission_waits_for_start(tmp_path, monkeypatch, request):
    # The API and worker never create the mission; genesis happens when the operator presses Start, once.
    import mission.provider as provider
    monkeypatch.setattr(provider,'ENV_FILE',tmp_path/'absent.env');monkeypatch.delenv('MISSION_OPERATOR_TOKEN',raising=False)
    store=make_store(tmp_path,request);app=create_app(store)
    async def exercise():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
            h=(await client.get('/api/v1/health')).json()
            assert h['status']=='ok' and h['started'] is False
            assert (await client.get('/api/v1/missions/public')).status_code==404
            assert (await client.post('/api/v1/start')).status_code==503  # no operator token configured: nobody can start
            monkeypatch.setenv('MISSION_OPERATOR_TOKEN','operator-test-token')
            assert (await client.post('/api/v1/start')).status_code==403  # visitor without the token
            assert (await client.post('/api/v1/start',headers={'X-Operator-Token':'wrong'})).status_code==403
            assert (await client.get('/api/v1/missions/public')).status_code==404
            op={'X-Operator-Token':'operator-test-token'}
            first=await client.post('/api/v1/start',headers=op)
            assert first.status_code==200 and first.json()['created'] is True
            again=await client.post('/api/v1/start',headers=op)
            assert again.status_code==200 and again.json()['created'] is False
            assert again.json()['mission']['revision']==first.json()['mission']['revision']
            assert (await client.post('/api/v1/start',headers={'Origin':'https://attacker.example',**op})).status_code==403
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


def test_ground_request_cannot_render_a_different_source_version(tmp_path,request,monkeypatch):
    from copy import deepcopy
    from mission.store import SourceVersion
    from mission import science
    store=make_store(tmp_path,request);store.initialize()
    with store.transaction() as db:
        db.add(SourceVersion(id='unit-ground-current',source_id='hirise-ground',record={'applies_to_site':True}))
        m=store.row(db,'public');state=deepcopy(m.state);state['source_pins']['hirise-ground']='unit-ground-current'
        store.save(db,m,state,{'kind':'explicit unit-test source pin'})
    def forbid(*args):raise AssertionError('No image fetch may follow a source-version mismatch')
    monkeypatch.setattr(science,'fetch',forbid)
    app=create_app(store)
    async def exercise():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
            result=await client.get('/api/v1/missions/public/evidence/ground.jpg?version=unit-ground-old')
            assert result.status_code==409 and 'pin changed' in result.text
    asyncio.run(exercise())


def test_acceptance_view_rejects_writes_but_allows_inspection(tmp_path,request,monkeypatch):
    store=make_store(tmp_path,request);store.initialize();app=create_app(store)
    monkeypatch.setenv('ACCEPTANCE_READ_ONLY','1')
    async def exercise():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
            snapshot=await client.get('/api/v1/missions/public')
            assert snapshot.status_code==200
            result=await client.post('/api/v1/forks',json={'revision':snapshot.json()['revision']})
            assert result.status_code==403 and 'read-only' in result.text
    asyncio.run(exercise())

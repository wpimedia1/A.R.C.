"""Media pipeline logic that needs no network. Live calls happen in the worker with the owner's key."""
import asyncio
import httpx
import mission.provider as provider
from mission.engine import new_state, advance
from mission.media import scene_prompt, pending_visual, illustrate, site_analysis_due, _label_value
from mission.api import create_app
from mission.store import Visual
from conftest import make_store
from sqlalchemy import select


def test_prompt_comes_from_state_only():
    s = new_state('meta')
    a = scene_prompt(s, 'genesis')
    assert 'still packed on its pallets' in a and 'No people, no text' in a
    assert 'Keep the same camera position' not in a
    s['jobs'][0].update(status='complete', progress=1.0)
    b = scene_prompt(s, 'job:power')
    assert 'radiators are deployed' in b and 'Keep the same camera position' in b


def test_pending_visual_order_and_failed_call_is_recorded(tmp_path, request, monkeypatch):
    monkeypatch.setenv('MISSION_MODEL_MODE', 'meta')
    monkeypatch.delenv('MODEL_API_KEY', raising=False)
    monkeypatch.setattr(provider, 'ENV_FILE', tmp_path / 'absent.env')
    store = make_store(tmp_path, request)
    store.initialize()
    assert pending_visual(store) == 'genesis'
    record = illustrate(store, 'public', 'genesis')
    assert record['status'] == 'failed' and 'MODEL_API_KEY' in record['error']
    with store.transaction() as db:
        v = db.scalar(select(Visual).where(Visual.trigger == 'genesis'))
        assert v.image is None
    assert pending_visual(store) is None  # failures are visible, not retried automatically
    assert site_analysis_due(store)   # D13: orbital segmentation is due at genesis


def test_visual_endpoints(tmp_path, request, monkeypatch):
    monkeypatch.setenv('COOKIE_SECURE', 'false')
    store = make_store(tmp_path, request); store.initialize(); app = create_app(store)
    async def go():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as c:
            r = await c.get('/api/v1/missions/public/visuals')
            assert r.status_code == 200 and r.json()['visuals'] == []
            assert (await c.get('/api/v1/missions/public/visuals/genesis/image')).status_code == 404
    asyncio.run(go())


def test_hirise_label_parsing():
    label = 'OBJECT = IMAGE\n  LINES = 52000\n  LINE_SAMPLES = 21000\nEND_OBJECT\n  MAP_SCALE = 0.25 <METERS/PIXEL>\n'
    assert _label_value(label, 'LINE_SAMPLES') == 21000 and _label_value(label, 'MAP_SCALE') == 0.25

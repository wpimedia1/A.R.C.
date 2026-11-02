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


# Projection keywords copied from the real label of HiRISE ESP_056974_2205_RED (hirise.lpl.arizona.edu PDS RDR).
ESP_056974_LABEL = '''    CENTER_LATITUDE              = 40.000 <DEG>
    CENTER_LONGITUDE             = 180.000 <DEG>
    MAP_RESOLUTION               = 118259.58864773 <PIX/DEG>
    MAP_SCALE                    = 0.5 <METERS/PIXEL>
    LINE_PROJECTION_OFFSET       = 4770142.5 <PIXEL>
    SAMPLE_PROJECTION_OFFSET     = -922911.5 <PIXEL>
    MAXIMUM_LATITUDE             = 40.336194259789 <DEG>
    WESTERNMOST_LONGITUDE        = 190.18755660562 <DEG>
'''


def test_site_is_the_centre_pixel_of_the_covering_hirise_image():
    from mission.media import site_pixel
    from mission.conditions import SITE
    line, sample = site_pixel(ESP_056974_LABEL, SITE['latitude'], SITE['longitude_east'])
    assert abs(line - (66625 - 1) / 2) < 1 and abs(sample - (18485 - 1) / 2) < 1
    # The image's north-west corner maps to pixel (0, 0) within half a pixel.
    corner = site_pixel(ESP_056974_LABEL, 40.336194259789, 190.18755660562)
    assert abs(corner[0]) < 1 and abs(corner[1]) < 1


def test_site_crop_decodes_a_full_resolution_window_centred_on_the_site(tmp_path):
    # A small JPEG2000 file with the same projection layout, written here, exercises the real decode and stretch path.
    import glymur, numpy as np, io
    from PIL import Image
    from mission.media import site_crop, site_pixel
    lines, samples = 600, 400
    label = ESP_056974_LABEL + f'  LINES = {lines}\n  LINE_SAMPLES = {samples}\n  CORE_NULL = 0\n  MRO:MINIMUM_STRETCH = 3\n  MRO:MAXIMUM_STRETCH = 1021\n'
    # Put the site at pixel (300, 200) by shifting the projection offsets for this small test image.
    lat, lon = 40.05, 190.29
    line, sample = site_pixel(ESP_056974_LABEL, lat, lon)
    label = label.replace('LINE_PROJECTION_OFFSET       = 4770142.5', f'LINE_PROJECTION_OFFSET       = {4770142.5 - line + 300}')
    label = label.replace('SAMPLE_PROJECTION_OFFSET     = -922911.5', f'SAMPLE_PROJECTION_OFFSET     = {-922911.5 - sample + 200}')
    dn = np.full((lines, samples), 512, dtype=np.uint16)
    dn[300, 200] = 1021
    path = tmp_path / 'test.jp2'
    glymur.Jp2k(str(path), data=dn)
    jpeg, window = site_crop(label, path, lat, lon, side=128)
    assert window['rows'] == [236, 364] and window['columns'] == [136, 264]
    with Image.open(io.BytesIO(jpeg)) as im:
        assert im.size == (128, 128)
        px = np.asarray(im)
    assert px[64, 64] > 240 and 120 < px[10, 10] < 135  # 1021 -> 255 at the site; 512 -> about 128 elsewhere

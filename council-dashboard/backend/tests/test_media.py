"""Media pipeline logic that needs no network. Live calls happen in the worker with the owner's key."""
import asyncio
import httpx
from mission.media import _label_value
from mission.api import create_app
from conftest import make_store


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


def test_no_hazard_free_route_blocks_the_survey():
    # Review finding 5: an unusable route is an execution blocker, not only an event.
    from mission.engine import new_state, job_by_id, reasons, start
    from mission.media import apply_site_analysis
    img = {'source_id': 'hirise-site', 'product': 'ESP_056974_2205', 'applies_to_site': True, 'site_relation': 'contains the site'}
    record = {'route': {'status': 'no hazard-free route across the scene', 'detour_factor': None, 'clearance_m': 1.35},
              'segmentations': [{'prompt': 'boulder', 'summary': {'count': 3}}], 'segmented_m_per_px': 0.5}
    s = new_state('meta'); s['source_pins'] = {}
    start(s, 'survey', ['rover-1'], 'survey', 'survey / test', [s['spec']['package_id']])
    assert job_by_id(s, 'survey')['status'] == 'review'
    apply_site_analysis(s, img, record, 'hirise-site:v1')
    sv = job_by_id(s, 'survey')
    assert sv['status'] == 'blocked' and sv['route_blocked']['source_version'] == 'hirise-site:v1' and s['power_used_kw'] == 0
    assert any('No hazard-free route' in r for r in reasons(s, sv, ['rover-1']))


def test_site_analysis_status_endpoint(tmp_path, request):
    store = make_store(tmp_path, request); store.initialize(); app = create_app(store)
    async def go():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as c:
            assert (await c.get('/api/v1/site/analysis')).json() == {'status': 'not started'}
            store.status('site-analysis', {'failed_at': 1.0, 'error': 'HTTP 503'})
            assert (await c.get('/api/v1/site/analysis')).json()['error'] == 'HTTP 503'
    asyncio.run(go())


def test_start_attaches_already_downloaded_evidence(tmp_path, request):
    # A new mission gets the newest already-retrieved regional products at Start, without downloading anything.
    import time
    from mission.store import SourceVersion
    store = make_store(tmp_path, request)
    with store.transaction() as db:
        db.add(SourceVersion(id='mola-arcadia:old', source_id='mola-arcadia', record={'retrieved_at': time.time() - 100, 'heights_m': [[1]]}))
        db.add(SourceVersion(id='mola-arcadia:new', source_id='mola-arcadia', record={'retrieved_at': time.time(), 'heights_m': [[2]]}))
        db.add(SourceVersion(id='hirise-site:x', source_id='hirise-site', record={'retrieved_at': time.time(), 'image_url': 'u'}))
    store.initialize()
    pins = store.snapshot('public')['state']['source_pins']
    assert pins['mola-arcadia'] == 'mola-arcadia:new' and 'hirise-site' not in pins


def test_each_genesis_gets_its_own_sam_site_analysis(tmp_path, request, monkeypatch):
    # A site analysis recorded for an earlier (discarded) mission must not stop SAM from running for a new genesis.
    monkeypatch.setenv('MISSION_MODEL_MODE', 'meta')
    from mission.media import site_analysis_due
    store = make_store(tmp_path, request)
    store.status('site-analysis', {'finished_at': 1.0, 'status': 'pinned', 'version': 'hirise-site:earlier-mission'})
    assert store.genesis()
    assert store.status('site-analysis') is None and site_analysis_due(store)

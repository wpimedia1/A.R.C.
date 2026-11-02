"""Meta media models on real mission inputs.

- Muse Image (muse-image-1.0): illustrations of the *persisted* mission state, generated at genesis and
  after each completed job, each one an edit of the previous illustration so the scene stays continuous.
  Every image is labeled as an AI illustration, never as observation.
- SAM 3.1 (sam-3.1): segmentation of a real HiRISE orbital image of Arcadia Planitia (public domain,
  NASA/JPL-Caltech/UArizona) for boulders and impact craters, run at genesis; detections route the survey (D13).
  Detections are model output on orbital imagery at the stated resolution, not ground truth.

Every request is recorded as an InferenceReceipt (status, HTTP status, x-request-id, cost) before and
after dispatch. Nothing is retried automatically except the documented retryable 503 on image generation.
"""
import base64
import hashlib
import math
import re
import time
from copy import deepcopy
import httpx
from sqlalchemy import select
from .provider import (credential, fingerprint, send, ProviderConfigError, ENDPOINT, IMAGE_MODEL, SAM_MODEL,
                       IMAGES_GENERATE, IMAGES_EDIT, IMAGE_USD_PER_IMAGE, SAM_USD_PER_IMAGE)
from .store import InferenceReceipt, Visual

HIRISE = {
    'source_id': 'hirise-esp052358',
    'product': 'ESP_052358_2210',
    'title': 'HiRISE ESP_052358_2210: Candidate Red Dragon landing site in Arcadia Planitia',
    'page': 'https://www.uahirise.org/ESP_052358_2210',
    'browse': 'https://hirise-pds.lpl.arizona.edu/PDS/EXTRAS/RDR/ESP/ORB_052300_052399/ESP_052358_2210/ESP_052358_2210_RED.abrowse.jpg',
    'hero': 'https://static.uahirise.org/images/2017/details/ESP_052358_2210.jpg',
    'label': 'https://hirise-pds.lpl.arizona.edu/PDS/RDR/ESP/ORB_052300_052399/ESP_052358_2210/ESP_052358_2210_RED.LBL',
    'latitude': 40.711, 'longitude_east': 201.603, 'acquired': '2017-09-27',
    'credit': 'NASA/JPL-Caltech/UArizona', 'license': 'Public domain (HiRISE image use policy); credit requested',
}
SAM_PROMPTS = ('boulder', 'impact crater')
FOOTPRINTS = 'https://astrogeology.usgs.gov/pygeoapi/collections/mars/hirise-observation-footprints-equatorial/items'
STAMP = 'AI ILLUSTRATION  ·  SIMULATED STATE  ·  NOT A PHOTOGRAPH  ·  NOT EVIDENCE'


def stamp(image_bytes):
    """Burn the illustration label into the pixels so it survives screenshots, downloads and exports."""
    from PIL import Image, ImageDraw, ImageFont
    import io
    with Image.open(io.BytesIO(image_bytes)) as img:
        img = img.convert('RGB')
        w, h = img.size
        band = max(24, h // 14)
        draw = ImageDraw.Draw(img)
        draw.rectangle([0, h - band, w, h], fill=(20, 20, 20))
        try:
            font = ImageFont.load_default(size=int(band * 0.5))
        except TypeError:
            font = ImageFont.load_default()
        draw.text((band // 2, h - band + band // 4), STAMP, fill=(255, 214, 102), font=font)
        draw.rectangle([0, 0, w - 1, h - 1], outline=(255, 214, 102), width=max(3, band // 8))
        out = io.BytesIO()
        img.save(out, format='WEBP', quality=90)
        return out.getvalue()


def _distance_km(lat1, lon1, lat2, lon2, radius_km):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * radius_km * math.asin(math.sqrt(min(1.0, a)))


def site_image(lat, lon_east, radius_km, transport=None):
    """HiRISE RED RDR product whose footprint contains the mission site (USGS footprint index); else the reference image as a proxy."""
    lon180 = ((lon_east + 180) % 360) - 180
    found, errors = [], []

    def search(half_deg):
        out = []
        for lo in sorted({lon180, lon_east}):
            try:
                with httpx.Client(timeout=60, follow_redirects=True, transport=transport) as c:
                    r = c.get(FOOTPRINTS, params={'bbox': f'{lo - half_deg},{lat - half_deg},{lo + half_deg},{lat + half_deg}', 'f': 'json', 'limit': 500})
                    r.raise_for_status()
                    out += r.json().get('features', [])
            except Exception as exc:
                errors.append(f'{type(exc).__name__}: {exc}'[:200])
        return out
    found = search(0.02)
    def contains(p):
        west, east = float(p['westlon']), float(p['eastlon'])
        lons = {lon_east % 360, lon180}
        return float(p['minlat']) <= lat <= float(p['maxlat']) and any(west <= x <= east for x in lons)
    candidates = [f['properties'] for f in found if f.get('properties', {}).get('productid', '').endswith('_RED')
                  and str(f['properties'].get('labelurl', '')).endswith('.LBL') and contains(f['properties'])]
    if candidates:
        p = min(candidates, key=lambda p: (float(p.get('emangle') or 90), p.get('utcstart') or ''))
        label = p['labelurl']
        browse = label.replace('/PDS/RDR/', '/PDS/EXTRAS/RDR/').replace('.LBL', '.abrowse.jpg')
        product = p['productid'].rsplit('_', 1)[0]
        return {**HIRISE, 'source_id': 'hirise-site', 'product': product, 'title': f'HiRISE {product}: footprint containing the mission site',
                'page': p.get('exturl') or f'https://www.uahirise.org/{product}', 'browse': browse, 'label': label,
                'latitude': float(p['centerlat']), 'longitude_east': float(p['centerlon']) % 360, 'acquired': (p.get('utcstart') or '')[:10],
                'site_relation': 'contains the mission site', 'site_distance_km': 0.0, 'applies_to_site': True,
                'footprint_index': FOOTPRINTS, 'candidates_found': len(candidates), 'search_errors': errors}
    # No footprint contains the site: use the nearest HiRISE RED product within about 1 degree, labelled with its distance.
    near = [f['properties'] for f in search(1.0) if f.get('properties', {}).get('productid', '').endswith('_RED') and str(f['properties'].get('labelurl', '')).endswith('.LBL')]
    if near:
        p = min(near, key=lambda p: _distance_km(lat, lon_east, float(p['centerlat']), float(p['centerlon']) % 360, radius_km))
        d = _distance_km(lat, lon_east, float(p['centerlat']), float(p['centerlon']) % 360, radius_km)
        label = p['labelurl']
        product = p['productid'].rsplit('_', 1)[0]
        return {**HIRISE, 'source_id': 'hirise-site', 'product': product, 'title': f'HiRISE {product}: nearest image to the mission site',
                'page': p.get('exturl') or f'https://www.uahirise.org/{product}', 'browse': label.replace('/PDS/RDR/', '/PDS/EXTRAS/RDR/').replace('.LBL', '.abrowse.jpg'),
                'label': label, 'latitude': float(p['centerlat']), 'longitude_east': float(p['centerlon']) % 360, 'acquired': (p.get('utcstart') or '')[:10],
                'site_relation': f'proxy: nearest image, centre {round(d)} km from the mission site', 'site_distance_km': round(d, 1), 'applies_to_site': False,
                'footprint_index': FOOTPRINTS, 'candidates_found': 0, 'nearby_found': len(near), 'search_errors': errors}
    d = _distance_km(lat, lon_east, HIRISE['latitude'], HIRISE['longitude_east'], radius_km)
    return {**HIRISE, 'site_relation': f'proxy: {round(d)} km from the mission site', 'site_distance_km': round(d, 1), 'applies_to_site': False,
            'footprint_index': FOOTPRINTS, 'candidates_found': 0, 'search_errors': errors,
            'note': 'No HiRISE RED footprint containing the mission site was returned' + (f' (search failed: {errors})' if errors else '') + '.'}


class MediaError(RuntimeError):
    pass


def _receipt(store, rid, mid, record):
    with store.transaction() as db:
        if db.get(InferenceReceipt, rid):
            raise MediaError(f'Request {rid} already recorded; it will not be sent twice')
        db.add(InferenceReceipt(id=rid, mission_id=mid, record=record))


def _update(store, rid, **fields):
    with store.transaction() as db:
        r = db.get(InferenceReceipt, rid)
        rec = deepcopy(r.record); rec.update(fields); r.record = rec


def _dispatch(store, rid, mid, model, url, payload, price, transport=None, retry_503=0):
    """Send one recorded request. Returns (json, correlation). Records failure and re-raises."""
    try:
        key, source = credential()
    except ProviderConfigError as exc:
        raise MediaError(str(exc)) from exc
    logged = {k: v for k, v in payload.items() if k != 'images'}
    if 'images' in payload:
        logged['images'] = [{'image_url': '<previous illustration, data URL omitted>'}] * len(payload['images'])
    _receipt(store, rid, mid, {'status': 'dispatched', 'model': model, 'endpoint': url, 'created_at': time.time(),
                               'request': logged, 'key_fingerprint': fingerprint(key), 'key_source': source,
                               'price_basis_usd': price})
    attempts = []
    for attempt in range(retry_503 + 1):
        try:
            result, corr = send(payload, key, transport, timeout=300, url=url)
            try:
                _update(store, rid, status='received', received_at=time.time(), actual_usd=price, attempts=attempts, **corr)
            except Exception as exc:
                # The provider answered and was paid: a bookkeeping error must never discard the result.
                import logging
                logging.exception('Receipt update failed after a successful %s response', model)
                corr = {**corr, 'receipt_update_error': f'{type(exc).__name__}: {exc}'[:300]}
            return result, corr
        except httpx.HTTPStatusError as exc:
            info = {'http_status': exc.response.status_code,
                    'request_id': exc.response.headers.get('x-request-id'),
                    'body': exc.response.text.replace(key, '[redacted]')[:600]}
            attempts.append(info)
            if exc.response.status_code == 503 and attempt < retry_503:
                time.sleep(5 * (attempt + 1))
                continue
            _update(store, rid, status='failed', attempts=attempts, **{k: v for k, v in info.items() if k != 'body'},
                    provider_error_message=info['body'])
            raise
        except Exception as exc:
            _update(store, rid, status='uncertain; no automatic retry', failure=type(exc).__name__, attempts=attempts)
            raise


# ---------------------------------------------------------------- Muse Image

DESCRIPTIONS = {
    'rover': 'a six-wheeled science rover similar to NASA Perseverance',
    'excavator': 'a small low robotic excavator with two counter-rotating bucket drums (RASSOR-class)',
    'rodwell': 'a compact drilling rig over a borehole, with an insulated hose to a small water tank (Rodwell)',
    'power': 'a compact fission reactor with vertical radiator panels, about one kilometre from the camp, linked by a ground cable',
    'habitat': 'a horizontal white cylindrical habitat module, 8.4 metres in diameter and 15.6 metres long',
}


def scene_prompt(s, trigger):
    """Deterministic prompt from persisted state only. Equipment and job progress come from the record."""
    # Deliberately non-photographic so the image cannot pass for a spacecraft photograph (audit 2026-10-31).
    lines = ['Technical concept illustration in a flat-shaded engineering-diagram style, clearly a drawing and not a photograph, '
             'of a simulated robotic construction site on Arcadia Planitia, Mars: a flat reddish plain under a pale sky. '
             'No people, no text, no labels, no logos.']
    present = [DESCRIPTIONS[a['kind']] + ('' if a['available'] else ' (idle, out of service)') for a in s['assets']]
    lines.append('Equipment on site: ' + '; '.join(present) + '.')
    state = []
    for j in s['jobs']:
        pct = round(100 * j['progress'])
        if j['id'] == 'power':
            state.append('the reactor radiators are deployed and the cable is laid' if j['status'] == 'complete'
                         else f'the reactor is being deployed ({pct}% of the deployment timeline)' if j['status'] == 'running'
                         else 'the reactor is still packed on its pallets')
        elif j['id'] == 'survey':
            state.append('rover wheel tracks cross the site' if j['status'] == 'complete' else 'the rover is surveying the site'
                         if j['status'] == 'running' else 'the ground is untouched')
        elif j['id'] == 'trench':
            state.append('a rectangular trench 1.58 metres deep is fully dug beside the habitat' if j['status'] == 'complete'
                         else f'a shallow rectangular trench beside the habitat is about {pct}% excavated, with spoil piles' if j['done'] > 0
                         else 'no trench has been dug yet')
        elif j['id'] == 'shielding':
            state.append('the habitat lies in the trench fully covered by a mound of regolith' if j['status'] == 'complete'
                         else f'the habitat is partly covered by regolith, about {pct}% of the shielding placed' if j['done'] > 0 else '')
        elif j['id'] == 'drill':
            state.append('the drilling rig stands over a finished borehole' if j['status'] == 'complete'
                         else f'the drilling rig is boring into the ground ({pct}% of depth)' if j['status'] == 'running' else '')
        elif j['id'] == 'water':
            state.append(f'the water tank holds about {round(j["done"])} kilograms of water' if j['done'] > 0 else '')
    lines.append('Current state: ' + '; '.join(x for x in state if x) + '.')
    if trigger != 'genesis':
        lines.append('Keep the same camera position, terrain and equipment layout as the input image; change only what the current state requires.')
    return ' '.join(lines)


def illustrate(store, mid, trigger, transport=None):
    """Generate one illustration for a trigger ('genesis' or 'job:<id>'). Stores bytes and record in mission_visuals."""
    snap = store.snapshot(mid)
    s = snap['state']
    prompt = scene_prompt(s, trigger)
    with store.transaction() as db:
        if db.scalar(select(Visual).where(Visual.mission_id == mid, Visual.trigger == trigger)):
            return None
        previous = db.scalars(select(Visual).where(Visual.mission_id == mid, Visual.image.is_not(None)).order_by(Visual.created.desc())).first()
        prev_bytes = (previous.raw_image or previous.image) if previous else None
        prev_format = previous.record.get('output_format', 'webp') if previous else None
    rid = f'visual:{mid}:{trigger}'
    if prev_bytes:
        url = IMAGES_EDIT
        payload = {'model': IMAGE_MODEL, 'prompt': prompt, 'n': 1,
                   'images': [{'image_url': f'data:image/{prev_format};base64,' + base64.b64encode(prev_bytes).decode()}]}
    else:
        url = IMAGES_GENERATE
        payload = {'model': IMAGE_MODEL, 'prompt': prompt, 'n': 1, 'size': '1792x1024', 'output_format': 'webp'}
    record = {'trigger': trigger, 'prompt': prompt, 'revision': snap['revision'], 'tick': s['tick'], 'sol': s['sol'],
              'method': 'edit of previous illustration' if prev_bytes else 'generation', 'model': IMAGE_MODEL,
              'receipt_id': rid, 'label': 'AI illustration generated by muse-image-1.0 from recorded mission state. Not an observation.'}
    try:
        result, corr = _dispatch(store, rid, mid, IMAGE_MODEL, url, payload, IMAGE_USD_PER_IMAGE, transport, retry_503=2)
        data = (result.get('data') or [{}])[0]
        if not data.get('b64_json'):
            raise MediaError('Muse Image response contained no image data')
        raw = base64.b64decode(data['b64_json'])
        image = stamp(raw)
        record.update(classification='generated illustration, not evidence', stamped_label=STAMP, raw_sha256=hashlib.sha256(raw).hexdigest(),
                      status='generated', output_format=result.get('output_format', 'webp'), provider_created=result.get('created'),
                      usage=result.get('usage'), sha256=hashlib.sha256(image).hexdigest(), bytes=len(image), output_format_stored='webp', **corr)
    except Exception as exc:
        image = raw = None
        record.update(status='failed', error=f'{type(exc).__name__}: {exc}'[:600])
    with store.transaction() as db:
        db.add(Visual(id=rid, mission_id=mid, trigger=trigger, created=time.time(), image=image, raw_image=raw, record=record))
    return record


def pending_visual(store, mid='public'):
    """Next trigger that has no visual yet: genesis first, then completed jobs in completion order."""
    s = store.snapshot(mid)['state']
    if s['mode'] != 'meta':
        return None
    with store.transaction() as db:
        done = {v.trigger for v in db.scalars(select(Visual).where(Visual.mission_id == mid)).all()}
    if 'genesis' not in done:
        return 'genesis'
    for j in sorted((j for j in s['jobs'] if j['status'] == 'complete'), key=lambda j: j['completed_tick']):
        if 'job:' + j['id'] not in done:
            return 'job:' + j['id']
    return None


# ---------------------------------------------------------------- SAM 3.1 on HiRISE

def _label_value(label, key):
    m = re.search(rf'^\s*{re.escape(key)}\s*=\s*(-?[0-9.]+(?:[eE][-+]?[0-9]+)?)', label, re.M)
    if not m:
        raise MediaError(f'HiRISE label has no {key}')
    return float(m.group(1))


# Full-resolution crop for SAM when the image contains the site. Side length in full-resolution pixels: at the 0.5 m/pixel
# HiRISE map scale this is 512 m, wider than the 175.15 m one-sol survey drive in every direction from the site.
CROP_PX = 1024


def site_pixel(label, lat, lon_east):
    """0-based (line, sample) of a planetocentric lat / east lon in a HiRISE equirectangular RDR, from its label
    (PDS3 IMAGE_MAP_PROJECTION: line = LINE_PROJECTION_OFFSET - lat * MAP_RESOLUTION;
    sample = SAMPLE_PROJECTION_OFFSET + MAP_RESOLUTION * (lon - CENTER_LONGITUDE) * cos(CENTER_LATITUDE))."""
    res = _label_value(label, 'MAP_RESOLUTION')
    line = _label_value(label, 'LINE_PROJECTION_OFFSET') - lat * res
    sample = _label_value(label, 'SAMPLE_PROJECTION_OFFSET') + res * (lon_east - _label_value(label, 'CENTER_LONGITUDE')) * math.cos(math.radians(_label_value(label, 'CENTER_LATITUDE')))
    return line - 1, sample - 1


def fetch_file(url, path, transport=None):
    """Download a large file to disk once (streamed), then reuse it. Fails loud on any HTTP or size mismatch."""
    from pathlib import Path
    path = Path(path)
    if path.exists():
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.part')
    with httpx.Client(timeout=httpx.Timeout(60, read=300), follow_redirects=True, transport=transport) as c:
        with c.stream('GET', url) as r:
            r.raise_for_status()
            expected = int(r.headers['content-length']) if r.headers.get('content-length') else None
            size = 0
            with open(tmp, 'wb') as out:
                for part in r.iter_bytes(1 << 20):
                    out.write(part); size += len(part)
    if expected is not None and size != expected:
        tmp.unlink(missing_ok=True)
        raise MediaError(f'Incomplete download of {url}: {size} of {expected} bytes')
    tmp.replace(path)
    return path


def site_crop(label, jp2_path, lat, lon_east, side=CROP_PX):
    """Full-resolution window centred on the site, decoded from the JPEG2000 RDR (only the window is decoded).
    10-bit DN are stretched to 8 bits with the label's own display stretch (MRO:MINIMUM_STRETCH..MRO:MAXIMUM_STRETCH);
    null pixels (CORE_NULL) stay black. Returns (JPEG bytes, window record)."""
    import io
    import glymur
    import numpy as np
    from PIL import Image
    lines, samples = int(_label_value(label, 'LINES')), int(_label_value(label, 'LINE_SAMPLES'))
    line, sample = site_pixel(label, lat, lon_east)
    if not (0 <= line < lines and 0 <= sample < samples):
        raise MediaError(f'Mission site falls outside the image: line {line:.0f} of {lines}, sample {sample:.0f} of {samples}')
    half = side // 2
    r0, c0 = max(0, int(round(line)) - half), max(0, int(round(sample)) - half)
    r1, c1 = min(lines, r0 + side), min(samples, c0 + side)
    dn = glymur.Jp2k(str(jp2_path))[r0:r1, c0:c1].astype('float64')
    lo, hi = _label_value(label, 'MRO:MINIMUM_STRETCH'), _label_value(label, 'MRO:MAXIMUM_STRETCH')
    null = dn == _label_value(label, 'CORE_NULL')
    px = np.clip((dn - lo) / (hi - lo) * 255, 0, 255)
    px[null] = 0
    out = io.BytesIO()
    Image.fromarray(px.astype('uint8'), 'L').save(out, format='JPEG', quality=92)
    window = {'rows': [r0, r1], 'columns': [c0, c1], 'site_pixel': [round(line, 1), round(sample, 1)],
              'site_in_crop_px': [round(sample - c0, 1), round(line - r0, 1)], 'null_fraction': round(float(null.mean()), 4),
              'stretch_dn': [lo, hi], 'method': 'JPEG2000 region decode (glymur/OpenJPEG) at full resolution'}
    return out.getvalue(), window


def _segment(store, mid, prompt, image_url, transport=None, product=None):
    from meta_sam_parser import image_segmentation_format, CompletedOutcome, SegmentationBoxRecord, SegmentationMaskRecord, decode_mask_to_svg_path
    rid = f'sam:{product or HIRISE["product"]}:{prompt.replace(" ", "-")}'
    payload = {'model': SAM_MODEL, 'input': [{'type': 'message', 'role': 'user', 'content': [
        {'type': 'input_text', 'text': prompt}, {'type': 'input_image', 'image_url': image_url}]}]}
    result, corr = _dispatch(store, rid, mid, SAM_MODEL, ENDPOINT, payload, SAM_USD_PER_IMAGE, transport)
    text = ''.join(part.get('text', '') for o in result.get('output', []) if o.get('type') == 'message'
                   for part in o.get('content', []) if part.get('type') == 'output_text')
    lanes = [part for o in result.get('output', []) if o.get('type') == 'message' for part in o.get('content', []) if part.get('type') == 'output_text']
    if not lanes:
        # No output_text lane at all: the response shape differs from the SAM 3 protocol. Fail loud with the evidence.
        import json as _json
        shape = _json.dumps(result, default=str)[:20000]
        _update(store, rid, status='received; output not parsed', raw_response=shape)
        raise MediaError('SAM 3.1 response has no output_text lane; raw response stored on receipt ' + rid + ': ' + shape[:600])
    # An empty lane is a valid completed response with zero matches (SAM 3 protocol, github.com/meta-models/meta-sam, protocol/sam3.md).
    parser = image_segmentation_format().create_parser()
    parser.push(text)
    parsed = parser.finish(CompletedOutcome()).result
    boxes = {r.object_id: r for r in parsed.records if isinstance(r, SegmentationBoxRecord)}
    masks = {r.object_id: r for r in parsed.records if isinstance(r, SegmentationMaskRecord)}
    _update(store, rid, response_id=result.get('id'), response_status=result.get('status'), usage=result.get('usage'),
            objects=len(boxes), diagnostics=[str(d) for d in parsed.diagnostics][:10])
    objects = []
    for n, (oid, b) in enumerate(boxes.items()):
        m = masks.get(oid)
        objects.append({'object_id': oid, 'left': b.left, 'top': b.top, 'right': b.right, 'bottom': b.bottom,
                        'confidence': b.confidence, 'svg_path': decode_mask_to_svg_path(m.mask) if m and n < 300 else None,
                        'mask_origin': [m.bounds.left, m.bounds.top] if m else None})
    # The raw model output is kept so any result (including zero detections) can be re-checked.
    return {'prompt': prompt, 'receipt_id': rid, 'response_id': result.get('id'), 'raw_output_sha256': hashlib.sha256(text.encode()).hexdigest(),
            'raw_output': text[:500000], 'raw_output_chars': len(text), 'response_output_types': [o.get('type') for o in result.get('output', [])],
            'objects': objects, 'diagnostics': [str(d) for d in parsed.diagnostics][:10], **corr}


def analyze_site(store, mid='public', transport=None):
    """Segment the HiRISE browse image for each prompt and pin the result as evidence on the mission."""
    from .science import fetch, pin
    from PIL import Image
    import io
    from .conditions import SITE
    from .package import load
    img = site_image(SITE['latitude'], SITE['longitude_east'], load()['values']['mars.mean_radius_km'], transport)
    label_raw, retrieved = fetch(img['label'], 2_000_000)
    label = label_raw.decode('ascii', errors='replace')
    full_samples = _label_value(label, 'LINE_SAMPLES')
    full_lines = _label_value(label, 'LINES')
    map_scale = _label_value(label, 'MAP_SCALE')  # metres per pixel of the full-resolution product
    window = None
    if img['applies_to_site']:
        # The image contains the site: segment a full-resolution window centred on it (D13).
        from .science import CACHE
        jp2_url = img['label'][:-len('.LBL')] + '.JP2'
        jp2 = fetch_file(jp2_url, CACHE / 'hirise' / (img['product'] + '_RED.JP2'), transport)
        raw, window = site_crop(label, jp2, SITE['latitude'], SITE['longitude_east'])
        sam_image = 'data:image/jpeg;base64,' + base64.b64encode(raw).decode()
        # The exact JPEG SAM segmented is kept so the detections can be shown over it and re-checked.
        image_source = {'jp2_url': jp2_url, 'window': window, 'segmented_jpeg_b64': base64.b64encode(raw).decode()}
        m_per_px = map_scale
    else:
        raw, retrieved = fetch(img['browse'], 60_000_000)
        sam_image = img['browse']
        image_source = {'browse_url': img['browse']}
    with Image.open(io.BytesIO(raw)) as picture:  # not `img`: that name holds the chosen site image record
        width, height = picture.size
    if window is None:
        m_per_px = map_scale * full_samples / width
    results = []
    for prompt in SAM_PROMPTS:
        seg = _segment(store, mid, prompt, sam_image, transport, img['product'])
        for o in seg['objects']:
            w = (o['right'] - o['left']) * m_per_px
            h = (o['bottom'] - o['top']) * m_per_px
            o.update(width_m=round(w, 2), height_m=round(h, 2), equivalent_diameter_m=round(math.sqrt(max(w, 0) * max(h, 0)), 2))
        sizes = sorted(o['equivalent_diameter_m'] for o in seg['objects'])
        seg['summary'] = {'count': len(sizes), 'min_m': sizes[0] if sizes else None, 'median_m': sizes[len(sizes) // 2] if sizes else None,
                          'max_m': sizes[-1] if sizes else None}
        results.append(seg)
    record = {**img, 'url': img['page'], 'image_url': image_source.get('jp2_url', img['browse']), 'image_source': image_source, 'retrieved_at': retrieved,
              'status': 'orbital image segmented by sam-3.1', 'classification': 'model detection on observed imagery',
              'image_size_px': [width, height], 'full_product_px': [full_samples, full_lines], 'map_scale_m': map_scale,
              'browse_m_per_px': round(m_per_px, 3), 'segmented_m_per_px': round(m_per_px, 3),
              'resolution_limit': f'Objects smaller than about {round(2 * m_per_px, 1)} m cannot be resolved in the segmented image.',
              'supports': 'Count and size of boulders and impact craters SAM 3.1 detects in real HiRISE orbital imagery of Arcadia Planitia.',
              'use': 'Model detections, not ground truth. ' + ('The image footprint contains the mission site.' if img['applies_to_site'] else
                     f"PROXY IMAGE: {img['site_relation']}. Detections do not describe the mission site and must not be used to approve or plan site work."),
              'segmentations': results, 'transformation_version': 'sam-3.1-hirise-fullres-crop-1' if window else 'sam-3.1-hirise-browse-1',
              'summary': {r['prompt']: r['summary'] for r in results}}
    from .route import plan
    record['route'] = plan(width, height, m_per_px, results)
    vid = pin(store, img['source_id'], record, raw)
    with store.transaction() as db:
        m = store.row(db, mid)
        s = deepcopy(m.state)
        s['source_pins'][img['source_id']] = vid
        s['site_imagery'] = {'source_id': img['source_id'], 'product': img['product'], 'applies_to_site': img['applies_to_site'], 'site_relation': img['site_relation']}
        s['planning_needed'] = s['mode'] == 'meta' and not s.get('inference_stopped')
        from .engine import event
        route = record['route']
        survey = next(j for j in s['jobs'] if j['id'] == 'survey')
        if not img['applies_to_site']:
            event(s, 'Hazard route not applied', f"SAM ran on a proxy image ({img['site_relation']}); the survey is unchanged (D13).", 'survey')
        elif route.get('detour_factor') and survey['status'] in ('pending', 'blocked', 'review') and not survey.get('route'):
            # D13: hazard avoidance lengthens the survey drive.
            survey['route'] = {k: route[k] for k in ('detour_factor', 'route_m', 'straight_m', 'blocked_fraction')} | {'base_target': survey['target'], 'source_version': vid}
            survey['target'] = survey['target'] * route['detour_factor']
            survey['basis'] += f" Hazard-avoiding route: x{route['detour_factor']} (D13)."
            event(s, 'Survey route planned around hazards', f"A* route {route['route_m']} m vs {route['straight_m']} m straight across HiRISE {img['product']}; "
                  f"survey drive target now {survey['target']:.0f} m.", 'survey')
        elif not route.get('detour_factor'):
            event(s, 'Hazard route not found', route['status'] + '. Survey target unchanged; agents informed.', 'survey')
        event(s, 'Orbital imagery segmented', ', '.join(f"{r['summary']['count']} {r['prompt']}" for r in results)
              + f" detected by SAM 3.1 in HiRISE {img['product']} ({round(m_per_px, 2)} m/pixel; {img['site_relation']}).")
        store.save(db, m, s, {'kind': 'site-segmentation', 'version': vid})
    return vid


def site_analysis_due(store, mid='public'):
    s = store.snapshot(mid)['state']
    if s['mode'] != 'meta' or s.get('site_imagery'):
        return False
    # D13: orbital site characterization runs at genesis, before surface work.
    st = store.status('site-analysis')
    # A failed attempt is recorded and not retried automatically; `python -m mission.cli retry-site-analysis` clears it.
    return not st or bool(st.get('cleared_at'))

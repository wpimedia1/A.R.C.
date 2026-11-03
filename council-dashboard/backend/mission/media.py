"""Meta media model on real mission inputs.

- SAM 3.1 (sam-3.1): segmentation of a real HiRISE orbital image of Arcadia Planitia (public domain,
  NASA/JPL-Caltech/UArizona) for boulders and impact craters, run at genesis; detections route the survey (D13).
  Detections are model output on orbital imagery at the stated resolution, not ground truth.

Every request is recorded as an InferenceReceipt (status, HTTP status, x-request-id, cost) before and
after dispatch. Nothing is retried automatically.
"""
import base64
import hashlib
import math
import re
import time
from copy import deepcopy
import httpx
from .provider import credential, fingerprint, send, ProviderConfigError, ENDPOINT, SAM_MODEL, SAM_USD_PER_IMAGE
from .store import InferenceReceipt

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


def _dispatch(store, rid, mid, model, url, payload, price, transport=None):
    """Send one recorded request. Returns (json, correlation). Records failure and re-raises."""
    try:
        key, source = credential()
    except ProviderConfigError as exc:
        raise MediaError(str(exc)) from exc
    logged = dict(payload)
    _receipt(store, rid, mid, {'status': 'dispatched', 'model': model, 'endpoint': url, 'created_at': time.time(),
                               'request': logged, 'key_fingerprint': fingerprint(key), 'key_source': source,
                               'price_basis_usd': price})
    try:
        result, corr = send(payload, key, transport, timeout=300, url=url)
        try:
            _update(store, rid, status='received', received_at=time.time(), actual_usd=price, **corr)
        except Exception as exc:
            # The provider answered and was paid: a bookkeeping error must never discard the result.
            import logging
            logging.exception('Receipt update failed after a successful %s response', model)
            corr = {**corr, 'receipt_update_error': f'{type(exc).__name__}: {exc}'[:300]}
        return result, corr
    except httpx.HTTPStatusError as exc:
        _update(store, rid, status='failed', http_status=exc.response.status_code, request_id=exc.response.headers.get('x-request-id'),
                provider_error_message=exc.response.text.replace(key, '[redacted]')[:600])
        raise
    except Exception as exc:
        _update(store, rid, status='uncertain; no automatic retry', failure=type(exc).__name__)
        raise


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
    from .package import load
    clearance_m = load()['values']['rover.width_m'] / 2  # rover centre keeps half its width from any hazard
    record['route'] = plan(width, height, m_per_px, results, clearance_m)
    vid = pin(store, img['source_id'], record, raw)

    # New evidence is applied only between planning cycles (a plan in progress is never overwritten).
    store.commit_unclaimed(mid, lambda s: apply_site_analysis(s, img, record, vid), {'kind': 'site-segmentation', 'version': vid})
    return vid


def apply_site_analysis(s, img, record, vid):
    """Adopt a segmented site image into a mission: pin it, and apply its hazard route to the survey (D13)."""
    s['source_pins'][img['source_id']] = vid
    s['site_imagery'] = {'source_id': img['source_id'], 'product': img['product'], 'applies_to_site': img['applies_to_site'], 'site_relation': img['site_relation']}
    s['planning_needed'] = s['mode'] == 'meta' and not s.get('inference_stopped')
    from .engine import event, release
    route = record['route']
    results, m_per_px = record['segmentations'], record['segmented_m_per_px']
    survey = next(j for j in s['jobs'] if j['id'] == 'survey')
    if not img['applies_to_site']:
        event(s, 'Hazard route not applied', f"SAM ran on a proxy image ({img['site_relation']}); the survey is unchanged (D13).", 'survey')
    elif not route.get('detour_factor'):
        # D13: no traversable route across the analysed site image. The survey may not run until new evidence clears it.
        survey['route_blocked'] = {'status': route['status'], 'source_version': vid}
        if survey['status'] in ('running', 'review'):
            survey.pop('authorization', None)
            release(s, survey, 'blocked', 'No hazard-free route: ' + route['status'])
        event(s, 'Survey blocked: no hazard-free route', route['status'] + f" in HiRISE {img['product']} (D13). The survey cannot start.", 'survey')
    elif survey['status'] in ('pending', 'blocked', 'review') and not survey.get('route'):
        # D13: hazard avoidance lengthens the survey drive.
        survey.pop('route_blocked', None)
        survey['route'] = {k: route[k] for k in ('detour_factor', 'route_m', 'straight_m', 'blocked_fraction', 'clearance_m')} | {'base_target': survey['target'], 'source_version': vid}
        survey['target'] = survey['target'] * route['detour_factor']
        survey['basis'] += f" Hazard-avoiding route: x{route['detour_factor']} (D13)."
        event(s, 'Survey route planned around hazards', f"A* route {route['route_m']} m vs {route['straight_m']} m straight across HiRISE {img['product']}, "
              f"keeping {route['clearance_m']} m (half the rover width) from detected hazards; survey drive target now {survey['target']:.0f} m.", 'survey')
    event(s, 'Orbital imagery segmented', ', '.join(f"{r['summary']['count']} {r['prompt']}" for r in results)
          + f" detected by SAM 3.1 in HiRISE {img['product']} ({round(m_per_px, 2)} m/pixel; {img['site_relation']}).")


def site_analysis_due(store, mid='public'):
    s = store.snapshot(mid)['state']
    if s['mode'] != 'meta' or s.get('site_imagery'):
        return False
    # D13: orbital site characterization runs at genesis, before surface work.
    st = store.status('site-analysis')
    # A failed attempt is recorded and not retried automatically; `python -m mission.cli retry-site-analysis` clears it.
    return not st or bool(st.get('cleared_at'))

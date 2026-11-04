import time
from mission import science
from mission.store import SourceVersion
from conftest import make_store

def test_unchanged_evidence_cannot_rewrite_its_original_version(tmp_path,request):
    store=make_store(tmp_path,request);store.initialize()
    first=science.pin(store,'rems',{'observation_time':'2026-03-21','retrieved_at':1},b'measurement')
    second=science.pin(store,'rems',{'observation_time':'2099-01-01','retrieved_at':time.time()},b'measurement')
    assert first==second
    with store.transaction() as db:assert db.get(SourceVersion,first).record['observation_time']=='2026-03-21'

def test_rems_retains_quality_flags_and_filters_invalid_pressure():
    fields=[('PRESSURE',1,8),('PRESSURE_UNCERTAINTY',9,8),('PS_CONFIDENCE_LEVEL',17,2),('LMST',19,10)]
    xml='<Product xmlns="http://pds.nasa.gov/pds4/pds/v1">'+''.join(f'<Field_Character><name>{name}</name><field_location>{loc}</field_location><field_length>{length}</field_length></Field_Character>' for name,loc,length in fields)+'</Product>'
    invalid=b' -9999.0     1.00112:00:00  '
    valid=b'   815.0     1.20112:05:00  '
    rows=[invalid]*300+[valid]
    result=science.parse_rems(xml.encode(),b'\n'.join(rows))
    assert len(result['observations'])==1
    point=result['observations'][0]
    assert point['row']==301 and point['pressure_pa']==815 and point['quality_flag']=='01'
    assert result['use']=='Off-site context only; no Arcadia weather transfer applied'


def test_one_publisher_failure_does_not_skip_other_products(tmp_path,request,monkeypatch):
    """Fault injection only; test versions cannot be used as live scientific evidence."""
    from mission import telemetry,schedule,terrain
    store=make_store(tmp_path,request)
    def fail(*args):raise RuntimeError('injected publisher outage')
    monkeypatch.setattr(telemetry,'ingest_weather',fail)
    monkeypatch.setattr(schedule,'ingest_architecture',lambda s:'test-architecture')
    monkeypatch.setattr(science,'ingest_document',lambda s,k,u:'test-'+k)
    monkeypatch.setattr(science,'ingest_rems',lambda s:'test-rems')
    monkeypatch.setattr(science,'ingest_swim',lambda s:'test-swim')
    monkeypatch.setattr(science,'ingest_radar',lambda s:'test-radar')
    monkeypatch.setattr(terrain,'arcadia',lambda s:'test-mola')
    monkeypatch.setattr(science,'ingest_ground',lambda s:'test-ground')
    monkeypatch.setattr(science,'ingest_well_reference',lambda s:'test-well-reference')
    versions=science.ingest(store,adopt=False)
    assert 'msl-weather' not in versions and versions['mola-arcadia']=='test-mola'
    assert len(versions)==9
    assert 'injected publisher outage' in store.status('science:msl-weather')['error']


def test_ground_rejects_wrong_projection_before_downloading_image(monkeypatch):
    import pytest
    from mission import media
    # Malformed metadata fixture, never mission evidence.
    monkeypatch.setattr(media,'site_image',lambda *args:{'applies_to_site':True,'label':'https://test.invalid/label'})
    monkeypatch.setattr(media,'site_pixel',lambda *args:(1000,1000))
    monkeypatch.setattr(media,'_label_value',lambda *args:10)
    monkeypatch.setattr(science,'fetch',lambda *args:(b'test-only label',0))
    with pytest.raises(ValueError,match='outside PDS image projection'):
        science.ingest_ground(None)

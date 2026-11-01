import json
import time
import hashlib
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

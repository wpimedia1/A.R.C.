import json
import pytest
from mission.telemetry import parse_weather

def test_weather_orders_actual_sols_preserves_missing_and_source_rows():
    raw=json.dumps({'soles':[
        {'sol':'4','terrestrial_date':'2026-01-04','min_temp':'-70','max_temp':'--','pressure':'777','local_uv_irradiance_index':'Moderate'},
        {'sol':'1','terrestrial_date':'2026-01-01','min_temp':'-80','max_temp':'-5','pressure':'--'}]}).encode()
    result=parse_weather(raw)
    a,b=result['daily_observations']
    assert (a['sol'],b['sol'])==(1,4)
    assert a['source_row']==2 and b['source_row']==1
    assert a['pressure_pa'] is None and b['air_max_c'] is None
    assert result['summary']['air_max_c']['latest_observed_at']=='2026-01-01'
    assert result['observation_time']=='2026-01-04'
    assert 'No transfer' in result['use']

def test_weather_rejects_invalid_payload_instead_of_fabricating_records():
    with pytest.raises(ValueError):parse_weather(b'{"soles":[]}')
    with pytest.raises(ValueError):parse_weather(b'{"soles":[{"sol":"1","terrestrial_date":"not a date"}]}')

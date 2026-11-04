from mission.climate import parse
from mission.nowcast import resolve_basis
from mission.store import SourceVersion
from mission.engine import InvalidAction
from conftest import make_store
import pytest


def ascii_fixture():
    # Explicit parser fixture, not a published mission observation.
    header='### MCD_v6.2\n### Ls 270.0deg. Latitude 40.05451N. Longitude 190.28958E. Altitude 1.0 m ALS.\n'
    return (header+'### Column 2 is Temperature (K)\n0 160\n24 160\n'
            +'### Column 2 is Surface temperature (K)\n0 150\n24 150\n'
            +'### Column 2 is Surface pressure (Pa)\n0 900\n24 900\n').encode()


def test_parse_model_preserves_units_and_classification():
    d=parse(ascii_fixture())
    assert d['classification']=='climate-model' and d['model_version']=='6.2'
    assert d['variables']['air_temperature_k']['unit']=='K'
    assert d['coordinates']['longitude_east']==190.28958
    with pytest.raises(ValueError):parse(ascii_fixture().replace(b'0 160',b'0 nan'))
    with pytest.raises(ValueError):parse(ascii_fixture().replace(b'Surface pressure (Pa)',b'Wrong variable'))


def test_agent_climate_citation_resolves_exact_version(tmp_path,request):
    store=make_store(tmp_path,request);record=parse(ascii_fixture())
    with store.transaction() as db:db.add(SourceVersion(id='climate-fixture:1',source_id='arcadia-climate',record=record))
    refs=[{'observation_id':'climate-fixture:1','variable':'air_temperature_k','interpretation':'Test interpretation'}]
    b=resolve_basis(store,refs)[0]
    assert b['kind']=='climate-model' and b['value']['minimum']==160 and b['record_hash']
    with pytest.raises(InvalidAction):resolve_basis(store,[{**refs[0],'variable':'internal_battery_temperature'}])

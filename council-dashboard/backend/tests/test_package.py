import json
import math
import pytest
import mission.package as package
from mission.package import load, require_approved, PackageError


def edit(dir_, fn):
    path = dir_ / 'arcadia-mars-v1.json'
    pkg = json.loads(path.read_text(encoding='utf-8'))
    fn(pkg)
    path.write_text(json.dumps(pkg), encoding='utf-8')


def test_every_parameter_resolves_with_provenance(approved_package):
    pkg = load()
    assert set(pkg['values']) == set(pkg['parameters'])
    for name, p in pkg['parameters'].items():
        if p['classification'] == 'published':
            assert p['source'] in pkg['sources'] and p['quote'] and p['locator'] and p['unit'], name
        assert math.isfinite(pkg['values'][name])


def test_derived_values_are_recomputed_from_inputs(approved_package):
    v = load()['values']
    assert v['excavator.mining_rate_kg_h'] == pytest.approx(v['excavator.min_rate_kg_per_day'] / v['excavator.mining_h_per_day'])
    assert v['water.rodwell_kwh_per_kg'] == pytest.approx(v['rodwell.power_kw'] * 24 / v['rodwell.water_kg_per_day'])


def test_missing_quote_is_rejected(approved_package):
    edit(approved_package, lambda p: p['parameters']['power.fsp_output_kwe'].pop('quote'))
    with pytest.raises(PackageError, match='quote'):
        load()


def test_unknown_formula_name_is_rejected(approved_package):
    def bad(p):
        p['parameters']['excavator.mining_rate_kg_h']['formula'] = 'excavator.min_rate_kg_per_day/hours'
    edit(approved_package, bad)
    with pytest.raises(PackageError):
        load()


def test_unapproved_decision_blocks_mission(approved_package):
    edit(approved_package, lambda p: p['operator_decisions']['D9_rodwell_establishment'].update(approved=False))
    with pytest.raises(PackageError, match='D9'):
        require_approved(load())


def test_shipped_package_lists_its_unapproved_decisions():
    pkg = json.loads((package.PACKAGES.parent / 'packages' / 'arcadia-mars-v1.json').read_text(encoding='utf-8')) if False else None
    from conftest import REAL_PACKAGES
    real = json.loads((REAL_PACKAGES / 'arcadia-mars-v1.json').read_text(encoding='utf-8'))
    for key, d in real['operator_decisions'].items():
        assert isinstance(d['approved'], bool), key

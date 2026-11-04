"""Versioned, explicitly hypothetical Arcadia mission. SI units unless stated."""
import hashlib
import json
from .provider import DIRECTOR_MODEL, SPECIALIST_MODEL

SOURCES = [
    {'id': 'nasa-dra', 'title': 'Human Exploration of Mars DRA 5.0', 'url': 'https://ntrs.nasa.gov/citations/20090012109', 'version': '2009', 'passage': 'The DRA is not a formal plan, but provides a vision and context', 'supports': 'Reference architecture; predeployment before crew arrival.', 'classification': 'published estimate'},
    {'id': 'nasa-m2m', 'title': 'Moon to Mars Architecture, Revision C', 'url': 'https://ntrs.nasa.gov/citations/20250010956', 'version': '2025 revision C', 'passage': None, 'supports': 'Architecture context; not a site-specific settlement authorization.', 'classification': 'published estimate'},
    {'id': 'swim', 'title': 'Subsurface Water Ice Mapping', 'url': 'https://swim.psi.edu/', 'version': 'catalog', 'passage': None, 'supports': 'Regional ice prospecting context; no local recoverable yield measurement.', 'classification': 'observed'},
    {'id': 'mola', 'title': 'USGS Mars MGS MOLA DEM, 463 m', 'url': 'https://astrogeology.usgs.gov/search/map/mars_mgs_mola_dem_463m', 'version': '2003-03-21', 'passage': None, 'supports': 'Regional topography; cannot establish rover-scale obstacle clearance.', 'classification': 'observed'},
    {'id': 'rems', 'title': 'Curiosity REMS observations', 'url': 'https://atmos.nmsu.edu/data_and_services/atmospheres_data/MARS/curiosity/rems.html', 'version': 'archive catalog', 'passage': None, 'supports': 'Off-site Gale crater context only. Not current Arcadia weather.', 'classification': 'observed'},
]

ROLES = [
    {'id': 'director', 'name': 'Mission director', 'model': DIRECTOR_MODEL, 'job': 'Reconciles independent assessments and sets the work priority.'},
    {'id': 'survey', 'name': 'Survey lead', 'model': SPECIALIST_MODEL, 'job': 'Authorizes the site survey.'},
    {'id': 'construction', 'name': 'Construction lead', 'model': SPECIALIST_MODEL, 'job': 'Authorizes trench excavation, shielding and configured payload offload; assigns compatible equipment.'},
    {'id': 'resources', 'name': 'Resource lead', 'model': SPECIALIST_MODEL, 'job': 'Authorizes Rodwell drilling and water production.'},
    {'id': 'assurance', 'name': 'Assurance review', 'model': SPECIALIST_MODEL, 'job': 'Reviews every authorized work order onboard before it starts and can hold it; cannot authorize work.'},
    {'id': 'power', 'name': 'Power lead', 'model': SPECIALIST_MODEL, 'job': 'Authorizes fission power deployment. The unit is designed for 10 years without maintenance (NASA FSP); capacity loss is handled by replanning.'},
    {'id': 'logistics', 'name': 'Logistics and finance lead', 'model': SPECIALIST_MODEL, 'job': 'Manages configured service work and spare manifests; orders complete replacement robots on the next Earth-Mars window (D12).'},
]

def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)

def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()

PACKAGE_ID = 'arcadia-mars-v1'

# Display-only layout (metres, local frame). Not used by any physical calculation.
LAYOUT = {'rover-1': [-10, 0, 6], 'excavator-1': [-2, 0, 14], 'excavator-2': [8, 0, 14], 'rodwell-1': [12, 0, -6],
          'fsp-1': [-14, 0, -12], 'habitat-1': [3, 0, 4]}


def specification(package_id=PACKAGE_ID, overrides=None):
    """Mission specification built only from a validated, fully approved environment package."""
    from .package import load, require_approved
    pkg = load(package_id, overrides)
    require_approved(pkg)
    v = pkg['values']
    if pkg['environment'] != 'mars':
        from .environments import construction_spec
        return construction_spec(pkg)
    tick_h = v['mars.day_length_h'] / 24  # D7: one tick = 1/24 sol

    def ref(*names):
        return list(names)

    assets = [
        {'id': 'rover-1', 'kind': 'rover', 'name': 'Survey rover (Perseverance-class)', 'mass_kg': v['rover.mass_kg'],
         'grid_power_kw': 0.0, 'rate_per_h': v['rover.max_drive_m_per_sol'] / v['mars.day_length_h'], 'rate_unit': 'm',
         'battery_wh': v['rover.battery_wh'], 'soc_wh': v['rover.battery_wh'], 'charging': False,
         'energy_wh_per_unit': v['rover.drive_wh_per_m'], 'generator_w': v['rover.power_w'], 'charge_kw': 0.0,
         'parameters': ref('rover.mass_kg', 'rover.power_w', 'rover.max_drive_m_per_sol', 'mars.day_length_h'),
         'note': 'Published 2,408 Wh battery and 110 W MMRTG; reference mobility energy from NASA speed/power bounds. Full housekeeping and terrain-dependent loads are not validated.'},
        *[{'id': f'excavator-{i}', 'kind': 'excavator', 'name': f'Excavator {i} (RASSOR 2.0-class)', 'mass_kg': v['excavator.mass_kg'],
           'grid_power_kw': 0.0, 'rate_per_h': v['excavator.mining_rate_kg_h'], 'rate_unit': 'kg',
           # D18: works on its battery; recharges from the fission grid. Starts the mission fully charged.
           'battery_wh': v['excavator.battery_wh'], 'soc_wh': v['excavator.battery_wh'], 'energy_wh_per_kg': v['excavator.energy_wh_per_kg'],
           'charge_kw': v['excavator.charge_kw'], 'charging': False,
           'parameters': ref('excavator.mass_kg', 'excavator.mining_rate_kg_h', 'excavator.battery_wh', 'excavator.energy_wh_per_kg', 'excavator.charge_kw'),
           'note': 'Works on its battery (1,410 Wh, 0.761 Wh per kg excavated) and recharges from the fission grid (D18).'} for i in (1, 2)],
        {'id': 'rodwell-1', 'kind': 'rodwell', 'name': 'Rodwell ice-melt water well', 'mass_kg': None,
         'grid_power_kw': v['rodwell.power_kw'], 'rate_per_h': v['rodwell.water_kg_per_day'] / 24, 'rate_unit': 'kg',
         'parameters': ref('rodwell.power_kw', 'rodwell.water_kg_per_day', 'drill.rop_min_mm_s'),
         'note': 'RedWater-class drill and Rodwell. No published Mars hardware mass; capital cost is not estimated (missing value).'},
        {'id': 'fsp-1', 'kind': 'power', 'name': 'Fission surface power unit', 'mass_kg': v['power.fsp_mass_max_kg'],
         'grid_power_kw': 0.0, 'output_kw': v['power.fsp_output_kwe'], 'rate_per_h': None, 'rate_unit': None,
         'parameters': ref('power.fsp_output_kwe', 'power.fsp_mass_max_kg', 'fsp.deploy_total_h'), 'note': 'No grid power until the deployment job completes (D8).'},
        {'id': 'habitat-1', 'kind': 'habitat', 'name': 'Common Habitat', 'mass_kg': v['habitat.mass_kg'],
         'grid_power_kw': 0.0, 'rate_per_h': None, 'rate_unit': None, 'parameters': ref('habitat.mass_kg'),
         'note': 'Landed beside the trench; offload not modeled (D4).'},
    ]
    assets[0]['operating_envelope'] = {
        'battery_temperature': {'minimum': v['rover.battery_min_c'], 'maximum': v['rover.battery_max_c'], 'unit':'degC', 'source':'rover-battery2021'},
        'processor_temperature': {'minimum': v['rad750.min_c'], 'maximum': v['rad750.max_c'], 'unit':'degC', 'source':'rad750-bae2025'},
        'processor_total_dose': {'minimum':0.0, 'maximum':v['rad750.total_dose_rad_si'], 'unit':'rad(Si)', 'source':'rad750-bae2025'}}
    # D14: mobile robots carry the series failure rate of the reference planetary rover model; others do not fail.
    for a in assets:
        a.update(available=True, position=LAYOUT[a['id']],
                 failure_rate_per_h=v['reliability.mobile_robot_failures_per_h'] if a['kind'] in ('rover', 'excavator') else None)
    jobs = [
        {'id': 'power', 'kind': 'commissioning', 'title': 'Deploy and commission fission power', 'owner': 'power', 'asset_kinds': ['power'],
         'target': v['fsp.deploy_total_h'], 'unit': 'h', 'output': 'power_commissioning_h', 'dependencies': [],
         'rate_per_asset_h': 1.0, 'power_per_asset_kw': 0.0, 'effect': {'grid_capacity_kw': v['power.fsp_output_kwe']},
         'parameters': ref('fsp.deploy_total_h', 'power.fsp_output_kwe'),
         'basis': 'D8: summed lunar deployment timeline (Oleson et al. 2022, Table 3.6); powered by lander and rover in the source.'},
        {'id': 'drill', 'kind': 'drilling', 'title': 'Drill the Rodwell through the overburden', 'owner': 'resources', 'asset_kinds': ['rodwell'],
         'target': v['ice.overburden_max_m'], 'unit': 'm', 'output': 'drilled_m', 'dependencies': ['survey', 'power'],
          'rate_per_asset_h': v['ice.overburden_max_m'] / v['drill.hours_through_overburden'], 'power_per_asset_kw': v['redwater.design_power_upper_kw'],
          'power_scope': '15 kW whole-system design allocation from RedWater 2019; not measured drilling-only demand',
         'parameters': ref('ice.overburden_max_m', 'drill.rop_min_mm_s', 'drill.hours_through_overburden', 'redwater.design_power_upper_kw'),
          'basis': 'D9: tested penetration rate (Stolov 2026); power reserved at RedWater 2019 whole-system upper design estimate.'},
        {'id': 'survey', 'kind': 'survey', 'title': 'Survey the work site', 'owner': 'survey', 'asset_kinds': ['rover'],
         'target': v['rover.max_drive_m_per_sol'], 'unit': 'm', 'output': 'survey_m', 'dependencies': [],
         'parameters': ref('rover.max_drive_m_per_sol'), 'basis': 'D3: one sol of driving at the published record distance.'},
        {'id': 'trench', 'kind': 'excavation', 'title': 'Excavate the habitat trench', 'owner': 'construction', 'asset_kinds': ['excavator'],
         'target': v['habitat.trench_mass_kg'], 'unit': 'kg', 'output': 'trench_kg', 'dependencies': ['survey', 'power'],
         'parameters': ref('habitat.trench_mass_kg'), 'basis': 'Trench 1.58 m deep, one habitat diameter wide, one habitat long.'},
        {'id': 'shielding', 'kind': 'excavation', 'title': 'Cover the habitat with regolith shielding', 'owner': 'construction',
         'asset_kinds': ['excavator'], 'target': v['habitat.shield_mass_kg'], 'unit': 'kg', 'output': 'shield_kg',
         'dependencies': ['trench'], 'parameters': ref('habitat.shield_mass_kg'), 'basis': '20 g/cm2 over the full habitat surface (upper bound).'},
        {'id': 'water', 'kind': 'water', 'title': 'Produce water from Arcadia ice', 'owner': 'resources', 'asset_kinds': ['rodwell'],
         'target': v['water.target_kg'], 'unit': 'kg', 'output': 'water_kg', 'dependencies': ['drill', 'power', 'well-establish'],
         'parameters': ref('water.target_kg', 'water.rodwell_kwh_per_kg', 'rodwell.control_reserve_kg'), 'basis': 'D1/D21 conditional design study: withdraw only after establishing the separately accounted liquid reserve; published effective energy operating point, not measured site yield.'},
    ]
    jobs.insert(-1,{'id':'well-establish','kind':'well-establishment','title':'Establish and qualify the well reserve',
        'owner':'resources','asset_kinds':['rodwell'],'target':v['rodwell.control_reserve_kg'],'unit':'kg',
        'output':'well_conditioned_kg','dependencies':['drill','power'],
        'rate_per_asset_h':v['rodwell.water_kg_per_day']/24,'power_per_asset_kw':v['rodwell.power_kw'],
        'parameters':ref('rodwell.control_reserve_kg','rodwell.establishment_effective_kwh','water.rodwell_kwh_per_kg'),
        'basis':'D21 scenario model: condition a one-control-interval reserve using the published effective steady-state energy per kg as a startup extrapolation. This is not calibrated startup performance. Reserve mass is not delivered water.'})
    positions = {'power': [-14, 0, -12], 'drill': [12, 0, -6], 'survey': [-6, 0, 4], 'trench': [3, 0, 10], 'shielding': [3, 0, 10], 'water': [9, 0, -5]}
    for j in jobs:
        j['position'] = positions['water' if j['id']=='well-establish' else j['id']]
    capital = [{'asset_id': a['id'], 'mass_kg': a['mass_kg'],
                'amount_usd': None if a['mass_kg'] is None else a['mass_kg'] * v['cost.landed_usd_per_kg'],
                'basis': 'mass x cost.landed_usd_per_kg (D5)' if a['mass_kg'] is not None else 'missing: no published hardware mass'}
               for a in assets]
    # Templates agents may instantiate as new work (gap 25). Each is an existing job definition with its published basis.
    by = {j['id']: j for j in jobs}
    templates = [
        {**{k:by['well-establish'][k] for k in ('kind','owner','asset_kinds','target','unit','output','rate_per_asset_h','power_per_asset_kw','parameters','position')},
         'template_id':'well-recondition','title':'Recondition the retained well reserve','dependencies':['drill','power'],
         'basis':'D21: restore qualification after interrupted heat, reusing retained water and separately accounting additional energy.'},
        {**{k: by['water'][k] for k in ('kind', 'owner', 'asset_kinds', 'target', 'unit', 'output', 'rate_per_asset_h', 'power_per_asset_kw', 'parameters', 'position') if k in by['water']},
         'template_id': 'water-batch', 'title': 'Produce an additional water batch', 'dependencies': ['drill', 'power', 'well-establish'],
         'basis': 'Another production run at the D1 water target from the existing Rodwell.'},
        {**{k: by['survey'][k] for k in ('kind', 'owner', 'asset_kinds', 'target', 'unit', 'output', 'parameters', 'position') if k in by['survey']},
         'template_id': 'survey-extension', 'title': 'Extend the site survey by one sol of driving', 'dependencies': [],
         'basis': 'D3: one additional sol of driving at the published record distance.'},
    ]
    spec = {'version': pkg['id'] + '/engine-11-water-establishment', 'package_id': pkg['id'], 'package_hash': pkg['hash'], 'environment': pkg['environment'],
            'tick_hours': tick_h, 'tick_seconds': v['mars.sol_s'] / 24, 'seconds_per_minute': 60, 'seconds_per_hour': 3600, 'wh_per_kwh': 1000, 'standby_max_ticks': 72,
            'ops_usd_per_tick': v['cost.ops_usd_per_sol'] / 24,
            'assets': assets, 'jobs': jobs, 'templates': templates, 'capital': capital,
            'water_model':{'reserve_kg':v['rodwell.control_reserve_kg'],'effective_kwh_per_kg':v['water.rodwell_kwh_per_kg'],
                'assumption':'D21_water_establishment_model','classification':'conditional scenario model',
                'limits':'Startup extrapolates the reference steady-state effective energy. Local ice concentration and actual liquid phase are uninstrumented. No physical readiness certification.',
                'parameters':ref('rodwell.control_reserve_kg','rodwell.establishment_effective_kwh','water.rodwell_kwh_per_kg')},
            'readiness': {'jobs': ['power', 'survey', 'drill', 'trench', 'shielding', 'well-establish', 'water'],
                          'description': 'Conditional scenario readiness: power, survey, trench, shielding, drilling, qualified well reserve and delivered-water target complete under the recorded model assumptions.'},
            'decisions': pkg['decisions'], 'conflicts': pkg['conflicts'],
            'parameters': {n: {**pkg['parameters'][n], 'value': pkg['values'][n]} for n in pkg['parameters']},
            'sources': pkg['sources']}
    spec['hash'] = digest(spec)
    return spec


def draw(seed, tick, asset_id):
    """Deterministic uniform number in [0, 1) for reproducible failure draws (D14)."""
    return int(hashlib.sha256(f'{seed}:{tick}:{asset_id}'.encode()).hexdigest()[:13], 16) / 16 ** 13

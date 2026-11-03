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
    {'id': 'construction', 'name': 'Construction lead', 'model': SPECIALIST_MODEL, 'job': 'Authorizes trench excavation and regolith shielding, and assigns the excavators.'},
    {'id': 'resources', 'name': 'Resource lead', 'model': SPECIALIST_MODEL, 'job': 'Authorizes Rodwell drilling and water production.'},
    {'id': 'assurance', 'name': 'Assurance review', 'model': SPECIALIST_MODEL, 'job': 'Reviews every authorized work order onboard before it starts and can hold it; cannot authorize work.'},
    {'id': 'power', 'name': 'Power lead', 'model': SPECIALIST_MODEL, 'job': 'Authorizes fission power deployment. The unit is designed for 10 years without maintenance (NASA FSP); capacity loss is handled by replanning.'},
    {'id': 'logistics', 'name': 'Logistics and finance lead', 'model': SPECIALIST_MODEL, 'job': 'Orders replacement robots for failed units on the next Earth-Mars window and books their landed cost (D12).'},
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
    tick_h = v['mars.day_length_h'] / 24  # D7: one tick = 1/24 sol
    from .package import PackageError
    if v['battery_swap.time_s'] > tick_h * 3600:
        raise PackageError('A battery swap (D21) must complete within one step')
    if v['ice.ice_below_overburden_m'] <= 0:
        # The drill target (the overburden) must end inside the regional ice layer (Bramson et al. 2015), or the Rodwell
        # has no ice to melt.
        raise PackageError('Drill target is not above the base of the Arcadia ice layer (ice.ice_below_overburden_m <= 0)')

    def ref(*names):
        return list(names)

    assets = [
        {'id': 'rover-1', 'kind': 'rover', 'name': 'Survey rover (Perseverance-class)', 'mass_kg': v['rover.mass_kg'],
         'grid_power_kw': 0.0, 'rate_per_h': v['rover.max_drive_m_per_sol'] / v['mars.day_length_h'], 'rate_unit': 'm',
         'tid_gy': v['rover.computer_tid_krad_si'] * 10, 'dose_gy': 0.0, 'dose_gy_per_h': v['mars.surface_dose_ugy_per_day'] / 1e6 / 24,  # µGy per Earth day -> Gy per hour
         'rtg_battery_wh': v['rover.battery_wh'], 'rtg_soc_wh': v['rover.battery_wh'], 'drive_w': v['rover.drive_power_max_w'], 'rtg_w': v['rover.power_w'],
         'parameters': ref('rover.mass_kg', 'rover.power_w', 'rover.max_drive_m_per_sol', 'mars.day_length_h', 'rover.battery_wh', 'rover.drive_power_max_w', 'rover.computer_tid_krad_si', 'mars.surface_dose_ugy_per_day', 'rover.computer_dose_life_days'),
         'note': 'Self-powered: MMRTG (about 110 W) and its own batteries (2,408 Wh); draws nothing from the grid. Driving draws under 200 W (NASA); the batteries cover the difference and the MMRTG recharges them.'},
        *[{'id': f'excavator-{i}', 'kind': 'excavator', 'name': f'Excavator {i} (RASSOR 2.0-class)', 'mass_kg': v['excavator.mass_kg'],
           'grid_power_kw': 0.0, 'rate_per_h': v['excavator.mining_rate_kg_h'], 'rate_unit': 'kg',
           # D18: works on its battery; recharges from the fission grid. Starts the mission fully charged.
           'battery_wh': v['excavator.battery_wh'], 'soc_wh': v['excavator.battery_wh'], 'energy_wh_per_kg': v['excavator.energy_wh_per_kg'],
           'charge_kw': v['excavator.charge_kw'], 'charging': False, 'spare_soc_wh': v['excavator.battery_wh'], 'spare_charging': False,
           'parameters': ref('excavator.mass_kg', 'excavator.mining_rate_kg_h', 'excavator.battery_wh', 'excavator.energy_wh_per_kg', 'excavator.charge_kw', 'battery_swap.time_s'),
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
         'rate_per_asset_h': v['ice.overburden_max_m'] / v['drill.hours_through_overburden'], 'power_per_asset_kw': None,
         'parameters': ref('ice.overburden_max_m', 'drill.rop_min_mm_s', 'drill.hours_through_overburden', 'ice.layer_base_mode_m', 'ice.ice_below_overburden_m', 'ice.excess_fraction_max'),
         'basis': 'D9: lowest tested rate of penetration (Stolov et al. 2026). The target, the deepest reported overburden, ends inside the regional ice layer (base mode 42 m, up to 75% ice by volume; Bramson et al. 2015). Drilling-only power is not published: the drill holds all unallocated grid capacity while it runs.'},
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
         'target': v['water.target_kg'], 'unit': 'kg', 'output': 'water_kg', 'dependencies': ['drill', 'power'],
         'parameters': ref('water.target_kg', 'water.rodwell_kwh_per_kg'), 'basis': 'D1: Rodwell melt extraction after drilling (D9). Melt start-up time not published.'},
    ]
    positions = {'power': [-14, 0, -12], 'drill': [12, 0, -6], 'survey': [-6, 0, 4], 'trench': [3, 0, 10], 'shielding': [3, 0, 10], 'water': [9, 0, -5]}
    for j in jobs:
        j['position'] = positions[j['id']]
    capital = [{'asset_id': a['id'], 'mass_kg': a['mass_kg'],
                'amount_usd': None if a['mass_kg'] is None else a['mass_kg'] * v['cost.landed_usd_per_kg'],
                'basis': 'mass x cost.landed_usd_per_kg (D5)' if a['mass_kg'] is not None else 'missing: no published hardware mass'}
               for a in assets]
    # Templates agents may instantiate as new work (gap 25). Each is an existing job definition with its published basis.
    by = {j['id']: j for j in jobs}
    templates = [
        {**{k: by['water'][k] for k in ('kind', 'owner', 'asset_kinds', 'target', 'unit', 'output', 'rate_per_asset_h', 'power_per_asset_kw', 'parameters', 'position') if k in by['water']},
         'template_id': 'water-batch', 'title': 'Produce an additional water batch', 'dependencies': ['drill', 'power'],
         'basis': 'Another production run at the D1 water target from the existing Rodwell.'},
        {**{k: by['survey'][k] for k in ('kind', 'owner', 'asset_kinds', 'target', 'unit', 'output', 'parameters', 'position') if k in by['survey']},
         'template_id': 'survey-extension', 'title': 'Extend the site survey by one sol of driving', 'dependencies': [],
         'basis': 'D3: one additional sol of driving at the published record distance.'},
    ]
    spec = {'version': pkg['id'] + '/engine-7-autonomous', 'package_id': pkg['id'], 'package_hash': pkg['hash'], 'environment': pkg['environment'],
            'tick_hours': tick_h, 'tick_seconds': v['mars.sol_s'] / 24, 'seconds_per_minute': 60, 'seconds_per_hour': 3600, 'wh_per_kwh': 1000, 'standby_max_ticks': 72,
            'ops_usd_per_tick': v['cost.ops_usd_per_sol'] / 24,
            'assets': assets, 'jobs': jobs, 'templates': templates, 'capital': capital,
            'readiness': {'jobs': ['power', 'survey', 'drill', 'trench', 'shielding', 'water'],
                          'description': 'Power commissioned, site surveyed, trench and shielding complete, Rodwell drilled and water target reached.'},
            'decisions': pkg['decisions'], 'conflicts': pkg['conflicts'],
            'parameters': {n: {**pkg['parameters'][n], 'value': pkg['values'][n]} for n in pkg['parameters']},
            'sources': pkg['sources']}
    spec['hash'] = digest(spec)
    return spec


def draw(seed, tick, asset_id):
    """Deterministic uniform number in [0, 1) for reproducible failure draws (D14)."""
    return int(hashlib.sha256(f'{seed}:{tick}:{asset_id}'.encode()).hexdigest()[:13], 16) / 16 ** 13

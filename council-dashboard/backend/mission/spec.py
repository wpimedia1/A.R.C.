"""Versioned, explicitly hypothetical Arcadia mission. SI units unless stated."""
import hashlib
import json

VERSION = 'arcadia-robotic-1.0'
SOURCES = [
    {'id': 'nasa-dra', 'title': 'Human Exploration of Mars DRA 5.0', 'url': 'https://ntrs.nasa.gov/citations/20090012109', 'version': '2009', 'passage': 'The DRA is not a formal plan, but provides a vision and context', 'supports': 'Reference architecture; predeployment before crew arrival.', 'classification': 'published estimate'},
    {'id': 'nasa-m2m', 'title': 'Moon to Mars Architecture, Revision C', 'url': 'https://ntrs.nasa.gov/citations/20250010956', 'version': '2025 revision C', 'passage': None, 'supports': 'Architecture context; not a site-specific settlement authorization.', 'classification': 'published estimate'},
    {'id': 'swim', 'title': 'Subsurface Water Ice Mapping', 'url': 'https://swim.psi.edu/', 'version': 'catalog', 'passage': None, 'supports': 'Regional ice prospecting context; no local recoverable yield measurement.', 'classification': 'observed'},
    {'id': 'mola', 'title': 'USGS Mars MGS MOLA DEM, 463 m', 'url': 'https://astrogeology.usgs.gov/search/map/mars_mgs_mola_dem_463m', 'version': '2003-03-21', 'passage': None, 'supports': 'Regional topography; cannot establish rover-scale obstacle clearance.', 'classification': 'observed'},
    {'id': 'rems', 'title': 'Curiosity REMS observations', 'url': 'https://atmos.nmsu.edu/data_and_services/atmospheres_data/MARS/curiosity/rems.html', 'version': 'archive catalog', 'passage': None, 'supports': 'Off-site Gale crater context only. Not current Arcadia weather.', 'classification': 'observed'},
]

def parameter(value, unit, justification, origin='scenario assumption'):
    return {'value': value, 'unit': unit, 'classification': origin, 'justification': justification, 'source_id': 'scenario-v1'}

PARAMETERS = {
    'sol_seconds': parameter(88775.244, 's', 'Conventional mean solar day used by this simulator.', 'scenario assumption'),
    'ticks_per_sol': parameter(24, 'ticks', 'Discrete approximation; each tick is 1/24 of a sol.'),
    'water_target': parameter(100, 'kg', 'Demonstration reserve threshold, not a crew life-support requirement.'),
    'water_yield': parameter(.25, 'kg/kg', 'Hypothetical recoverable water per kg feedstock; not SWIM-measured.'),
    'initial_energy': parameter(600, 'kWh', 'Landed battery reserve for the scenario.'),
    'initial_power': parameter(4, 'kW', 'Temporary landed power source.'),
    'deployed_power': parameter(18, 'kW', 'Scenario power unit after commissioning; technology not certified.'),
    'operating_budget': parameter(250000, '2026 USD', 'Scenario spending authority excluding launch, R&D and capital.'),
    'capital_allocation': parameter(5000000, '2026 USD', 'Illustrative landed equipment allocation; not a NASA cost estimate.'),
    'battery_capacity': parameter(800, 'kWh', 'Storage ceiling; generated surplus is curtailed.'),
}

ROLES = [
    {'id': 'director', 'name': 'Mission director', 'model': 'muse-wonder-1.0', 'job': 'Sequence milestones and resolve cross-team resource conflicts.'},
    {'id': 'survey', 'name': 'Survey lead', 'model': 'muse-spark-1.3', 'job': 'Inspect routes and reduce terrain uncertainty.'},
    {'id': 'construction', 'name': 'Construction lead', 'model': 'muse-spark-1.3', 'job': 'Prepare foundations and assemble the habitat.'},
    {'id': 'resources', 'name': 'Resource lead', 'model': 'muse-spark-1.3', 'job': 'Excavate feedstock and produce the water reserve.'},
    {'id': 'power', 'name': 'Power and maintenance lead', 'model': 'muse-spark-1.3', 'job': 'Commission power and maintain equipment.'},
    {'id': 'logistics', 'name': 'Logistics and finance lead', 'model': 'muse-spark-1.3', 'job': 'Reconcile inventory, reservations and spending.'},
]

# All engineering quantities below are scenario assumptions, not extracted specifications.
JOBS = [
    dict(id='survey', title='Survey the landing zone', owner='survey', asset='rover', duration=2, power_kw=2, cost=3000, inputs={'energy_kwh': 8}, outputs={}, dependencies=[], position=[-5, 0, 4]),
    dict(id='power', title='Commission the power unit', owner='power', asset='utility', duration=3, power_kw=3, cost=15000, inputs={'energy_kwh': 12, 'materials_kg': 30}, outputs={}, dependencies=['survey'], position=[6, 0, -4]),
    dict(id='excavate', title='Excavate the resource test site', owner='resources', asset='excavator', duration=4, power_kw=10, cost=12000, inputs={'energy_kwh': 50}, outputs={'feedstock_kg': 500, 'regolith_kg': 300}, dependencies=['power'], position=[-6, 0, -2]),
    dict(id='water', title='Build the water reserve', owner='resources', asset='processor', duration=4, power_kw=12, cost=9000, inputs={'energy_kwh': 55, 'feedstock_kg': 500}, outputs={}, dependencies=['excavate'], position=[5, 0, 2]),
    dict(id='habitat', title='Prepare the first habitat', owner='construction', asset='builder', duration=6, power_kw=12, cost=25000, inputs={'energy_kwh': 80, 'regolith_kg': 200, 'materials_kg': 100}, outputs={}, dependencies=['excavate'], position=[0, 0, 0]),
    dict(id='verify', title='Verify outpost readiness', owner='logistics', asset='rover', duration=1, power_kw=1, cost=1000, inputs={'energy_kwh': 2}, outputs={}, dependencies=['water', 'habitat'], position=[0, 0, 3]),
    dict(id='maintenance', title='Service the excavation robot', owner='power', asset='utility', duration=2, power_kw=3, cost=2000, inputs={'energy_kwh': 6, 'spares': 1}, outputs={}, dependencies=['power'], position=[-6, 0, -2]),
]

def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)

def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()

def specification():
    result = {'version': VERSION, 'title': 'Arcadia robotic preparation', 'region': 'Arcadia Planitia',
              'site': {'latitude': 40, 'longitude': -170, 'classification': 'scenario assumption'},
              'parameters': PARAMETERS, 'jobs': JOBS, 'roles': ROLES,
              'job_parameter_origin': 'All job durations, costs, positions, power and material quantities are scenario assumptions. Costs are 2026 USD with ±50% illustrative uncertainty.',
              'conflicts': ['DRA 5.0 and Revision C are different architectural generations; this scenario does not assert compatibility of their vehicle designs.',
                            'REMS measures Gale crater, not Arcadia. No local weather transfer model is applied.',
                            'SWIM indicates regional ice consistency, not verified mine yield.'],
              'requirements': [{'id': 'ready-power', 'text': 'Commission the scenario power unit', 'source_ids': ['scenario-v1', 'nasa-m2m']},
                               {'id': 'ready-water', 'text': 'Store at least 100 kg of water', 'source_ids': ['scenario-v1', 'swim']},
                               {'id': 'ready-habitat', 'text': 'Complete habitat preparation', 'source_ids': ['scenario-v1', 'nasa-dra']},
                               {'id': 'ready-check', 'text': 'Pass deterministic readiness verification', 'source_ids': ['scenario-v1']}]}
    result['hash'] = digest(result)
    return result

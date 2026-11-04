"""Optional, explicit lumped equipment thermal/housekeeping model.

Heat balance: C dT/dt = P - K(T-Ta) - epsilon sigma A(T^4-Tr^4).
NASA thermal-control reference: https://www.nasa.gov/smallsat-institute/sst-soa/thermal-control/
sigma: NIST CODATA, https://physics.nist.gov/cgi-bin/cuu/Value?sigma
No thermal coefficients, ambient readings or household loads are supplied by default.
"""
from copy import deepcopy
import json
from pathlib import Path
from .procedures import quantity, fail
from .spec import digest

REFERENCES=json.loads(Path(__file__).with_name('physics-references.json').read_text(encoding='utf-8'))
SIGMA = REFERENCES['stefan-boltzmann']['value']  # Rounded CODATA value, with actual retrieved source hash.
UNITS = {'heat_capacity':'J/K', 'conductance':'W/K', 'radiating_area':'m2', 'emissivity':'1',
         'initial_temperature':'K', 'ambient_temperature':'K', 'radiative_temperature':'K',
         'housekeeping':'W', 'heater_max':'W', 'heater_setpoint':'K', 'heat_fraction':'1', 'absorbed_solar':'W'}


def configure(s, profiles):
    from .engine import asset_by_id
    if not isinstance(profiles, dict) or not profiles:
        fail('Equipment physics requires asset profiles')
    for aid, profile in profiles.items():
        a = asset_by_id(s, aid)
        if aid in s.get('equipment_physics', {}):
            fail('Physics design is immutable once configured; fork to change it')
        if not a.get('battery_wh'):
            fail('This thermal/electrical model requires an explicitly modeled onboard battery')
        if not isinstance(profile, dict) or set(profile)-{'climate_boundary'} != set(UNITS) | {'variable'}:
            fail('Thermal profile must supply all heat-balance inputs and its component variable')
        variable = profile['variable']
        if variable not in a.get('operating_envelope', {}) or a['operating_envelope'][variable]['unit'] != 'degC':
            fail('Thermal variable must match a published component temperature envelope')
        values = {k:quantity(s, profile[k], unit, k in ('heat_capacity','initial_temperature','ambient_temperature','radiative_temperature','heater_setpoint')) for k,unit in UNITS.items()}
        if values['emissivity'] > 1 or values['heat_fraction'] > 1:
            fail('Emissivity and heat fraction must be between zero and one')
        boundary=profile.get('climate_boundary')
        evidence=None
        if boundary:
            if not isinstance(boundary,dict) or set(boundary)!={'version_id','variable'} or boundary['variable']!='air_temperature_k':
                fail('Climate boundary must select a pinned MCD air-temperature series')
            evidence=s.get('physics_evidence',{}).get(boundary['version_id'])
            if not evidence or s.get('source_pins',{}).get('arcadia-climate')!=boundary['version_id']:
                fail('Climate boundary does not resolve to the mission-pinned MCD source')
            if not s.get('environment') or s['environment'].get('clock',{}).get('site_ltst_h') is None:
                fail('Climate coupling requires a mission local-solar-time clock')
        s.setdefault('equipment_physics', {})[aid] = {'profile':deepcopy(profile), 'profile_hash':digest(profile),
            'temperature_k':values['initial_temperature'], 'classification':'calculated engineering scenario',
            'cumulative_housekeeping_wh':0.0, 'cumulative_heater_wh':0.0, 'history':[], 'climate_evidence':deepcopy(evidence),
            'model_references':deepcopy(REFERENCES), 'input_source_versions':deepcopy(s.get('source_pins',{}))}


def solve_temperature(initial, seconds, capacity, conductance, ambient, area, emissivity, radiative, power):
    """Monotone implicit heat balance, stable for long mission steps; residual in joules.

    This is a single backward-Euler interval, not a resolved multi-node thermal model.
    """
    def residual(t):
        return capacity*(t-initial)-seconds*(power-conductance*(t-ambient)-emissivity*SIGMA*area*(t**4-radiative**4))
    lo = 0.0; hi = max(initial, ambient, radiative) + max(0.0,power)*seconds/capacity + 1.0
    for _ in range(80):
        mid=(lo+hi)/2
        if residual(mid)>0:hi=mid
        else:lo=mid
    value=(lo+hi)/2
    return value,residual(value)


def advance(s, hours):
    from .engine import asset_by_id
    for aid, model in s.get('equipment_physics', {}).items():
        a=asset_by_id(s,aid)
        if not a['available']:
            continue
        p={k:v['value'] for k,v in model['profile'].items() if k in UNITS}
        boundary=None
        if model.get('climate_evidence'):
            from .engine import sim_unix
            from .conditions import mars_clock
            local_time=mars_clock(sim_unix(s))['site_ltst_h']
            evidence=model['climate_evidence']
            points=evidence['points']
            left,right=points[0],points[-1]
            for a0,b0 in zip(points,points[1:]):
                if a0['local_time_h']<=local_time<=b0['local_time_h']:
                    left,right=a0,b0;break
            weight=(local_time-left['local_time_h'])/(right['local_time_h']-left['local_time_h'])
            p['ambient_temperature']=left['value']+weight*(right['value']-left['value'])
            boundary={'source_version':model['profile']['climate_boundary']['version_id'],'content_hash':evidence['content_hash'],
                      'local_time_h':local_time,'ambient_temperature_k':p['ambient_temperature'], 'bracketing_samples':[left,right],
                      'interpretation':'Pinned site climatology drives the lumped environmental boundary; not a current sensor reading'}
        seconds=hours*3600
        initial=model['temperature_k']
        # Heater thermostat requests only the power needed to reach its setpoint
        # in this implicit interval. Housekeeping has priority over heating.
        setpoint=p['heater_setpoint']
        loss=p['conductance']*(setpoint-p['ambient_temperature'])+p['emissivity']*SIGMA*p['radiating_area']*(setpoint**4-p['radiative_temperature']**4)
        wanted=max(0.0,min(p['heater_max'],p['heat_capacity']*(setpoint-initial)/seconds+loss-p['housekeeping']*p['heat_fraction']-p['absorbed_solar']))
        house_wh=min(a['soc_wh'],p['housekeeping']*hours)
        heater_wh=min(max(0.0,a['soc_wh']-house_wh),wanted*hours)
        a['soc_wh']-=house_wh+heater_wh
        power=house_wh/hours*p['heat_fraction']+heater_wh/hours+p['absorbed_solar']
        temperature,residual=solve_temperature(initial,seconds,p['heat_capacity'],p['conductance'],p['ambient_temperature'],p['radiating_area'],p['emissivity'],p['radiative_temperature'],power)
        model['temperature_k']=temperature
        model['cumulative_housekeeping_wh']+=house_wh;model['cumulative_heater_wh']+=heater_wh
        model['housekeeping_unserved_wh']=max(0.0,p['housekeeping']*hours-house_wh)
        receipt={'tick':s['tick'],'input_temperature_k':initial,'temperature_k':temperature,'housekeeping_wh':house_wh,
                 'heater_wh':heater_wh,'housekeeping_unserved_wh':model['housekeeping_unserved_wh'],
                 'thermal_balance_residual_j':residual,'profile_hash':model['profile_hash'],
                 'classification':'calculated engineering scenario; not a sensor measurement',
                 'climate_boundary':boundary,
                 'transformation_version':'lumped-implicit-heat-balance-1'}
        model['history'].append(receipt)
        # Every worker step is persisted as a full revision. Keep the current-state
        # working set bounded; earlier receipts remain in those append-only revisions.
        model['history']=model['history'][-24:]
        variable=model['profile']['variable']
        s.setdefault('equipment_conditions',{}).setdefault(aid,{})[variable]={'value':temperature-273.15,'unit':'degC',
            'classification':'calculated engineering scenario','basis':'Lumped heat balance '+model['profile_hash'],
            'calculation':receipt}
        s['onboard_consumed_wh']=s.get('onboard_consumed_wh',0.0)+house_wh+heater_wh

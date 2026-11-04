"""Additional sourced operating envelopes. These are explicit construction studies, not copied Mars environments."""
from copy import deepcopy


def construction_spec(pkg):
    from .spec import digest
    v=pkg['values']; moon=pkg['environment']=='moon'
    if pkg['environment'] not in ('moon','earth'):raise ValueError('Unsupported construction environment')
    assets=[]
    for i in (1,2):
        assets.append({'id':f'excavator-{i}','name':f'RASSOR-class excavator {i}','kind':'excavator','mass_kg':v['excavator.mass_kg'],
                       'grid_power_kw':0.0,'rate_per_h':v['excavator.mining_rate_kg_h'],'rate_unit':'kg',
                       'battery_wh':v['excavator.battery_wh'],'soc_wh':v['excavator.battery_wh'],'energy_wh_per_kg':v['excavator.energy_wh_per_kg'],
                       'charge_kw':v['excavator.charge_kw'],'charging':False,'available':True,'position':[i*2,0,0],
                       'failure_rate_per_h':v['reliability.mobile_robot_failures_per_h'],
                       'parameters':['excavator.mass_kg','excavator.mining_rate_kg_h','excavator.battery_wh','excavator.energy_wh_per_kg'],
                       'note':'Published RASSOR reference operating point. Earth package is a laboratory calibration study; field throughput requires soil/gravity validation.'})
    power={'id':'power-1','name':'Lunar fission surface power' if moon else 'Allocated laboratory electrical supply','kind':'power',
           'mass_kg':v['power.fsp_mass_max_kg'] if moon else None,'grid_power_kw':0.0,'output_kw':v['power.fsp_output_kwe'],
           'rate_per_h':None,'rate_unit':None,'available':True,'position':[-2,0,0],'failure_rate_per_h':None,
           'parameters':['power.fsp_output_kwe'],'note':'NASA lunar design reference' if moon else 'Laboratory power allocation equal to the reference power system rating; not a utility measurement or hardware mass.'}
    assets.append(power)
    jobs=[{'id':'power','title':'Commission reference power' if moon else 'Authorize laboratory power allocation','kind':'commissioning','owner':'power',
           'asset_kinds':['power'],'target':v['fsp.deploy_total_h'] if moon else 1.0,'unit':'h','output':'commissioning_h','dependencies':[],
           'rate_per_asset_h':1.0,'power_per_asset_kw':0.0,'parameters':['fsp.deploy_total_h'] if moon else [],
           'effect':{'grid_capacity_kw':v['power.fsp_output_kwe']},'position':[-2,0,0],
           'basis':'NASA lunar deployment timeline' if moon else 'One mission step to authorize an already available laboratory supply; scenario protocol, not installation duration.'},
          {'id':'excavate','title':'Prepare habitat footprint' if moon else 'Run reference excavation batch','kind':'excavation','owner':'construction',
           'asset_kinds':['excavator'],'target':v['habitat.trench_mass_kg'] if moon else v['excavator.min_rate_kg_per_day'],
           'unit':'kg','output':'excavated_kg','dependencies':['power'],'parameters':['habitat.trench_mass_kg'] if moon else ['excavator.min_rate_kg_per_day'],
           'position':[0,0,0],'basis':'Lunar habitat-footprint study' if moon else 'One published RASSOR daily batch as the calibration objective.'}]
    spec={'version':pkg['id']+'/construction-1','package_id':pkg['id'],'package_hash':pkg['hash'],'environment':pkg['environment'],
          'tick_hours':1.0,'tick_seconds':3600.0,'seconds_per_minute':60,'seconds_per_hour':3600,'wh_per_kwh':1000,'standby_max_ticks':72,
          'ops_usd_per_tick':0.0,'assets':assets,'jobs':jobs,'templates':[],
          'readiness':{'jobs':['power','excavate'],'description':'Construction study objective met; not human-arrival readiness.'},
          'capital':[], 'decisions':pkg['decisions'],'conflicts':pkg['conflicts'],
          'financial_scope':'Financial estimation excluded for this construction envelope; zero booked cost does not mean free operations.',
          'time_basis':'One Earth hour per step; sol field is a 24-step mission-day counter, not a lunar solar day.',
          'parameters':{n:{**pkg['parameters'][n],'value':v[n]} for n in pkg['parameters']},'sources':pkg['sources']}
    spec['hash']=digest(spec)
    return spec

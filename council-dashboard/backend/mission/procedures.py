"""Resource-conserving service/offload work orders. No default hardware or durations.

An operator supplies a versioned engineering configuration in a private experiment.
Agents may select that configuration, but cannot invent its design inputs or spares.
All execution uses the normal job reservations, assurance and persisted step loop.
"""
import math
from copy import deepcopy
from .spec import digest


def fail(message):
    from .engine import InvalidAction
    raise InvalidAction(message)


def quantity(s, item, unit, positive=False):
    if not isinstance(item, dict) or item.get('unit') != unit:
        fail('Engineering quantity requires unit ' + unit)
    value = item.get('value')
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0 or (positive and value == 0):
        fail('Engineering quantity must be finite and ' + ('positive' if positive else 'nonnegative'))
    origin = item.get('origin')
    known = set(s['spec']['sources']) | set(s.get('source_pins', {})) | {s['spec']['package_id']}
    if origin not in ('observed', 'published estimate', 'calculated', 'scenario assumption'):
        fail('Engineering quantity requires an explicit origin classification')
    if not isinstance(item.get('justification'), str) or not item['justification'].strip():
        fail('Engineering quantity requires an applicability justification')
    if origin == 'scenario assumption':
        if item.get('approved') is not True:
            fail('Scenario engineering inputs need explicit operator approval')
    elif item.get('source_id') not in known or not item.get('locator'):
        fail('Engineering input must resolve a pinned/package source and passage locator')
    if origin == 'calculated' and (not item.get('formula') or not item.get('inputs')):
        fail('Calculated engineering inputs require their formula and inputs')
    return float(value)


def configure(s, config):
    """Install an explicit design study; called only by owned experiment configuration.

    Inventory is a manifest of individually identified items. Reconfiguration cannot
    reset consumed spares or charging state after the first procedure is authorized.
    """
    from .engine import asset_by_id
    if s.get('procedure_configuration') or any(j.get('procedure') for j in s['jobs']):
        fail('Procedure configuration is immutable once installed; fork before changing the design')
    if not isinstance(config, dict) or set(config) != {'profiles', 'inventory', 'service_equipment'}:
        fail('Procedure configuration requires profiles, inventory and service_equipment')
    if not isinstance(config['profiles'], list) or not 1 <= len(config['profiles']) <= 24:
        fail('Provide one to 24 procedure profiles')
    if not isinstance(config['inventory'], list) or len(config['inventory']) > 1000:
        fail('Inventory must be a bounded manifest')
    if not isinstance(config['service_equipment'], dict):
        fail('Service equipment must map existing asset IDs to explicit capabilities')
    equipment = {}
    for aid, declaration in config['service_equipment'].items():
        asset_by_id(s, aid)
        if not isinstance(declaration, dict) or not declaration.get('interface') or not declaration.get('justification'):
            fail('Service equipment requires a compatible interface and justification')
        if declaration.get('approved') is not True:
            fail('Service-equipment design assignment requires explicit operator approval')
        equipment[aid] = deepcopy(declaration)
    profiles = {}
    for p in config['profiles']:
        if not isinstance(p, dict) or p.get('kind') not in ('repair', 'battery-swap', 'battery-charge', 'offload'):
            fail('Procedure kind must be repair, battery-swap, battery-charge or offload')
        pid = p.get('id')
        if not isinstance(pid, str) or not pid.strip() or pid in profiles:
            fail('Procedure profile IDs must be nonempty and unique')
        target = asset_by_id(s, p.get('target_id'))
        if not p.get('interface') or not p.get('title'):
            fail('Procedure requires a title and hardware interface')
        if not isinstance(p.get('stages'), list) or not 1 <= len(p['stages']) <= 16:
            fail('Procedure requires one to 16 bounded stages')
        for stage in p['stages']:
            if not isinstance(stage,dict) or not stage.get('name'):
                fail('Each stage needs a name')
            quantity(s, stage.get('duration'), 'h', True)
            quantity(s, stage.get('grid_power'), 'kW')
        if len({x['name'] for x in p['stages']})!=len(p['stages']):
            fail('Procedure stage names must be unique')
        if not math.isfinite(sum(x['duration']['value'] for x in p['stages'])) or not math.isfinite(sum(x['duration']['value']*x['grid_power']['value'] for x in p['stages'])):
            fail('Procedure totals exceed the numerical execution domain')
        if p['kind'] == 'repair' and not p.get('component'):
            fail('Repair must identify the failed component; whole-unit availability is insufficient diagnosis')
        if p['kind'] == 'battery-swap' and not target.get('battery_wh'):
            fail('Battery swap requires a battery-powered target')
        if p['kind'] == 'battery-charge':
            efficiency=quantity(s,p.get('charge_efficiency'),'1',True)
            if efficiency>1:fail('Charging efficiency cannot exceed one')
        if p['kind'] == 'offload':
            if target['kind'] != 'habitat' or target.get('mass_kg') is None:
                fail('Offload requires a known payload mass')
            if quantity(s, p.get('rated_payload'), 'kg', True) < target['mass_kg']:
                fail('Offload equipment is rated below the payload mass')
            if p.get('initial_location') != 'lander':
                fail('Offload must start with the payload on its lander')
            for key in ('support_verified', 'stability_verified', 'attachment_verified'):
                if p.get(key) is not True:
                    fail('Offload design must explicitly verify ' + key)
            if not p.get('verification_basis'):
                fail('Offload needs a documented structural/stability/attachment verification basis')
            lift=p.get('lifting',{})
            units={'gravity':'m/s2','travel':'m','speed':'m/s','reach':'m','restoring_moment':'N m',
                   'structural_moment_limit':'N m','cable_load_limit':'N','braking_capacity':'W','safety_factor':'1'}
            if set(lift)!=set(units)|{'motion_stage'}:
                fail('Offload requires its lifting geometry, load limits, braking and motion stage')
            values={k:quantity(s,lift.get(k),unit,k in ('gravity','speed','safety_factor')) for k,unit in units.items()}
            if values['safety_factor']<1:
                fail('Offload safety factor must be at least one')
            force=target['mass_kg']*values['gravity']
            moment=force*values['reach'];factored=moment*values['safety_factor']
            if values['restoring_moment']<factored or values['structural_moment_limit']<factored:
                fail('Offload overturning/structural moment exceeds the declared design limit')
            if values['cable_load_limit']<force*values['safety_factor']:
                fail('Offload cable load exceeds its design limit')
            if values['braking_capacity']<force*values['speed']:
                fail('Offload descent power exceeds braking capacity')
            stage=next((x for x in p['stages'] if x['name']==lift['motion_stage']),None)
            if stage is None or stage['duration']['value']*3600<values['travel']/values['speed']:
                fail('Offload motion time is shorter than travel divided by speed')
            rotation=p.get('rotation',{})
            rotation_units={'initial_angle':'deg','final_angle':'deg','angular_speed':'deg/s','cg_offset':'m','torque_limit':'N m'}
            if set(rotation)!=set(rotation_units)|{'rotation_stage'}:
                fail('Offload requires its orientation, rotation rate, center-of-gravity offset and torque limit')
            rv={k:quantity(s,rotation[k],unit,k=='angular_speed') for k,unit in rotation_units.items()}
            if max(rv['initial_angle'],rv['final_angle'])>90 or rv['final_angle']<rv['initial_angle']:
                fail('This offload model supports gravity-lowering rotation from vertical toward horizontal, zero to 90 degrees')
            low,high=sorted((rv['initial_angle'],rv['final_angle']))
            peak_sine=1.0 if low<=90<=high else max(math.sin(math.radians(low)),math.sin(math.radians(high)))
            torque=force*rv['cg_offset']*peak_sine*values['safety_factor']
            rotation_seconds=abs(rv['final_angle']-rv['initial_angle'])/rv['angular_speed']
            rotation_stage=next((x for x in p['stages'] if x['name']==rotation['rotation_stage']),None)
            if rv['torque_limit']<torque:fail('Offload rotation torque exceeds the declared design limit')
            if rotation_stage is None or rotation_stage['duration']['value']*3600<rotation_seconds:
                fail('Offload rotation time is shorter than angle divided by angular speed')
            rotation_braking=force*rv['cg_offset']*peak_sine*math.radians(rv['angular_speed'])
            braking=force*values['speed']+rotation_braking if rotation['rotation_stage']==lift['motion_stage'] else max(force*values['speed'],rotation_braking)
            if values['braking_capacity']<braking:fail('Combined offload motion exceeds braking capacity')
            p={**p,'calculation':{'payload_force_n':force,'overturning_moment_nm':moment,'factored_moment_nm':factored,
                 'minimum_motion_seconds':values['travel']/values['speed'],'descent_braking_w':force*values['speed'],
                 'factored_rotation_torque_nm':torque,'minimum_rotation_seconds':rotation_seconds,
                 'scope':'Static lowering/rotation design bounds and staged kinematics; not flexible-body, wind or certified structural analysis'}}
        profiles[pid] = deepcopy(p)
    inventory = {}
    for item in config['inventory']:
        if not isinstance(item,dict):fail('Inventory entries must be individually identified items')
        iid = item.get('id')
        if not isinstance(iid, str) or not iid or iid in inventory or item.get('kind') not in ('module', 'battery') or not item.get('interface'):
            fail('Inventory needs unique serial IDs, kinds and interfaces')
        asset_by_id(s, item.get('compatible_asset_id'))
        if not item.get('manifest_basis') or item.get('approved') is not True:
            fail('Added spare inventory requires an approved manifest basis')
        if item['kind'] == 'battery':
            cap = quantity(s, item.get('capacity'), 'Wh', True)
            charge = quantity(s, item.get('initial_charge'), 'Wh')
            if charge > cap:
                fail('Spare charge exceeds capacity')
            item = {**item, 'capacity_wh': cap, 'soc_wh': charge}
        if item.get('capital_cost') is not None:
            quantity(s,item['capital_cost'],'USD')
            if not isinstance(item.get('currency_year'),int) or not item.get('cost_scope'):
                fail('Priced inventory needs a currency year and cost scope')
        inventory[iid] = {**deepcopy(item), 'status': 'stored', 'reserved_by': None}
    from .physics import REFERENCES
    s['procedure_configuration'] = {'hash': digest(config), 'profiles': profiles, 'equipment': equipment,
                                    'input_source_versions':deepcopy(s.get('source_pins',{})), 'reference_documents':deepcopy(REFERENCES),
                                    'installed_tick': s['tick'], 'scope': 'Explicit operator engineering study; not hardware certification'}
    s['inventory'] = inventory
    for item in inventory.values():
        cost=item.get('capital_cost',{}).get('value') if item.get('capital_cost') is not None else None
        if cost is None:s['capital_unestimated'].append('spare '+item['id'])
        else:s['capital_usd']+=cost
        s['ledger'].append({'tick':s['tick'],'kind':'spare-manifest','asset_id':item['compatible_asset_id'],'spare_id':item['id'],
             'amount_usd':cost,'currency_year':item.get('currency_year'),'scope':item.get('cost_scope'),
             'basis':deepcopy(item.get('capital_cost')) if cost is not None else 'No priced spare manifest; cost unestimated, not zero'})
    for p in profiles.values():
        if p['kind'] == 'offload':
            if any(j['id'] == 'shielding' and j['done'] > 0 for j in s['jobs']):
                fail('Cannot move an already shielded habitat back onto a lander')
            asset_by_id(s, p['target_id'])['location'] = 'lander'
            asset_by_id(s, p['target_id'])['orientation_deg']=p['rotation']['initial_angle']['value']
            asset_by_id(s, p['target_id'])['descent_remaining_m']=p['lifting']['travel']['value']
            s.setdefault('unfulfilled_payloads',{})[p['target_id']]='Requires configured offload to prepared site'
            s['milestones']['ready']=False;s['readiness_tick']=None
    from .engine import event
    event(s, 'Engineering procedures configured', s['procedure_configuration']['hash'])


def create(s, profile_id, service_ids, spare_id, actor, summary):
    """Create a work order; normal start/assurance is still mandatory."""
    from .engine import asset_by_id, busy_assets, event
    config = s.get('procedure_configuration', {})
    profile = config.get('profiles', {}).get(profile_id)
    if not profile:
        fail('No operator-configured procedure profile: ' + str(profile_id))
    if not isinstance(summary, str) or not summary.strip():
        fail('Procedure needs a public rationale')
    if not isinstance(service_ids, list) or not service_ids or len(service_ids) != len(set(service_ids)):
        fail('Procedure requires distinct service equipment')
    target = asset_by_id(s, profile['target_id'])
    if profile['kind']!='battery-charge' and any(o['asset_id']==target['id'] and o['status']=='in transit' for o in s.get('orders',[])):
        fail('A complete replacement is already in transit; service cannot silently supersede that commitment')
    if target['id'] in service_ids or (profile['kind']!='battery-charge' and (target['id'] in busy_assets(s) or target.get('charging'))):
        fail('Target must be stopped and cannot service itself')
    if profile['kind']!='battery-charge' and any(j.get('procedure', {}).get('target_id') == target['id'] and j.get('procedure',{}).get('kind')!='battery-charge' and j['status'] != 'complete' for j in s['jobs']):
        fail('An unfinished procedure already owns this target')
    for aid in service_ids:
        a = asset_by_id(s, aid)
        capability = config['equipment'].get(aid, {})
        if not a['available'] or capability.get('interface') != profile['interface']:
            fail('Service equipment is unavailable or has an incompatible interface')
        if a.get('charging') or aid in busy_assets(s):
            fail('Service equipment is already reserved or charging')
    spare = None
    if profile['kind'] in ('repair', 'battery-swap', 'battery-charge'):
        spare = s.get('inventory', {}).get(spare_id)
        expected = 'battery' if profile['kind'] in ('battery-swap','battery-charge') else 'module'
        if not spare or spare['kind'] != expected or spare['status'] != 'stored' or spare['reserved_by']:
            fail('A compatible, unreserved spare is required')
        if spare['compatible_asset_id'] != target['id'] or spare['interface'] != profile['interface']:
            fail('Spare interface/asset mismatch')
        if profile['kind'] == 'repair':
            if target['available'] or target.get('failed_component') != profile['component'] or spare.get('component') != profile['component']:
                fail('Repair must match the diagnosed failed component and spare module')
        elif spare['capacity_wh'] != target['battery_wh']:
            fail('Replacement battery capacity does not match the installed battery design')
    elif spare_id is not None:
        fail('Offload does not consume a repair spare')
    if profile['kind'] == 'battery-swap' and spare['soc_wh'] <= target['soc_wh']:
        fail('Replacement pack must contain more usable energy than the installed pack')
    if profile['kind']=='battery-charge' and spare['soc_wh']>=spare['capacity_wh']:
        fail('Spare battery is already full')
    if profile['kind'] == 'offload' and target.get('location') != 'lander':
        fail('Payload is not on its lander')
    jid = 'procedure-' + str(1 + sum('procedure' in j for j in s['jobs']))
    hours = sum(x['duration']['value'] for x in profile['stages'])
    peak = max(x['grid_power']['value'] for x in profile['stages'])
    dependencies = ['power', 'trench'] if profile['kind'] == 'offload' else ['power']
    dependencies = [x for x in dependencies if any(j['id'] == x for j in s['jobs'])]
    record = {'profile_id': profile_id, 'profile_hash': digest(profile), 'configuration_hash': config['hash'],
              'kind': profile['kind'], 'target_id': target['id'], 'service_ids': list(service_ids), 'spare_id': spare_id,
              'stages': deepcopy(profile['stages']), 'input_target': deepcopy(target), 'actor': actor,
              'calculation':deepcopy(profile.get('calculation')), 'engine_version':s['spec']['version']}
    job = dict(id=jid, title=profile['title'], kind='procedure', owner='logistics' if profile['kind'] != 'offload' else 'construction',
               asset_kinds=list({asset_by_id(s, a)['kind'] for a in service_ids}), target=hours, unit='h', output=jid+'_h',
               dependencies=dependencies, rate_per_asset_h=1/len(service_ids), power_per_asset_kw=peak/len(service_ids),
               parameters=[], basis='Versioned engineering profile '+digest(profile), position=target['position'],
               status='pending', done=0.0, progress=0.0, assigned=[], reason='', decision_id=None, started_tick=None,
               completed_tick=None, procedure=record)
    if spare:
        spare.update(reserved_by=jid)
    s['jobs'].append(job); s['priority'].append(jid); s['resources'][job['output']] = 0.0
    s['milestones'][jid] = False
    if profile['kind'] == 'offload':
        s.setdefault('additional_readiness_jobs', []).append(jid)
        s['milestones']['ready'] = False; s['readiness_tick'] = None
        shielding = next((j for j in s['jobs'] if j['id'] == 'shielding'), None)
        if shielding and jid not in shielding['dependencies']:
            shielding['dependencies'].append(jid)
    event(s, 'Procedure work created', summary, jid)
    return jid


def locks(s, exclude=None):
    return {j['procedure']['target_id'] for j in s['jobs'] if j.get('procedure') and j['procedure']['kind']!='battery-charge' and j['status'] != 'complete' and j['id'] != exclude}


def execution_blockers(s, job):
    from .engine import asset_by_id
    p = job.get('procedure')
    if not p:
        return []
    target = asset_by_id(s, p['target_id'])
    profile = s['procedure_configuration']['profiles'][p['profile_id']]
    if p['kind'] == 'repair' and (target['available'] or target.get('failed_component') != profile['component']):
        return ['Repair diagnosis changed; revalidate the procedure']
    if p['kind'] == 'offload' and target.get('location') != 'lander':
        return ['Offload payload moved; revalidate the procedure']
    spare = s.get('inventory', {}).get(p['spare_id'])
    if p['kind'] != 'offload' and (not spare or spare['status'] != 'stored' or spare['reserved_by'] != job['id']):
        return ['Procedure spare reservation is no longer valid']
    return []


def validate_assignment(j, ids):
    return [] if not j.get('procedure') or set(ids) == set(j['procedure']['service_ids']) else ['Procedure must use its exact validated service-equipment assignment']


def stage_energy(job, hours):
    """Integrate exact stage overlap, including multiple sub-tick stages."""
    cursor = 0.0; energy = 0.0; portions = []
    lo, hi = job['done'], job['done'] + hours
    for stage in job['procedure']['stages']:
        end = cursor + stage['duration']['value']
        overlap = max(0.0, min(hi, end) - max(lo, cursor))
        if overlap:
            e = overlap * stage['grid_power']['value']; energy += e
            portions.append({'name': stage['name'], 'hours': overlap, 'grid_energy_kwh': e})
        cursor = end
    return energy, portions


def bounded_hours(s,job,hours):
    if job['procedure']['kind']!='battery-charge':return hours
    p=job['procedure'];spare=s['inventory'][p['spare_id']]
    efficiency=s['procedure_configuration']['profiles'][p['profile_id']]['charge_efficiency']['value']
    need=(spare['capacity_wh']-spare['soc_wh'])/1000/efficiency
    if stage_energy(job,hours)[0]<=need:return hours
    lo,hi=0.0,hours
    for _ in range(60):
        mid=(lo+hi)/2
        if stage_energy(job,mid)[0]>need:hi=mid
        else:lo=mid
    return (lo+hi)/2


def apply_energy(s,job,energy):
    if job['procedure']['kind']!='battery-charge':return
    p=job['procedure'];spare=s['inventory'][p['spare_id']]
    efficiency=s['procedure_configuration']['profiles'][p['profile_id']]['charge_efficiency']['value']
    added=min(spare['capacity_wh']-spare['soc_wh'],energy*1000*efficiency)
    spare['soc_wh']+=added
    p['charged_wh']=p.get('charged_wh',0.0)+added


def update_kinematics(s,job):
    if job['procedure']['kind']!='offload':return
    from .engine import asset_by_id
    profile=s['procedure_configuration']['profiles'][job['procedure']['profile_id']]
    target=asset_by_id(s,profile['target_id'])
    def fraction(name):
        cursor=0.0
        for stage in profile['stages']:
            duration=stage['duration']['value']
            if stage['name']==name:return max(0.0,min(1.0,(job['done']-cursor)/duration))
            cursor+=duration
        return 0.0
    rotation=profile['rotation'];f=fraction(rotation['rotation_stage'])
    initial,final=rotation['initial_angle']['value'],rotation['final_angle']['value']
    target['orientation_deg']=initial+(final-initial)*f
    target['descent_remaining_m']=profile['lifting']['travel']['value']*(1-fraction(profile['lifting']['motion_stage']))


def complete(s, job):
    from .engine import asset_by_id, event
    p = job['procedure']; target = asset_by_id(s, p['target_id'])
    spare = s.get('inventory', {}).get(p['spare_id'])
    if p['kind'] == 'repair':
        spare.update(status='installed', reserved_by=None, installed_in=target['id'])
        old = target.get('installed_modules', {}).get(s['procedure_configuration']['profiles'][p['profile_id']]['component'])
        component = s['procedure_configuration']['profiles'][p['profile_id']]['component']
        target.setdefault('installed_modules', {})[component] = spare['id']
        target.update(available=True, failed_component=None)
        old = old or 'initial-module:'+target['id']+':'+component
        s['inventory'][old] = {**s['inventory'].get(old,{}), 'id':old, 'kind':'module', 'component':component,
                               'compatible_asset_id':target['id'], 'status':'failed', 'installed_in':None,
                               'reserved_by':None, 'manifest_basis':'Removed failed installed module'}
    elif p['kind'] == 'battery-swap':
        old_id = target.get('battery_serial') or 'initial-pack:'+target['id']
        s['inventory'][old_id] = {'id':old_id, 'kind':'battery', 'interface':spare['interface'],
                                  'compatible_asset_id':target['id'], 'capacity_wh':target['battery_wh'],
                                  'soc_wh':target['soc_wh'], 'status':'stored', 'reserved_by':None,
                                  'manifest_basis':'Removed installed pack; preserves measured simulator charge'}
        target.update(soc_wh=spare['soc_wh'], battery_serial=spare['id'], low_flagged=False)
        spare.update(status='installed', reserved_by=None, installed_in=target['id'], soc_wh=None)
    elif p['kind']=='battery-charge':
        spare['reserved_by']=None
    else:
        target['location'] = 'prepared-site'
        s.get('unfulfilled_payloads',{}).pop(target['id'],None)
    job['procedure']['result'] = {'tick':s['tick'], 'target':deepcopy(target), 'spare_id':p['spare_id'],
                                  'verification':'Deterministic configured procedure completed; not a physical robot telemetry receipt'}
    event(s, 'Procedure result verified', p['kind']+' · '+target['name'], job['id'])

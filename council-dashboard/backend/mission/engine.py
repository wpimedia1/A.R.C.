"""Deterministic state transitions driven by the approved environment package.
Agents propose; this module validates and executes. No physical quantity is defined here."""
from copy import deepcopy
import math
from .spec import specification, digest, draw


class InvalidAction(ValueError):
    pass


def new_state(mode='meta'):
    spec = specification()
    s = {'tick': 0, 'sol': 0.0, 'status': 'active', 'mode': mode, 'spec': spec,
         'assets': deepcopy(spec['assets']),
         'jobs': [{**deepcopy(j), 'status': 'pending', 'done': 0.0, 'progress': 0.0, 'assigned': [], 'reason': '',
                   'decision_id': None, 'started_tick': None, 'completed_tick': None} for j in spec['jobs']],
         'priority': [j['id'] for j in spec['jobs']],
         'resources': {j['output']: 0.0 for j in spec['jobs']},
         'power_capacity_kw': 0.0, 'power_commissioned': False,
         'power_used_kw': 0.0, 'energy_used_kwh': 0.0, 'energy_unestimated_hours': {},
         'milestones': {jid: False for jid in spec['readiness']['jobs']} | {'ready': False}, 'readiness_tick': None,
         'ledger': [], 'physical_ledger': [], 'decisions': [], 'activity': [], 'faults': [],
         'spent_usd': 0.0, 'capital_usd': 0.0, 'capital_unestimated': [],
         'planning_needed': mode == 'meta', 'inference_stopped': False, 'environment': None, 'orders': [],
         'reliability_seed': spec['package_hash'],
         'planning_status': 'Awaiting Meta mission plan' if mode == 'meta' else 'Fixed-priority benchmark'}
    for c in spec['capital']:
        if c['amount_usd'] is None:
            s['capital_unestimated'].append(c['asset_id'])
            s['ledger'].append({'tick': 0, 'kind': 'capital', 'asset_id': c['asset_id'], 'amount_usd': None, 'basis': c['basis']})
        else:
            s['capital_usd'] += c['amount_usd']
            s['ledger'].append({'tick': 0, 'kind': 'capital', 'asset_id': c['asset_id'], 'amount_usd': c['amount_usd'], 'basis': c['basis']})
    event(s, 'Mission initialized', f"Package {spec['package_id']} ({spec['package_hash'][:12]}).")
    return s


def event(s, title, detail, job_id=None):
    s['activity'].append({'id': len(s['activity']) + 1, 'tick': s['tick'], 'title': title, 'detail': detail, 'job_id': job_id})


def job_by_id(s, jid):
    job = next((j for j in s['jobs'] if j['id'] == jid), None)
    if job is None:
        raise InvalidAction('Unknown job ' + str(jid))
    return job


def asset_by_id(s, aid):
    asset = next((a for a in s['assets'] if a['id'] == aid), None)
    if asset is None:
        raise InvalidAction('Unknown asset ' + str(aid))
    return asset


def busy_assets(s, exclude=None):
    return {aid for j in s['jobs'] if j['status'] in ('running', 'review') and j['id'] != exclude for aid in j['assigned']}


def reviewed_onboard(s, actor):
    """D10: Meta agents run onboard; their work orders pass onboard assurance review, then execute at once (no Earth uplink).
    The fixed-priority benchmark scheduler is not reviewed."""
    return s['mode'] == 'meta' and actor != 'fixed-priority'


def battery(a):
    """D18: battery-powered units carry a state of charge (Wh)."""
    return a.get('battery_wh') is not None


def step_energy_wh(s, a):
    """Battery energy one step of excavation needs: rate x step length x energy per kg (schuler2019, D18)."""
    return a['rate_per_h'] * s['spec']['tick_hours'] * a['energy_wh_per_kg']


def charge(s, asset_ids, reason, actor):
    """Start recharging units from the fission grid. They do no work while charging and stop charging when full."""
    if not s['power_commissioned']:
        raise InvalidAction('No grid power: fission power is not commissioned, so batteries cannot be charged')
    if not isinstance(reason, str) or not reason.strip():
        raise InvalidAction('Charging needs a public reason')
    if not isinstance(asset_ids, list) or not asset_ids or len(set(asset_ids)) != len(asset_ids):
        raise InvalidAction('Charging needs a list of distinct units')
    # The whole command is validated before anything changes: a rejected command leaves the state untouched.
    units, needed = [], 0.0
    for aid in asset_ids:
        a = asset_by_id(s, aid)
        if not battery(a):
            raise InvalidAction(f'{aid} has no battery to charge')
        if not a['available']:
            raise InvalidAction(f'{aid} is unavailable')
        if a.get('charging'):
            raise InvalidAction(f'{aid} is already charging')
        if a['soc_wh'] >= a['battery_wh'] - 1e-9:
            raise InvalidAction(f'{aid} battery is already full')
        needed += a['charge_kw']
        units.append(a)
    if s['power_used_kw'] + needed > s['power_capacity_kw'] + 1e-9:
        raise InvalidAction(f'Not enough grid power to charge {", ".join(asset_ids)}: needs {needed:.3f} kW; '
                            f'{s["power_used_kw"]:.3f} of {s["power_capacity_kw"]} kW in use')
    for a in units:
        a['charging'] = True
        a['low_flagged'] = False
        s['power_used_kw'] += a['charge_kw']
        event(s, 'Charging: ' + a['name'], f"{a['soc_wh']:.0f} of {a['battery_wh']:.0f} Wh. {reason}")
    s.setdefault('charge_log', []).append({'tick': s['tick'], 'assets': list(asset_ids), 'reason': reason, 'actor': actor})


def stop_charging(s, a, why):
    if a.get('charging'):
        a['charging'] = False
        s['power_used_kw'] = max(0.0, s['power_used_kw'] - a['charge_kw'])
        event(s, 'Charging ended: ' + a['name'], why)


def power_known(j):
    """False when the job's power draw is not published (power_per_asset_kw is None)."""
    return j is None or j.get('power_per_asset_kw', 0.0) is not None


def demand_kw(s, asset_ids, j=None):
    """Grid power for these assets on this job, or None when the job's power draw is not published (unknown, not zero)."""
    if j is not None and 'power_per_asset_kw' in j:
        return None if j['power_per_asset_kw'] is None else j['power_per_asset_kw'] * len(asset_ids)
    return sum(asset_by_id(s, a)['grid_power_kw'] for a in asset_ids)


def reserved_kw(s, asset_ids, j=None):
    """Power booked on the grid ledger. An unpublished draw books nothing and is reported as unvalidated, never as 0 kW."""
    return demand_kw(s, asset_ids, j) or 0.0


def reasons(s, j, asset_ids=None):
    """Every reason this job cannot start with these assets now. Empty list means valid."""
    if j['status'] not in ('pending', 'blocked'):
        return ['Job is ' + j['status']]
    out = []
    for d in j['dependencies']:
        if job_by_id(s, d)['status'] != 'complete':
            out.append('Waiting for ' + job_by_id(s, d)['title'].lower())
    asset_ids = asset_ids if asset_ids is not None else compatible_free(s, j)
    if not asset_ids:
        out.append('No compatible equipment is available')
    busy = busy_assets(s)
    for aid in asset_ids:
        try:
            a = asset_by_id(s, aid)
        except InvalidAction as exc:
            out.append(str(exc)); continue
        if a['kind'] not in j['asset_kinds']:
            out.append(f"{a['name']} cannot perform {j['kind']}")
        if not a['available']:
            out.append(f"{a['name']} is unavailable")
        if aid in busy:
            out.append(f"{a['name']} is assigned to other work")
    if len(set(asset_ids)) != len(asset_ids):
        out.append('Duplicate equipment assignment')
    if j['id'] == 'survey' and j.get('route_blocked'):
        out.append('No hazard-free route across the analysed site image: ' + j['route_blocked']['status'] + ' (D13)')
    if not out and not power_known(j):
        # Unknown draw: the job cannot be checked against capacity. It may run only on a commissioned grid with spare
        # capacity, and its decision is recorded as not physically validated for power.
        if not s['power_commissioned'] or s['power_capacity_kw'] - s['power_used_kw'] <= 1e-9:
            out.append('Power draw is not published and no grid capacity is unallocated'
                       + ('' if s['power_commissioned'] else ' (fission power not yet commissioned)'))
    elif not out and s['power_used_kw'] + demand_kw(s, asset_ids, j) > s['power_capacity_kw'] + 1e-9:
        out.append(f"Needs {demand_kw(s, asset_ids, j):.3g} kW; {s['power_capacity_kw'] - s['power_used_kw']:.3g} kW unallocated"
                   + ('' if s['power_commissioned'] else ' (fission power not yet commissioned)'))
    return out


def compatible_free(s, j):
    busy = busy_assets(s)
    return [a['id'] for a in s['assets'] if a['kind'] in j['asset_kinds'] and a['available'] and a['id'] not in busy]


def start(s, jid, asset_ids, rationale, actor, source_ids):
    j = job_by_id(s, jid)
    errors = reasons(s, j, asset_ids)
    if errors:
        raise InvalidAction('; '.join(errors))
    allowed = set(s.get('source_pins', {})) | set(s['spec']['sources']) | {s['spec']['package_id']}
    unknown = [k for k in source_ids if k not in allowed]
    if not source_ids or unknown:
        raise InvalidAction('Evidence references must resolve to pinned sources: ' + ', '.join(unknown or ['none given']))
    d = {'id': f'D{len(s["decisions"]) + 1}', 'tick': s['tick'], 'job_id': jid, 'actor': actor, 'summary': rationale,
         'assets': list(asset_ids), 'source_ids': list(source_ids),
         'source_versions': {k: s.get('source_pins', {}).get(k) for k in source_ids},
         'package_hash': s['spec']['package_hash'], 'parameters': j['parameters'],
         'input_snapshot': {'resources': deepcopy(s['resources']), 'power_used_kw': s['power_used_kw'],
                            'power_capacity_kw': s['power_capacity_kw']},
         'calculation': {'target': j['target'], 'unit': j['unit'], 'rate_per_tick': rate_per_tick(s, asset_ids, j),
                         'power_kw': demand_kw(s, asset_ids, j), 'power_published': power_known(j)},
         'validation': 'accepted' if power_known(j) else 'accepted; power not physically validated (draw not published)',
         'outcome': None}
    s['decisions'].append(d)
    s['power_used_kw'] += reserved_kw(s, asset_ids, j)
    if reviewed_onboard(s, actor):
        # Equipment and power are reserved from authorization; work begins as soon as onboard assurance approves.
        j.update(status='review', assigned=list(asset_ids), decision_id=d['id'], reason='Awaiting onboard assurance review',
                 authorization={'queued_tick': s['tick'], 'assurance': 'pending'})
        d['authorization'] = j['authorization']
        event(s, j['title'] + ' authorized onboard', rationale, jid)
        return d['id']
    j.update(status='running', assigned=list(asset_ids), reason='', decision_id=d['id'], run_since_tick=s['tick'], done_at_run=j['done'], behind_flagged=False,
             started_tick=j['started_tick'] if j['started_tick'] is not None else s['tick'])
    event(s, j['title'] + ' started', rationale, jid)
    return d['id']


SITE_JOBS = ('survey', 'trench', 'shielding', 'drill', 'water')


def open_conditions(s, j):
    """Facts the simulator knows are unresolved for this work order. Assurance must acknowledge each one to approve."""
    out = []
    units = [asset_by_id(s, a) for a in j['assigned']]
    if any(battery(a) for a in units) and not s['power_commissioned']:
        out.append({'id': 'no-grid-charging', 'text': 'Batteries cannot be recharged until fission power is commissioned'})
    low = [a['id'] for a in units if battery(a) and a['soc_wh'] < step_energy_wh(s, a)]
    if low:
        out.append({'id': 'battery-low', 'text': 'Battery too low for one step of work: ' + ', '.join(low)})
    if j['id'] in SITE_JOBS:
        img = s.get('site_imagery')
        if not img:
            out.append({'id': 'no-site-imagery', 'text': 'No orbital hazard imagery of the mission site has been analysed'})
        elif not img['applies_to_site']:
            out.append({'id': 'proxy-site-imagery', 'text': 'Orbital detections are from a proxy image (' + img['site_relation'] + '), not the mission site'})
    if not power_known(j):
        out.append({'id': 'energy-not-estimated', 'text': 'Power draw for this job is not published: it is not checked against grid capacity and its energy use is not estimated'})
    return out


def assurance_decision(s, jid, approve, reason, actor, acknowledged=None):
    """Assurance review of an authorized, unsent work order. A hold releases equipment and power and escalates to the director."""
    j = job_by_id(s, jid)
    if j['status'] != 'review' or j['authorization'].get('assurance') != 'pending':
        raise InvalidAction(f'{jid} has no work order awaiting assurance')
    if not isinstance(reason, str) or not reason.strip():
        raise InvalidAction('Assurance must give a reason')
    conditions = open_conditions(s, j)
    missing = [c['id'] for c in conditions if c['id'] not in (acknowledged or [])]
    if approve and missing:
        raise InvalidAction('Approval must acknowledge every open condition: ' + ', '.join(missing))
    review = {'tick': s['tick'], 'actor': actor, 'approved': bool(approve), 'reason': reason, 'open_conditions': conditions,
              'acknowledged': list(acknowledged or [])}
    d = next(x for x in s['decisions'] if x['id'] == j['decision_id'])
    d['assurance'] = review
    if approve:
        j['authorization']['assurance'] = 'approved'
        j.update(status='running', reason='', run_since_tick=s['tick'], done_at_run=j['done'], behind_flagged=False,
                 started_tick=j['started_tick'] if j['started_tick'] is not None else s['tick'])
        event(s, j['title'] + ' passed onboard assurance and started', reason, jid)
    else:
        d['validation'] = 'held by assurance'
        release(s, j, 'blocked', 'Held by assurance: ' + reason)
        j.pop('authorization', None)
        s.setdefault('department_conflicts', []).append({'role': 'assurance', 'tick': s['tick'], 'summary': f'{jid}: {reason}', 'status': 'unresolved'})
        event(s, j['title'] + ' held by assurance', reason, jid)
        s['planning_needed'] = s['mode'] == 'meta' and not s['inference_stopped']
    return review


def place_order(s, order):
    """D12: record a replacement unit in transit. Delivery makes the asset available at order['arrival_tick']."""
    asset = asset_by_id(s, order['asset_id'])
    if asset['available']:
        raise InvalidAction(f"{asset['name']} has not failed; no replacement needed")
    if any(o['asset_id'] == order['asset_id'] and o['status'] == 'in transit' for o in s['orders']):
        raise InvalidAction(f"A replacement for {asset['name']} is already in transit")
    o = {**order, 'id': f"O{len(s['orders']) + 1}", 'tick': s['tick'], 'status': 'in transit'}
    s['orders'].append(o)
    if o['cost_usd'] is None:
        s['capital_unestimated'].append(o['asset_id'] + ' replacement')
    else:
        s['capital_usd'] += o['cost_usd']
    s['ledger'].append({'tick': s['tick'], 'kind': 'replacement', 'asset_id': o['asset_id'], 'amount_usd': o['cost_usd'], 'basis': o['cost_basis']})
    event(s, 'Replacement ordered: ' + asset['name'], f"Launch {o['launch_utc'].split('T')[0]}, arrival {o['arrival_utc'].split('T')[0]} (tick {o['arrival_tick']}). " + o['summary'])
    return o


def apply_environment(s, env):
    """Live Mars conditions at this tick (D10, D11). Changes that alter what is feasible trigger agent replanning."""
    prev = s.get('environment')
    env['applied_tick'] = s['tick']
    s['environment'] = env
    replan = False
    if prev is None:
        event(s, 'Live Mars conditions applied', f"{env['clock']['utc']}: Mars year {env['clock']['mars_year']}, Ls {env['clock']['ls_deg']:.1f} deg ({env['clock']['season']}); "
              f"Earth-Mars {env['geometry']['one_way_light_s'] / s['spec']['seconds_per_minute']:.1f} light-minutes; DSN {env['link']['dsn']}.")
        return s
    if env.get('resumed_after_s'):
        event(s, 'Mission resumed', f"Paused for {env['resumed_after_s'] / s['spec']['seconds_per_hour']:.1f} h of real time; Mars conditions kept running. "
              + env.get('while_paused', ''))
        replan = True
    if env['link']['conjunction'] != prev['link']['conjunction']:
        event(s, 'Solar conjunction ' + ('began' if env['link']['conjunction'] else 'ended'),
              f"Sun-Mars separation {env['geometry']['sun_mars_separation_deg']:.2f} deg seen from Earth; Earth contact " + ('interrupted; the outpost continues on its own.' if env['link']['conjunction'] else 'restored.'))
        replan = True
    if env['clock']['season'] != prev['clock']['season']:
        event(s, 'Season changed', f"{env['clock']['season'].capitalize()} began at Ls {env['clock']['ls_deg']:.1f} deg (Mars year {env['clock']['mars_year']}).")
        replan = True
    if env['link']['dsn'] != prev['link']['dsn']:
        event(s, 'DSN feed ' + ('restored' if env['link']['dsn'] == 'live' else 'unavailable'), env['link'].get('dsn_error') or 'Live DSN Now readings applied.')
    if replan:
        s['planning_needed'] = s['mode'] == 'meta' and not s['inference_stopped']
    return s


def rate_per_tick(s, asset_ids, j=None):
    if j is not None and j.get('rate_per_asset_h') is not None:
        return j['rate_per_asset_h'] * len(asset_ids) * s['spec']['tick_hours']
    return sum(asset_by_id(s, a)['rate_per_h'] for a in asset_ids) * s['spec']['tick_hours']


def release(s, j, status, reason=''):
    s['power_used_kw'] = max(0.0, s['power_used_kw'] - reserved_kw(s, j['assigned'], j))
    j.update(status=status, reason=reason, assigned=[])


def advance(state, env=None):
    s = deepcopy(state)
    if s['status'] != 'active':
        return s
    s['tick'] += 1
    if env is not None:
        apply_environment(s, env)
    s['sol'] = round(s['tick'] / 24, 6)
    hours = s['spec']['tick_hours']
    ops = s['spec']['ops_usd_per_tick']
    s['spent_usd'] += ops
    sol_index = (s['tick'] - 1) // 24
    last = s['ledger'][-1] if s['ledger'] else None
    if last and last['kind'] == 'operations' and last['sol_index'] == sol_index:
        last['amount_usd'] += ops; last['ticks'] += 1; last['through_tick'] = s['tick']
    else:
        s['ledger'].append({'tick': s['tick'], 'through_tick': s['tick'], 'sol_index': sol_index, 'ticks': 1, 'kind': 'operations',
                            'amount_usd': ops, 'basis': 'cost.ops_usd_per_sol / 24 per tick, summed per sol (D5)'})
    # D14: working mobile robots can fail this tick (deterministic draw per mission seed, tick and unit).
    for j in [j for j in s['jobs'] if j['status'] == 'running']:
        for aid in j['assigned']:
            a = asset_by_id(s, aid)
            rate = a.get('failure_rate_per_h')
            if s.get('failures_enabled', True) and a['available'] and rate and draw(s.get('reliability_seed', s['spec']['package_hash']), s['tick'], aid) < -math.expm1(-rate * hours):
                a['available'] = False
                s['faults'].append({'tick': s['tick'], 'kind': 'failure', 'asset_id': aid, 'available': False, 'basis': 'D14 failure rate'})
                event(s, a['name'] + ' failed', f"Random failure while working on {j['title'].lower()} (D14: rate {rate:.3g}/h, source stancliff2005).", j['id'])
    # Power loss or equipment failure holds work. Jobs (running or awaiting assurance) and chargers book power on the same
    # ledger (power_used_kw); while booked power exceeds supply, reservations are released until it fits.
    for a in [a for a in s['assets'] if a.get('charging') and not a['available']]:
        stop_charging(s, a, 'Unit unavailable.')
    for j in sorted([j for j in s['jobs'] if j['status'] in ('running', 'review')], key=lambda j: s['priority'].index(j['id'])):
        lost = [a for a in j['assigned'] if not asset_by_id(s, a)['available']]
        if lost or s['power_used_kw'] > s['power_capacity_kw'] + 1e-9:
            if j['status'] == 'review':
                j.pop('authorization', None)
                d = next((x for x in s['decisions'] if x['id'] == j['decision_id']), None)
                if d: d['validation'] = 'withdrawn before assurance review: ' + ('equipment unavailable' if lost else 'power supply below booked demand')
            release(s, j, 'blocked', 'Execution stopped: ' + ('equipment unavailable' if lost else 'power capacity below allocated demand'))
            event(s, j['title'] + ' stopped', j['reason'], j['id'])
            s['planning_needed'] = s['mode'] == 'meta' and not s['inference_stopped']
    for a in [a for a in s['assets'] if a.get('charging')]:
        if s['power_used_kw'] > s['power_capacity_kw'] + 1e-9:
            stop_charging(s, a, f"Grid supply {s['power_capacity_kw']} kW is below booked demand; charging interrupted.")
            s['planning_needed'] = s['mode'] == 'meta' and not s['inference_stopped']
    # D18: charging units take booked grid power and refill; they stop on their own when full.
    charged_now = set()  # a unit that charged during this step does no work in it
    for a in [a for a in s['assets'] if a.get('charging')]:
        charged_now.add(a['id'])
        added = min(a['charge_kw'] * s['spec']['wh_per_kwh'] * hours, a['battery_wh'] - a['soc_wh'])
        a['soc_wh'] += added
        s['energy_used_kwh'] += added / s['spec']['wh_per_kwh']
        s['charging_energy_kwh'] = s.get('charging_energy_kwh', 0.0) + added / s['spec']['wh_per_kwh']
        if a['soc_wh'] >= a['battery_wh'] - 1e-9:
            a['soc_wh'] = a['battery_wh']
            stop_charging(s, a, 'Battery full.')
    for j in s['jobs']:
        if j['status'] != 'running':
            continue
        waiting = [a for a in j['assigned'] if asset_by_id(s, a).get('standby_until_tick', 0) > s['tick']]
        if waiting:
            j['reason'] = 'Standby until tick ' + str(max(asset_by_id(s, a)['standby_until_tick'] for a in waiting)) + ': ' + asset_by_id(s, waiting[0])['standby']['reason']
            continue
        if j['reason'].startswith('Standby'):
            j['reason'] = ''
            event(s, j['title'] + ' resumed', 'Standby ended.', j['id'])
        units = [asset_by_id(s, a) for a in j['assigned']]
        empty = [a for a in units if battery(a) and not a.get('charging') and a['soc_wh'] < step_energy_wh(s, a) - 1e-9]
        for a in empty:
            if not a.get('low_flagged'):
                a['low_flagged'] = True
                event(s, 'Battery low: ' + a['name'], f"{a['soc_wh']:.0f} Wh left; one step of work needs {step_energy_wh(s, a):.0f} Wh. Work paused until recharged.", j['id'])
                s['planning_needed'] = s['mode'] == 'meta' and not s['inference_stopped']
        working = [a for a in units if not a.get('charging') and a['id'] not in charged_now and a not in empty]
        if not working:
            j['reason'] = 'Paused: ' + ('charging' if any(a.get('charging') for a in units) else 'batteries too low; recharge needed')
            continue
        if j['reason'].startswith('Paused'):
            j['reason'] = ''
        amount = min(rate_per_tick(s, [a['id'] for a in working], j), j['target'] - j['done'])
        for a in [a for a in working if battery(a)]:
            a['soc_wh'] = max(0.0, a['soc_wh'] - amount / len(working) * a['energy_wh_per_kg'])
        if not power_known(j):
            energy = None
            s['energy_unestimated_hours'][j['id']] = s['energy_unestimated_hours'].get(j['id'], 0.0) + hours
        else:
            energy = demand_kw(s, j['assigned'], j) * hours
        j['done'] += amount
        j['progress'] = round(j['done'] / j['target'], 6)
        s['resources'][j['output']] += amount
        if energy is not None:
            s['energy_used_kwh'] += energy
        entry = next((e for e in reversed(s['physical_ledger'][-8:]) if e['sol_index'] == sol_index and e['job_id'] == j['id']
                      and e['assets'] == j['assigned']), None)
        if entry:
            entry['amount'] += amount; entry['energy_kwh'] = None if energy is None else entry['energy_kwh'] + energy; entry['ticks'] += 1; entry['through_tick'] = s['tick']
        else:
            s['physical_ledger'].append({'tick': s['tick'], 'through_tick': s['tick'], 'sol_index': sol_index, 'ticks': 1, 'job_id': j['id'],
                                         'resource': j['output'], 'amount': amount, 'energy_kwh': energy, 'assets': list(j['assigned'])})
        if j['done'] >= j['target'] - 1e-9:
            j['done'] = j['target']; j['progress'] = 1.0; j['completed_tick'] = s['tick']
            release(s, j, 'complete')
            s['milestones'][j['id']] = True
            if 'grid_capacity_kw' in j.get('effect', {}):
                s['power_capacity_kw'] = j['effect']['grid_capacity_kw']
                s['power_commissioned'] = True
                event(s, 'Grid power available', f"{s['power_capacity_kw']} kW", j['id'])
            for d in s['decisions']:
                if d['job_id'] == j['id'] and d['outcome'] is None:
                    d['outcome'] = {'completed_tick': s['tick'], 'resources': deepcopy(s['resources'])}
            event(s, j['title'] + ' completed', f"{j['target']:.6g} {j['unit']} recorded by the simulator.", j['id'])
            s['planning_needed'] = s['mode'] == 'meta' and not s['inference_stopped']
    # Plan vs actual: more than one step of work behind the authorized rate (for any reason: standby, batteries,
    # charging) asks the agents to replan, once per authorization.
    for j in [j for j in s['jobs'] if j['status'] == 'running' and j.get('run_since_tick') is not None and not j.get('behind_flagged')]:
        d = next((x for x in s['decisions'] if x['id'] == j.get('decision_id')), None)
        if d:
            expected = d['calculation']['rate_per_tick'] * (s['tick'] - j['run_since_tick'])
            actual = j['done'] - j.get('done_at_run', 0.0)
            if expected - actual > d['calculation']['rate_per_tick'] + 1e-9:
                j['behind_flagged'] = True
                event(s, j['title'] + ' behind plan', f"{actual:.6g} {j['unit']} done against {expected:.6g} expected at the authorized rate.", j['id'])
                s['planning_needed'] = s['mode'] == 'meta' and not s['inference_stopped']
    for o in s.get('orders', []):
        if o['status'] == 'in transit' and s['tick'] >= o['arrival_tick']:
            o['status'] = 'delivered'
            asset_by_id(s, o['asset_id'])['available'] = True
            s['faults'].append({'tick': s['tick'], 'kind': 'equipment', 'asset_id': o['asset_id'], 'available': True, 'order': o['id']})
            event(s, 'Replacement delivered: ' + o['asset_name'], f"Order {o['id']} arrived ({o['arrival_utc'].split('T')[0]}).")
            s['planning_needed'] = s['mode'] == 'meta' and not s['inference_stopped']
    if all(s['milestones'][k] for k in s['spec']['readiness']['jobs']) and not s['milestones']['ready']:
        s['milestones']['ready'] = True
        s['readiness_tick'] = s['tick']
        # Readiness is a milestone, not the end of operations: added work, charging and failures continue afterwards.
        event(s, 'Readiness criteria met', s['spec']['readiness']['description'] + ' Operations continue. Simulation result, not engineering certification.')
    if s['mode'] == 'fixed-priority' and s['status'] == 'active':
        # The benchmark charges any battery that cannot supply the next step, when grid power allows.
        for a in [a for a in s['assets'] if battery(a) and a['available'] and not a.get('charging') and a['soc_wh'] < step_energy_wh(s, a) - 1e-9]:
            try:charge(s, [a['id']], 'Battery below one step of work.', 'fixed-priority')
            except InvalidAction:pass
        for jid in s['priority']:
            j = job_by_id(s, jid)
            if j['status'] in ('pending', 'blocked'):
                assets = compatible_free(s, j)
                errors = reasons(s, j, assets)
                if errors:
                    j.update(status='blocked', reason='; '.join(errors))
                else:
                    start(s, jid, assets, 'Next in fixed priority; all compatible free equipment assigned.', 'fixed-priority',
                          [s['spec']['package_id']])
    elif s['mode'] == 'meta':
        for j in s['jobs']:
            if j['status'] in ('pending', 'blocked'):
                j['reason'] = '; '.join(reasons(s, j)) or 'Awaiting an agent work order'
    assert all(v >= -1e-9 for v in s['resources'].values())
    assert s['power_used_kw'] <= s['power_capacity_kw'] + 1e-9
    return s


def modify(state, changes):
    """Experiment changes. Each one is recorded; none changes the environment package."""
    s = deepcopy(state)
    if set(changes) - {'priority', 'equipment', 'power_capacity_kw', 'planner'}:
        raise InvalidAction('Unsupported change: ' + ', '.join(sorted(set(changes) - {'priority', 'equipment', 'power_capacity_kw', 'planner'})))
    if 'priority' in changes:
        p = changes['priority']
        if not isinstance(p, list) or sorted(p) != sorted(s['priority']):
            raise InvalidAction('Priority must contain every job exactly once')
        s['priority'] = p
    if 'equipment' in changes:
        if not isinstance(changes['equipment'], dict):
            raise InvalidAction('Equipment must map asset IDs to availability')
        for aid, available in changes['equipment'].items():
            if not isinstance(available, bool):
                raise InvalidAction('Availability must be true or false')
            asset_by_id(s, aid)['available'] = available
            s['faults'].append({'tick': s['tick'], 'kind': 'equipment', 'asset_id': aid, 'available': available})
    if 'power_capacity_kw' in changes:
        v = changes['power_capacity_kw']
        rated = next(a['output_kw'] for a in s['assets'] if a['kind'] == 'power')
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not 0 <= v <= rated:
            raise InvalidAction(f'Power capacity must be between 0 and the rated {rated} kW')
        if not s['power_commissioned'] and v > 0:
            raise InvalidAction('Fission power is not commissioned; capacity stays 0 until the deployment job completes')
        s['power_capacity_kw'] = float(v)
        s['faults'].append({'tick': s['tick'], 'kind': 'power', 'capacity_kw': float(v)})
    if 'planner' in changes:
        if changes['planner'] not in ('meta', 'fixed-priority'):
            raise InvalidAction('Unknown planner')
        s['mode'] = changes['planner']
        s['inference_stopped'] = False
        s['planning_status'] = 'Awaiting Meta mission plan' if s['mode'] == 'meta' else 'Fixed-priority benchmark'
    s['planning_needed'] = s['mode'] == 'meta'
    event(s, 'Experiment changed', ', '.join(f'{k}={changes[k]}' for k in changes))
    return s


def sim_unix(s):
    """Simulated UTC of this state: the applied conditions' time plus ticks elapsed since (frozen in experiments)."""
    env = s.get('environment')
    if env is None:
        return None
    return env['clock']['unix'] + (s['tick'] - env.get('applied_tick', s['tick'])) * s['spec']['tick_seconds']


def failed_without_order(s):
    return [a['id'] for a in s['assets'] if not a['available']
            and not any(o['asset_id'] == a['id'] and o['status'] == 'in transit' for o in s.get('orders', []))]


def instantiate_job(s, template_id, actor, summary):
    """Create new work from a package template (agents may add work; readiness criteria are unchanged)."""
    t = next((t for t in s['spec'].get('templates', []) if t['template_id'] == template_id), None)
    if t is None:
        raise InvalidAction('Unknown job template ' + str(template_id))
    if not isinstance(summary, str) or not summary.strip():
        raise InvalidAction('A public reason is required to create work')
    n = sum(1 for j in s['jobs'] if j.get('template_id') == template_id) + 1
    jid = f'{template_id}-{n}'
    job = {k: deepcopy(v) for k, v in t.items()}
    output = job['output'] + '_' + jid.replace('-', '_')
    job.update(id=jid, output=output, status='pending', done=0.0, progress=0.0, assigned=[], reason='', decision_id=None,
               started_tick=None, completed_tick=None, created_by=actor, created_tick=s['tick'], created_reason=summary)
    s['jobs'].append(job)
    s['priority'].append(jid)
    s['resources'][output] = 0.0
    s['milestones'][jid] = False
    event(s, 'New work created: ' + job['title'], summary + ' (' + actor + ')', jid)
    return jid


BASIS_KINDS = ('weather-obs', 'weather-estimate', 'weather-check')
BASIS_KEYS = {'observation_id', 'kind', 'station', 'variable', 'value', 'record_hash', 'interpretation'}


def set_standby(s, asset_ids, ticks, reason, actor, basis):
    """Agent-ordered protective standby: the units do no work for `ticks` ticks. Jobs keep their authorization and resume
    automatically. `basis` is a list of observation references already resolved against stored records
    (nowcast.resolve_basis): observation id, kind, station, variable, the stored value, record hash and the agent's
    interpretation. The whole command is validated before anything changes."""
    if not isinstance(ticks, int) or ticks < 1 or ticks > s['spec']['standby_max_ticks']:
        raise InvalidAction('Standby must be between 1 and ' + str(s['spec']['standby_max_ticks']) + ' ticks')
    if not isinstance(reason, str) or not reason.strip():
        raise InvalidAction('Standby needs a public reason')
    if not isinstance(basis, list) or not basis or any(not isinstance(b, dict) or set(b) != BASIS_KEYS or b['kind'] not in BASIS_KINDS
                                                       or not isinstance(b['interpretation'], str) or not b['interpretation'].strip() for b in basis):
        raise InvalidAction('Standby needs resolved observation references (stored measurement, estimate or check) with an interpretation')
    if not isinstance(asset_ids, list) or not asset_ids or len(set(asset_ids)) != len(asset_ids):
        raise InvalidAction('Standby needs a list of distinct units')
    units = [asset_by_id(s, aid) for aid in asset_ids]
    for a in units:
        aid = a['id']
        a['standby_until_tick'] = s['tick'] + ticks
        a['standby'] = {'from_tick': s['tick'], 'until_tick': s['tick'] + ticks, 'reason': reason, 'actor': actor, 'basis': basis}
    s.setdefault('standby_log', []).append({'tick': s['tick'], 'assets': list(asset_ids), 'ticks': ticks, 'reason': reason, 'actor': actor, 'basis': basis})
    event(s, 'Standby ordered: ' + ', '.join(asset_by_id(s, a)['name'] for a in asset_ids), f"{ticks} ticks. {reason}")


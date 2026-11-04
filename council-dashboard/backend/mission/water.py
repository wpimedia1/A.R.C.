"""Conditional aggregate well operations, never synthetic sensor observations.

The D21 control reserve and startup extrapolation are explicit model assumptions.
Water held in the well is distinct from delivered water and finite ice feed.
"""
from copy import deepcopy


def initialize(state,allocate_reserve=True):
    model=state['spec'].get('water_model')
    if not model:return
    state['well']={'phase':'unestablished','contained_kg':0.0,'qualified_liquid_kg':0.0,
        'reserve_kg':model['reserve_kg'],'established_tick':None,'conditioning_runs':0,
        'basis':deepcopy(model),'history':[]}
    if allocate_reserve:state['production']['water_feed_remaining_kg']+=model['reserve_kg']
    state['production']['initial_feed_allocation_kg']=state['production']['water_feed_remaining_kg']+state['production']['water_stored_kg']
    state['production']['basis']='D21 finite design allocation: delivered-water objective plus control reserve. Neither is an observed deposit or qualified tank.'


def blockers(state,job):
    well=state.get('well')
    if not well:return []
    if job['kind']=='well-establishment':
        required=max(0.0,well['reserve_kg']-well['contained_kg'])
        if state['production']['water_feed_remaining_kg']<required:
            return ['Insufficient allocated ice to establish the well reserve']
        p=state['production']
        if p['rate_multiplier']<=0:return ['Well conditioning throughput is zero']
        if p['water_feed_remaining_kg']-required<=1e-9 or p['water_storage_capacity_kg']-p['water_stored_kg']<=1e-9:
            return ['No feed/storage capacity for withdrawal; conditioning cannot support useful production']
    if job['kind']=='water' and (well['phase']!='established' or well['qualified_liquid_kg']<well['reserve_kg']-1e-9):
        return ['Establish and qualify the liquid-water reserve before withdrawal (D21)']
    return []


def condition(state,amount):
    well=state['well'];production=state['production']
    fresh=min(amount,max(0.0,well['reserve_kg']-well['contained_kg']))
    if fresh>production['water_feed_remaining_kg']+1e-9:
        from .engine import InvalidAction
        raise InvalidAction('Well establishment cannot create feed water')
    production['water_feed_remaining_kg']-=fresh
    well['contained_kg']+=fresh
    well['qualified_liquid_kg']=min(well['contained_kg'],well['qualified_liquid_kg']+amount)
    well['phase']='conditioning'
    well['last_heat_tick']=state['tick']


def complete(state,job):
    from .engine import event,InvalidAction
    well=state['well']
    if well['qualified_liquid_kg']<well['reserve_kg']-1e-9:
        raise InvalidAction('Conditioning completed without the required reserve')
    well.update(phase='established',established_tick=state['tick'],last_heat_tick=state['tick'],conditioning_runs=well['conditioning_runs']+1)
    result={'tick':state['tick'],'job_id':job['id'],'qualified_liquid_kg':well['qualified_liquid_kg'],
        'kind':'calculated model result','assumption':'D21_water_establishment_model'}
    well['history'].append(result)
    event(state,'Well reserve established',f"{well['qualified_liquid_kg']:.6g} kg retained in the well under D21; delivered water remains separately metered.",job['id'])


def check_continuity(state):
    """Loss of authorized heat invalidates qualification, not conservation.

    No freezing time or measured phase is invented. Reconditioning consumes grid
    energy again and reuses the same contained mass rather than creating water.
    """
    well=state.get('well')
    if not well or well['phase'] not in ('established','conditioning') or well.get('last_heat_tick')==state['tick']:return
    from .engine import event,release
    well.update(phase='requalification-required',qualified_liquid_kg=0.0)
    for j in state['jobs']:
        if j['kind']=='water' and j['status'] in ('running','review'):
            release(state,j,'blocked','Well heat continuity interrupted; re-establish the retained reserve')
    # An interrupted partial job may restart, but completed work and its milestone
    # are immutable. Later requalification gets its own pending work order.
    for job in state['jobs']:
        if job['kind']=='well-establishment' and job['status']!='complete':
            release(state,job,'pending','Heat continuity not established; recondition the retained reserve')
            job.update(done=0.0,progress=0.0,started_tick=None,completed_tick=None)
            state['planning_needed']=state['mode']=='meta' and not state.get('inference_stopped')
    require_establishment(state)
    well['history'].append({'tick':state['tick'],'kind':'qualification invalidated','contained_kg':well['contained_kg'],
        'reason':'No authorized withdrawal/heating work; physical phase is unmeasured'})
    event(state,'Well heat continuity interrupted','Contained water remains accounted; phase is unmeasured. Reconditioning is required before withdrawal.','well-establish')


def require_establishment(state):
    """A newly authorized batch must requalify a suspended pool before use."""
    well=state.get('well')
    if not well or well['phase']=='established':return
    if not any(j['kind']=='water' and j['status']!='complete' for j in state['jobs']):return
    if any(j['kind']=='well-establishment' and j['status']!='complete' for j in state['jobs']):return
    p=state['production']
    if p['water_feed_remaining_kg']<=1e-9 or p['water_storage_capacity_kg']-p['water_stored_kg']<=1e-9:return
    from .engine import instantiate_job
    instantiate_job(state,'well-recondition','simulator dependency / D21','Heat continuity interrupted: requalify the retained reserve before another withdrawal. This creates pending work, not authorization.')
    state['planning_needed']=state['mode']=='meta' and not state.get('inference_stopped')


def assert_conservation(state):
    well=state.get('well');p=state.get('production',{})
    if not well:return
    assert 0<=well['qualified_liquid_kg']<=well['contained_kg']+1e-9
    assert well['contained_kg']<=well['reserve_kg']+1e-9
    total=p['water_feed_remaining_kg']+p['water_stored_kg']+well['contained_kg']
    assert abs(total-p['initial_feed_allocation_kg'])<1e-6, 'Well/feed/storage mass conservation failed'

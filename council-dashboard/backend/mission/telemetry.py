"""NASA daily weather products. Measured values never become Arcadia measurements."""
import json
import math
from datetime import date

URL='https://mars.nasa.gov/rss/api/?feed=weather&category=msl&feedtype=json'
FIELDS={'min_temp':('air_min_c','degC'), 'max_temp':('air_max_c','degC'),
        'min_gts_temp':('ground_min_c','degC'),'max_gts_temp':('ground_max_c','degC'),
        'pressure':('pressure_pa','Pa')}

def parse_weather(raw, window=90):
    payload=json.loads(raw)
    rows=payload.get('soles')
    if not isinstance(rows,list) or not rows:raise ValueError('NASA weather response has no daily records')
    by_sol={}
    for index,row in enumerate(rows):
        observed=date.fromisoformat(row['terrestrial_date'])
        sol=int(row['sol'])
        point={'sol':sol,'observed_at':observed.isoformat(),'source_row':index+1,
               'location':'Gale crater / Curiosity','classification':'observed daily summary',
               'quality':'NASA public summary; calibrated instrument quality flags not supplied',
               'uv_category':None if row.get('local_uv_irradiance_index') in (None,'--','') else row['local_uv_irradiance_index']}
        missing=[]
        for field,(name,unit) in FIELDS.items():
            value=row.get(field)
            if value in (None,'--',''):point[name]=None;missing.append(name);continue
            value=float(value)
            if not math.isfinite(value) or (name=='pressure_pa' and value<=0):
                point[name]=None;missing.append(name)
            else:point[name]=value
        point['missing_fields']=missing
        if sol in by_sol and by_sol[sol]['observed_at']!=point['observed_at']:raise ValueError('Conflicting NASA observation dates for one sol')
        by_sol[sol]=point
    ordered=sorted(by_sol.values(),key=lambda p:p['sol'])
    selected=ordered[-window:]
    summary={}
    for name,unit in FIELDS.values():
        valid=[p for p in selected if p[name] is not None]
        summary[name]={'unit':unit,'valid_count':len(valid),'minimum':min((p[name] for p in valid),default=None),
                       'maximum':max((p[name] for p in valid),default=None),
                       'latest':valid[-1][name] if valid else None,
                       'latest_observed_at':valid[-1]['observed_at'] if valid else None}
    return {'title':'Curiosity daily environmental observations','url':URL,
            'version':'NASA MSL weather JSON / weather-daily-1','status':'published observations',
            'observation_time':ordered[-1]['observed_at'],'coverage_start':ordered[0]['observed_at'],
            'coverage_end':ordered[-1]['observed_at'],'observation_location':'Curiosity, Gale crater',
            'daily_observations':selected,'archive_record_count':len(ordered),'summary':summary,
            'units':dict(FIELDS.values()),'transformation_version':'weather-daily-1',
            'supports':'Measured daily air and ground temperatures, pressure and UV category at Gale crater',
            'use':'Off-site observed context. No transfer to Arcadia weather or equipment loads is applied.',
            'selection':f'Most recent {window} available sols; missing sols are not interpolated',
            'quality':'Public summary, not a replacement for calibrated PDS products and their quality flags'}

def ingest_weather(store):
    from .science import fetch,pin
    raw,retrieved=fetch(URL,10_000_000)
    record=parse_weather(raw)
    record['retrieved_at']=retrieved
    return pin(store,'msl-weather',record,raw)

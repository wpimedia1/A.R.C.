"""Public MCD 6.2 client. Climatology is model evidence, never an Arcadia sensor measurement.

Interface and citation: https://www-mars.lmd.jussieu.fr/mars/access.html
Scientific use requires attribution; commercial use requires the publisher's authorization.
"""
import math
import re
import time
from urllib.parse import urlencode, urljoin, urlsplit

BASE = 'https://www-mars.lmd.jussieu.fr/mcd_python/'
VARIABLES = {'Temperature (K)': ('air_temperature_k', 'K'),
             'Surface temperature (K)': ('surface_temperature_k', 'K'),
             'Surface pressure (Pa)': ('surface_pressure_pa', 'Pa')}


def parse(raw):
    text = raw.decode('utf-8')
    version = re.search(r'MCD_v([\d.]+)', text)
    coordinate = re.search(r'Ls ([\d.]+)deg\. Latitude ([-\d.]+)N\. Longitude ([-\d.]+)E\. Altitude ([\d.]+) m ALS', text)
    if not version or not coordinate:
        raise ValueError('MCD output lacks its model version and coordinate header')
    series, current = {}, None
    for line in text.splitlines():
        if 'Column 2 is ' in line:
            label = line.split('Column 2 is ', 1)[1].strip()
            if label not in VARIABLES: raise ValueError('Unsupported MCD variable: '+label)
            current = VARIABLES[label][0]
            series[current] = {'unit': VARIABLES[label][1], 'points': []}
        elif line.strip() and not line.lstrip().startswith('#'):
            if current is None: raise ValueError('MCD values preceded variable definition')
            parts = line.split()
            if len(parts) != 2: raise ValueError('Unexpected MCD column count')
            lt, value = map(float, parts)
            if not 0 <= lt <= 24 or not math.isfinite(value) or value <= 0:
                raise ValueError('Invalid MCD time or physical value')
            series[current]['points'].append({'local_time_h':lt, 'value':value})
    if set(series) != {v[0] for v in VARIABLES.values()}:
        raise ValueError('MCD response did not contain all requested variables')
    for values in series.values():
        points=values['points']
        if len(points)<2 or any(a['local_time_h']>=b['local_time_h'] for a,b in zip(points,points[1:])):
            raise ValueError('MCD time samples are missing or unordered')
        values['minimum']=min(p['value'] for p in points)
        values['maximum']=max(p['value'] for p in points)
    ls,lat,lon,alt=map(float,coordinate.groups())
    return {'model_version':version.group(1),'classification':'climate-model',
            'coordinates':{'latitude':lat,'longitude_east':lon,'altitude_above_surface_m':alt,'ls_deg':ls},
            'variables':series,'transformation_version':'mcd-ascii-labelled-blocks-1',
            'use':'Site climatology for agent planning and environmental experiments; not a current weather measurement or internal equipment temperature.'}


def ingest(store, ls_deg, latitude, longitude_east):
    from .science import fetch, pin
    # One diurnal profile for the current integer Ls, cached by the source fetcher for 24 hours (moderate service use).
    params=dict(var1='t',var2='tsurf',var3='ps',var4='none',latitude=latitude,longitude=longitude_east,
                altitude=1,zkey=3,ls=int(ls_deg)%360,localtime='all',dust=1,hrkey=1,datekeyhtml=1,
                isfixedlt='off',averaging='off',islog='off',iswind='off',dpi=80,colorm='jet',proj='cyl')
    query_url=BASE+'cgi-bin/mcdcgi.py?'+urlencode(params)
    html,_=fetch(query_url,2_000_000)
    match=re.search(r"href=['\"]([^'\"]*/txt/[a-f0-9]+\.txt)['\"]",html.decode('utf-8'))
    if not match: raise ValueError('MCD service returned no ASCII data link')
    data_url=urljoin(query_url,match.group(1))
    if urlsplit(data_url).netloc!=urlsplit(BASE).netloc: raise ValueError('MCD data link changed host')
    raw,retrieved=fetch(data_url,2_000_000)
    record=parse(raw)
    c=record['coordinates']
    if abs(c['latitude']-latitude)>0.0001 or abs(c['longitude_east']-longitude_east)>0.0001 or abs(c['ls_deg']-params['ls'])>0.001:
        raise ValueError('MCD returned a different coordinate or season')
    record.update(title='Arcadia climate model · MCD '+record['model_version'],url=data_url,query_url=query_url,
                  retrieved_at=retrieved,status='published climate model output',
                  supports='Modeled site air temperature, surface temperature and pressure over a local day',
                  attribution='Mars Climate Database © LMD/OU/IAA/ESA/CNES',
                  license_url='https://www-mars.lmd.jussieu.fr/mars/access.html',
                  uncertainty='Climatological interpolation; not an extreme-weather bound, forecast confidence interval, or measured Arcadia weather')
    return pin(store,'arcadia-climate',record,raw)

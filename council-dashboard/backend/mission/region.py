"""Arcadia geography and transformations. Unknown local sensors remain null."""
import math

BOUNDS={'south':33.87,'north':64.17,'west':165.86,'east':210.43,'longitude_convention':'east-positive 0..360'}
MOLA_URN='urn:nasa:pds:context_pds3:data_set:data_set.mgs-m-mola-5-megdr-l3-v1.0_i5cu-m763'
SENSOR_UNITS={'air_temperature':'K','ground_temperature':'K','pressure':'Pa','wind_speed':'m/s','soil_ice_fraction':'kg/kg','soil_bearing_strength':'Pa','local_obstacle_height':'m'}

def local_sensors():
    return {key:{'value':None,'unit':unit,'status':'uninstrumented','observed_at':None,'source_version':None} for key,unit in SENSOR_UNITS.items()}

def coordinates(size=64):
    return [(r,c,BOUNDS['north']-(BOUNDS['north']-BOUNDS['south'])*r/(size-1),
             BOUNDS['west']+(BOUNDS['east']-BOUNDS['west'])*c/(size-1)) for r in range(size) for c in range(size)]

def raster_cell(lat,lon,meta):
    """Use the raster's actual affine map, including longitude seam normalization."""
    scale=meta['ModelPixelScale'];tie=meta['ModelTiepoint'];radius=meta['GeogSemiMajorAxisGeoKey']
    signed=(lon+180)%360-180
    return (math.floor((tie[4]-radius*math.radians(lat))/scale[1]),
            math.floor((radius*math.radians(signed)-tie[3])/scale[0]))

def sample_swim_region(grid,meta,size=64):
    rows=[]
    for r,c,lat,lon in coordinates(size):
        rr,cc=raster_cell(lat,lon,meta)
        value=float(grid[rr,cc]) if 0<=rr<grid.shape[0] and 0<=cc<grid.shape[1] else None
        if value is not None and (not math.isfinite(value) or not -1<=value<=1):value=None
        rows.append({'row':r,'column':c,'latitude':round(lat,6),'longitude':round(lon,6),
                     'value':value,'source_row':rr if value is not None else None,'source_column':cc if value is not None else None,
                     'status':'published estimate' if value is not None else 'no product coverage'})
    return {'bounds':BOUNDS,'grid_size':size,'cells':rows,'valid_count':sum(c['value'] is not None for c in rows),
            'transform':'arcadia-swim-nearest-1','source_pixel_size_m':meta['ModelPixelScale'][:2],
            'interpretation':'Nearest raster samples across the requested region. Null is no coverage, never zero ice.'}

def regional_metrics(heights,latitudes,longitudes):
    """Resolved baseline gradients only; never infer rover-scale slopes."""
    radius=3396190.;slopes=[];valid=[]
    for r,row in enumerate(heights):
        for c,z in enumerate(row):
            if z is None:continue
            valid.append(z)
            for rr,cc in ((r+1,c),(r,c+1)):
                if rr>=len(heights) or cc>=len(row) or heights[rr][cc] is None:continue
                dy=radius*math.radians(latitudes[rr]-latitudes[r])
                dx=radius*math.cos(math.radians((latitudes[r]+latitudes[rr])/2))*math.radians(longitudes[cc]-longitudes[c])
                distance=math.hypot(dx,dy)
                if distance:slopes.append(math.degrees(math.atan(abs(heights[rr][cc]-z)/distance)))
    return {'elevation_min_m':min(valid) if valid else None,'elevation_max_m':max(valid) if valid else None,
            'mean_elevation_m':sum(valid)/len(valid) if valid else None,
            'max_sample_baseline_gradient_deg':max(slopes) if slopes else None,
            'valid_count':len(valid),'gradient_scope':'Between coarse sampled orbital cells; not local slope or traversability',
            'transform_version':'arcadia-regional-gradients-1'}

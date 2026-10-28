"""Bounded HTTP-range sampling of the USGS 463 m MOLA raster.
Never use this regional sample to certify rover-scale traversability.
"""
import io
import json
import hashlib
import time
from pathlib import Path
import httpx

URL='https://planetarymaps.usgs.gov/mosaic/Mars_MGS_MOLA_DEM_mosaic_global_463m.tif'

class RangeFile(io.RawIOBase):
    def __init__(self,url):
        self.url=url;self.position=0;self.total_read=0;self.ranges=[]
        self.client=httpx.Client(timeout=30,follow_redirects=True)
        response=self.client.get(url,headers={'Range':'bytes=0-31'});response.raise_for_status()
        if response.status_code!=206:raise ValueError('Server must support byte ranges')
        self.length=int(response.headers['Content-Range'].split('/')[-1])
    def readable(self):return True
    def seekable(self):return True
    def tell(self):return self.position
    def seek(self,offset,whence=0):
        self.position=offset if whence==0 else self.position+offset if whence==1 else self.length+offset
        return self.position
    def read(self,size=-1):
        if size==0:return b''
        if size<0 or size>2_000_000 or self.total_read+size>25_000_000:raise ValueError('Terrain download safety bound exceeded')
        start=self.position;end=min(self.length-1,start+size-1)
        with self.client.stream('GET',self.url,headers={'Range':f'bytes={start}-{end}'}) as response:
            if response.status_code!=206:raise ValueError('Range response required')
            data=b''.join(response.iter_bytes())
        if len(data)!=end-start+1:raise ValueError('Incomplete byte range')
        self.position+=len(data);self.total_read+=len(data)
        self.ranges.append({'start':start,'length':len(data),'sha256':hashlib.sha256(data).hexdigest()})
        return data

def inspect():
    import tifffile
    stream=RangeFile(URL)
    with tifffile.TiffFile(stream) as tif:
        page=tif.pages[0]
        print('shape',page.shape,'dtype',page.dtype,'compression',page.compression,'rowsperstrip',page.rowsperstrip)
        for name in ('ModelPixelScaleTag','ModelTiepointTag','GeoKeyDirectoryTag'):
            if name in page.tags:print(name,page.tags[name].value)
        print('first strip offsets',page.dataoffsets[:3],page.databytecounts[:3])
    stream.client.close()

def sample():
    import tifffile
    import struct
    stream=RangeFile(URL)
    with tifffile.TiffFile(stream) as tif:
        page=tif.pages[0]
        if page.shape!=(23040,46080) or page.rowsperstrip!=1 or int(page.compression)!=1 or str(page.dtype)!='int16':
            raise ValueError('Raster layout changed; transformation requires review')
        # Equirectangular global raster: longitude -180..180, latitude 90..-90.
        row0,col0=6368,1248
        heights=[]
        for y in range(32):
            stream.seek(page.dataoffsets[row0+y*2]+col0*2)
            row=struct.unpack('<64h',stream.read(128))
            heights.append(list(row[::2]))
        result={'source_url':URL,'source_catalog':'https://astrogeology.usgs.gov/search/map/mars_mgs_mola_dem_463m','retrieved_at':time.time(),
                'classification':'observed regional orbital elevation, resampled','source_resolution_m':page.tags['ModelPixelScaleTag'].value[0],
                'sample_spacing_m':page.tags['ModelPixelScaleTag'].value[0]*2,'grid_size':32,'heights_m':heights,
                'bounds_degrees':{'north':90-row0/128,'south':90-(row0+64)/128,'west':-180+col0/128,'east':-180+(col0+64)/128},
                'transform_version':'mola-int16-range-nearest-1','vertical_datum':'MOLA planetary radius reference; see USGS catalog',
                'warning':'Regional relief only. No local traversability, excavation depth, obstacle or construction-surface claim.',
                'range_receipts':stream.ranges,'downloaded_bytes':stream.total_read}
        result['content_hash']=hashlib.sha256(json.dumps(result,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    stream.client.close()
    target=Path(__file__).resolve().parents[2]/'frontend'/'public'/'evidence'/'arcadia-mola.json'
    target.parent.mkdir(parents=True,exist_ok=True);target.write_text(json.dumps(result),encoding='utf-8')
    print(json.dumps({k:result[k] for k in ('content_hash','bounds_degrees','sample_spacing_m','downloaded_bytes')}))

if __name__=='__main__':sample()

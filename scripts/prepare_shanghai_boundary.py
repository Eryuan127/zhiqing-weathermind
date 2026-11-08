"""Prepare a local WGS84 model-scope boundary from DataV district geometry.
DataV/AMAP data: learning and communication only; no commercial redistribution.
"""
import sys,json,hashlib
from pathlib import Path
from datetime import datetime,timezone
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from services.coord_transform import wgs84_to_gcj02
root=Path(__file__).resolve().parents[1];source=root/'data/shanghai_datav_gcj02.geojson'
if not source.exists():
 import requests
 response=requests.get('https://geo.datav.aliyun.com/areas_v3/bound/310000_full.json',timeout=30);response.raise_for_status();source.write_bytes(response.content)
def inverse(point):
 lon,lat=point;x,y=lon,lat
 for _ in range(6):
  gx,gy=wgs84_to_gcj02(x,y);x-=gx-lon;y-=gy-lat
 return [x,y]
data=json.loads(source.read_text('utf-8'));features=[]
for feature in data['features']:
 geometry=feature['geometry'];polygons=geometry['coordinates'] if geometry['type']=='MultiPolygon' else [geometry['coordinates']]
 features.extend([[inverse(p) for p in ring] for ring in polygon] for polygon in polygons)
result=dict(type='FeatureCollection',features=[dict(type='Feature',properties=dict(name='Shanghai municipality',source='DataV.GeoAtlas / AMAP',purpose='model scope, educational use only'),geometry=dict(type='MultiPolygon',coordinates=features))])
(root/'data/shanghai_boundary.geojson').write_text(json.dumps(result,ensure_ascii=False),'utf-8')
meta=dict(source='https://geo.datav.aliyun.com/areas_v3/bound/310000_full.json',documentation='https://help.aliyun.com/en/datav/datav-7-0/user-guide/datav-geoatlas-widgets/',source_coordinate_system='GCJ-02',output_coordinate_system='WGS84 (iterative approximate inverse)',coordinate_code='wandergis/coordTransform_py (MIT)',license='DataV/AMAP learning and communication only; not cleared for commercial redistribution',districts=len(data['features']),source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),prepared_at=datetime.now(timezone.utc).isoformat(),limitations='Historical third-party geometry, not an authoritative cadastral or current coastline survey')
(root/'data/shanghai_boundary.source.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2),'utf-8')
print('Prepared',len(data['features']),'districts',len(features),'polygons')

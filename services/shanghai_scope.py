"""WGS84 point-in-polygon for the supplied Shanghai municipality boundary.
Boundary is a historical third-party approximation, not a cadastral survey.
"""
import json,math
from pathlib import Path
from functools import lru_cache

@lru_cache(maxsize=1)
def boundary():return json.loads((Path(__file__).resolve().parents[1]/'data/shanghai_boundary.geojson').read_text(encoding='utf-8'))['features'][0]['geometry']

def in_ring(x,y,ring):
    inside=False
    for (ax,ay),(bx,by) in zip(ring,ring[1:]+ring[:1]):
        if abs((x-ax)*(by-ay)-(y-ay)*(bx-ax))<1e-10 and min(ax,bx)-1e-10<=x<=max(ax,bx)+1e-10 and min(ay,by)-1e-10<=y<=max(ay,by)+1e-10:return True
        if (ay>y)!=(by>y) and x<(bx-ax)*(y-ay)/(by-ay)+ax:inside=not inside
    return inside

def contains(latitude,longitude):
    if not isinstance(latitude,(float,int)) or not isinstance(longitude,(float,int)) or not math.isfinite(latitude) or not math.isfinite(longitude):return False
    g=boundary();polygons=g['coordinates'] if g['type']=='MultiPolygon' else [g['coordinates']]
    return any(in_ring(longitude,latitude,p[0]) and not any(in_ring(longitude,latitude,h) for h in p[1:]) for p in polygons)

def sample_points(count=12):
    # Deterministic geographic coverage, never any user's GPS history.
    polygons=boundary()['coordinates'];coords=[p for polygon in polygons for ring in polygon for p in ring]
    minx,maxx=min(p[0] for p in coords),max(p[0] for p in coords);miny,maxy=min(p[1] for p in coords),max(p[1] for p in coords)
    candidates=[];y=miny+.025
    while y<=maxy:
        x=minx+.025
        while x<=maxx:
            if contains(y,x):candidates.append((round(y,5),round(x,5)))
            x+=.05
        y+=.05
    selected=[(31.23,121.47)]
    while len(selected)<count:
        selected.append(max(candidates,key=lambda p:min((p[0]-q[0])**2+((p[1]-q[1])*.855)**2 for q in selected)))
    return [dict(id=f'SH{i+1:02}',latitude=p[0],longitude=p[1]) for i,p in enumerate(selected)]

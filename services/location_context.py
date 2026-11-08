"""Canonical location contract; UI labels are never geocoding inputs."""
import math,time
from zoneinfo import ZoneInfo
LABELS={'当前位置','定位地点','我的位置','当地'}
TTL=21600

def normalize(location):
    if location is None:return None
    if not isinstance(location,dict):raise ValueError('无效定位')
    lat=location.get('latitude');lon=location.get('longitude')
    if isinstance(lat,bool) or isinstance(lon,bool):raise ValueError('无效坐标')
    lat=float(lat);lon=float(lon)
    if not math.isfinite(lat) or not math.isfinite(lon) or not -90<=lat<=90 or not -180<=lon<=180:raise ValueError('无效坐标')
    city=location.get('city',location.get('name'))
    if city is not None and (not isinstance(city,str) or len(city)>100):raise ValueError('无效城市')
    city=city.strip() if city else None
    if city in LABELS:city=None
    source=location.get('source','browser' if not city else 'manual')
    if source not in ('browser','manual'):raise ValueError('无效定位来源')
    granted=location.get('permission_granted',False) is True
    if source=='browser' and not granted:return None
    timestamp=location.get('obtained_at')
    if timestamp is not None and (not isinstance(timestamp,(int,float)) or not 0<=time.time()-timestamp<TTL):return None
    zone=location.get('timezone')
    if zone:ZoneInfo(zone)
    country=location.get('country')
    if country is not None and (not isinstance(country,str) or len(country)>100):raise ValueError('无效国家')
    return dict(latitude=lat,longitude=lon,city=city,country=country,timezone=zone,source=source,permission_granted=granted,obtained_at=timestamp)

def valid_session(ctx):
    return bool(ctx.get('city') and (ctx['city'] not in LABELS or ctx.get('query_method')=='coordinates') and ctx.get('timezone') and isinstance(ctx.get('latitude'),(int,float)) and isinstance(ctx.get('longitude'),(int,float)) and 0<=time.time()-(ctx.get('location_verified_at') or 0)<TTL)

def select(ctx,home,cities):
    ctx=dict(ctx)
    if cities:
        ctx.update(city=cities[0],latitude=None,longitude=None,timezone=None,location_verified_at=None,location_source='explicit',query_method='city_name')
        return ctx,'explicit'
    if valid_session(ctx):return ctx,'session'
    # Preserve temporal/activity preferences independently of location.
    ctx.update(city=None,latitude=None,longitude=None,timezone=None,location_verified_at=None)
    home=normalize(home or None)
    if home:
        ctx.update(city=home['city'] or '定位地点',latitude=home['latitude'],longitude=home['longitude'],timezone=home['timezone'],location_source=home['source'],query_method='coordinates')
        return ctx,'homepage'
    return ctx,'unavailable'


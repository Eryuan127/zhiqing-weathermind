from .http_client import fetch,record
import time,copy,threading
from services import agent_store as store
_CACHE={};_LOCK=threading.Lock();CACHE_TTL=6*3600

def search_locations(name):
    key=name.strip().casefold();now=time.monotonic()
    with _LOCK:
        cached=_CACHE.get(key)
        if cached and now-cached[0]<CACHE_TTL:
            record(dict(service='geocoding',status='cache_hit',cache_age_seconds=round(now-cached[0]),ttl_seconds=CACHE_TTL))
            return copy.deepcopy(cached[1])
    if cached is None:
        persisted=store.cached_locations(key,CACHE_TTL)
        if persisted:
            with _LOCK:_CACHE[key]=(now,copy.deepcopy(persisted))
            record(dict(service='geocoding',status='persistent_cache_hit',ttl_seconds=CACHE_TTL))
            return copy.deepcopy(persisted)
    data=fetch('https://geocoding-api.open-meteo.com/v1/search',{'name':name,'count':20,'language':'zh','format':'json'})
    keys=('id','name','country','country_code','admin1','admin2','latitude','longitude','timezone')
    rows=[{key:row.get(key) for key in keys} for row in data.get('results',[]) if 'latitude' in row and 'longitude' in row and row.get('timezone')]
    rows=[{**row,'_verified_at':time.time()} for row in rows]
    if rows:
        store.cache_locations(key,rows)
        with _LOCK:
            if len(_CACHE)>=128:_CACHE.pop(next(iter(_CACHE)))
            _CACHE[key]=(now,copy.deepcopy(rows))
    return rows

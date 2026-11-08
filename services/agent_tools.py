"""Typed LangChain tools. All weather values carry provenance."""
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
import math
import copy,time,threading
from services.http_client import UpstreamError,record
_WEATHER_CACHE={}
_WEATHER_LOCK=threading.Lock()
WEATHER_CACHE_TTL=300
from langchain_core.tools import tool
from services.weather_service import get_weather
from services.online_ml import predict_online
from services.time_constraints import filter_rows, contains, local_now

def coordinates(latitude,longitude):
    if not math.isfinite(latitude) or not math.isfinite(longitude) or not -90<=latitude<=90 or not -180<=longitude<=180: raise ValueError('无效坐标')
def weather_part(latitude,longitude,part,time_window=None):
    coordinates(latitude,longitude)
    key=(float(latitude),float(longitude));cached=False
    try:
        w=get_weather(latitude,longitude)
        with _WEATHER_LOCK:
            if len(_WEATHER_CACHE)>=128:_WEATHER_CACHE.pop(next(iter(_WEATHER_CACHE)))
            _WEATHER_CACHE[key]=(time.monotonic(),copy.deepcopy(w))
    except UpstreamError:
        with _WEATHER_LOCK:
            entry=_WEATHER_CACHE.get(key)
            if not entry or time.monotonic()-entry[0]>=WEATHER_CACHE_TTL:raise
            w=copy.deepcopy(entry[1]);cached=True
        record(dict(service='weather',status='cache_fallback',ttl_seconds=WEATHER_CACHE_TTL,cache_age_seconds=round(time.monotonic()-entry[0]),call_chain='weather tool → same-coordinate cache'))
        w['warnings']=[*w.get('warnings',[]),'网络查询失败，使用5分钟内同坐标缓存；更新时间保持原值。']
    data=w.get('hourly_extended',w[part]) if part=='hourly' else w[part]
    if time_window and isinstance(data,list): data=filter_rows(data,time_window,daily=part=='daily')
    return dict(status='ok',source=w['source'],updated_at=w['current']['time'],timezone=w['timezone'],data=data,warnings=w['warnings'],cached=cached)
@tool
def get_current_weather(latitude:float,longitude:float,time_window:dict|None=None)->dict:
    """当前天气，摄氏度、km/h；Open-Meteo，连接5秒/读取20秒超时。"""
    return weather_part(latitude,longitude,'current',time_window)
@tool
def get_hourly_forecast(latitude:float,longitude:float,time_window:dict|None=None)->dict:
    """未来72小时预报，Open-Meteo，连接5秒/读取20秒超时。"""
    return weather_part(latitude,longitude,'hourly',time_window)
@tool
def get_daily_forecast(latitude:float,longitude:float,time_window:dict|None=None)->dict:
    """未来7日预报，Open-Meteo，连接5秒/读取20秒超时。"""
    return weather_part(latitude,longitude,'daily',time_window)
@tool
def predict_next_hour_temperature(latitude:float,longitude:float,time_window:dict|None=None)->dict:
    """本地小时模型实验性在线推理；不可用时prediction为空，绝不使用日均历史回放。"""
    coordinates(latitude,longitude)
    if time_window:
        from datetime import timedelta
        expected=local_now(time_window['timezone']).replace(minute=0,second=0,microsecond=0)+timedelta(hours=1)
        if not time_window.get('target_time') or datetime.fromisoformat(time_window['target_time'])!=expected:
            return dict(status='unavailable',prediction=None,mode='live_prediction',reason='unsupported_target_time',target_time=time_window.get('target_time'),source='local hourly model')
    return predict_online(latitude,longitude)
@tool
def evaluate_activity(activity:str,weather:dict,preference:str='balanced')->dict:
    """可解释Python规则，非机器学习。temperature°C、wind_speed km/h、precipitation_probability%、code WMO。"""
    if activity not in ['跑步','散步','拍照','骑行']: raise ValueError('不支持的活动')
    required=['temperature','wind_speed','precipitation_probability','code']
    if any(not isinstance(weather.get(k),(int,float)) or not math.isfinite(weather[k]) for k in required):
        return dict(status='unavailable',source='Python activity rules v2',reason='活动评估数据不足')
    t,w,p,c=[weather[k] for k in required]
    if not -100<=t<=70 or w<0 or not 0<=p<=100: raise ValueError('天气参数超出范围')
    # Explicit activity-specific weights; continuous penalties, no artificial jitter.
    config={'跑步':(16,10,0.45,0.35,0.20),'散步':(21,14,0.40,0.40,0.20),'拍照':(20,18,0.20,0.50,0.30),'骑行':(18,12,0.30,0.30,0.40)}
    ideal,scale,wt,wp,ww=config[activity]
    if preference not in ['balanced','wind','temperature','precipitation']:raise ValueError('不支持的评分偏好')
    default_weights=dict(temperature=wt,precipitation=wp,wind=ww)
    if preference!='balanced':
        weights=dict(default_weights);weights[preference]*=3
        total=sum(weights.values());wt,wp,ww=[weights[k]/total for k in ['temperature','precipitation','wind']]
    temperature=max(0,100-abs(t-ideal)*100/scale)
    rain=max(0,100-p)
    wind=max(0,100-w*(4 if activity=='骑行' else 3 if activity=='拍照' else 2.5))
    components=dict(temperature=round(temperature,1),precipitation=round(rain,1),wind=round(wind,1))
    score=round(wt*temperature+wp*rain+ww*wind,1)
    reasons=['按活动适温、降水概率和风速加权']
    if c>=95:score=0;reasons=['雷暴风险，避免户外活动']
    elif t<0 or t>35 or w>=50:score=min(score,30);reasons.append('极端气温或强风，限制户外推荐')
    return dict(status='ok',activity=activity,score=score,components=components,weights=dict(temperature=wt,precipitation=wp,wind=ww),default_weights=default_weights,preference=preference,weight_policy='priority factor 3 then normalize' if preference!='balanced' else 'default activity weights',reasons=reasons,unassessed=['空气质量','光照','路况'],source='Python activity rules v2')
@tool
def rank_time_slots(activity:str,slots:list[dict],time_window:dict|None=None)->dict:
    """按可解释活动规则排序最多48个候选小时，返回完整时间和评分。"""
    if len(slots)>48: raise ValueError('最多48个时间段')
    rows=[]
    for slot in slots:
        if time_window and not contains(slot['time'],time_window):continue
        if (time_window or {}).get('avoid_wind') and slot.get('wind_speed',float('inf'))>=20:continue
        datetime.fromisoformat(slot['time'])
        r=evaluate_activity.invoke(dict(activity=activity,weather=slot,preference=(time_window or {}).get('preference') or 'balanced'))
        if r['status']=='ok': rows.append(dict(time=slot['time'],**r))
    duration=(time_window or {}).get('duration_hours')
    if duration:
        by_time={datetime.fromisoformat(r['time']):r for r in rows};segments=[]
        for start,row in sorted(by_time.items()):
            hours=[by_time.get(start+timedelta(hours=i)) for i in range(duration)]
            end=start+timedelta(hours=duration)
            if any(h is None for h in hours):continue
            if time_window:
                aware_start=start.replace(tzinfo=ZoneInfo(time_window['timezone'])) if start.tzinfo is None else start
                aware_end=end.replace(tzinfo=aware_start.tzinfo)
                if not any(datetime.fromisoformat(r['start'])<=aware_start and aware_end<=datetime.fromisoformat(r['end']) for r in time_window['ranges']):continue
            if (time_window or {}).get('avoid_rain'):
                raw={r['time']:r for r in slots}
                if any(raw[h['time']]['precipitation_probability']>=(time_window or {}).get('rain_threshold',20) or raw[h['time']]['code']>=51 for h in hours):continue
            score=round(sum(h['score'] for h in hours)/duration,1)
            if any(h['score']==0 for h in hours):score=0
            components={k:round(sum(h['components'][k] for h in hours)/duration,1) for k in row['components']}
            segments.append(dict(**{**row,'score':score,'components':components},end_time=end.isoformat(),duration_hours=duration,hours=hours))
        rows=segments
    elif (time_window or {}).get('avoid_rain'):
        raw={r['time']:r for r in slots};rows=[r for r in rows if raw[r['time']]['precipitation_probability']<time_window.get('rain_threshold',20) and raw[r['time']]['code']<51]
    return dict(status='ok' if rows else 'unavailable',reason=None if rows else '没有满足时间窗口、连续时长及天气约束的完整候选时段。',source='Python activity rules v2',data=sorted(rows,key=lambda r:r['score'],reverse=True))

@tool
def get_air_quality_forecast(latitude:float,longitude:float,time_window:dict|None=None)->dict:
    """CAMS空气质量预报，US AQI及PM2.5微克/立方米；不是监测站实测。"""
    from services.air_quality import get_air_quality
    result=get_air_quality(latitude,longitude)
    rows=result['hourly']
    if time_window:rows=filter_rows(rows,time_window)
    return {**result,'data':rows,'warnings':[result['notice']]}

TOOLS={t.name:t for t in [get_current_weather,get_hourly_forecast,get_daily_forecast,predict_next_hour_temperature,evaluate_activity,rank_time_slots,get_air_quality_forecast]}

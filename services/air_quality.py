"""CAMS gridded model air quality, never described as a station observation."""
import math
from datetime import datetime
from services.http_client import fetch,UpstreamError

def get_air_quality(latitude,longitude):
    if not all(isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v) for v in (latitude,longitude)) or not -90<=latitude<=90 or not -180<=longitude<=180:raise ValueError('无效坐标')
    raw=fetch('https://air-quality-api.open-meteo.com/v1/air-quality',dict(latitude=latitude,longitude=longitude,current='us_aqi,pm2_5',hourly='us_aqi,pm2_5',timezone='auto',forecast_days=3))
    zone=raw.get('timezone');current=raw.get('current') or {};hourly=raw.get('hourly') or {}
    try:datetime.fromisoformat(current['time'])
    except (KeyError,TypeError,ValueError):raise UpstreamError('空气质量服务缺少有效时间',service='air_quality')
    def value(v):return v if isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v) and v>=0 else None
    rows=[]
    for i,stamp in enumerate(hourly.get('time',[])):
        row=dict(time=stamp)
        for key in ('us_aqi','pm2_5'):
            values=hourly.get(key,[]);row[key]=value(values[i]) if i<len(values) else None
        rows.append(row)
    return dict(status='ok',source='Open-Meteo / CAMS',standard='US AQI',timezone=zone,updated_at=current['time'],current=dict(time=current['time'],us_aqi=value(current.get('us_aqi')),pm2_5=value(current.get('pm2_5'))),hourly=rows,notice='网格模式估计与预报，非附近监测站实测；US AQI 不等同于中国 AQI。')

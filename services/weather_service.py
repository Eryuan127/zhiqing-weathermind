from datetime import datetime, timedelta
from .http_client import fetch, UpstreamError

def condition(code):
    groups = [([0], '晴', '☀️'), ([1,2], '少云', '🌤️'), ([3], '多云', '☁️'), ([45,48], '雾', '🌫️'), ([51,53,55], '毛毛雨', '🌦️'), ([56,57,66,67], '冻雨', '🌧️'), ([61,63,65], '雨', '🌧️'), ([71,73,75,77,85,86], '雪', '🌨️'), ([80,81,82], '阵雨', '🌦️'), ([95,96,99], '雷暴', '⛈️')]
    for codes, text, icon in groups:
        if code in codes:
            return {'code': code, 'description': text, 'icon': icon}
    return {'code': code, 'description': '未知天气', 'icon': '—'}

def normalize(data):
    cur = data.get('current') or {}
    try:
        now = datetime.fromisoformat(cur['time'])
    except (KeyError, TypeError, ValueError) as exc:
        raise UpstreamError('天气服务缺少有效的当地更新时间，请重试。') from exc
    current = {key: cur.get(source) for key, source in {'is_day':'is_day','time':'time','temperature':'temperature_2m','feels_like':'apparent_temperature','humidity':'relative_humidity_2m','wind_speed':'wind_speed_10m','precipitation':'precipitation'}.items()}
    for key in ('temperature', 'feels_like'):
        if isinstance(current[key], (int, float)):
            current[key] = round(current[key], 1)
    current.update(condition(cur.get('weather_code')))
    warnings = []
    def rows(section, mapping):
        source = data.get(section) or {}
        for i, time in enumerate(source.get('time', [])):
            row = {'time': time}
            for target, key in mapping.items():
                values = source.get(key) or []
                row[target] = values[i] if i < len(values) else None
            for key in ('temperature', 'temperature_max', 'temperature_min'):
                if isinstance(row.get(key), (int, float)):
                    row[key] = round(row[key], 1)
            row.update(condition(row.pop('weather_code')))
            yield row
    hourly = []
    extended = []
    for row in rows('hourly', {'is_day':'is_day','wind_speed':'wind_speed_10m','temperature':'temperature_2m','precipitation_probability':'precipitation_probability','weather_code':'weather_code'}):
        try:
            time = datetime.fromisoformat(row['time'])
        except (ValueError, TypeError):
            continue
        if now <= time < now + timedelta(hours=72):
            extended.append(row)
        if now <= time < now + timedelta(hours=24):
            hourly.append(row)
    daily = list(rows('daily', {'temperature_max':'temperature_2m_max','temperature_min':'temperature_2m_min','precipitation_probability':'precipitation_probability_max','weather_code':'weather_code'}))[:7]
    if len(hourly) < 24 or any(r['temperature'] is None or r['precipitation_probability'] is None or r['code'] is None for r in hourly):
        warnings.append('部分逐小时数据缺失，当前仅展示可用数据。')
    if len(daily) < 7 or any(any(r[k] is None for k in ('temperature_max','temperature_min','precipitation_probability','code')) for r in daily):
        warnings.append('部分每日预报数据缺失。')
    if any(current[k] is None for k in ('temperature','feels_like','humidity','wind_speed','code')):
        warnings.append('部分实时天气数据缺失。')
    return {'timezone': data.get('timezone'), 'current':current, 'hourly':hourly, 'hourly_extended':extended, 'daily':daily, 'warnings':warnings, 'source':'Open-Meteo'}

def get_weather(latitude, longitude):
    return normalize(fetch('https://api.open-meteo.com/v1/forecast', {'latitude':latitude,'longitude':longitude,'timezone':'auto','forecast_days':8,'current':'is_day,temperature_2m,relative_humidity_2m,apparent_temperature,weather_code,wind_speed_10m,precipitation','hourly':'is_day,temperature_2m,precipitation_probability,weather_code,wind_speed_10m','daily':'weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max','temperature_unit':'celsius','wind_speed_unit':'kmh'}))

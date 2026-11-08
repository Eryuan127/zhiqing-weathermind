import pytest
from datetime import datetime,timedelta
from zoneinfo import ZoneInfo
from services import weather_agent as agent
from services.agent_tools import TOOLS
from services.time_constraints import parse_window,contains,merged_slots
NOW=datetime(2026,11,6,18,30,tzinfo=ZoneInfo('Asia/Shanghai'))
@pytest.fixture(autouse=True)
def environment(monkeypatch,tmp_path):
    from services.agent_tools import _WEATHER_CACHE
    _WEATHER_CACHE.clear()
    monkeypatch.setenv('AGENT_DB',str(tmp_path/'agent.sqlite3'));monkeypatch.setenv('AGENT_MODE','rules')
    monkeypatch.setattr('services.time_constraints.local_now',lambda zone:NOW.astimezone(ZoneInfo(zone)))
    monkeypatch.setattr(agent,'local_now',lambda zone:NOW.astimezone(ZoneInfo(zone)))
    monkeypatch.setattr('services.agent_tools.local_now',lambda zone:NOW.astimezone(ZoneInfo(zone)))
    def geo(name):
        return [dict(name=name,latitude=lat,longitude=lon,timezone='Asia/Shanghai')] if name in agent.CITIES else []
    def checked_geo(name):
        if name not in agent.CITIES:return []
        lat,lon=agent.CITIES[name];return [dict(name=name,latitude=lat,longitude=lon,timezone='Asia/Shanghai')]
    monkeypatch.setattr(agent,'search_locations',checked_geo)
    def weather(lat,lon):
        warm=lat>31
        rows=[dict(time=(NOW.replace(tzinfo=None,minute=0)+timedelta(hours=i)).isoformat(),temperature=16 if warm else 28,wind_speed=6 if warm else 20,precipitation_probability=10 if warm else 70,code=0) for i in range(1,73)]
        return dict(source='Open-Meteo',timezone='Asia/Shanghai',current=dict(time=NOW.replace(tzinfo=None).isoformat(),temperature=16,wind_speed=6,description='晴'),hourly=rows,daily=[],warnings=[])
    monkeypatch.setattr('services.agent_tools.get_weather',weather)

@pytest.mark.parametrize('question,days,lo,hi',[
 ('周六上海适合拍照吗？帮我选个时间',{7},6,22),
 ('上海周末适不适合骑行',{7,8},6,22),
 ('明天下午上海适合跑步吗',{7},12,18)])
def test_requested_dates(question,days,lo,hi):
    r=agent.chat(question,question)
    ranked=[t for t in r['tools'] if t['name']=='rank_time_slots']
    assert ranked,r
    for trace in ranked:
        assert 'time_window' in trace['args']
        for row in trace['result']['data']:
            d=datetime.fromisoformat(row['time']);assert d.day in days and lo<=d.hour<hi
    assert '11月' in r['response'] and 'T12:' not in r['response']

def test_future_ml_rejected_before_plan():
    r=agent.chat('far','预测上海下个月15日14点的准确气温')
    assert not r['tools'];assert 'plan_tools' not in r['path'];assert '仅支持' in r['response']
    assert '下一小时结果替代' in r['response']

def test_invalid_city_and_no_fallback():
    r=agent.chat('invalid','查询XYZABC123明天的天气')
    assert r['city']=='XYZABC123';assert not r['tools'];assert '未找到该城市' in r['response']
    assert 'plan_tools' not in r['path']

def test_multiple_cities_have_independent_data():
    r=agent.chat('compare','上海和杭州哪个更适合明天散步')
    calls=[t for t in r['tools'] if t['name']=='get_hourly_forecast']
    assert len(calls)==2 and calls[0]['args']['latitude']!=calls[1]['args']['latitude']
    assert calls[0]['result']['data'][0]['temperature']==16
    assert calls[1]['result']['data'][0]['temperature']==28
    assert '16°C' in r['response'] and '28°C' in r['response']
    assert '上海' in r['response'] and '杭州' in r['response']

def test_follow_evening_preserves_date_city_activity():
    agent.chat('multi','明天下午杭州适合跑步吗')
    r=agent.chat('multi','那晚上呢')
    assert r['city']=='杭州' and r['time_window']['dates']==['2026-11-07']
    trace=r['tools'][-1];assert trace['args']['activity']=='跑步'
    assert all(datetime.fromisoformat(row['time']).day==7 and datetime.fromisoformat(row['time']).hour>=18 for row in trace['result']['data'])

def test_regular_next_hour_uses_real_local_ridge(monkeypatch):
    from services.online_ml import predict_online
    monkeypatch.setattr('services.online_ml.fetch',lambda *a:dict(hourly=dict(time=['2026-11-06T18:00','2026-11-06T17:00','2026-11-05T19:00'],temperature_2m=[16,17,18])))
    monkeypatch.setattr('services.agent_tools.predict_online',lambda lat,lon:predict_online(lat,lon,NOW))
    r=agent.chat('next','预测上海下一小时气温')
    assert r['tools'][0]['name']=='predict_next_hour_temperature'
    assert r['tools'][0]['result']['model']=='hourly_ridge'
    assert '实验性' in r['response'] and '11月6日' in r['response']

@pytest.mark.parametrize('text,days',[('今天',[6]),('明天',[7]),('后天',[8]),('今晚',[6]),('周日',[8]),('下周六',[14]),('下个月15日14点',[15])])
def test_time_parser(text,days):
    window=parse_window(text,'Asia/Shanghai');assert [datetime.fromisoformat(d).day for d in window['dates']]==days

def test_next_week_and_month_rejected():
    for q in ['下周上海适合跑步吗','上海下个月15日天气','昨天上海天气']:
        r=agent.chat(q,q);assert not r['tools'];assert any(w in r['response'] for w in ['超出','过去'])

def test_rank_defends_own_window():
    window=parse_window('周六','Asia/Shanghai',activity='拍照')
    slots=[dict(time=f'2026-11-0{day}T14:00',temperature=20,wind_speed=5,precipitation_probability=0,code=0) for day in [6,7]]
    ranked=TOOLS['rank_time_slots'].invoke(dict(activity='拍照',slots=slots,time_window=window))
    assert len(ranked['data'])==1 and '11-07' in ranked['data'][0]['time']

def test_tool_rejects_far_ml_target(monkeypatch):
    def forbidden(*a):raise AssertionError('must not infer')
    monkeypatch.setattr('services.agent_tools.predict_online',forbidden)
    result=TOOLS['predict_next_hour_temperature'].invoke(dict(latitude=31.23,longitude=121.47,time_window=parse_window('下个月15日14点','Asia/Shanghai',ml=True)))
    assert result['prediction'] is None and result['reason']=='unsupported_target_time'

def test_scoring_continuous_activity_specific_and_safe():
    data=dict(temperature=20,wind_speed=10,precipitation_probability=20,code=0)
    scores=[TOOLS['evaluate_activity'].invoke(dict(activity=a,weather=data)) for a in ['跑步','散步','拍照','骑行']]
    assert len(set(s['score'] for s in scores))>1
    assert all(0<=s['score']<100 and set(s['components'])=={'temperature','precipitation','wind'} for s in scores)
    bad=TOOLS['evaluate_activity'].invoke(dict(activity='跑步',weather={**data,'wind_speed':40,'precipitation_probability':80}))
    assert bad['score']<scores[0]['score']
    assert '光照' in scores[2]['unassessed']

def test_merge_chinese_intervals():
    result=merged_slots([dict(time='2026-11-07T14:00'),dict(time='2026-11-07T15:00'),dict(time='2026-11-07T17:00')])
    assert result=='11月7日（周六）14:00—16:00；11月7日（周六）17:00—18:00'

def test_invalid_calendar_date():
    r=agent.chat('invalid-date','上海下个月32日适合拍照吗');assert not r['tools'];assert '无效' in r['response']

def test_current_not_misread_as_day_before_yesterday():
    assert parse_window('上海当前天气','Asia/Shanghai')['dates']==['2026-11-06']

def test_known_names_disambiguated_by_verified_region(monkeypatch):
    monkeypatch.setattr(agent,'search_locations',lambda name:[dict(name='上海',latitude=27,longitude=100,timezone='Asia/Shanghai'),dict(name='上海',latitude=31.22,longitude=121.46,timezone='Asia/Shanghai')])
    r=agent.chat('geo','上海当前天气')
    assert r['tools'][0]['args']['latitude']==31.22

def test_mixed_valid_invalid_cities(monkeypatch):
    r=agent.chat('mixed','上海和火星哪个更适合明天散步')
    assert not r['tools'] and '未找到该城市' in r['response']

def test_requested_city_geocoder_failure_has_no_default(monkeypatch):
    def fail(name):raise TimeoutError()
    monkeypatch.setattr(agent,'search_locations',fail)
    r=agent.chat('geo-error','上海当前天气')
    assert not r['tools'] and '服务暂时不可用' in r['response']

def test_foreign_timezone_is_used():
    window=parse_window('明天下午','America/New_York')
    assert window['ranges'][0]['start'].endswith('-05:00')
    assert datetime.fromisoformat(window['ranges'][0]['start']).hour==12

def test_weekend_on_sunday_never_monday(monkeypatch):
    sunday=datetime(2026,11,8,9,tzinfo=ZoneInfo('Asia/Shanghai'))
    monkeypatch.setattr('services.time_constraints.local_now',lambda zone:sunday)
    window=parse_window('周末','Asia/Shanghai',activity='骑行')
    assert all(datetime.fromisoformat(r['start']).weekday() in [5,6] for r in window['ranges'])
    assert not contains('2026-11-09T10:00',window)

def test_wrong_model_target_is_rejected(monkeypatch):
    monkeypatch.setattr('services.agent_tools.predict_online',lambda *a:dict(status='experimental',prediction=22,target_time='2026-11-06T20:00',mode='live_prediction'))
    r=agent.chat('wrong-target','预测上海下一小时气温');assert '目标不一致' in r['response']

# Latest manual acceptance regressions: all external services mocked by environment.
@pytest.mark.parametrize('text',["帮我用 Ridge 模型预测上个月15日的气温","误差必须小于0.1°C","MAE RMSE Ridge °C","please help"])
def test_technical_words_never_cities(text):
    from services.city_resolution import extract_cities
    assert extract_cities(text)==[]

def test_temporal_prefix_and_alias_dedup():
    from services.city_resolution import extract_cities,normalize_cities
    assert extract_cities('明天下午上海和杭州哪个更适合跑步？我不喜欢风大的地方。')==['上海','杭州']
    assert normalize_cities(['上海','上海市','杭州',' 杭州市 ','Ridge','C'])==['上海','杭州']

def test_two_cities_do_not_accumulate_previous_city():
    agent.chat('noappend','北京当前天气')
    r=agent.chat('noappend','明天下午上海和杭州哪个更适合跑步')
    assert r['parsed_cities']==['上海','杭州'] and len(r['tools'])==4
    from services.agent_store import connect
    import json
    with connect() as db:record=json.loads(db.execute("SELECT payload FROM events WHERE kind='parse' ORDER BY id DESC LIMIT 1").fetchone()[0])
    assert record['cities']==['上海','杭州']

def test_ridge_previous_month_boundary():
    r=agent.chat('past-ridge','上海帮我用 Ridge 模型预测上个月15日的气温')
    assert r['parsed_cities']==['上海'] and not r['tools']
    assert '仅支持' in r['response'] and r['path'][-1]=='handle_error'

def test_accuracy_guarantee_refused():
    r=agent.chat('precision','预测上海明天14点的准确气温，误差必须小于0.1°C。')
    assert r['parsed_cities']==['上海'] and not r['tools'] and '无法保证' in r['response']

def test_aqi_boundary_no_fake_values():
    r=agent.chat('aqi','上海明天AQI适合跑步吗')
    assert r['parsed_cities']==['上海'] and r['tools'][0]['name']=='get_air_quality_forecast' and 'US AQI' in r['response']

@pytest.mark.parametrize('duration,text',[(2,'选最好的两小时'),(3,'连续三小时'),(1,'一小时左右')])
def test_duration_segments_match_request(duration,text):
    r=agent.chat(text,'上海周六14:00到18:00之间跑步，'+text)
    assert r['time_window']['duration_hours']==duration
    ranking=r['tools'][-1]
    assert ranking['args']['time_window']['ranges'][0]['start'].startswith('2026-11-07T14:00')
    best=ranking['result']['data'][0]
    assert len(best['hours'])==duration
    assert (datetime.fromisoformat(best['end_time'])-datetime.fromisoformat(best['time'])).total_seconds()==duration*3600
    assert datetime.fromisoformat(best['end_time']).hour<=18
    assert all(contains(h['time'],r['time_window']) for h in best['hours'])
    assert '推荐时间段' in r['response']

def test_best_segment_uses_average_not_individual_peaks():
    window=parse_window('周六14:00到18:00之间最好的两小时','Asia/Shanghai',activity='跑步')
    slots=[dict(time=f'2026-11-07T{h}:00',temperature=16,wind_speed=5,precipitation_probability=80 if h==16 else 0,code=0) for h in range(14,18)]
    result=TOOLS['rank_time_slots'].invoke(dict(activity='跑步',slots=slots,time_window=window))
    best=result['data'][0]
    assert best['time']=='2026-11-07T14:00' and best['end_time']=='2026-11-07T16:00:00'
    assert best['score']==round(sum(h['score'] for h in best['hours'])/2,1)

def test_impossible_duration_explained():
    r=agent.chat('impossible','上海周六14:00到16:00之间跑步，连续三小时')
    assert '没有满足' in r['response'] and '实际评估' in r['response']
    assert r['tools'][-1]['result']['data']==[]

def test_missing_hour_does_not_form_continuous_segment():
    window=parse_window('周六14:00到18:00之间连续三小时','Asia/Shanghai',activity='跑步')
    slots=[dict(time=f'2026-11-07T{h}:00',temperature=16,wind_speed=5,precipitation_probability=0,code=0) for h in [14,16,17]]
    assert TOOLS['rank_time_slots'].invoke(dict(activity='跑步',slots=slots,time_window=window))['data']==[]

def test_monday_nine_exact_time_not_any_morning():
    r=agent.chat('monday','下周一上午九点上海适合跑步吗')
    assert r['time_window']['target_time']=='2026-11-09T09:00:00+08:00'
    ranked=r['tools'][-1]['result']['data']
    assert ranked and all(h['time'].startswith('2026-11-09T09:00') for h in ranked)
    assert '11月9日' in r['response'] and '09:00' in r['response']

def test_conditional_rain_returns_dry_hours(monkeypatch):
    def weather(*a):
        rows=[dict(time=f'2026-11-07T{h}:00',temperature=20,wind_speed=5,precipitation_probability=80 if h==14 else 10,code=61 if h==14 else 0) for h in range(12,18)]
        return dict(source='Open-Meteo',timezone='Asia/Shanghai',current=dict(time='2026-11-06T18:30'),hourly=rows,daily=[],warnings=[])
    monkeypatch.setattr('services.agent_tools.get_weather',weather)
    r=agent.chat('rain-condition','明天下午上海下雨的话，尽量不要淋雨')
    assert r['time_window']['avoid_rain']
    assert '条件可能成立' in r['response'] and '不能保证' in r['response']
    assert '12:00—14:00' in r['response'] and '14:00—15:00' not in r['response']

def test_one_city_tool_failure_keeps_other_success(monkeypatch):
    from services.http_client import UpstreamError
    def weather(lat,lon):
        if lat<31:raise UpstreamError('天气API请求超时',kind='timeout',service='weather',error_type='Timeout')
        return dict(source='Open-Meteo',timezone='Asia/Shanghai',current=dict(time='2026-11-06T18:30'),hourly=[dict(time='2026-11-07T14:00',temperature=16,wind_speed=5,precipitation_probability=0,code=0)],daily=[],warnings=[])
    monkeypatch.setattr('services.agent_tools.get_weather',weather)
    r=agent.chat('partial','明天下午上海和杭州哪个更适合跑步')
    assert '上海' in r['response'] and '杭州' in r['response'] and '无法完成完整比较' in r['response']
    assert '16°C' in r['response'] and r['path'][-1]=='generate_response'
    assert any(t['result'].get('kind')=='timeout' for t in r['tools'])

def test_each_normalized_city_geocoded_once(monkeypatch):
    calls=[]
    def geo(name):
        calls.append(name);lat,lon=agent.CITIES[name]
        return [dict(name=name,latitude=lat,longitude=lon,timezone='Asia/Shanghai')]
    monkeypatch.setattr(agent,'search_locations',geo)
    r=agent.chat('unique','明天下午上海市和杭州市哪个更适合跑步')
    assert r['parsed_cities']==['上海','杭州'] and calls==['上海','杭州']

def test_unmet_duration_one_city_does_not_discard_other(monkeypatch):
    def weather(lat,lon):
        hours=[14,15] if lat>31 else [14]
        rows=[dict(time=f'2026-11-07T{h}:00',temperature=16,wind_speed=5,precipitation_probability=0,code=0) for h in hours]
        return dict(source='Open-Meteo',timezone='Asia/Shanghai',current=dict(time='2026-11-06T18:30'),hourly=rows,daily=[],warnings=[])
    monkeypatch.setattr('services.agent_tools.get_weather',weather)
    r=agent.chat('partial-duration','周六14:00到18:00上海和杭州跑步选最好的两小时')
    assert '14:00—16:00' in r['response'] and '无法完成完整比较' in r['response']

def test_graph_records_redacted_network_error_and_never_says_city_missing(monkeypatch):
    from services.http_client import fetch,DIAGNOSTICS
    import requests
    def fail(*a,**k):raise requests.Timeout('private-secret')
    monkeypatch.setattr(requests,'get',fail)
    monkeypatch.setattr(agent,'search_locations',lambda name:fetch('https://geocoding-api.open-meteo.com/v1/search',{'name':name}))
    r=agent.chat('network','上海当前天气')
    assert '超时' in r['response'] and '未找到该城市' not in r['response']
    assert len([d for d in r['service_diagnostics'] if d['service']=='geocoding'])==2 and 'private-secret' not in str(r)
    assert DIAGNOSTICS.get() is None

def test_chinese_clock_without_explicit_city_uses_session():
    agent.chat('clock-session','杭州当前天气')
    r=agent.chat('clock-session','下周一上午九点适合跑步吗')
    assert r['parsed_cities']==['杭州'] and r['city_source']=='session'
    assert r['time_window']['target_time']=='2026-11-09T09:00:00+08:00'

def test_verified_session_skips_redundant_geocoding(monkeypatch):
    first=agent.chat('reuse','上海当前天气')
    def offline(name):raise AssertionError('verified city must not require another lookup')
    monkeypatch.setattr(agent,'search_locations',offline)
    r=agent.chat('reuse','今天适合跑步吗')
    assert r['tools'][-1]['name']=='rank_time_slots'
    assert any(d['status']=='verified_session_reuse' for d in r['service_diagnostics'])

def test_verified_home_coordinates_work_when_geocoder_offline(monkeypatch):
    from services import agent_store
    agent_store.prove_weather_coordinates(31.22222,121.45806,'Asia/Shanghai')
    def offline(name):raise AssertionError('home proof should avoid geocoding')
    monkeypatch.setattr(agent,'search_locations',offline)
    r=agent.chat('home-proof','今天适合跑步吗',dict(name='上海',latitude=31.22222,longitude=121.45806))
    assert r['tools'][-1]['name']=='rank_time_slots'
    assert r['tools'][0]['args']['latitude']==31.22222
    assert any(d['status']=='resolved_coordinates' for d in r['service_diagnostics'])

def test_home_city_name_cannot_substitute_other_coordinates(monkeypatch):
    from services import agent_store
    from services.http_client import UpstreamError
    agent_store.prove_weather_coordinates(30.27,120.15,'Asia/Shanghai')
    def offline(name):raise UpstreamError('城市查询网络失败',kind='network',service='geocoding')
    monkeypatch.setattr(agent,'search_locations',offline)
    r=agent.chat('mismatch','今天适合跑步吗',dict(name='上海',latitude=30.27,longitude=120.15))
    assert not r['tools'] and '名称与坐标不一致' in r['response']

def test_aqi_then_weather_does_not_treat_null_proof_as_valid():
    agent.chat('null-proof','上海AQI')
    r=agent.chat('null-proof','今天适合跑步吗')
    assert r['tools'] and r['city']=='上海'  # AQI now confirms a real resolved location.

def test_invalid_city_cannot_inherit_old_verified_coordinates():
    agent.chat('invalid-after-valid','上海当前天气')
    r=agent.chat('invalid-after-valid','查询XYZABC123明天天气')
    assert not r['tools'] and '未找到' in r['response']
    r2=agent.chat('invalid-after-valid','今天适合跑步吗')
    assert r2['tools'] and r2['city']=='上海'  # Last confirmed city survives an unconfirmed lookup.

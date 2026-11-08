import pytest
from datetime import datetime,timedelta
from zoneinfo import ZoneInfo
from app import create_app
from services import weather_agent as agent
from services.agent_tools import TOOLS
from services.online_ml import predict_online
from ml.hourly import features
@pytest.fixture(autouse=True)
def isolated(tmp_path,monkeypatch):
    from services.agent_tools import _WEATHER_CACHE
    _WEATHER_CACHE.clear()
    monkeypatch.setattr(agent,'search_locations',lambda name:[dict(name=name,latitude=agent.CITIES[name][0],longitude=agent.CITIES[name][1],timezone='Asia/Shanghai')] if name in agent.CITIES else [])
    monkeypatch.setenv('AGENT_DB',str(tmp_path/'agent.sqlite3')); monkeypatch.setenv('AGENT_MODE','rules')
@pytest.fixture
def weather(monkeypatch):
    now=datetime.now(ZoneInfo('Asia/Shanghai')).replace(tzinfo=None,minute=0,second=0,microsecond=0)
    data=dict(source='Open-Meteo',timezone='Asia/Shanghai',current=dict(time=now.isoformat(),temperature=20,description='晴',wind_speed=5),hourly=[dict(time=(now+timedelta(hours=i)).isoformat(),temperature=20,wind_speed=5,precipitation_probability=0,code=0) for i in range(1,25)],daily=[dict(time=now.date().isoformat(),temperature_min=15,temperature_max=22,precipitation_probability=0)],warnings=[])
    monkeypatch.setattr('services.agent_tools.get_weather',lambda *a:data)
    return data
@pytest.mark.parametrize('text,intent',[('上海当前天气','current'),('上海未来7天','daily'),('上海下一小时气温','ml'),('上海几点适合跑步','rank'),('上海明天天气','hourly')])
def test_intent(text,intent): assert agent.parse_request(dict(message=text))['intent']==intent

def test_multiturn(weather):
    now=datetime.now(ZoneInfo('Asia/Shanghai')).replace(tzinfo=None,minute=0,second=0,microsecond=0)
    weather['hourly']=[dict(time=(now+timedelta(hours=i)).isoformat(),temperature=20,wind_speed=5,precipitation_probability=0,code=0) for i in range(1,73)]
    first=agent.chat('a','现在天气怎么样'); assert not first['tools']; assert first['city_source']=='unavailable'
    second=agent.chat('a','上海'); assert '20' in second['response']; assert second['tools'][0]['name']=='get_current_weather'
    third=agent.chat('a','明天几点适合跑步'); assert third['tools'][-1]['name']=='rank_time_slots'
    assert '月' in third['response'] and '推荐时间段' in third['response']

def test_missing_activity(): assert '跑步' in agent.chat('a','上海几点合适')['response']
@pytest.mark.parametrize('name',['get_current_weather','get_hourly_forecast','get_daily_forecast'])
def test_weather_tools(weather,name): assert TOOLS[name].invoke(dict(latitude=31.23,longitude=121.47))['source']=='Open-Meteo'
@pytest.mark.parametrize('name',list(TOOLS)[:4])
def test_bad_coordinates(name):
    with pytest.raises(ValueError): TOOLS[name].invoke(dict(latitude=float('nan'),longitude=0))
def test_activity():
    r=TOOLS['evaluate_activity'].invoke(dict(activity='骑行',weather=dict(temperature=20,wind_speed=5,precipitation_probability=10,code=95)))
    assert r['score']==0 and '雷暴' in r['reasons'][0]
def test_missing_activity_data(): assert TOOLS['evaluate_activity'].invoke(dict(activity='跑步',weather={}))['status']=='unavailable'
def test_hourly_no_leakage():
    t=datetime(2026,11,6,10); h={t-timedelta(hours=n):20 for n in [1,2,24]}; x=features(t,h); h[t]=999; h[t+timedelta(hours=1)]=-999; assert x==features(t,h)
def test_online(monkeypatch):
    now=datetime(2026,11,6,10,30,tzinfo=ZoneInfo('Asia/Shanghai'))
    data={'hourly':{'time':['2026-11-06T10:00','2026-11-06T09:00','2026-11-05T11:00','2026-11-06T11:00'],'temperature_2m':[20,19,18,9999]}}
    monkeypatch.setattr('services.online_ml.fetch',lambda *a:data)
    first=predict_online(31.23,121.47,now); assert first['status']=='experimental' and first['prediction']<100
    data['hourly']['temperature_2m'][-1]=-9999
    assert predict_online(31.23,121.47,now)['prediction']==first['prediction']
    data['hourly']['time']=[]
    assert predict_online(31.23,121.47,now)['prediction'] is None
    assert predict_online(0,0,now)['reason']=='outside_model_scope'
def test_ml_end_to_end(monkeypatch):
    from services.online_ml import predict_online as real
    now=datetime.now(ZoneInfo('Asia/Shanghai')).replace(minute=0,second=0,microsecond=0,tzinfo=None)
    times=[(now-timedelta(hours=h)).isoformat() for h in [0,1,23]]
    monkeypatch.setattr('services.online_ml.fetch',lambda *a:{'hourly':dict(time=times,temperature_2m=[20,19,18])})
    result=agent.chat('ml','上海下一小时气温预测'); assert result['tools'][0]['name']=='predict_next_hour_temperature'; assert '实验性' in result['response']; assert str(result['tools'][0]['result']['prediction']) in result['response']
def test_model_fallback(monkeypatch,weather):
    monkeypatch.setenv('AGENT_MODE','qwen'); monkeypatch.setenv('DASHSCOPE_API_KEY','test'); monkeypatch.setenv('QWEN_FREE_ONLY_CONFIRMED','true')
    def fail(*a,**k): raise TimeoutError('secret-must-not-log')
    monkeypatch.setattr('services.qwen_adapter.ChatOpenAI',fail)
    result=agent.chat('fallback','上海当前天气'); assert result['mode']=='model_unavailable' and '20' in result['response']
    from services.agent_store import connect
    with connect() as db: assert 'secret-must-not-log' not in str(db.execute('SELECT payload FROM events').fetchall())
def test_no_key(monkeypatch,weather):
    monkeypatch.setenv('AGENT_MODE','auto');monkeypatch.delenv('DASHSCOPE_API_KEY',raising=False)
    assert agent.chat('nokey','上海当前天气')['mode']=='missing_key'
def test_failure(monkeypatch):
    def fail(*a): raise TimeoutError()
    monkeypatch.setattr('services.agent_tools.get_weather',fail)
    r=agent.chat('failure','上海当前天气'); assert r['tools'][0]['status']=='error' and '无法' in r['response']
def test_stale(weather):
    weather['current']['time']='2021-01-01T00:00'; assert '过旧' in agent.chat('old','上海当前天气')['response']
def test_replay_rejected(monkeypatch):
    monkeypatch.setattr('services.agent_tools.predict_online',lambda *a:dict(mode='historical_replay',status='ok',prediction=20))
    assert '拒绝' in agent.chat('replay','上海下一小时气温')['response']
def test_web(weather):
    c=create_app().test_client();assert c.get('/assistant').status_code==200
    assert c.post('/api/auth/register',json={'nickname':'测试','password':'password123'}).status_code==201
    assert c.post('/api/agent/chat',json={'message':''}).status_code==400
    assert c.post('/api/agent/chat',json={'message':'上海当前天气'}).status_code==200
    assert c.delete('/api/agent/session').status_code==200
    assert c.post('/api/agent/chat',json={'message':'现在天气'}).json['city_source']=='unavailable'
def test_out_of_range(weather): assert '可用预报范围' in agent.chat('tomorrow','上海后天早上跑步')['response']
@pytest.mark.parametrize('failure',[PermissionError,ConnectionError,TimeoutError])
def test_qwen_api_errors(monkeypatch,weather,failure):
    monkeypatch.setenv('AGENT_MODE','qwen');monkeypatch.setenv('DASHSCOPE_API_KEY','mock');monkeypatch.setenv('QWEN_FREE_ONLY_CONFIRMED','true')
    def fail(*a,**k): raise failure()
    monkeypatch.setattr('services.qwen_adapter.ChatOpenAI',fail)
    assert agent.chat('apierror','上海当前天气')['mode']=='model_unavailable'
def test_free_guard(monkeypatch,weather):
    monkeypatch.setenv('AGENT_MODE','qwen');monkeypatch.setenv('DASHSCOPE_API_KEY','mock');monkeypatch.delenv('QWEN_FREE_ONLY_CONFIRMED',raising=False)
    assert agent.chat('guard','上海当前天气')['mode']=='free_only_not_confirmed'
def test_qwen_tool_call(monkeypatch,weather):
    from types import SimpleNamespace
    monkeypatch.setenv('AGENT_MODE','qwen');monkeypatch.setenv('DASHSCOPE_API_KEY','mock');monkeypatch.setenv('QWEN_FREE_ONLY_CONFIRMED','true')
    class Model:
        def __init__(self,**kwargs): pass
        def bind_tools(self,tools): assert len(tools)==7;return self
        async def astream(self,messages,**kwargs):
            from langchain_core.messages import AIMessageChunk
            yield AIMessageChunk(content='',tool_calls=[dict(name='get_current_weather',args=dict(latitude=0,longitude=0),id='test',type='tool_call')])
    monkeypatch.setattr('services.qwen_adapter.ChatOpenAI',Model)
    r=agent.chat('qwen','上海当前天气');assert r['mode']=='qwen';assert r['tools'][0]['args']['latitude']==31.23
    from services.agent_store import connect
    import json
    with connect() as db:
        logs=[json.loads(row[0]) for row in db.execute("SELECT payload FROM events WHERE kind='tool'")]
    assert logs==r['tools']
def test_missing_values(weather):
    weather['current']['temperature']=None
    assert '不完整' in agent.chat('missing','上海当前天气')['response']
def test_http_timeout(monkeypatch):
    import requests
    from services.http_client import fetch,UpstreamError
    def timeout(*a,**k): assert k['timeout']==(5,20);raise requests.Timeout()
    monkeypatch.setattr('requests.get',timeout)
    with pytest.raises(UpstreamError):fetch('https://api.open-meteo.com/v1/forecast',{})
@pytest.mark.parametrize('q',['预测上海下一小时的气温，并告诉我使用了什么模型。','气温预测模型','使用什么模型','上海下一小时气温'])
def test_targeted_ml_route(q,monkeypatch):
    now=datetime.now(ZoneInfo('Asia/Shanghai')).replace(tzinfo=None,minute=0,second=0,microsecond=0)
    monkeypatch.setattr('services.online_ml.fetch',lambda *a:{'hourly':{'time':[(now-timedelta(hours=h)).isoformat() for h in [0,1,23]],'temperature_2m':[20,19,18]}})
    r=agent.chat(q,'上海'+q); assert r['tools'][0]['name']=='predict_next_hour_temperature';assert 'hourly_ridge' in r['response'];assert '预测状态' in r['response'];assert r['path']==['parse_request','check_context','plan_tools','execute_tools','validate_results','generate_response']

def test_targeted_city_priority(weather):
    home=dict(name='杭州',latitude=30.27,longitude=120.15)
    assert agent.chat('home','现在天气',home)['city']=='杭州'
    assert agent.chat('home','上海天气',home)['city']=='上海'
    assert agent.chat('home','那明天呢？',home)['city']=='上海'
    c=create_app().test_client()
    c.post('/api/auth/register',json={'nickname':'测试','password':'password123'})
    c.post('/api/agent/chat',json={'message':'上海天气'})
    assert c.put('/api/agent/context',json={'city':home}).status_code==200
    assert c.post('/api/agent/chat',json={'message':'现在天气'}).json['city']=='上海'
    assert c.post('/api/agent/chat',json={'message':'北京天气','home_city':home}).json['city']=='北京'

def test_targeted_followup(weather):
    agent.chat('follow','上海');r=agent.chat('follow','那明天呢？')
    assert r['city']=='上海' and r['tools'][0]['name']=='get_hourly_forecast'

def test_targeted_activity_and_compare(weather):
    now=datetime.now(ZoneInfo('Asia/Shanghai')).replace(tzinfo=None,minute=0,second=0,microsecond=0)
    weather['hourly']=[dict(time=(now+timedelta(hours=i)).isoformat(),temperature=20,wind_speed=5,precipitation_probability=10,code=0) for i in range(1,73)]
    for q in ['明天上海适合跑步吗？','明天下午上海适合拍照吗？','上海和杭州哪个更适合明天散步？']:
        r=agent.chat(q,q);assert '推荐时间段' in r['response'];assert '默认活动权重' in r['response']
        assert sum(t['name']=='rank_time_slots' for t in r['tools'])==(2 if '杭州' in q else 1)
        assert len(r['tools'])<=4
    assert '最高评分相同' in r['response']

def test_targeted_rain(weather):
    r=agent.chat('rain','今晚上海会下雨吗？');assert r['tools'][0]['name']=='get_hourly_forecast'
    assert agent.parse_request(dict(message='今晚上海会下雨吗？'))['period']=='晚上'

def test_targeted_qwen_ml(monkeypatch):
    from types import SimpleNamespace
    monkeypatch.setenv('AGENT_MODE','qwen');monkeypatch.setenv('DASHSCOPE_API_KEY','mock');monkeypatch.setenv('QWEN_FREE_ONLY_CONFIRMED','true')
    class Model:
        def __init__(self,**kwargs):pass
        def bind_tools(self,tools):assert any(t.name=='predict_next_hour_temperature' for t in tools);return self
        async def astream(self,m,**kwargs):
            from langchain_core.messages import AIMessageChunk
            yield AIMessageChunk(content='',tool_calls=[dict(name='predict_next_hour_temperature',args={},id='test',type='tool_call')])
    monkeypatch.setattr('services.qwen_adapter.ChatOpenAI',Model)
    monkeypatch.setattr('services.agent_tools.predict_online',lambda *a:dict(mode='live_prediction',status='unavailable',prediction=None,reason='insufficient_as_of_hourly_data',target_time='2026-11-07T00:00',model=None,data_time=None))
    r=agent.chat('qm','预测上海下一小时的气温，并告诉我使用了什么模型。')
    assert r['mode_label']=='Qwen 智能模式';assert '不可预测' in r['response'];assert '缺少预测截止' in r['response']

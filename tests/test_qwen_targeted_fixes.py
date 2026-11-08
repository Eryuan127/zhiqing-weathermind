"""Targeted fixes: Qwen/weather are mocked here. Real tests are in a separate script."""
import json
import pytest
from services import weather_agent as a,qwen_decision as q,agent_store as store
from services.agent_tools import TOOLS
from services.weather_service import normalize
from test_qwen_phase4 import isolated,decision,fake_client

@pytest.mark.parametrize('mode',['rules','qwen'])
def test_running_to_clothing_and_outfit_followup(monkeypatch,mode):
    import services.agent_tools as tools
    original=tools.get_weather
    def weather(*args):
        return {**original(*args),'daily':[
            dict(time='2026-11-07',temperature_min=8,temperature_max=16,precipitation_probability=60),
            dict(time='2026-11-08',temperature_min=12,temperature_max=20,precipitation_probability=0)]}
    monkeypatch.setattr(tools,'get_weather',weather)
    d=decision();d.update(intent='activity',activity='跑步',temporal_text='明天',tools=['get_hourly_forecast','rank_time_slots'])
    monkeypatch.setattr(q,'decide',lambda s:(d.copy(),dict(status='ok')))
    monkeypatch.setattr(q,'explain',lambda s,t:(t,dict(status='ok')))
    first=a.chat('outfit','上海明天适合跑步吗',mode=mode)
    assert first['tools'][-1]['name']=='rank_time_slots'
    # Even a model decision stuck on the previous activity must honor this topic change.
    second=a.chat('outfit','明天适合怎么穿衣服',mode=mode)
    assert second['execution']['intent']=='clothing'
    assert [t['name'] for t in second['tools']]==['get_daily_forecast']
    assert '8～16°C' in second['response'] and '带伞' in second['response']
    assert len(second['response'].split('\n\n'))>=3
    third=a.chat('outfit','单一件长袖加外套怎么样',mode=mode)
    assert third['time_window']['dates']==['2026-11-07']
    assert '长袖加外套可以作为基础搭配' in third['response']
    assert '早晚可能偏冷' in third['response']
    for query in ['我要是单穿一件长袖加长裤会冷吗','我要是单穿一件长衬加长裤会冷吗','长袖长裤不穿外套会冷吗']:
        followup=a.chat('outfit',query,mode=mode)
        assert followup['time_window']['dates']==['2026-11-07']
        assert '早晚可能会冷' in followup['response']
        assert '建议随身带外套' in followup['response']
        assert followup['response']!=second['response']
    fourth=a.chat('outfit','后天穿什么',mode=mode)
    assert fourth['time_window']['dates']==['2026-11-08']

@pytest.mark.parametrize('mode',['qwen','rules'])
@pytest.mark.parametrize('temporal,dates',[
    ('今天',['2026-11-06']),
    ('明天',['2026-11-07']),
    ('后天',['2026-11-08']),
    ('2026-11-09',['2026-11-09']),
    ('周末',['2026-11-07','2026-11-08']),
])
def test_clothing_uses_validated_dates(monkeypatch,mode,temporal,dates):
    import services.agent_tools as tools
    original=tools.get_weather
    daily=[dict(time=date,temperature_min=8,temperature_max=18,precipitation_probability=0)
           for date in ['2026-11-06','2026-11-07','2026-11-08','2026-11-09']]
    def weather(*args):
        return {**original(*args),'daily':daily}
    monkeypatch.setattr(tools,'get_weather',weather)
    d=decision();d.update(intent='clothing',temporal_text=temporal,tools=['get_daily_forecast'])
    monkeypatch.setattr(q,'decide',lambda s:(d.copy(),dict(status='ok')))
    monkeypatch.setattr(q,'explain',lambda s,t:(t,dict(status='ok')))
    result=a.chat('clothing',f'上海{temporal}适合怎么穿衣服',mode=mode)
    assert result['mode']==mode
    assert result['time_window']['dates']==dates
    assert [row['time'] for row in result['tools'][0]['result']['data']]==dates
    assert '缺少预报' not in result['response']
    for date in dates:
        assert a.chinese(date) in result['response']
    assert '8～18°C' in result['response'] and '建议外套与长裤' in result['response']

@pytest.mark.parametrize('message',['帮我写一段 Python 冒泡排序代码','解释一下二分查找','帮我写封求职信'])
def test_scope_does_not_inherit_aqi(monkeypatch,message):
    store.save('s',{'intent':'aqi','activity':'跑步','city':'杭州','preference':'wind'})
    d=decision();d.update(intent='out_of_scope',tools=[],cities=[])
    fake_client(monkeypatch,[dict(name='Decision',args=d)])
    before=store.read('s');r=a.chat('s',message,mode='qwen')
    assert not r['tools'] and r['mode']=='qwen' and '非天气请求' in r['response'] and '空气质量 API' not in r['response']
    assert store.read('s')==before

def test_history_injection_and_clear(monkeypatch):
    store.event('s','conversation',{'message':'我想跑步','response':'已记录'})
    store.event('private','conversation',{'message':'秘密偏好','response':'保密'})
    captured=[]
    class Model:
        def bind_tools(self,*args,**kwargs):return self
        async def astream(self,messages,**kwargs):
            captured.append(json.loads(messages[1].content))
            from types import SimpleNamespace
            d=decision();d.update(intent='recall',tools=[],cities=[])
            from langchain_core.messages import AIMessageChunk
            yield AIMessageChunk(content='',tool_calls=[dict(name='Decision',args=d,id='test',type='tool_call')])
    monkeypatch.setattr(q,'client',lambda **kwargs:Model())
    store.save('s',dict(city='杭州',activity='跑步',preference='wind',time_window={'dates':['2026-11-07'],'period':'下午'}))
    before=store.read('s');r=a.chat('s','我刚才说想做什么运动？',mode='qwen')
    assert '跑步' in r['response'] and '杭州' in r['response'] and '2026-11-07' in r['response'] and '风速优先' in r['response'] and not r['tools']
    assert captured[0]['recent_history'][0]['user']=='我想跑步' and '秘密偏好' not in json.dumps(captured[0],ensure_ascii=False)
    assert store.read('s')==before
    other=a.chat('new','我刚才说想做什么运动？',mode='qwen');assert '尚未记录' in other['response'] and captured[-1]['recent_history']==[]
    store.clear('s');cleared=a.chat('s','我刚才说想做什么运动？',mode='qwen');assert '尚未记录' in cleared['response'] and captured[-1]['recent_history']==[]

@pytest.mark.parametrize('amount',[0,1.4,None])
def test_current_precipitation_complete(monkeypatch,amount):
    monkeypatch.setattr(q,'decide',lambda s:(decision(),dict(status='ok')))
    monkeypatch.setattr(q,'explain',lambda s,t:(t,dict(status='ok')))
    import services.agent_tools as tools
    original=tools.get_weather
    def weather(*args):
        data=original(*args);data['current']['precipitation']=amount;return data
    monkeypatch.setattr(tools,'get_weather',weather)
    r=a.chat('s','上海当前的温度、风速和降水情况',mode='qwen')
    assert '20' in r['response'] and '风速 5' in r['response']
    assert ('降水量数据缺失' in r['response']) if amount is None else (f'{amount} mm' in r['response'])
    assert '降水概率未提供' in r['response']

def test_normalize_keeps_current_precipitation():
    w=normalize({'current':{'time':'2026-11-06T10:30','precipitation':0.3}})
    assert w['current']['precipitation']==0.3

def test_weight_change_is_real_and_safety_preserved():
    weather=dict(temperature=16,wind_speed=25,precipitation_probability=0,code=0)
    default=TOOLS['evaluate_activity'].invoke(dict(activity='跑步',weather=weather))
    wind=TOOLS['evaluate_activity'].invoke(dict(activity='跑步',weather=weather,preference='wind'))
    assert default['weights']==dict(temperature=.45,precipitation=.35,wind=.20)
    assert wind['weights']['wind']>wind['weights']['temperature'] and wind['score']<default['score']
    assert sum(wind['weights'].values())==pytest.approx(1)
    severe=TOOLS['evaluate_activity'].invoke(dict(activity='跑步',weather={**weather,'code':95},preference='wind'));assert severe['score']==0
    with pytest.raises(ValueError):TOOLS['evaluate_activity'].invoke(dict(activity='跑步',weather=weather,preference='unknown'))

def test_preference_passed_to_scores_and_retained(monkeypatch):
    d=decision();d.update(intent='activity',activity='跑步',temporal_text='明天下午',tools=['get_hourly_forecast','rank_time_slots'],preference='wind')
    monkeypatch.setattr(q,'decide',lambda s:(d.copy(),dict(status='ok')))
    monkeypatch.setattr(q,'explain',lambda s,t:(t,dict(status='ok')))
    r=a.chat('s','明天下午上海跑步，风速比温度更重要',mode='qwen')
    assert r['tools'][-1]['result']['data'][0]['preference']=='wind' and '风速优先' in r['response']
    d.update(preference=None,cities=['杭州'])
    r=a.chat('s','换成杭州呢',mode='qwen');assert r['time_window']['preference']=='wind'
    assert store.read('s')['activity']=='跑步' and store.read('s')['preference']=='wind'
    assert store.read('new')=={}

def test_priority_can_change_recommendation():
    slots=[dict(time='2026-11-07T14:00',temperature=16,wind_speed=25,precipitation_probability=0,code=0),dict(time='2026-11-07T15:00',temperature=22,wind_speed=5,precipitation_probability=0,code=0)]
    default=TOOLS['rank_time_slots'].invoke(dict(activity='跑步',slots=slots))
    personal=TOOLS['rank_time_slots'].invoke(dict(activity='跑步',slots=slots,time_window={'preference':'wind','timezone':'Asia/Shanghai','ranges':[{'start':'2026-11-07T12:00+08:00','end':'2026-11-07T18:00+08:00'}]}))
    assert default['data'][0]['time'].endswith('14:00')
    assert personal['data'][0]['time'].endswith('15:00')

def test_bounded_history_order():
    for i in range(12):store.event('s','conversation',{'message':str(i),'response':'ok'})
    assert [r['user'] for r in store.recent_history('s')]==[str(i) for i in range(4,12)]

def test_unrelated_aqi_plan_is_rejected(monkeypatch):
    d=decision();d.update(intent='aqi',tools=[])
    monkeypatch.setattr(q,'decide',lambda s:(d,dict(status='ok')))
    store.save('s',{'intent':'aqi','city':'杭州'})
    r=a.chat('s','解释一下递归算法',mode='qwen')
    assert r['mode']=='qwen_failed' and not r['tools']
    assert '尚未接入空气质量 API' not in r['response'] and store.read('s')['city']=='杭州'

"""Phase 4 unit tests: all Qwen and weather calls in this file are MOCKS."""
import json
from types import SimpleNamespace
from datetime import datetime,timedelta
from zoneinfo import ZoneInfo
import pytest
from services import qwen_decision as q, weather_agent as a, agent_store
from app import create_app

@pytest.fixture(autouse=True)
def isolated(monkeypatch,tmp_path):
    monkeypatch.setenv('AGENT_DB',str(tmp_path/'test.sqlite3'))
    monkeypatch.setenv('AGENT_MODE','rules')
    monkeypatch.setenv('DASHSCOPE_API_KEY','mock-only')
    monkeypatch.setenv('QWEN_MODEL','mock-only')
    monkeypatch.setenv('QWEN_BASE_URL','https://example.invalid/v1')
    monkeypatch.setenv('QWEN_FREE_ONLY_CONFIRMED','true')
    now=datetime(2026,11,6,10,30,tzinfo=ZoneInfo('Asia/Shanghai'))
    monkeypatch.setattr('services.time_constraints.local_now',lambda zone:now)
    monkeypatch.setattr(a,'local_now',lambda zone:now)
    monkeypatch.setattr(a,'search_locations',lambda name:[dict(name=name,latitude=a.CITIES[name][0],longitude=a.CITIES[name][1],timezone='Asia/Shanghai')] if name in a.CITIES else [])
    rows=[dict(time=(now.replace(minute=0,tzinfo=None)+timedelta(hours=i)).isoformat(),temperature=20,wind_speed=5,precipitation_probability=0,code=0) for i in range(73)]
    monkeypatch.setattr('services.agent_tools.get_weather',lambda *args:dict(source='MOCK weather fixture',timezone='Asia/Shanghai',current=dict(time=now.replace(tzinfo=None).isoformat(),temperature=20,wind_speed=5,description='晴'),hourly=rows,daily=[],warnings=[]))

def decision(**kw):
    return dict(cities=['上海'],intent='current',activity=None,temporal_text='今天',avoid_wind=False,tools=['get_current_weather'],**kw)

def fake_client(monkeypatch,calls):
    class Model:
        def bind_tools(self,*args,**kwargs):return self
        async def astream(self,*args,**kwargs):
            from langchain_core.messages import AIMessageChunk
            yield AIMessageChunk(content='',tool_calls=[dict(c,id=c.get('id',str(i)),type='tool_call') for i,c in enumerate(calls)])
    monkeypatch.setattr(q,'client',lambda **kwargs:Model())

@pytest.mark.parametrize('key,reason',[('DASHSCOPE_API_KEY','missing_key'),('QWEN_MODEL','missing_model'),('QWEN_BASE_URL','invalid_base_url'),('QWEN_FREE_ONLY_CONFIRMED','free_only_not_confirmed')])
def test_configuration_missing(monkeypatch,key,reason):
    monkeypatch.delenv(key);assert q.availability()==(False,reason)
    r=a.chat('x','天气',mode='qwen');assert r['mode']=='qwen_failed' and not r['tools']

@pytest.mark.parametrize('status,body,expected',[(401,{},'authentication_or_permission'),(403,{},'authentication_or_permission'),(429,{},'rate_limited'),(429,{'code':'FreeTierQuotaExhausted'},'quota_exhausted'),(400,{'code':'AllocationQuota.FreeTierOnly'},'quota_exhausted')])
def test_api_failures(monkeypatch,status,body,expected):
    class Failure(Exception):status_code=status
    exc=Failure('secret-must-not-log');exc.body=body
    def fail(**kwargs):raise exc
    monkeypatch.setattr(q,'client',fail)
    r=a.chat('x','天气',mode='qwen')
    assert r['execution']['qwen']['error_type']==expected
    assert 'secret-must-not-log' not in json.dumps(r)

@pytest.mark.parametrize('calls',[[dict(name='unknown',args={})],[dict(name='Decision',args={'cities':999})],[]])
def test_invalid_function_call(monkeypatch,calls):
    fake_client(monkeypatch,calls);r=a.chat('x','天气',mode='qwen')
    assert r['mode']=='qwen_failed' and not r['tools']

def test_wrong_tool_policy(monkeypatch):
    d=decision();d['tools']=['predict_next_hour_temperature']
    fake_client(monkeypatch,[dict(name='Decision',args=d)])
    r=a.chat('x','上海天气',mode='qwen');assert not r['tools'] and r['mode']=='qwen_failed'

def test_qwen_multiturn_and_log(monkeypatch):
    decisions=[dict(cities=['上海'],intent='activity',activity='跑步',temporal_text='明天下午',avoid_wind=False,tools=['get_hourly_forecast','rank_time_slots']),dict(cities=['杭州'],intent='activity',activity='跑步',temporal_text='明天下午',avoid_wind=False,tools=['get_hourly_forecast','rank_time_slots']),dict(cities=['杭州'],intent='activity',activity='跑步',temporal_text='晚上',avoid_wind=False,tools=['get_hourly_forecast','rank_time_slots'])]
    contexts=[]
    def decide(state):contexts.append(state['context']);return decisions.pop(0),dict(status='ok')
    monkeypatch.setattr(q,'decide',decide);monkeypatch.setattr(q,'explain',lambda s,t:(t,dict(status='ok')))
    for text in ['我明天下午想在上海跑步','改成杭州呢','那晚上呢']:r=a.chat('x',text,mode='qwen')
    assert contexts[1]['activity']=='跑步' and contexts[2]['city']=='杭州'
    assert r['time_window']['dates']==['2026-11-07'] and r['time_window']['period']=='晚上'
    assert r['mode']=='qwen' and '20' in r['response']
    assert r['execution']['path']==r['path'] and r['request_id']
    assert agent_store.read('other')=={}
    agent_store.clear('x');assert agent_store.read('x')=={}

def test_historical_ridge_no_execution(monkeypatch):
    d=decision();d.update(intent='ml',temporal_text='上个月15日',tools=['predict_next_hour_temperature'])
    fake_client(monkeypatch,[dict(name='Decision',args=d)])
    r=a.chat('x','上海使用Ridge预测上个月15日气温',mode='qwen');assert not r['tools'] and '仅支持' in r['response']

def test_modes(monkeypatch):
    c=create_app().test_client()
    c.post('/api/auth/register',json={'nickname':'测试','password':'password123'})
    assert c.get('/api/agent/config').json['qwen_enabled']
    assert c.post('/api/agent/chat',json={'message':'天气','mode':'invalid'}).status_code==400
    r=c.post('/api/agent/chat',json={'message':'上海当前天气','mode':'rules'}).json
    assert r['mode']=='rules' and r['execution']['qwen'] is None

def test_fact_additions_rejected(monkeypatch):
    fake_client(monkeypatch,[dict(name='EvidenceOrder',args={'paragraph_ids':[0,99]})])
    text,log=q.explain({'message':'天气'},'20°C\n\n仅供参考')
    assert text=='20°C\n\n仅供参考' and log['status']=='error'

def test_unsupported_planned_tool(monkeypatch):
    d=decision();d['tools']=['shell_execute']
    fake_client(monkeypatch,[dict(name='Decision',args=d)])
    r=a.chat('x','天气',mode='qwen');assert r['mode']=='qwen_failed' and not r['tools']

def test_failed_explanation_is_partial_not_success(monkeypatch):
    monkeypatch.setattr(q,'decide',lambda s:(decision(),dict(status='ok')))
    monkeypatch.setattr(q,'explain',lambda s,t:(t,dict(status='error',error_type='rate_limited')))
    r=a.chat('x','上海当前天气',mode='qwen')
    assert r['mode']=='qwen_partial' and '部分执行' in r['mode_label']

def test_activity_change_keeps_date_and_session_isolation():
    a.chat('x','我明天下午想在上海跑步',mode='rules')
    r=a.chat('x','改成拍照呢',mode='rules')
    assert r['execution']['activity']=='拍照' and r['time_window']['dates']==['2026-11-07']
    other=a.chat('new','当前天气',mode='rules')
    assert other['execution']['activity'] is None and other['time_window'] is None and not other['tools']
    agent_store.clear('x')
    after=a.chat('x','当前天气',mode='rules');assert after['execution']['activity'] is None

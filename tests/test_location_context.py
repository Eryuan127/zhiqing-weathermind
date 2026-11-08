"""Deterministic unit regressions; upstream fixtures are NOT live API evidence."""
import time
import pytest
from services import weather_agent as agent
from services import agent_store
from test_agent_constraints import environment,NOW

HOME=dict(latitude=31.22222,longitude=121.45806,city=None,country=None,timezone=None,source='browser',permission_granted=True)

def test_browser_coordinates_never_geocode_display_label(monkeypatch):
 monkeypatch.setattr(agent,'search_locations',lambda name:pytest.fail('coordinate lookup must never geocode '+name))
 r=agent.chat('gps','明天下午会下雨吗？',HOME,mode='rules')
 assert r['execution']['query_method']=='coordinates'
 assert r['execution']['location_source']=='browser'
 assert r['tools'][0]['args']['latitude']==HOME['latitude']
 assert r['time_window']['timezone']=='Asia/Shanghai'
 assert r['time_window']['dates']==['2026-11-07'] and r['time_window']['period']=='下午'

def test_explicit_then_follow_then_date(monkeypatch):
 original=agent.search_locations
 def geo(name):
  if name=='南京':return [dict(name=name,latitude=32.06,longitude=118.79,timezone='Asia/Shanghai')]
  return original(name)
 monkeypatch.setattr(agent,'search_locations',geo)
 first=agent.chat('chain','明天下午杭州会下雨吗？',HOME,mode='rules')
 assert first['city']=='杭州' and first['tools'][0]['args']['latitude']==30.27
 second=agent.chat('chain','那南京呢？',HOME,mode='rules')
 assert second['city']=='南京' and second['time_window']['dates']==first['time_window']['dates']
 assert second['time_window']['period']=='下午'
 third=agent.chat('chain','后天下午呢？',HOME,mode='rules')
 assert third['city']=='南京' and third['time_window']['dates']==['2026-11-08']
 assert third['execution']['intent']=='rain'
 assert agent.chat('chain','明天会下雨吗？',HOME,mode='rules')['city']=='南京'

def test_denied_manual_and_new_session():
 denied={**HOME,'permission_granted':False}
 r=agent.chat('denied','明天下午会下雨吗？',denied,mode='rules')
 assert not r['tools'] and '请告诉我' in r['response']
 manual=dict(city='杭州',latitude=30.27,longitude=120.15,source='manual',permission_granted=False)
 r=agent.chat('manual','明天下午会下雨吗？',manual,mode='rules')
 assert r['city']=='杭州' and r['execution']['query_method']=='coordinates'
 agent.chat('old','明天下午杭州会下雨吗？',HOME,mode='rules')
 new=agent.chat('new','明天下午会下雨吗？',HOME,mode='rules')
 assert new['city']=='定位地点'
 assert not agent.chat('new-empty','明天下午会下雨吗？',mode='rules')['tools']

def test_unknown_city_and_stale_location_are_not_defaulted():
 stale={**HOME,'obtained_at':time.time()-21601}
 assert not agent.chat('stale','明天下午会下雨吗？',stale,mode='rules')['tools']
 assert not agent.chat('unknown','未知市明天天气',HOME,mode='rules')['tools']

@pytest.mark.parametrize('reason',['denied','unsupported','timeout'])
def test_unavailable_reasons_need_city(reason):
 r=agent.chat(reason,'明天下午会下雨吗？',None,mode='rules')
 assert '请告诉我' in r['response'] and not r['tools']

def test_qwen_coordinate_policy(monkeypatch):
 def decision(s):return dict(cities=['当前位置'],intent='hourly',activity=None,temporal_text='明天下午',avoid_wind=False,tools=['get_hourly_forecast']),dict(status='ok')
 monkeypatch.setattr('services.qwen_decision.decide',decision)
 monkeypatch.setattr('services.qwen_decision.explain',lambda state,text:(text,dict(status='ok')))
 r=agent.chat('qwen-location','明天下午会下雨吗？',HOME,mode='qwen')
 assert r['execution']['query_method']=='coordinates' and r['tools'][0]['args']['longitude']==HOME['longitude']


def test_authenticated_api_separates_accounts_and_home_from_session():
 from app import create_app
 app=create_app();a=app.test_client();b=app.test_client()
 assert a.get('/').status_code==200
 assert a.post('/api/agent/chat',json={'message':'明天下午会下雨吗？','home_city':HOME}).status_code==401
 for client in (a,b):assert client.post('/api/auth/register',json={'nickname':'测试','password':'password123'}).status_code==201
 first=a.post('/api/agent/chat',json={'message':'明天下午杭州会下雨吗？','home_city':HOME}).json
 assert first['city']=='杭州'
 assert a.put('/api/agent/context',json={'city':HOME}).status_code==200
 follow=a.post('/api/agent/chat',json={'message':'后天下午呢？','home_city':HOME}).json
 assert follow['city']=='杭州'
 other=b.post('/api/agent/chat',json={'message':'明天下午会下雨吗？'}).json
 assert not other['tools'] and '请告诉我' in other['response']
 assert b.get('/api/agent/conversations/'+first['session_id']).status_code==404
 a.post('/api/agent/conversations')
 new=a.post('/api/agent/chat',json={'message':'明天下午会下雨吗？','home_city':HOME}).json
 assert new['execution']['location_source']=='browser' and new['session_id']!=first['session_id']
 a.post('/api/auth/logout')
 assert a.get('/api/agent/conversations').status_code==401
 assert a.get('/api/auth/me').json['user'] is None


def test_qwen_cannot_replace_afternoon_with_daily(monkeypatch):
 def decision(s):return dict(cities=[],intent='daily',activity=None,temporal_text='明天下午',avoid_wind=False,tools=['get_daily_forecast']),dict(status='ok')
 monkeypatch.setattr('services.qwen_decision.decide',decision)
 r=agent.chat('wrong-granularity','明天下午会下雨吗？',HOME,mode='qwen')
 assert not r['tools'] and r['mode']=='qwen_failed' and '全天' in r['response']


def test_legacy_display_label_is_not_a_confirmed_city():
 agent_store.save('legacy',dict(city='当前位置',latitude=HOME['latitude'],longitude=HOME['longitude'],timezone='Asia/Shanghai',location_verified_at=time.time()))
 r=agent.chat('legacy','明天下午会下雨吗？',HOME,mode='rules')
 assert r['execution']['query_method']=='coordinates' and r['city']=='定位地点'
 r=agent.chat('ui-label','当前位置明天下午会下雨吗？',HOME,mode='rules')
 assert r['execution']['query_method']=='coordinates' and r['tools']


def test_browser_resolved_city_does_not_snap_gps_to_city_center(monkeypatch):
 from services.http_client import UpstreamError
 monkeypatch.setattr(agent,'search_locations',lambda name:pytest.fail('GPS must not be re-geocoded'))
 home={**HOME,'city':'上海','latitude':31.9}
 r=agent.chat('city-boundary','明天下午会下雨吗？',home,mode='rules')
 assert r['tools'] and r['tools'][0]['args']['latitude']==31.9
 assert r['city']=='上海' and r['execution']['query_method']=='coordinates'

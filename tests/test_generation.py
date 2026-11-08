import threading,uuid,json
from app import create_app
from services import agent_store as store

def clients(tmp_path,monkeypatch):
 monkeypatch.setenv('AGENT_DB',str(tmp_path/'gen.db'));app=create_app();a=app.test_client();b=app.test_client()
 for c in (a,b):c.post('/api/auth/register',json={'nickname':'测试','password':'password123'})
 sid=a.get('/api/agent/conversations').json['active_id']
 return app,a,b,sid

def test_cancel_during_work_never_commits_late_reply(tmp_path,monkeypatch):
 app,a,b,sid=clients(tmp_path,monkeypatch);entered=threading.Event();release=threading.Event();rid=str(uuid.uuid4());results=[]
 def work(sid,*args,**kwargs):
  store.save(sid,{'city':'不应保存'});store.event(sid,'conversation',{'message':'hi','response':'不应出现'})
  entered.set();assert release.wait(5);return {'response':'不应出现'}
 monkeypatch.setattr('agent_routes.chat',work)
 cookie=a.get_cookie('session').value
 def run():
  client=app.test_client();client.set_cookie('session',cookie);results.append(client.post('/api/agent/chat',json={'message':'hi','client_request_id':rid}))
 t=threading.Thread(target=run);t.start();assert entered.wait(5)
 assert b.post(f'/api/agent/generations/{rid}/cancel',json={}).status_code==404
 assert a.post(f'/api/agent/generations/{rid}/cancel',json={}).json['stopped']
 release.set();t.join(5);assert not t.is_alive()
 assert results[0].status_code==409 and store.transcript(sid)==[] and store.read(sid)=={} and store.recent_history(sid)==[]

def test_cancel_before_start_and_after_complete(tmp_path,monkeypatch):
 app,a,b,sid=clients(tmp_path,monkeypatch)
 def work(sid,*args,**kwargs):
  store.save(sid,{'city':'上海'});store.event(sid,'conversation',{'message':'hi','response':'完整回复'});return {'response':'完整回复'}
 monkeypatch.setattr('agent_routes.chat',work)
 early=str(uuid.uuid4());a.post(f'/api/agent/generations/{early}/cancel',json={})
 assert a.post('/api/agent/chat',json={'message':'hi','client_request_id':early}).status_code==409
 rid=str(uuid.uuid4());r=a.post('/api/agent/chat',json={'message':'hi','client_request_id':rid});assert r.status_code==200
 a.post(f'/api/agent/generations/{rid}/cancel',json={'visible':'完整'})
 assert store.transcript(sid)==[]
 assert store.recent_history(sid)==[] and store.read(sid)=={}
 assert a.get('/api/agent/conversations').json['conversations']==[]

def test_reply_edit_overlay_is_owned_and_preserves_evidence(tmp_path,monkeypatch):
 app,a,b,sid=clients(tmp_path,monkeypatch);monkeypatch.setattr('agent_routes.chat',lambda *a,**k:dict(response='原始回复',tools=[{'evidence':'真实依据'}]))
 reply=a.post('/api/agent/chat',json={'message':'hi'}).json;url=f"/api/agent/conversations/{sid}/turns/{reply['turn_id']}"
 assert b.patch(url,json={'text':'他人修改'}).status_code==404
 assert a.patch(url,json={'text':'个人修订'}).status_code==200
 turn=store.transcript(sid)[0];assert turn['reply']['response']=='个人修订' and turn['reply']['edited']
 with store.connect() as db:assert json.loads(db.execute('SELECT response FROM conversation_turns WHERE id=?',(reply['turn_id'],)).fetchone()[0])['response']=='原始回复'


def test_clear_removes_edit_and_cancels_running_requests(tmp_path,monkeypatch):
 app,a,b,sid=clients(tmp_path,monkeypatch);monkeypatch.setattr('agent_routes.chat',lambda *a,**k:dict(response='原文'))
 old=a.post('/api/agent/chat',json={'message':'原问题'}).json
 a.patch(f"/api/agent/conversations/{sid}/turns/{old['turn_id']}",json={'text':'私密修订'})
 a.delete('/api/agent/session')
 a.post('/api/agent/chat',json={'message':'新问题'})
 assert store.transcript(sid)[0]['reply']['response']=='原文' and not store.transcript(sid)[0]['reply'].get('edited')


def test_real_graph_stops_before_next_tool_after_cancel(tmp_path,monkeypatch):
 app,a,b,sid=clients(tmp_path,monkeypatch);entered=threading.Event();release=threading.Event();calls=[];results=[];rid=str(uuid.uuid4())
 def geocode(name):
  entered.set();assert release.wait(5)
  return [dict(name='上海',latitude=31.23,longitude=121.47,timezone='Asia/Shanghai')]
 def forecast(*args):calls.append(args);raise AssertionError('cancelled graph must not query weather')
 monkeypatch.setattr('services.weather_agent.search_locations',geocode);monkeypatch.setattr('services.agent_tools.get_weather',forecast)
 cookie=a.get_cookie('session').value
 def run():
  client=app.test_client();client.set_cookie('session',cookie);results.append(client.post('/api/agent/chat',json={'message':'上海当前天气','mode':'rules','client_request_id':rid}))
 thread=threading.Thread(target=run);thread.start();assert entered.wait(5)
 assert a.post(f'/api/agent/generations/{rid}/cancel',json={}).status_code==200
 release.set();thread.join(5);assert not thread.is_alive()
 assert results[0].status_code==409 and calls==[] and store.transcript(sid)==[]

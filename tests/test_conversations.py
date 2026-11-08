import pytest
from app import create_app
from services import agent_store
@pytest.fixture
def app(tmp_path,monkeypatch):
    monkeypatch.setenv('AGENT_DB',str(tmp_path/'history.sqlite3'));monkeypatch.setenv('AGENT_MODE','rules')
    return create_app()

def test_create_switch_restore_and_separate_context(app):
    c=signed_client(app);first=c.get('/api/agent/conversations').json['active_id']
    reply=c.post('/api/agent/chat',json={'message':'上海AQI怎么样'}).json
    assert reply['session_id']==first
    second=c.post('/api/agent/conversations').json['active_id'];assert second!=first
    assert agent_store.read(second)=={}
    c.post('/api/agent/chat',json={'message':'杭州AQI怎么样'})
    listing=c.get('/api/agent/conversations').json
    assert len(listing['conversations'])==2 and listing['active_id']==second
    assert {r['title'] for r in listing['conversations']}=={'上海AQI怎么样','杭州AQI怎么样'}
    data=c.put(f'/api/agent/conversations/{first}/activate').json
    assert data['turns'][0]['message']=='上海AQI怎么样' and data['turns'][0]['reply']==reply
    assert c.get('/api/agent/conversations').json['active_id']==first
    assert agent_store.read(first)['city']=='上海' and agent_store.read(second)['city']=='杭州'

def test_history_cannot_be_read_or_activated_by_other_browser(app):
    a=signed_client(app);b=signed_client(app)
    aid=a.get('/api/agent/conversations').json['active_id']
    bid=b.get('/api/agent/conversations').json['active_id']
    assert aid!=bid
    assert b.get(f'/api/agent/conversations/{aid}').status_code==404
    assert b.put(f'/api/agent/conversations/{aid}/activate').status_code==404
    assert len(b.get('/api/agent/conversations').json['conversations'])==0

def test_clear_affects_only_active_conversation(app):
    c=signed_client(app);first=c.get('/api/agent/conversations').json['active_id']
    c.post('/api/agent/chat',json={'message':'上海AQI'})
    second=c.post('/api/agent/conversations').json['active_id']
    c.post('/api/agent/chat',json={'message':'杭州AQI'})
    assert c.delete('/api/agent/session').status_code==200
    assert not c.get(f'/api/agent/conversations/{second}').json['turns']
    assert c.get(f'/api/agent/conversations/{first}').json['turns']

def test_history_and_browser_cookie_survive_app_restart(app):
    c=signed_client(app);id=c.get('/api/agent/conversations').json['active_id']
    c.post('/api/agent/chat',json={'message':'上海AQI'})
    cookie=c.get_cookie('session')
    new_app=create_app();assert app.secret_key==new_app.secret_key
    fresh=signed_client(new_app);fresh.set_cookie('session',cookie.value)
    assert fresh.get('/api/agent/conversations').json['active_id']==id
    assert fresh.get(f'/api/agent/conversations/{id}').json['turns'][0]['message']=='上海AQI'

def test_compact_is_separate_limited_and_can_continue_in_full_chat(app,monkeypatch):
    monkeypatch.setattr('agent_routes.chat',lambda sid,message,home,**kwargs:dict(response='收到：'+message,session_id=sid))
    c=signed_client(app);original=c.get('/api/agent/conversations').json['active_id']
    c.post('/api/agent/chat',json={'message':'原来的大聊天'})
    compact=c.post('/api/agent/compact').json['id']
    assert compact!=original and agent_store.read(compact)=={}
    assert not c.get(f'/api/agent/conversations/{compact}').json['turns']
    assert c.get('/api/agent/conversations').json['active_id']==original
    for i in range(5):
        r=c.post(f'/api/agent/compact/{compact}/chat',json={'message':f'第{i+1}问'})
        assert r.status_code==200 and r.json['remaining']==4-i
    rejected=c.post(f'/api/agent/compact/{compact}/chat',json={'message':'第六问'})
    assert rejected.status_code==409 and rejected.json['limit_reached']
    assert len(agent_store.transcript(compact))==5
    assert len(agent_store.transcript(original))==1
    assert signed_client(app).post(f'/api/agent/compact/{compact}/chat',json={'message':'其他浏览器'}).status_code==404
    assert c.put(f'/api/agent/conversations/{compact}/activate').status_code==200
    assert c.post('/api/agent/chat',json={'message':'大聊天继续第六问'}).status_code==200
    assert len(agent_store.transcript(compact))==6
    assert c.post('/api/agent/compact').json['id']!=compact


def signed_client(app):
    client=app.test_client()
    assert client.post('/api/auth/register',json={'nickname':'测试用户','password':'test-password'}).status_code==201
    return client


def test_empty_drafts_not_history_and_new_reuses_draft(app,monkeypatch):
 c=signed_client(app);first=c.get('/api/agent/conversations').json['active_id']
 for _ in range(4):assert c.post('/api/agent/conversations').json['active_id']==first
 assert c.get('/api/agent/conversations').json['conversations']==[]
 c.post('/api/agent/compact');assert c.get('/api/agent/conversations').json['conversations']==[]
 monkeypatch.setattr('agent_routes.chat',lambda *args,**kwargs:dict(response='完成'))
 c.post('/api/agent/chat',json={'message':'已完成的问题'})
 assert len(c.get('/api/agent/conversations').json['conversations'])==1
 import uuid
 rid=str(uuid.uuid4());c.post('/api/agent/chat',json={'message':'取消的问题','client_request_id':rid})
 c.post('/api/agent/generations/'+rid+'/cancel',json={})
 assert len(agent_store.transcript(first))==1
 assert c.get('/api/agent/conversations').json['conversations'][0]['title']=='已完成的问题'

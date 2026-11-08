from app import create_app
from services.agent_store import connect

def test_account_access_and_isolation(tmp_path,monkeypatch):
 monkeypatch.setenv('AGENT_DB',str(tmp_path/'auth.sqlite3'))
 app=create_app();a=app.test_client();b=app.test_client()
 assert a.get('/').status_code==200
 assert a.get('/api/auth/me').json['user'] is None
 assert a.post('/api/agent/chat',json={'message':'hi'}).status_code==401
 assert a.get('/assistant?embedded=1').status_code==401
 assert a.post('/api/auth/login',json={'account':'missing','password':'invalid-password'}).status_code==401
 r=a.post('/api/auth/register',json={'nickname':'小晴','password':'password123'})
 assert r.status_code==201
 account=r.json['user']['account'];assert any(x.isdigit() for x in account)
 first=a.get('/api/agent/conversations').json['active_id']
 assert '你好，小晴' in a.get('/assistant?embedded=1').text
 with connect() as db:assert db.execute('SELECT password FROM users').fetchone()[0]!='password123'
 assert b.post('/api/auth/register',json={'nickname':'另一个','password':'password123'}).status_code==201
 assert b.get(f'/api/agent/conversations/{first}').status_code==404
 assert a.post('/api/auth/logout',json={}).status_code==200
 assert a.get('/api/agent/conversations').status_code==401
 assert a.post('/api/auth/login',json={'account':account,'password':'wrong'}).status_code==401
 assert a.post('/api/auth/login',json={'account':account,'password':'password123'}).status_code==200
 assert a.get(f'/api/agent/conversations/{first}').status_code==200
 assert a.post('/api/auth/logout',json={},headers={'Origin':'https://other.example'}).status_code==403

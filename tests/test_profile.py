import io,sqlite3
from PIL import Image
from app import create_app

def test_profile_alias_avatar_and_old_data(tmp_path,monkeypatch):
 path=tmp_path/'profile.db';monkeypatch.setenv('AGENT_DB',str(path))
 from werkzeug.security import generate_password_hash
 with sqlite3.connect(path) as db:
  db.execute('CREATE TABLE users (id TEXT PRIMARY KEY,nickname TEXT NOT NULL,password TEXT NOT NULL)')
  db.execute('INSERT INTO users VALUES (?,?,?)',('Sky12345678','旧昵称',generate_password_hash('password123')))
 app=create_app();a=app.test_client();b=app.test_client()
 assert a.patch('/api/auth/profile',json={'nickname':'冒用'}).status_code==401
 assert a.post('/api/auth/login',json={'account':'Sky12345678','password':'password123'}).status_code==200
 old=a.get('/api/auth/me').json['user'];assert old['legacy_account']
 conversation=a.get('/api/agent/conversations').json['active_id']
 r=a.patch('/api/auth/profile',json={'account':'my_weather','nickname':'新昵称'})
 assert r.status_code==200 and r.json['user']['account']==old['account']
 assert a.get('/api/agent/conversations').json['active_id']==conversation
 a.post('/api/auth/logout')
 for name in ['MY_WEATHER','Sky12345678']:
  assert a.post('/api/auth/login',json={'account':name,'password':'password123'}).status_code==200
 r=b.post('/api/auth/register',json={'account':'fresh_user','nickname':'新注册','password':'password123'})
 assert r.status_code==201 and r.json['user']['login_account']=='fresh_user'
 assert b.post('/api/auth/register',json={'account':'My_Weather','nickname':'重复','password':'password123'}).status_code==409
 assert b.patch('/api/auth/profile',json={'account':'sky12345678'}).status_code==409
 assert b.post('/api/auth/register',json={'account':'bad name','nickname':'错误','password':'password123'}).status_code==400
 assert a.post('/api/auth/avatar',data={'avatar':(io.BytesIO(b'<svg></svg>'),'bad.png')}).status_code==400
 image=Image.new('RGB',(320,160),'blue');raw=io.BytesIO();image.save(raw,format='PNG');raw.seek(0)
 r=a.post('/api/auth/avatar',data={'avatar':(raw,'avatar.png')});assert r.status_code==200
 url=r.json['user']['avatar_url'];assert url
 response=a.get(url);assert response.status_code==200 and response.mimetype=='image/png'
 with Image.open(io.BytesIO(response.data)) as saved:assert saved.size==(128,128)
 assert b.get(url).status_code==404
 assert a.post('/api/auth/avatar',data={'avatar':(io.BytesIO(b'x'*(1024*1024+1)),'big.png')}).status_code==413
 assert a.delete('/api/auth/avatar').json['user']['avatar_url'] is None
 assert b.get('/api/auth/me').json['user']['nickname']=='新注册'
 assert a.patch('/api/auth/profile',json={'nickname':'  '}).status_code==400
 assert a.patch('/api/auth/profile',json={'nickname':'禁止'},headers={'Origin':'https://example.com'}).status_code==403

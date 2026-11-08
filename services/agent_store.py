"""SQLite state and separate model/tool experiment events; no exception/key logging."""
import sqlite3,json,os
from contextlib import contextmanager
from pathlib import Path
from datetime import datetime,timezone

@contextmanager
def connect():
    path=os.getenv('AGENT_DB',str(Path(__file__).resolve().parents[1]/'data/agent.sqlite3'))
    db=sqlite3.connect(path,timeout=10)
    db.execute('CREATE TABLE IF NOT EXISTS sessions (id TEXT PRIMARY KEY, state TEXT)')
    db.execute('CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY, session TEXT, kind TEXT, payload TEXT, time TEXT)')
    db.execute('CREATE TABLE IF NOT EXISTS conversations (id TEXT PRIMARY KEY, owner TEXT NOT NULL, title TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)')
    db.execute('CREATE INDEX IF NOT EXISTS conversation_owner ON conversations(owner,updated_at)')
    db.execute('CREATE TABLE IF NOT EXISTS conversation_turns (id INTEGER PRIMARY KEY, session TEXT NOT NULL, message TEXT NOT NULL, response TEXT NOT NULL)')
    db.execute('CREATE TABLE IF NOT EXISTS location_cache (name TEXT PRIMARY KEY, payload TEXT NOT NULL, verified_at REAL NOT NULL)')
    db.execute('CREATE TABLE IF NOT EXISTS weather_location_proofs (latitude REAL, longitude REAL, timezone TEXT NOT NULL, verified_at REAL NOT NULL, PRIMARY KEY(latitude,longitude))')
    try:
        with db:
            yield db
    finally:
        db.close()

def read(sid):
    with connect() as db:
        r=db.execute('SELECT state FROM sessions WHERE id=?',(sid,)).fetchone()
    return json.loads(r[0]) if r else {}
def save(sid,state):
    from services.generation import context,checkpoint
    if context.get():
        checkpoint();context.get()['states'][sid]=state;return
    with connect() as db: db.execute('INSERT OR REPLACE INTO sessions VALUES (?,?)',(sid,json.dumps(state,ensure_ascii=False)))
def event(sid,kind,payload):
    from services.generation import context,checkpoint
    if context.get():
        checkpoint();payload={**payload,'client_request_id':context.get()['id']};context.get()['events'].append((sid,kind,payload));return
    with connect() as db: db.execute('INSERT INTO events(session,kind,payload,time) VALUES (?,?,?,?)',(sid,kind,json.dumps(payload,ensure_ascii=False),datetime.now(timezone.utc).isoformat()))
def clear(sid):
    with connect() as db:
        from services.generation import table
        table(db);db.execute("UPDATE generations SET cancelled=1,status='cancelled' WHERE sid=? AND status='running'",(sid,))
        db.execute('CREATE TABLE IF NOT EXISTS reply_edits (turn_id INTEGER PRIMARY KEY, text TEXT)')
        db.execute('DELETE FROM reply_edits WHERE turn_id IN (SELECT id FROM conversation_turns WHERE session=?)',(sid,))
        db.execute('DELETE FROM sessions WHERE id=?',(sid,)); db.execute('DELETE FROM events WHERE session=?',(sid,)); db.execute('DELETE FROM conversation_turns WHERE session=?',(sid,))


def ensure_conversation(owner,sid=None):
    import uuid
    sid=sid or str(uuid.uuid4());now=datetime.now(timezone.utc).isoformat()
    with connect() as db:
        row=db.execute('SELECT owner FROM conversations WHERE id=?',(sid,)).fetchone()
        if row and row[0]!=owner:sid=str(uuid.uuid4());row=None
        if not row:db.execute('INSERT INTO conversations VALUES (?,?,?,?,?)',(sid,owner,'新会话',now,now))
    return sid

def list_conversations(owner):
    with connect() as db:
        rows=db.execute("SELECT id,title,created_at,updated_at FROM conversations WHERE owner=? AND EXISTS (SELECT 1 FROM conversation_turns t WHERE t.session=conversations.id AND COALESCE(json_extract(t.response,'$.stopped'),0)=0) ORDER BY updated_at DESC,id DESC",(owner,)).fetchall()
    return [dict(zip(['id','title','created_at','updated_at'],r)) for r in rows]

def owned(owner,sid):
    with connect() as db:return db.execute('SELECT 1 FROM conversations WHERE id=? AND owner=?',(sid,owner)).fetchone() is not None

def append_turn(sid,message,response):
    with connect() as db:
        db.execute('INSERT INTO conversation_turns(session,message,response) VALUES (?,?,?)',(sid,message,json.dumps(response,ensure_ascii=False)))
        first=db.execute('SELECT message FROM conversation_turns WHERE session=? ORDER BY id LIMIT 1',(sid,)).fetchone()[0]
        db.execute('UPDATE conversations SET title=?,updated_at=? WHERE id=?',(' '.join(first.split())[:32],datetime.now(timezone.utc).isoformat(),sid))

def transcript(sid):
    with connect() as db:
        db.execute('CREATE TABLE IF NOT EXISTS reply_edits (turn_id INTEGER PRIMARY KEY, text TEXT)')
        rows=db.execute('SELECT t.id,t.message,t.response,e.text FROM conversation_turns t LEFT JOIN reply_edits e ON e.turn_id=t.id WHERE t.session=? ORDER BY t.id',(sid,)).fetchall()
    result=[]
    for turn_id,message,response,edited in rows:
        reply=json.loads(response)
        if edited is not None and not reply.get('stopped'):reply={**reply,'response':edited,'edited':True}
        result.append(dict(id=turn_id,message=message,reply=reply))
    return result


def reset_conversation(sid):
    clear(sid)
    with connect() as db:db.execute('UPDATE conversations SET title=?,updated_at=? WHERE id=?',('新会话',datetime.now(timezone.utc).isoformat(),sid))


def cache_locations(name,rows):
    import time
    with connect() as db:db.execute('INSERT OR REPLACE INTO location_cache VALUES (?,?,?)',(name,json.dumps(rows,ensure_ascii=False),time.time()))

def cached_locations(name,ttl=21600):
    import time
    with connect() as db:row=db.execute('SELECT payload,verified_at FROM location_cache WHERE name=?',(name,)).fetchone()
    if row and 0<=time.time()-row[1]<ttl:return [{**r,'_verified_at':row[1]} for r in json.loads(row[0])]
    return None

def prove_weather_coordinates(lat,lon,zone):
    import time
    if not zone:return
    with connect() as db:db.execute('INSERT OR REPLACE INTO weather_location_proofs VALUES (?,?,?,?)',(lat,lon,zone,time.time()))

def verified_weather_zone(lat,lon,ttl=21600):
    import time
    with connect() as db:row=db.execute('SELECT timezone,verified_at FROM weather_location_proofs WHERE latitude=? AND longitude=?',(lat,lon)).fetchone()
    return row[0] if row and 0<=time.time()-row[1]<ttl else None


def verified_weather_location(lat,lon,ttl=21600):
    import time
    with connect() as db:row=db.execute('SELECT timezone,verified_at FROM weather_location_proofs WHERE latitude=? AND longitude=?',(lat,lon)).fetchone()
    return dict(timezone=row[0],_verified_at=row[1]) if row and 0<=time.time()-row[1]<ttl else None


def recent_history(sid,limit=8):
    """Bounded history from this session only; includes direct graph callers too."""
    with connect() as db:
        rows=db.execute("SELECT payload FROM events WHERE session=? AND kind='conversation' ORDER BY id DESC LIMIT ?",(sid,min(limit,8))).fetchall()
    return [dict(user=(p:=json.loads(row[0])).get('message','')[:1000],assistant=p.get('response','')[:600]) for row in reversed(rows)]

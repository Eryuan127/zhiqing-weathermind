"""Cooperative cancellation and atomic persistence; aborted work never commits."""
import json,uuid
from contextvars import ContextVar
from threading import RLock
from datetime import datetime,timezone
context=ContextVar('generation',default=None)
locks=[RLock() for _ in range(64)]
class Cancelled(Exception):pass

def table(db):db.execute('CREATE TABLE IF NOT EXISTS generations (id TEXT PRIMARY KEY, owner TEXT, sid TEXT, cancelled INTEGER, status TEXT, previous TEXT)')
def checkpoint():
    current=context.get()
    if not current:return
    from services.agent_store import connect
    with connect() as db:
        table(db);row=db.execute('SELECT cancelled FROM generations WHERE id=?',(current['id'],)).fetchone()
    if row and row[0]:raise Cancelled()

def run(owner,sid,request_id,operation,message):
    from services import agent_store as store
    try:request_id=str(uuid.UUID(request_id))
    except (ValueError,TypeError,AttributeError):raise ValueError('无效请求编号')
    lock=locks[hash(request_id)%len(locks)]
    with lock,store.connect() as db:
        table(db);row=db.execute('SELECT owner,cancelled FROM generations WHERE id=?',(request_id,)).fetchone()
        if row:
            if row[0]==owner and row[1]:raise Cancelled()
            raise ValueError('请求编号已使用')
        db.execute('INSERT INTO generations VALUES (?,?,?,0,?,?)',(request_id,owner,sid,'running',json.dumps(store.read(sid),ensure_ascii=False)))
    stage={'id':request_id,'events':[],'states':{}};token=context.set(stage)
    try:
        checkpoint();result=operation();checkpoint();result['client_request_id']=request_id
        with lock,store.connect() as db:
            table(db)
            if db.execute('SELECT cancelled FROM generations WHERE id=?',(request_id,)).fetchone()[0]:raise Cancelled()
            now=datetime.now(timezone.utc).isoformat()
            for session_id,state in stage['states'].items():
                state={**state,'_generation_id':request_id};db.execute('INSERT OR REPLACE INTO sessions VALUES (?,?)',(session_id,json.dumps(state,ensure_ascii=False)))
            for session_id,kind,payload in stage['events']:db.execute('INSERT INTO events(session,kind,payload,time) VALUES (?,?,?,?)',(session_id,kind,json.dumps(payload,ensure_ascii=False),now))
            cursor=db.execute('INSERT INTO conversation_turns(session,message,response) VALUES (?,?,?)',(sid,message,json.dumps(result,ensure_ascii=False)));result['turn_id']=cursor.lastrowid;db.execute('UPDATE conversation_turns SET response=? WHERE id=?',(json.dumps(result,ensure_ascii=False),cursor.lastrowid))
            first=db.execute('SELECT message FROM conversation_turns WHERE session=? ORDER BY id LIMIT 1',(sid,)).fetchone()[0]
            db.execute('UPDATE conversations SET title=?,updated_at=? WHERE id=?',(first[:32],now,sid));db.execute("UPDATE generations SET status='complete' WHERE id=?",(request_id,))
        return result
    finally:context.reset(token)

def cancel(owner,request_id,visible=''):
    from services import agent_store as store
    request_id=str(uuid.UUID(request_id));lock=locks[hash(request_id)%len(locks)]
    with lock,store.connect() as db:
        table(db);row=db.execute('SELECT owner,sid,previous,status FROM generations WHERE id=?',(request_id,)).fetchone()
        if row and row[0]!=owner:raise PermissionError()
        if not row:
            db.execute('INSERT INTO generations VALUES (?,?,NULL,1,?,?)',(request_id,owner,'cancelled','{}'));return
        db.execute("UPDATE generations SET cancelled=1,status='cancelled' WHERE id=?",(request_id,))
        sid=row[1]
        if not sid:return
        for turn_id,response in db.execute('SELECT id,response FROM conversation_turns WHERE session=?',(sid,)).fetchall():
            reply=json.loads(response)
            if reply.get('client_request_id')==request_id:
                db.execute('CREATE TABLE IF NOT EXISTS reply_edits (turn_id INTEGER PRIMARY KEY, text TEXT)')
                db.execute('DELETE FROM reply_edits WHERE turn_id=?',(turn_id,))
                db.execute('DELETE FROM conversation_turns WHERE id=?',(turn_id,))
        for event_id,payload in db.execute("SELECT id,payload FROM events WHERE session=?",(sid,)).fetchall():
            value=json.loads(payload)
            if value.get('client_request_id')==request_id:db.execute('DELETE FROM events WHERE id=?',(event_id,))
        previous_turns=db.execute('SELECT message FROM conversation_turns WHERE session=? ORDER BY id',(sid,)).fetchall()
        db.execute('UPDATE conversations SET title=? WHERE id=?',(' '.join(previous_turns[0][0].split())[:32] if previous_turns else '新会话',sid))
        current=db.execute('SELECT state FROM sessions WHERE id=?',(sid,)).fetchone()
        if current and json.loads(current[0]).get('_generation_id')==request_id:db.execute('UPDATE sessions SET state=? WHERE id=?',(row[2],sid))

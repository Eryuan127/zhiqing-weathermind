from flask import Blueprint,request,jsonify,render_template,session
import uuid
from threading import Lock
compact_locks = [Lock() for _ in range(32)]
from services.weather_agent import chat
from services import agent_store
agent_api=Blueprint('agent_api',__name__)
@agent_api.get('/assistant')
def assistant():
    from auth_routes import user
    if request.args.get('embedded')=='1' and not user():return '请先登录后使用助手',401
    return render_template('assistant.html',current_user=user())
def owner():
    return 'user:'+session['user_id']


def sid():
    session['agent_id']=agent_store.ensure_conversation(owner(),session.get('agent_id'))
    return session['agent_id']
@agent_api.post('/api/agent/chat')
def ask():
    body=request.get_json(silent=True) or {}; message=body.get('message')
    if not isinstance(message,str) or not 1<=len(message.strip())<=1000: return jsonify(error='请输入1至1000字的问题。'),400
    try: home=validate_city(body.get('home_city'))
    except (ValueError,TypeError,KeyError): return jsonify(error='首页城市参数无效'),400
    mode=body.get('mode','rules')
    if mode not in ('rules','qwen'):return jsonify(error='无效的执行模式'),400
    current=sid()
    from services import generation
    try:
        result=generation.run(owner(),current,body.get('client_request_id') or str(uuid.uuid4()),lambda:chat(current,message.strip(),home,mode=mode),message.strip())
        return jsonify(result)
    except generation.Cancelled:return jsonify(cancelled=True),409
    except ValueError:return jsonify(error='请求编号无效或已使用'),400

@agent_api.post('/api/agent/compact')
def new_compact():
    # A floating chat never changes the conversation selected in the full chat.
    current=agent_store.ensure_conversation(owner())
    return jsonify(id=current),201

@agent_api.post('/api/agent/compact/<conversation_id>/chat')
def compact_ask(conversation_id):
    if not agent_store.owned(owner(),conversation_id):return jsonify(error='会话不存在'),404
    body=request.get_json(silent=True) or {};message=body.get('message')
    if not isinstance(message,str) or not 1<=len(message.strip())<=200:return jsonify(error='请输入1至200字的问题。'),400
    try:home=validate_city(body.get('home_city'))
    except (ValueError,TypeError,KeyError):return jsonify(error='首页城市参数无效'),400
    with compact_locks[hash(conversation_id)%len(compact_locks)]:
        turns=len(agent_store.transcript(conversation_id))
        if turns>=5:return jsonify(error='小窗已聊满5次，请到完整聊天继续。',limit_reached=True),409
        result=chat(conversation_id,message.strip(),home)
        agent_store.append_turn(conversation_id,message.strip(),result)
        return jsonify(**result,remaining=4-turns)

@agent_api.delete('/api/agent/session')
def clear():
    agent_store.reset_conversation(sid())
    return jsonify(status='cleared')


def validate_city(city):
    from services.location_context import normalize
    return normalize(city)

@agent_api.put('/api/agent/context')
def update_city():
    try: city=validate_city((request.get_json(silent=True) or {}).get('city'))
    except (ValueError,TypeError,KeyError): return jsonify(error='城市参数无效'),400
    if not city: return jsonify(error='城市不能为空'),400
    # Homepage updates must not overwrite a confirmed conversation city.
    return jsonify(location=city)


@agent_api.get('/api/agent/conversations')
def conversations():
    current=sid()
    return jsonify(active_id=current,conversations=agent_store.list_conversations(owner()))

@agent_api.post('/api/agent/conversations')
def new_conversation():
    current=session.get('agent_id')
    if not current or not agent_store.owned(owner(),current) or agent_store.transcript(current):
        current=agent_store.ensure_conversation(owner())
    session['agent_id']=current
    return jsonify(active_id=current),201

@agent_api.get('/api/agent/conversations/<conversation_id>')
def conversation(conversation_id):
    if not agent_store.owned(owner(),conversation_id):return jsonify(error='会话不存在'),404
    return jsonify(id=conversation_id,turns=agent_store.transcript(conversation_id))

@agent_api.put('/api/agent/conversations/<conversation_id>/activate')
def activate_conversation(conversation_id):
    if not agent_store.owned(owner(),conversation_id):return jsonify(error='会话不存在'),404
    session['agent_id']=conversation_id
    return jsonify(active_id=conversation_id,turns=agent_store.transcript(conversation_id))

@agent_api.get('/api/agent/config')
def agent_config():
    from services.qwen_decision import availability
    enabled,reason=availability()
    return jsonify(default_mode='rules',qwen_enabled=enabled,reason=reason)

@agent_api.post('/api/agent/generations/<request_id>/cancel')
def cancel_generation(request_id):
    from services.generation import cancel
    visible=(request.get_json(silent=True) or {}).get('visible','')
    if not isinstance(visible,str) or len(visible)>50000:return jsonify(error='内容无效'),400
    try:cancel(owner(),request_id,visible)
    except (ValueError,AttributeError):return jsonify(error='请求编号无效'),400
    except PermissionError:return jsonify(error='请求不存在'),404
    return jsonify(stopped=True)

@agent_api.patch('/api/agent/conversations/<conversation_id>/turns/<int:turn_id>')
def edit_reply(conversation_id,turn_id):
    if not agent_store.owned(owner(),conversation_id):return jsonify(error='会话不存在'),404
    text=(request.get_json(silent=True) or {}).get('text')
    if not isinstance(text,str) or not 1<=len(text.strip())<=10000:return jsonify(error='请输入1至10000字'),400
    with agent_store.connect() as db:
        if not db.execute('SELECT 1 FROM conversation_turns WHERE id=? AND session=?',(turn_id,conversation_id)).fetchone():return jsonify(error='消息不存在'),404
        db.execute('CREATE TABLE IF NOT EXISTS reply_edits (turn_id INTEGER PRIMARY KEY, text TEXT)')
        db.execute('INSERT OR REPLACE INTO reply_edits VALUES (?,?)',(turn_id,text.strip()))
    return jsonify(edited=True)

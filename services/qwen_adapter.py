"""One bounded Qwen tool-planning call; safe default requires console free-only confirmation."""
import os,json
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage,HumanMessage
from services.agent_tools import TOOLS
from services.agent_store import event
from services.qwen_stream import stream_call
from services.generation import Cancelled

def propose(state):
    if os.getenv('AGENT_MODE','rules') not in ('auto','qwen'): return None,'rules_selected'
    if not os.getenv('DASHSCOPE_API_KEY'): return None,'missing_key'
    if os.getenv('QWEN_FREE_ONLY_CONFIRMED')!='true': return None,'free_only_not_confirmed'
    model=os.getenv('QWEN_MODEL','qwen-turbo')
    try:
        def bound(transport):return ChatOpenAI(model=model,api_key=os.environ['DASHSCOPE_API_KEY'],base_url=os.getenv('QWEN_BASE_URL','https://dashscope.aliyuncs.com/compatible-mode/v1'),temperature=0,timeout=15,max_retries=0,max_tokens=600,extra_body={'enable_thinking':False},stream_usage=True,**transport).bind_tools(list(TOOLS.values()))
        response=stream_call(bound,[SystemMessage(content='仅规划天气查询工具。最多调用一个天气工具。不要编造数据。使用给定坐标，不修改城市和时间。'),HumanMessage(content=json.dumps({k:state.get(k) for k in ['message','city','latitude','longitude','intent']},ensure_ascii=False))])
        calls=response.tool_calls
        event(state['sid'],'model',dict(model=model,status='ok',tool_calls=calls,usage=response.usage_metadata))
        return calls,'qwen'
    except Cancelled:raise
    except Exception as exc:
        event(state['sid'],'model',dict(model=model,status='error',error_type=type(exc).__name__))
        return None,'model_unavailable'

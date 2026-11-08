"""Streaming lifecycle tests; all providers in this file are local fixtures."""
import asyncio,threading,time,uuid,json
import pytest
from langchain_core.messages import AIMessageChunk
from services.qwen_stream import stream_call
from services import generation,agent_store as store


def test_fragmented_tool_call_and_usage_are_assembled_and_transports_close():
 resources={}
 class Model:
  async def astream(self,messages,**kwargs):
   assert kwargs['stream_usage'] is True
   yield AIMessageChunk(content='',tool_call_chunks=[dict(name='Decision',args='{"cities":',id='call',index=0)])
   yield AIMessageChunk(content='',tool_call_chunks=[dict(name=None,args='["上海"]}',id=None,index=0)])
   yield AIMessageChunk(content='',usage_metadata=dict(input_tokens=12,output_tokens=8,total_tokens=20))
 def factory(transport):resources.update(transport);return Model()
 reply=stream_call(factory,[])
 assert reply.tool_calls[0]['args']=={'cities':['上海']} and reply.usage_metadata['total_tokens']==20
 assert resources['http_client'].is_closed and resources['http_async_client'].is_closed

@pytest.mark.parametrize('first_chunk',[False,True])
def test_cancel_during_silent_read_closes_iterator_and_prevents_next_call(tmp_path,monkeypatch,first_chunk):
 monkeypatch.setenv('AGENT_DB',str(tmp_path/'stream.db'));owner='user:test';sid=store.ensure_conversation(owner);rid=str(uuid.uuid4());entered=threading.Event();closed=threading.Event();resources={};outcome=[];next_calls=[]
 class Model:
  async def astream(self,*a,**k):
   try:
    if first_chunk:yield AIMessageChunk(content='partial')
    entered.set();await asyncio.sleep(3600)
   finally:closed.set()
 def factory(transport):resources.update(transport);return Model()
 def operation():
  stream_call(factory,[]);next_calls.append('must not run');return dict(response='must not commit')
 def run():
  try:generation.run(owner,sid,rid,operation,'test')
  except generation.Cancelled:outcome.append('cancelled')
 thread=threading.Thread(target=run);thread.start();assert entered.wait(5);started=time.monotonic();generation.cancel(owner,rid);thread.join(3)
 assert not thread.is_alive() and outcome==['cancelled'] and closed.is_set() and not next_calls
 assert time.monotonic()-started<3 and resources['http_async_client'].is_closed and store.transcript(sid)==[]
 with store.connect() as db:stats=json.loads(db.execute("SELECT payload FROM events WHERE kind='model_stream'").fetchone()[0])
 assert stats['cancelled'] and stats['transport_closed'] and stats['usage'] is None and not stats['usage_complete']


def test_pre_cancel_makes_no_provider_call(tmp_path,monkeypatch):
 monkeypatch.setenv('AGENT_DB',str(tmp_path/'before.db'));owner='user:test';rid=str(uuid.uuid4());sid=store.ensure_conversation(owner);calls=[]
 generation.cancel(owner,rid)
 with pytest.raises(generation.Cancelled):generation.run(owner,sid,rid,lambda:calls.append('provider'),'test')
 assert calls==[]


def test_local_http_sse_disconnects_on_cancel(tmp_path,monkeypatch):
 from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
 from langchain_openai import ChatOpenAI
 from services.qwen_decision import Decision
 monkeypatch.setenv('AGENT_DB',str(tmp_path/'http.db'));entered=threading.Event();disconnected=threading.Event();done=threading.Event();payloads=[];result=[]
 class Handler(BaseHTTPRequestHandler):
  def log_message(self,*args):pass
  def do_POST(self):
   payloads.append(json.loads(self.rfile.read(int(self.headers['Content-Length']))));self.send_response(200);self.send_header('Content-Type','text/event-stream');self.end_headers()
   chunk={'id':'local','object':'chat.completion.chunk','created':1,'model':'local-fixture','choices':[{'index':0,'delta':{'role':'assistant','tool_calls':[{'index':0,'id':'call','type':'function','function':{'name':'Decision','arguments':'{'}}]},'finish_reason':None}]}
   try:
    self.wfile.write(('data: '+json.dumps(chunk)+'\n\n').encode());self.wfile.flush();entered.set()
    while not done.wait(.05):self.wfile.write(b': heartbeat\n\n');self.wfile.flush()
   except (BrokenPipeError,ConnectionResetError,OSError):disconnected.set()
 server=ThreadingHTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=server.serve_forever,daemon=True).start()
 owner='user:http';sid=store.ensure_conversation(owner);rid=str(uuid.uuid4())
 def factory(transport):return ChatOpenAI(model='local-fixture',api_key='local-only',base_url=f'http://127.0.0.1:{server.server_port}/v1',max_retries=0,stream_usage=True,**transport).bind_tools([Decision],tool_choice='Decision')
 def run():
  try:generation.run(owner,sid,rid,lambda:stream_call(factory,[]),'test')
  except generation.Cancelled:result.append('cancelled')
 thread=threading.Thread(target=run);thread.start()
 try:
  assert entered.wait(5);generation.cancel(owner,rid);thread.join(3)
  assert result==['cancelled'] and disconnected.wait(3) and not thread.is_alive()
  assert payloads[0]['stream'] is True and payloads[0]['stream_options']['include_usage'] is True
  assert store.transcript(sid)==[]
 finally:done.set();thread.join(3);server.shutdown();server.server_close()

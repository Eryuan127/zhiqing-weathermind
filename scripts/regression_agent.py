"""Opt-in real weather regression. Qwen is never enabled by this script."""
import os,sys,json,tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app import create_app
from services.weather_agent import chat
from services.agent_store import read
os.environ['AGENT_MODE']='rules'
with tempfile.TemporaryDirectory() as tmp:
 os.environ['AGENT_DB']=str(Path(tmp)/'regression.sqlite3')
 records=[]
 questions=['今晚上海会下雨吗？','今天上海适合跑步吗？','预测上海下一小时的气温，并告诉我使用了什么模型。','明天下午上海适合拍照吗？','上海和杭州哪个更适合明天散步？']
 for i,q in enumerate(questions):
  r=chat(str(i),q);records.append(dict(case=q,execution='real Open-Meteo + local model/rules',**r));print('Completed case',i+1,flush=True)
 for q in ['上海','那明天呢？']:
  records.append(dict(case=q,execution='real multi-turn',**chat('multi',q)))
 client=create_app().test_client()
 client.put('/api/agent/context',json={'city':dict(name='杭州',latitude=30.27,longitude=120.15)})
 records.append(dict(case='切换首页杭州后询问当前天气',execution='real HTTP context + real weather',**client.post('/api/agent/chat',json={'message':'现在天气怎么样'}).json))
 os.environ['AGENT_MODE']='qwen'
 os.environ.pop('DASHSCOPE_API_KEY',None)
 records.append(dict(case='Qwen无Key降级',execution='real missing-key fallback + real weather',**chat('fallback','预测上海下一小时的气温，并告诉我使用了什么模型。')))
 path=Path('artifacts/hourly/targeted-regression.json');path.write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf-8')
 print('Saved',len(records),'records',flush=True)

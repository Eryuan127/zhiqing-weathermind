"""Opt-in real geocoding/weather + real graph, no Qwen calls or retraining."""
import sys,os,json,tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from services.weather_agent import chat
os.environ['AGENT_MODE']='rules'
questions=['周六上海适合拍照吗？帮我选个时间','帮我看看周末适不适合骑行','明天下午上海适合跑步吗','预测上海下个月15日14点的准确气温','查询XYZABC123明天的天气','上海和杭州哪个更适合明天散步','明天下午上海适合跑步吗','那晚上呢','预测上海下一小时气温']
with tempfile.TemporaryDirectory() as tmp:
 os.environ['AGENT_DB']=str(Path(tmp)/'smoke.sqlite3')
 records=[]
 for i,q in enumerate(questions):
  sid='follow' if i in [6,7] else str(i)
  r=chat(sid,q);records.append(dict(question=q,kind='real geocoding/weather/local Ridge; rules mode',**r))
  print(i+1,'tools:',','.join(t['name'] for t in r['tools']),'path:',','.join(r['path']),flush=True)
 Path('artifacts/hourly/constraints-real-smoke.json').write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf-8')
 print('Saved 9 actual results',flush=True)

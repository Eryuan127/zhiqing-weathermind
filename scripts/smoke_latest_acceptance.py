"""Real latest-acceptance smoke; rules only, no paid model requests."""
import sys,os,json,tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from services.weather_agent import chat
from services.time_constraints import contains
os.environ['AGENT_MODE']='rules'
questions=['帮我用 Ridge 模型预测上个月15日的气温','预测上海明天14点的准确气温，误差必须小于0.1°C。','明天下午上海和杭州哪个更适合跑步？我不喜欢风大的地方。','周六14:00到18:00之间跑步，选最好的两小时','下周一上午九点上海适合跑步吗','明天下午上海下雨的话，尽量不要淋雨','上海明天AQI适合跑步吗','上海下一小时气温预测']
with tempfile.TemporaryDirectory() as tmp:
 os.environ['AGENT_DB']=str(Path(tmp)/'real.sqlite3');records=[]
 for i,q in enumerate(questions):
  r=chat(str(i),q)
  for trace in r['tools']:
   if trace['name']=='rank_time_slots':
    for segment in trace['result'].get('data',[]):
     for h in segment.get('hours') or [segment]:assert contains(h['time'],trace['args']['time_window'])
     if trace['args']['time_window'].get('duration_hours'):assert len(segment['hours'])==trace['args']['time_window']['duration_hours']
  records.append(dict(question=q,execution='real graph/geocoding/weather/local model; rules mode',**r))
  print('Case',i+1,'path:','/'.join(r['path']),'statuses:',[t['status'] for t in r['tools']],'services:',[(d.get('service'),d.get('status'),d.get('status_code'),d.get('error_type')) for d in r['service_diagnostics']],flush=True)
 Path('artifacts/hourly/latest-acceptance-real.json').write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf-8')
 print('Saved 8 real execution records',flush=True)

"""Reproduce paired experiments. Weather snapshot is real; failures injected explicitly.
Run --capture once, then --qwen-limit 3 (bounded pilot) or 14 (full set).
No API keys or raw upstream exception messages are saved.
"""
import sys,os,json,argparse,tempfile,copy,csv
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from dotenv import load_dotenv
load_dotenv()
from services import weather_agent as a,agent_tools as t
from services.weather_service import get_weather
from services.http_client import UpstreamError
import services.time_constraints as tc
root=Path('artifacts/qwen');root.mkdir(parents=True,exist_ok=True)
CASES=[
 ('current','上海当前天气',['get_current_weather'],None,None,None),
 ('ridge','上海下一小时气温预测',['predict_next_hour_temperature'],None,None,None),
 ('run','我明天下午想在上海跑步',['get_hourly_forecast','rank_time_slots'],'跑步','下午',None),
 ('photo','上海明天下午连续两小时拍照，推荐时间',['get_hourly_forecast','rank_time_slots'],'拍照','下午',None),
 ('compare','明天下午上海和杭州哪个更适合跑步',['get_hourly_forecast','rank_time_slots'],'跑步','下午',None),
 ('wind','上海明天下午跑步，我不喜欢风大的地方',['get_hourly_forecast','rank_time_slots'],'跑步','下午',None),
 ('follow-city','改成杭州呢',['get_hourly_forecast','rank_time_slots'],'跑步','下午',None),
 ('follow-time','那晚上呢',['get_hourly_forecast','rank_time_slots'],'跑步','晚上',None),
 ('invalid','火星市当前天气',[],None,None,'未找到'),
 ('history','用Ridge预测上海上个月15日气温',[],None,None,'仅支持'),
 ('guarantee','预测上海明天气温，保证误差小于0.1°C',[],None,None,'无法保证'),
 ('aqi','上海明天空气质量AQI适合运动吗',[],None,None,'尚未接入'),
 ('api-error','上海当前天气',['get_current_weather'],None,None,'无法完成'),
]
def main():
 p=argparse.ArgumentParser();p.add_argument('--capture',action='store_true');p.add_argument('--qwen-limit',type=int,default=3);args=p.parse_args()
 snapshot=root/'weather_snapshot.json'
 if args.capture:
  data={'captured_at':datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(),'source':'real Open-Meteo weather_service capture','cities':{}}
  for name in ['上海','杭州']:
   data['cities'][name]=get_weather(*a.CITIES[name]);print('Captured',name,flush=True)
  snapshot.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
 data=json.loads(snapshot.read_text(encoding='utf-8'));now=datetime.fromisoformat(data['captured_at'])
 records=[]
 with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,{'AGENT_DB':str(Path(tmp)/'experiment.sqlite3'),'AGENT_MODE':'rules'}),patch.object(tc,'local_now',lambda z:now.astimezone(ZoneInfo(z))),patch.object(a,'local_now',lambda z:now.astimezone(ZoneInfo(z))),patch.object(a,'search_locations',lambda name:[dict(name=name,latitude=a.CITIES[name][0],longitude=a.CITIES[name][1],timezone='Asia/Shanghai')] if name in a.CITIES else []):
  for mode in ['rules','qwen']:
   for index,(cid,text,expected,activity,period,error) in enumerate(CASES):
    record=dict(case_id=cid,expected_tools=expected,expected_activity=activity,expected_period=period,expected_error=error,mode=mode,input=text,weather='real Open-Meteo fixed snapshot',geocoding='fixed known-city fixture',ridge='real local Ridge + live external model input' if cid=='ridge' else 'not invoked',qwen='real API' if mode=='qwen' else 'not invoked')
    if mode=='qwen' and index>=args.qwen_limit:records.append(dict(record,status='not_tested'));continue
    def weather(lat,lon):
     if cid=='api-error':raise UpstreamError('实验注入：天气API超时',kind='timeout',service='weather',error_type='Timeout')
     name='上海' if lat>31 else '杭州';return copy.deepcopy(data['cities'][name])
    t._WEATHER_CACHE.clear()
    sid=mode+'-multi' if cid in ['run','follow-city','follow-time'] else mode+'-'+cid
    with patch.object(t,'get_weather',weather):r=a.chat(sid,text,mode=mode)
    names=[x['name'] for x in r['tools']]
    tools_ok=(set(names)==set(expected))
    if error:params_ok=True
    else:
     expected_cities=['上海','杭州'] if cid=='compare' else ['杭州'] if cid.startswith('follow-') else ['上海']
     params_ok=r['parsed_cities']==expected_cities and (not activity or r['execution']['activity']==activity) and (not period or (r.get('time_window') or {}).get('period')==period)
     if activity:params_ok=params_ok and (r.get('time_window') or {}).get('dates')==[(now.date()+__import__('datetime').timedelta(days=1)).isoformat()]
     if cid=='photo':params_ok=params_ok and r['time_window']['duration_hours']==2
     if cid=='wind':params_ok=params_ok and bool(r['time_window'].get('avoid_wind'))
    actual_ok=r['mode']==mode
    grounded=r['execution'].get('grounded_paragraphs')
    consistency=(sorted(r['response'].split('\n\n'))==sorted(grounded) if grounded else bool(error and error in r['response'])) and r['mode'] not in ['qwen_failed','qwen_partial']
    success=bool(error in r['response']) if error else all(x['status'] in ['ok','experimental'] for x in r['tools']) and bool(r['tools']) and r['path'][-1]=='generate_response'
    checks=dict(task_completed=success and tools_ok and params_ok and actual_ok,tool_selection=tools_ok and actual_ok,parameter_parsing=params_ok and actual_ok,data_consistency=consistency,exception_handling=(bool(error in r['response']) and actual_ok) if error else None)
    records.append(dict(record,status='executed',fault_injection=cid=='api-error',checks=checks,result=r,duration_ms=r['execution']['duration_ms']))
    print(mode,cid,checks,flush=True)
 out={'conditions':{'snapshot':str(snapshot),'clock':data['captured_at'],'qwen_limit':args.qwen_limit,'consistency_criterion':'extractive evidence only; semantic accuracy still requires human review'},'records':records,'metrics':{}}
 for mode in ['rules','qwen']:
  rows=[r for r in records if r['mode']==mode and r['status']=='executed'];m={'executed':len(rows),'not_tested':len(CASES)-len(rows),'average_ms':round(sum(r['duration_ms'] for r in rows)/len(rows),1) if rows else None}
  for key in ['task_completed','tool_selection','parameter_parsing','data_consistency','exception_handling']:
   vals=[r['checks'][key] for r in rows if r['checks'][key] is not None];m[key]=dict(passed=sum(vals),total=len(vals),rate=sum(vals)/len(vals) if vals else None)
  out['metrics'][mode]=m
 (root/'comparison.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
 with (root/'comparison.csv').open('w',encoding='utf-8-sig',newline='') as f:
  writer=csv.DictWriter(f,fieldnames=['case_id','mode','input','status','duration_ms','checks','result']);writer.writeheader()
  for row in records:writer.writerow({k:json.dumps(row[k],ensure_ascii=False) if isinstance(row.get(k),dict) else row.get(k) for k in writer.fieldnames})
 print(json.dumps(out['metrics'],ensure_ascii=False),flush=True)
if __name__=='__main__':main()

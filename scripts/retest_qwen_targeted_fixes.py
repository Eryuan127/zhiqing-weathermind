"""Real HTTP + Qwen + live weather retest. No patches or fixtures."""
import json,time
from pathlib import Path
import requests
BASE='http://127.0.0.1:5001'
ROOT=Path('artifacts/qwen/targeted-fixes');ROOT.mkdir(parents=True,exist_ok=True)
records=[]
def ask(client,case,text):
    start=time.monotonic()
    response=client.post(BASE+'/api/agent/chat',json={'message':text,'mode':'qwen'},timeout=100)
    data=response.json();e=data.get('execution',{})
    checks={'real_qwen_success':data.get('mode')=='qwen' and (e.get('qwen') or {}).get('status')=='ok'}
    if case=='non_weather_after_aqi':checks.update(correct_intent=e.get('intent')=='out_of_scope',no_tools=not data.get('tools'),no_aqi_reply='空气质量 API' not in data.get('response',''))
    if case=='recall':checks.update(correct_intent=e.get('intent')=='recall',retains_activity='跑步' in data.get('response',''),retains_preference='风速优先' in data.get('response',''),no_tools=not data.get('tools'))
    if case in ['new_session','after_clear']:checks.update(isolation='尚未记录' in data.get('response',''),no_tools=not data.get('tools'))
    if case=='current_metrics':checks.update(correct_intent=e.get('intent')=='current',complete=all(x in data.get('response','') for x in ['气温','风速','降水量']),tool_success=any(t['status']=='ok' for t in data.get('tools',[])))
    if case=='weighted_compare':
        rankings=[t for t in data.get('tools',[]) if t['name']=='rank_time_slots']
        checks.update(planned_preference=e.get('preference')=='wind',scores_executed=len(rankings)==2 and all(t['status']=='ok' for t in rankings),weights_applied=bool(rankings) and all(row['weights']['wind']>row['weights']['temperature'] for t in rankings for row in t['result'].get('data',[])))
    records.append(dict(case=case,input=text,execution='REAL Qwen API + real local HTTP; weather/geocoding live when invoked; no Mock',http_status=response.status_code,duration_ms=round((time.monotonic()-start)*1000),checks=checks,result=data))
    (ROOT/'real-retest.json').write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf-8')
    print(case,json.dumps(checks),flush=True)
    if (e.get('qwen') or {}).get('error_type')=='quota_exhausted':raise SystemExit('Stopped: quota exhausted')
client=requests.Session()
ask(client,'aqi_setup','上海明天空气质量怎么样？')
ask(client,'non_weather_after_aqi','帮我写一段 Python 冒泡排序代码')
ask(client,'weighted_compare','我明天下午想跑步，比较上海和杭州，风速比温度更重要')
ask(client,'recall','我刚才说想做什么运动？还记得日期和偏好吗？')
ask(client,'current_metrics','请告诉我上海当前的温度、风速和降水情况')
ask(requests.Session(),'new_session','我刚才说想做什么运动？')
client.delete(BASE+'/api/agent/session',timeout=10).raise_for_status()
ask(client,'after_clear','我刚才说想做什么运动？')

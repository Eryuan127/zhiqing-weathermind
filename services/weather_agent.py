"""Bounded LangGraph workflow. Rules own validation, execution and grounded rendering."""
import re,time
from datetime import datetime,timedelta
from zoneinfo import ZoneInfo
from typing import TypedDict
from langgraph.graph import StateGraph,START,END
from services.agent_tools import TOOLS
from services import agent_store as store
from services.geocoding_service import search_locations
from services.qwen_adapter import propose
from services.time_constraints import parse_window, local_now, contains, filter_rows, chinese, merged_slots
from services.city_resolution import extract_cities,normalize_cities
from services.location_context import select as select_location, LABELS
from services.http_client import UpstreamError,DIAGNOSTICS,REQUEST_ID
class State(TypedDict,total=False):
    query_method:str; location_source:str; history:list; preference:str; grounded_paragraphs:list; explanation_log:dict; requested_mode:str; decision:dict; qwen_log:dict; temporal_text:str; avoid_wind:bool; request_id:str
    location_verified_at:float; failures:list; time_window:dict; resolved_cities:list; requested_cities:list; timezone:str; home_city:dict; city_source:str; cities:list; sid:str; message:str; context:dict; city:str; latitude:float; longitude:float; intent:str; activity:str; day:int; period:str; plan:list; results:list; traces:list; response:str; error:str; missing:str; mode:str
CITIES={'上海':(31.23,121.47),'北京':(39.9,116.4),'杭州':(30.27,120.15),'广州':(23.13,113.26),'深圳':(22.54,114.06)}
def clothing_request(text):
    return bool(re.search(r'穿衣|穿什么|怎么穿|穿搭|冷不冷|长袖|短袖|外套|羽绒|毛衣|卫衣|长裤|短裤',text))

def parse_request(s):
    if s.get('requested_mode')=='qwen':
        from services.qwen_decision import decide
        d,log=decide(s)
        if not d:return dict(error='Qwen 调用未成功：'+log['error_type']+'；本次未回退规则模式。',mode='qwen_failed',qwen_log=log,traces=[],results=[])
        if clothing_request(s['message']):
            d={**d,'intent':'clothing','activity':None,'temporal_text':s['message'],'tools':['get_daily_forecast']}
            log={**log,'decision':d,'intent_policy':'explicit_clothing'}
        explicit=normalize_cities(extract_cities(s['message']))
        cities=explicit or [c for c in normalize_cities(d['cities']) if c in s['message'] and c not in LABELS]
        ctx,source=select_location(s.get('context',{}),s.get('home_city'),cities)
        return {**ctx,'requested_cities':cities,'city_source':source,'cities':cities if len(cities)>1 else [],'intent':d['intent'],'preference':d.get('preference') or ctx.get('preference','balanced'),'activity':d['activity'] or ctx.get('activity'),'temporal_text':d['temporal_text'],'avoid_wind':d['avoid_wind'],'decision':d,'qwen_log':log,'mode':'qwen','traces':[],'results':[],'day':0}
    text=s['message']; ctx=dict(s.get('context',{})); home=s.get('home_city') or {}
    cities=[c for c in normalize_cities(extract_cities(text)) if c not in LABELS]
    if not cities:
        match=re.search(r'([\u4e00-\u9fff]{2,8})市',text)
        if match and match[1] not in LABELS:cities=[match[1]]
    ctx,source=select_location(ctx,home,cities)
    explicit_activity=next((a for a in ['跑步','散步','拍照','骑行'] if a in text),None)
    follow=bool(re.search(r'那|呢|明天|后天|连续|小时',text)) and not explicit_activity and not re.search(r'天气|下雨|气温|模型|预报',text)
    activity=explicit_activity or (ctx.get('activity') if follow else None)
    if re.search(r'刚才|之前|前面|记得',text) and re.search(r'说|提|运动|活动|城市|偏好',text):intent='recall'
    elif clothing_request(text):intent='clothing'
    elif not cities and not re.search(r'天气|温度|气温|风|雨|雪|空气|AQI|PM2|PM10|雾霾|预报|预测|模型|跑步|散步|拍照|骑行|穿|洗车|那|呢|明天|今天|现在|小时|周',text,re.I):intent='out_of_scope'
    elif re.search(r'空气质量|AQI|PM2[._]?5|PM10|雾霾',text,re.I):intent='aqi'
    elif re.search(r'下一?小时|下个小时|气温预测|温度预测|预测.*气温|使用.*模型|什么模型|哪个模型',text): intent='ml'
    elif re.search(r'几点|时段|什么时候|最好.*小时|连续.*小时',text): intent='rank'
    elif explicit_activity or (follow and activity): intent='activity'
    elif re.search(r'下雨|降雨|带伞|携伞',text): intent='rain'
    elif re.search(r'穿衣|穿什么|冷不冷',text): intent='clothing'
    elif '洗车' in text: intent='wash'
    elif re.search(r'多日|一周|七天|7天',text): intent='daily'
    elif follow and ctx.get('intent') in ('rain','aqi'):intent=ctx['intent']
    elif re.search(r'明天|后天|小时|今晚|晚上|下午|早上|周|下个月',text): intent='hourly'
    elif follow: intent=ctx.get('intent') or 'current'
    else: intent='current'
    day=2 if '后天' in text else 1 if re.search(r'明天|明早|明晚',text) else (ctx.get('day') or 0) if follow and not re.search(r'今天|今晚',text) else 0
    period='晚上' if re.search(r'今晚|明晚|晚上|夜里',text) else '早上' if re.search(r'早上|上午|明早',text) else '下午' if '下午' in text else (ctx.get('period') or '全天') if follow else '全天'
    return {**ctx,'requested_cities':cities,'city_source':source,'cities':cities[:2] if len(cities)>1 else [],'preference':('wind' if re.search('风速.*(?:更重要|优先)|(?:优先|更看重).*风',text) else 'balanced' if re.search('恢复默认|默认权重',text) else ctx.get('preference','balanced')),'avoid_wind':bool(re.search('不喜欢风大|避免大风|不要风大|避风',text)) or (ctx.get('avoid_wind',False) if follow else False),'activity':activity,'intent':intent,'day':day,'period':period,'traces':[],'results':[]}

def check_context(s):
    if s.get('error'):return {}
    if s['intent'] in ['recall','out_of_scope']:
        if s.get('requested_mode')=='qwen' and s['decision']['tools']:return dict(error='Qwen 非天气请求包含天气工具计划，已拒绝执行。',mode='qwen_failed')
        return {}
    if s['intent']=='aqi' and s.get('requested_mode')=='qwen' and not re.search('空气|AQI|污染|雾霾|PM2|PM10',s['message'],re.I) and not (s.get('context',{}).get('intent')=='aqi' and re.search('那|呢|这个|它',s['message'])):
        return dict(error='Qwen 意图与本轮请求缺少明确关联，已拒绝空气质量分支；请重新表述本轮需求。',mode='qwen_failed')
    if s.get('requested_mode')=='qwen' and s['intent']=='daily' and re.search('下午|上午|晚上|早上|点|小时',s['message']) and re.search('雨|天气',s['message']):
        return dict(error='Qwen 选择了日预报，但本次询问具体时段，已拒绝用全天数据回答；请重试。',mode='qwen_failed')
    if re.search(r'误差.*(?:小于|低于|不超过|必须)|保证.*(?:准确|误差)',s['message']):
        return dict(error='无法保证气温预测误差小于0.1°C或任何指定上限。本地 Ridge 仅作实验性下一整点预测，历史 MAE 不是实时误差保证。')
    if len(s.get('requested_cities',[]))>2:return dict(missing='目前最多比较两座城市，请缩小范围。')
    if s['intent'] in ['rank','activity'] and not s.get('activity'): return dict(missing='你想安排跑步、散步、拍照还是骑行？')
    resolved=[]
    if s.get('query_method')=='coordinates' and s.get('location_source')=='manual' and s.get('city') in CITIES:
        lat,lon=CITIES[s['city']]
        if abs(s['latitude']-lat)>.5 or abs(s['longitude']-lon)>.5:return dict(missing='首页城市名称与坐标不一致，请重新选择城市。')
    if not s.get('city'):return dict(missing='请告诉我你要查询的城市，或允许首页定位后再试。')
    names=s.get('requested_cities') or [s['city']]
    request_geocodes={}
    for name in normalize_cities(names):
        try:
            context=s.get('context',{});home=s.get('home_city') or {};reused=None
            direct=s.get('query_method')=='coordinates' and not s.get('requested_cities')
            if direct:
                from services.agent_tools import get_weather
                # Obtain the authoritative local timezone from weather coordinates,
                # independent of reverse geocoding and client timezone claims.
                weather=get_weather(s['latitude'],s['longitude'])
                zone=weather['timezone'];ZoneInfo(zone)
                reused=dict(name=name,latitude=s['latitude'],longitude=s['longitude'],timezone=zone,_verified_at=time.time())
            elif context.get('city')==name and 0<=time.time()-(context.get('location_verified_at') or 0)<21600 and context.get('timezone') and isinstance(context.get('latitude'),(int,float)) and isinstance(context.get('longitude'),(int,float)):
                reused=dict(name=name,latitude=context['latitude'],longitude=context['longitude'],timezone=context['timezone'],_verified_at=context['location_verified_at'])
            from services.http_client import record
            record(dict(service='location',status='resolved_coordinates' if direct else 'verified_session_reuse' if reused else 'resolve_city_name',location_source=s.get('location_source',s.get('city_source')),query_method='coordinates' if direct else 'city_name'))
            if name not in request_geocodes:request_geocodes[name]=[reused] if reused else search_locations(name)
            candidates=request_geocodes[name]
            exact=[r for r in candidates if (r.get('name') or '').removesuffix('市').casefold()==name.removesuffix('市').casefold()]
            if name in CITIES and not direct:
                lat,lon=CITIES[name]
                exact=[r for r in exact if abs(r['latitude']-lat)<0.5 and abs(r['longitude']-lon)<0.5]
            if not exact: return dict(missing=f'未找到该城市：{name}，请确认名称；不会自动回退到默认城市。')
            if len(exact)>1:return dict(missing=f'{name}有多个同名地点，请提供更明确的城市或地区。')
            row=exact[0];zone=row.get('timezone')
            if not zone:return dict(error='城市缺少当地时区，无法可靠解析时间。')
            temporal=s.get('temporal_text') or s['message']
            if s['intent']=='clothing' and not re.search(r'今天|今晚|明天|明早|明晚|后天|昨天|前天|周|星期|月|\d{4}-\d{2}-\d{2}',s['message']) and s.get('context',{}).get('time_window'):
                temporal='那'
            if s.get('requested_mode')=='qwen' and re.search('那|呢|改成|换成',s['message']):temporal='那'+temporal
            window=parse_window(temporal,zone,s.get('context',{}).get('time_window'),s.get('activity'),s['intent']=='ml')
            window['avoid_wind']=s.get('avoid_wind',False)
            window['preference']=s.get('preference','balanced')
            now=local_now(zone)
            if s['intent']=='daily' and not re.search('周|明天|后天|下个月|今天',s['message']):
                window=parse_window('下周',zone)
                window['dates']=[(now+timedelta(days=i)).date().isoformat() for i in range(7)]
                window['ranges']=[dict(start=now.replace(hour=0,minute=0,second=0,microsecond=0).isoformat(),end=(now.replace(hour=0,minute=0,second=0,microsecond=0)+timedelta(days=7)).isoformat())]
            if s['intent']=='ml':
                expected=now.replace(minute=0,second=0,microsecond=0)+timedelta(hours=1)
                target=window.get('target_time')
                if not target or datetime.fromisoformat(target)!=expected:
                    return dict(error='本地 Ridge 模型仅支持下一整点的一小时预测，无法预测你指定日期或时刻的准确气温。天气 API 预报与本地模型预测不同；不会用下一小时结果替代。')
            else:
                ends=[datetime.fromisoformat(r['end']) for r in window['ranges']]
                starts=[datetime.fromisoformat(r['start']) for r in window['ranges']]
                if max(ends)<=now:return dict(error='所选时间已过去，请选择未来日期或时段。')
                horizon=timedelta(days=7) if s['intent'] in ['daily','wash','clothing'] else timedelta(hours=72)
                if min(starts)>=now+horizon or max(ends)>now+horizon:
                    return dict(error='所选时间超出当前可用预报范围（小时预报72小时、日预报7日），无法给出该时段建议。')
            resolved.append(dict(city=name,latitude=row['latitude'],longitude=row['longitude'],timezone=zone,time_window=window,location_verified_at=row.get('_verified_at',time.time()),query_method='coordinates' if direct else 'city_name',location_source=s.get('location_source',s.get('city_source'))))
        except ValueError as exc:return dict(missing='日期、时间或时区无效，请确认日期与时间。')
        except UpstreamError as exc:return dict(error=str(exc)+' 这不表示城市不存在。')
        except Exception as exc:
            from services.http_client import record
            record(dict(service='geocoding_or_constraints',status='error',kind='program',error_type=type(exc).__name__,status_code=None,call_chain='check_context → geocoding/constraints'))
            return dict(error='城市或时间处理服务暂时不可用（程序异常），请稍后重试。')
    first=resolved[0]
    return dict(**first,resolved_cities=resolved)

def clarify_request(s): return dict(response=s['missing'])
def plan_tools(s):
    name={'aqi':'get_air_quality_forecast','ml':'predict_next_hour_temperature','daily':'get_daily_forecast','current':'get_current_weather','clothing':'get_daily_forecast','wash':'get_daily_forecast'}.get(s['intent'],'get_hourly_forecast')
    if s.get('requested_mode')=='qwen':
        tools=s['decision']['tools']
        required=[name]+(['rank_time_slots'] if s['intent'] in ['activity','rank'] else [])
        if tools!=required:return dict(error='Qwen 工具计划与任务约束不一致，已拒绝执行。',mode='qwen_failed')
        return dict(plan=[dict(name=tools[0],args=dict(latitude=c['latitude'],longitude=c['longitude'],time_window=c['time_window']),city=c['city']) for c in s['resolved_cities']],mode='qwen')
    calls,mode=(None,'rules') if s.get('requested_mode')=='rules' else propose(s)
    # The Python policy constrains LLM proposals to the validated task and coordinates.
    plan=[dict(name=name,args=dict(latitude=c['latitude'],longitude=c['longitude'],time_window=c['time_window']),city=c['city']) for c in s['resolved_cities']]
    if calls and len(calls)==1 and calls[0]['name']==name: mode='qwen'
    elif mode=='qwen': mode='rules:invalid_model_plan'
    return dict(plan=plan,mode=mode)
def call(s,name,args,traces):
    from services.generation import checkpoint
    checkpoint()
    start=time.monotonic()
    try: result=TOOLS[name].invoke(args); status=result.get('status','ok')
    except UpstreamError as exc: result=dict(status='error',reason=str(exc),**exc.diagnostic());status='error'
    except Exception as exc: result=dict(status='error',reason='工具调用失败（程序异常），请稍后重试',kind='program',error_type=type(exc).__name__); status='error'
    checkpoint()
    trace=dict(location_source=s.get('location_source'),query_method=s.get('query_method'),name=name,args=args,status=status,source=result.get('source'),updated_at=result.get('updated_at',result.get('data_time')),duration_ms=round((time.monotonic()-start)*1000),result=result)
    traces.append(trace); store.event(s['sid'],'tool',trace)
    return result
def execute_tools(s):
    traces=[]; results=[dict(call(s,p['name'],p['args'],traces),city=p.get('city',s['city']),time_window=p['args']['time_window']) for p in s['plan'][:2]]
    return dict(traces=traces,results=results)
def validate_results(s):
    if len(s['results'])>1:
        validated=[];failures=[]
        for r in s['results']:
            part=validate_results({**s,'results':[r]})
            if part.get('error'):failures.append(r['city']+'：'+part['error'])
            else:validated.extend(part['results'])
        if not validated:return dict(error='；'.join(failures),failures=failures)
        return dict(results=validated,failures=failures)
    r=s['results'][0]
    if r.get('mode')=='historical_replay': return dict(error='已拒绝将历史回放作为未来预测。')
    if r['status'] not in ['ok','experimental']:
        if s['intent']=='ml' and r.get('mode')=='live_prediction': return dict(results=[r])
        return dict(error='当前无法完成查询：'+r.get('reason','数据不可用'))
    if s['intent']=='ml':
        requested=datetime.fromisoformat(r['time_window']['target_time']).replace(tzinfo=None)
        if datetime.fromisoformat(r['target_time']).replace(tzinfo=None)!=requested:return dict(error='模型返回时间与请求目标不一致，已拒绝该预测。')
        if r.get('prediction') is None or datetime.fromisoformat(r['target_time'])<=local_now('Asia/Shanghai').replace(tzinfo=None): return dict(error='预测时间无效或数据不足。')
    else:
        try:
            now=local_now(r['timezone']).replace(tzinfo=None)
            stamp=datetime.fromisoformat(r['updated_at'])
            if abs((now-stamp).total_seconds())>7200: return dict(error='天气数据更新时间过旧或无效，请稍后重试。')
            data=r['data']
            if isinstance(data,list) and s['intent'] not in ['daily','clothing','wash']:
                data=filter_rows(data,r['time_window'])
                now_aware=local_now(r['time_window']['timezone'])
                data=[row for row in data if datetime.fromisoformat(row['time']).replace(tzinfo=now_aware.tzinfo)>=now_aware]
            elif isinstance(data,list):
                data=filter_rows(data,r['time_window'],daily=True)
            if not data: return dict(error='所选时间超出当前可用预报范围，无法给出建议。')
            import math
            rows=data if isinstance(data,list) else [data]
            fields=['us_aqi','pm2_5'] if s['intent']=='aqi' else ['temperature_min','temperature_max','precipitation_probability'] if s['intent'] in ['daily','clothing','wash'] else ['temperature','wind_speed'] if s['intent']=='current' else ['temperature','wind_speed','precipitation_probability','code']
            if any(any(not isinstance(row.get(k),(int,float)) or not math.isfinite(row[k]) for k in fields) for row in rows): return dict(error='天气数据不完整，无法给出可靠建议。')
            r=dict(r,data=data)
        except (KeyError,ValueError,TypeError): return dict(error='天气数据结构或时间无效。')
    return dict(results=[r])
def self_window(window):
    return '；'.join(chinese(r['start'])+'—'+chinese(r['end']) for r in window['ranges'])

def generate_response(s):
    r=s['results'][0]; traces=list(s['traces']); intent=s['intent'];response_failures=list(s.get('failures',[]))
    if intent=='aqi':
        paragraphs=[]
        for result in s['results']:
            worst=max(result['data'],key=lambda row:row['us_aqi']);aqi=worst['us_aqi']
            label='良好' if aqi<=50 else '中等' if aqi<=100 else '对敏感人群不健康' if aqi<=150 else '不健康' if aqi<=200 else '非常不健康' if aqi<=300 else '危险'
            paragraphs.append(f"**{result.get('city',s['city'])}所选时段空气质量：{label}（US AQI）。**\n\n时段：{self_window(result['time_window'])}。最高 US AQI {aqi:g}，对应 {chinese(worst['time'])}；该小时 PM2.5 {worst['pm2_5']:g} μg/m³。")
        text='\n\n'.join(paragraphs)+"\n\n数据来源：Open-Meteo / CAMS；网格模式估计与预报，非附近监测站实测，US AQI 不等同于中国 AQI。空气质量不能单独证明适合运动，还需结合天气与个人情况。"
    elif intent=='ml':
        reasons={'insufficient_as_of_hourly_data':'缺少预测截止时刻所需的小时数据','outside_model_scope':'所选坐标不在上海市域边界内，暂不支持外市预测','hourly_model_missing':'小时模型文件缺失','incompatible_model':'模型特征或目标不兼容'}
        value=f"{r['prediction']}°C" if r.get('prediction') is not None else '不可预测'
        text=f"**结论：{s['city']}下一小时气温：{value}。**\n\n目标时间：{chinese(r.get('target_time'))}。\n\n模型：{r.get('model') or '未加载'}；数据时间：{chinese(r.get('data_time')) if r.get('data_time') else '数据不足'}；预测状态：{r.get('status')}。\n\n注意："+(reasons.get(r.get('reason'), '实验性预测，实时精度未验证；输入为模式分析数据。'))
    elif intent in ['activity','rank']:
        ranked_cities=[]
        for result in s['results']:
            ranked=call(s,'rank_time_slots',dict(activity=s['activity'],slots=result['data'],time_window=result['time_window']),traces)
            if not ranked.get('data'):
                response_failures.append(result.get('city',s['city'])+'：'+ranked.get('reason','天气数据不足，无法评估活动。')+' 实际评估：'+self_window(result['time_window']))
                continue
            ranked_cities.append((result.get('city',s['city']),ranked['data'],result['data']))
        if not ranked_cities:return dict(response='；'.join(response_failures),traces=traces)
        ranked_cities.sort(key=lambda x:x[1][0]['score'],reverse=True)
        city,ranked,raw=ranked_cities[0]; best=ranked[0]
        conclusion='较适合' if best['score']>=80 else '需谨慎安排' if best['score']>=50 else '不建议'
        if len(ranked_cities)>1:
            scores='，'.join(f"{c} {rs[0]['score']}/100" for c,rs,_ in ranked_cities)
            lead=f"两地最高评分相同：现有温度、风速和降水规则未形成可区分的总分，缺少光照、空气质量及路况数据，无法据此判定哪座城市更适合。{scores}" if ranked_cities[0][1][0]['score']==ranked_cities[1][1][0]['score'] else f"{city}的可用时段评分更高。{scores}"
        else: lead=f"{city}在可用时段内{conclusion}{s['activity']}（最高 {best['score']}/100）。"
        selected=(best.get('hours') or ranked[:3]) if best['score']>=50 else []
        times=merged_slots(selected) if selected else '暂无建议的户外时段'
        if len(ranked_cities)>1:
            times='；'.join(c+' '+merged_slots(rs[0].get('hours') or rs[:1]) if rs[0]['score']>=50 else c+' 暂无建议时段' for c,rs,_ in ranked_cities)
        facts=next(x for x in raw if x['time']==best['time'])
        evidence=[]
        for c,rs,weather in ranked_cities:
            members=rs[0].get('hours') or [rs[0]]
            relevant=[x for x in weather if x['time'] in {h['time'] for h in members}]
            row=dict(temperature=round(sum(x['temperature'] for x in relevant)/len(relevant),1),wind_speed=round(sum(x['wind_speed'] for x in relevant)/len(relevant),1),precipitation_probability=max(x['precipitation_probability'] for x in relevant))
            components=rs[0].get('components',{})
            evidence.append(f"{c}：{rs[0]['score']}/100，{row['temperature']:g}°C（时段平均），平均风速 {row['wind_speed']} km/h，最大小时降水概率 {row['precipitation_probability']}%；温度分 {components.get('temperature','未知')}、降水分 {components.get('precipitation','未知')}、风速分 {components.get('wind','未知')}")
        text=f"**结论：{lead}**\n\n推荐时间段：{times if len(ranked_cities)>1 else city+' '+times}。\n\n关键天气依据："+'；'.join(evidence)+"。\n\n注意：评分来自活动专用天气规则；未评估空气质量、光照或路况，拍照评分不代表光线效果。出发前复查预报。"
    elif intent=='current':
        d=r['data']; text=f"{s['city']}当前气温 {d.get('temperature')}°C，{d.get('description')}，风速 {d.get('wind_speed')} km/h。"
        import math
        amount=d.get('precipitation')
        text+=f'当前数据时段降水量 {amount} mm。' if isinstance(amount,(int,float)) and not isinstance(amount,bool) and math.isfinite(amount) and amount>=0 else '当前降水量数据缺失，无法判断实时降水量。'
        text+='当前降水概率未提供；逐小时降水概率属于预报，不能当作当前实测。'
    elif intent in ['rain','hourly']:
        rows=r['data']; wet=max(rows,key=lambda d:d['precipitation_probability']); lo=min(d['temperature'] for d in rows);hi=max(d['temperature'] for d in rows)
        text=f"**结论：{s['city']}所选时段"+('有降雨风险，建议备伞。' if wet['precipitation_probability']>=40 else '降水概率较低，仍不能保证无雨。')+f"**\n\n关注时间段：{chinese(rows[0]['time'])} 至 {chinese(rows[-1]['time'])}。\n\n关键天气依据：气温 {lo}～{hi}°C，最大小时降水概率 {wet['precipitation_probability']}%（{chinese(wet['time'])}）。\n\n注意：降水概率不代表确定下雨；详细逐小时预报见分析依据。"
        if r['time_window'].get('avoid_rain'):
            dry=[row for row in rows if row['precipitation_probability']<r['time_window'].get('rain_threshold',20) and row['code']<51]
            condition='预报提示降雨风险，条件可能成立' if wet['precipitation_probability']>=40 or any(row['code']>=51 for row in rows) else '目前预报未提示明显降雨，条件尚不能视为成立'
            text=f"**结论：{condition}。**\n\n推荐时间："+(merged_slots(dry[:3]) if dry else '没有满足避雨规则的时段，建议室内安排或推迟')+"。实际评估："+self_window(r['time_window'])+f"。\n\n天气依据：最大小时降水概率 {wet['precipitation_probability']}%；避雨筛选要求每小时概率低于20%且无降水天气码。\n\n注意：这只能降低淋雨风险，不能保证不下雨。"
    elif intent=='clothing':
        # Results already match the validated city-local time window. The legacy
        # day offset is not populated by Qwen and cannot select dates reliably.
        paragraphs=[]
        for d in r['data']:
            lo,hi=d['temperature_min'],d['temperature_max']
            if lo<10:
                outfit='建议外套与长裤，内搭长袖；早晚偏冷，可增加毛衣或保暖内层。'
            elif hi<22:
                outfit='建议长袖搭配薄外套和长裤，方便随气温增减。'
            else:
                outfit='白天可选透气上衣，早晚备一件薄外套；怕冷时搭配长裤。'
            if '长袖' in s['message'] and '外套' in s['message']:
                outfit='长袖加外套可以作为基础搭配。'+('如果只是薄长袖和薄外套，早晚可能偏冷，建议加保暖内层或换稍厚外套。' if lo<10 else '可选容易穿脱的外套，白天热时脱下。')
            if re.search(r'长[袖衬]',s['message']) and ('外套' not in s['message'] or re.search(r'不穿外套|不加外套|不带外套|没有外套',s['message'])):
                if lo<15:
                    outfit='只穿一件长袖加长裤，早晚可能会冷，尤其是薄长袖、怕冷或长时间待在室外时。建议随身带外套，早晚穿上；'+('午后是否能脱外套，还要看衣服厚度、风和个人体感。' if hi<18 else '午后较暖时可按体感脱下外套。')
                elif hi<24:
                    outfit='长袖加长裤通常可以作为基础搭配；薄长袖在早晚、风大或久坐时仍可能偏凉，怕冷的话备一件薄外套。'
                else:
                    outfit='长袖加长裤在较暖的白天可能偏热，建议选轻薄透气的面料；早晚是否需要加衣，还要看个人体感和风。'
            paragraphs.append(f"**{s['city']} {chinese(d['time'])}穿衣建议：**{outfit}")
            paragraphs.append(f"天气依据：气温 {lo}～{hi}°C，最高降水概率 {d['precipitation_probability']}%。"+('有降雨风险，外出带伞，鞋子尽量防滑。' if d['precipitation_probability']>=40 else '降水概率较低，出门前仍可再确认预报。'))
            paragraphs.append('早晚按最低气温穿，午后可减少一层；怕冷或久坐时适当加厚。日预报不代表每个小时的体感，运动出汗后及时擦干并穿回外套。')
        text='\n\n'.join(paragraphs)
    elif intent=='wash':
        rows=r['data']; good=[d['time'] for d,n in zip(rows,rows[1:]) if d['precipitation_probability']<30 and n['precipitation_probability']<30]
        text=s['city']+'：'+('可考虑 '+ '、'.join(chinese(d) for d in good[:3])+' 洗车，当天及次日降水概率均低于30%。' if good else '未找到当天及次日均低降水概率的洗车窗口。')+'未评估沙尘或结冰。'
    else:
        rows=r['data']; text=s['city']+'预报：\n'+'\n'.join(f"- {chinese(d['time'])}：{d.get('temperature_min')}～{d.get('temperature_max')}°C，降水概率 {d.get('precipitation_probability')}%" for d in rows)
    if intent in ['activity','rank']:
        weights=best.get('weights',{})
        label={'wind':'风速优先','temperature':'温度优先','precipitation':'降水优先','balanced':'默认活动权重'}.get(s.get('preference') or 'balanced')
        text+='\n\n实际评分权重（'+label+'）：'+ '、'.join(k+' '+f'{weights.get(k,0):.1%}' for k in ['temperature','precipitation','wind'])+'。优先项权重乘3后归一化；雷暴、极端天气限制仍保留。' if label!='默认活动权重' else '\n\n评分使用默认活动权重，未做个性化调整。'
    if any(result.get('cached') for result in s['results']):text+='\n\n数据说明：网络失败，使用5分钟内同坐标缓存；各城市原更新时间见执行记录。'
    if response_failures:text+='\n\n部分结果不可用：'+'；'.join(response_failures)+'。已保留成功城市结果，无法完成完整比较。'
    if s.get('requested_mode')=='qwen':
        from services.qwen_decision import explain
        grounded=text.split('\n\n')
        text,log=explain(s,text)
        return dict(response=text,traces=traces,grounded_paragraphs=grounded,explanation_log=log,mode='qwen' if log['status']=='ok' else 'qwen_partial')
    return dict(response=text,traces=traces,grounded_paragraphs=text.split('\n\n'))

def respond_without_tools(s):
    if s['intent']=='out_of_scope':
        text='我专注于天气查询、户外活动安排和天气模型预测，暂不处理这个非天气请求。你的天气会话上下文已保留。'
    else:
        ctx=s.get('context',{});parts=[]
        if ctx.get('activity'):parts.append('你之前提到的活动是'+ctx['activity'])
        if ctx.get('city'):parts.append('城市是'+ctx['city'])
        window=ctx.get('time_window') or {}
        if window.get('dates'):parts.append('日期是'+'、'.join(window['dates'])+'，时段是'+window.get('period','全天'))
        labels={'wind':'风速优先','temperature':'温度优先','precipitation':'降水优先','balanced':'默认活动权重'}
        if ctx.get('preference'):parts.append('评分偏好是'+labels.get(ctx['preference'],'未支持'))
        if ctx.get('avoid_wind'):parts.append('并且希望避开强风')
        text='；'.join(parts)+'。' if parts else '当前会话尚未记录你提到的活动、城市、日期或偏好；我不会使用其他会话的信息。'
    return dict(response=text,traces=[],mode='qwen' if s.get('requested_mode')=='qwen' else 'rules',grounded_paragraphs=[text])

def handle_error(s): return dict(response=s.get('error','服务暂时不可用，请稍后重试。'))
def guard_node(function):
    def execute(state):
        from services.generation import checkpoint
        checkpoint();result=function(state);checkpoint();return result
    return execute

def build_graph():
    g=StateGraph(State)
    for f in [parse_request,check_context,clarify_request,plan_tools,execute_tools,validate_results,generate_response,handle_error,respond_without_tools]: g.add_node(f.__name__,guard_node(f))
    g.add_edge(START,'parse_request'); g.add_edge('parse_request','check_context')
    g.add_conditional_edges('check_context',lambda s:'handle_error' if s.get('error') else 'clarify_request' if s.get('missing') else 'respond_without_tools' if s.get('intent') in ['recall','out_of_scope'] else 'plan_tools')
    g.add_conditional_edges('plan_tools',lambda s:'handle_error' if s.get('error') else 'execute_tools'); g.add_edge('execute_tools','validate_results')
    g.add_conditional_edges('validate_results',lambda s:'handle_error' if s.get('error') else 'generate_response')
    for n in ['generate_response','clarify_request','handle_error','respond_without_tools']: g.add_edge(n,END)
    return g.compile()
GRAPH=build_graph()
def token_usage(*logs):
    """Sum provider-reported usage across this turn, retaining unknown usage."""
    totals=[]
    for log in logs:
        if log is None:continue
        usage=log.get('usage') or {}
        total=usage.get('total_tokens')
        if not isinstance(total,int) or isinstance(total,bool) or total<0:
            totals.append(None)
        else:totals.append(total)
    known=[n for n in totals if n is not None]
    return dict(total_tokens=sum(known) if known else None,complete=bool(totals) and len(known)==len(totals))

def chat(sid,message,home_city=None,mode=None):
    import uuid
    started=time.monotonic();request_id=str(uuid.uuid4())
    path=[]
    diagnostic_token=DIAGNOSTICS.set([]);request_token=REQUEST_ID.set(request_id)
    initial=dict(sid=sid,message=message,history=store.recent_history(sid),context=store.read(sid),home_city=home_city,requested_mode=mode,request_id=request_id)
    result=dict(initial)
    try:
        for step in GRAPH.stream(initial,config={'recursion_limit':12},stream_mode='updates'):
            for node,update in step.items():
                path.append(node); result.update(update or {})
        diagnostics=list(DIAGNOSTICS.get() or [])
    finally:
        DIAGNOSTICS.reset(diagnostic_token);REQUEST_ID.reset(request_token)
    for item in diagnostics:store.event(sid,'service',item)
    final_cities=normalize_cities([c['city'] for c in result.get('resolved_cities',[])] or result.get('requested_cities') or ([result['city']] if result.get('city') else []))
    store.event(sid,'parse',dict(cities=final_cities,city_source=result.get('city_source'),time_window=result.get('time_window')))
    if result.get('resolved_cities') and not result.get('missing') and result.get('mode')!='qwen_failed' and result.get('intent') not in ['recall','out_of_scope']:store.save(sid,{k:result.get(k) for k in ['city','latitude','longitude','activity','intent','day','period','timezone','time_window','location_verified_at','avoid_wind','preference','query_method','location_source']})
    store.event(sid,'conversation',dict(message=message,response=result['response'],path=path,mode=result.get('mode','rules')))
    execution=dict(location_source=result.get('location_source'),query_method=result.get('query_method'),request_id=request_id,session_id=sid,requested_mode=mode or 'environment',actual_mode=result.get('mode','rules'),intent=result.get('intent'),preference=result.get('preference'),history_turns=len(initial['history']),cities=final_cities,activity=result.get('activity'),time_window=result.get('time_window'),path=path,qwen=result.get('qwen_log'),explanation=result.get('explanation_log'),grounded_paragraphs=result.get('grounded_paragraphs'),tools=result.get('traces',[]),error_type=(result.get('qwen_log') or {}).get('error_type') or (result.get('explanation_log') or {}).get('error_type') or ('validation_or_upstream' if result.get('error') else None),duration_ms=round((time.monotonic()-started)*1000))
    if mode=='qwen' or result.get('qwen_log'):
        execution['token_usage']=token_usage(result.get('qwen_log'),result.get('explanation_log'))
    store.event(sid,'execution',execution)
    return dict(request_id=request_id,execution=execution,session_id=sid,response=result['response'],mode=result.get('mode','rules'),mode_label='Qwen 智能模式' if result.get('mode')=='qwen' else 'Qwen 未成功' if result.get('mode')=='qwen_failed' else 'Qwen 部分执行（解释失败，使用已验证事实）' if result.get('mode')=='qwen_partial' else '规则模式',city='、'.join(result.get('cities') or ([result['city']] if result.get('city') else [])),city_source=result.get('city_source'),path=path,parsed_cities=final_cities,service_diagnostics=diagnostics,time_window=result.get('time_window'),tools=result.get('traces',[]))

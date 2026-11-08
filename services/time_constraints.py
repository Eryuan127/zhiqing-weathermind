"""Single city-local time contract, shared by graph and tools. End is exclusive."""
import re
from datetime import datetime,timedelta,date,time
from zoneinfo import ZoneInfo

def local_now(zone): return datetime.now(ZoneInfo(zone))
def number(value):
    if value.isdigit():return int(value)
    numbers={'零':0,'一':1,'二':2,'两':2,'三':3,'四':4,'五':5,'六':6,'七':7,'八':8,'九':9,'十':10}
    if '十' in value:
        left,right=value.split('十');return numbers.get(left,1)*10+numbers.get(right,0)
    return numbers[value]

def parse_window(text,zone,previous=None,activity=None,ml=False):
    now=local_now(zone); today=now.date(); dates=None; exact=None
    period='晚上' if re.search('今晚|明晚|晚上|夜里',text) else '下午' if '下午' in text else '早上' if re.search('早上|上午|明早',text) else None
    specific=re.search(r'(下个月|上个月)(\d{1,2})[日号]',text)
    calendar=re.search(r'(\d{4})年(\d{1,2})月(\d{1,2})[日号]',text)
    iso=re.search(r'(\d{4})-(\d{2})-(\d{2})',text)
    if iso: dates=[date(*map(int,iso.groups()))]
    elif specific:
        index=today.year*12+today.month-1+(1 if specific[1]=='下个月' else -1)
        year,month=divmod(index,12);month+=1
        dates=[date(year,month,int(specific[2]))]
    elif calendar: dates=[date(*map(int,calendar.groups()))]
    elif '下个月' in text:raise ValueError('请提供下个月的具体日期。')
    elif '下周' in text:
        start=today+timedelta(days=7-today.weekday())
        named=re.search(r'下周([一二三四五六日天])',text)
        dates=[start+timedelta(days=min('一二三四五六日天'.index(named[1]),6))] if named else [start+timedelta(days=i) for i in range(7)]
    elif '周末' in text:
        sat=today+timedelta(days=5-today.weekday())
        dates=[sat,sat+timedelta(days=1)]
    elif re.search(r'周[一二三四五六日天]|星期[一二三四五六日天]',text):
        w=re.search(r'(?:周|星期)([一二三四五六日天])',text)[1];idx='一二三四五六日天'.index(w);idx=min(idx,6)
        dates=[today+timedelta(days=(idx-today.weekday())%7)]
    elif '后天' in text: dates=[today+timedelta(days=2)]
    elif re.search('明天|明早|明晚',text): dates=[today+timedelta(days=1)]
    elif re.search(r'昨天|(?<!当)前天',text): dates=[today-timedelta(days=2 if '前天' in text else 1)]
    elif re.search('今天|今晚',text): dates=[today]
    elif re.search('那|呢',text) and previous:
        dates=[date.fromisoformat(d) for d in previous['dates']]
    if re.search(r'\d+\.\d+\s*(?:个)?小时|半(?:个)?小时|一个半小时|一小时半',text):raise ValueError('当前小时预报仅支持整数小时持续时长，无法精确评估半小时。')
    duration_match=re.search(r'(?:连续|最好[的]?|选|安排|持续)?([一二两三四五六七八九十\d]+)(?:个)?小时',text)
    duration=number(duration_match[1]) if duration_match else previous.get('duration_hours') if previous and re.search('那|呢',text) and not ml else None
    if duration is not None and not 1<=duration<=24:raise ValueError('活动持续时长需为1至24小时。')
    clock=re.search(r'(\d{1,2}|[零一二两三四五六七八九十]{1,3})(?::(\d{2})|点(?:(\d{1,2})分)?)(?:\s*(?:到|至|—|-)\s*(\d{1,2}|[零一二两三四五六七八九十]{1,3})(?::(\d{2})|点(?:(\d{1,2})分)?))?',text)
    hour=re.search(r'(?<!\d)(\d{1,2})[点时](?:(\d{1,2})分)?',text)
    if clock or hour:
        h=number(clock[1]) if clock else int(hour[1]);minute=int((clock[2] or clock[3] or 0) if clock else hour[2] or 0)
        if period=='下午' and h<12:h+=12
        if period=='晚上' and h<12:h+=12
        if not 0<=h<=23 or not 0<=minute<=59: raise ValueError('时间无效，请确认小时和分钟。')
        exact=datetime.combine((dates or [today])[0],time(h,minute),ZoneInfo(zone))
    explicit_range=None
    if clock and clock[4]:
        eh=number(clock[4]);em=int(clock[5] or clock[6] or 0)
        if period in ['下午','晚上'] and eh<12:eh+=12
        if not 0<=eh<=23 or not 0<=em<=59:raise ValueError('时间无效')
        end_clock=datetime.combine((dates or [today])[0],time(eh,em),ZoneInfo(zone))
        if end_clock<=exact:raise ValueError('结束时间必须晚于开始时间')
        explicit_range=(exact,end_clock)
    if ml and dates is None and exact is None:
        exact=now.replace(minute=0,second=0,microsecond=0)+timedelta(hours=1);dates=[exact.date()]
    dates=dates or [today]
    if period is None: period=previous.get('period','全天') if previous and re.search('那|呢',text) else '全天'
    bounds={'早上':(6,12),'下午':(12,18),'晚上':(18,24),'全天':(6,22) if activity else (0,24)}[period]
    ranges=[]
    for d in dates:
        start=datetime.combine(d,time.min,ZoneInfo(zone))+timedelta(hours=bounds[0]);end=datetime.combine(d,time.min,ZoneInfo(zone))+timedelta(hours=bounds[1])
        if exact: start=exact;end=exact+timedelta(hours=duration or 1)
        if explicit_range:start,end=explicit_range
        ranges.append(dict(start=start.isoformat(),end=end.isoformat()))
        if exact:break
    return dict(timezone=zone,ranges=ranges,dates=[d.isoformat() for d in dates],period=period,target_time=exact.isoformat() if exact and not explicit_range else None,duration_hours=duration if not ml else None,avoid_rain=bool(re.search('不要淋雨|避免淋雨|不淋雨|避雨',text)),rain_threshold=20)

def contains(stamp,window):
    dt=datetime.fromisoformat(stamp)
    if dt.tzinfo is None:dt=dt.replace(tzinfo=ZoneInfo(window['timezone']))
    return any(datetime.fromisoformat(r['start'])<=dt<datetime.fromisoformat(r['end']) for r in window['ranges'])

def filter_rows(rows,window,daily=False):
    if daily:return [r for r in rows if r['time'] in window['dates']]
    return [r for r in rows if contains(r['time'],window)]

def chinese(stamp):
    if not stamp:return '未知'
    d=datetime.fromisoformat(stamp);week='一二三四五六日'[d.weekday()]
    return f'{d.month}月{d.day}日（周{week}）'+(f'{d.hour:02d}:{d.minute:02d}' if 'T' in stamp else '')

def merged_slots(rows):
    stamps=sorted(datetime.fromisoformat(r['time']) for r in rows);groups=[]
    for d in stamps:
        if groups and groups[-1][1]==d and groups[-1][0].date()==d.date():groups[-1][1]=d+timedelta(hours=1)
        else:groups.append([d,d+timedelta(hours=1)])
    return '；'.join(chinese(a.isoformat())+'—'+b.strftime('%H:%M') for a,b in groups)

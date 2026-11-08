"""Conservative explicit place extraction: unknown names never become default Shanghai."""
import re
TECH={'ridge','mae','rmse','c','f','aqi','api','ml','qwen','langgraph','langchain','python','sklearn','weather','model','temperature','please','help','the','in','and'}
def normalize_city(name):
    name=name.strip(' ，。？！?!.').removesuffix('市')
    name=re.sub(r'^(明天下午|今天下午|明天上午|明天晚上|明天|今天|后天|今晚|下午|上午|早上|晚上|周末|下周|查询|请查询|比较|帮我|我想在|在)+','',name)
    for known in ['上海','北京','杭州','广州','深圳']:
        if re.match(re.escape(known)+r'(?:跑步|散步|拍照|骑行|的|哪个|更)',name):return known
    return name

def normalize_cities(names):
    result=[];seen=set()
    for name in names:
        name=normalize_city(name);key=name.casefold()
        if not name or key in TECH or key in seen:continue
        seen.add(key);result.append(name)
    return result

KNOWN=['上海','北京','杭州','广州','深圳']
def extract_cities(text):
    follow=re.fullmatch(r'那([\u4e00-\u9fff]{2,8}?)(?:市)?呢[？?。]?',text)
    if follow and follow[1] not in ['明天','后天','今天','晚上','下午','早上','上午','周末']:return normalize_cities([follow[1]])
    names=sorted([c for c in KNOWN if c in text],key=text.index)
    latin=re.findall(r'[A-Za-z][A-Za-z0-9]*(?:[ -][A-Za-z]+)*',text)
    for word in latin:
        if word.casefold() not in TECH and re.search(r'(?:查询|查|在|城市|地点)\s*'+re.escape(word)+r'|'+re.escape(word)+r'(?=明天|今天|天气|后天|的天气)',text):names.append(word)
    for match in re.finditer(r'(?:和|与|、)([\u4e00-\u9fffA-Za-z0-9]+?)(?=哪个|哪座|更|明天|今天|后天|周|适合|天气|$)',text):
        names.append(match[1].removesuffix('市'))
    prefix=re.match(r'^(?:查询|请查询|比较)?([\u4e00-\u9fffA-Za-z0-9]+?)(?:和|与|、)',text)
    if prefix:names.append(prefix[1].removesuffix('市'))
    if names:return normalize_cities([n for n in names if not re.search('温度|风速|降水|湿度|气温',n)])
    cleaned=re.sub(r'^(请|帮我|帮忙|麻烦|查询|查一下|查|看看|看一下|预测|天气预报|我想知道|我想查|帮我看看)+','',text)
    cleaned=re.sub(r'^(?:(?:下周|本周|周|星期)[一二三四五六日天]|(?:上午|下午|晚上|早上)|(?:[零一二两三四五六七八九十\d]+点)|(?:\d{1,2}:\d{2})|到|至)+','',cleaned)
    cleaned=re.sub(r'^(今天|明天|后天|今晚|周末|周[一二三四五六日天]|星期[一二三四五六日天]|下周|明天下午|下午|早上|晚上)+','',cleaned)
    if re.match(r'适不适合|适合|可以|能不能|什么时候|几点',cleaned):return []
    match=re.match(r'([\u4e00-\u9fff]{2,12}?)(?:市|明天|今天|后天|周末|下周|下个月|适合|的天气|天气)',cleaned)
    if match and match[1] not in ['现在','当前','明天','今天','后天','什么','一下','那','晚上','几点','什么时候','哪个时间','哪天']:
        return normalize_cities([match[1]])
    if re.fullmatch(r'[\u4e00-\u9fff]{2,8}市',cleaned):return normalize_cities([cleaned[:-1]])
    return []

let currentCity=null;
let weatherData,selectedField='temperature',weatherCity='';
const temp=v=>Number.isFinite(v)?v.toFixed(1):'—';
const $=id=>document.getElementById(id);let controller,sequence=0,retryAction,chart;const show=v=>v??'—';
function element(tag,text,cls){const e=document.createElement(tag);e.textContent=text;if(cls)e.className=cls;return e}
async function run(action){controller?.abort();controller=new AbortController();const id=++sequence;retryAction=action;$('status').className='';$('status').textContent='正在查询，请稍候…';$('dashboard').setAttribute('aria-busy','true');WeatherUI.weather('loading');$('search').querySelector('button').disabled=true;try{await action(controller.signal,id);if(id===sequence){$('status').textContent='';}}catch(e){if(id===sequence&&e.name!=='AbortError'){WeatherMindLocation.resolve();$('status').className='error';$('status').textContent=e.message;const b=element('button','重试');b.onclick=()=>run(retryAction);$('status').append(b);WeatherUI.weather('error',e.message,()=>run(retryAction))}}finally{if(id===sequence){$('dashboard').setAttribute('aria-busy','false');document.querySelectorAll('.current[data-state=loading],.trend[data-state=loading],.detail[data-state=loading],.week[data-state=loading],.hourly-panel[data-state=loading]').forEach(card=>WeatherUI.state(card,weatherData?'ready':'empty','请选择城市候选后查看数据',()=>toggleSaved(true)));$('search').querySelector('button').disabled=false}}}
async function get(url,signal){const r=await fetch(url,{signal});const d=await r.json();if(!r.ok)throw Error(d.error||'查询失败，请重试。');return d}
function publishLocation(city,timezone=null){
 WeatherMindLocation.data={latitude:city.latitude,longitude:city.longitude,city:city.source==='browser'&&!city.resolved_city?null:city.name,country:city.country||null,timezone,source:city.source||'manual',permission_granted:city.permission_granted===true,obtained_at:Date.now()/1000};
 ZhiqingAuth.ready.then(()=>{WeatherMindLocation.owner=ZhiqingAuth.user?.account||null;WeatherMindLocation.resolve();});
}
function choose(city){publishLocation(city);$('candidates').replaceChildren();run(async(signal,id)=>{const d=await get(`/api/weather?latitude=${city.latitude}&longitude=${city.longitude}`,signal);if(id!==sequence)return;render(city,d);$('city').value='';})}
$('search').onsubmit=e=>{e.preventDefault();const name=$('city').value.trim();if(name.length<2){$('status').textContent='请输入至少两个字符的城市名称。';return} $('candidates').replaceChildren();run(async(signal,id)=>{const d=await get('/api/locations?name='+encodeURIComponent(name),signal);if(id!==sequence)return;if(!d.locations.length)throw Error('未找到城市，请尝试完整名称或英文名。');$('candidates').append(element('p','请选择城市：'));d.locations.forEach(c=>{const b=element('button',[c.name,c.admin1,c.admin2,c.country].filter(Boolean).join(' · '));b.onclick=()=>{toggleSaved(false);choose(c)};$('candidates').append(b)})})};
function render(city,d){d={...d,hourly:Array.isArray(d.hourly)?d.hourly:[],daily:Array.isArray(d.daily)?d.daily:[],warnings:Array.isArray(d.warnings)?d.warnings:[]};WeatherUI.weather('ready');currentCity={...city};publishLocation(city,d.timezone||null);
renderSavedCities();$('place').textContent=city.name;$('selected-city').textContent=city.name;$('highlow').textContent='↑ '+temp(d.daily[0]?.temperature_max)+'°C　 ↓ '+temp(d.daily[0]?.temperature_min)+'°C';$('region').textContent=city.country?'，'+city.country:'';const c=d.current||{};$('nowIcon').replaceChildren(weatherIcon(c));$('temperature').textContent=temp(c.temperature)+'°C';$('description').textContent=c.description||'天气状态缺失';$('updated').textContent=typeof c.time==='string'?'更新于 '+c.time.slice(11,16)+' · 城市当地时间':'更新时间缺失';$('metrics').replaceChildren();[['体感温度',c.feels_like,'°C'],['相对湿度',c.humidity,'%'],['风速',c.wind_speed,'km/h'],['降水概率',d.daily[0]?.precipitation_probability,'%']].forEach(([name,val,unit])=>{const box=element('article','','metric');const reading=element('strong','','metric-reading');reading.append(element('span',unit==='°C'?temp(val):show(val),'metric-number'),document.createTextNode(' '),element('span',unit,'metric-unit'));box.append(element('p',name),reading);WeatherVisual.metric(box,name,val,unit);$('metrics').append(box)});$('hourly').replaceChildren();$('hourly-preview').replaceChildren();$('hourly-expansion').hidden=d.hourly.length<=6;d.hourly.forEach((h,i)=>{const box=hourlyRow(h,i,d.hourly);const target=i<6?$('hourly-preview'):$('hourly');if(i===0||hourPeriod(h)!==hourPeriod(d.hourly[i-1]))target.append(element('div',hourPeriod(h),'hourly-period'));target.append(box)});$('daily').replaceChildren();d.daily.forEach((h,i)=>{const box=element('article','','day'+(i===0?' today':'')+(h.precipitation_probability>=60?' rainy':''));const validDate=typeof h.time==='string'&&Number.isFinite(Date.parse(h.time+'T12:00:00Z'));const weekday=validDate?new Intl.DateTimeFormat('zh-CN',{weekday:'long',timeZone:'UTC'}).format(new Date(h.time+'T12:00:00Z')):'日期缺失';box.append(element('strong',i===0?'今天':i===1?'明天':weekday),element('p',validDate?Number(h.time.slice(5,7))+'月'+Number(h.time.slice(8))+'日':'—'),weatherIcon(h),element('p',h.description),element('strong',temp(h.temperature_min)+'° — '+temp(h.temperature_max)+'°'),rainReading(h.precipitation_probability));decorateDay(box,h,i,d.daily);$('daily').append(box)});weatherData=d;if(window.echarts){chart??=echarts.init($('chart'));weatherCity=city.name;drawChart();updateAdvice();}else{$('chart').textContent='趋势图组件未加载，下方仍可查看逐小时数据。'}window.dispatchEvent(new CustomEvent('weather-rendered',{detail:{city:{...city},weather:d}}));if(!d.current||!Number.isFinite(c.temperature))WeatherUI.state(document.querySelector('.current'),'empty','该城市当前天气数据缺失',()=>choose(city));if(!d.hourly.length){WeatherUI.state(document.querySelector('.trend'),'empty','暂无逐小时预报',()=>choose(city));WeatherUI.state(document.querySelector('.hourly-panel'),'empty','暂无逐小时预报',()=>choose(city));}if(!d.daily.length)WeatherUI.state(document.querySelector('.week'),'empty','暂无未来七日预报',()=>choose(city));if(![c.feels_like,c.humidity,c.wind_speed].some(Number.isFinite))WeatherUI.state(document.querySelector('.detail'),'empty','该城市天气指标缺失',()=>choose(city));if(d.warnings.length){const note=element('p',d.warnings.join(' '));$('hourly').prepend(note)}}
window.addEventListener('resize',()=>{chart?.resize();drawChart();});function initialLocation(){
 const startupSequence=sequence;
 const unavailable=reason=>{if(sequence!==startupSequence)return;WeatherMindLocation.data=null;WeatherMindLocation.resolve();$('dashboard').setAttribute('aria-busy','false');$('place').textContent='选择城市';$('selected-city').textContent='选择城市';$('updated').textContent=reason;WeatherUI.weather('empty','定位不可用，请手动选择城市',()=>toggleSaved(true));$('status').textContent=reason+'，请搜索并选择城市。';};
 if(!navigator.geolocation){unavailable('浏览器不支持定位');return;}
 $('updated').textContent='正在获取你的位置…';
 navigator.geolocation.getCurrentPosition(pos=>{
  if(sequence!==startupSequence)return;
  const city={name:'城市解析中',source:'browser',permission_granted:true,latitude:pos.coords.latitude,longitude:pos.coords.longitude};
  choose(city);const lookupSequence=sequence;
  resolveCityName(city).then(location=>{
   if(sequence!==lookupSequence)return;
   Object.assign(city,{name:location.city,resolved_city:true,country:location.country});
   updateLocatedCity(city);
  }).catch(()=>{
   if(sequence!==lookupSequence)return;
   city.name='城市名解析失败';updateLocatedCity(city);
  });
},e=>unavailable(e.code===1?'你已拒绝定位':e.code===3?'定位超时':'暂时无法获取位置'),{timeout:8000,maximumAge:300000});
}initialLocation();

async function resolveCityName(city){
 const params=new URLSearchParams({latitude:String(city.latitude),longitude:String(city.longitude),localityLanguage:'zh'});
 // The free reverse-geocode-client endpoint is called only by the browser,
 // with the device's consented current GPS coordinates; never use IP fallback.
 const response=await fetch('https://api.bigdatacloud.net/data/reverse-geocode-client?'+params,{signal:AbortSignal.timeout(8000),credentials:'omit',referrerPolicy:'no-referrer'});
 if(!response.ok)throw Error('城市名解析失败');
 const data=await response.json();
 const name=data.city||data.locality;
 if(typeof name!=='string'||!name.trim())throw Error('缺少城市名');
 return {city:name.trim(),country:data.countryName||null};
}
function updateLocatedCity(city){
 const zone=WeatherMindLocation.data?.timezone||null;
 if(currentCity&&currentCity.source==='browser'&&sameCity(currentCity,city))Object.assign(currentCity,city);
 publishLocation(city,zone);$('selected-city').textContent=city.name;$('place').textContent=city.name;$('region').textContent=city.country?'，'+city.country:'';
 weatherCity=city.name;if(weatherData)drawChart();renderSavedCities();window.dispatchEvent(new Event('weather-city-renamed'));
}

function weatherIcon(weather){return WeatherVisual.icon(weather);}

function drawChart(){
 if(!chart||!weatherData||['loading','error'].includes(document.querySelector('.trend').dataset.state))return;
 const css=getComputedStyle(document.documentElement),color=name=>css.getPropertyValue(name).trim();
 const unit={temperature:'°C',precipitation_probability:'%',wind_speed:' km/h'}[selectedField],rows=weatherData.hourly,values=rows.map(h=>h[selectedField]).filter(Number.isFinite);
 if(!values.length){WeatherUI.state(document.querySelector('.trend'),'empty','该指标暂无有效数据',()=>choose(currentCity));return;}
 WeatherUI.state(document.querySelector('.trend'),'ready');
 const lo=Math.min(...values),hi=Math.max(...values),padding=Math.max(2,(hi-lo)*.35),isRain=selectedField==='precipitation_probability';
 const min=isRain?0:selectedField==='wind_speed'?Math.max(0,Math.floor(lo-padding)):Math.floor(lo-padding),max=isRain?100:Math.ceil(hi+padding),primary=color('--color-primary');
 chart.setOption({animation:false,grid:{left:50,right:28,top:40,bottom:48},tooltip:{trigger:'axis',confine:true,backgroundColor:color('--color-tooltip-surface'),borderColor:color('--color-tooltip-border'),extraCssText:innerWidth>720?'backdrop-filter:blur(12px) saturate(125%);-webkit-backdrop-filter:blur(12px) saturate(125%);box-shadow:1px 6px 20px rgba(42,76,125,.1);':'box-shadow:1px 4px 12px rgba(42,76,125,.08);',textStyle:{color:color('--color-text')},formatter:items=>{const point=Array.isArray(items)?items[0]:items;const h=point?.componentType==='markPoint'?rows.find(row=>row[selectedField]===hi):rows[point?.dataIndex];if(!h)return '数据点暂不可用';return `${(h.time||'时间缺失').replace('T',' ')} · ${h.description||'天气描述缺失'}<br>气温 ${temp(h.temperature)}°C　降水概率 ${show(h.precipitation_probability)}%　风速 ${show(h.wind_speed)} km/h`;}},xAxis:{type:'category',boundaryGap:isRain,data:rows.map(h=>h.time?.slice(5).replace('T',' ')||'—'),axisLine:{show:false},axisTick:{show:false},axisLabel:{color:color('--color-text-secondary'),interval:innerWidth<720?5:2,formatter:(v,index)=>index===0||rows[index]?.time?.slice(0,10)!==rows[Math.max(0,index-(innerWidth<720?6:3))]?.time?.slice(0,10)?v.slice(0,5)+'\n'+v.slice(6):v.slice(6)}},yAxis:{type:'value',min,max,interval:(max-min)/4,splitNumber:4,axisLabel:{color:color('--color-text-secondary'),formatter:v=>Number(v.toFixed(1))+unit},splitLine:{lineStyle:{color:color('--color-border')}}},series:[{type:isRain?'bar':'line',barMaxWidth:18,smooth:false,symbol:'circle',symbolSize:7,connectNulls:false,data:rows.map(h=>Number.isFinite(h[selectedField])?h[selectedField]:null),markPoint:{symbol:'circle',symbolSize:10,itemStyle:{color:primary,borderColor:color('--color-surface'),borderWidth:2,shadowBlur:10,shadowColor:color('--color-chart-fill')},label:{position:'top',distance:12,fontSize:12,color:color('--color-primary-ink'),backgroundColor:color('--color-surface'),borderColor:color('--color-border'),borderWidth:1,padding:[4,8],borderRadius:6,formatter:p=>Number(p.value).toFixed(1)+unit},data:isRain?[]:[{type:'max',name:'最高'}]},lineStyle:{color:primary,width:3},itemStyle:isRain?{color:primary,borderRadius:[5,5,0,0]}:{color:color('--color-surface'),borderColor:primary,borderWidth:2},areaStyle:isRain?undefined:{color:new echarts.graphic.LinearGradient(0,0,0,1,[{offset:0,color:color('--color-chart-fill')},{offset:1,color:color('--color-chart-fade')}]),opacity:1}}]},true);
 chart.off('click');chart.on('click',p=>{if(p.componentType==='series'&&Number.isInteger(p.dataIndex)){const h=rows[p.dataIndex];addReply((h.time||'时间缺失').replace('T',' ')+' · '+judgeHour(h));}});
}

document.querySelectorAll('[data-field]').forEach(b=>b.onclick=()=>{selectedField=b.dataset.field;document.querySelectorAll('[data-field]').forEach(x=>x.classList.toggle('active',x===b));drawChart()});
function openSearch(){ $('city').focus(); if($('city').value.trim())$('search').requestSubmit(); }
$('city-toggle').onclick=()=>toggleSaved($('saved-cities').hidden);

function decorateDay(box,h,i,days){
 box.classList.add(h.code===0||h.code===1?'clear-day':h.code>=71&&h.code<=77?'snow-day':h.precipitation_probability>=60?'wet-day':'cloud-day');
 const valid=days.flatMap(day=>[day.temperature_min,day.temperature_max]).filter(Number.isFinite);
 const track=element('div','','temperature-track');track.setAttribute('role','img');
 if(Number.isFinite(h.temperature_min)&&Number.isFinite(h.temperature_max)&&valid.length){const low=Math.min(...valid),range=Math.max(1,Math.max(...valid)-low);const fill=element('span','','temperature-fill');fill.style.left=((h.temperature_min-low)/range*100)+'%';fill.style.width=Math.max(2,(h.temperature_max-h.temperature_min)/range*100)+'%';track.append(fill);track.setAttribute('aria-label',`最低 ${h.temperature_min}°C，最高 ${h.temperature_max}°C`);}else track.setAttribute('aria-label','温度区间数据缺失');
 box.append(track);
 if(i>0&&typeof h.temperature_max==='number'&&typeof days[i-1].temperature_max==='number'){
 const delta=h.temperature_max-days[i-1].temperature_max;if(Math.abs(delta)>=3)box.append(element('span',(delta>0?'升温 ':'降温 ')+Math.abs(delta).toFixed(1)+'°','change-note'));
 }
}
function judgeHour(h){
 const facts=`气温 ${temp(h.temperature)}°C，降水概率 ${show(h.precipitation_probability)}%，风速 ${show(h.wind_speed)} km/h。`;
 if([95,96,99].includes(h.code))return facts+'有雷暴预报，建议取消户外运动。';
 if(h.precipitation_probability==null||h.temperature==null||h.wind_speed==null)return facts+'关键数据不足，暂不判断运动适宜程度。';
 if(h.precipitation_probability>=40||h.wind_speed>=25||h.temperature<5||h.temperature>30)return facts+'按降水≥40%、风速≥25 km/h 或气温不在5至30°C的保守规则，建议改为室内运动。';
 return facts+'天气条件初步适合轻量户外活动；出发前再确认天气，并结合体感与空气质量。';
}
function updateAdvice(){}
function addReply(text){$('conversation').append(element('p',text,'reply'));setAssistant(true);$('conversation').scrollTop=$('conversation').scrollHeight;}
let agentBusy=false;
let citySync=Promise.resolve(),panelLoading=null,panelReady=false,welcomeControl=null,compactId=null,compactTurns=0;
function panelBusy(value){agentBusy=value;const disabled=value||compactTurns>=5;$('question').disabled=disabled;$('ask-form').querySelector('button').disabled=disabled;document.querySelectorAll('.quick-questions button').forEach(b=>b.disabled=disabled);}
async function loadPanel(){
 if(panelReady)return;
 if(panelLoading)return panelLoading;
 panelLoading=(async()=>{
  panelBusy(true);
  try{
   const r=await fetch('/api/agent/compact',{method:'POST'});if(!r.ok)throw Error('无法创建小窗会话');const data=await r.json();compactId=data.id;compactTurns=0;
   if(welcomeControl)welcomeControl.finish=true;
   $('conversation').replaceChildren();
   const greeting=element('div','','reply welcome-reply');$('conversation').append(greeting);
   welcomeControl={finish:false};WeatherMindAgent.type(greeting,window.WeatherContextUI?.greeting()||'hi，我是知晴，可以问我明天要不要带伞、今天适不适合跑步，或周末的天气。',()=>{},welcomeControl);
   panelReady=true;$('conversation').scrollTop=0;
  }catch(e){panelReady=false;$('conversation').replaceChildren(element('p',e.message+'，请关闭后重新打开。','reply'));}
  finally{panelBusy(false);panelLoading=null;}
 })();return panelLoading;
}
async function answer(question){
 if(agentBusy||!panelReady||compactTurns>=5)return;
 if(welcomeControl)welcomeControl.finish=true;
 panelBusy(true);$('conversation').append(element('p',question,'user-question'));
 const pending=element('div','','reply');$('conversation').append(pending);WeatherMindAgent.loading(pending);$('conversation').scrollTop=$('conversation').scrollHeight;
 try{await WeatherMindAgent.locationReady();const r=await fetch('/api/agent/compact/'+encodeURIComponent(compactId)+'/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({message:question,home_city:WeatherMindAgent.home()})});const data=await r.json();if(!r.ok){if(data.limit_reached){compactTurns=5;showCompactLimit();}throw Error(data.error||'请求失败');}compactTurns=5-data.remaining;$('compact-source').textContent=(data.mode_label||'天气助手')+'回复 · 预报仅供参考，可在完整对话查看依据';pending.replaceChildren();await WeatherMindAgent.type(pending,data.response,()=>{$('conversation').scrollTop=$('conversation').scrollHeight});window.dispatchEvent(new Event('agent-history-updated'));if(compactTurns>=5)showCompactLimit();}
 catch(e){pending.textContent='请求失败，请重试。'+e.message}finally{panelBusy(false);$('conversation').scrollTop=$('conversation').scrollHeight;}
}
function showCompactLimit(){
 if($('compact-limit'))return;
 const box=element('div','','compact-limit');box.id='compact-limit';box.setAttribute('role','status');
 box.append(element('p','小窗已聊满 5 次，去完整聊天继续吧。'));
 const button=element('button','到完整聊天继续 ↗');button.type='button';
 button.onclick=async()=>{button.disabled=true;try{const r=await fetch('/api/agent/conversations/'+encodeURIComponent(compactId)+'/activate',{method:'PUT'});if(!r.ok)throw Error('打开会话失败，请重试');window.dispatchEvent(new Event('agent-history-updated'));$('nav-assistant').click();}catch(e){button.textContent=e.message;button.disabled=false;}};
 box.append(button);$('conversation').append(box);$('question').placeholder='请到完整聊天继续';
}
$('ask-form').onsubmit=e=>{e.preventDefault();const q=$('question').value.trim();if(!q||agentBusy)return;answer(q);$('question').value='';};
document.querySelectorAll('.quick-questions button').forEach(b=>b.onclick=()=>answer(b.textContent));

let assistantReturnFocus;
async function setAssistant(open){
 if(open){await ZhiqingAuth.ready;if(!ZhiqingAuth.user){ZhiqingAuth.open();return;}if(document.body.classList.contains('chat-view-active'))return;}

 const panel=$('assistant');if(open&&panel.hidden)assistantReturnFocus=document.activeElement;
 panel.hidden=!open;document.querySelectorAll('.assistant-toggle').forEach(b=>b.setAttribute('aria-expanded',String(open)));
 if(open){positionAssistant();if(!agentBusy)loadPanel().then(()=>{if(!panel.hidden)$('question').focus({preventScroll:true});});}else{assistantReturnFocus?.focus({preventScroll:true});}
}
document.querySelectorAll('.assistant-toggle').forEach(b=>b.onclick=e=>{if(b.id==='assistant-bubble'&&suppressBubbleClick){e.preventDefault();return;}setAssistant($('assistant').hidden);});
$('close-assistant').onclick=()=>setAssistant(false);
document.addEventListener('keydown',e=>{if(e.key==='Escape'&&!$('assistant').hidden)setAssistant(false)});

function savedCityKey(){return 'weathermind.cities.'+(ZhiqingAuth.user?.account||'guest');}
ZhiqingAuth.ready.then(()=>renderSavedCities());
function loadSavedCities(){try{const data=JSON.parse(localStorage.getItem(savedCityKey())||'[]');return Array.isArray(data)?data.filter(c=>c&&typeof c.name==='string'&&Number.isFinite(c.latitude)&&Number.isFinite(c.longitude)&&Math.abs(c.latitude)<=90&&Math.abs(c.longitude)<=180).slice(0,12):[];}catch{return [];}}
function sameCity(a,b){return a&&b&&a.latitude===b.latitude&&a.longitude===b.longitude;}
function toggleSaved(open){$('saved-cities').hidden=!open;$('city-toggle').setAttribute('aria-expanded',String(open));if(open){renderSavedCities();$('saved-status').textContent='';}}
function persistSaved(cities){try{localStorage.setItem(savedCityKey(),JSON.stringify(cities));return true;}catch{$('saved-status').textContent='浏览器未允许保存，请检查隐私或存储设置。';return false;}}
function renderSavedCities(){
 const list=$('saved-list');list.replaceChildren();const cities=loadSavedCities();
 if(!cities.length)list.append(element('p','还没有常用城市，添加一个吧。','saved-empty'));
 cities.forEach(city=>{const row=element('div','','saved-row');const select=element('button',city.name,'saved-select');select.type='button';select.classList.toggle('selected',sameCity(city,currentCity));select.append(element('small',[city.admin1,city.country].filter(Boolean).join(' · ')));select.onclick=()=>{toggleSaved(false);choose(city);};const remove=element('button','×','saved-remove');remove.type='button';remove.setAttribute('aria-label','删除'+city.name);remove.title='删除'+city.name;remove.onclick=()=>{if(persistSaved(loadSavedCities().filter(c=>!sameCity(c,city)))){renderSavedCities();$('saved-status').textContent='已删除 '+city.name;}};row.append(select,remove);list.append(row);});
 const saved=cities.some(c=>sameCity(c,currentCity));$('save-current').disabled=!currentCity||saved||cities.length>=12;$('save-current').textContent=saved?'已添加当前城市':cities.length>=12?'最多添加12个城市':'＋ 添加当前城市';
}
$('save-current').onclick=()=>{if(!currentCity)return;const cities=loadSavedCities();if(cities.length>=12||cities.some(c=>sameCity(c,currentCity)))return;if(persistSaved([...cities,currentCity])){renderSavedCities();$('saved-status').textContent='已添加 '+currentCity.name;}};
document.addEventListener('click',e=>{if(!$('saved-cities').hidden&&!$('saved-cities').contains(e.target)&&!$('city-toggle').contains(e.target))toggleSaved(false);});
document.addEventListener('keydown',e=>{if(e.key==='Escape'&&!$('saved-cities').hidden){toggleSaved(false);$('city-toggle').focus();}});
window.addEventListener('storage',e=>{if(e.key===savedCityKey())renderSavedCities();});

let suppressBubbleClick=false, bubblePoint=null, bubbleDrag=null;
const bubble=$('assistant-bubble');
function placeBubble(x,y){
 const size=bubble.offsetWidth;const maxX=Math.max(8,innerWidth-size-8),maxY=Math.max(8,innerHeight-size-8);
 bubblePoint={x:Math.max(8,Math.min(x,maxX)),y:Math.max(8,Math.min(y,maxY))};
 Object.assign(bubble.style,{left:bubblePoint.x+'px',top:bubblePoint.y+'px',right:'auto',bottom:'auto'});positionAssistant();
}
function positionAssistant(){
 const r=bubble.getBoundingClientRect(),panel=$('assistant');
 for(const item of [panel]){
 const width=Math.min(parseFloat(getComputedStyle(panel).getPropertyValue('--compact-width'))||380,innerWidth-24);item.style.width=width+'px';
 const left=Math.max(12,Math.min(r.right-width,innerWidth-width-12));item.style.left=left+'px';item.style.right='auto';
 const spaceAbove=r.top-20,spaceBelow=innerHeight-r.bottom-20;
 if(spaceAbove>=spaceBelow){item.style.top='auto';item.style.bottom=(innerHeight-r.top+12)+'px';item.style.maxHeight=Math.max(100,spaceAbove)+'px';}
 else{item.style.bottom='auto';item.style.top=(r.bottom+12)+'px';item.style.maxHeight=Math.max(100,spaceBelow)+'px';}
 }
}
bubble.addEventListener('pointerdown',e=>{
 if(e.button!==0)return;const r=bubble.getBoundingClientRect();bubbleDrag={id:e.pointerId,startX:e.clientX,startY:e.clientY,x:r.left,y:r.top,moved:false};bubble.setPointerCapture(e.pointerId);
});
bubble.addEventListener('pointermove',e=>{
 if(!bubbleDrag||bubbleDrag.id!==e.pointerId)return;
 const dx=e.clientX-bubbleDrag.startX,dy=e.clientY-bubbleDrag.startY;
 if(Math.hypot(dx,dy)>6)bubbleDrag.moved=true;
 if(bubbleDrag.moved){bubble.classList.add('dragging');placeBubble(bubbleDrag.x+dx,bubbleDrag.y+dy);}
});
function endBubbleDrag(e){
 if(!bubbleDrag||bubbleDrag.id!==e.pointerId)return;const moved=bubbleDrag.moved;bubbleDrag=null;bubble.classList.remove('dragging');
 if(moved){suppressBubbleClick=true;setTimeout(()=>{suppressBubbleClick=false;},300);if(bubblePoint)try{localStorage.setItem('weathermind.assistant-position',JSON.stringify(bubblePoint));}catch{}}
}
bubble.addEventListener('pointerup',endBubbleDrag);bubble.addEventListener('pointercancel',endBubbleDrag);
bubble.addEventListener('keydown',e=>{
 const moves={ArrowLeft:[-24,0],ArrowRight:[24,0],ArrowUp:[0,-24],ArrowDown:[0,24]};if(!moves[e.key])return;e.preventDefault();const r=bubble.getBoundingClientRect();placeBubble(r.left+moves[e.key][0],r.top+moves[e.key][1]);try{localStorage.setItem('weathermind.assistant-position',JSON.stringify(bubblePoint));}catch{}
});
bubble.title='知晴生活助手 · 拖动可移动';bubble.setAttribute('aria-label','知晴生活助手，点击打开，方向键移动');
try{const pos=JSON.parse(localStorage.getItem('weathermind.assistant-position'));if(pos&&Number.isFinite(pos.x)&&Number.isFinite(pos.y))placeBubble(pos.x,pos.y);}catch{}
positionAssistant();window.addEventListener('resize',()=>{if(bubblePoint)placeBubble(bubblePoint.x,bubblePoint.y);else positionAssistant();});


// Presentation helpers preserve missing values and the API's hourly order.
function rainReading(value){
 const group=element('span','','rain-reading');group.setAttribute('aria-label','降水概率 '+show(value)+'%');
 const track=element('span','','rain-track');track.setAttribute('aria-hidden','true');
 if(Number.isFinite(value)){const fill=element('span','','rain-fill');fill.style.width=Math.max(0,Math.min(100,value))+'%';track.append(fill);}
 group.title='降水概率：短条表示概率大小，不代表降水量。';group.append(track,element('span','降水概率','rain-caption'),element('span',show(value)+'%'));return group;
}
function hourlyRow(h,index,rows){
 const row=element('div','','hour'+(index===0?' next-hour':''));const time=element('span','','hour-time');
 if(typeof h.time==='string'){time.append(element('span',h.time.slice(11,16)));if(index===0||h.time.slice(0,10)!==rows[index-1]?.time?.slice(0,10))time.append(element('small',h.time.slice(5,10)));time.title=h.time.replace('T',' ')+' · 城市当地时间';}else time.textContent='时间缺失';
 row.append(time,weatherIcon(h),element('strong',temp(h.temperature)+'°'),rainReading(h.precipitation_probability));return row;
}

function hourPeriod(h){
 if(typeof h?.time!=='string')return '时段未知';const hour=Number(h.time.slice(11,13));
 return h.time.slice(5,10)+' · '+(hour<6?'深夜':hour<12?'上午':hour<18?'下午':'晚上');
}

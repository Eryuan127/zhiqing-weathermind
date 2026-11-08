/* Display-only context. No coordinates, storage, extra weather calls or LLM calls. */
(()=>{
 'use strict';
 const by=id=>document.getElementById(id),finite=Number.isFinite;
 const number=value=>finite(value)?value.toFixed(1):'—';
 const embedded=document.body.classList.contains('embedded-chat');
 function snapshot(city,weather){
  if(!city||!weather?.current||!finite(weather.current.temperature))return null;
  const c=weather.current,rows=(weather.hourly||[]).filter(h=>typeof h.time==='string'&&h.time>=c.time);
  const upcoming=rows.slice(0,24),rain=upcoming.filter(h=>finite(h.precipitation_probability));
  const rainy=rain.find(h=>h.precipitation_probability>=50),peak=rain.length?Math.max(...rain.map(h=>h.precipitation_probability)):null;
  const when=h=>{const date=h.time.slice(0,10),today=c.time?.slice(0,10);return (date===today?'今天 ':date.slice(5)+' ')+h.time.slice(11,16);};
  const rainText=rainy?`${when(rainy)}起降水概率达到 ${rainy.precipitation_probability}%，未来 24 小时最高 ${peak}%，出门记得带伞。`:peak!==null?`未来 24 小时最高降水概率 ${peak}%，出行前留意最新预报。`:'逐小时降水数据暂缺，出行前请确认最新预报。';
  const wind=finite(c.wind_speed)&&c.wind_speed>=25?`当前风速 ${c.wind_speed} km/h，户外活动请留意风力。`:finite(c.feels_like)?`当前体感 ${number(c.feels_like)}°C。`:'';
  const hour=Number(c.time?.slice(11,13)),salutation=!finite(hour)?'你好':hour<6?'夜深了':hour<11?'早上好':hour<14?'中午好':hour<18?'下午好':'晚上好';
  return Object.freeze({city:city.name,temperature:number(c.temperature),description:c.description||'天气描述缺失',code:c.code,is_day:c.is_day,precipitation:upcoming[0]?.precipitation_probability,updated:c.time?.slice(11,16)||'时间未知',timezone:weather.timezone||'时区未知',shortSummary:rainy?`${when(rainy)}起降水概率 ${rainy.precipitation_probability}%`:peak!==null?`未来 24 小时最高降水概率 ${peak}%`:'降水数据暂缺',summary:rainText,brief:rainText+' '+wind,salutation,evidence:rain.length?`Open-Meteo 逐小时预报 · ${weather.timezone||'时区未知'}。依据 ${when(rain[0])} 至 ${when(rain[rain.length-1])} 的 ${rain.length} 个有效降水概率数据点，按 ≥50% 标示提醒起点。概率不代表一定下雨。`:'Open-Meteo · 缺少有效逐小时降水数据，暂不判断降水趋势。'});
 }
 function capsule(node,data){
  if(!node)return;node.hidden=!data;node.replaceChildren();if(!data)return;
  const mark=document.createElement('span');mark.className='capsule-pin';mark.setAttribute('aria-hidden','true');mark.innerHTML='<svg viewBox="0 0 24 24"><path d="M19 10c0 5-7 11-7 11S5 15 5 10a7 7 0 0 1 14 0Z"/><circle cx="12" cy="10" r="2"/></svg>';
  const main=document.createElement('strong');main.textContent=`${data.city} · ${data.temperature}°C ${data.description}`;
  const rain=document.createElement('span');rain.className='capsule-rain';rain.textContent=`降水 ${finite(data.precipitation)?data.precipitation:'—'}%`;
  const time=document.createElement('small');time.textContent=data.updated+' 更新';
  node.append(mark,main,rain,time);if(node.id==='welcome-weather'){time.textContent=data.shortSummary;time.className='welcome-weather-summary';}
 }
 if(embedded){
  const parentWindow=window.parent;
  function paint(){
   // This is a same-origin iframe; its context is ephemeral and has no private coordinates.
   let data=null;try{data=parentWindow.WeatherContextUI?.get();}catch{}
   capsule(by('welcome-weather'),data);const card=by('sidebar-weather');card.hidden=!data;if(!data)return;
   card.querySelector('[data-context=city]').textContent=data.city+' · '+data.description;
   card.querySelector('[data-context=temperature]').textContent=data.temperature+'°C';
   card.querySelector('[data-context=summary]').textContent=data.summary;
   const icon=card.querySelector('[data-context=icon]');icon.replaceChildren();if(parentWindow.WeatherVisual)icon.append(parentWindow.WeatherVisual.icon(data));
   const h=by('welcome').querySelector('h1');if(!h.dataset.original)h.dataset.original=h.textContent;
   h.textContent=h.dataset.original.replace(/^你好/,data.salutation);
  }
  by('sidebar-back').onclick=()=>{try{parentWindow.document.querySelector('#back-weather').click();}catch{location.href='/';}};
  try{parentWindow.addEventListener('weather-display-updated',paint);window.addEventListener('pagehide',()=>parentWindow.removeEventListener('weather-display-updated',paint),{once:true});}catch{}
  paint();return;
 }
 let context=null;
 window.WeatherContextUI={get:()=>context,greeting:()=>context?`${context.salutation}，我是知晴。现在${context.city} ${context.temperature}°C，${context.description}。${context.brief} 可以继续问我天气或活动安排。`:'hi，我是知晴。当前天气暂不可用，可以告诉我城市，再问问天气或活动安排。'};
 function paint(){
  context=snapshot(currentCity,weatherData);
  const ready=context&&document.querySelector('.current')?.dataset.state==='ready';
  by('forecast-brief').hidden=!ready;if(ready){by('brief-text').textContent=context.brief;by('brief-evidence').textContent=context.evidence;}
  capsule(by('compact-weather'),ready?context:null);
  by('compact-context-status').textContent=ready?'已读取当前页面天气':'天气数据暂不可用';
  by('compact-source').textContent='预报摘要基于 Open-Meteo 数据 · 不额外调用 AI';
  by('expand-hours').hidden=by('hourly-expansion').hidden;
  window.dispatchEvent(new Event('weather-display-updated'));
 }
 window.addEventListener('weather-rendered',paint);window.addEventListener('weather-city-renamed',paint);
 // Hide stale context while a city request is loading or has failed.
 new MutationObserver(()=>{const ready=document.querySelector('.current').dataset.state==='ready';if(!ready){context=null;by('forecast-brief').hidden=true;capsule(by('compact-weather'),null);by('compact-context-status').textContent='等待当前天气数据';window.dispatchEvent(new Event('weather-display-updated'));}}).observe(document.querySelector('.current'),{attributes:true,attributeFilter:['data-state']});
 by('brief-evidence-toggle').onclick=()=>{const open=by('brief-evidence').hidden;by('brief-evidence').hidden=!open;by('brief-evidence-toggle').setAttribute('aria-expanded',String(open));};
 const expansion=by('hourly-expansion'),expandButton=by('expand-hours');
 function reflectHours(){document.querySelector('.middle-surface').classList.toggle('hours-expanded',expansion.open);expandButton.setAttribute('aria-expanded',String(expansion.open));expandButton.textContent=expansion.open?'收起逐小时详情':'展开未来 24 小时';}
 expandButton.onclick=()=>{const scroll=by('hourly-scroll');expansion.open=!expansion.open;reflectHours();if(!expansion.open){scroll.scrollTop=0;requestAnimationFrame(()=>{if(scroll.getBoundingClientRect().bottom<0)scroll.scrollIntoView({block:'center',behavior:'instant'});});}};expansion.addEventListener('toggle',reflectHours);
 by('ask-week').onclick=async()=>{
  await ZhiqingAuth.ready;if(!ZhiqingAuth.user){ZhiqingAuth.open('assistant');return;}
  by('nav-assistant').click();const frame=by('chat-frame');
  function send(){const doc=frame.contentDocument,input=doc?.querySelector('#message');if(!input)return false;input.value='这周哪天适合出游？请比较未来七天的天气。';input.dispatchEvent(new Event('input',{bubbles:true}));input.focus();return true;}
  if(!send())frame.addEventListener('load',send,{once:true});
 };
 by('expand-conversation').onclick=async()=>{
  const button=by('expand-conversation');button.disabled=true;
  try{if(compactId&&compactTurns>0){const response=await fetch('/api/agent/conversations/'+encodeURIComponent(compactId)+'/activate',{method:'PUT'});if(!response.ok)throw Error('打开完整对话失败，请重试');window.dispatchEvent(new Event('agent-history-updated'));}by('nav-assistant').click();}
  catch(error){button.textContent=error.message;}finally{button.disabled=false;}
 };
 if(typeof weatherData!=='undefined')paint();
})();

/* Decorative front-end visuals only; no requests, keys, or model behavior. */
(()=>{
 'use strict';
 const by=id=>document.getElementById(id);
 const reduced=matchMedia('(prefers-reduced-motion: reduce)'),mobile=matchMedia('(max-width: 720px)');
 const ns='http://www.w3.org/2000/svg';
 const svgNode=(name,attrs={})=>{const node=document.createElementNS(ns,name);for(const [key,value] of Object.entries(attrs))node.setAttribute(key,String(value));return node;};
 const bounded=(n,a,b)=>Math.max(a,Math.min(b,n));
 function icon(weather){
  const node=document.createElement('span');node.className='weather-icon';node.setAttribute('role','img');node.setAttribute('aria-label',weather.description||'天气数据缺失');
  const code=weather.code;if(!Number.isFinite(code)){node.textContent='—';return node;}
  const cloud='<path class="flat-cloud" d="M14 43h32a10 10 0 0 0 0-20 15 15 0 0 0-29-3 12 12 0 0 0-3 23Z"/><path class="flat-cloud-light" d="M15 39h29a7 7 0 0 0 0-14 12 12 0 0 0-24-2 9 9 0 0 0-5 16Z"/>';
  const sun='<circle class="flat-sun" cx="30" cy="27" r="11"/><path class="flat-ray" fill="none" d="M30 8V4M30 50v-4M11 27H7M53 27h-4M16 13l-3-3M44 41l3 3M44 13l3-3M16 41l-3 3"/>';
  const moon='<path class="flat-moon" d="M39 7a23 23 0 1 0 16 32A24 24 0 0 1 39 7Z"/>';
  const rain=[51,53,55,56,57,61,63,65,66,67,80,81,82].includes(code),snow=[71,73,75,77,85,86].includes(code),thunder=[95,96,99].includes(code);
  let shapes=code===0?(weather.is_day===0?moon:sun):code===1||code===2?'<g transform="translate(13,-3) scale(.72)">'+(weather.is_day===0?moon:sun)+'</g>'+cloud:cloud;
  if(rain){if(code<60)shapes+='<circle class="flat-rain" cx="18" cy="50" r="2.5"/><circle class="flat-rain" cx="32" cy="55" r="2.5"/><circle class="flat-rain" cx="46" cy="50" r="2.5"/>';else shapes+='<path class="flat-rain" d="M20 45c0 0-7 8-7 11a4 4 0 0 0 8 0c0-3-1-11-1-11Zm15 2s-7 8-7 11a4 4 0 0 0 8 0c0-3-1-11-1-11Zm15-2s-7 8-7 11a4 4 0 0 0 8 0c0-3-1-11-1-11Z"/>';}
  if(snow)shapes+='<path class="flat-snow" fill="none" d="M20 47v13m-5-10 10 7m0-7-10 7M43 47v13m-5-10 10 7m0-7-10 7"/>';
  if(thunder)shapes+='<path class="flat-sun" d="m33 33-11 16h11l-5 13 19-21H35l4-8Z"/>';
  if(code===45||code===48)shapes+='<path class="flat-fog" fill="none" d="M10 47h44M16 55h32"/>';
  node.innerHTML='<svg viewBox="0 0 64 64" aria-hidden="true">'+shapes+'</svg>';return node;
 }
 // NOAA fractional-year approximation. Estimates only; no terrain/elevation correction.
 // https://www.gml.noaa.gov/grad/solcalc/solareqns.PDF
 function solar(city,timezone,now=new Date()){
  if(!Number.isFinite(city?.latitude)||!Number.isFinite(city?.longitude)||Math.abs(city.latitude)>90||Math.abs(city.longitude)>180||!timezone)return null;
  try{
   const format=new Intl.DateTimeFormat('en-CA',{timeZone:timezone,year:'numeric',month:'2-digit',day:'2-digit'});
   const parts=Object.fromEntries(format.formatToParts(now).map(p=>[p.type,p.value]));
   const year=Number(parts.year),month=Number(parts.month),day=Number(parts.day),base=Date.UTC(year,month-1,day);
   const ordinal=Math.floor((base-Date.UTC(year,0,1))/86400000)+1,days=(Date.UTC(year+1,0,1)-Date.UTC(year,0,1))/86400000;
   const g=2*Math.PI/days*(ordinal-1),rad=Math.PI/180;
   const eq=229.18*(.000075+.001868*Math.cos(g)-.032077*Math.sin(g)-.014615*Math.cos(2*g)-.040849*Math.sin(2*g));
   const decl=.006918-.399912*Math.cos(g)+.070257*Math.sin(g)-.006758*Math.cos(2*g)+.000907*Math.sin(2*g)-.002697*Math.cos(3*g)+.00148*Math.sin(3*g);
   const lat=city.latitude*rad,cos=Math.cos(90.833*rad)/(Math.cos(lat)*Math.cos(decl))-Math.tan(lat)*Math.tan(decl);
   if(cos>1||cos< -1)return {polar:true,day:cos< -1};
   const angle=Math.acos(cos)/rad,noon=720-4*city.longitude-eq;
   const rise=new Date(base+(noon-4*angle)*60000),set=new Date(base+(noon+4*angle)*60000);
   const timeFormat=new Intl.DateTimeFormat('zh-CN',{timeZone:timezone,hour:'2-digit',minute:'2-digit',hourCycle:'h23'});
   return {rise,set,riseLabel:timeFormat.format(rise),setLabel:timeFormat.format(set),progress:bounded((now-rise)/(set-rise),0,1),day:now>=rise&&now<=set};
  }catch{return null;}
 }
 function drawSolar(info){
  const container=by('solar-arc');container.replaceChildren();container.hidden=!info;if(!info)return;
  const svg=svgNode('svg',{viewBox:'0 0 320 80',role:'img'}),title=svgNode('title');
  title.textContent='太阳轨迹为时间比例示意，日出日落按经纬度估算，未考虑地形、海拔和实际折射变化。';svg.append(title);
  svg.append(svgNode('path',{d:'M16 53Q160 -30 304 53',class:'solar-track'}),svgNode('path',{d:'M16 53H304',class:'solar-horizon'}));
  if(info.polar){const text=svgNode('text',{x:160,y:70,'text-anchor':'middle'});text.textContent=info.day?'极昼 · 日出日落估算':'极夜 · 日出日落估算';svg.append(text);}
  else{
   const t=info.progress,x=16+288*t,y=53-166*t*(1-t);
   const marker=svgNode('circle',{cx:x,cy:y,r:6,class:'solar-sun'+(info.day?'':' solar-night')});svg.append(marker);
   for(const [xPos,anchor,label] of [[16,'start','日出约 '+info.riseLabel],[304,'end','日落约 '+info.setLabel]]){const text=svgNode('text',{x:xPos,y:75,'text-anchor':anchor});text.textContent=label;svg.append(text);}
   svg.setAttribute('aria-label',`日出约 ${info.riseLabel}，日落约 ${info.setLabel}，太阳位置为当前时间比例示意`);
   container.dataset.progress=t.toFixed(4);
  }
  container.append(svg);
 }
 function roll(el){
  if(!el)return;const text=el.textContent;if(!/\d/.test(text)){el.removeAttribute('aria-label');return;}
  el.getAnimations({subtree:true}).forEach(a=>a.cancel());
  if(reduced.matches||!el.isConnected)return;
  el.setAttribute('aria-label',text);const fragment=document.createDocumentFragment();let index=0;
  for(const char of text){if(/\d/.test(char)){const outer=document.createElement('span'),digit=document.createElement('span');outer.className='digit-window';outer.setAttribute('aria-hidden','true');digit.className='rolling-digit';digit.textContent=char;outer.append(digit);fragment.append(outer);digit.animate([{transform:'translateY(100%)',opacity:.25},{transform:'translateY(0)',opacity:1}],{duration:220,delay:Math.min(index++*8,24),easing:'cubic-bezier(.22,1,.36,1)',fill:'backwards'});}else fragment.append(document.createTextNode(char));}
  el.replaceChildren(fragment);
 }
 function metric(container,name,value,unit){
  const icons={
   '体感温度':'<path d="M10 14V5a3 3 0 0 1 6 0v9a5 5 0 1 1-6 0Z"/><path d="M13 8v10"/>',
   '相对湿度':'<path d="M12 3S5 11 5 15a7 7 0 0 0 14 0c0-4-7-12-7-12Z"/><path d="M9 17a3 3 0 0 0 3 2"/>',
   '风速':'<path d="M3 8h12a3 3 0 1 0-3-3M3 12h16a3 3 0 1 1-3 3M3 16h5a3 3 0 1 1-3 3"/>',
   '降水概率':'<path d="M5 13a5 5 0 0 1 0-10 7 7 0 0 1 13 2 4 4 0 0 1 1 8H5Z"/><path d="m7 17-2 3m8-3-2 3m8-3-2 3"/>'
  };
  const mark=document.createElement('span');mark.className='metric-symbol';mark.setAttribute('aria-hidden','true');mark.innerHTML='<svg viewBox="0 0 24 24">'+icons[name]+'</svg>';container.prepend(mark);
  const visual=document.createElement('div');visual.className='metric-visual';visual.setAttribute('aria-hidden','true');
  if(Number.isFinite(value)){
   if(unit==='%'){
    const svg=svgNode('svg',{viewBox:'0 0 44 44'});svg.append(svgNode('circle',{cx:22,cy:22,r:17,class:'metric-ring-track'}),svgNode('circle',{cx:22,cy:22,r:17,class:'metric-ring-value',pathLength:100,'stroke-dasharray':`${bounded(value,0,100)} 100`,transform:'rotate(-90 22 22)'}));visual.append(svg);
   }else{
    // No arbitrary percentage for temperature/wind: this is a decorative unit glyph.
    visual.classList.add('metric-glyph');visual.innerHTML='<svg viewBox="0 0 24 24">'+icons[name]+'</svg>';
   }
  }
  container.append(visual);
 }
 function gauge(value){
  const svg=by('aq-gauge');svg.replaceChildren();if(!Number.isFinite(value)){svg.parentElement.removeAttribute('role');svg.parentElement.removeAttribute('aria-label');svg.parentElement.removeAttribute('title');roll(by('air-value'));return;}
  const point=amount=>{const a=(135+amount/500*270)*Math.PI/180;return [60+44*Math.cos(a),48+44*Math.sin(a)];};
  const stops=[0,50,100,150,200,300,500],colors=['green','yellow','orange','red','purple','maroon'];
  for(let i=0;i<colors.length;i++){const from=point(stops[i]+1),to=point(stops[i+1]-1);svg.append(svgNode('path',{d:`M${from} A44 44 0 0 1 ${to}`,class:'aq-segment',stroke:`var(--aq-${colors[i]})`,opacity:.68}));}
  const [x,y]=point(bounded(value,0,500));svg.append(svgNode('circle',{cx:x,cy:y,r:4.5,class:'aq-marker'}));
  for(const [x,anchor,text] of [[25,'middle','0'],[95,'middle','500']]){const label=svgNode('text',{x,y:95,'text-anchor':anchor,class:'aq-scale'});label.textContent=text;svg.append(label);}
  svg.parentElement.setAttribute('role','img');svg.parentElement.setAttribute('aria-label',`US AQI ${value}，彩色量程 0 至 500`);
  svg.parentElement.title=`US AQI ${value} · 量程 0–500；绿、黄、橙、红、紫、深红对应 US AQI 等级`;
  roll(by('air-value'));
 }
 const canvas=by('weather-atmosphere'),card=document.querySelector('.current'),context=canvas.getContext('2d');
 let frame=0,last=0,width=0,height=0,visible=true,sky='cloudy',nodes=[],weather=null,city=null,solarInfo=null;
 const random=i=>{const x=Math.sin(i*127.1+311.7)*43758.5453;return x-Math.floor(x);};
 function makeNodes(){const count=sky==='rainy'?64:sky==='cloudy'?5:sky==='snowy'?32:0;nodes=Array.from({length:count},(_,i)=>({x:random(i),y:random(i+100),size:.4+random(i+200),speed:.5+random(i+300)}));canvas.dataset.particleCount=String(count);}
 function stop(){cancelAnimationFrame(frame);frame=0;last=0;}
 function active(){return context&&!reduced.matches&&!mobile.matches&&visible&&!document.hidden&&card.dataset.state==='ready'&&nodes.length>0;}
 function tick(time){
  frame=0;if(!active())return;
  const dt=last?Math.min((time-last)/1000,.05):0;last=time;context.clearRect(0,0,width,height);
  const css=getComputedStyle(card);context.strokeStyle=css.getPropertyValue('--weather-rain');context.lineCap='round';
  for(const node of nodes){
   if(sky==='cloudy'){
    node.x=(node.x+dt*.008*node.speed)%1.5;const x=width*.62+node.x*width*.7,y=height*.15+node.y*height*.34;
    // Soft cloud banks stay on the right, away from the primary reading.
    context.save();context.translate(x,y);context.scale(node.size,node.size);
    const glow=context.createRadialGradient(0,0,6,0,0,90);glow.addColorStop(0,'rgba(255,255,255,.48)');glow.addColorStop(1,'rgba(255,255,255,0)');context.fillStyle=glow;context.fillRect(-100,-65,200,130);
    context.fillStyle='rgba(255,255,255,.25)';context.beginPath();context.moveTo(-65,14);context.bezierCurveTo(-85,-6,-55,-35,-32,-23);context.bezierCurveTo(-22,-61,32,-61,40,-25);context.bezierCurveTo(73,-33,95,7,65,20);context.bezierCurveTo(35,33,-38,32,-65,14);context.fill();context.restore();
   }else{
    node.y=(node.y+dt*(sky==='rainy'?.38:.06)*node.speed)%1;const x=node.x*width,y=node.y*height;
    if(sky==='rainy'){context.globalAlpha=.18;context.lineWidth=1.2;context.beginPath();context.moveTo(x,y);context.lineTo(x-3,y+10*node.size);context.stroke();}
    else{context.fillStyle='rgba(255,255,255,.55)';context.beginPath();context.arc(x,y,2*node.size,0,Math.PI*2);context.fill();}
   }
  }
  context.globalAlpha=1;frame=requestAnimationFrame(tick);
 }
 function refresh(){stop();context?.clearRect(0,0,width,height);canvas.hidden=mobile.matches||reduced.matches||!context;canvas.dataset.animating=String(Boolean(active()));canvas.dataset.pausedReason=reduced.matches?'reduced-motion':mobile.matches?'mobile':!visible?'offscreen':document.hidden?'hidden':card.dataset.state!=='ready'?'data-state':nodes.length===0?'static-weather':'none';if(active())frame=requestAnimationFrame(tick);}
 function resize(){const rect=card.getBoundingClientRect(),dpr=Math.min(devicePixelRatio||1,1.5);width=rect.width;height=rect.height;canvas.width=Math.round(width*dpr);canvas.height=Math.round(height*dpr);context?.setTransform(dpr,0,0,dpr,0,0);refresh();}
 function update(data){
  if(!data?.weather||!data?.city)return;weather=data.weather;city=data.city;const current=weather.current||{},code=current.code;solarInfo=solar(city,weather.timezone);
  const night=solarInfo?!solarInfo.day:current.is_day===0;
  sky=[51,53,55,56,57,61,63,65,66,67,80,81,82,95,96,99].includes(code)?'rainy':[71,73,75,77,85,86].includes(code)?'snowy':code===0||code===1?'sunny':'cloudy';
  card.dataset.sky=sky;card.dataset.phase=night?'night':'day';
  by('weather-summary').textContent=current.description?`${night?'今夜':'此刻'}${current.description}，${sky==='rainy'?'出门记得带伞':sky==='snowy'?'出行注意保暖':sky==='cloudy'?'云影轻轻掠过':night?'月色相伴':'阳光相伴'}`:'当前天气';
  drawSolar(solarInfo);makeNodes();resize();
  document.querySelectorAll('#temperature,#highlow,.metric-number,.day>strong').forEach(roll);
 }
 new ResizeObserver(resize).observe(card);
 new IntersectionObserver(entries=>{visible=entries[entries.length-1].isIntersecting;refresh();}).observe(card);
 new MutationObserver(refresh).observe(card,{attributes:true,attributeFilter:['data-state']});
 reduced.addEventListener('change',()=>{refresh();if(reduced.matches)document.getAnimations().forEach(a=>a.cancel());});mobile.addEventListener('change',refresh);document.addEventListener('visibilitychange',refresh);
 // Recompute the local-time sun marker without requesting or fabricating weather.
 setInterval(()=>{if(weather&&city&&!document.hidden){solarInfo=solar(city,weather.timezone);drawSolar(solarInfo);if(solarInfo)card.dataset.phase=solarInfo.day?'day':'night';}},60000);
 window.WeatherVisual={icon,solar,gauge,roll,metric};window.addEventListener('weather-rendered',e=>update(e.detail));
})();

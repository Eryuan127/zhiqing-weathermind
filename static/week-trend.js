/* Seven-day display only. Missing values break paths; no interpolation of data. */
(()=>{
 const root=document.getElementById('daily'),ns='http://www.w3.org/2000/svg';let days=[];
 const node=(tag,attrs)=>{const e=document.createElementNS(ns,tag);for(const [k,v] of Object.entries(attrs||{}))e.setAttribute(k,v);return e;};
 function draw(){
  root.querySelector('.week-temperature-chart')?.remove();
  if(!days.length)return;
  const width=root.getBoundingClientRect().width,height=150;
  const values=days.flatMap(d=>[d.temperature_min,d.temperature_max]).filter(Number.isFinite);
  if(!values.length)return;
  const lo=Math.min(...values)-3,hi=Math.max(...values)+3;
  const y=v=>20+(hi-v)/(hi-lo)*105;
  const cards=[...root.querySelectorAll('.day')],base=root.getBoundingClientRect();
  const x=i=>cards[i].getBoundingClientRect().left-base.left+cards[i].getBoundingClientRect().width/2;
  const svg=node('svg',{viewBox:`0 0 ${width} ${height}`,class:'week-temperature-chart',role:'img','aria-label':'未来七天最高温为蓝线，最低温为浅蓝线；数值来自天气预报，缺失数据处断开'});
  const defs=node('defs'),gradient=node('linearGradient',{id:'week-temperature-fill',x1:0,y1:0,x2:0,y2:1});
  gradient.append(node('stop',{offset:'0%','stop-color':'#386bff','stop-opacity':'.10'}),node('stop',{offset:'100%','stop-color':'#386bff','stop-opacity':'.015'}));defs.append(gradient);svg.append(defs);
  // Shade only runs where both min and max exist.
  let run=[];function area(){if(run.length>1){const points=[...run.map(i=>[x(i),y(days[i].temperature_max)]),...run.slice().reverse().map(i=>[x(i),y(days[i].temperature_min)])];svg.append(node('path',{d:points.map((p,i)=>(i?'L':'M')+p.join(',')).join(' ')+'Z',fill:'url(#week-temperature-fill)'}));}run=[];}
  days.forEach((d,i)=>{if(Number.isFinite(d.temperature_min)&&Number.isFinite(d.temperature_max))run.push(i);else area();});area();
  for(const [key,cls,offset] of [['temperature_max','week-high',-11],['temperature_min','week-low',17]]){
   let path='',connected=false;
   days.forEach((d,i)=>{const v=d[key];if(!Number.isFinite(v)){connected=false;return;}path+=(connected?'L':'M')+x(i)+','+y(v)+' ';connected=true;});
   svg.append(node('path',{d:path,class:cls,fill:'none','stroke-width':2.2,'stroke-linejoin':'round','stroke-linecap':'round'}));
   days.forEach((d,i)=>{const v=d[key];if(!Number.isFinite(v))return;
    const circle=node('circle',{cx:x(i),cy:y(v),r:3.3,class:cls+' point','data-day':i,'data-field':key,'data-value':v});
    const title=node('title');title.textContent=`${d.time} ${key==='temperature_max'?'最高':'最低'} ${v}°C`;circle.append(title);svg.append(circle);
    const text=node('text',{x:x(i),y:y(v)+offset,'text-anchor':'middle',class:cls+' label'});text.textContent=Number(v.toFixed(1))+'°';svg.append(text);
   });
  }
  root.append(svg);
 }
 window.addEventListener('weather-rendered',e=>{days=e.detail.weather?.daily||[];root.style.gridTemplateColumns=`repeat(${Math.max(1,days.length)},minmax(115px,1fr))`;draw();});
 new ResizeObserver(draw).observe(root);
})();

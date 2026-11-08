try{localStorage.removeItem('weathermind.currentCity');}catch{}
window.WeatherMindLocation={data:null,owner:null};
WeatherMindLocation.ready=new Promise(resolve=>WeatherMindLocation.resolve=resolve);
window.WeatherMindAgent={
 render(container,text){
  for(const paragraph of text.split(/\n\s*\n/)){
   const block=document.createElement('div');block.className='agent-paragraph';
   for(const line of paragraph.split('\n')){
    const row=document.createElement('div');if(/^(?:\*\*)?(?:结论[：:]|推荐[时活]|关键天气依据[：:]|预测结果[：:])/.test(line))row.className=/结论/.test(line)?'answer-heading':'answer-fact';else if(/^(?:注意|提示|建议)[：:]/.test(line))row.className='answer-note';if(line.startsWith('- '))row.append(document.createTextNode('• '));
    const content=line.startsWith('- ')?line.slice(2):line;
    content.split(/(\*\*.*?\*\*)/g).forEach(part=>{if(part.startsWith('**')&&part.endsWith('**')){const strong=document.createElement('strong');strong.textContent=part.slice(2,-2);row.append(strong)}else row.append(document.createTextNode(part))});block.append(row);
   }container.append(block);
  }
 },
 loading(container){
  const dots=document.createElement('span');dots.className='loading-dots';dots.setAttribute('role','status');dots.setAttribute('aria-label','正在等待回复');
  for(let i=0;i<3;i++)dots.append(document.createElement('i'));container.replaceChildren(dots);
 },
 async type(container,text,onUpdate=()=>{},control={}){
  this.render(container,text);
  if(matchMedia('(prefers-reduced-motion: reduce)').matches){onUpdate();return}
  const walker=document.createTreeWalker(container,NodeFilter.SHOW_TEXT),entries=[];let node;
  while(node=walker.nextNode()){const chars=Array.from(node.textContent);entries.push({node,chars});node.textContent=''}
  const total=entries.reduce((sum,e)=>sum+e.chars.length,0);if(!total)return;
  const duration=Math.min(5500,Math.max(350,total*18));let start=null,shown=0;
  await new Promise(resolve=>{function tick(now){if(control.stopped){resolve();return;}if(start===null)start=now;const target=control.finish?total:Math.min(total,Math.floor((now-start)/duration*total));let remain=target;
   for(const entry of entries){const count=Math.min(entry.chars.length,remain);entry.node.textContent=entry.chars.slice(0,count).join('');remain-=count}
   if(target!==shown){shown=target;onUpdate()}
   if(target>=total)resolve();else requestAnimationFrame(tick)
  }requestAnimationFrame(tick)});
 },
 evidence(container,data){
  const label=document.createElement('p');label.className='execution-label';label.textContent='本次执行：'+(data.mode_label||'规则模式');
  if(data.mode?.startsWith('qwen')||data.execution?.requested_mode==='qwen'){
   let usage=data.execution?.token_usage;
   if(!usage){const logs=[data.execution?.qwen,data.execution?.explanation].filter(Boolean),totals=logs.map(log=>log.usage?.total_tokens),known=totals.filter(n=>Number.isSafeInteger(n)&&n>=0);usage={total_tokens:known.length?known.reduce((a,b)=>a+b,0):null,complete:logs.length>0&&known.length===logs.length};}
   const count=usage.total_tokens,known=Number.isSafeInteger(count)&&count>=0,badge=document.createElement('span');badge.className='token-usage';
   const description=known?`${usage.complete?'本轮输入与输出合计':'本轮已返回用量，部分调用用量未知'}：${count.toLocaleString('zh-CN')} tokens`:'模型服务未返回本轮 token 用量';badge.title=description;badge.setAttribute('aria-label',description);
   const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');svg.setAttribute('viewBox','0 0 24 24');svg.setAttribute('aria-hidden','true');
   const path=document.createElementNS('http://www.w3.org/2000/svg','path');path.setAttribute('d','M12 2C13.5 8.5 15.5 10.5 22 12C15.5 13.5 13.5 15.5 12 22C10.5 15.5 8.5 13.5 2 12C8.5 10.5 10.5 8.5 12 2Z');svg.append(path);badge.append(svg,document.createTextNode(known?(usage.complete?'':'≥ ')+count.toLocaleString('zh-CN'):'—'));label.append(badge);
  }
  container.append(label);if(!data.tools?.length&&!data.parsed_cities)return;const details=document.createElement('details'),summary=document.createElement('summary');summary.textContent='查看分析依据与真实工具记录';details.append(summary);
  const path=document.createElement('p');path.textContent='执行路径：'+data.path.join(' → ');details.append(path);
  const parsed=document.createElement('pre');parsed.textContent=JSON.stringify({最终解析城市:data.parsed_cities,城市来源:data.city_source,评估时间:data.time_window,服务诊断:data.service_diagnostics,请求执行记录:data.execution},null,2);details.append(parsed);
  for(const tool of (data.tools||[])){const pre=document.createElement('pre');pre.textContent=JSON.stringify(tool,null,2);details.append(pre)}container.append(details);
 },
 home(){try{const root=window.parent!==window?window.parent:window;const location=root.WeatherMindLocation,user=root.ZhiqingAuth?.user;if(!user||location?.owner!==user.account||!location.data||Date.now()/1000-location.data.obtained_at>=21600)return null;return {...location.data};}catch{return null}},
 async locationReady(){try{const root=window.parent!==window?window.parent:window;await root.WeatherMindLocation?.ready;}catch{}},

 async ask(message,home_city,options={}){if(options.signal){await new Promise((resolve,reject)=>{const signal=options.signal,abort=()=>reject(new DOMException('Stopped','AbortError'));if(signal.aborted){abort();return;}signal.addEventListener('abort',abort,{once:true});this.locationReady().then(()=>{signal.removeEventListener('abort',abort);resolve();},reject);});}else await this.locationReady();home_city=this.home();const response=await fetch('/api/agent/chat',{signal:options.signal,method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({message,home_city,client_request_id:options.requestId,mode:document.querySelector('#execution-mode')?.value||'rules'})});const data=await response.json();if(!response.ok)throw Error(data.error||'请求失败');return data}
};

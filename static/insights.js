(()=>{
 const by=id=>document.getElementById(id);let selected=null,airSequence=0,modelSequence=0,pollutantController=null,pollutantRetry=null;
 const state=(selector,value,message,retry)=>WeatherUI.state(document.querySelector(selector),value,message,retry);
 const localTime=value=>typeof value==='string'?value.replace('T',' ').slice(0,16):'未知';
 async function json(url){const r=await fetch(url);const data=await r.json();if(!r.ok)throw Error(data.error||'暂时无法查询，请重试');return data;}
 function grade(value){if(value<=50)return ['良好','good'];if(value<=100)return ['中等','moderate'];if(value<=150)return ['对敏感人群不健康','unhealthy'];if(value<=200)return ['不健康','unhealthy'];if(value<=300)return ['非常不健康','unhealthy'];return ['危险','unhealthy'];}
 function airAdvice(value){
  const title=by('air-advice-title'),text=by('air-advice-text'),box=document.querySelector('.air-advice');
  if(!Number.isFinite(value)){title.textContent='AQI 数据暂缺';text.textContent='暂不提供空气质量建议。';box.dataset.level='missing';return;}
  const entries=value<=50?['空气质量良好','可按日常习惯安排活动，留意天气变化。','good']:value<=100?['空气质量中等','特别敏感的人群请留意体感，适当调整户外活动。','moderate']:value<=150?['敏感人群需留意','敏感人群宜减少长时间或高强度户外活动。','unhealthy']:value<=200?['建议减少户外活动','减少长时间或高强度户外活动，关注最新预报。','unhealthy']:['建议优先室内活动','尽量减少户外停留，关注当地空气质量提示。','unhealthy'];
  [title.textContent,text.textContent,box.dataset.level]=entries;
 }
 // Supplement the existing AQI response without changing its backend contract.
 // https://open-meteo.com/en/docs/air-quality-api -- all concentrations in μg/m³.
 const pollutantFields=[['pm2_5','PM2.5'],['pm10','PM10'],['ozone','O₃'],['nitrogen_dioxide','NO₂']];
 function renderPollutants(values,note,loading=false){
  const list=by('pollutant-rows');list.replaceChildren();by('pollutants').setAttribute('aria-busy',String(loading));
  const valid=pollutantFields.map(([key])=>values[key]).filter(v=>Number.isFinite(v)&&v>=0),scale=Math.max(10,Math.ceil(Math.max(0,...valid)/10)*10);
  for(const [key,label] of pollutantFields){
   const row=document.createElement('div');row.className='pollutant-row';row.dataset.pollutant=key;
   const name=document.createElement('span');name.textContent=label;
   const track=document.createElement('span');track.className='pollutant-track';track.setAttribute('aria-hidden','true');
   const value=values[key],present=Number.isFinite(value)&&value>=0;
   if(present){const fill=document.createElement('span');fill.style.width=(value/scale*100)+'%';track.append(fill);}else row.classList.add(loading?'is-loading':'is-missing');
   const reading=document.createElement('strong');reading.textContent=present?value.toFixed(1):loading?'…':'—';reading.setAttribute('aria-label',present?`${label} ${value.toFixed(1)} 微克每立方米`:`${label} ${loading?'加载中':'数据暂缺'}`);
   row.append(name,track,reading);list.append(row);
  }
  by('pollutants-note').textContent=`模型估计 · μg/m³ · 统一量程 0–${scale}。${note}`;
 }
 async function loadPollutants(city,id,fallback){
  pollutantController?.abort();const controller=new AbortController();pollutantController=controller;
  by('pollutants-retry').hidden=true;renderPollutants(fallback,'正在补充其他污染物…',true);
  const timer=setTimeout(()=>controller.abort(),10000);
  try{
   const params=new URLSearchParams({latitude:String(city.latitude),longitude:String(city.longitude),current:pollutantFields.map(([key])=>key).join(','),timezone:'auto'});
   const response=await fetch('https://air-quality-api.open-meteo.com/v1/air-quality?'+params,{signal:controller.signal,credentials:'omit',referrerPolicy:'no-referrer'});
   if(!response.ok)throw Error('补充数据暂不可用');const data=await response.json();if(id!==airSequence||controller!==pollutantController)return;
   if(!data.current||typeof data.current.time!=='string')throw Error('补充数据缺少有效时间');
   const values={};for(const [key] of pollutantFields){const v=data.current[key];values[key]=data.current_units?.[key]==='μg/m³'&&Number.isFinite(v)&&v>=0?v:null;}
   const missing=pollutantFields.some(([key])=>values[key]===null);
   renderPollutants(values,`更新于 ${localTime(data.current.time)} · ${data.timezone||'时区未知'}${missing?'；部分数据暂缺。':'。'}`);
   by('pollutants-retry').hidden=!missing;
  }catch{
   if(id!==airSequence||controller!==pollutantController)return;
   renderPollutants(fallback,'其他数据暂不可用，可重试。');by('pollutants-retry').hidden=false;
  }finally{clearTimeout(timer);}
 }
 by('pollutants-retry').onclick=()=>pollutantRetry?.();
 async function loadAir(){if(!selected)return;const city={...selected},id=++airSequence;pollutantController?.abort();pollutantController=null;pollutantRetry=null;renderPollutants({},'等待空气质量数据…',true);state('.air-panel','loading');by('air-retry').hidden=true;try{const d=await json(`/api/air-quality?latitude=${city.latitude}&longitude=${city.longitude}`);if(id!==airSequence)return;const value=d.current?.us_aqi,pm=d.current?.pm2_5;by('air-value').textContent=Number.isFinite(value)?String(value):'—';WeatherVisual.gauge(value);airAdvice(value);const [label,level]=Number.isFinite(value)?grade(value):['AQI 数据缺失','missing'];by('air-grade').textContent=label;by('air-grade').dataset.grade=level;by('air-detail').textContent=`PM2.5 ${Number.isFinite(pm)?pm:'—'} μg/m³`;by('air-time').textContent=`更新于 ${localTime(d.updated_at)} · ${d.timezone||'时区未知'}；等级采用 US AQI 标准。`;state('.air-panel',Number.isFinite(value)||Number.isFinite(pm)?'ready':'empty','该城市暂无空气质量数据',loadAir);const fallback={pm2_5:pm};pollutantRetry=()=>loadPollutants(city,id,fallback);if(Number.isFinite(value)||Number.isFinite(pm))pollutantRetry();}catch(e){if(id!==airSequence)return;state('.air-panel','error',e.message,loadAir);}}
 function onWeather(e){selected=e.detail.city;++modelSequence;state('.model-panel','ready');by('run-model').disabled=false;by('model-result').textContent='—';WeatherVisual.roll(by('model-result'));by('model-result').className='';by('model-detail').textContent='尚未运行预测。选择城市后可手动运行；使用当地时间的下一整点作为预测目标。';loadAir();}
 window.addEventListener('weather-rendered',onWeather);
 if(typeof currentCity!=='undefined'&&currentCity)onWeather({detail:{city:{...currentCity}}});
 else state('.air-panel','empty','选择城市后查看空气质量',()=>by('city-toggle').click());
 by('air-retry').onclick=loadAir;
 by('run-model').onclick=async()=>{if(!selected){by('model-result').textContent='请先选择城市';by('model-result').className='unavailable';return;}const city={...selected},id=++modelSequence;by('run-model').disabled=true;state('.model-panel','loading');try{const d=await json(`/api/ml/online?latitude=${city.latitude}&longitude=${city.longitude}`);if(id!==modelSequence)return;const reasons={outside_model_scope:'所选城市暂不在模型适用范围',insufficient_as_of_hourly_data:'当前小时输入数据不足',hourly_model_missing:'模型文件缺失',incompatible_model:'模型文件不兼容'};state('.model-panel',Number.isFinite(d.prediction)?'ready':'empty',reasons[d.reason]||'暂无可用预测，请稍后重试',()=>by('run-model').click());by('model-result').className='';by('model-result').textContent=Number.isFinite(d.prediction)?`${d.prediction}°C`:'—';WeatherVisual.roll(by('model-result'));by('model-detail').textContent=`预测目标：${localTime(d.target_time)}；输入截止：${localTime(d.data_time)}（城市当地时间）。实验性预测，实时精度未验证。`;}catch(e){if(id===modelSequence)state('.model-panel','error',e.message,()=>by('run-model').click());}finally{if(id===modelSequence)by('run-model').disabled=false;}};
 async function loadMetrics(){by('model-metrics').textContent='正在读取本地实验记录…';try{const d=await json('/api/ml/hourly-experiment');by('model-label').textContent={ridge:'本地 Ridge',linear:'本地线性回归',persistence:'持久性基线'}[d.selected]||'本地回归模型';const entries=Object.entries(d.test_mae||{}).filter(([,v])=>Number.isFinite(v));if(!entries.length){by('model-metrics').textContent='暂无历史评估记录';return;}const table=document.createElement('table');table.className='experiment-table';const caption=document.createElement('caption');caption.textContent=`上海多区域小时气温测试 MAE（°C） · ${d.sources?.length||0} 个采样点`;table.append(caption);for(const [name,value] of entries){const row=document.createElement('tr'),label=document.createElement('th'),metric=document.createElement('td');label.scope='row';label.textContent={persistence:'持久性基线',linear:'线性回归',ridge:'Ridge'}[name]||name;metric.textContent=value.toFixed(3);row.append(label,metric);table.append(row);}by('model-metrics').replaceChildren(table);}catch(e){const p=document.createElement('p'),b=document.createElement('button');p.textContent=e.message;b.textContent='重试';b.onclick=loadMetrics;by('model-metrics').replaceChildren(p,b);}}
 loadMetrics();
})();

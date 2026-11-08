const log=document.querySelector('#messages'),form=document.querySelector('form'),input=document.querySelector('#message'),status=document.querySelector('#status'),welcome=document.querySelector('#welcome');let busy=false,activeId=null,loadingHistory=false,replyController=null,requestId=null,typingControl=null,activePending=null,stopRequested=false,stopConfirmed=false;
// Atmosphere belongs only to the empty welcome state, never to a long conversation.
function syncWelcome(){document.body.classList.toggle('welcome-active',!welcome.hidden);}
new MutationObserver(syncWelcome).observe(welcome,{attributes:true,attributeFilter:['hidden']});syncWelcome();

function nearBottom(){return log.scrollHeight-log.scrollTop-log.clientHeight<100}
function scrollBottom(){log.scrollTop=log.scrollHeight}
function add(label,text,user=false){const el=document.createElement('article');el.className='message'+(user?' user':'');const avatar=document.createElement('div');avatar.className='avatar';avatar.textContent='知';avatar.setAttribute('aria-hidden','true');const inner=document.createElement('div');inner.className='message-inner';const name=document.createElement('div');name.className='label';name.textContent=label;const body=document.createElement('div');body.className='message-body';inner.append(name,body);el.append(avatar,inner);if(text)WeatherMindAgent.render(body,text);attachActions(el,body,user);log.append(el);scrollBottom();return {el,inner,name,body}}
function setBusy(value){busy=value;document.querySelector('#stop-wait').hidden=!value||!replyController;document.querySelector('#send').hidden=value&&!!replyController;document.querySelectorAll('nav button,#send,#clear,#new-chat,#history-list button,#execution-mode').forEach(b=>b.disabled=value);log.setAttribute('aria-busy',String(value))}
function resizeInput(){input.style.height='auto';input.style.height=Math.min(120,input.scrollHeight)+'px'}
input.addEventListener('input',resizeInput);input.addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey&&!e.isComposing){e.preventDefault();form.requestSubmit()}});
form.addEventListener('submit',async e=>{e.preventDefault();if(busy||!input.value.trim())return;const message=input.value.trim();input.value='';resizeInput();welcome.hidden=true;status.textContent='';replyController=new AbortController();requestId=crypto.randomUUID();stopRequested=false;stopConfirmed=false;setBusy(true);const userMessage=add('你',message,true);const pending=add('知晴','');activePending=pending;pending.el.classList.add('pending');WeatherMindAgent.loading(pending.body);try{const data=await WeatherMindAgent.ask(message,WeatherMindAgent.home(),{signal:replyController.signal,requestId});if(stopRequested)throw new DOMException('Stopped','AbortError');document.querySelector('#agent-mode').textContent=data.mode_label+' · '+data.city+(data.mode==='model_unavailable'?' · 已安全降级':'');pending.el.classList.remove('pending');pending.el.classList.add('typing');pending.body.replaceChildren();const skip=document.createElement('button');skip.type='button';skip.className='skip';skip.textContent='立即显示';const control={finish:false,stopped:false};typingControl=control;skip.onclick=()=>{control.finish=true};pending.name.append(skip);await WeatherMindAgent.type(pending.body,data.response,()=>{if(nearBottom())scrollBottom()},control);skip.remove();pending.el.classList.remove('typing');if(stopRequested)pending.el.classList.add('stopped');if(!stopRequested){WeatherMindAgent.evidence(pending.inner,data);pending.el.dataset.turnId=data.turn_id;pending.el.dataset.conversation=data.session_id;}if(nearBottom())scrollBottom();await refreshHistory()}catch(e){pending.el.classList.remove('pending','typing');pending.body.replaceChildren();pending.body.textContent='暂时没能获得回复，请稍后重试。';status.textContent=e.name==='AbortError'?'已停止生成。':e.message||'请求失败，请重试。';if(e.name==='AbortError')pending.body.textContent='已停止生成。'}finally{if(stopRequested&&stopPromise)await stopPromise;if(stopConfirmed){pending.el.remove();userMessage.el.remove();welcome.hidden=!!log.querySelector('.message');input.value=message;resizeInput();await refreshHistory();}replyController=null;typingControl=null;activePending=null;setBusy(false);input.focus({preventScroll:true})}});
document.querySelectorAll('nav button').forEach(b=>b.onclick=()=>{input.value=b.dataset.question;form.requestSubmit()});document.querySelector('#clear').onclick=async()=>{if(busy)return;setBusy(true);try{const r=await fetch('/api/agent/session',{method:'DELETE'});if(!r.ok)throw Error();log.querySelectorAll('.message').forEach(m=>m.remove());welcome.hidden=false;document.querySelector('#agent-mode').textContent='天气与生活，一起安排';status.textContent='';log.scrollTop=0;await refreshHistory()}catch{status.textContent='清除失败，请重试。'}finally{setBusy(false)}};

function resetView(){log.querySelectorAll('.message').forEach(m=>m.remove());welcome.hidden=false;status.textContent='';input.value='';resizeInput();document.querySelector('#agent-mode').textContent='天气与生活，一起安排';log.scrollTop=0}
function showHistory(open){document.body.classList.toggle('history-open',open);document.querySelector('#history-toggle').setAttribute('aria-expanded',String(open));document.querySelector('#history-shade').hidden=!open;if(open)document.querySelector('#new-chat').focus()}
async function api(url,options){const r=await fetch(url,options);const d=await r.json();if(!r.ok)throw Error(d.error||'会话请求失败');return d}
async function refreshHistory(){
 const data=await api('/api/agent/conversations');activeId=data.active_id;const list=document.querySelector('#history-list');list.replaceChildren();
 let previousGroup=null;const today=new Date().toLocaleDateString('en-CA');
 for(const item of data.conversations){const updated=new Date(item.updated_at),isToday=updated.toLocaleDateString('en-CA')===today,group=isToday?'今天':'更早';if(group!==previousGroup){const heading=document.createElement('p');heading.className='history-group';heading.textContent=group;list.append(heading);previousGroup=group;}const button=document.createElement('button');button.type='button';button.className='history-item';button.classList.toggle('selected',item.id===activeId);if(item.id===activeId)button.setAttribute('aria-current','true');button.disabled=busy;button.title=item.title;const title=document.createElement('span');title.textContent=item.title;const date=document.createElement('small');date.textContent=isToday?updated.toLocaleTimeString('zh-CN',{hour:'2-digit',minute:'2-digit',hourCycle:'h23'}):updated.toLocaleDateString('zh-CN',{month:'numeric',day:'numeric'});button.append(title,date);button.onclick=()=>loadConversation(item.id,true);list.append(button)}
 return data;
}
async function loadConversation(id,activate=false){
 if(busy||loadingHistory)return;loadingHistory=true;setBusy(true);
 try{const data=await api('/api/agent/conversations/'+encodeURIComponent(id)+(activate?'/activate':''),activate?{method:'PUT'}:undefined);resetView();
 for(const turn of data.turns){welcome.hidden=true;add('你',turn.message,true);const reply=add('知晴',turn.reply.response);reply.el.dataset.turnId=turn.id;reply.el.dataset.conversation=id;if(turn.reply.edited)reply.el.classList.add('edited');WeatherMindAgent.evidence(reply.inner,turn.reply);document.querySelector('#agent-mode').textContent=turn.reply.mode_label+' · '+turn.reply.city}
 activeId=id;await refreshHistory();showHistory(false);scrollBottom();
 }catch(e){status.textContent='加载历史会话失败：'+e.message}finally{loadingHistory=false;setBusy(false)}
}
document.querySelector('#new-chat').onclick=async()=>{if(busy)return;setBusy(true);try{const data=await api('/api/agent/conversations',{method:'POST'});activeId=data.active_id;resetView();await refreshHistory();showHistory(false);input.focus()}catch(e){status.textContent='新建会话失败：'+e.message}finally{setBusy(false)}};
document.querySelector('#history-toggle').onclick=()=>showHistory(!document.body.classList.contains('history-open'));
document.querySelector('#history-shade').onclick=()=>showHistory(false);
document.addEventListener('keydown',e=>{if(e.key==='Escape')showHistory(false)});
(async()=>{setBusy(true);try{const data=await refreshHistory();setBusy(false);await loadConversation(data.active_id)}catch(e){status.textContent='历史会话加载失败：'+e.message;setBusy(false)}})();

fetch('/api/agent/config').then(r=>r.json()).then(data=>{
 const select=document.querySelector('#execution-mode');select.querySelector('[value=qwen]').disabled=!data.qwen_enabled;
 const reasons={missing_key:'尚未配置密钥',free_only_not_confirmed:'尚未确认免费额度保护',missing_model:'尚未指定模型',invalid_base_url:'API 地址无效'};
 document.querySelector('#mode-reason').textContent=data.qwen_enabled?'':(reasons[data.reason]||'智能模式不可用');
}).catch(()=>{document.querySelector('#mode-reason').textContent='无法获取智能模式配置'});

let stopPromise=null;
document.querySelector('#stop-wait').onclick=()=>{
 if(!requestId||stopRequested)return;
 stopRequested=true;if(typingControl)typingControl.stopped=true;
 const visible=typingControl?activePending.body.innerText:'';
 document.querySelector('#stop-wait').disabled=true;
 stopPromise=fetch('/api/agent/generations/'+requestId+'/cancel',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({visible})}).then(async r=>{if(!r.ok)throw Error('停止请求失败，请重试');stopConfirmed=true;status.textContent='已停止生成，本轮未保存。';}).catch(e=>{status.textContent=e.message;}).finally(()=>{document.querySelector('#stop-wait').disabled=false;});
 replyController?.abort();
};

function attachActions(el,body,user){
 const bar=document.createElement('div');bar.className='message-actions';
 const copy=document.createElement('button'),edit=document.createElement('button');
 for(const [button,label,path] of [[copy,'复制','<rect x="8" y="8" width="12" height="12" rx="2"/><path d="M16 8V4H4v12h4"/>'],[edit,'编辑','<path d="m15 4 5 5M4 20l4-1L20 7l-5-5L3 15Z"/>']]){button.type='button';button.title=label;button.setAttribute('aria-label',label);button.innerHTML='<svg viewBox="0 0 24 24" aria-hidden="true">'+path+'</svg>';bar.append(button);}
 copy.onclick=async()=>{try{await navigator.clipboard.writeText(body.innerText);copy.title='已复制';}catch{status.textContent='复制失败，请手动选择文本复制。';}};
 edit.onclick=()=>{
  if(busy||el.querySelector('.message-editor'))return;
  const editor=document.createElement('div');editor.className='message-editor';const area=document.createElement('textarea');area.value=body.innerText;area.setAttribute('aria-label','编辑消息');area.maxLength=user?1000:10000;const save=document.createElement('button'),cancel=document.createElement('button');save.type=cancel.type='button';save.textContent=user?'重新发送':'保存修改';cancel.textContent='取消';
  const closeEditor=()=>{editor.remove();body.hidden=false;el.classList.remove('editing-message');edit.focus({preventScroll:true});};
  cancel.onclick=closeEditor;save.onclick=async()=>{const text=area.value.trim();if(!text)return;if(user){input.value=text;closeEditor();form.requestSubmit();return;}if(!el.dataset.turnId){status.textContent='这条消息尚未保存，请稍后从历史中编辑。';return;}save.disabled=true;try{await api('/api/agent/conversations/'+el.dataset.conversation+'/turns/'+el.dataset.turnId,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({text})});body.replaceChildren();WeatherMindAgent.render(body,text);el.classList.add('edited');closeEditor();}catch(e){status.textContent=e.message;save.disabled=false;}};
  if(!user){const note=document.createElement('small');note.textContent='修改作为个人修订保存，原始查询依据保持不变。';editor.append(note);}const controls=document.createElement('div');controls.className='editor-controls';cancel.className='editor-cancel';save.className='editor-save';controls.append(cancel,save);editor.append(area,controls);body.hidden=true;el.classList.add('editing-message');el.querySelector('.message-inner').append(editor);const fit=()=>{area.style.height='auto';area.style.height=Math.min(300,Math.max(48,area.scrollHeight))+'px';};area.addEventListener('input',fit);area.addEventListener('keydown',event=>{if(event.key==='Escape'){event.preventDefault();event.stopPropagation();closeEditor();}});fit();area.focus();area.setSelectionRange(area.value.length,area.value.length);
 };
 el.append(bar);
}

document.querySelector('#open-settings').onclick=()=>{document.querySelector('.chat-workspace').hidden=true;document.querySelector('#settings-view').hidden=false;document.querySelector('#close-settings').focus();};
document.querySelector('#close-settings').onclick=()=>{document.querySelector('#settings-view').hidden=true;document.querySelector('.chat-workspace').hidden=false;document.querySelector('#open-settings').focus();};

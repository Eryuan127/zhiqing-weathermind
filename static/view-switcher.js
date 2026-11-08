(()=>{
 const home=document.querySelector('.brand'),assistant=document.querySelector('#nav-assistant'),main=document.querySelector('#main'),view=document.querySelector('#chat-view'),frame=document.querySelector('#chat-frame');
 // Keep the floating panel outside the content view so it remains available.
 document.body.append(document.querySelector('#assistant'));
 async function show(chat,push=false){
  if(chat){await ZhiqingAuth.ready;if(!ZhiqingAuth.user){ZhiqingAuth.open('assistant');if(location.pathname==='/assistant')history.replaceState({},'','/');chat=false;}}

  main.hidden=chat;view.hidden=!chat;if(chat){document.querySelector('#assistant').hidden=true;document.querySelector('#assistant-bubble').setAttribute('aria-expanded','false');}document.body.classList.toggle('chat-view-active',chat);
  assistant.hidden=chat;document.querySelector('#back-weather').hidden=!chat;
  if(chat){assistant.setAttribute('aria-current','page');home.removeAttribute('aria-current')}else{home.setAttribute('aria-current','page');assistant.removeAttribute('aria-current')}
  if(chat){if(!frame.getAttribute('src'))frame.src=frame.dataset.src;else if(frame.dataset.dirty){frame.contentWindow.location.reload();delete frame.dataset.dirty;}}
  if(push)history.pushState({chat},'',chat?'/assistant':'/');
  if(!chat)requestAnimationFrame(()=>window.dispatchEvent(new Event('resize')));
 }
 assistant.addEventListener('click',e=>{if(e.ctrlKey||e.metaKey||e.shiftKey||e.altKey)return;e.preventDefault();show(true,true)});
 document.querySelector('#back-weather').addEventListener('click',e=>{if(e.ctrlKey||e.metaKey||e.shiftKey||e.altKey)return;e.preventDefault();show(false,true)});
 home.addEventListener('click',e=>{if(e.ctrlKey||e.metaKey||e.shiftKey||e.altKey)return;e.preventDefault();show(false,true)});
 
 document.querySelector('#search').addEventListener('submit',()=>{if(main.hidden)show(false,true)});
 window.addEventListener('agent-history-updated',()=>{frame.dataset.dirty='true';if(!view.hidden){frame.contentWindow.location.reload();delete frame.dataset.dirty;}});
 window.addEventListener('popstate',()=>show(location.pathname==='/assistant'));
 show(location.pathname==='/assistant');
})();

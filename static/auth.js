window.ZhiqingAuth={user:null,pending:null};
(()=>{
 const auth=window.ZhiqingAuth,by=id=>document.getElementById(id),dialog=by('auth-dialog'),form=by('auth-form');let register=false;
 async function api(path,body){const r=await fetch('/api/auth/'+path,body?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:undefined);const data=await r.json();if(!r.ok)throw Error(data.error||'请求失败，请重试');return data;}
 function paint(){const u=auth.user;by('profile-name').textContent=u?u.nickname:'游客';by('profile-account').textContent=u?u.login_account||u.account:'登录后使用知晴助手';by('profile-login').hidden=!!u;by('profile-edit').hidden=!u;paintAvatar(by('profile-toggle'),u);paintAvatar(document.querySelector('.profile-info .profile-avatar'),u);by('profile-switch').hidden=!u;by('profile-logout').hidden=!u;by('profile-toggle').title=u?u.nickname:'注册 / 登录';}
 function mode(value){register=value;by('auth-title').textContent=value?'注册知晴':'登录知晴';by('auth-submit').textContent=value?'注册并登录':'登录';by('auth-mode').textContent=value?'已有账号？去登录':'还没有账号？注册账号';by('account-field').hidden=false;form.elements.account.required=true;form.elements.account.minLength=value?3:1;form.elements.account.maxLength=value?32:64;if(value)form.elements.account.pattern='[A-Za-z][A-Za-z0-9_]{2,31}';else form.elements.account.removeAttribute('pattern');form.elements.account.placeholder=value?'设置一个好记的登录账号':'请输入登录账号，不是昵称';by('account-hint').textContent=value?'3–32 位，以英文字母开头，可含数字和下划线。':'使用注册时设置的账号；旧版随机账号仍可登录。';by('auth-description').textContent=value?'设置登录账号、昵称和密码，和知晴一起安排天气与生活。':'登录后，和知晴一起安排天气与生活。';by('nickname-field').hidden=!value;form.elements.nickname.required=value;form.elements.password.autocomplete=value?'new-password':'current-password';by('auth-error').textContent='';}
 auth.open=(pending=null)=>{auth.pending=pending;mode(false);by('profile-card').hidden=true;by('profile-toggle').setAttribute('aria-expanded','false');dialog.showModal();};
 auth.ready=api('me').then(data=>{auth.user=data.user;paint();if(sessionStorage.getItem('zhiqing.showProfile')){sessionStorage.removeItem('zhiqing.showProfile');by('profile-card').hidden=false;by('profile-toggle').setAttribute('aria-expanded','true');}}).catch(()=>{by('profile-account').textContent='账号暂时无法加载，请重试登录';});
 by('profile-toggle').onclick=()=>{const open=by('profile-card').hidden;by('profile-card').hidden=!open;by('profile-toggle').setAttribute('aria-expanded',String(open));};
 by('profile-login').onclick=()=>auth.open();by('profile-switch').onclick=()=>auth.open();
 function clearPrivate(){WeatherMindLocation.data=null;WeatherMindLocation.owner=null;localStorage.removeItem('weathermind.currentCity');localStorage.removeItem('weathermind.cities');localStorage.setItem('zhiqing.authChange',String(Date.now())+Math.random());}
 window.addEventListener('storage',e=>{if(e.key==='zhiqing.authChange')location.href='/';});
 by('profile-logout').onclick=async()=>{try{await api('logout',{});clearPrivate();location.href='/';}catch(e){by('profile-account').textContent=e.message;}};
 by('auth-close').onclick=()=>dialog.close();by('auth-mode').onclick=()=>mode(!register);
 form.onsubmit=async e=>{e.preventDefault();by('auth-submit').disabled=true;by('auth-error').textContent='';try{const data=await api(register?'register':'login',{account:form.elements.account.value,nickname:form.elements.nickname.value,password:form.elements.password.value});clearPrivate();auth.user=data.user;sessionStorage.setItem('zhiqing.showProfile','1');location.href=auth.pending==='assistant'?'/assistant':'/';}catch(e){by('auth-error').textContent=e.message;}finally{by('auth-submit').disabled=false;}};

 function paintAvatar(node,u){
  if(!node)return;
  if(!node.dataset.original)node.dataset.original=node.innerHTML;
  node.replaceChildren();if(u?.avatar_url){const image=document.createElement('img');image.src=u.avatar_url;image.alt='用户头像';node.append(image);}else node.innerHTML=node.dataset.original;
 }
 const profileDialog=by('profile-dialog'),profileForm=by('profile-form');
 by('profile-edit').onclick=()=>{if(!auth.user)return;profileForm.elements.account.value=auth.user.login_account||auth.user.account;profileForm.elements.nickname.value=auth.user.nickname;by('profile-error').textContent='';paintAvatar(by('avatar-preview'),auth.user);by('profile-card').hidden=true;profileDialog.showModal();};
 by('profile-close').onclick=()=>profileDialog.close();
 function profileUpdated(data){auth.user=data.user;paint();paintAvatar(by('avatar-preview'),auth.user);const frame=by('chat-frame');if(frame.getAttribute('src')){const heading=frame.contentDocument?.querySelector('#welcome h1');if(heading){heading.dataset.original='你好，'+auth.user.nickname+'！';heading.textContent=(window.WeatherContextUI?.get()?.salutation||'你好')+'，'+auth.user.nickname+'！';}}}
 profileForm.onsubmit=async e=>{e.preventDefault();by('profile-save').disabled=true;by('profile-error').textContent='';try{const response=await fetch('/api/auth/profile',{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({account:profileForm.elements.account.value,nickname:profileForm.elements.nickname.value})});const data=await response.json();if(!response.ok)throw Error(data.error||'保存失败');profileUpdated(data);by('profile-error').textContent='资料已保存';}catch(error){by('profile-error').textContent=error.message;}finally{by('profile-save').disabled=false;}};
 by('avatar-file').onchange=async()=>{
  const file=by('avatar-file').files[0];if(!file)return;
  if(file.size>1024*1024){by('profile-error').textContent='图片不能超过1MB';by('avatar-file').value='';return;}
  const body=new FormData();body.append('avatar',file);by('avatar-file').disabled=true;by('profile-error').textContent='正在上传头像…';
  try{const r=await fetch('/api/auth/avatar',{method:'POST',body});const data=await r.json();if(!r.ok)throw Error(data.error||'上传失败');profileUpdated(data);by('profile-error').textContent='头像已更新';}catch(error){by('profile-error').textContent=error.message;}finally{by('avatar-file').disabled=false;by('avatar-file').value='';}
 };
 by('avatar-remove').onclick=async()=>{by('avatar-remove').disabled=true;try{const r=await fetch('/api/auth/avatar',{method:'DELETE'});const data=await r.json();if(!r.ok)throw Error(data.error||'恢复失败');profileUpdated(data);by('profile-error').textContent='已恢复默认头像';}catch(error){by('profile-error').textContent=error.message;}finally{by('avatar-remove').disabled=false;}};
 document.addEventListener('click',e=>{if(!e.target.closest('.profile')){by('profile-card').hidden=true;by('profile-toggle').setAttribute('aria-expanded','false');}});
 document.addEventListener('keydown',e=>{if(e.key==='Escape'){by('profile-card').hidden=true;by('profile-toggle').setAttribute('aria-expanded','false');}});
})();

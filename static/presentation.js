/* Presentation only: no endpoints or request parameters are changed. */
window.WeatherUI={
 state(card,state,message,retry){if(!card)return;card.dataset.state=state;card.setAttribute('aria-busy',String(state==='loading'));let box=card.querySelector(':scope > .card-status');if(!box){box=document.createElement('div');box.className='card-status';box.setAttribute('role','status');card.append(box);}box.replaceChildren();box.hidden=state==='ready';const title=card.matches('.current')?'当前天气':card.matches('.trend')?'24 小时趋势':card.querySelector('h2')?.textContent;if(state!=='ready'&&title){const heading=document.createElement('strong');heading.textContent=title;box.append(heading);}if(state==='loading'){box.setAttribute('aria-label','正在加载');for(let i=0;i<3;i++){const line=document.createElement('div');line.className='skeleton-line';box.append(line);}}else if(state!=='ready'){const text=document.createElement('p');text.textContent=message;box.append(text);if(retry){const button=document.createElement('button');button.type='button';button.textContent='重试';button.onclick=retry;box.append(button);}}},
 weather(state,message,retry){document.querySelectorAll('.current,.trend,.detail,.week,.hourly-panel').forEach(c=>this.state(c,state,message,retry));}
};
document.addEventListener('DOMContentLoaded',()=>{
 document.querySelector('#open-tools').onclick=()=>document.querySelector('#tools-dialog').showModal();
 document.querySelector('#close-tools').onclick=()=>document.querySelector('#tools-dialog').close();
 if(!document.querySelector('.current').dataset.state)WeatherUI.weather('loading');
});

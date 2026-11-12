'use strict';
const $ = id => document.getElementById(id);
let snapshot, csrf = document.querySelector('meta[name=q-csrf]').content, generation = 0;
const number = value => value == null ? '—' : new Intl.NumberFormat('ru-RU', {maximumFractionDigits:1}).format(value);
function draw() {
  if (!snapshot) return;
  const s=snapshot.summary, w=snapshot.successful_windows;
  $('cards').replaceChildren();
  for (const [title,value] of [['Всего запросов',s.total],['Успешных',s.success],['Ошибок',s.errors],['Успешных сегодня',w.today],['Успешных за 7 дней',w.days7],['Успешных за 30 дней',w.days30],['Success rate',s.success_rate==null?'—':number(s.success_rate)+'%'],['Известная длительность · мин',s.duration_seconds==null?'—':number(s.duration_seconds/60)],['Средняя обработка · мс',s.avg_processing_ms]]) {
    const card=document.createElement('article');card.className='card';
    const label=document.createElement('p');label.textContent=title;
    const valueNode=document.createElement('strong');valueNode.textContent=typeof value==='string'?value:number(value);
    card.append(label,valueNode);$('cards').append(card);
  }
  $('chart').replaceChildren();
  $('chart-detail').textContent=snapshot.daily.length?'Выберите день. Дни без запросов не показаны.':'За выбранный период событий нет.';
  const yes=$('show-success').checked, no=$('show-errors').checked;
  const max=Math.max(1,...snapshot.daily.map(d=>(yes?d.success:0)+(no?d.errors:0)));
  for (const d of snapshot.daily) {
    const button=document.createElement('button');button.className='day';
    const text=`${d.day}: успешно ${d.success}, ошибок ${d.errors}`;
    button.title=text;button.setAttribute('aria-label',text);
    const stack=document.createElement('span');stack.className='stack';
    for (const [className,value] of [['bar-error',no?d.errors:0],['bar-success',yes?d.success:0]]) {
      const bar=document.createElement('span');bar.className=className;bar.style.height=(value/max*175)+'px';stack.append(bar);
    }
    const label=document.createElement('small');label.textContent=d.day.slice(5);
    button.append(stack,label);button.onmouseenter=button.onfocus=()=>{$('chart-detail').textContent=text;};$('chart').append(button);
  }
  $('events').replaceChildren();
  for (const e of snapshot.recent) {
    const row=document.createElement('tr');
    const date=new Intl.DateTimeFormat('ru-RU',{timeZone:snapshot.timezone,dateStyle:'short',timeStyle:'medium'}).format(new Date(e.created_at));
    for(const value of [date,e.status==='success'?'Успешно':'Ошибка',e.media_type,number(e.processing_ms)+' мс',e.duration_seconds==null?'Неизвестна':number(e.duration_seconds)+' с',e.source,e.error_code||'—']){
      const cell=document.createElement('td');cell.textContent=value;row.append(cell);
    }
    row.children[1].className=e.status;$('events').append(row);
  }
  if(!snapshot.recent.length){const row=document.createElement('tr'),cell=document.createElement('td');cell.colSpan=7;cell.textContent='Событий пока нет';row.append(cell);$('events').append(row);}
}
async function refresh() {
  const ticket=++generation;
  $('refresh').disabled=true;$('error').hidden=true;$('data').hidden=true;$('updated').textContent='Загрузка…';
  try {
    const response=await fetch('/api/admin/stats?'+new URLSearchParams({period:$('period').value,timezone:$('timezone').value}),{cache:'no-store'});
    if(response.status===401||response.status===404){location.assign('/admin/login');return;}
    if(!response.ok)throw Error('load');
    const next=await response.json();if(ticket!==generation)return;
    snapshot=next;csrf=next.csrf;draw();$('data').hidden=false;
    $('updated').textContent='Обновлено '+new Intl.DateTimeFormat('ru-RU',{timeZone:next.timezone,timeStyle:'medium'}).format(new Date(next.as_of));
  }catch{if(ticket!==generation)return;snapshot=null;$('data').hidden=true;$('updated').textContent='';$('error').hidden=false;$('error').textContent='Не удалось загрузить статистику. Проверьте доступность базы и повторите попытку.';}
  finally{if(ticket===generation)$('refresh').disabled=false;}
}
$('refresh').onclick=refresh;$('period').onchange=refresh;$('timezone').onchange=refresh;
$('show-success').onchange=draw;$('show-errors').onchange=draw;
$('logout').onclick=async()=>{
  try{if(!csrf)throw Error();const r=await fetch('/api/admin/logout',{method:'POST',headers:{'X-CSRF-Token':csrf}});if(!r.ok)throw Error();location.assign('/admin/login');}
  catch{$('error').hidden=false;$('error').textContent='Не удалось завершить сессию. Повторите после восстановления соединения. Сессия истекает через час после входа.';}
};
refresh();

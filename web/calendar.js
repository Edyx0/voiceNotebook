/* A recurring weekly plan, with editable drafts and real recording matches. */
let calendarWeek = null, editingClass = null, classSnapshot = null, isNewClass = false;
const minuteValue = value => /^\d\d:\d\d$/.test(value) ? Number(value.slice(0,2))*60+Number(value.slice(3)) : NaN;
const clockValue = minute => `${String(Math.floor(minute/60)).padStart(2,'0')}:${String(minute%60).padStart(2,'0')}`;
const classRows = () => [...document.querySelectorAll('#lecture-slots .slot')];
function classValue(row) { return Object.fromEntries([...row.querySelectorAll('[data-key]')].map(input=>[input.dataset.key,input.dataset.key==='day'?(input.value===''?null:Number(input.value)):input.value])); }
function setClassValue(row,value) { for(const input of row.querySelectorAll('[data-key]')) input.value=value[input.dataset.key]??''; }
const courseColors = ['oklch(.94 .12 110)','oklch(.91 .055 27)','oklch(.90 .012 250)','oklch(.92 .05 85)','oklch(.91 .03 5)','oklch(.86 .015 250)','oklch(.96 .07 110)','oklch(.95 .025 27)'];
function courseColor(course) { let hash=0;for(const c of course.toUpperCase())hash=(hash*31+c.charCodeAt(0))>>>0;return courseColors[hash%courseColors.length]; }
function recordingMatches(value,week=calendarWeek,values=classRows().map(classValue)) {
  if(!state?.recordings)return [];
  const start=minuteValue(value.start),end=minuteValue(value.end),zone=state.config.timezone;
  return state.recordings.filter(recording=>{
    if(!recording.route||recording.status==='ignored'||!recording.recorded_at||recording.route.course!==value.course.toUpperCase()||recording.route.week!==week)return false;
    const parts=Object.fromEntries(new Intl.DateTimeFormat('en-US',{timeZone:zone,weekday:'short',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).formatToParts(new Date(recording.recorded_at)).map(p=>[p.type,p.value]));
    const day=['Mon','Tue','Wed','Thu','Fri','Sat','Sun'].indexOf(parts.weekday),minute=Number(parts.hour)*60+Number(parts.minute);
    const exactClass=values.some(v=>v.day===day&&v.course.toUpperCase()===value.course.toUpperCase()&&minute>=minuteValue(v.start)&&minute<minuteValue(v.end));
    return day===value.day&&minute<end&&(minute>=start||(!exactClass&&minute>=start-state.config.tolerance_minutes));
  });
}
function renderTimetable() {
  if(!state)return;
  const rows=classRows(),values=rows.map(classValue),weeks=Number($('semester-weeks').value)||16,weekOne=$('week-one').value;
  if(calendarWeek===null){const today=state.overview?.now?.slice(0,10)||localInput(new Date().toISOString()).slice(0,10);calendarWeek=weekOne?Math.max(1,Math.min(weeks,Math.floor((Date.parse(today)-Date.parse(weekOne))/604800000)+1)):1;}
  calendarWeek=Math.max(1,Math.min(weeks,calendarWeek));
  const selector=$('calendar-week');
  selector.replaceChildren();for(let week=1;week<=weeks;week++){const option=el('option',weekOne?`Week ${week}`:'Weekly plan');option.value=week;selector.append(option);if(!weekOne)break;}selector.value=calendarWeek;
  $('previous-week').disabled=!weekOne||calendarWeek===1;$('next-week').disabled=!weekOne||calendarWeek===weeks;
  const valid=drawWeeklyCalendar($('weekly-calendar'),values,{week:calendarWeek,weekOne,onEdit:(value,button)=>editTimetableClass(rows[value.index],button),onAdd:newTimetableClass});
  const incomplete=$('incomplete-classes');incomplete.replaceChildren();
  values.forEach((value,index)=>{if(!valid.some(v=>v.index===index)){const button=el('button',`${value.course||'New class'} · complete times`,'incomplete-class');button.type='button';button.onclick=()=>editTimetableClass(rows[index],button);incomplete.append(button);}});
  const comparable=v=>({course:v.course.toUpperCase(),day:v.day,start:v.start,end:v.end});
  const dirty=JSON.stringify(values.map(comparable))!==JSON.stringify(state.config.lectures.map(comparable))||weekOne!==state.config.week_one;
  $('calendar-draft').textContent=dirty?'Unsaved changes':'';
}
function drawWeeklyCalendar(root,values,options) {
  const {week,weekOne}=options;
  const valid=values.map((value,index)=>({...value,index,startMinute:minuteValue(value.start),endMinute:minuteValue(value.end)})).filter(v=>v.course&&v.day!==null&&v.startMinute<v.endMinute);
  const first=valid.length?Math.min(...valid.map(v=>v.startMinute)):540,last=valid.length?Math.max(...valid.map(v=>v.endMinute)):1020;
  const dayCount=values.some(v=>v.day>=5)?7:5,pixelsPerMinute=Math.max(.5,Math.min(56/60,(innerHeight*.56-65)/(last-first))),height=Math.max(56,(last-first)*pixelsPerMinute);
  root.replaceChildren();root.dataset.start=clockValue(first);root.dataset.end=clockValue(last);
  const scroll=el('div',null,'calendar-scroll'),head=el('div',null,'calendar-head'),body=el('div',null,'calendar-body');
  head.style.gridTemplateColumns=body.style.gridTemplateColumns=`44px repeat(${dayCount},minmax(100px,1fr))`;
  const zone=el('span',null,'calendar-zone');zone.textContent='';head.append(zone);
  const weekStart=weekOne?new Date(Date.parse(weekOne+'T12:00:00Z')+(week-1)*604800000):null;
  for(let day=0;day<dayCount;day++){
    const label=el('div',null,'calendar-day-label');label.append(el('span',days[day].slice(0,3)));
    if(weekStart){const offset=(day-((weekStart.getUTCDay()+6)%7)+7)%7,when=new Date(weekStart.getTime()+offset*86400000);label.append(el('strong',String(when.getUTCDate())));}
    head.append(label);
  }
  const axis=el('div',null,'calendar-axis');axis.style.height=`${height+15}px`;
  const ticks=[first];for(let t=Math.ceil((first+1)/60)*60;t<last;t+=60)ticks.push(t);ticks.push(last);
  for(const tick of ticks){const label=el('span',clockValue(tick));label.style.top=`${(tick-first)*pixelsPerMinute}px`;axis.append(label);}body.append(axis);
  for(let day=0;day<dayCount;day++){
    const column=el('div',null,'calendar-day');column.style.height=`${height}px`;column.dataset.day=day;
    for(const tick of ticks){const rule=el('div',null,'calendar-rule');rule.style.top=`${(tick-first)*pixelsPerMinute}px`;column.append(rule);}
    const events=valid.filter(v=>v.day===day).sort((a,b)=>a.startMinute-b.startMinute),lanes=[];let group=[],groupEnd=-1;
    function placeGroup(){const count=Math.max(1,...group.map(v=>v.lane+1));for(const value of group){
      const matches=recordingMatches(value,week,values),occurrence=options.classes?.find(c=>c.index===value.index),button=el('button',null,'calendar-event'+(matches.length?' has-recording':'')+(occurrence?' '+occurrence.status+'-class':''));button.type='button';button.dataset.course=value.course.toUpperCase();button.dataset.color=courseColor(value.course);button.dataset.recordingCount=matches.length;
      button.style.backgroundColor=courseColor(value.course);button.style.top=`${(value.startMinute-first)*pixelsPerMinute+2}px`;button.style.height=`${Math.max(24,(value.endMinute-value.startMinute)*pixelsPerMinute-4)}px`;button.style.left=`calc(${value.lane/count*100}% + 3px)`;button.style.width=`calc(${100/count}% - 6px)`;
      button.append(el('strong',value.course.toUpperCase()),el('span',`${value.start}–${value.end}`));
      if(matches.length)button.append(el('small',`● ${matches.length} recording${matches.length===1?'':'s'}`,'recording-mark'));
      button.setAttribute('aria-label',`${value.course}, ${days[value.day]}, ${value.start} to ${value.end}${matches.length?`, ${matches.length} matched recordings`:''}. Edit class`);
      button.onclick=()=>options.onEdit?.(value,button);column.append(button);
    }group=[];lanes.length=0;}
    for(const event of events){if(event.startMinute>=groupEnd&&group.length)placeGroup();let lane=lanes.findIndex(end=>end<=event.startMinute);if(lane<0)lane=lanes.length;lanes[lane]=event.endMinute;event.lane=lane;group.push(event);groupEnd=Math.max(event.endMinute,...group.map(v=>v.endMinute));}placeGroup();
    if(options.onAdd)column.ondblclick=event=>{if(event.target.closest('.calendar-event'))return;const minute=Math.max(0,Math.min(1380,Math.round((first+(event.clientY-column.getBoundingClientRect().top)/pixelsPerMinute)/30)*30));options.onAdd({course:'',day,start:clockValue(minute),end:clockValue(minute+60)},column);};
    if(options.now&&options.classes?.some(c=>c.day===day&&c.date===options.now.date)&&options.now.minute>=first&&options.now.minute<=last){const line=el('div',null,'calendar-now');line.style.top=`${(options.now.minute-first)*pixelsPerMinute}px`;line.setAttribute('aria-label','Current time '+clockValue(options.now.minute));column.append(line);}
    body.append(column);
  }
  scroll.append(head,body);root.append(scroll);
  return valid;
}
function editTimetableClass(row,anchor=null,newClass=false) {
  editingClass=row;classSnapshot=classValue(row);isNewClass=newClass;
  for(const key of ['course','day','start','end'])$('lecture-'+key).value=classSnapshot[key]??'';
  $('lecture-heading').textContent=newClass?'New class':'Edit class';$('lecture-delete').hidden=newClass;
  const editor=$('lecture-editor'),rect=anchor?.getBoundingClientRect()||$('weekly-calendar').getBoundingClientRect();
  editor.style.left=`${Math.max(16,Math.min(innerWidth-340,rect.left+20))}px`;editor.style.top=`${Math.max(16,Math.min(innerHeight-390,rect.top))}px`;
  if(!editor.matches(':popover-open'))editor.showPopover();$('lecture-course').focus();
}
function newTimetableClass(value={course:'',day:0,start:'09:00',end:'10:00'},anchor=null) { const row=slot(value);editTimetableClass(row,anchor,true); }
for(let day=0;day<7;day++){const option=el('option',days[day]);option.value=day;$('lecture-day').append(option);}
$('add-slot').onclick=()=>newTimetableClass();
$('lecture-form').oninput=()=>{
  if(!editingClass)return;const value=Object.fromEntries(['course','day','start','end'].map(k=>[k,$('lecture-'+k).value]));setClassValue(editingClass,value);renderTimetable();
};
$('lecture-form').onsubmit=event=>{event.preventDefault();if($('lecture-start').value>=$('lecture-end').value){$('lecture-end').setCustomValidity('End time must be after start time.');$('lecture-end').reportValidity();return;}$('lecture-end').setCustomValidity('');$('lecture-editor').hidePopover();renderTimetable();};
$('lecture-end').oninput=()=>$('lecture-end').setCustomValidity('');
$('lecture-start').oninput=()=>$('lecture-end').setCustomValidity('');
$('lecture-cancel').onclick=()=>{if(editingClass){if(isNewClass)editingClass.remove();else setClassValue(editingClass,classSnapshot);}$('lecture-editor').hidePopover();renderTimetable();};
$('lecture-delete').onclick=()=>{editingClass?.remove();$('lecture-editor').hidePopover();renderTimetable();};
$('calendar-week').onchange=()=>{calendarWeek=Number($('calendar-week').value);renderTimetable();};
$('previous-week').onclick=()=>{calendarWeek--;renderTimetable();};$('next-week').onclick=()=>{calendarWeek++;renderTimetable();};
for(const id of ['week-one','semester-weeks'])$(id).addEventListener('input',renderTimetable);
function installHelp() {
  document.querySelectorAll('[data-help]').forEach((host,index)=>{
    const text=host.dataset.help,button=el('button','?','help-button'),tip=el('span',text,'help-tooltip');button.type='button';button.setAttribute('aria-label','Help');button.setAttribute('aria-describedby','help-'+index);tip.id='help-'+index;tip.setAttribute('role','tooltip');host.className='help-wrap';host.append(button,tip);
    const position=()=>{const rect=button.getBoundingClientRect();tip.style.left=`${Math.max(10,Math.min(innerWidth-275,rect.left))}px`;tip.style.top=`${Math.min(innerHeight-130,rect.bottom+8)}px`;};host.onmouseenter=position;button.onfocus=position;button.onclick=event=>{event.preventDefault();position();host.classList.toggle('open');};
  });
  document.addEventListener('click',event=>document.querySelectorAll('.help-wrap.open').forEach(h=>{if(!h.contains(event.target))h.classList.remove('open');}));
}
installHelp();if(typeof state!=='undefined'&&state)renderTimetable();
window.addEventListener('resize',()=>requestAnimationFrame(renderTimetable));

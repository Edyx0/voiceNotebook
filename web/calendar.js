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
  const valid=drawWeeklyCalendar($('weekly-calendar'),values,{week:calendarWeek,weekOne,onEdit:(value,button)=>editTimetableClass(rows[value.index],button),onAdd:newTimetableClass,onMove:(value,change)=>moveWeeklyClass(value,change)});
  const incomplete=$('incomplete-classes');incomplete.replaceChildren();
  values.forEach((value,index)=>{if(!valid.some(v=>v.index===index)){const button=el('button',`${value.course||'New class'} · complete times`,'incomplete-class');button.type='button';button.onclick=()=>editTimetableClass(rows[index],button);incomplete.append(button);}});
  const comparable=v=>({course:v.course.toUpperCase(),day:v.day,start:v.start,end:v.end});
  const dirty=JSON.stringify(values.map(comparable))!==JSON.stringify(state.config.lectures.map(comparable))||weekOne!==state.config.week_one;
  $('calendar-draft').textContent=dirty?'Unsaved changes':'';
}
function moveWeeklyClass(value,change,fromHome=false,displayWeek=null) {
  const rows=classRows();
  const same=row=>{
    const draft=classValue(row);
    return draft.course.toUpperCase()===value.course.toUpperCase()&&draft.day===value.day&&draft.start===value.start&&draft.end===value.end;
  };
  const matches=fromHome?rows.filter(same):[];
  const row=fromHome?(matches.length===1?matches[0]:null):rows[value.index];
  if(fromHome){calendarWeek=displayWeek||state.overview?.week||calendarWeek;view('setup');}
  if(!row){notice('Review your existing timetable draft before moving this class.',true);return;}
  setClassValue(row,{...classValue(row),...change});renderTimetable();
  notice('This move affects every week. Review and save the timetable to apply.');
}
function drawWeeklyCalendar(root,values,options) {
  const {week,weekOne}=options;
  const valid=values.map((value,index)=>({...value,index,startMinute:minuteValue(value.start),endMinute:minuteValue(value.end)})).filter(v=>v.course&&v.day!==null&&v.startMinute<v.endMinute);
  const first=valid.length?Math.min(...valid.map(v=>v.startMinute)):540,last=valid.length?Math.max(...valid.map(v=>v.endMinute)):1020;
  if(root.dataset.dragging==='true')return valid;
  const previous=root.querySelector('.calendar-scroll'),position=previous?.dataset.positionInitialized==='true'&&previous.clientHeight?{top:previous.scrollTop,left:previous.scrollLeft}:null;
  const dayCount=7,pixelsPerMinute=1.2,gridStart=0,gridEnd=1440,height=(gridEnd-gridStart)*pixelsPerMinute;
  root.replaceChildren();root.dataset.start=clockValue(first);root.dataset.end=clockValue(last);
  const scroll=el('div',null,'calendar-scroll'),head=el('div',null,'calendar-head'),body=el('div',null,'calendar-body');
  scroll.tabIndex=0;scroll.setAttribute('aria-label','Scroll the weekly calendar');
  head.style.gridTemplateColumns=body.style.gridTemplateColumns=`44px repeat(${dayCount},minmax(100px,1fr))`;
  head.style.minWidth=body.style.minWidth=`${44+dayCount*100}px`;
  const zone=el('span',null,'calendar-zone');zone.textContent='';head.append(zone);
  const weekStart=weekOne?new Date(Date.parse(weekOne+'T12:00:00Z')+(week-1)*604800000):null;
  for(let day=0;day<dayCount;day++){
    const label=el('div',null,'calendar-day-label');label.append(el('span',days[day].slice(0,3)));
    if(weekStart){const offset=(day-((weekStart.getUTCDay()+6)%7)+7)%7,when=new Date(weekStart.getTime()+offset*86400000);label.append(el('strong',String(when.getUTCDate())));}
    head.append(label);
  }
  const axis=el('div',null,'calendar-axis');axis.style.height=`${height+15}px`;
  const ticks=[];for(let t=gridStart;t<=gridEnd;t+=60)ticks.push(t);
  for(const tick of ticks){const label=el('span',clockValue(tick));label.style.top=`${(tick-gridStart)*pixelsPerMinute}px`;axis.append(label);}body.append(axis);
  let dragging=null,preview=null;
  function dragMinute(event,column) {
    const duration=dragging.value.endMinute-dragging.value.startMinute;
    const minute=gridStart+(event.clientY-column.getBoundingClientRect().top-dragging.grabOffset)/pixelsPerMinute;
    return Math.max(0,Math.min(Math.floor((1439-duration)/15)*15,Math.round(minute/15)*15));
  }
  function showDragPreview() {
    const {button,clientX,clientY,value}=dragging,bounds=scroll.getBoundingClientRect();
    button.style.pointerEvents='none';
    const column=document.elementFromPoint(clientX,clientY)?.closest('.calendar-day');
    button.style.pointerEvents='';
    if(!column||!body.contains(column)||clientX<bounds.left||clientX>bounds.right||clientY<head.getBoundingClientRect().bottom||clientY>bounds.bottom){
      dragging.target=null;preview?.remove();preview=null;return;
    }
    const minute=dragMinute(dragging,column),duration=value.endMinute-value.startMinute;
    dragging.target={day:Number(column.dataset.day),minute};
    if(!preview){preview=el('div',null,'calendar-drop-preview');preview.setAttribute('aria-hidden','true');}
    preview.textContent=`${value.course.toUpperCase()} · ${clockValue(minute)}–${clockValue(minute+duration)}`;
    preview.style.top=`${(minute-gridStart)*pixelsPerMinute+2}px`;
    preview.style.height=`${Math.max(24,duration*pixelsPerMinute-4)}px`;column.append(preview);
  }
  function autoScrollDrag() {
    if(!dragging)return;
    dragging.frame=null;
    const bounds=scroll.getBoundingClientRect(),{clientX:x,clientY:y}=dragging;
    if(x<bounds.left||x>bounds.right||y<bounds.top||y>bounds.bottom)return;
    const oldTop=scroll.scrollTop,oldLeft=scroll.scrollLeft;
    if(y<head.getBoundingClientRect().bottom+24)scroll.scrollTop-=8;
    else if(y>bounds.bottom-24)scroll.scrollTop+=8;
    if(x<bounds.left+24)scroll.scrollLeft-=8;
    else if(x>bounds.right-24)scroll.scrollLeft+=8;
    if(scroll.scrollTop!==oldTop||scroll.scrollLeft!==oldLeft){showDragPreview();dragging.frame=requestAnimationFrame(autoScrollDrag);}
  }
  function enableClassMove(button,value) {
    let pending=null,suppressClick=false;
    button.classList.add('movable');button.title='Drag to move this weekly class';
    function finish(commit) {
      if(!pending)return;
      const current=pending,target=current.target;pending=null;
      if(current.frame)cancelAnimationFrame(current.frame);
      dragging=null;preview?.remove();preview=null;delete root.dataset.dragging;button.classList.remove('dragging');
      document.removeEventListener('keydown',cancelOnEscape);
      if(button.hasPointerCapture(current.pointerId))button.releasePointerCapture(current.pointerId);
      if(commit&&target&&(target.day!==value.day||target.minute!==value.startMinute)){
        const duration=value.endMinute-value.startMinute;
        options.onMove(value,{day:target.day,start:clockValue(target.minute),end:clockValue(target.minute+duration)});
      }
    }
    function cancelOnEscape(event){
      if(event.key==='Escape'&&pending?.active){
        event.preventDefault();suppressClick=true;finish(false);
        document.addEventListener('pointerup',()=>setTimeout(()=>{suppressClick=false;},0),{once:true});
      }
    }
    button.addEventListener('pointerdown',event=>{
      if(event.button!==0||!event.isPrimary)return;
      pending={value,button,pointerId:event.pointerId,startX:event.clientX,startY:event.clientY,
        clientX:event.clientX,clientY:event.clientY,grabOffset:Math.max(0,Math.min(button.offsetHeight,event.clientY-button.getBoundingClientRect().top)),active:false};
      button.setPointerCapture(event.pointerId);document.addEventListener('keydown',cancelOnEscape);
    });
    button.addEventListener('pointermove',event=>{
      if(!pending||event.pointerId!==pending.pointerId)return;
      if(!pending.active&&Math.hypot(event.clientX-pending.startX,event.clientY-pending.startY)<5)return;
      if(!pending.active){pending.active=true;dragging=pending;root.dataset.dragging='true';button.classList.add('dragging');}
      pending.clientX=event.clientX;pending.clientY=event.clientY;showDragPreview();
      if(!pending.frame)pending.frame=requestAnimationFrame(autoScrollDrag);
    });
    button.addEventListener('pointerup',event=>{
      if(!pending||event.pointerId!==pending.pointerId)return;
      const moved=pending.active;
      if(moved){suppressClick=true;event.preventDefault();setTimeout(()=>{suppressClick=false;},0);}
      finish(moved);
    });
    button.addEventListener('pointercancel',()=>finish(false));
    button.addEventListener('lostpointercapture',()=>finish(false));
    button.addEventListener('click',event=>{if(suppressClick){event.preventDefault();event.stopImmediatePropagation();suppressClick=false;}},true);
  }
  for(let day=0;day<dayCount;day++){
    const column=el('div',null,'calendar-day');column.style.height=`${height}px`;column.dataset.day=day;
    for(const tick of ticks){const rule=el('div',null,'calendar-rule');rule.style.top=`${(tick-gridStart)*pixelsPerMinute}px`;column.append(rule);}
    const events=valid.filter(v=>v.day===day).sort((a,b)=>a.startMinute-b.startMinute),lanes=[];let group=[],groupEnd=-1;
    function placeGroup(){const count=Math.max(1,...group.map(v=>v.lane+1));for(const value of group){
      const matches=recordingMatches(value,week,values),occurrence=options.classes?.find(c=>c.index===value.index),button=el('button',null,'calendar-event'+(matches.length?' has-recording':'')+(occurrence?' '+occurrence.status+'-class':''));button.type='button';button.dataset.course=value.course.toUpperCase();button.dataset.color=courseColor(value.course);button.dataset.recordingCount=matches.length;
      button.style.backgroundColor=courseColor(value.course);button.style.top=`${(value.startMinute-gridStart)*pixelsPerMinute+2}px`;button.style.height=`${Math.max(24,(value.endMinute-value.startMinute)*pixelsPerMinute-4)}px`;button.style.left=`calc(${value.lane/count*100}% + 3px)`;button.style.width=`calc(${100/count}% - 6px)`;
      if(value.endMinute-value.startMinute<=45)button.classList.add('compact-event');
      button.append(el('strong',value.course.toUpperCase()),el('span',`${value.start}–${value.end}`));
      if(matches.length)button.append(el('small',`● ${matches.length} recording${matches.length===1?'':'s'}`,'recording-mark'));
      button.setAttribute('aria-label',`${value.course}, ${days[value.day]}, ${value.start} to ${value.end}${matches.length?`, ${matches.length} matched recordings`:''}. ${options.onAdd?'Edit class':'View recordings'}. Drag to move this weekly class.`);
      if(options.onMove)enableClassMove(button,value);
      button.onclick=()=>options.onEdit?.(value,button);column.append(button);
    }group=[];lanes.length=0;}
    for(const event of events){if(event.startMinute>=groupEnd&&group.length)placeGroup();let lane=lanes.findIndex(end=>end<=event.startMinute);if(lane<0)lane=lanes.length;lanes[lane]=event.endMinute;event.lane=lane;group.push(event);groupEnd=Math.max(event.endMinute,...group.map(v=>v.endMinute));}placeGroup();
    if(options.onAdd)column.ondblclick=event=>{if(event.target.closest('.calendar-event'))return;const minute=Math.max(0,Math.min(1410,Math.round((gridStart+(event.clientY-column.getBoundingClientRect().top)/pixelsPerMinute)/30)*30));options.onAdd({course:'',day,start:clockValue(minute),end:clockValue(Math.min(1439,minute+60))},column);};
    if(options.now&&options.classes?.some(c=>c.day===day&&c.date===options.now.date)&&options.now.minute>=gridStart&&options.now.minute<=gridEnd){const line=el('div',null,'calendar-now');line.style.top=`${(options.now.minute-gridStart)*pixelsPerMinute}px`;line.setAttribute('aria-label','Current time '+clockValue(options.now.minute));column.append(line);}
    body.append(column);
  }
  scroll.append(head,body);root.append(scroll);
  if(scroll.clientHeight){scroll.scrollTop=position?position.top:Math.max(0,(first-75-gridStart)*pixelsPerMinute);if(position)scroll.scrollLeft=position.left;scroll.dataset.positionInitialized='true';}
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

const $ = (id) => document.getElementById(id);
const days = ['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday'];
let state, token, filter = 'all', editing = null, setupLoaded = false, lastRendered = '';
const settingsWindow = new URLSearchParams(location.search).has('settings');
let activeView='home';
function el(tag, text, cls) { const n = document.createElement(tag); if (text != null) n.textContent = text; if (cls) n.className = cls; return n; }
function notice(message, error = false) { $('notice').textContent = message; $('notice').className = error ? 'error' : ''; $('notice').hidden = !message; }
async function request(path, data = {}) {
  const r = await fetch(path, {method:'POST', headers:{'Content-Type':'application/json','X-App-Token':token},body:JSON.stringify(data)});
  const result = await r.json(); if (!r.ok) throw new Error(result.error || 'Request failed.'); return result;
}
async function action(path, data, message) {
  try { await request(path,data); if(message) notice(message); await refresh(); return true; }
  catch(e) { notice(e.message,true); return false; }
}
function view(name) {
  if(settingsWindow||state?.permissions?.recordings!=='granted')return;
  activeView=name;
  for(const n of ['home','setup','recordings','connection']) $(n+'-view').hidden = n !== name;
  document.querySelectorAll('.tab').forEach(b => { b.classList.toggle('active',b.dataset.view===name); b.setAttribute('aria-pressed',String(b.dataset.view===name)); });
  if(name==='setup')window.renderTimetable?.();
  if(state&&!state.job.busy&&!state.job.error)notice('');
}
document.querySelectorAll('.tab').forEach(b => b.onclick=()=>{if(b.dataset.view==='recordings')window.recordingScope=null;view(b.dataset.view);if(b.dataset.view==='recordings')renderRecords();});
$('open-setup').onclick=()=>view('setup');
function slot(value = {course:'',day:0,start:'09:00',end:'10:00'}) {
  const row=el('div',null,'slot');
  for(const [key,label,type] of [['course','Course','text'],['day','Day','select'],['start','Starts','time'],['end','Ends','time']]) {
    const l=el('label',label), input=el(type==='select'?'select':'input');
    if(type==='select'){const prompt=el('option','Choose day');prompt.value='';prompt.disabled=true;input.append(prompt);days.forEach((d,i)=>{const o=el('option',d);o.value=i;input.append(o);});} else input.type=type;
    input.value=value[key]??''; input.dataset.key=key; input.required=true; if(key==='course')input.maxLength=40;
    l.append(input);row.append(l);
  }
  const remove=el('button','×','icon-button');remove.type='button';remove.setAttribute('aria-label','Remove lecture time');remove.onclick=()=>{row.remove();window.renderTimetable?.();};row.append(remove);$('lecture-slots').append(row);window.renderTimetable?.();return row;
}
$('add-slot').onclick=()=>slot();
$('import-timetable').onclick=()=>$('timetable-image').click();
$('timetable-image').onchange=async()=>{
  const file=$('timetable-image').files[0];if(!file)return;
  const status=$('timetable-import-status');status.hidden=false;
  if(file.size>20000000){status.textContent='Choose an image smaller than 20 MB.';return;}
  $('import-timetable').disabled=true;status.textContent='Reading timetable photo…';
  try{
    const content=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(String(reader.result).split(',')[1]);reader.onerror=()=>reject(Error('Could not open this photo.'));reader.readAsDataURL(file);});
    const data=await request('/api/timetable/photo',{content});
    const existing=new Set([...document.querySelectorAll('.slot')].map(r=>JSON.stringify([...r.querySelectorAll('[data-key]')].map(i=>i.value))));let added=0;
    for(const draft of data.slots){const key=JSON.stringify([draft.course,draft.day==null?'':String(draft.day),draft.start,draft.end]);if(!existing.has(key)){slot(draft);existing.add(key);added++;}}
    status.replaceChildren(el('p',added?`${added} classes imported. Review before saving.`:'No new classes found.'));
    if(data.warnings?.length){const list=el('ul');data.warnings.forEach(w=>list.append(el('li',w)));status.append(list);}
    $('timetable-detected').hidden=!data.text;$('timetable-text').textContent=data.text||'';
  }catch(e){status.textContent=e.message;}
  finally{$('import-timetable').disabled=false;$('timetable-image').value='';}
};
$('setup-form').onsubmit=async e=>{
  e.preventDefault();
  const lectures=[...document.querySelectorAll('.slot')].map(row=>Object.fromEntries([...row.querySelectorAll('[data-key]')].map(n=>[n.dataset.key,n.dataset.key==='day'?Number(n.value):n.value])));
  const cfg={...state.config,week_one:$('week-one').value,semester_weeks:Number($('semester-weeks').value),timezone:$('timezone').value.trim(),tolerance_minutes:Number($('tolerance').value),recordings_folder:$('folder').value,notebook_prefix:$('prefix').value,auto_sync:$('auto-sync').checked,lectures};
  if(!lectures.length){notice('Add at least one class.',true);return;}
  if(!cfg.week_one){const now=new Date();now.setDate(now.getDate()-(now.getDay()+6)%7);cfg.week_one=`${now.getFullYear()}-${String(now.getMonth()+1).padStart(2,'0')}-${String(now.getDate()).padStart(2,'0')}`;$('week-one').value=cfg.week_one;}
  const invalid=[...document.querySelectorAll('.slot')].find(r=>[...r.querySelectorAll('[data-key]')].some(i=>!i.value)||r.querySelector('[data-key="start"]').value>=r.querySelector('[data-key="end"]').value);
  if(invalid){notice('Complete the class day and times before saving.',true);window.editTimetableClass?.(invalid);return;}
  if(await action('/api/config',cfg,'Saved.')) view('recordings');
};
$('scan').onclick=()=>action('/api/scan',{},'Scanning your recordings…');
$('sync').onclick=()=>action('/api/sync',{},'Uploading…');
$('connection-shortcut').onclick=()=>view('connection');
let googleSignInFinishing=false;
window.finishGoogleSignIn=async()=>{
    if(googleSignInFinishing||$('google-account-dialog').open)return;
    await refresh();
    if(state?.auth?.status!=='signing_in')return;
    googleSignInFinishing=true;
    try{
      const {accounts}=await request('/api/login/accounts');
      if(!accounts.length)throw Error('Finish Google sign-in first.');
      if(accounts.length===1){await action('/api/login/complete',{email:accounts[0]});return;}
      const select=$('google-account');select.replaceChildren();
      for(const email of accounts){const option=el('option',email);option.value=email;select.append(option);}
      $('google-account-dialog').showModal();
    }catch(e){await action('/api/login/cancel',{});notice(e.message,true);}
    finally{googleSignInFinishing=false;}
};
$('login').onclick=async()=>{
  if(state?.auth?.status==='signing_in'&&state.auth.presentation==='managed')await action('/api/login/cancel',{});
  else if(state?.auth?.status==='signing_in'&&native){native.postMessage({action:'closeGoogleSignIn'});await window.finishGoogleSignIn();}
  else if(state?.auth?.status==='signing_in')await action('/api/login/complete',{});
  else await action('/api/login',{presentation:'managed'});
};
$('google-account-form').onsubmit=async event=>{event.preventDefault();if(await action('/api/login/complete',{email:$('google-account').value}))$('google-account-dialog').close();};
$('google-account-cancel').onclick=async()=>{$('google-account-dialog').close();await action('/api/login/cancel',{});};
$('settings-login').onclick=()=>$('login').click();
$('check-connection').onclick=()=>action('/api/connection',{},'Checking your NotebookLM connection…');
const native = window.webkit?.messageHandlers?.native;
if(native){
  document.querySelectorAll('.native-only').forEach(n=>n.hidden=false);
}
$('show-data').onclick=()=>native?.postMessage({action:'showData'});
document.querySelectorAll('.filter').forEach(b=>b.onclick=()=>{filter=b.dataset.filter;document.querySelectorAll('.filter').forEach(x=>x.classList.toggle('selected',x===b));renderRecords();});
function localInput(iso) {
  if(!iso)return '';
  const parts=new Intl.DateTimeFormat('en-CA',{timeZone:state.config.timezone,year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).formatToParts(new Date(iso));
  const p=Object.fromEntries(parts.map(p=>[p.type,p.value]));return `${p.year}-${p.month}-${p.day}T${p.hour}:${p.minute}`;
}
function review(row) {
  editing=row.id;$('review-name').textContent=row.display_name||row.name;$('review-date').value=localInput(row.recorded_at);$('review-course').value=row.route?.course||'';$('review-week').value=row.route?.week||row.week||'';$('review-dialog').showModal();
}
$('close-review').onclick=()=>$('review-dialog').close();
$('review-form').onsubmit=async e=>{e.preventDefault();if(await action('/api/review',{id:editing,course:$('review-course').value,week:Number($('review-week').value),recorded_at:$('review-date').value},'Assignment saved.'))$('review-dialog').close();};
const recordingAudio=document.createElement('audio');
recordingAudio.controls=true;recordingAudio.preload='metadata';recordingAudio.className='recording-audio';
let activeRecordingId=null;
function recordingRename(row,main){
  if(main.querySelector('.recording-rename'))return;
  const form=el('form',null,'recording-rename'),input=el('input'),save=el('button','Save','secondary'),cancel=el('button','Cancel','secondary');
  input.value=row.display_name||row.name;input.maxLength=160;input.required=true;input.setAttribute('aria-label','Recording name');save.type='submit';cancel.type='button';
  cancel.onclick=()=>{form.remove();main.querySelector('.recording-name').focus();};
  input.onkeydown=event=>{if(event.key==='Escape'){event.preventDefault();cancel.click();}};
  form.onsubmit=async event=>{event.preventDefault();save.disabled=true;if(!await action('/api/recordings/rename',{id:row.id,name:input.value}))save.disabled=false;};
  form.append(input,save,cancel);main.append(form);input.focus();input.select();
}
function renderRecordingQueue() {
  const records=state.recordings.filter(r=>window.recordingInScope?.(r)??true);
  const ready=records.filter(r=>r.status==='ready').length,review=records.filter(r=>r.status==='review').length;
  $('queue-description').textContent=records.length?`${ready} ready · ${review} need review`:'';
  $('scan').disabled=state.job.busy;$('sync').disabled=state.job.busy||!records.some(r=>r.status==='ready'&&r.route);
}
function renderRecords() {
  renderRecordingQueue();
  lastRendered=JSON.stringify([state.recordings,state.job.busy,filter]);
  const root=$('recording-list');root.replaceChildren();
  const records=state.recordings.filter(r=>(filter==='all'||r.status===filter)&&(window.recordingInScope?.(r)??true));
  if(activeRecordingId&&!records.some(r=>r.id===activeRecordingId)){recordingAudio.pause();activeRecordingId=null;recordingAudio.removeAttribute('src');recordingAudio.load();}
  if(!records.length){const empty=el('div',null,'empty'),tape=el('div',null,'empty-tape');tape.setAttribute('aria-hidden','true');for(let i=0;i<7;i++)tape.append(el('span'));empty.append(tape,el('h2',window.recordingScope?'No recordings for this class.':filter==='all'?'No recordings yet.':'No recordings in this view.'),el('p',window.recordingScope?'Choose All recordings to see the full library.':filter==='all'?'Scan recordings to begin.':''));root.append(empty);return;}
  const groups=new Map();
  for(const row of records){const label=row.week_label||(row.route?`Week ${row.route.week}`:'Unassigned week');if(!groups.has(label))groups.set(label,[]);groups.get(label).push(row);}
  for(const [label,group]of groups){
    const divider=el('div',null,'recording-week');divider.append(el('h2',label),el('span',`${group.length} ${group.length===1?'recording':'recordings'}`));divider.title=group[0].week_source||'';root.append(divider);
  for(const row of group){
    const item=el('article',null,'recording'),main=el('div'),dest=el('div'),status=el('div'),buttons=el('div',null,'row-actions');
    const name=el('div',row.display_name||row.name,'recording-name');name.tabIndex=-1;main.append(name);
    const when=row.recorded_at?new Intl.DateTimeFormat('en-GB',{timeZone:state.config.timezone,dateStyle:'medium',timeStyle:'short'}).format(new Date(row.recorded_at)):'Date needs review';
    const detail=el('small',`${when} · ${Math.max(1,Math.round(row.duration/60))} min · ${(row.size/1e6).toFixed(1)} MB`);detail.title=row.date_source||'';main.append(detail);
    const reason=row.error||row.reason;if(reason&&!reason.startsWith('Add week 1 and')&&!reason.startsWith('Matched by recording start time.'))main.append(el('small',reason,row.error?'error-text':''));
    if(row.route){const title=el(row.notebook_id?'a':'strong',row.route.title,'notebook-link');if(row.notebook_id){title.href='https://notebooklm.google.com/notebook/'+encodeURIComponent(row.notebook_id);title.target='_blank';title.rel='noopener noreferrer';}dest.append(title);dest.append(el('small',row.notebook_id?'Open notebook ↗':'Weekly notebook'));}else dest.append(el('small','Awaiting assignment'));
    const names={review:'Needs review',ready:'Ready',uploaded:'Uploaded',error:'Error',ignored:'Ignored',converting:'Converting…',uploading:'Uploading…'};status.append(el('span',names[row.status]||row.status,'badge '+row.status));
    const play=el('button',activeRecordingId===row.id&&!recordingAudio.paused?'Pause':'Play','secondary recording-play');play.setAttribute('aria-label',`Play ${row.display_name||row.name}`);
    const bindPlayer=()=>{recordingAudio.onplay=()=>{play.textContent='Pause';play.setAttribute('aria-label',`Pause ${row.display_name||row.name}`);};recordingAudio.onpause=()=>{play.textContent='Play';play.setAttribute('aria-label',`Play ${row.display_name||row.name}`);};recordingAudio.onerror=()=>notice('Could not play this recording. Check folder access and try again.',true);};
    play.onclick=async()=>{
      if(activeRecordingId===row.id&&!recordingAudio.paused){recordingAudio.pause();return;}
      if(activeRecordingId!==row.id){recordingAudio.pause();activeRecordingId=row.id;document.querySelectorAll('.recording-play').forEach(b=>b.textContent='Play');recordingAudio.src=`/api/recordings/audio/${encodeURIComponent(row.id)}?token=${encodeURIComponent(token)}`;}
      bindPlayer();main.append(recordingAudio);recordingAudio.setAttribute('aria-label',row.display_name||row.name);
      try{await recordingAudio.play();}catch(e){if(e.name!=='AbortError')notice('Could not play this recording. Check folder access and try again.',true);}
    };
    if(activeRecordingId===row.id){main.append(recordingAudio);bindPlayer();}
    const rename=el('button','Rename','secondary');rename.onclick=()=>recordingRename(row,main);buttons.append(play,rename);
    if(row.parts.length)status.append(el('small',`${row.parts.filter(p=>p.status==='done').length}/${row.parts.length} parts ready`));
    if(!['uploaded','converting','uploading'].includes(row.status)){
      const b=el('button',row.status==='error'?'Retry':'Review','secondary');b.disabled=state.job.busy;b.onclick=()=>row.status==='error'?action('/api/review',{id:row.id,action:'retry'},'Recording queued. Run Convert & upload to retry.'):review(row);buttons.append(b);
      if(!row.parts.length){const ignore=el('button','Skip','secondary');ignore.disabled=state.job.busy;ignore.onclick=()=>action('/api/review',{id:row.id,action:'ignore'},'Recording skipped. Use Review to include it again.');buttons.append(ignore);}
    }
    if(row.status==='uploaded'&&state.permissions?.photos_enabled){const photos=el('button','Photos','secondary home-photo-button');photos.disabled=state.job.busy;photos.onclick=()=>window.openClassPhotos?.(row.id);buttons.append(photos);}
    item.append(main,dest,status,buttons);root.append(item);
  }
  }
}
async function refresh() {
  try {
    const previousAuth=state?.auth?.status;
    const r=await fetch('/api/state');if(!r.ok)throw Error('Could not load app state.');state=await r.json();token=state.token;
    $('folder').value=state.config.recordings_folder;
    if(!setupLoaded){const c=state.config;for(const [id,key] of [['week-one','week_one'],['semester-weeks','semester_weeks'],['timezone','timezone'],['tolerance','tolerance_minutes'],['folder','recordings_folder'],['prefix','notebook_prefix']])$(id).value=c[key];$('auto-sync').checked=c.auto_sync;c.lectures.forEach(slot);setupLoaded=true;}
    $('count').textContent=state.recordings.length;
    renderRecordingQueue();
    $('activity').textContent=state.job.busy?state.job.message:(state.config.auto_sync?'AUTO SYNC / EVERY MINUTE':'MANUAL SYNC');
    $('source-label').textContent=state.config.recordings_folder.includes('com.apple.VoiceMemos')?'Voice Memos':'Audio folder';
    const auth=state.auth||{status:'idle',message:'Sign in to connect NotebookLM.'};
    const titles={connected:'Connected',checking:'Checking connection…',signing_in:'Waiting for Google sign-in',error:'Connection needs attention',idle:state.login_saved?'Session saved':'Not connected'};
    $('auth-title').textContent=titles[auth.status]||'Not connected';
    $('connection-label').textContent=auth.status==='connected'?'NotebookLM connected':auth.status==='checking'?'Checking NotebookLM…':auth.status==='signing_in'?'Signing in…':state.login_saved?'NotebookLM · session saved':'NotebookLM not connected';
    $('auth-indicator').className=auth.status;$('connection-light').className=auth.status;
    $('connection').textContent=!state.dependencies.notebooklm?'NotebookLM client is missing. Reinstall the Mac app.':!state.dependencies.ffmpeg?'Audio converter is missing. Reinstall the Mac app.':auth.status==='idle'&&state.login_saved?'A saved Google session was found. Check the connection before uploading.':auth.message;
    $('login').textContent=auth.status==='signing_in'?(auth.presentation==='managed'?'Cancel sign-in':'Finish sign-in'):'Sign in with Google ↗';
    if(auth.status==='connected'&&['signing_in','checking'].includes(previousAuth))native?.postMessage({action:'googleSignInConnected'});
    $('login').disabled=state.job.busy||auth.status==='checking';
    $('settings-login').textContent=$('login').textContent;$('settings-login').disabled=$('login').disabled;
    $('settings-google-status').textContent=auth.status==='error'?auth.message:$('auth-title').textContent;
    $('check-connection').disabled=state.job.busy||['signing_in','checking'].includes(auth.status);
    if(state.job.error)notice(state.job.error,true);else if(state.job.busy)notice(state.job.message);
    else if($('notice').textContent.startsWith('Uploading ')||$('notice').textContent.startsWith('Converting ')||$('notice').textContent.startsWith('Scanning '))notice(state.job.message);
    if(lastRendered!==JSON.stringify([state.recordings,state.job.busy,filter])){renderRecords();window.renderTimetable?.();}
    window.renderWorkflow?.(state);
    window.renderOnboarding?.();
  } catch(e){notice('Cannot reach the local tool. Restart it, then reload this page.',true);}
}
refresh();setInterval(refresh,2500);

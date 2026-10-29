let homeSignature='',workspaceReady=false,sourcePathLoaded=false,uploadStage='options';
window.uploadRecordingIds=[];
const permissionLabel={authorized:'Enabled',limited:'Selected photos only',notDetermined:'Optional',denied:'Off',restricted:'Restricted',unavailable:'Mac app required'};
function nativeAction(action){if(native)native.postMessage({action});else notice('Open the Mac app to manage system access.',true);}
window.refreshAccess=async()=>{if(token)await action('/api/permissions/refresh',{},'');};
$('voice-grant').onclick=()=>nativeAction('fullDiskAccess');
$('photos-grant').onclick=$('upload-photos-grant').onclick=()=>window.explainPhotos();
$('home-import').onclick=()=>view('setup');
$('source-folder').onclick=()=>{if(native)nativeAction('chooseFolder');else $('source-path-input').focus();};
window.openSettings=()=>{
  if(native&&!settingsWindow){nativeAction('settings');return;}
  if(settingsWindow)return;
  $('settings-content').prepend($('notice'));
  if(!$('settings-dialog').open)$('settings-dialog').showModal();
};
$('open-settings').onclick=$('gate-settings').onclick=window.openSettings;
$('settings-close').onclick=()=>$('settings-dialog').close();
$('settings-dialog').addEventListener('close',()=>{$('workspace-nav').after($('notice'));});
if(settingsWindow){
  document.body.classList.add('settings-window');
  $('settings-content').prepend($('notice'));
  document.querySelector('main').append($('settings-content'));
  $('settings-close').hidden=true;document.title='Settings';
}
$('source-path-form').onsubmit=async event=>{
  event.preventDefault();const path=$('source-path-input').value.trim();
  if(!path){$('source-path-input').setCustomValidity('Enter a recordings folder path.');$('source-path-input').reportValidity();return;}
  $('source-path-save').disabled=true;
  try{if(await action('/api/config',{...state.config,recordings_folder:path},'Recordings folder saved. Scan recordings to find exported audio.')){$('folder').value=path;await window.refreshAccess();}}
  finally{$('source-path-save').disabled=!!state.job.busy;}
};
$('source-path-input').oninput=()=>$('source-path-input').setCustomValidity('');
window.voiceNotebookFolderChosen=path=>{$('source-path-input').value=path;$('source-path-input').focus();notice('Folder selected. Choose Save Folder to use it.');};
function openUploadFlow(ids=null,review=false){
  window.uploadRecordingIds=ids||state.recordings.filter(r=>r.status==='ready'&&r.route&&window.recordingInScope(r)).map(r=>r.id);
  uploadStage=review?'review':'options';$('include-photos').checked=false;
  if(!$('upload-dialog').open)$('upload-dialog').showModal();renderUpload();
}
window.openClassPhotos=id=>openUploadFlow([id],true);
$('sync').onclick=()=>openUploadFlow();
$('upload-close').onclick=()=>$('upload-dialog').close();
$('upload-start').onclick=async()=>{uploadStage='running';renderUpload();if(!await action('/api/sync',{include_photos:$('include-photos').checked,recording_ids:window.uploadRecordingIds},'')){uploadStage='options';renderUpload();}};
function scopedPhotos(){const ids=new Set(window.uploadRecordingIds);return (state.photos||[]).filter(p=>(p.recording_ids||[]).some(id=>ids.has(id)));}
window.scopedUploadPhotos=scopedPhotos;
function renderUpload(){
  if(!$('upload-dialog').open||!state)return;
  const allowed=!!state.permissions?.photos_enabled,busy=state.job.busy;
  if(uploadStage==='running'&&['audio','photo_review','complete'].includes(state.upload_batch?.stage))window.uploadRecordingIds=state.upload_batch.recording_ids;
  $('include-photos').disabled=!allowed;$('upload-enable').hidden=allowed;
  if(!allowed)$('include-photos').checked=false;
  $('upload-summary').textContent=`${window.uploadRecordingIds.length} recording${window.uploadRecordingIds.length===1?'':'s'} → weekly notebooks`;
  if(['running','photo_upload'].includes(uploadStage)&&!busy)uploadStage=state.upload_batch?.stage==='photo_review'?'review':'complete';
  $('upload-title').textContent=uploadStage==='review'?'Review class photos':'Upload recordings';
  $('upload-options').hidden=uploadStage!=='options';$('upload-progress').hidden=uploadStage==='options';
  $('upload-progress').textContent=busy?state.job.message:state.job.error||state.upload_batch?.photo_error||(uploadStage==='review'?'Audio uploaded. Choose which photos to include.':'Upload finished.');
  $('upload-photo-review').hidden=!['review','photo_upload'].includes(uploadStage);
  if(!$('upload-photo-review').hidden)window.renderClassPhotos?.(state);
}
window.beginPhotoUpload=()=>{uploadStage='photo_upload';renderUpload();};
function openClassRecordings(value){view('recordings');const matches=recordingMatches(value,state.overview.week,state.config.lectures);window.recordingScope=new Set(matches.map(r=>r.id));renderRecords();if(!matches.length)notice('No recording matched this class yet.');}
window.recordingInScope=recording=>!window.recordingScope||window.recordingScope.has(recording.id);
document.querySelectorAll('.filter').forEach(button=>button.addEventListener('click',()=>{window.recordingScope=null;renderRecords();}));
window.renderWorkflow=()=>{
  if(!state)return;
  const permissions=state.permissions||{},overview=state.overview||{};
  const isVoiceMemos=state.config.recordings_folder.includes('com.apple.VoiceMemos');
  $('voice-access-state').textContent=!isVoiceMemos?'Using an audio folder':permissions.recordings==='granted'?'Connected':permissions.recordings==='missing'?'Choose a folder':'Access needed';
  $('voice-grant').hidden=permissions.recordings==='granted';$('voice-grant').disabled=!native;
  $('photos-access-state').textContent=permissionLabel[permissions.photos]||'Optional';
  $('photos-grant').textContent=permissions.photos_enabled?'Photos settings ↗':permissions.photos==='denied'?'Open settings':'Enable Photos';
  $('photos-grant').disabled=!native;
  $('access-summary').textContent=permissions.recordings==='granted'?(isVoiceMemos?'Voice Memos connected':'Audio folder connected'):permissions.recordings==='missing'?'Folder not found':'Access needed';
  $('source-path-save').disabled=!!state.job.busy;
  if(!sourcePathLoaded){$('source-path-input').value=state.config.recordings_folder;sourcePathLoaded=true;}
  const ready=permissions.recordings==='granted';
  $('workspace-nav').hidden=settingsWindow||!ready;
  $('connection-shortcut').hidden=settingsWindow||!ready;
  $('access-gate').hidden=settingsWindow||ready;
  $('access-gate-status').textContent=permissions.recordings==='missing'?'The selected recordings folder could not be found.':!ready?'Recordings access is needed to continue.':'';
  document.querySelector('footer').hidden=settingsWindow||!ready;
  if(!ready||settingsWindow){for(const name of ['home','setup','recordings','connection'])$(name+'-view').hidden=true;}
  else if(!workspaceReady)view(activeView);
  workspaceReady=ready;
  $('home-import').textContent=state.config.lectures.length?'Edit timetable':'Set up timetable';
  $('home-title').textContent=overview.week?`Week ${overview.week}`:'This week';
  const displayTime=iso=>new Intl.DateTimeFormat('en-GB',{timeZone:state.config.timezone,hour:'2-digit',minute:'2-digit'}).format(new Date(iso));
  $('home-current').textContent=overview.current?`Now · ${overview.current.course} until ${displayTime(overview.current.ends_at)}`:overview.next?`Next · ${overview.next.course} · ${new Intl.DateTimeFormat('en-GB',{timeZone:state.config.timezone,weekday:'short'}).format(new Date(overview.next.starts_at))} ${displayTime(overview.next.starts_at)}`:overview.week?'No more classes this week.':'';
  $('home-coverage').textContent=overview.past_count?`${overview.matched_count} of ${overview.past_count} past classes matched`:overview.week?'No completed classes yet.':'';
  $('home-captured').textContent=overview.coverage_percent==null?'':`${overview.coverage_percent}% audio coverage`;
  const signature=JSON.stringify([state.config.lectures,state.config.week_one,overview.week,overview.classes,state.recordings,overview.now?.slice(0,16)]);
  if(signature!==homeSignature){homeSignature=signature;
    if(overview.week&&state.config.lectures.length){const parts=Object.fromEntries(new Intl.DateTimeFormat('en-CA',{timeZone:state.config.timezone,year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).formatToParts(new Date(overview.now)).map(p=>[p.type,p.value]));drawWeeklyCalendar($('home-calendar'),state.config.lectures,{week:overview.week,weekOne:state.config.week_one,classes:overview.classes,now:{date:`${parts.year}-${parts.month}-${parts.day}`,minute:Number(parts.hour)*60+Number(parts.minute)},onEdit:openClassRecordings});}
    else{const empty=el('div',null,'home-empty');empty.append(el('p',overview.season==='upcoming'?'Your semester hasn’t started yet.':overview.season==='ended'?'Your semester has ended.':'Add your timetable to see this week.'));$('home-calendar').replaceChildren(empty);}
  }
  renderUpload();
};
window.addEventListener('resize',()=>{homeSignature='';window.renderWorkflow();});
if(typeof state!=='undefined'&&state)window.renderWorkflow();

(() => {
  let step=0;
  const steps=[
    {title:'Your lectures. In order.',copy:'Connect recordings, add your timetable, and send each lecture to its weekly NotebookLM notebook.',action:'Connect recordings…'},
    {title:'One notebook. One course. One week.',copy:'Sign in with Google. Two EE221 recordings in week 3 both go to EE221 w3. Long recordings are split automatically.',action:'Connect NotebookLM…'},
    {title:'Bring your timetable.',copy:'Import a photo, review the detected classes, and save. You can edit every class on the calendar.',action:'Add timetable…'}
  ];
  function show(){
    const s=steps[step];$('onboarding-step').textContent=`${step+1} / ${steps.length}`;
    $('onboarding-title').textContent=s.title;$('onboarding-copy').textContent=s.copy;
    $('onboarding-action').textContent=s.action;$('onboarding-back').hidden=step===0;
    $('onboarding-next').textContent=step===2?'Finish':'Continue';
    const connected=state?.permissions?.recordings==='granted';
    $('onboarding-status').textContent=step===0?(connected?'Recordings connected.':'Choose Voice Memos access or an exported-audio folder.'):step===1?(state?.auth?.status==='connected'?'NotebookLM connected.':'Sign-in can also be completed later.'):(state?.config?.lectures.length?'Timetable saved.':'Review and save the photo import before matching recordings.');
  }
  window.startOnboarding=()=>{step=0;show();if(!$('onboarding-dialog').open)$('onboarding-dialog').showModal();};
  $('continue-onboarding').onclick=()=>{show();$('onboarding-dialog').showModal();};
  window.explainPhotos=()=>{if(!$('photos-explanation').open)$('photos-explanation').showModal();};
  $('photos-not-now').onclick=()=>$('photos-explanation').close();
  $('photos-continue').onclick=()=>{$('photos-explanation').close();nativeAction('photosAccess');};
  $('restart-onboarding').onclick=()=>{if($('settings-dialog').open)$('settings-dialog').close();window.startOnboarding();};
  $('onboarding-back').onclick=()=>{step=Math.max(0,step-1);show();};
  async function finish(){
    if(!state||!await action('/api/config',{...state.config,onboarding_complete:true},''))return;
    $('onboarding-dialog').close();
  }
  $('onboarding-close').onclick=finish;
  $('onboarding-dialog').addEventListener('cancel',event=>{event.preventDefault();finish();});
  $('onboarding-next').onclick=()=>{if(step===2)finish();else{step++;show();}};
  $('onboarding-action').onclick=()=>{
    if(step===2&&state.permissions?.recordings!=='granted'){$('onboarding-status').textContent='Connect a recordings folder first, in Settings.';return;}
    $('onboarding-dialog').close();
    if(step===0)window.openSettings();
    else if(step===1){if(state.permissions?.recordings==='granted')view('connection');$('login').click();}
    else view('setup');
    if(step<2)step++;
  };
  window.renderOnboarding=()=>{
    $('continue-onboarding').hidden=settingsWindow||!!state.config.onboarding_complete||!!state.config.lectures.length;
    if($('onboarding-dialog').open)show();
  };
  if(state)window.renderOnboarding();
})();

(() => {
  let rendered = '', photoIndex = 0;
  window.resetPhotoReview = () => { photoIndex = 0; rendered = ''; };
  const labels = {review:'Needs approval',approved:'Approved',skipped:'Skipped',uploaded:'Uploaded',uploading:'Uploading…',error:'Needs attention'};
  $('photo-scan').onclick = () => action('/api/photos/scan', {recording_ids:window.uploadRecordingIds}, 'Finding photos from this class…');
  $('photo-sync').onclick = () => {window.beginPhotoUpload?.();return action('/api/photos/sync', {ids:(window.scopedUploadPhotos?.()||[]).filter(p=>p.status==='approved').map(p=>p.id)}, 'Uploading approved class photos…');};
  $('photo-preview-close').onclick = () => $('photo-preview').close();
  window.renderClassPhotos = state => {
    const photos = state.photos_available?(window.scopedUploadPhotos?.()||[]):[], busy = state.job.busy;
    const approved = photos.filter(p => p.status === 'approved').length;
    $('photo-sync').disabled = busy || !approved;
    $('photo-sync').textContent = approved ? `Upload ${approved} approved photo${approved === 1 ? '' : 's'} ↗` : 'Upload approved photos ↗';
    $('photo-scan').disabled = busy || !state.photos_available;
    $('photo-access').textContent = state.photos_available
      ? (photos.length ? '' : 'Find class photos to review.')
      : 'Enable optional Photos access on the home screen, or continue with audio only.';
    $('photo-summary').textContent = photos.length ? `${photos.filter(p => p.status === 'review').length} need approval · ${approved} approved · ${photos.filter(p => p.status === 'uploaded').length} uploaded` : '';
    photoIndex = Math.max(0,Math.min(photoIndex,photos.length-1));
    const key = JSON.stringify([photos,busy,state.config.timezone,photoIndex]);
    if (rendered === key) return;
    rendered = key;
    const root = $('photo-list');
    root.replaceChildren();
    if(!photos.length){root.append(el('p',state.photos_available?'No matching photos found.':'You can continue with audio only.','hint'));return;}
    for (const photo of [photos[photoIndex]]) {
      const item = el('article', null, 'class-photo');
      const when = new Intl.DateTimeFormat('en-GB',{timeZone:state.config.timezone,dateStyle:'medium',timeStyle:'short'}).format(new Date(photo.captured_at));
      const preview = el('button', null, 'photo-open');
      preview.setAttribute('aria-label',`Enlarge photo from ${when}`);
      const image = el('img'); image.src = `/api/photos/image/${photo.id}`; image.alt = `Class photo taken ${when}`; image.loading = 'lazy';
      const hint = el('span', 'Enlarge to review ↗'); preview.append(image,hint);
      preview.onclick = () => {
        $('photo-preview-image').src = image.src;
        $('photo-preview-caption').textContent = `${when} · ${photo.title || 'Choose a matching notebook before approval'}`;
        $('photo-preview').showModal();
      };
      const visual = el('div',null,'photo-visual'), navigation = el('div',null,'photo-navigation');
      navigation.append(el('span',`Photo ${photoIndex+1} of ${photos.length} · ${when}`));
      const arrows=el('div',null,'photo-arrows');
      for(const [direction,delta,symbol] of [['Previous',-1,'‹'],['Next',1,'›']]){const arrow=el('button',symbol);arrow.type='button';arrow.setAttribute('aria-label',`${direction} photo`);arrow.disabled=photoIndex+delta<0||photoIndex+delta>=photos.length;arrow.onclick=()=>{photoIndex+=delta;window.renderClassPhotos(state);};arrows.append(arrow);}
      navigation.append(arrows);visual.append(preview,navigation);
      const details = el('div', null, 'photo-details');
      const descriptions={review:'Check the photo and choose the notebook. Only approved photos will be uploaded.',uploaded:'This photo was uploaded to its class notebook.',approved:'This photo is approved and ready to upload.',skipped:'This photo was skipped. You can review it again.',error:'Review the error before retrying this photo.'};
      details.append(el('h2',photo.status==='review'?'Include this photo?':labels[photo.status]||photo.status),el('p',descriptions[photo.status]||'Updating this photo…','hint'),el('span',labels[photo.status] || photo.status,'badge '+photo.status));
      let destination;
      if (photo.status === 'review') {
        const label = el('label','Notebook'); destination = el('select');
        destination.setAttribute('aria-label',`Notebook for photo from ${when}`);
        const empty = el('option','Choose a class notebook');empty.value='';destination.append(empty);
        for (const choice of photo.destinations) { const option=el('option',choice.title); option.value=choice.notebook_id;destination.append(option); }
        if (photo.destinations.length === 1) destination.value=photo.destinations[0].notebook_id;
        label.append(destination);details.append(label);
      } else if (photo.notebook_id) {
        const link=el('a',photo.title,'notebook-link');link.href=`https://notebooklm.google.com/notebook/${encodeURIComponent(photo.notebook_id)}`;link.target='_blank';link.rel='noopener noreferrer';details.append(link);
      }
      if (photo.error) details.append(el('p',photo.error,'error-text'));
      const actions=el('div',null,'actions photo-actions');
      const button=(title,command,cls='secondary')=>{const b=el('button',title,cls);b.disabled=busy;b.onclick=()=>action('/api/photos/review',{id:photo.id,action:command,notebook_id:destination?.value},command==='approve'?'Photo approved. Choose Upload approved photos when ready.':'Photo review saved.');actions.append(b);return b;};
      if (photo.status === 'review') {
        const approve=button('Approve photo','approve','primary');approve.disabled=busy||!destination.value;
        destination.onchange=()=>approve.disabled=busy||!destination.value;
        button('Skip','skip');
      } else if (photo.status === 'error') button('Retry upload','retry');
      else if (['approved','skipped'].includes(photo.status) && !photo.attempted) button(photo.status === 'approved'?'Undo approval':'Review again','review');
      details.append(actions); item.append(visual,details);root.append(item);
    }
  };
  if (state) window.renderClassPhotos(state);
})();

(() => {
  const selectedDialog = $('selected-photos-dialog'), selectedInput = $('selected-photos-input');
  const selectedNotebook = $('selected-photos-notebook'), selectedMessage = $('selected-photos-message');
  let selectedFiles = [], selectedURLs = [], selectedBusy = false, notebookSignature = '';
  function clearSelected(resetInput = true) {
    selectedURLs.forEach(URL.revokeObjectURL); selectedURLs = []; selectedFiles = [];
    if (resetInput) selectedInput.value = ''; $('selected-photos-preview').replaceChildren();
  }
  function selectedControls() {
    $('selected-photos-upload').disabled = selectedBusy || !!state?.job?.busy || !selectedFiles.length || !selectedNotebook.value;
    $('selected-photos-choose').disabled = selectedBusy || !!state?.job?.busy;
    selectedNotebook.disabled = selectedBusy || !!state?.job?.busy;
  }
  $('add-gallery-photos').onclick = () => { selectedMessage.textContent = ''; window.renderSelectedPhotos(state); selectedDialog.showModal(); };
  $('selected-photos-close').onclick = () => selectedDialog.close();
  selectedDialog.addEventListener('cancel', event => { if (selectedBusy) event.preventDefault(); });
  selectedDialog.addEventListener('close', () => clearSelected());
  $('selected-photos-choose').onclick = () => selectedInput.click();
  selectedNotebook.onchange = selectedControls;
  selectedInput.onchange = () => {
    const files = Array.from(selectedInput.files); clearSelected(false); selectedFiles = files;
    for (const file of files) {
      const url = URL.createObjectURL(file); selectedURLs.push(url);
      const image = el('img'); image.src = url; image.alt = file.name || 'Selected photo';
      $('selected-photos-preview').append(image);
    }
    selectedMessage.textContent = files.length ? `${files.length} photo${files.length === 1 ? '' : 's'} selected. Review them before adding.` : '';
    selectedControls();
  };
  async function jpegData(file) {
    const url = URL.createObjectURL(file);
    try {
      const image = new Image(); image.src = url; await image.decode();
      const canvas = document.createElement('canvas'); canvas.width = image.naturalWidth; canvas.height = image.naturalHeight;
      if (!canvas.width || !canvas.height) throw Error('Could not read this photo.');
      const context = canvas.getContext('2d'); if (!context) throw Error('Could not prepare this photo.');
      context.fillStyle = '#fff'; context.fillRect(0, 0, canvas.width, canvas.height); context.drawImage(image, 0, 0);
      const data = canvas.toDataURL('image/jpeg', 0.92);
      if (data.length > 26600000) throw Error('Photo is too large. Choose a smaller image.');
      return data;
    } finally { URL.revokeObjectURL(url); }
  }
  $('selected-photos-upload').onclick = async () => {
    if (selectedBusy || !selectedFiles.length || !selectedNotebook.value) return;
    selectedBusy = true; $('selected-photos-close').disabled = true; selectedControls(); const ids = [];
    try {
      for (const file of selectedFiles) {
        selectedMessage.textContent = `Preparing ${ids.length + 1} of ${selectedFiles.length}…`;
        const content = await jpegData(file);
        const result = await request('/api/photos/selected', {content, notebook_id: selectedNotebook.value}); ids.push(result.id);
      }
      clearSelected();
      await request('/api/photos/sync', {ids});
      selectedMessage.textContent = 'Uploading selected photos. Check their status below.';
    } catch (error) {
      if (ids.length) {
        clearSelected();
        selectedMessage.textContent = `${error.message} ${ids.length} photo(s) were saved; use Upload saved photos below.`;
      } else selectedMessage.textContent = error.message;
    } finally { selectedBusy = false; $('selected-photos-close').disabled = false; selectedControls(); await refresh(); }
  };
  window.renderSelectedPhotos = current => {
    if (!current) return;
    const signature = JSON.stringify(current.notebook_catalog || []);
    if (signature !== notebookSignature) {
      const old = selectedNotebook.value; notebookSignature = signature;
      selectedNotebook.replaceChildren();
      for (const item of current.notebook_catalog || []) { const option = el('option', item.title?.trim() || 'Untitled notebook'); option.value = item.id; selectedNotebook.append(option); }
      selectedNotebook.value = old;
    }
    selectedControls();
    if (!selectedDialog.open) return;
    const root = $('selected-photos-history'); root.replaceChildren();
    for (const photo of (current.photos || []).filter(p => p.label === 'Selected photo').slice(0, 20)) {
      const row = el('div', null, 'selected-photo-row'), image = el('img'); image.src = `/api/photos/image/${photo.id}`; image.alt = 'Selected photo';
      const description = el('div'); description.append(el('strong', photo.title), el('p', photo.error || ({approved:'Ready to upload', uploading:'Uploading…', uploaded:'Uploaded', error:'Upload needs attention'}[photo.status] || photo.status), photo.error ? 'error-text' : 'hint'));
      row.append(image, description);
      if (['approved', 'error'].includes(photo.status)) {
        const button = el('button', photo.status === 'error' ? 'Retry' : 'Upload saved photo', 'secondary'); button.disabled = selectedBusy || current.job.busy;
        button.onclick = async () => { if (photo.status === 'error' && !await action('/api/photos/review', {id:photo.id,action:'retry'}, '')) return; await action('/api/photos/sync', {ids:[photo.id]}, 'Uploading selected photo…'); };
        row.append(button);
      }
      root.append(row);
    }
  };
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

'use strict';
const $ = s => document.querySelector(s);
let podiumSeen=null;
const podiumLabels={1:'🥇 1ST',2:'🥈 2ND',3:'🥉 3RD'};
let account=null, currentPage='briefing', clockOffset=0, noteVersion=0, noteDirty=false, noteConflict=null;
let saveTask=null, pollBusy=false, noteTimer=null, viewVersion=0, activationToken=null, noteLoaded=false;
let registrationOpen=false;
const draftPrefix='zodiac_v2_draft:';
async function api(path, body){
  const controller=new AbortController(), timeout=setTimeout(()=>controller.abort(),15000);
  try{
    const response=await fetch('/api/'+path,{signal:controller.signal,credentials:'same-origin',cache:'no-store',headers:{'Content-Type':'application/json'},...(body!==undefined?{method:'POST',body:JSON.stringify(body)}:{})});
    let result;try{result=await response.json();}catch(_){throw new Error('Unexpected server response. Please retry or contact the organizer.');}
    if(!response.ok){const error=new Error(result.error||'Request failed.');error.status=response.status;error.result=result;throw error;}
    return result;
  }finally{clearTimeout(timeout);}
}
function message(error){return error.name==='AbortError'||error.message==='Failed to fetch'?'Connection interrupted. Please retry.':error.message;}
function notify(text){$('#toast').textContent=text;$('#toast').hidden=false;setTimeout(()=>$('#toast').hidden=true,6000);}
function authError(error){const box=$('#auth-error');box.textContent=message(error);box.hidden=false;try{box.scrollIntoView({block:'center'});}catch(_){}}
function elapsed(seconds){seconds=Math.max(0,Math.floor(seconds));return [Math.floor(seconds/3600),Math.floor(seconds/60)%60,seconds%60].map(n=>String(n).padStart(2,'0')).join(':');}
function authView(view){
  for(const name of ['register','login','token'])$('#'+name+'-form').hidden=name!==view;
  document.querySelectorAll('[data-auth]').forEach(button=>button.classList.toggle('active',button.dataset.auth===view));
  $('#auth-error').hidden=true;
}
document.querySelectorAll('[data-auth]').forEach(button=>button.onclick=()=>authView(button.dataset.auth));
function buildMembers(){
  const container=$('#member-fields'), old=[...container.querySelectorAll('fieldset')].map(field=>Object.fromEntries([...field.querySelectorAll('[data-field]')].map(input=>[input.dataset.field,input.value])));
  const team=$('#entry-kind').value==='team';$('#team-fields').hidden=!team;$('#team-name').required=team;
  const size=team?Number($('#team-size').value):1;container.replaceChildren();
  for(let i=0;i<size;i++){
    const field=document.createElement('fieldset');field.className='member-fieldset';
    const legend=document.createElement('legend');legend.textContent='INVESTIGATOR '+(i+1)+(i===0?' · YOU / CREATOR':'');field.append(legend);
    for(const [key,label] of [['name','FULL NAME'],['admission','ADMISSION NUMBER · 3–4 DIGITS'],['class_name','CLASS'],['section','SECTION']]){
      const id='member-'+i+'-'+key, lab=document.createElement('label');lab.htmlFor=id;lab.textContent=label;
      const input=document.createElement(key==='class_name'?'select':'input');input.id=id;input.dataset.field=key;input.required=true;
      if(key==='class_name')for(const val of ['',...Array.from({length:12},(_,j)=>String(j+1))]){const opt=document.createElement('option');opt.value=val;opt.textContent=val||'Select class';input.append(opt);}
      else{input.type='text';input.maxLength=key==='name'?70:key==='section'?3:4;input.autocomplete=key==='name'&&i===0?'name':'off';
        if(key==='admission'){input.inputMode='numeric';input.pattern='[0-9]{3,4}';input.minLength=3;input.oninput=()=>input.value=input.value.replace(/[^0-9]/g,'').slice(0,4);}
        if(key==='name')input.minLength=2;
        if(key==='section'){input.pattern='[A-Za-z]{1,3}';input.oninput=()=>input.value=input.value.replace(/[^a-z]/gi,'').toUpperCase();}}
      input.value=old[i]?.[key]||'';field.append(lab,input);
    }container.append(field);
  }
}
$('#entry-kind').onchange=buildMembers;$('#team-size').onchange=buildMembers;buildMembers();
async function submitForm(form, action){
  const button=form.querySelector('[type=submit]');button.disabled=true;$('#auth-error').hidden=true;
  try{await action();}catch(error){authError(error);}finally{button.disabled=false;}
}
$('#register-form').onsubmit=event=>{event.preventDefault();submitForm(event.currentTarget,async()=>{
  if($('#register-password').value!==$('#register-confirm').value)throw new Error('Passwords do not match.');
  const members=[...$('#member-fields').querySelectorAll('fieldset')].map(field=>Object.fromEntries([...field.querySelectorAll('[data-field]')].map(input=>[input.dataset.field,input.value])));
  const result=await api('register',{kind:$('#entry-kind').value,team_name:$('#team-name').value,members,password:$('#register-password').value});
  $('#register-form').reset();buildMembers();await enter(result);for(const invitation of result.invitations||[])showInvitation(invitation);
});};
$('#login-form').onsubmit=event=>{event.preventDefault();submitForm(event.currentTarget,async()=>{
  await api('login',{admission:$('#login-admission').value,password:$('#login-password').value});const me=await api('me');$('#login-form').reset();await enter(me);
});};
$('#token-form').onsubmit=event=>{event.preventDefault();submitForm(event.currentTarget,async()=>{
  if($('#token-password').value!==$('#token-confirm').value)throw new Error('Passwords do not match.');
  await api('token/complete',{token:activationToken,password:$('#token-password').value});activationToken=null;const me=await api('me');$('#token-form').reset();await enter(me);
});};
function draftKey(){return account?draftPrefix+account.entry.id+':'+account.student.admission:null;}
function persistDraft(){if(!noteDirty||!account)return;try{localStorage.setItem(draftKey(),JSON.stringify({body:$('#field-notes').value,version:noteVersion}));}catch(_){$('#notes-status').textContent='UNSAVED · KEEP THIS TAB OPEN';}}
function clearDraft(){try{localStorage.removeItem(draftKey());}catch(_){}}
function logoutView(){
  persistDraft();account=null;viewVersion++;noteLoaded=false;noteDirty=false;noteConflict=null;clearTimeout(noteTimer);
  document.body.classList.remove('workspace');$('#landing').hidden=false;$('#dashboard').hidden=true;$('#nav').hidden=true;
  $('#field-notes').value='';$('#field-notes').disabled=true;$('#invitation-list').replaceChildren();$('#entry-members').replaceChildren();$('#notes-conflict').hidden=true;
  $('#header-status').textContent='ARCHIVE OPEN';authView('login');
}
$('#logout').onclick=async()=>{
  if(noteDirty&&!confirm('You have unsaved notebook edits. A draft will stay on this browser. Log out anyway?'))return;
  try{await api('logout',{});logoutView();}catch(error){notify(message(error));}
};
function renderMembers(){
  $('#entry-title').textContent=account.entry.name+' · '+(account.entry.kind==='team'?'TEAM':'SOLO');
  $('#entry-members').replaceChildren();
  for(const member of account.members){const card=document.createElement('div');card.className='member-pill';card.textContent=`${member.name} · ${member.admission} · Class ${member.class_name}${member.section} · ${member.activated?'Active account':'Awaiting activation'}`;
    if(account.is_creator&&!member.activated){const button=document.createElement('button');button.className='outline';button.textContent='Create private activation link';button.onclick=async()=>{button.disabled=true;try{showInvitation(await api('invitations',{admission:member.admission}));}catch(error){notify(message(error));}finally{button.disabled=false;}};card.append(button);}
    $('#entry-members').append(card);
  }
}
function showInvitation(invitation){
  const member=account.members.find(m=>m.admission===invitation.admission), card=document.createElement('div');card.className='invitation';card.dataset.admission=invitation.admission;
  [...$('#invitation-list').children].filter(c=>c.dataset.admission===invitation.admission).forEach(c=>c.remove());
  const text=document.createElement('strong');text.textContent=`Private activation for ${member?.name||invitation.admission} (${invitation.admission})`;
  const input=document.createElement('input');input.readOnly=true;input.value=location.origin+'/#activate='+encodeURIComponent(invitation.token);input.setAttribute('aria-label','Private activation link');
  const info=document.createElement('p');info.className='form-help';info.textContent='Copy and send privately to this member only. Anyone holding this link can set their password. Creating a new link invalidates the previous one.';
  const copy=document.createElement('button');copy.className='outline';copy.textContent='Copy private link';copy.onclick=async()=>{try{await navigator.clipboard.writeText(input.value);notify('Private link copied. Share only with its named member.');}catch(_){input.select();notify('Select and copy the private link above.');}};
  card.append(text,input,copy,info);$('#invitation-list').append(card);
}
async function enter(result){
  persistDraft();podiumSeen=null;account=result;viewVersion++;const generation=viewVersion;clockOffset=result.server_time*1000-Date.now();noteLoaded=false;noteDirty=false;noteConflict=null;
  document.body.classList.add('workspace');$('#landing').hidden=true;$('#dashboard').hidden=false;$('#nav').hidden=false;
  $('#sidebar-name').textContent=result.student.name;$('#sidebar-initial').textContent=result.student.name.split(/\s+/).slice(0,2).map(n=>n[0]).join('').toUpperCase();
  $('#sidebar-class').textContent=`${result.entry.kind.toUpperCase()} · ${result.entry.name}`;$('#agent-id').textContent='#'+result.student.admission;
  $('#greeting').textContent=`${result.student.name} · ${result.entry.kind==='team'?'Team '+result.entry.name:'Solo investigator'} · One original clock, verified progress and cloud notes.`;
  $('#header-status').textContent='INVESTIGATOR ONLINE';$('#field-notes').value='';$('#field-notes').disabled=true;$('#notes-conflict').hidden=true;
  renderMembers();renderProgress(result);updateClock();page(currentPage);
  try{const notes=await api('notes');if(generation===viewVersion)loadInitialNotes(notes);}catch(error){$('#notes-status').textContent='NOT CONNECTED · RETRYING';}
  await refreshBoard();
  try{sessionStorage.removeItem('zodiac_return_to');}catch(_){}
  window.scrollTo({top:0,behavior:'instant'});
}
function renderProgress(result){
  if(account)account.finish=result.finish||null;
  const finish=result.finish;
  $('#own-progress').textContent=`${result.levels_accomplished||0} / 4 VERIFIED`+(finish?' · '+(podiumLabels[finish.podium_place]||'FINISHED'):'');
  $('#clock-caption').textContent=finish?'FINISHED · Timer stopped after all four levels':'Elapsed since solo / team registration';
  $('#mission-live').hidden=!!finish;
  if(finish)$('#header-status').textContent='ALL FOUR LEVELS VERIFIED';
  updateClock();
}
function page(next){if(!account)return;const titles={briefing:'Mission Briefing',objectives:'Mission Objectives',initial:'Initial Evidence',case:'Case overview',hunt:'Shared field notebook',board:'Investigator ledger'};currentPage=(titles[next]&&$('#page-'+next))?next:'case';for(const name of ['briefing','objectives','initial','case','hunt','board']){const section=$('#page-'+name);if(section)section.hidden=name!==currentPage;}document.querySelectorAll('[data-page]').forEach(button=>button.classList.toggle('active',button.dataset.page===currentPage));document.title=(titles[currentPage]||'Investigation workspace')+' — The Zodiac Seeker';}
document.querySelectorAll('[data-page]').forEach(button=>button.onclick=()=>page(button.dataset.page));
$('.brand').onclick=event=>{event.preventDefault();page('briefing');window.scrollTo({top:0,behavior:'smooth'});};$('.footer-brand').onclick=event=>{event.preventDefault();window.scrollTo({top:0,behavior:'smooth'});};
function updateClock(){if(!account)return;$('#timer').textContent=elapsed(account.finish?account.finish.elapsed_seconds:(Date.now()+clockOffset)/1000-account.entry.started);document.querySelectorAll('[data-started]').forEach(cell=>cell.textContent=elapsed(cell.dataset.finishedSeconds!==undefined?Number(cell.dataset.finishedSeconds):(Date.now()+clockOffset)/1000-Number(cell.dataset.started)));}
setInterval(updateClock,1000);
function td(value){const cell=document.createElement('td');cell.textContent=value;return cell;}
function renderPodium(winners){
  const previous=podiumSeen;podiumSeen=new Set(winners.map(w=>w.id));
  $('#podium-list').replaceChildren();
  for(const winner of winners){const card=document.createElement('div');card.className='podium-card';
    const badge=document.createElement('strong');badge.textContent=podiumLabels[winner.podium_place];
    const name=document.createElement('span');name.textContent=winner.name+' · '+winner.kind.toUpperCase();
    const time=document.createElement('small');time.textContent='All four verified · '+elapsed(winner.elapsed_seconds)+' · timer stopped';
    card.append(badge,name,time);$('#podium-list').append(card);
    if(previous&&!previous.has(winner.id))notify(`${podiumLabels[winner.podium_place]} FINISHER: ${winner.name} completed all four levels!`);
  }
  $('#podium-empty').hidden=winners.length>0;
}
async function refreshBoard(){
  if(!account)return;const generation=viewVersion;
  try{const result=await api('leaderboard');if(generation!==viewVersion)return;clockOffset=result.server_time*1000-Date.now();$('#total-agents').textContent=result.total;$('#active-agents').textContent=result.active;$('#board-body').replaceChildren();renderPodium(result.podium||[]);
    for(const row of result.entries){const tr=document.createElement('tr');const name=td(`${row.finish?.podium_place?podiumLabels[row.finish.podium_place]+' · ':''}${row.name} · ${row.kind.toUpperCase()}${row.id===account.entry.id?' · YOU':''}`);
      const members=td(row.members.map(m=>`${m.name} (${m.class_name}${m.section})`).join(' · '));const started=td(new Date(row.started*1000).toLocaleString());const clock=td(elapsed(row.finish?row.finish.elapsed_seconds:result.server_time-row.started));clock.dataset.started=row.started;if(row.finish)clock.dataset.finishedSeconds=row.finish.elapsed_seconds;
      const levels=td(`${row.levels_accomplished} / 4 · ${row.completed_levels.length?row.completed_levels.map(n=>'Level '+n+' completed').join(' · '):'No levels completed'}`);
      tr.append(name,members,started,clock,levels,td(row.finish?'FINISHED':row.last_seen>result.server_time-60?'ACTIVE':'AWAY'));$('#board-body').append(tr);
      if(row.id===account.entry.id)renderProgress(row);
    }$('#board-updated').textContent='Updated '+new Date().toLocaleTimeString()+' · First three by server-recorded finish order; all completed clocks stopped';$('#board-error').hidden=true;
  }catch(error){if(error.status===401){logoutView();notify('Please log in again.');}else{$('#board-error').textContent=message(error);$('#board-error').hidden=false;}}
}
function applyNotes(notes){noteVersion=notes.version;$('#field-notes').value=notes.body;noteLoaded=true;$('#field-notes').disabled=false;$('#notes-status').textContent='SAVED TO CLOUD';}
function showConflict(notes){noteConflict=notes;$('#remote-notes').value=notes.body;$('#notes-conflict').hidden=false;$('#notes-status').textContent='REVIEW CONCURRENT EDIT';persistDraft();}
function loadInitialNotes(notes){
  applyNotes(notes);let draft;try{draft=JSON.parse(localStorage.getItem(draftKey()));}catch(_){}
  if(draft&&typeof draft.body==='string'&&draft.body!==notes.body){$('#field-notes').value=draft.body;noteDirty=true;
    if(draft.version!==notes.version)showConflict(notes);else{$('#notes-status').textContent='RESTORED UNSAVED DRAFT';noteTimer=setTimeout(saveNotes,800);}
  }else clearDraft();
}
async function syncNotes(){
  if(!account||saveTask)return;const generation=viewVersion;
  try{const notes=await api('notes');if(generation!==viewVersion)return;
    if(!noteLoaded){loadInitialNotes(notes);return;}
    if(notes.version!==noteVersion){if(noteDirty)showConflict(notes);else applyNotes(notes);}
    else if(!noteDirty)$('#notes-status').textContent='SAVED TO CLOUD';
  }catch(error){if(error.status===401){logoutView();notify('Session ended. Log in again.');}else{$('#notes-status').textContent='OFFLINE · UNSAVED EDITS STAY HERE';persistDraft();}}
}
function saveNotes(){
  if(!account||!noteLoaded||!noteDirty||noteConflict)return saveTask||Promise.resolve();if(saveTask)return saveTask;
  const text=$('#field-notes').value, version=noteVersion, generation=viewVersion;
  $('#notes-status').textContent='SAVING…';
  saveTask=(async()=>{
    try{const result=await api('notes',{body:text,version});if(generation!==viewVersion)return;noteVersion=result.version;
      if($('#field-notes').value===text){noteDirty=false;clearDraft();$('#notes-status').textContent='SAVED TO CLOUD';}
      else{persistDraft();$('#notes-status').textContent='UNSAVED CHANGES';}
    }catch(error){if(generation!==viewVersion)return;if(error.status===409)showConflict(error.result.latest);else if(error.status===401){logoutView();notify('Session ended. Your unsaved draft stays on this browser.');}else{$('#notes-status').textContent='NOT SAVED · RETRY';persistDraft();}}
    finally{saveTask=null;if(account&&noteDirty&&!noteConflict)noteTimer=setTimeout(saveNotes,1800);}
  })();return saveTask;
}
$('#field-notes').oninput=()=>{noteDirty=true;persistDraft();$('#notes-status').textContent='UNSAVED CHANGES';clearTimeout(noteTimer);noteTimer=setTimeout(saveNotes,800);};
$('#save-notes').onclick=()=>{if(noteConflict)notify('Resolve the concurrent edit below first.');else saveNotes();};
$('#use-remote').onclick=()=>{if(!noteConflict)return;if(!confirm('Replace the editor text with the server version? Copy any local edits you want to keep first.'))return;applyNotes(noteConflict);noteDirty=false;noteConflict=null;clearDraft();$('#notes-conflict').hidden=true;};
$('#keep-local').onclick=()=>{if(!noteConflict)return;noteVersion=noteConflict.version;noteConflict=null;$('#notes-conflict').hidden=true;noteDirty=true;persistDraft();saveNotes();};
window.addEventListener('beforeunload',event=>{if(noteDirty){persistDraft();event.preventDefault();event.returnValue='';}});
$('#open-image').onclick=()=>$('#image-modal').showModal();$('#close-image').onclick=()=>$('#image-modal').close();
$('#image-modal').onclick=event=>{if(event.target===$('#image-modal')){const r=event.target.getBoundingClientRect();if(event.clientX<r.left||event.clientX>r.right||event.clientY<r.top||event.clientY>r.bottom)event.target.close();}};
async function poll(){
  if(!account||document.hidden||pollBusy)return;pollBusy=true;
  try{await syncNotes();}finally{pollBusy=false;}
}
setInterval(poll,2000);
setInterval(async()=>{if(!account||document.hidden)return;try{const generation=viewVersion,result=await api('me');if(generation===viewVersion){account.members=result.members;clockOffset=result.server_time*1000-Date.now();renderMembers();renderProgress(result);}await refreshBoard();}catch(error){if(error.status===401){logoutView();notify('Session ended. Please log in again.');}else $('#header-status').textContent='RECONNECTING';}},8000);
window.addEventListener('focus',()=>{poll();refreshBoard();});document.addEventListener('visibilitychange',()=>{if(!document.hidden){poll();refreshBoard();}});
async function loadConfig(){try{const config=await api('config');registrationOpen=config.registration_open;$('#registration-status').textContent=registrationOpen?'Register solo or with 2–4 investigators. Already registered? Log in from any device.':'New registration is currently closed. Existing members can still log in or activate their reserved account.';$('#register-submit').disabled=!registrationOpen;$('#register-submit').textContent=registrationOpen?'Register & begin investigation →':'Registration is currently closed';}catch(error){$('#registration-status').textContent='Cannot reach the archive. Check your connection and reload.';}}
(async()=>{
  // Ignore all v1 cached identities and browser notes; they never authenticate v2 accounts.
  const fragment=new URLSearchParams(location.hash.slice(1));activationToken=fragment.get('activate')||fragment.get('reset');
  if(activationToken){history.replaceState(null,'',location.pathname+location.search);authView('token');await loadConfig();return;}
  await loadConfig();try{await enter(await api('me'));}catch(error){if(error.status!==401)authError(error);else if(!registrationOpen)authView('login');}
})();

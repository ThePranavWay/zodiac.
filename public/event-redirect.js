/* Zodiac Seeker — scheduled closing redirect. No credentials or puzzle answers. */
(() => {
 'use strict';
 const FALLBACK_END_AT = Date.parse('2026-11-13T12:00:00+05:30');
 const DESTINATION = '/event-ended';
 let endAt = FALLBACK_END_AT, offset = 0, clockReady = false, redirecting = false, syncing = false;
 function check(){
  if(!clockReady||redirecting||location.pathname.replace(/\/$/,'')===DESTINATION||location.pathname==='/event-ended.html')return;
  if(Date.now()+offset>=endAt){redirecting=true;window.ZodiacEventClosed=true;location.replace(DESTINATION);}
 }
 async function sync(){
  if(syncing)return;syncing=true;
  const controller=new AbortController(),timeout=setTimeout(()=>controller.abort(),5000);
  try{
   const response=await fetch('/api/event-clock',{cache:'no-store',credentials:'same-origin',signal:controller.signal});
   if(response.ok){
    const clock=await response.json();
    if(Number.isFinite(clock.server_time)&&Number.isFinite(clock.ends_at)){
     offset=clock.server_time*1000-Date.now();endAt=clock.ends_at*1000;
    }
   }
  }catch(_){}
  finally{clearTimeout(timeout);clockReady=true;syncing=false;check();}
 }
 sync();
 setInterval(check,1000);
 setInterval(()=>{if(!document.hidden)sync();},60000);
 window.addEventListener('focus',sync);
 document.addEventListener('visibilitychange',()=>{if(!document.hidden)sync();});
})();

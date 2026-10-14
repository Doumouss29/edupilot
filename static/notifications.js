(() => {
  'use strict';
  const bell=document.getElementById('notification-bell');
  const panel=document.getElementById('notification-panel');
  if(!bell||!panel)return;
  const count=document.getElementById('notification-count');
  const items=document.getElementById('notification-items');
  const enable=document.getElementById('notification-push-enable');
  const pushStatus=document.getElementById('notification-push-status');
  let records=[],unread=0;
  const csrf=window.EDUPILOT_CSRF;
  async function api(url,data){
    const response=await fetch(url,{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:JSON.stringify(data)});
    if(!response.ok)throw new Error('Erreur '+response.status);
    return response.json();
  }
  function button(label,action,title){
    const el=document.createElement('button');
    el.type='button';el.textContent=label;el.className='notification-item-action';el.title=title||label;el.addEventListener('click',action);
    return el;
  }
  function render(){
    count.hidden=unread===0;count.textContent=unread>99?'99+':String(unread);
    bell.setAttribute('aria-label',unread?unread+' notifications non lues':'Ouvrir les notifications');
    items.replaceChildren();
    if(!records.length){const empty=document.createElement('p');empty.className='notification-empty';empty.textContent='Aucune notification pour le moment.';items.append(empty);return;}
    for(const n of records){
      const row=document.createElement('div');row.className='notification-item'+(n.read?'':' is-unread');
      const link=document.createElement('a');
      link.className='notification-item-link';
      link.href=(typeof n.href==='string'&&n.href.startsWith('/')&&!n.href.startsWith('//'))?n.href:'/';
      const msg=document.createElement('span');msg.textContent=n.message;
      const date=document.createElement('small');date.textContent=n.created_at||'';
      link.append(msg,date);
      link.addEventListener('click',()=>{if(!n.read)api('/api/notifications/read',{ids:[n.id]}).catch(()=>{});});
      row.append(link,button('×',async()=>{try{await api('/api/notifications/delete',{ids:[n.id]});await load();}catch(e){pushStatus.textContent='Impossible de supprimer la notification.';}},'Effacer cette notification'));
      items.append(row);
    }
  }
  async function load(){
    const response=await fetch('/api/notifications',{credentials:'same-origin',cache:'no-store'});
    if(!response.ok)throw new Error('Lecture impossible');
    const data=await response.json();records=data.notifications||[];unread=data.unread||0;render();
  }
  bell.addEventListener('click',async()=>{
    const open=panel.hidden;panel.hidden=!open;bell.setAttribute('aria-expanded',String(open));
    if(open){try{await load();}catch(e){pushStatus.textContent='Impossible de charger les notifications.';} await refreshPush();}
  });
  document.getElementById('notification-close').addEventListener('click',()=>{panel.hidden=true;bell.setAttribute('aria-expanded','false');});
  document.addEventListener('click',e=>{if(!panel.hidden&&!document.getElementById('notification-control').contains(e.target)){panel.hidden=true;bell.setAttribute('aria-expanded','false');}});
  document.addEventListener('keydown',e=>{if(e.key==='Escape'){panel.hidden=true;bell.setAttribute('aria-expanded','false');}});
  document.getElementById('notification-read-all').addEventListener('click',async()=>{try{await api('/api/notifications/read',{ids:[]});await load();}catch(e){pushStatus.textContent='Action impossible.';}});
  document.getElementById('notification-clear-all').addEventListener('click',async()=>{
    if(!records.length||!confirm('Effacer définitivement toutes vos notifications ?'))return;
    try{await api('/api/notifications/delete',{all:true});await load();}catch(e){pushStatus.textContent='Suppression impossible.';}
  });
  function decodeKey(key){
    const pad='='.repeat((4-key.length%4)%4);
    const bin=atob((key+pad).replace(/-/g,'+').replace(/_/g,'/'));
    return Uint8Array.from(bin,c=>c.charCodeAt(0));
  }
  async function refreshPush(){
    enable.hidden=true;
    if(!('serviceWorker' in navigator)||!('PushManager' in window)||!('Notification' in window)){
      pushStatus.textContent='Notifications du téléphone non disponibles dans ce navigateur.';return;
    }
    if(Notification.permission==='denied'){pushStatus.textContent='Notifications bloquées : autorisez EduPilot dans les réglages du téléphone.';return;}
    try{
      const r=await fetch('/api/push/config',{credentials:'same-origin'});
      if(!r.ok)return;
      const config=await r.json();
      if(!config.enabled){pushStatus.textContent='Notifications push non configurées par EduPilot.';return;}
      const registration=await navigator.serviceWorker.register('/sw.js',{scope:'/'});
      const existing=await registration.pushManager.getSubscription();
      if(existing){
        await api('/api/push/subscribe',existing.toJSON());
        pushStatus.textContent='Notifications du téléphone activées sur cet appareil.';return;
      }
      pushStatus.textContent='Recevoir les alertes EduPilot même lorsque le site est fermé.';
      enable.hidden=false;enable.dataset.publicKey=config.public_key;
    }catch(e){pushStatus.textContent='Activation indisponible : vérifiez la connexion.';}
  }
  enable.addEventListener('click',async()=>{
    try{
      const permission=await Notification.requestPermission();
      if(permission!=='granted'){pushStatus.textContent='Autorisation non accordée.';return;}
      const registration=await navigator.serviceWorker.register('/sw.js',{scope:'/'});
      const subscription=await registration.pushManager.subscribe({userVisibleOnly:true,applicationServerKey:decodeKey(enable.dataset.publicKey)});
      await api('/api/push/subscribe',subscription.toJSON());
      enable.hidden=true;pushStatus.textContent='Notifications du téléphone activées.';
    }catch(e){pushStatus.textContent='Impossible d’activer les notifications sur cet appareil.';}
  });
  const logoutForm=document.getElementById('edupilot-logout');
  if(logoutForm){
    logoutForm.addEventListener('submit',async event=>{
      event.preventDefault();
      try{
        if('serviceWorker' in navigator){
          const registration=await navigator.serviceWorker.getRegistration('/');
          const subscription=registration ? await registration.pushManager.getSubscription() : null;
          if(subscription){
            logoutForm.querySelector('[name="push_endpoint"]').value=subscription.endpoint;
            await subscription.unsubscribe();
          }
        }
      }catch(e){/* Logout must remain available without Web Push. */}
      logoutForm.submit();
    });
  }
  load().catch(()=>{});
  document.addEventListener('visibilitychange',()=>{if(!document.hidden)load().catch(()=>{});});
  setInterval(()=>{if(!document.hidden)load().catch(()=>{});},60000);
})();

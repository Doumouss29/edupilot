/* Optional mobile/tablet installation suggestion after authenticated login. */
(()=>{
  const ua=navigator.userAgent||'';
  const isMobile=/Android|iPhone|iPad|iPod|Mobile|Tablet/i.test(ua)||
    (navigator.platform==='MacIntel'&&navigator.maxTouchPoints>1);
  const installed=window.matchMedia('(display-mode: standalone)').matches||navigator.standalone===true;
  if(!isMobile||installed)return;
  const uid=String(window.EDUPILOT_USER_ID||'');
  if(!uid)return;
  const key='edupilot-install-offer-'+uid;
  const now=Date.now();
  try{
    const previous=Number(localStorage.getItem(key)||0);
    if(previous && now-previous<30*24*60*60*1000)return;
  }catch(err){return;}
  const panel=document.createElement('section');
  panel.setAttribute('role','region');
  panel.setAttribute('aria-label',"Installer l'application EduPilot");
  panel.style.cssText='position:fixed;z-index:9998;bottom:18px;left:14px;right:14px;max-width:430px;margin:auto;background:#fff;color:#203950;border:1px solid #dce6ef;border-radius:16px;box-shadow:0 12px 48px #101e3440;padding:18px;font:14px system-ui,sans-serif';
  const title=document.createElement('strong');
  title.textContent='Installer EduPilot sur cet appareil ?';
  title.style.cssText='font-size:16px';
  const body=document.createElement('p');
  body.textContent='Retrouvez votre établissement depuis votre écran d’accueil et accédez rapidement à EduPilot.';
  body.style.cssText='line-height:1.55';
  const buttons=document.createElement('div');
  buttons.style.cssText='display:flex;gap:9px;flex-wrap:wrap';
  const install=document.createElement('a');
  install.href='/installer';
  install.textContent='Voir comment installer';
  install.style.cssText='background:#203950;color:#fff;text-decoration:none;padding:11px 15px;border-radius:9px;font-weight:700';
  const later=document.createElement('button');
  later.type='button';
  later.textContent='Plus tard';
  later.style.cssText='border:1px solid #cbd6e0;background:#fff;color:#203950;border-radius:9px;padding:10px 14px;cursor:pointer';
  function dismiss(){
    try{localStorage.setItem(key,String(Date.now()));}catch(err){}
    panel.remove();
  }
  install.addEventListener('click',dismiss);
  later.addEventListener('click',dismiss);
  buttons.append(install,later);panel.append(title,body,buttons);
  document.body.append(panel);
})();

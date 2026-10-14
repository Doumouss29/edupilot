(() => {
  'use strict';
  const sidebar=document.getElementById('main-sidebar');
  const button=document.getElementById('mobile-menu-button');
  const backdrop=document.getElementById('mobile-backdrop');
  const closer=document.getElementById('mobile-menu-close');
  if(!sidebar||!button||!backdrop||!closer)return;
  const mobile=window.matchMedia('(max-width: 720px)');
  let previousFocus=null;
  const isOpen=()=>sidebar.classList.contains('mobile-open');
  function close(){
    if(!isOpen())return;
    sidebar.classList.remove('mobile-open');
    backdrop.hidden=true;
    document.body.classList.remove('mobile-menu-open');
    button.setAttribute('aria-expanded','false');
    if(previousFocus && previousFocus.isConnected)previousFocus.focus();
  }
  function open(){
    if(!mobile.matches)return;
    previousFocus=document.activeElement;
    sidebar.classList.add('mobile-open');
    backdrop.hidden=false;
    document.body.classList.add('mobile-menu-open');
    button.setAttribute('aria-expanded','true');
    closer.focus();
  }
  button.addEventListener('click',()=>isOpen()?close():open());
  closer.addEventListener('click',close);
  backdrop.addEventListener('click',close);
  sidebar.querySelectorAll('nav a').forEach(link=>link.addEventListener('click',close));
  document.addEventListener('keydown',event=>{
    if(!isOpen())return;
    if(event.key==='Escape'){close();return;}
    if(event.key==='Tab'){
      const selectors='a[href],button:not([disabled]),input:not([disabled]),select:not([disabled])';
      const focusables=[...sidebar.querySelectorAll(selectors)].filter(el=>el.getClientRects().length);
      if(!focusables.length)return;
      const first=focusables[0],last=focusables[focusables.length-1];
      if(event.shiftKey&&document.activeElement===first){event.preventDefault();last.focus();}
      else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first.focus();}
    }
  });
  mobile.addEventListener('change',event=>{if(!event.matches)close();});
  window.addEventListener('pagehide',close);
})();

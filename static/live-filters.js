(() => {
  'use strict';
  function norm(value){return String(value||'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLocaleLowerCase('fr').trim();}
  function tokens(value){return String(value||'').split(',').map(v=>v.trim()).filter(Boolean);}
  const tables=new Set();
  document.querySelectorAll('[data-filter-target]').forEach(bar=>{
    const table=document.getElementById(bar.dataset.filterTarget);
    if(!table)return;
    tables.add(table);
    const selects=[...bar.querySelectorAll('[data-filter]')];
    const rows=[...table.querySelectorAll('tbody tr[data-filter-row]')];
    const counter=bar.querySelector('.live-filter-count');
    function update(){
      let visible=0;
      const values=Object.fromEntries(selects.map(input=>[input.dataset.filter,String(input.value||'')]));
      rows.forEach(row=>{
        const matches=Object.entries(values).every(([key,val])=>{
          if(!val)return true;
          if(key==='search')return norm(row.textContent).includes(norm(val));
          return tokens(row.dataset[key]).includes(val);
        });
        row.hidden=!matches;
        if(matches)visible++;
        else row.querySelectorAll('input[type=checkbox]').forEach(box=>{box.checked=false;});
      });
      if(counter)counter.textContent=visible+' / '+rows.length+' résultat(s)';
      const master=table.querySelector('thead input[type=checkbox]');
      if(master)master.checked=false;
    }
    selects.forEach(input=>{input.addEventListener('input',update);input.addEventListener('change',update);});
    update();
  });
  // Every ordinary tabular listing also offers immediate keyword search.
  // Forms and action columns are left intact; hidden rows are unselected.
  document.querySelectorAll('.table-scroll > table').forEach(table=>{
    if(tables.has(table)||table.dataset.noLiveSearch==='true')return;
    const rows=[...table.querySelectorAll('tbody tr')].filter(row=>row.querySelector('td'));
    if(rows.length<2)return;
    const host=table.closest('.table-scroll');
    if(!host)return;
    const wrap=document.createElement('div');
    wrap.className='live-filter-bar live-filter-auto';
    const label=document.createElement('label');
    label.textContent='Recherche rapide';
    const search=document.createElement('input');
    search.type='search';search.placeholder='Rechercher dans ce tableau…';
    search.setAttribute('aria-label','Rechercher dans ce tableau');
    const counter=document.createElement('span');
    counter.className='live-filter-count';counter.setAttribute('aria-live','polite');
    label.appendChild(search);wrap.append(label,counter);
    host.parentNode.insertBefore(wrap,host);
    function update(){
      const query=norm(search.value);
      let visible=0;
      for(const row of rows){
        const show=!query||norm(row.textContent).includes(query);
        row.hidden=!show;
        if(show)visible++;
        else row.querySelectorAll('input[type=checkbox]').forEach(input=>input.checked=false);
      }
      counter.textContent=visible+' / '+rows.length+' résultat(s)';
    }
    search.addEventListener('input',update);
    update();
  });
})();

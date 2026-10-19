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
    const allOptions=new Map(selects.filter(el=>el.tagName==='SELECT').map(el=>[el,[...el.options].map(o=>({value:o.value,label:o.textContent}))]));
    const counter=bar.querySelector('.live-filter-count');
    function matchesFilter(row,key,val){
      if(!val)return true;
      if(key==='search')return norm(row.textContent).includes(norm(val));
      if(key==='last-from')return !!row.dataset.lastDate && row.dataset.lastDate>=val;
      if(key==='last-to')return !!row.dataset.lastDate && row.dataset.lastDate<=val;
      return tokens(row.dataset[key]).includes(val);
    }
    function update(){
      // Cascade: available choices reflect all *other* selected criteria.
      const current=Object.fromEntries(selects.map(el=>[el.dataset.filter,String(el.value||'')]));
      for(const [select,options] of allOptions){
        const key=select.dataset.filter;
        const allowed=new Set(rows.filter(row=>Object.entries(current).every(([other,val])=>!val||other===key||matchesFilter(row,other,val))).flatMap(row=>tokens(row.dataset[key])));
        const previous=select.value;
        for(const option of select.options){option.disabled=!!option.value&&!allowed.has(option.value);}
        // Keep selected value visible if it becomes temporarily incompatible.
        if(previous)for(const option of select.options)if(option.value===previous)option.disabled=false;
      }
      let visible=0;
      const values=Object.fromEntries(selects.map(input=>[input.dataset.filter,String(input.value||'')]));
      rows.forEach(row=>{
        const matches=Object.entries(values).every(([key,val])=>{
          if(!val)return true;
          return matchesFilter(row,key,val);
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
  // GET filters update immediately without a dedicated Apply button.
  document.querySelectorAll('form[data-auto-submit-filters]').forEach(form=>{
    form.querySelectorAll('select').forEach(select=>select.addEventListener('change',()=>form.requestSubmit()));
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

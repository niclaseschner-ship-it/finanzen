
window.BK=(function(){
 const esc=s=>{const d=document.createElement('div');d.textContent=s==null?'':s;return d.innerHTML.replace(/"/g,'&quot;').replace(/'/g,'&#39;');};  // textContent maskiert " nicht — in value="..." waere das eine Luecke
 const fmt=x=>Math.round(x).toLocaleString('de-DE');
 const fmt2=x=>Number(x).toLocaleString('de-DE',{minimumFractionDigits:2,maximumFractionDigits:2});
 let META={cats:[],labels:[]};
 function ensureDom(){
   if(document.getElementById('bkstyle'))return;
   const st=document.createElement('style'); st.id='bkstyle'; st.textContent=`
    .bk-tbl{width:100%;border-collapse:collapse;font-size:14px}
    .bk-tbl td,.bk-tbl th{padding:6px 8px;border-bottom:1px solid var(--linie);vertical-align:top}
    .bk-tbl th{color:var(--text2);text-align:left}.bk-r{text-align:right;white-space:nowrap}
    .bk-neg{color:var(--rot)}.bk-pos{color:var(--akzent-text)}
    .bk-tbl select,.bk-tbl input{background:var(--fl2);color:var(--text);border:1px solid var(--linie);border-radius:7px;padding:4px 6px;font-size:13px}
    .bk-komm{width:150px}
    tr.bk-rev>td{background:var(--akzent-fl)} tr.bk-ign{opacity:.4}
    tr.bk-unsaved>td{background:var(--rot-fl);outline:1px solid var(--rot)}
    .bk-prod{color:var(--akzent-text);font-weight:600;font-size:13px;margin:2px 0}
    .bk-ctx{color:var(--text2);font-size:12px;max-width:420px}.bk-mr{color:var(--blau);font-size:11px}.bk-why{color:var(--leise);font-size:11px}
    .bk-chip{background:var(--fl2);border-radius:6px;padding:1px 6px;margin:1px;display:inline-block;font-size:12px}
    .bk-lbe{background:var(--fl2);border:0;color:var(--text2);border-radius:6px;cursor:pointer;padding:1px 7px}
    .bk-lc{cursor:pointer;min-width:140px}
    .bk-b{background:var(--fl2);border:1px solid var(--linie);color:var(--text);border-radius:6px;cursor:pointer;padding:2px 7px;font-weight:600}
    .bk-okb{background:var(--akzent-fl);border-color:var(--akzent);color:var(--akzent-text)}.bk-nob{background:var(--rot-fl);border-color:var(--rot);color:var(--rot)}
    .bk-mailbtn{background:var(--blau-fl);border:1px solid var(--blau-fl);color:var(--blau);border-radius:6px;cursor:pointer;padding:1px 7px;font-size:11px}
    .bk-vtg{background:var(--lila-fl);color:var(--lila);border-radius:5px;padding:0 5px;font-size:10px;vertical-align:middle}
    #bklp{position:fixed;z-index:60;background:var(--fl);border:1px solid var(--linie);border-radius:10px;width:270px;box-shadow:0 8px 30px #000a;display:none}
    #bklp .lphd{padding:10px 12px 6px}
    #bklp .lq{width:100%;box-sizing:border-box;background:var(--fl2);color:var(--text);border:1px solid var(--linie);border-radius:7px;padding:7px 9px;font-size:13px}
    #bklp .lplist{max-height:42vh;overflow:auto;padding:4px 12px 6px}#bklp .lo{display:block;padding:3px 0;font-size:13px;cursor:pointer}
    #bklp .lo.on{color:var(--akzent-text);font-weight:600}
    #bklp .lnew{padding:6px 9px;margin:2px 0 6px;background:var(--akzent-fl);color:var(--akzent-text);border:1px solid var(--akzent);border-radius:7px;cursor:pointer;font-size:13px}
    #bklp .lpfoot{padding:8px 12px;border-top:1px solid var(--linie)}
    #bklp button{background:var(--akzent);border:0;color:var(--auf-akzent);border-radius:7px;padding:6px 10px;cursor:pointer}#bklp .sec{background:var(--fl2);color:var(--text)}
    #bkov{position:fixed;inset:0;background:#000a;display:none;z-index:70;align-items:center;justify-content:center}
    #bkmod{background:var(--fl);border:1px solid var(--linie);border-radius:12px;max-width:820px;width:92%;max-height:82vh;overflow:auto;padding:0}
    /* Kopf bleibt beim Scrollen stehen; kein float mehr, sonst umfliesst der Betreff den Knopf */
    .bk-kopf{position:sticky;top:0;z-index:2;display:flex;gap:12px;align-items:flex-start;
      background:var(--fl);border-bottom:1px solid var(--linie);padding:14px 16px;border-radius:12px 12px 0 0}
    .bk-kopf-t{font-size:17px;font-weight:700;line-height:1.3;overflow-wrap:anywhere;flex:1}
    #bkmod .x{flex:none;background:var(--fl2);border:0;color:var(--text);border-radius:7px;padding:5px 10px;cursor:pointer}
    .bk-inhalt{padding:12px 16px 16px}
    #bkmod h4{overflow-wrap:anywhere;margin:14px 0 6px}
    .bk-rel{border-top:1px solid var(--linie);padding-top:6px;margin-top:6px}
    /* overflow:auto ist Pflicht, sobald eine Hoehe gedeckelt wird. Ohne das lief der Text
       sichtbar aus dem Kasten heraus und legte sich ueber die naechste Betreffzeile. */
    .bk-mailbody{white-space:pre-wrap;font-size:13px;line-height:1.45;color:var(--text);background:var(--fl);border:1px solid var(--linie);border-radius:8px;padding:10px;margin:6px 0;overflow-wrap:anywhere;overflow:auto}
    .bk-snip{max-height:150px}
    .bk-werb{background:var(--warn-fl);color:var(--warn);border-radius:5px;padding:0 5px;font-size:10px;margin-left:6px;vertical-align:middle}
    #bkmod details>summary{cursor:pointer;color:var(--blau);font-size:13px;padding:8px 0}
    /* Anhaenge als Karten: Kopfzeile mit Name/Typ/Groesse, darunter die Vorschau */
    .bk-att{border:1px solid var(--linie);border-radius:8px;margin:8px 0;overflow:hidden;background:var(--fl)}
    .bk-att-kopf{display:flex;gap:8px;align-items:center;flex-wrap:wrap;padding:8px 10px;border-bottom:1px solid var(--linie)}
    .bk-att-name{font-weight:600;font-size:13px;overflow-wrap:anywhere;min-width:0}
    .bk-att-meta{color:var(--leise);font-size:11px;white-space:nowrap}
    .bk-att .dl{margin-left:auto;background:var(--fl2);color:var(--text);border-radius:6px;padding:3px 9px;font-size:12px;text-decoration:none;white-space:nowrap}
    .bk-att img{display:block;max-width:100%;height:auto;background:#fff}
    .bk-att iframe{display:block;width:100%;height:70vh;border:0;background:#fff}
    .bk-att-pdf{padding:10px}
    .bk-pdfbtn{background:var(--fl2);border:1px solid var(--linie);color:var(--text);border-radius:7px;padding:5px 10px;cursor:pointer;font-size:12px}
    .bk-att details{padding:0 10px 8px}.bk-att summary{cursor:pointer;color:var(--blau);font-size:12px;padding:6px 0}
    .bk-att-hint{padding:8px 10px;color:var(--leise);font-size:12px}`;
   document.head.appendChild(st);
   const lp=document.createElement('div'); lp.id='bklp'; document.body.appendChild(lp);
   const ov=document.createElement('div'); ov.id='bkov'; ov.innerHTML='<div id=bkmod></div>'; document.body.appendChild(ov);
   ov.addEventListener('click',e=>{if(e.target.id==='bkov')ov.style.display='none';});
   document.addEventListener('mousedown',e=>{const l=document.getElementById('bklp');
     if(l.style.display==='block'&&!l.contains(e.target)&&!e.target.closest('.bk-lc'))l.style.display='none';});
   document.addEventListener('keydown',e=>{if(e.key==='Escape'){document.getElementById('bklp').style.display='none';document.getElementById('bkov').style.display='none';}});
 }
 async function init(){ ensureDom(); try{META=await (await fetch('api/meta')).json();}catch(e){} return META; }
 const chips=s=>(s||'').split(',').map(x=>x.trim()).filter(Boolean).map(l=>`<span class=bk-chip>${esc(l)}</span>`).join('');
 const catOptions=c=>META.cats.map(x=>`<option${x===c?' selected':''}>${esc(x)}</option>`).join('')+`<option value="__new__">➕ neue Kategorie…</option>`;
 async function save(r,patch,tr,onChange){
   const body=Object.assign({tx_id:r.id,scope:'tx',src:'detail'},patch);  // NUR geändertes Feld (merge-sicher)
   try{
     const resp=await fetch('api/edit',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
     if(!resp.ok) throw new Error('HTTP '+resp.status);
     const j=await resp.json(); if(!j.row) throw new Error('keine Bestätigung');
     Object.assign(r,j.row);
     if(tr){tr.classList.remove('bk-unsaved');tr.classList.toggle('bk-ign',!!r.ignore);tr.classList.toggle('bk-rev',!!r.reviewed&&!r.ignore);}
     if(onChange)onChange();
   }catch(e){ if(tr)tr.classList.add('bk-unsaved'); alert('⚠ NICHT gespeichert: '+e.message+'\nServer erreichbar?'); }
 }
 function _lev(a,b){const m=a.length,n=b.length;if(!m)return n;if(!n)return m;let p=[];for(let j=0;j<=n;j++)p[j]=j;
   for(let i=1;i<=m;i++){let c=[i];for(let j=1;j<=n;j++)c[j]=Math.min(p[j]+1,c[j-1]+1,p[j-1]+(a[i-1]===b[j-1]?0:1));p=c;}return p[n];}
 function _lscore(L,Q){if(L===Q)return 1000;if(L.startsWith(Q))return 600-L.length;const i=L.indexOf(Q);if(i>=0)return 400-i;
   const d=_lev(L,Q),md=Math.max(1,Math.floor(Q.length/3));if(d<=md)return 350-d*30;
   let p=0;while(p<L.length&&p<Q.length&&L[p]===Q[p])p++;if(p>=3)return 150+p;return -1;}
 function _rank(Q,sel){const ql=Q.toLowerCase(),pool=[...new Set([...(META.labels||[]),...sel])];
   let it=pool.map(l=>({l,on:sel.has(l),s:ql?_lscore(l.toLowerCase(),ql):0}));
   if(ql)it=it.filter(x=>x.on||x.s>=0);
   it.sort((a,b)=>(b.on-a.on)||(b.s-a.s)||a.l.localeCompare(b.l));return it;}
 function openLabels(r,tr,e,onChange){
   const lp=document.getElementById('bklp');
   const sel=new Set((r.labels||'').split(',').map(x=>x.trim()).filter(Boolean));
   lp.innerHTML=`<div class=lphd><input id=bklq class=lq placeholder="suchen oder neu… ⏎" autocomplete=off></div>`
    +`<div class=lplist id=bkll></div>`
    +`<div class=lpfoot><button id=bkls>Übernehmen</button> <button id=bklc class=sec>Abbrechen</button></div>`;
   lp.style.display='block';
   const q=lp.querySelector('#bklq'),list=lp.querySelector('#bkll');
   const draw=()=>{const Q=q.value.trim(),exact=(META.labels||[]).some(l=>l.toLowerCase()===Q.toLowerCase());
     let h=(Q&&!exact)?`<div class=lnew id=bklnew>➕ „${esc(Q)}" anlegen</div>`:'';
     const it=_rank(Q,sel);
     h+=it.map(x=>`<label class="lo${x.on?' on':''}"><input type=checkbox value="${esc(x.l)}" ${x.on?'checked':''}> ${esc(x.l)}</label>`).join('');
     if(!it.length&&!(Q&&!exact))h+='<div class=bk-why style="padding:4px">nichts gefunden</div>';
     list.innerHTML=h;
     const nw=list.querySelector('#bklnew');if(nw)nw.onclick=()=>addNew(Q);
     list.querySelectorAll('input[type=checkbox]').forEach(cb=>cb.onchange=()=>{cb.checked?sel.add(cb.value):sel.delete(cb.value);
       cb.parentElement.classList.toggle('on',cb.checked);});};
   const addNew=async v=>{v=(v||'').trim();if(!v)return;
     try{const res=await (await fetch('api/addlabel',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:v})})).json();META.labels=res.labels||META.labels;}catch(_){}
     sel.add(v);q.value='';draw();q.focus();};
   const toggle=l=>{sel.has(l)?sel.delete(l):sel.add(l);q.value='';draw();q.focus();};
   q.addEventListener('input',draw);
   q.addEventListener('keydown',ev=>{
     if(ev.key==='Enter'){ev.preventDefault();const Q=q.value.trim();if(!Q)return apply();
       const c=_rank(Q,new Set()).filter(x=>x.s>=300);
       if(c.length)toggle(c[0].l);else addNew(Q);}
     else if(ev.key==='Escape')lp.style.display='none';});
   function apply(){r.labels=[...sel].join(',');
     tr.querySelector('.bk-lc').innerHTML=chips(r.labels)+'<button type=button class=bk-lbe>＋</button>';
     tr.querySelector('.bk-lc').addEventListener('click',ev=>openLabels(r,tr,ev,onChange));
     lp.style.display='none';save(r,{labels:r.labels},tr,onChange);}
   lp.querySelector('#bkls').onclick=apply;
   lp.querySelector('#bklc').onclick=()=>lp.style.display='none';
   draw();
   const w=lp.offsetWidth,h=lp.offsetHeight;
   lp.style.left=Math.max(8,Math.min(e.clientX,innerWidth-w-12))+'px'; lp.style.top=Math.max(8,Math.min(e.clientY,innerHeight-h-12))+'px';
   q.focus();
 }
 async function onCatChange(r,tr,sel,onChange){
   if(sel.value==='__new__'){const name=(prompt('Neue Kategorie:')||'').trim();
     if(!name){sel.value=r.cat;return;}
     try{const res=await (await fetch('api/addcat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name})})).json();META.cats=res.cats||META.cats;}catch(e){}
     sel.innerHTML=catOptions(name);}
   r.cat=sel.value; save(r,{category:r.cat},tr,onChange);
 }
 async function showMail(txid){
   const ov=document.getElementById('bkov'),mod=document.getElementById('bkmod');
   mod.innerHTML='<div class=bk-kopf><div class=bk-kopf-t>Beleg-Mail</div>'
     +'<button class=x onclick="document.getElementById(\'bkov\').style.display=\'none\'">schließen ✕</button></div>'
     +'<div class=bk-inhalt><div class=bk-why>lädt…</div></div>';
   ov.style.display='flex';
   const m=await (await fetch('api/mail?tx_id='+encodeURIComponent(txid))).json();
   // Kopfzeile als eigene, klebende Leiste: der Schliessen-Knopf lag vorher als
   // float:right VOR der Ueberschrift, dadurch lief ein langer Betreff um ihn herum
   // und bei langen Mails scrollte er aus dem Bild.
   let h=`<div class=bk-kopf><div class=bk-kopf-t>${esc(m.found?(m.subject||'(kein Betreff)'):'Beleg-Mail')}</div>`
        +`<button class=x>schließen ✕</button></div><div class=bk-inhalt>`;
   if(!m.found){h+='<p class=bk-why>Keine direkt verknüpfte Beleg-Mail.</p>';}
   else{
     h+=`<div class=bk-why>${esc(m.from||'')} · ${esc(m.date||'')} · Treffer: <b style="color:${m.sure?'var(--akzent-text)':'var(--warn)'}">${esc(m.match_art||'')}</b></div>`;
     h+=`<pre class=bk-mailbody>${esc(m.body||'')}</pre>`;
     const att=m.attachments||[];
     if(att.length){
       h+=`<h4>📎 ${att.length} ${att.length===1?'Anhang':'Anhänge'}</h4>`;
       att.forEach(a=>{h+=attHTML(a);});
     }
   }
   const rel=m.related||[];
   // Zugeklappt: das sind Kandidaten, nicht der Beleg. Offen verdraengten sie bei
   // Haendlern mit taeglichem Newsletter die eigentliche Mail komplett aus dem Sichtfeld.
   if(rel.length){
     const nAtt=rel.reduce((s,x)=>s+((x.anhaenge||[]).length),0);
     // Aufgeklappt, sobald hier ueberhaupt eine Datei haengt: dann ist genau das der
     // Grund, warum jemand die Beleg-Mail geoeffnet hat.
     h+=`<details${nAtt?' open':''}><summary>📬 ${rel.length} weitere Mails dieses Händlers`
       +(nAtt?` · <b style="color:var(--akzent-text)">${nAtt} Anhang${nAtt===1?'':'/Anhänge'}</b>`:'')
       +` · nur Info, KEINE Buchungen</summary>`;
     rel.forEach(x=>{
       const at=x.anhaenge||[];
       h+=`<div class=bk-rel><b>${esc(x.subject)}</b>${x.werbung?'<span class=bk-werb>Werbung</span>':''}`
         +`<div class=bk-why>${esc(x.from)} · ${esc(x.date)}</div>`
         +`<pre class="bk-mailbody bk-snip">${esc(x.snippet)}</pre>`;
       at.forEach(a=>{h+=attHTML(a);});
       h+=`</div>`;});
     h+=`</details>`;}
   mod.innerHTML=h+'</div>';
   mod.querySelector('.x').onclick=()=>{ov.style.display='none';};
   mod.querySelectorAll('.bk-pdfbtn').forEach(b=>b.onclick=()=>{
     b.outerHTML=`<iframe src="${b.dataset.url}" title="PDF-Vorschau"></iframe>`;});
   mod.scrollTop=0;
 }
 // EINE Darstellung fuer Anhaenge, egal ob an der verknuepften Mail oder an einer
 // Begleitmail. Vorher gab es sie nur fuer die verknuepfte — und genau dort haengt die
 // Rechnung fast nie, weil der Zahlungsbeleg eine eigene Mail ist.
 function attHTML(a){
   const url='api/anhang?id='+encodeURIComponent(a.id);
   const bild=/^image\//.test(a.typ||''), pdf=(a.typ||'')==='application/pdf';
   let h=`<div class=bk-att><div class=bk-att-kopf>`
     +`<span class=bk-att-name>${esc(a.name)}</span>`
     +`<span class=bk-att-meta>${esc(kurztyp(a.typ))}${a.size?' · '+groesse(a.size):''}</span>`
     +(a.da?`<a class=dl href="${url}" target=_blank rel=noopener>öffnen ↗</a>`
           :`<span class=bk-att-meta style="margin-left:auto;color:var(--warn)">Datei fehlt</span>`)
     +`</div>`;
   if(a.da&&bild)     h+=`<img src="${url}" loading=lazy alt="${esc(a.name)}">`;
   // PDFs erst auf Klick laden: zehn Belege gleichzeitig als iframe legen die Seite lahm.
   else if(a.da&&pdf) h+=`<div class=bk-att-pdf><button class=bk-pdfbtn data-url="${url}">Vorschau anzeigen</button></div>`;
   if(a.text)         h+=`<details><summary>ausgelesener Text</summary><pre class=bk-mailbody>${esc(a.text)}</pre></details>`;
   else if(!bild&&!pdf&&a.da) h+=`<div class=bk-att-hint>Kein Text ausgelesen — über „öffnen" ansehen.</div>`;
   return h+`</div>`;
 }
 const groesse=n=>n>=1048576?(n/1048576).toFixed(1).replace('.',',')+' MB'
                :n>=1024?Math.round(n/1024)+' KB':n+' B';
 // Aus "application/vnd.openxmlformats-officedocument.wordprocessingml.document" wird "DOCX"
 const KURZ={'application/pdf':'PDF','image/jpeg':'JPEG','image/jpg':'JPEG','image/png':'PNG',
   'image/gif':'GIF','image/webp':'WEBP','application/octet-stream':'Datei','text/plain':'Text',
   'application/vnd.openxmlformats-officedocument.wordprocessingml.document':'DOCX',
   'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet':'XLSX',
   'application/vnd.openxmlformats-officedocument.presentationml.presentation':'PPTX',
   'application/msword':'DOC','application/vnd.ms-excel':'XLS','application/zip':'ZIP'};
 const kurztyp=t=>KURZ[t]||((t||'').split('/').pop().split('.').pop().slice(0,12).toUpperCase()||'Datei');
 // KANONISCHE Detailtabelle – überall identisch
 function renderBookings(container,rows,opts){
   opts=opts||{}; const onChange=opts.onChange;
   const cont=typeof container==='string'?document.getElementById(container):container;
   rows=rows.slice().sort((a,b)=>Math.abs(b.b)-Math.abs(a.b));
   const sum=rows.reduce((s,r)=>s+(-r.b),0);
   let h=`<div class=bk-why>${rows.length} Buchungen · ${fmt(sum)} € · ✓ geprüft / ✗ ignorieren · Kategorie+Labels+Kommentar direkt änderbar</div>`;
   h+='<table class=bk-tbl><thead><tr><th>Prüfen</th><th>Datum</th><th class=bk-r>Betrag</th><th>Händler / Kontext</th><th>Kategorie</th><th>Labels</th><th>Kommentar</th></tr></thead><tbody>';
   rows.slice(0,400).forEach((r,i)=>{
     const mail=r.ctx?`<div class=bk-mr>✉ ${esc(r.ctx).slice(0,150)}</div>`:'';
     const prod=r.prod?`<div class=bk-prod>🛒 ${esc(r.prod)}</div>`:'';
     const mbtn=(r.ml||r.art==='PayPal')?` <button class=bk-mailbtn>✉ Mail</button>`:'';
     h+=`<tr data-i=${i} class="${r.ignore?'bk-ign':(r.reviewed?'bk-rev':'')}">
       <td><button class="bk-b bk-okb" data-a=rev title="geprüft/ok">✓</button> <button class="bk-b bk-nob" data-a=ign title="ignorieren (raus aus Statistik)">✗</button></td>
       <td>${r.d}${r.vtg?' <span class=bk-vtg>Vertrag</span>':''}</td>
       <td class="bk-r ${r.b<0?'bk-neg':'bk-pos'}">${fmt2(r.b)} €</td>
       <td>${esc(r.h).slice(0,40)}${mbtn}${prod}<div class=bk-ctx>${esc(r.vz||'').slice(0,150)}${mail}<div class=bk-why>${esc(r.art||'')} · 🏷️ ${esc(r.why||r.src||'')}</div></div></td>
       <td><select data-f=cat>${catOptions(r.cat)}</select></td>
       <td class=bk-lc>${chips(r.labels)}<button type=button class=bk-lbe>＋</button></td>
       <td><input data-f=note class=bk-komm value="${esc(r.note||'')}" placeholder="was war das?"></td></tr>`;
   });
   if(rows.length>400)h+=`<tr><td colspan=7 class=bk-why>… ${rows.length-400} weitere</td></tr>`;
   h+='</tbody></table>'; cont.innerHTML=h;
   cont.querySelectorAll('tbody tr[data-i]').forEach(tr=>{
     const r=rows[+tr.dataset.i];
     const selc=tr.querySelector('[data-f=cat]'); if(selc)selc.addEventListener('change',()=>onCatChange(r,tr,selc,onChange));
     const noi=tr.querySelector('[data-f=note]'); if(noi)noi.addEventListener('change',()=>{r.note=noi.value;save(r,{note:r.note},tr,onChange);});
     const lc=tr.querySelector('.bk-lc'); if(lc)lc.addEventListener('click',e=>openLabels(r,tr,e,onChange));
     const mb=tr.querySelector('.bk-mailbtn'); if(mb)mb.addEventListener('click',()=>showMail(r.id));
     tr.querySelector('[data-a=rev]').addEventListener('click',()=>{save(r,{reviewed:r.reviewed?0:1},tr,onChange);});
     tr.querySelector('[data-a=ign]').addEventListener('click',()=>{save(r,{ignore:r.ignore?0:1},tr,onChange);});
   });
 }
 async function loadInto(container,url,opts){
   const cont=typeof container==='string'?document.getElementById(container):container;
   cont.innerHTML='<div class=bk-why>lädt…</div>';
   const rows=await (await fetch(url)).json(); renderBookings(cont,rows,opts);
 }
 // Filter-Persistenz pro Seite: bleibt beim Seitenwechsel erhalten, NUR bei hartem Neuladen (F5)
 // wird zurückgesetzt. clear() = manueller Reset ("alle Buchungen").
 function filterState(key){
   const K='filt:'+key;
   let isReload=false;
   try{const nav=performance.getEntriesByType('navigation')[0];isReload=nav&&nav.type==='reload';}catch(e){}
   if(isReload){try{sessionStorage.removeItem(K);}catch(e){}}
   return {
     reloaded:isReload,
     load(){if(isReload)return null;try{return JSON.parse(sessionStorage.getItem(K)||'null');}catch(e){return null;}},
     save(o){try{sessionStorage.setItem(K,JSON.stringify(o));}catch(e){}},
     clear(){try{sessionStorage.removeItem(K);}catch(e){}}
   };
 }
 return {init,renderBookings,loadInto,showMail,fmt,fmt2,esc,filterState,get META(){return META;}};
})();

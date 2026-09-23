"""Statistik-Seite -> output/statistik.html (DB->HTML, Chart.js, kein Server).
- Einnahmen/Ausgaben/Monat, Ausgaben gestapelt nach Kategorie, Kategorie-Ranking
- Klick auf Balken -> zugehörige Buchungen als Liste darunter (Drill-down)
- Reisen mit ORTEN statt Datum (häufigste Kartenorte je Trip)
- Jahr-Filter clientseitig; Nav zu liste.html
"""
import json, re, db, datetime

def json_fuer_script(obj):
    """JSON so einbetten, dass es ein <script>-Element nicht sprengen kann.

    json.dumps maskiert '<' und '/' nicht. Ein Verwendungszweck wie
    "</script><img src=x onerror=...>" beendet sonst das Skript-Element und der Rest
    wird als HTML ausgefuehrt — und Verwendungszwecke bestimmt, wer ueberweist.
    Die drei Ersetzungen sind in JSON-Strings zulaessig und aendern den Wert nicht."""
    return (json.dumps(obj, ensure_ascii=False)
            .replace("<", r"\u003c").replace(">", r"\u003e").replace("&", r"\u0026"))

from collections import defaultdict, Counter
import os

CHART_JS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "seiten", "chart.min.js")

def chart_js_bereitstellen():
    """Chart.js neben die erzeugte Seite legen (statt vom CDN zu laden).

    Die Seite traegt alle Buchungen als JSON in sich; ein Skript von fremdem Server
    koennte sie mitlesen. Deshalb liegt die Bibliothek im Projekt — und wird hierher
    kopiert, damit die Datei auch beim direkten Oeffnen im Browser gefunden wird."""
    ziel = os.path.join(db.OUTPUT_DIR, "chart.min.js")
    try:
        if not os.path.exists(ziel) or os.path.getsize(ziel) != os.path.getsize(CHART_JS):
            os.makedirs(db.OUTPUT_DIR, exist_ok=True)
            with open(CHART_JS, "rb") as q, open(ziel, "wb") as z:
                z.write(q.read())
    except OSError as e:
        print(f"  Hinweis: chart.min.js konnte nicht kopiert werden ({e})")


BT = ["Einnahme", "Konsum", "Sparen"]   # kein "Asset" mehr – Camper/Kredit = normale Ausgaben

def btyp(cat, flow):
    if flow == "intern" or cat == "Umbuchung intern": return None
    if flow == "einnahme" or cat == "Einnahme": return "Einnahme"   # Einnahmen IMMER zuerst (auch Miete)
    if cat == "Sparen/Invest": return "Sparen"
    return "Konsum"     # alles andere (inkl. Camper) = normale Ausgabe

def clean_ort(o):
    o = re.sub(r"[\d.]+", " ", o or "")
    o = re.sub(r"\s+", " ", o).strip().title()
    return o

def run():
    con = db.connect()
    MINM, MAXM = db.period_bounds()   # berücksichtigter Zeitraum (Import-Seite); Monat unvollendet -> immer raus
    # eff_monat (= Datum-Override falls gesetzt) statt Roh-Monat; Ignorierte raus
    rows = con.execute("""select t.id,c.eff_monat,t.datum,t.betrag,t.flow,c.category,
        coalesce(e.haendler_norm,t.gegenpartei),
        trim(coalesce(t.verwendungszweck,'')||' · '||coalesce(t.gegenpartei,'')),
        coalesce(e.zahlungsart,''),lower(coalesce(e.creditor_id,'')),lower(coalesce(e.haendler_norm,'')),
        coalesce(group_concat(distinct l.label),''),substr(coalesce(x.ctx,''),1,170),
        (select 1 from tx_mail_links ml where ml.tx_id=t.id limit 1),
        coalesce(c.source_rule,''),coalesce(c.reason,''),coalesce(c.status,''),
        coalesce(mm.note,''),coalesce(x.produkt,''),coalesce(mm.ignore,0),coalesce(mm.reviewed,0)
        from transactions t join tx_category c on c.tx_id=t.id
        left join tx_enrich e on e.tx_id=t.id
        left join tx_labels l on l.tx_id=t.id
        left join (select tx_id, betreff||' '||snippet ctx, produkt from tx_context) x on x.tx_id=t.id
        left join tx_manual mm on mm.tx_id=t.id
        where c.eff_monat is not null and c.status<>'ignoriert'
          and c.eff_monat <= ? and (?='' or c.eff_monat >= ?)
        group by t.id""", (MAXM, MINM, MINM)).fetchall()
    # Vertrags-Schlüssel (nicht abgelehnte Verträge) -> Buchungen als Vertrag markieren
    credset, hndset = set(), set()
    for kt, kv in con.execute("select key_type,key_val from contracts where status<>'rejected'"):
        (credset if kt == "creditor" else hndset).add((kv or "").lower())
    # Reisen aus der bestätigten trips-Tabelle (abgelehnte raus); Anzeige: Name sonst Orte
    trips = []
    try:
        kost = db.trip_costs(con)      # live, sonst weicht die Reisetabelle von den Monatsbalken ab
        for tid, start, ende, orte, kosten, status, name in con.execute(
                """select id,start,ende,orte,kosten,status,coalesce(name,'')
                   from trips where status<>'rejected' order by start desc"""):
            trips.append({"label": tid, "ym": start[:7], "kosten": kost.get(tid, 0),
                          "orte": name or orte or start})
    except Exception:
        pass
    con.close()

    months = set(); tx = []; alltot = defaultdict(float)
    for tid, mon, datum, b, flow, cat, hn, vz, art, cred, hnl, labs, ctx, hasmail, src, why, st, note, prod, ign, rev in rows:
        bt = btyp(cat, flow)
        if not bt: continue
        labset = set(x for x in (labs or "").split(",") if x)
        vtg = 1 if (cred and cred in credset) or (hnl and hnl in hndset) else 0
        months.add(mon); alltot[cat] += abs(b)
        tx.append({"id": tid, "m": mon, "d": datum, "b": round(b, 2), "h": db.clean_disp(hn) or (hn or ""), "c": cat,
                   "bt": bt, "fx": 1 if "fixkosten" in labset else 0, "vtg": vtg,
                   "vz": db.clean_disp(vz)[:170], "art": art or "", "ml": 1 if hasmail else 0,
                   "src": src or "", "why": (why or "")[:60], "st": st or "", "note": note or "", "prod": prod or "",
                   "ignore": ign, "reviewed": rev,
                   "lab": ",".join(sorted(x for x in labset if not x.startswith("TRIP-"))), "ctx": ctx or ""})
    months = sorted(months)
    # alle Kategorien (für Excel-artigen Filter), nach Gesamtumsatz sortiert
    cats = [c for c, _ in sorted(alltot.items(), key=lambda x: -x[1])]

    con2 = db.connect()
    try:
        osm_n = con2.execute("select count(*) from merchant_branche where coalesce(category,'')<>''").fetchone()[0]
        osm_tot = con2.execute("select count(*) from merchant_branche").fetchone()[0]
    except Exception:
        osm_n = osm_tot = 0
    con2.close()
    build_ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    data = {"months": months, "cats": cats, "tx": tx, "trips": trips, "maxm": MAXM,
            "build": build_ts, "osm_n": osm_n, "osm_tot": osm_tot}

    tmpl = r"""<!doctype html><html lang=de><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1"><title>Finanzen · Statistik</title>
<script src="chart.min.js"></script>
<style>
 body{font-family:system-ui,Arial,sans-serif;margin:0;background:#0f1117;color:#e6e6e6}
 .wrap{max-width:1850px;margin:0 auto;padding:20px 30px}
 nav a{color:#9aa4b2;text-decoration:none;margin-right:16px;font-weight:600} nav a.active{color:#4f8cff}
 h2{margin-top:30px;border-bottom:1px solid #2a2f3a;padding-bottom:6px} h3{margin:14px 0 6px}
 .kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(185px,1fr));gap:12px;margin:16px 0}
 .kpi{background:#171a23;border:1px solid #262b36;border-radius:12px;padding:14px}
 .kpi .v{font-size:22px;font-weight:700} .kpi .l{color:#9aa4b2;font-size:12px;margin-top:3px}
 /* Diagramme: feste Hoehe ueber den Rahmen, NICHT ueber das Seitenverhaeltnis.
    Vorher ergab sich die Hoehe aus dem Verhaeltnis der Canvas-Attribute — auf einem
    Telefon waren die Diagramme dadurch nur gut hundert Pixel hoch und unlesbar. */
 .cbox{position:relative;height:330px;background:#171a23;border-radius:12px;padding:10px;margin-top:10px}
 .cbox.hoch{height:520px}
 .cbox canvas{width:100%!important;height:100%!important}
 select{background:#1b1f2a;color:#e6e6e6;border:1px solid #2c323f;border-radius:8px;padding:7px 9px}
 table{width:100%;border-collapse:collapse;font-size:14px} td,th{padding:6px 8px;border-bottom:1px solid #232834}
 th{color:#9aa4b2;text-align:left} .r{text-align:right}
 #detail{background:#141823;border:1px solid #262b36;border-radius:12px;padding:12px;margin-top:12px;min-height:40px}
 .hint{color:#6b7280;font-size:12px}
 .toolbar{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin:6px 0 4px}
 .fbtn{background:#222a38;border:1px solid #2c323f;color:#cbd5e1;border-radius:7px;padding:6px 11px;cursor:pointer;font-size:13px}
 .fbtn:hover{background:#2a3343}
 #catfilter{display:grid;grid-template-columns:repeat(auto-fill,minmax(210px,1fr));gap:2px 14px;
   background:#141823;border:1px solid #262b36;border-radius:12px;padding:12px 14px;margin:8px 0}
 #catfilter label{display:flex;align-items:center;gap:7px;font-size:13px;padding:2px 0;cursor:pointer}
 #catfilter .amt{margin-left:auto;color:#6b7280;font-size:12px}
 #catfilter .amt.neg{color:#ff8a8a}#catfilter .amt.pos{color:#7ee0a0}
 .filterbadge{color:#f0b46b;font-size:13px}
 #detail .neg{color:#ff8a8a}#detail .pos{color:#7ee0a0}
 #detail td{vertical-align:top} #detail .dctx{color:#9aa4b2;font-size:12px;max-width:520px}
 #detail .mail{color:#7f9cc7;font-size:11px} #detail .why{color:#6b7280;font-size:11px}
 #detail .prod{color:#7ee0a0;font-weight:600;font-size:13px;margin:2px 0}
 #detail select,#detail input{background:#1b1f2a;color:#e6e6e6;border:1px solid #2c323f;border-radius:7px;padding:4px 6px;font-size:13px}
 #detail .komm{width:170px}
 tr.saved>td{background:#16301d}
 #detail tr.unsaved>td{background:#3a1620;outline:1px solid #ff8a8a}
 .vtgtag{background:#3a2f4d;color:#c9b6ec;border-radius:5px;padding:0 5px;font-size:10px;vertical-align:middle}
 #detail .lc{cursor:pointer;min-width:150px} .chip{background:#26324a;border-radius:6px;padding:1px 6px;margin:1px;display:inline-block;font-size:12px}
 .lbe{background:#2a3343;border:0;color:#9aa4b2;border-radius:6px;cursor:pointer;padding:1px 7px}
 #lp{position:fixed;z-index:50;background:#11141c;border:1px solid #3a4252;border-radius:10px;width:250px;box-shadow:0 8px 30px #000a;display:none}
 #lp .lplist{max-height:38vh;overflow:auto;padding:12px 12px 6px}
 #lp .lo{display:block;padding:3px 0;font-size:13px}
 #lp .lpfoot{padding:8px 12px;border-top:1px solid #2c323f;background:#11141c;border-radius:0 0 10px 10px}
 #lp .newl{display:flex;gap:6px;margin-bottom:8px}
 #lp button{background:#4f8cff;border:0;color:#fff;border-radius:7px;padding:6px 10px;cursor:pointer}
 #lp .sec{background:#2a3343;color:#cbd5e1}
 .mailbtn{background:#22324a;border:1px solid #2c4060;color:#9ec1ff;border-radius:6px;cursor:pointer;padding:1px 7px;font-size:11px}
 #ov{position:fixed;inset:0;background:#000a;display:none;z-index:60;align-items:center;justify-content:center}
 #mod{background:#11141c;border:1px solid #3a4252;border-radius:12px;max-width:820px;width:92%;max-height:82vh;overflow:auto;padding:16px;box-shadow:0 12px 40px #000b}
 #mod h3{margin:0 6px 2px 0}#mod h4{margin:14px 0 4px;color:#9ec1ff}#mod .x{float:right;background:#2a3343;border:0;color:#cbd5e1;border-radius:7px;padding:5px 10px;cursor:pointer}
 /* ---- Handy und Tablet ---------------------------------------------------- */
 #fltbox>summary{display:none}          /* am Schreibtisch immer offen, kein Aufklapper */
 @media(max-width:900px){
  .wrap{padding:12px}
  nav{display:flex;flex-wrap:wrap;gap:4px 14px;margin-bottom:8px}
  nav a{margin-right:0;font-size:13px}
  h1{font-size:21px}
  h2{margin-top:20px;font-size:17px}
  .kpis{grid-template-columns:1fr 1fr;gap:8px}
  .kpi{padding:10px}.kpi .v{font-size:17px}
  #fltbox>summary{display:block;cursor:pointer;background:#171a23;border:1px solid #262b36;
    border-radius:10px;padding:9px 12px;font-weight:600;margin-bottom:8px;list-style:none}
  #fltbox>summary::-webkit-details-marker{display:none}
  #fltbox>summary::before{content:"▸ ";color:#6b7280}
  #fltbox[open]>summary::before{content:"▾ "}
  .toolbar{flex-wrap:wrap;gap:7px}
  #catfilter{grid-template-columns:1fr 1fr}
  /* die Diagramme brauchen am Telefon mehr Hoehe, nicht weniger */
  .cbox{height:300px} .cbox.hoch{height:560px}
  table{display:block;overflow-x:auto;max-width:100%}
 }
 .mailbody{white-space:pre-wrap;font-family:inherit;font-size:13px;line-height:1.45;color:#dfe5ee;background:#141823;border:1px solid #232834;border-radius:8px;padding:10px;margin:6px 0;overflow-wrap:anywhere}
</style></head><body><script src="/shared.js"></script><div class=wrap>
<nav><a href="/">✏️ Editor</a><a href="statistik.html" class=active>📊 Statistik</a><a href="/vertraege">📑 Verträge</a><a href="/reisen">🏖️ Reisen</a><a href="/import">📥 Import</a><a href="/vermoegen">💰 Vermögen</a><a href="/vorsorge">🎯 Vorsorge</a></nav>
<h1>📊 Finanz-Statistik <span id=stand class=hint style="font-size:13px;font-weight:400"></span></h1>
<details id=fltbox open><summary>🔎 Filter und Kategorien</summary>
<div class=toolbar>
 <span>Jahr: <select id=yr onchange=render()></select></span>
 <button class=fbtn onclick="toggleFilter()">▾ Kategorien ein/aus</button>
 <button class=fbtn onclick="setCats('all')">alle</button>
 <button class=fbtn onclick="setCats('none')">keine</button>
 <span>📑 <select id=vf onchange=render()><option value=all>alle Buchungen</option>
   <option value=only>nur Verträge</option><option value=none>ohne Verträge</option></select></span>
 <span>🏷️ <select id=lf onchange=render()><option value="">alle Labels</option></select></span>
 <button class=fbtn onclick="resetAll()" title="alle Filter zurücksetzen">⟳ alle Buchungen</button>
 <span class=filterbadge id=fbadge></span>
 <span class=hint>· berücksichtigter Zeitraum __PERIOD__ (<a href="/import">Import</a>) · Filter-Zahlen = Netto über alle Jahre · Balken anklicken → Buchungen</span>
</div>
<div id=catfilter></div>
</details>
<div class=kpis id=kpis></div>
<h2>Einnahmen vs. Ausgaben pro Monat</h2><div class=cbox><canvas id=c1></canvas></div>
<h2>Ausgaben pro Monat nach Kategorie</h2><div class=cbox><canvas id=c2></canvas></div>
<!-- hoch: waagerechte Balken, eine Zeile je Kategorie — braucht echte Hoehe -->
<h2>Kategorie-Ranking (Zeitraum)</h2><div class="cbox hoch"><canvas id=c3></canvas></div>
<h3 id=dh class=hint style="margin-top:14px">Klick auf einen Balken/eine Kategorie zeigt hier die Buchungen.</h3>
<div id=detail></div>
<h2>🏖️ Reisen</h2><table id=trips><tr><th>Reise (Orte)</th><th>Zeit</th><th class=r>Kosten</th></tr></table>
<datalist id=labcat></datalist>
<script>
const D=__DATA__, BT=["Einnahme","Konsum","Sparen"];
const PAL=['#4f8cff','#34d399','#f59e0b','#ef4444','#a78bfa','#22d3ee','#f472b6','#84cc16',
 '#fb923c','#60a5fa','#2dd4bf','#facc15','#c084fc','#fca5a5','#94a3b8','#4ade80','#e879f9','#38bdf8'];
const COL=Object.fromEntries(D.cats.map((c,i)=>[c,PAL[i%PAL.length]]));   // feste Farbe je Kategorie
const fmt=x=>Math.round(x).toLocaleString('de-DE');
const esc=s=>{const d=document.createElement('div');d.textContent=s==null?'':s;return d.innerHTML.replace(/"/g,'&quot;').replace(/'/g,'&#39;');};  // textContent maskiert " nicht — in value="..." waere das eine Luecke
const isImmo=c=>/Immobilie|Kredit\/Immobilie/.test(c);
let charts=[], sel=new Set(D.cats), META={cats:D.cats,labels:[]};   // ausgewählte Kategorien
const yok=m=>{const y=yr.value;return y==='Alle'||m.startsWith(y);};
const cok=t=>sel.has(t.c);
const vok=t=>{const v=vf.value;return v==='all'||(v==='only'?t.vtg:!t.vtg);};   // Vertrags-Filter
const lok=t=>{const l=lf.value;return !l||(','+(t.lab||'')+',').includes(','+l+',');};  // Label-Filter (UND)
const ok=t=>yok(t.m)&&cok(t)&&vok(t)&&lok(t);

// Kategorie-Filter-Panel
function buildFilter(){
 // Zahl = NETTO je Kategorie über alle Jahre (Einnahmen − Ausgaben), nicht Volumen
 const net={}; D.tx.forEach(t=>net[t.c]=(net[t.c]||0)+t.b);
 document.getElementById('catfilter').innerHTML=D.cats.map(c=>{
   const v=net[c]||0;
   return `<label><input type=checkbox value="${esc(c)}" ${sel.has(c)?'checked':''} onchange="onCat(this)">`
    +`<span>${esc(c)}</span><span class="amt ${v<0?'neg':'pos'}">${fmt(v)} €</span></label>`;}).join('');
}
function onCat(el){ el.checked?sel.add(el.value):sel.delete(el.value); render(); }
function setCats(mode){
 if(mode==='all') sel=new Set(D.cats);
 else if(mode==='none') sel=new Set();
 buildFilter(); render();
}
function toggleFilter(){const f=document.getElementById('catfilter');
 f.style.display=f.style.display==='none'?'grid':'none';}

// Aggregation NUR aus gefilterten Buchungen -> KPIs + Charts passen sich an
function agg(){
 const months=D.months.filter(yok), mi={}; months.forEach((m,i)=>mi[m]=i);
 const z=()=>Array(months.length).fill(0);
 const a={ein:z(),kon:z(),spar:z(),fix:z(),catm:{}};
 for(const t of D.tx){
  if(!yok(t.m)||!cok(t)||!vok(t)||!lok(t)||t.ignore) continue; const i=mi[t.m];
  if(t.bt==='Einnahme') a.ein[i]+=t.b;
  else if(t.bt==='Konsum'){ a.kon[i]+=-t.b; (a.catm[t.c]=a.catm[t.c]||z())[i]+=-t.b; }
  else if(t.bt==='Sparen') a.spar[i]+=-t.b;
  if(t.fx) a.fix[i]+=-t.b;
 }
 a.months=months; return a;
}
let curDetail=[];
// D.tx -> kanonisches Buchungs-Objekt für die geteilte Detailtabelle (BK aus /shared.js)
function toCanon(t){return {id:t.id,d:t.d,b:t.b,h:t.h,art:t.art,cat:t.c,status:t.st,src:t.src,
  labels:t.lab,ctx:t.ctx,ignore:t.ignore||0,reviewed:t.reviewed||0,vz:t.vz,vtg:t.vtg,
  prod:t.prod,note:t.note,why:t.why,ml:t.ml,_o:t};}
function detailRows(title, rows){
 document.getElementById('dh').textContent=title+' · '+rows.length+' Buchungen';
 curDetail=rows.map(toCanon);
 BK.renderBookings('detail', curDetail, {onChange:()=>{        // Änderung -> zurück nach D.tx + Charts neu
   curDetail.forEach(r=>{const t=r._o; if(t){t.c=r.cat;t.lab=r.labels;t.st=r.status;
     t.ignore=r.ignore;t.reviewed=r.reviewed;t.note=r.note;}});
   buildFilter(); render();
 }});
 document.getElementById('dh').scrollIntoView({behavior:'smooth',block:'start'});
}
function render(){
 const A=agg(), labels=A.months, sum=a=>a.reduce((x,y)=>x+y,0), n=labels.length||1;
 const nsel=sel.size, badge=document.getElementById('fbadge');
 const parts=[];
 if(nsel!==D.cats.length)parts.push(`${nsel}/${D.cats.length} Kategorien`);
 if(vf.value!=='all')parts.push(vf.value==='only'?'nur Verträge':'ohne Verträge');
 if(lf.value)parts.push('Label: '+lf.value);
 if(yr.value!=='Alle')parts.push('Jahr '+yr.value);
 badge.textContent = parts.length ? '· Filter aktiv: '+parts.join(' · ') : '';
 saveState();
 document.getElementById('kpis').innerHTML=[
  ['Ø Einnahmen/Mon',sum(A.ein)/n],['Ø Ausgaben/Mon',sum(A.kon)/n],['Ø Fixkosten/Mon',sum(A.fix)/n],
  ['Ø Sparen/Mon',sum(A.spar)/n],
  ['Netto-Cashflow',sum(A.ein)-sum(A.kon)-sum(A.spar)]
 ].map(([l,v])=>`<div class=kpi><div class=v>${fmt(v)} €</div><div class=l>${esc(l)}</div></div>`).join('');
 charts.forEach(c=>c.destroy()); charts=[];
 const SCHMAL = window.innerWidth < 900;   // Telefon/Tablet
 charts.push(new Chart(c1,{type:'bar',data:{labels,datasets:[
   {label:'Einnahmen',data:A.ein,backgroundColor:'#34d399'},{label:'Ausgaben',data:A.kon,backgroundColor:'#ef4444'},
   {label:'Sparen',data:A.spar,backgroundColor:'#4f8cff'}]},
   options:{maintainAspectRatio:false,onClick:(e,el)=>{if(!el.length)return;const m=labels[el[0].index],bt=BT[el[0].datasetIndex];
     detailRows(`${bt} · ${m}`, D.tx.filter(t=>t.m===m&&t.bt===bt&&cok(t)&&vok(t)&&lok(t)));},
    plugins:{legend:{labels:{color:'#cbd5e1'}}},scales:{x:{ticks:{color:'#9aa4b2'}},y:{ticks:{color:'#9aa4b2'}}}}}));
 const konCats=Object.keys(A.catm).sort((x,y)=>sum(A.catm[y])-sum(A.catm[x]));
 charts.push(new Chart(c2,{type:'bar',data:{labels,datasets:konCats.map(c=>(
   {label:c,data:A.catm[c],backgroundColor:COL[c]||'#94a3b8'}))},
   options:{maintainAspectRatio:false,onClick:(e,el)=>{if(!el.length)return;const m=labels[el[0].index],cat=konCats[el[0].datasetIndex];
     detailRows(`${cat} · ${m}`, D.tx.filter(t=>t.m===m&&t.c===cat&&vok(t)&&lok(t)));},
    plugins:{legend:{display:!SCHMAL,labels:{color:'#cbd5e1',boxWidth:12,font:{size:10}}}},
    scales:{x:{stacked:true,ticks:{color:'#9aa4b2'}},y:{stacked:true,ticks:{color:'#9aa4b2'}}}}}));
 const curCt=konCats.map(c=>[c,sum(A.catm[c])]).filter(x=>x[1]>0);
 charts.push(new Chart(c3,{type:'bar',data:{labels:curCt.map(x=>x[0]),
   datasets:[{data:curCt.map(x=>x[1]),backgroundColor:curCt.map(x=>COL[x[0]]||'#94a3b8')}]},
   options:{maintainAspectRatio:false,indexAxis:'y',onClick:(e,el)=>{if(!el.length)return;const cat=curCt[el[0].index][0];
     detailRows(`${cat} · Zeitraum`, D.tx.filter(t=>yok(t.m)&&t.c===cat&&vok(t)&&lok(t)));},
    plugins:{legend:{display:false}},scales:{x:{ticks:{color:'#9aa4b2'}},y:{ticks:{color:'#9aa4b2'}}}}}));
 document.getElementById('trips').innerHTML='<tr><th>Reise (Orte)</th><th>Zeit</th><th class=r>Kosten</th></tr>'+
   D.trips.filter(t=>yr.value==='Alle'||t.ym.startsWith(yr.value)).map(t=>
     `<tr><td>${esc(t.orte)}</td><td>${t.ym}</td><td class=r>${fmt(t.kosten)} €</td></tr>`).join('');
}
// Auf Telefon/Tablet startet der Filterblock zugeklappt — sonst muss man an
// zwanzig Kategorie-Kaestchen vorbeiscrollen, bevor das erste Diagramm kommt.
if(window.innerWidth<900)document.getElementById('fltbox').open=false;
const YEARS=[...new Set(D.months.map(m=>m.slice(0,4)))].sort();
['Alle',...YEARS].forEach(y=>{const o=document.createElement('option');o.textContent=y;yr.appendChild(o);});
yr.value=YEARS[YEARS.length-1]||'Alle';   // Fokus aufs aktuelle Jahr
// Label-Filter: alle in den Buchungen vorkommenden Labels (häufigste zuerst -> urlaub/fixkosten/vertrag/Reisenamen oben)
const LABC={}; D.tx.forEach(t=>(t.lab||'').split(',').filter(Boolean).forEach(l=>LABC[l]=(LABC[l]||0)+1));
Object.keys(LABC).sort((a,b)=>LABC[b]-LABC[a]).forEach(l=>{
  const o=document.createElement('option');o.value=l;o.textContent='nur: '+l+' ('+LABC[l]+')';lf.appendChild(o);});
document.getElementById('stand').textContent=`· Stand: ${D.build} · OSM-Branchen erkannt: ${D.osm_n} (von ${D.osm_tot} abgefragt)`;

// Filter merken (Seitenwechsel) / zurücksetzen (F5 oder „alle Buchungen")
const FS=BK.filterState('statistik');
function saveState(){FS.save({yr:yr.value,vf:vf.value,lf:lf.value,sel:[...sel],
  open:document.getElementById('catfilter').style.display!=='none'});}
function restoreState(){const s=FS.load();if(!s)return;
  if(s.yr!=null&&[...yr.options].some(o=>o.value===s.yr))yr.value=s.yr;
  if(s.vf!=null)vf.value=s.vf;
  if(s.lf!=null&&[...lf.options].some(o=>o.value===s.lf))lf.value=s.lf;
  if(Array.isArray(s.sel))sel=new Set(s.sel);
  if(s.open)document.getElementById('catfilter').style.display='grid';}
function resetAll(){sel=new Set(D.cats);yr.value='Alle';vf.value='all';lf.value='';FS.clear();buildFilter();render();}

async function init(){
 try{ await BK.init(); }catch(e){}    // Library (Detailtabelle, Labels, Kategorien) laden
 restoreState();                       // gemerkte Filter wiederherstellen (außer nach hartem Neuladen)
 buildFilter(); render();
}
init();
</script></div></body></html>"""
    period = (MINM+" – "+MAXM) if MINM else ("bis "+MAXM)
    out = (tmpl.replace("__DATA__", json_fuer_script(data))
              .replace("__MAXM__", MAXM).replace("__PERIOD__", period))
    chart_js_bereitstellen()
    p = db.os.path.join(db.BASE, "output", "statistik.html")
    with open(p, "w", encoding="utf-8") as f:
        f.write(out)
    print("geschrieben:", p, "|", len(data["months"]), "Monate,", len(tx), "Buchungen,", len(trips), "Reisen")

if __name__ == "__main__":
    run()

"""Grosse interaktive Liste -> output/liste.html
- Filter nach Kategorie / Label / Freitext
- Kategorie + Labels je Zeile editierbar
- Button 'Aenderungen exportieren' -> feedback.json (zum Lernen via apply_feedback.py)
"""
import json, db, konfig

# Kategorien aus konfig.json — EINE Quelle für Editor, Liste und Statistik.
CATS = konfig.KATEGORIEN

def run():
    con = db.connect()
    rows = con.execute("""
        select t.id, t.datum, t.betrag, coalesce(e.haendler_norm,t.gegenpartei),
               coalesce(e.zahlungsart,''), c.category, c.status, c.source_rule, c.reason,
               coalesce(group_concat(distinct l.label),''),
               coalesce(x.betreff,''), coalesce(x.snippet,''),
               trim(coalesce(t.verwendungszweck,''))
        from transactions t
        join tx_category c on c.tx_id=t.id
        left join tx_enrich e on e.tx_id=t.id
        left join tx_labels l on l.tx_id=t.id
        left join tx_context x on x.tx_id=t.id
        group by t.id order by t.datum desc""").fetchall()
    data = [{"id":r[0],"d":r[1],"b":round(r[2],2),"h":r[3],"art":r[4],"cat":r[5],
             "st":r[6],"src":r[7],"why":r[8],"labels":r[9],
             "ctx":r[10],"ctxs":r[11],"vz":r[12]} for r in rows]
    con.close()

    tmpl = r"""<!doctype html><html lang=de><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1"><title>Buchungen</title>
<style>
 body{font-family:system-ui,Arial,sans-serif;margin:0;background:#0f1117;color:#e6e6e6;font-size:14px}
 .bar{position:sticky;top:0;background:#11141c;padding:12px;border-bottom:1px solid #262b36;display:flex;gap:10px;flex-wrap:wrap;align-items:center;z-index:5}
 select,input{background:#1b1f2a;color:#e6e6e6;border:1px solid #2c323f;border-radius:8px;padding:7px 9px;font-size:14px}
 button{background:#4f8cff;color:#fff;border:0;border-radius:8px;padding:8px 14px;font-weight:600;cursor:pointer}
 table{width:100%;border-collapse:collapse} td,th{padding:7px 9px;border-bottom:1px solid #1e232e;vertical-align:top}
 th{position:sticky;top:56px;background:#11141c;color:#9aa4b2;text-align:left}
 .r{text-align:right;white-space:nowrap} .neg{color:#ff8a8a} .pos{color:#7ee0a0}
 .ctx{color:#9aa4b2;font-size:12px;max-width:380px} .why{color:#6b7280;font-size:11px}
 tr.chg{background:#1d2a1f} .lbl{width:150px} .stat{color:#9aa4b2;margin-left:auto}
 .pill{background:#222838;border-radius:6px;padding:1px 6px;font-size:11px;color:#b9c3d3}
</style></head><body>
<div class=bar>
 <a href="/" style="color:#9aa4b2;text-decoration:none;font-weight:600">✏️ Editor</a>
 <a href="statistik.html" style="color:#9aa4b2;text-decoration:none;font-weight:600">📊 Statistik</a>
 <a href="/vertraege" style="color:#9aa4b2;text-decoration:none;font-weight:600">📑 Verträge</a>
 <a href="/reisen" style="color:#9aa4b2;text-decoration:none;font-weight:600">🏖️ Reisen</a>
 <b style="color:#4f8cff">📋 Liste</b>
 <select id=fcat onchange=render()><option value="">— Kategorie —</option>__CATOPTS__</select>
 <input id=flabel placeholder="Label filtern…" oninput=render() class=lbl>
 <input id=fsearch placeholder="Suche Händler/Kontext…" oninput=render() style="width:240px">
 <button onclick=exp()>⬇ Änderungen exportieren</button>
 <span class=stat id=stat></span>
</div>
<table><thead><tr><th>Datum</th><th class=r>Betrag</th><th>Händler</th><th>Art</th>
<th>Kategorie</th><th>Labels</th><th>Kontext / Beleg</th></tr></thead><tbody id=tb></tbody></table>
<script>
const DATA=__DATA__, CATS=__CATS__, changes={};
const fmt=x=>x.toLocaleString('de-DE',{minimumFractionDigits:2,maximumFractionDigits:2});
function esc(s){const d=document.createElement('div');d.textContent=s==null?'':s;return d.innerHTML;}
function mark(id,cat,labels){changes[id]={kategorie:cat,labels:labels};}
function render(){
 const fc=fcat.value, fl=flabel.value.toLowerCase(), fs=fsearch.value.toLowerCase();
 const tb=document.getElementById('tb'); tb.innerHTML=''; let n=0,sum=0;
 for(const r of DATA){
  if(fc && r.cat!==fc) continue;
  if(fl && !(r.labels||'').toLowerCase().includes(fl)) continue;
  if(fs && !((r.h+' '+r.vz+' '+r.ctx+' '+r.ctxs).toLowerCase().includes(fs))) continue;
  n++; sum+=r.b;
  const tr=document.createElement('tr'); if(changes[r.id])tr.className='chg';
  const opts=CATS.map(c=>`<option${c===(changes[r.id]?.kategorie||r.cat)?' selected':''}>${c}</option>`).join('');
  tr.innerHTML=`<td>${r.d}</td><td class="r ${r.b<0?'neg':'pos'}">${fmt(r.b)}</td>
   <td>${esc(r.h).slice(0,40)}</td><td><span class=pill>${esc(r.art)}</span></td>
   <td><select>${opts}</select></td>
   <td><input class=lbl value="${esc(changes[r.id]?.labels??r.labels)}"></td>
   <td class=ctx>${esc(r.vz).slice(0,170)}${r.ctx?'<br><b>✉ '+esc(r.ctx)+'</b> '+esc(r.ctxs).slice(0,140):''}
       <div class=why>${esc(r.src||'')} · ${esc(r.why||'')} · ${esc(r.st)}</div></td>`;
  const sel=tr.querySelector('select'), inp=tr.querySelector('input');
  sel.onchange=()=>{mark(r.id,sel.value,inp.value);tr.className='chg';};
  inp.onchange=()=>{mark(r.id,sel.value,inp.value);tr.className='chg';};
  tb.appendChild(tr);
 }
 stat.textContent=n+' Buchungen · '+fmt(sum)+' € · '+Object.keys(changes).length+' geändert';
}
function exp(){
 const arr=Object.entries(changes).map(([id,v])=>({tx_id:id,...v}));
 const blob=new Blob([JSON.stringify(arr,null,1)],{type:'application/json'});
 const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='feedback.json';a.click();
}
render();
</script></body></html>"""
    out_html = tmpl.replace("__CATOPTS__", "".join(f"<option>{c}</option>" for c in CATS)) \
                   .replace("__DATA__", json.dumps(data, ensure_ascii=False)) \
                   .replace("__CATS__", json.dumps(CATS, ensure_ascii=False))
    p = db.os.path.join(db.BASE, "output", "liste.html")
    with open(p, "w", encoding="utf-8") as f:
        f.write(out_html)
    print("geschrieben:", p, "|", len(data), "Zeilen")

if __name__ == "__main__":
    run()

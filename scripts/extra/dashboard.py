"""Schlankes Frontend: rendert die DB zu EINER statischen HTML-Datei (output/dashboard.html).
Kein Server. Charts via Chart.js (CDN). Daten als JSON eingebettet.
"""
import json, html, db, konfig

# Nicht-Konsum: Vermögensumschichtung, Kredite, Einnahmen. Eigene Kategorien
# (z.B. "Immobilie X", ein Nebengewerbe) kommen aus konfig.json.
EXCL = ("Sparen/Invest", "Kredit/Immobilie", "Camper",
        "Umbuchung intern", "Einnahme") + tuple(konfig.KAT_KEIN_KONSUM)

def run():
    con = db.connect(); q = con.execute
    konsum_where = f"t.flow='ausgabe' and c.category not in {EXCL}"

    # Monatliche Konsumausgaben
    monat = q(f"""select t.monat, round(sum(-t.betrag),0) from transactions t
        join tx_category c on c.tx_id=t.id where {konsum_where} and t.monat is not null
        group by t.monat order by t.monat""").fetchall()
    # Kategorien (Konsum, gesamt)
    kat = q(f"""select c.category, round(sum(-t.betrag),0) n from transactions t
        join tx_category c on c.tx_id=t.id where {konsum_where}
        group by c.category order by n desc""").fetchall()
    # Reisen
    trips = q("""select l.label, count(distinct l.tx_id), round(sum(-t.betrag),0)
        from tx_labels l join transactions t on t.id=l.tx_id
        where l.label like 'TRIP-%' group by l.label order by l.label""").fetchall()
    # Groesste Konsumausgaben
    big = q(f"""select t.datum, round(-t.betrag,0), e.haendler_norm, c.category
        from transactions t join tx_category c on c.tx_id=t.id
        left join tx_enrich e on e.tx_id=t.id where {konsum_where}
        order by t.betrag asc limit 20""").fetchall()
    # KPIs
    n_monate = len(monat) or 1
    konsum_total = sum(m[1] for m in monat)
    sparen = q("select round(sum(-betrag),0) from transactions t join tx_category c on c.tx_id=t.id where c.category='Sparen/Invest' and t.flow='ausgabe'").fetchone()[0] or 0
    einnahmen = q("select round(sum(betrag),0) from transactions where flow='einnahme'").fetchone()[0] or 0
    fix = q("""select t.monat, sum(-t.betrag) from transactions t join tx_labels l on l.tx_id=t.id and l.label='fixkosten'
        group by t.monat""").fetchall()
    fix_avg = round(sum(f[1] for f in fix)/len(fix)) if fix else 0
    # Status / Qualitaet
    status = dict(q("select status,count(*) from tx_category group by status").fetchall())
    beleg_fehlt = q("select count(distinct tx_id) from tx_labels where label='beleg_fehlt'").fetchone()[0]
    trip_avg = round(sum(t[2] for t in trips)/len(trips)) if trips else 0

    con.close()

    data = {"monat": monat, "kat": kat}
    H = f"""<!doctype html><html lang=de><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>Finanz-Dashboard</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
<style>
 body{{font-family:system-ui,Arial,sans-serif;margin:0;background:#0f1117;color:#e6e6e6}}
 .wrap{{max-width:1100px;margin:0 auto;padding:24px}}
 h1{{font-weight:650}} h2{{margin-top:34px;border-bottom:1px solid #2a2f3a;padding-bottom:6px}}
 .kpis{{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:14px;margin:18px 0}}
 .kpi{{background:#171a23;border:1px solid #262b36;border-radius:12px;padding:16px}}
 .kpi .v{{font-size:26px;font-weight:700}} .kpi .l{{color:#9aa4b2;font-size:13px;margin-top:4px}}
 table{{width:100%;border-collapse:collapse;font-size:14px}}
 td,th{{text-align:left;padding:7px 8px;border-bottom:1px solid #232834}} th{{color:#9aa4b2}}
 .r{{text-align:right}} .tag{{background:#222838;border-radius:6px;padding:2px 7px;font-size:12px;color:#b9c3d3}}
 canvas{{background:#171a23;border-radius:12px;padding:10px;margin-top:10px}}
 .muted{{color:#9aa4b2;font-size:13px}}
</style></head><body><div class=wrap>
<h1>💶 Finanz-Dashboard</h1>
<div class=muted>Erste Version · {n_monate} Monate Daten · Konsum = Ausgaben ohne Sparen/Kredit/Umbuchung</div>
<div class=kpis>
 <div class=kpi><div class=v>{konsum_total/n_monate:,.0f} €</div><div class=l>Ø Konsum / Monat</div></div>
 <div class=kpi><div class=v>{fix_avg:,.0f} €</div><div class=l>Ø Fixkosten / Monat</div></div>
 <div class=kpi><div class=v>{trip_avg:,.0f} €</div><div class=l>Ø pro Reise ({len(trips)} Reisen)</div></div>
 <div class=kpi><div class=v>{sparen:,.0f} €</div><div class=l>Sparen/Invest gesamt</div></div>
 <div class=kpi><div class=v>{einnahmen:,.0f} €</div><div class=l>Einnahmen gesamt</div></div>
</div>

<h2>Konsumausgaben pro Monat</h2><canvas id=mc height=90></canvas>
<h2>Kategorien (Konsum)</h2><canvas id=kc height=120></canvas>

<h2>🏖️ Reisen</h2><table><tr><th>ab</th><th class=r>Buchungen</th><th class=r>Kosten</th></tr>
{''.join(f"<tr><td>{html.escape(t[0].replace('TRIP-',''))}</td><td class=r>{t[1]}</td><td class=r>{t[2]:,.0f} €</td></tr>" for t in trips)}
</table>

<h2>💥 Größte Konsumausgaben</h2><table><tr><th>Datum</th><th>Händler</th><th>Kategorie</th><th class=r>Betrag</th></tr>
{''.join(f"<tr><td>{b[0]}</td><td>{html.escape((b[2] or '')[:40])}</td><td><span class=tag>{html.escape(b[3])}</span></td><td class=r>{b[1]:,.0f} €</td></tr>" for b in big)}
</table>

<h2>🔎 Datenqualität (ehrlich)</h2>
<div class=muted>Status: {html.escape(str(status))} · Belege fehlen (markiert): {beleg_fehlt}</div>

<script>
const D={json.dumps(data)};
new Chart(mc,{{type:'bar',data:{{labels:D.monat.map(x=>x[0]),
 datasets:[{{label:'Konsum €',data:D.monat.map(x=>x[1]),backgroundColor:'#4f8cff'}}]}},
 options:{{plugins:{{legend:{{display:false}}}},scales:{{x:{{ticks:{{color:'#9aa4b2'}}}},y:{{ticks:{{color:'#9aa4b2'}}}}}}}}}});
new Chart(kc,{{type:'bar',data:{{labels:D.kat.map(x=>x[0]),
 datasets:[{{label:'€',data:D.kat.map(x=>x[1]),backgroundColor:'#34d399'}}]}},
 options:{{indexAxis:'y',plugins:{{legend:{{display:false}}}},scales:{{x:{{ticks:{{color:'#9aa4b2'}}}},y:{{ticks:{{color:'#9aa4b2'}}}}}}}}}});
</script>
</div></body></html>"""
    out = db.os.path.join(db.BASE, "output", "dashboard.html")
    open(out, "w", encoding="utf-8").write(H)
    print("geschrieben:", out)

if __name__ == "__main__":
    run()

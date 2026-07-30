"""Erste Auswertungen -> output/report.md + Konsole. Reine DB-Abfragen (schnell)."""
import os, db, konfig
con = db.connect(); q = con.execute
L = []
def p(s=""): L.append(s); print(s)

p("# Finanz-Report (erster Wurf)\n")

p("## Status der Kategorisierung")
for st,n in q("select status,count(*) from tx_category group by status order by 2 desc"):
    p(f"- {st}: {n}")
p("")

p("## Reisen erkannt (Urlaubskosten je Trip)")
rows=q("""select l.label, count(distinct l.tx_id), round(sum(t.betrag),0)
  from tx_labels l join transactions t on t.id=l.tx_id
  where l.label like 'TRIP-%' group by l.label order by l.label""").fetchall()
for lab,n,s in rows:
    p(f"- {lab.replace('TRIP-','ab ')}: {n} Auswärts-Buchungen, **{-s:.0f} €**")
if rows:
    avg=-sum(r[2] for r in rows)/len(rows)
    p(f"\n**Ø Urlaub: {avg:.0f} €** über {len(rows)} Reisen.")
p("")

p("## Größte Einzelausgaben (ohne interne Umbuchungen)")
for d,b,hn,cat in q("""select t.datum,t.betrag,e.haendler_norm,c.category
  from transactions t join tx_category c on c.tx_id=t.id
  left join tx_enrich e on e.tx_id=t.id
  where t.flow='ausgabe' order by t.betrag asc limit 15"""):
    p(f"- {d}  {-b:8.0f} €  [{cat}]  {hn}")
p("")

p("## Größte KONSUM-Ausgaben (ohne Sparen/Kredit/Umbuchung/Einnahme)")
# Eigene Nicht-Konsum-Kategorien (z.B. "Immobilie X") aus konfig.json.
EXCL = ("Sparen/Invest","Kredit/Immobilie","Camper","Umbuchung intern",
        "Einnahme") + tuple(konfig.KAT_KEIN_KONSUM)
for d,b,hn,cat in q(f"""select t.datum,t.betrag,e.haendler_norm,c.category
  from transactions t join tx_category c on c.tx_id=t.id
  left join tx_enrich e on e.tx_id=t.id
  where t.flow='ausgabe' and c.category not in {EXCL} order by t.betrag asc limit 15"""):
    p(f"- {d}  {-b:8.0f} €  [{cat}]  {hn}")
p("")

p("## Kategorien 2025 (Ausgaben)")
for cat,n,s in q("""select c.category,count(*),round(sum(t.betrag),0)
  from transactions t join tx_category c on c.tx_id=t.id
  where t.flow='ausgabe' and t.jahr=2025 group by c.category order by 3"""):
    p(f"- {cat:24} {-s:8.0f} €  ({n})")
p("")

p("## Fixkosten 2025 (Label 'fixkosten')")
fk=q("""select t.monat, round(sum(t.betrag),0) from transactions t
  join tx_labels l on l.tx_id=t.id and l.label='fixkosten'
  where t.jahr=2025 group by t.monat order by 1""").fetchall()
if fk:
    avg=-sum(r[1] for r in fk)/len(fk)
    p(f"- Ø Fixkosten/Monat: **{avg:.0f} €** (über {len(fk)} Monate)")
p("")

p("## Camper gesamt")
for cat in ["Camper"]:
    s=q("select round(sum(t.betrag),0) from transactions t join tx_category c on c.tx_id=t.id where c.category=?",(cat,)).fetchone()[0]
    p(f"- {cat}: {-(s or 0):.0f} €")

os.makedirs(os.path.join(db.BASE,"output"),exist_ok=True)
open(os.path.join(db.BASE,"output","report.md"),"w",encoding="utf-8").write("\n".join(L))
con.close()
print("\n-> output/report.md geschrieben")

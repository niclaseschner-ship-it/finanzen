"""Verträge MECHANISCH (kein LLM), reproduzierbar, Teil der Pipeline.
- derive(con): leitet Verträge aus enrich.ist_vertrag ab -> Tabelle `contracts`
- normalize_months(con): Doppelmonat-Fix für Monatsverträge (deterministisch, idempotent,
  respektiert manuelle datum_override) -> setzt tx_category.eff_monat
Status/Name/Kategorie bleiben über Re-Runs erhalten.
"""
import datetime, hashlib, re
from collections import defaultdict, Counter
import db

# Referenz-/Code-Müll, ab dem der Verwendungszweck abgeschnitten wird (mechanisch)
_CUT = re.compile(r"(?i)\b(eref|mref|cred|creditor|mandate?|mandatsref|kundenreferenz|svwz|"
                  r"iban|bic|abwa|abwe)\b.*$")
_VISA = re.compile(r"(?i)\bvisa\b.*$")
_CODE = re.compile(r"\b(?=[\w./-]*\d)[\w./-]{5,}\b")        # Tokens mit Ziffern (Codes/Refs/Nummern)
_DATE = re.compile(r"\b\d{1,2}\.\d{1,2}\.\d{2,4}\b|\bvom\b")

def clean_zweck(vz):
    """Bank-Verwendungszweck auf die menschlich-lesbare Kernaussage reduzieren
    ('Salary 052026 EREF:…' -> 'Salary', 'Miete' -> 'Miete'). Rein mechanisch."""
    s = vz or ""
    s = _CUT.sub("", s); s = _VISA.sub("", s)
    s = _DATE.sub(" ", s); s = _CODE.sub(" ", s)
    s = re.sub(r"[^0-9A-Za-zÄÖÜäöüß .,/&+-]", " ", s)
    s = re.sub(r"\s+", " ", s).strip(" .,/-")
    if len(s) < 2 or not re.search(r"[A-Za-zÄÖÜäöüß]", s): return ""
    return s[:28].strip()

def dominant_zweck(vzs):
    """Häufigster bereinigter Zweck der Vertragsbuchungen (muster-basiert, robust)."""
    cl = [clean_zweck(v) for v in vzs]
    cnt = Counter(z for z in cl if z)
    if not cnt: return ""
    z, n = cnt.most_common(1)[0]
    return z if n >= max(2, 0.3 * len(cl)) else ""

# Policen-/Vertragsreferenz aus dem Verwendungszweck (KV…/SV…/VS…/KR… + lange Nummer).
# Stabil je Police (ändert sich nicht je Buchung) -> Schlüssel zum Trennen mehrerer Verträge
# auf EINEM Gläubiger (z.B. DKV = 2 Policen, ERGO = Haftpflicht+Hausrat+Rechtsschutz).
_REF = re.compile(r"(?i)\b([A-Z]{2,3})[\s\-./]?(\d{6,})\b")
def policy_ref(vz):
    m = _REF.search(vz or "")
    return (m.group(1) + m.group(2)).upper() if m else ""

def add_month(ym):
    y, m = int(ym[:4]), int(ym[5:7]); m += 1
    if m > 12: m = 1; y += 1
    return f"{y}-{m:02d}"

def sub_month(ym):
    y, m = int(ym[:4]), int(ym[5:7]); m -= 1
    if m < 1: m = 12; y -= 1
    return f"{y}-{m:02d}"

def rhythmus(med):
    # Verträge sind HÖCHSTENS monatlich getaktet (alles Häufigere = Stammladen, kein Vertrag)
    for lo, hi, name in [(24,38,"monatlich"),(52,70,"2-monatlich"),(80,100,"quartalsweise"),
                         (170,200,"halbjährlich"),(330,400,"jährlich")]:
        if lo <= med <= hi: return name
    return "unregelmäßig"

def derive(con):
    prev = {}
    try:   # Entscheidungen erhalten: Status/Name/Kategorie + manueller Aktiv-Override
        prev = {r[0]: (r[1], r[2], r[3], r[4]) for r in
                con.execute("select id,status,name,kategorie,aktiv_user from contracts")}
    except Exception:
        try:   # Migration: alte Tabelle ohne aktiv_user -> Entscheidungen trotzdem behalten
            prev = {r[0]: (r[1], r[2], r[3], None) for r in
                    con.execute("select id,status,name,kategorie from contracts")}
        except Exception:
            pass
    front = con.execute("select max(datum) from transactions").fetchone()[0]
    fd = datetime.date.fromisoformat(front[:10])     # Datenfront = jüngste Buchung
    con.execute("DROP TABLE IF EXISTS contracts")
    con.execute("""CREATE TABLE contracts (
        id TEXT PRIMARY KEY, key_type TEXT, key_val TEXT, name TEXT, kategorie TEXT,
        rhythmus TEXT, betrag_typ REAL, betrag_min REAL, betrag_max REAL, betrag_letzter REAL,
        anzahl INTEGER, erste TEXT, letzte TEXT, naechste TEXT, status TEXT, richtung TEXT,
        zweck TEXT, med_gap INTEGER, aktiv INTEGER, tage_seit_letzter INTEGER, ref TEXT,
        aktiv_user INTEGER, note TEXT)""")
    rows = con.execute("""select e.creditor_id,e.haendler_norm,t.datum,t.betrag,c.category,
        t.verwendungszweck
        from tx_enrich e join transactions t on t.id=e.tx_id
        join tx_category c on c.tx_id=e.tx_id
        where t.flow in ('ausgabe','einnahme')""").fetchall()
    grp = defaultdict(list)
    for cred, hn, datum, betrag, cat, vz in rows:
        key = ("creditor", cred.strip()) if (cred and cred.strip()) else ("haendler", (hn or "").lower())
        grp[key].append((datum, betrag or 0, hn, cat, vz))

    def build_stream(items, cid, kt, kv, ref="", zweck_hint=""):
        """Prüft EINEN (Sub-)Strom mechanisch und liefert das Vertrags-Tupel oder None.
        Mindestanzahl hängt vom Takt ab: jährlich genügen 2, quartalsweise 3, sonst 4 Buchungen."""
        if len(items) < 2: return None
        items = sorted(items)
        dates = [datetime.date.fromisoformat(d[:10]) for d, *_ in items]
        amts = sorted(abs(it[1]) for it in items)
        med_amt = amts[len(amts)//2]
        if med_amt <= 0: return None
        gaps = [g for g in ((dates[i+1]-dates[i]).days for i in range(len(dates)-1)) if g > 0]
        if not gaps: return None
        med_gap = sorted(gaps)[len(gaps)//2]
        if med_gap < 24: return None                    # öfter als monatlich -> kein Vertrag
        rh = rhythmus(med_gap)
        if rh == "unregelmäßig": return None
        need = 2 if med_gap >= 150 else (3 if med_gap >= 80 else 4)   # lange Takte: weniger Belege nötig
        if len(items) < need: return None
        # Wenige Belege (seltener Takt) nur als Vertrag akzeptieren, wenn es ein echtes
        # SEPA-Mandat ist ODER eine Policen-/Vertragsreferenz trägt — sonst sind 2 Karten-
        # zahlungen ~1 Jahr auseinander nur Zufall (Lidl, Buchladen…), kein Vertrag.
        if need < 4 and kt != "creditor" and not any(policy_ref(it[4]) for it in items):
            return None
        span_m = (dates[-1].year*12+dates[-1].month) - (dates[0].year*12+dates[0].month) + 1
        if span_m < min(4, need * 2): return None
        share = sum(1 for a in amts if abs(a-med_amt) <= 0.3*med_amt) / len(amts)
        if share < 0.4: return None                     # dominanter Betrag
        reg = sum(1 for g in gaps if 0.65*med_gap <= g <= 1.5*med_gap) / len(gaps)
        if reg < 0.6: return None                       # regelmäßiger Takt
        name0 = Counter(it[2] for it in items).most_common(1)[0][0]
        cat0 = Counter(it[3] for it in items).most_common(1)[0][0]
        zweck = dominant_zweck([it[4] for it in items]) or zweck_hint
        richtung = "Einnahme" if sum(it[1] for it in items) > 0 else "Ausgabe"
        st, nm, kg, au = prev.get(cid, ("candidate", name0, cat0, None))
        nxt = (dates[-1] + datetime.timedelta(days=med_gap)).isoformat()
        seit = (fd - dates[-1]).days
        # ausgelaufen = mehr als EIN Takt + feste Toleranz (75 T) überfällig. Tolerant bei
        # Monatsverträgen (verpasste Monate ok), streng bei Jahresverträgen (verpasste
        # Verlängerung = aus) — anders als ein prozentualer Faktor, der jährlich zu lasch wäre.
        aktiv = 1 if seit <= med_gap + 75 else 0
        last6 = sorted(abs(it[1]) for it in items
                       if (fd - datetime.date.fromisoformat(it[0][:10])).days <= 183)
        betrag_6m = round(last6[len(last6)//2], 2) if last6 else round(med_amt, 2)
        betrag_letzter = round(abs(items[-1][1]), 2)
        return (cid, kt, kv, nm or name0, kg or cat0, rh, betrag_6m,
                round(amts[0],2), round(amts[-1],2), betrag_letzter, len(items),
                dates[0].isoformat(), dates[-1].isoformat(), nxt, st, richtung, zweck,
                med_gap, aktiv, seit, ref, au, None)

    out = []
    for (kt, kv), items in grp.items():
        base = hashlib.md5((kt + kv).encode()).hexdigest()[:12]
        # Mehrere Policen auf EINEM Gläubiger trennen: nach Referenznummer gruppieren,
        # splitten nur wenn >=2 stabile Refs (je >=2 Belege) mit DEUTLICH versch. Beträgen
        byref = defaultdict(list)
        for it in items: byref[policy_ref(it[4])].append(it)
        named = {r: its for r, its in byref.items() if r and len(its) >= 2}
        reps = {r: sorted(abs(it[1]) for it in its)[len(its)//2] for r, its in named.items()}
        split = (len(named) >= 2 and reps and max(reps.values()) > 1.25 * min(reps.values()))
        if split:
            # größter Strom behält Basis-ID (erhält evtl. vorhandene Entscheidung); andere -> Ref-ID
            order = sorted(named, key=lambda r: (-len(named[r]), -reps[r]))
            for i, r in enumerate(order):
                cid = base if i == 0 else hashlib.md5((kt + kv + "#" + r).encode()).hexdigest()[:12]
                c = build_stream(named[r], cid, kt, kv, ref=r, zweck_hint=r)
                if c: out.append(c)
        else:
            c = build_stream(items, base, kt, kv)
            if c: out.append(c)
    con.executemany("INSERT INTO contracts VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", out)
    return len(out)

def normalize_months(con):
    """Monatsraten dem RICHTIGEN Monat zuordnen, ausgerichtet am typischen Zahltag.
    - Spät-Zahler (typ. Tag >=20): Buchung am Monatsanfang (Tag <=7) gehört zum VORMONAT
      (z.B. Darlehen/Miete am 01. = Rate des Vormonats, nur 1 Tag zu spät).
    - Früh-Zahler (typ. Tag <=10): Buchung am Monatsende (Tag >=24) gehört zum FOLGEMONAT.
    Nur auf die dominante Vertragsrate angewandt (Kleinbeträge auf demselben Konto bleiben),
    deterministisch, idempotent (aus Datum berechnet), manuelle datum_override gewinnt."""
    moves = 0
    # nur EINDEUTIGE Monatsverträge (gesplittete Gläubiger/Policen ausgenommen)
    contracts = con.execute("""select key_type,key_val from contracts
        where rhythmus='monatlich' and status<>'rejected'
        group by key_type,key_val having count(*)=1""").fetchall()
    for kt, kv in contracts:
        col = "creditor_id" if kt == "creditor" else "haendler_norm"
        rows = con.execute(f"""select t.id,t.datum,c.eff_monat,t.betrag from tx_enrich e
            join transactions t on t.id=e.tx_id join tx_category c on c.tx_id=e.tx_id
            where lower(e.{col})=?
              and not exists(select 1 from tx_manual m where m.tx_id=t.id and ifnull(m.datum_override,'')<>'')
            """, (kv.lower(),)).fetchall()
        if len(rows) < 2: continue
        amts = sorted(abs(b) for _, _, _, b in rows)
        dom = amts[len(amts)//2]                              # dominante Rate (Median)
        rec = [(tid, d, eff) for tid, d, eff, b in rows if dom and abs(abs(b)-dom) <= 0.25*dom]
        if len(rec) < 2: continue
        days = sorted(int(d[8:10]) for _, d, _ in rec)
        typ = days[len(days)//2]                              # typischer Zahltag
        for tid, d, eff in rec:
            ym, dd = d[:7], int(d[8:10])
            if typ >= 20 and dd <= 7:     target = sub_month(ym)   # Monatsanfang = Vormonats-Rate
            elif typ <= 10 and dd >= 24:  target = add_month(ym)   # Monatsende = Folgemonats-Rate
            else:                          target = ym
            if target != eff:
                con.execute("update tx_category set eff_monat=? where tx_id=?", (target, tid))
                moves += 1
    return moves

def apply_fixkosten(con):
    """Fixkosten-Label = Buchungen aller NICHT abgelehnten Ausgabe-Verträge (contracts-Tabelle).
    EINE Wahrheitsquelle statt der alten ist_vertrag-Heuristik; Immobilie zählt mit.
    Pro-Buchung-Label -> historisch korrekt (ausgelaufene Verträge haben einfach keine neuen Buchungen)."""
    con.execute("delete from tx_labels where label='fixkosten'")
    seen = set()
    for kt, kv, ref, dom in con.execute("""select key_type,key_val,coalesce(ref,''),betrag_typ from contracts
            where status<>'rejected' and richtung='Ausgabe'"""):
        col = "creditor_id" if kt == "creditor" else "haendler_norm"
        for tid, vz, betr in con.execute(f"""select e.tx_id, t.verwendungszweck, t.betrag from tx_enrich e
                join transactions t on t.id=e.tx_id where lower(e.{col})=?""", ((kv or "").lower(),)):
            if ref and policy_ref(vz or "") != ref: continue          # nur Buchungen DIESER Police
            if dom and abs(abs(betr or 0) - abs(dom)) > 0.35 * abs(dom): continue  # nur nahe der Vertragsrate
            if tid in seen: continue
            seen.add(tid); con.execute("insert into tx_labels values(?,?,?)", (tid, "fixkosten", "contract"))
    return len(seen)

def run():
    con = db.connect()
    n = derive(con); mv = normalize_months(con)
    con.commit(); con.close()
    print(f"Verträge: {n} | Doppelmonat-Normalisierung: {mv} Buchungen verschoben")

if __name__ == "__main__":
    run()
    con = db.connect()
    print(f"\n{'Vertrag':28} {'Rhythmus':12} {'Ø':>8}  Spanne  Richtung | Kategorie")
    for nm,rh,bt,bmin,bmax,kat,ri in con.execute(
        """select name,rhythmus,betrag_typ,betrag_min,betrag_max,kategorie,richtung
           from contracts order by betrag_typ desc limit 30"""):
        print(f"  {nm[:26]:26} {rh:12} {bt:7.0f}  {bmin:.0f}-{bmax:.0f}  {ri:8} | {kat}")
    con.close()

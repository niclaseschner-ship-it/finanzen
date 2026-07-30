"""Anreicherung: extrahiert Signale aus jeder Buchung in tx_enrich.
Rohdaten bleiben unangetastet. Idempotent (komplett neu berechenbar).
"""
import re, datetime
import db

# Hier stand eine zweite HOME-Liste (Heimatorte), die nie benutzt wurde und schon von der
# echten in rules.py abwich ('h.kirch' statt 'h kirch'). Heimatorte stehen jetzt einmal in
# konfig.json; rules.py liest sie. Nicht wieder hier duplizieren.

ENRICH_SCHEMA = """
CREATE TABLE IF NOT EXISTS tx_enrich (
  tx_id TEXT PRIMARY KEY,
  zahlungsart TEXT, haendler_norm TEXT, ort TEXT, ausland INTEGER,
  waehrung_orig TEXT, betrag_orig REAL, kauf_datum TEXT,
  creditor_id TEXT, ref_amazon TEXT, ref_paypal_txn TEXT, paypal_haendler TEXT,
  vertrag_nr TEXT, rechnung_nr TEXT, zeitraum_von TEXT, zeitraum_bis TEXT,
  wiederkehrend INTEGER, ist_vertrag INTEGER
);
"""

def iso(d):  # TT.MM.JJJJ -> ISO
    try: return datetime.datetime.strptime(d, "%d.%m.%Y").strftime("%Y-%m-%d")
    except Exception: return None

def first(pat, s, g=1, fl=0):
    m = re.search(pat, s or "", fl)
    return m.group(g).strip() if m else None

PAYPAL_CRED = "lu96zzz0000000000000000058"

def clean_gp(gp):
    # SEPA-Anhang abschneiden: "... EREF: ... MREF: ... CRED: ..."
    return re.split(r"\s*(?:EREF|MREF|CRED|SVWZ|ABWA)\s*:.*", gp or "", flags=re.I)[0].strip()

def zahlungsart(gp, vz, bt, gid):
    g, v, b = (gp or "").lower(), (vz or "").lower(), (bt or "").lower()
    if "debitkart" in v or "kartenzahlung" in v or "visa" in v: return "Karte"
    if (g.startswith("paypal") or PAYPAL_CRED in (gid or "").lower()
            or PAYPAL_CRED in g or "pplxlul2" in g): return "PayPal"
    if "geldautomat" in v or "bargeld" in v or "auszahlung" in v: return "Bargeld"
    if gid and "eingang" not in b: return "SEPA-Lastschrift"
    if "eingang" in b: return "Eingang/Ueberweisung"
    return "Ueberweisung/Sonstige"

def haendler_norm(gp, art, paypal_h):
    if art == "PayPal" and paypal_h: return paypal_h
    g = gp or ""
    if "/" in g and art == "Karte":
        g = g.rsplit("/", 1)[0]
    g = re.sub(r"[._]+", " ", g)
    return re.sub(r"\s+", " ", g).strip()

def ort_of(gp, art):
    if art == "Karte" and "/" in (gp or ""):
        return re.sub(r"[._]+", " ", gp.rsplit("/", 1)[1]).strip()
    return None

def run():
    con = db.connect()
    con.execute("DROP TABLE IF EXISTS tx_enrich")
    con.executescript(ENRICH_SCHEMA)
    rows = con.execute("""select id,gegenpartei,verwendungszweck,buchungstext,
                          glaeubiger_id,betrag,datum from transactions""").fetchall()
    out = []
    for tid, gp, vz, bt, gid, betrag, datum in rows:
        vz = vz or ""
        gpc = clean_gp(gp)            # gegenpartei ohne SEPA-Anhang
        art = zahlungsart(gp, vz, bt, gid)
        # Referenzen
        ref_amazon = first(r"\b(\d{3}-\d{7}-\d{7})\b", (gp or "") + " " + vz)
        ppm = first(r"PP/\.?\s*([^,]+?),\s*Ihr Einkauf bei", vz) or \
              first(r"Ihr Einkauf bei (.+)$", vz)
        # PayPal-Haendler-Fallback: echter Name steckt in gegenpartei (vor EREF)
        if art == "PayPal" and not ppm and gpc and \
           not gpc.lower().startswith(("paypal", "eref")):
            ppm = gpc
        pptxn = first(r"(\d{6,})/PP\.", vz)
        # Fremdwaehrung
        bo = first(r"Ursprungsbetrag in Fremdw\w*hrung\s*([\d.]+,\d{2})", vz)
        wo = first(r"Ursprungsbetrag in Fremdw\w*hrung\s*[\d.,]+\s*([A-Z]{3})", vz)
        betrag_orig = float(bo.replace(".", "").replace(",", ".")) if bo else None
        # Vertrag / Rechnung
        vertrag = (first(r"Vertragskonto\s*(\d+)", vz) or first(r"\b(KV\d{6,})", vz)
                   or first(r"\bVS\.?\s*([\d./-]{5,})", vz)
                   or first(r"Versicherungsnummer:?\s*(\w+)", vz))
        rechnung = (first(r"\bRG\s*([\w/]+)", vz) or first(r"\bRE\s*(\d{4,})", vz)
                    or first(r"Rechnung[s]?-?\s*(?:nr\.?|nummer)?\s*[:.]?\s*([\w-]{4,})", vz, fl=re.I))
        zv = first(r"(\d{2}\.\d{2}\.\d{4})\s*-\s*\d{2}\.\d{2}\.\d{4}", vz)
        zb = first(r"\d{2}\.\d{2}\.\d{4}\s*-\s*(\d{2}\.\d{2}\.\d{4})", vz)
        kd = first(r"vom\s*(\d{2}\.\d{2}\.\d{4})", vz)
        hn = haendler_norm(gpc, art, ppm)
        ort = ort_of(gpc, art)
        ausland = 1 if (wo and wo != "EUR") else 0
        out.append((tid, art, hn, ort, ausland, wo, betrag_orig, iso(kd) if kd else None,
                    gid, ref_amazon, pptxn, ppm, vertrag, rechnung,
                    iso(zv) if zv else None, iso(zb) if zb else None, 0, 0))
    con.executemany("""INSERT OR REPLACE INTO tx_enrich VALUES
        (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", out)
    # Vertrag vs. wiederkehrend robust bestimmen (pro Gläubiger-ID, sonst Händler):
    #  Vertrag      = regelmäßige Kadenz (wöchentl./monatl.) + ähnliche Beträge
    #                 (Steigerungen/Senkungen erlaubt, aber keine wilden Sprünge)
    #  wiederkehrend= häufiger Händler, aber kein klares Vertragsmuster
    import datetime as _dt
    from collections import defaultdict
    grp = defaultdict(list)
    for tid, datum, betrag, cred, hn in con.execute(
        """select e.tx_id, t.datum, t.betrag, e.creditor_id, e.haendler_norm
           from tx_enrich e join transactions t on t.id=e.tx_id
           where t.flow in ('ausgabe','einnahme')""").fetchall():
        k = ("c", cred.strip()) if (cred and cred.strip()) else ("h", (hn or "").lower())
        if k[1]:
            grp[k].append((tid, datum, abs(betrag or 0)))
    vset, wset = set(), set()
    for items in grp.values():
        if len(items) < 3:
            continue
        items.sort(key=lambda x: x[1])
        dates = [_dt.date.fromisoformat(d[:10]) for _, d, _ in items if d]
        amts = [a for _, _, a in items]
        frequent = len({d.strftime("%Y-%m") for d in dates}) >= 4 or len(items) >= 6
        gaps = [g for g in ((dates[i+1]-dates[i]).days for i in range(len(dates)-1)) if g > 0]
        vertrag = False
        if len(gaps) >= 2:
            med = sorted(gaps)[len(gaps)//2]
            cadence = (26 <= med <= 33) or (6 <= med <= 9)          # monatl. / wöchentl.
            reg = sum(1 for g in gaps if abs(g-med) <= max(3, 0.3*med)) / len(gaps)
            steps = [abs(amts[i+1]-amts[i]) / max(amts[i+1], amts[i], 1)
                     for i in range(len(amts)-1)]
            stable = (sum(1 for s in steps if s <= 0.25) / len(steps)) if steps else 0
            vertrag = bool(cadence and reg >= 0.6 and stable >= 0.6)
        for tid, _, _ in items:
            (vset if vertrag else (wset if frequent else set())).add(tid)
    con.executemany("UPDATE tx_enrich SET ist_vertrag=1 WHERE tx_id=?", [(t,) for t in vset])
    con.executemany("UPDATE tx_enrich SET wiederkehrend=1 WHERE tx_id=?", [(t,) for t in wset])
    con.commit()
    n = con.execute("select count(*) from tx_enrich").fetchone()[0]
    wk = con.execute("select count(*) from tx_enrich where wiederkehrend=1").fetchone()[0]
    vt = con.execute("select count(*) from tx_enrich where ist_vertrag=1").fetchone()[0]
    az = con.execute("select count(*) from tx_enrich where ref_amazon is not null").fetchone()[0]
    pp = con.execute("select count(*) from tx_enrich where paypal_haendler is not null").fetchone()[0]
    print(f"angereichert: {n} | Vertrag: {vt} | wiederkehrend: {wk} | Amazon-Ref: {az} | PayPal-Haendler: {pp}")
    print("Zahlungsarten:", dict(con.execute(
        "select zahlungsart,count(*) from tx_enrich group by zahlungsart").fetchall()))
    con.close()

if __name__ == "__main__":
    run()

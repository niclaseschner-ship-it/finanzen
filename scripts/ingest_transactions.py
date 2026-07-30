"""Kontodaten -> transactions. Wendet die Systemgrenze (Kontenkarte) an.
Idempotent: gleiche Buchung -> gleiche id -> kein Doppeln bei Re-Run.
"""
import csv, hashlib, os, datetime
import db, konfig

CSV_PATH = db.BANK_CSV   # zentrale Config (db.py); per Env FINANZEN_BANK_CSV überschreibbar

# --- Kontenkarte / Systemgrenze -> steht in konfig.json ---------------------
# Wichtigster Teil der Konfiguration: eigene Giro-Konten bilden das "System", ihre
# Transfers untereinander sind keine Ausgaben. Zugeordnete Fremdkonten (Depot, Darlehen,
# Gehalt) zaehlen mit und bekommen eine Vorgabe-Kategorie.
KNOWN_GIRO     = konfig.EIGENE_GIRO
INTERNAL_EXTRA = konfig.WEITERE_INTERN
ACCOUNT_MAP    = konfig.ZUORDNUNG

def tx_key(r):
    return "|".join([r.get("konto",""), r.get("datum",""), r.get("betrag",""),
                     r.get("gegenpartei",""), r.get("verwendungszweck",""),
                     r.get("buchungstext","")])

def tx_id(key, occ):
    # occ = wievielte identische Buchung -> echte Doppelbuchungen bleiben erhalten
    return hashlib.md5((key + "|#" + str(occ)).encode("utf-8")).hexdigest()

def classify(iban, betrag):
    """-> (flow, is_internal, preset_category, preset_note)

    Die IBAN wird GENAUSO normalisiert wie beim Laden der Konfiguration
    (konfig._iban_map): ohne Leerzeichen, groß. Sonst ist der Vergleich asymmetrisch —
    ein Export, der 'DE00 0000 ...' oder Kleinschreibung liefert, träfe keinen Eintrag
    der Kontenkarte, und jede interne Umbuchung zählte als Ausgabe."""
    iban = (iban or "").replace(" ", "").upper().strip()
    if iban in KNOWN_GIRO or iban in INTERNAL_EXTRA:
        note = KNOWN_GIRO.get(iban) or INTERNAL_EXTRA.get(iban)
        return ("intern", 1, "Umbuchung intern", note)
    if iban in ACCOUNT_MAP:
        cat, note = ACCOUNT_MAP[iban]
        flow = "einnahme" if betrag >= 0 else "ausgabe"
        return (flow, 0, cat, note)
    return ("einnahme" if betrag >= 0 else "ausgabe", 0, None, None)

def run():
    db.init()
    con = db.connect()
    with open(CSV_PATH, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f, delimiter=";"))
    n = 0
    from collections import Counter
    fc = Counter(); seen = Counter()
    for r in rows:
        try:
            betrag = float(r.get("betrag") or 0)
        except ValueError:
            betrag = 0.0
        datum = (r.get("datum") or "").strip()
        flow, is_int, cat, note = classify(r.get("iban_gegen"), betrag)
        fc[flow] += 1
        key = tx_key(r); occ = seen[key]; seen[key] += 1
        con.execute(
            """INSERT OR REPLACE INTO transactions
            (id,konto,datum,jahr,monat,betrag,gegenpartei,verwendungszweck,buchungstext,
             iban_gegen,glaeubiger_id,quelle,flow,is_internal,preset_category,preset_note)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (tx_id(key, occ), r.get("konto"), datum,
             int(datum[:4]) if datum[:4].isdigit() else None,
             datum[:7] if len(datum) >= 7 else None,
             betrag, r.get("gegenpartei"), r.get("verwendungszweck"), r.get("buchungstext"),
             (r.get("iban_gegen") or "").strip(), r.get("glaeubiger_id"), r.get("quelle"),
             flow, is_int, cat, note))
        n += 1
    con.execute("INSERT INTO ingest_log VALUES (?,?,?)",
                (datetime.datetime.now().isoformat(timespec="seconds"),
                 "transactions", f"{n} Buchungen, flows={dict(fc)}"))
    con.commit(); con.close()
    print(f"Transaktionen importiert: {n}")
    print("Flows:", dict(fc))

if __name__ == "__main__":
    run()

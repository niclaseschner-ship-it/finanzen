"""Liest die in der Liste exportierte feedback.json und lernt daraus.
- schreibt user_overrides (hoechste Prioritaet, schlaegt alle Regeln)
- erkennt Muster: gleicher Haendler mehrfach gleich korrigiert -> Regel-Vorschlag
Sucht feedback.json in: BASE/, BASE/output/, ~/Downloads/.
"""
import json, os, db

PATHS = [os.path.join(db.BASE, "feedback.json"),
         os.path.join(db.BASE, "output", "feedback.json"),
         os.path.join(os.path.expanduser("~"), "Downloads", "feedback.json")]

def run():
    path = next((p for p in PATHS if os.path.exists(p)), None)
    if not path:
        print("Keine feedback.json gefunden in:", PATHS); return
    with open(path, encoding="utf-8") as f:
        fb = json.load(f)
    con = db.connect()
    con.execute("""CREATE TABLE IF NOT EXISTS user_overrides
        (tx_id TEXT PRIMARY KEY, category TEXT, labels TEXT)""")
    for r in fb:
        con.execute("INSERT OR REPLACE INTO user_overrides VALUES (?,?,?)",
                    (r["tx_id"], r.get("kategorie"), r.get("labels", "")))
    con.commit()
    print(f"Feedback übernommen: {len(fb)} Korrekturen aus {path}")

    # Lernen: Haendler, die mehrfach gleich korrigiert wurden -> Regel-Kandidat
    from collections import defaultdict, Counter
    bym = defaultdict(Counter)
    for r in fb:
        hn = con.execute("select lower(haendler_norm) from tx_enrich where tx_id=?",
                         (r["tx_id"],)).fetchone()
        if hn and hn[0]:
            bym[hn[0]][r.get("kategorie")] += 1
    print("\n=== Regel-Kandidaten (Händler → Kategorie, aus deinem Feedback) ===")
    sugg = []
    for hn, cnt in bym.items():
        cat, n = cnt.most_common(1)[0]
        if n >= 1:
            sugg.append((hn, cat, n))
            print(f'  {n}x  "{hn[:34]}" → {cat}')
    print("\nTipp: bestätigte Muster als SEED2-Zeile in rules.py aufnehmen (\"befördern\").")
    con.close()

if __name__ == "__main__":
    run()

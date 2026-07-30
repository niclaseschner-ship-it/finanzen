"""Laedt KI-Kategorisierungen nach ki_overrides (Long-Tail-Fallback).
Input = JSON im Format aus ki_prompt.md:
  [{"haendler":"...","kategorie":"...","labels":[...],"konfidenz":0.8,"begruendung":"..."}]

Schreibt NUR nach ki_overrides. Die Kategorie landet erst beim naechsten rules.py-Lauf in
tx_category - und auch nur dort, wo keine SEED-Regel getroffen hat (Kette: user_overrides >
Regeln > ki_overrides > OSM > Sonstiges). Die manuelle Schicht bleibt unangetastet.

Aufruf: python ki_load.py <datei.json> [--note ki-2026-07] [--dry]
"""
import json, sys, db

def run(path, note="ki", dry=False):
    with open(path, encoding="utf-8") as f:
        rows = json.load(f)
    if isinstance(rows, dict): rows = [rows]
    con = db.connect()
    con.execute("""CREATE TABLE IF NOT EXISTS ki_overrides
        (haendler_norm TEXT PRIMARY KEY, category TEXT, labels TEXT, confidence REAL, note TEXT,
         begruendung TEXT)""")
    try: con.execute("ALTER TABLE ki_overrides ADD COLUMN begruendung TEXT")   # Migration
    except Exception: pass
    cats = set(r[0] for r in con.execute("select name from cats_catalog"))
    # Haendler muessen EXAKT haendler_norm treffen, sonst greift der Eintrag stillschweigend
    # nie. Deshalb hart gegen tx_enrich pruefen statt hoffen.
    known = set(r[0] for r in con.execute(
        "select distinct lower(haendler_norm) from tx_enrich where coalesce(haendler_norm,'')<>''"))
    ok, bad_cat, unknown, offen = [], [], [], []
    for r in rows:
        h = (r.get("haendler") or "").strip().lower()
        cat = (r.get("kategorie") or "").strip()
        if not h: continue
        if cat not in cats: bad_cat.append((h, cat)); continue
        # 'Sonstiges' ist KEINE Zuordnung, sondern ein Nicht-Ergebnis. Wuerde man es laden,
        # springt der Status von 'unkategorisiert' auf 'ki-vorschlag' und die Buchung fiele
        # aus der Offen-Liste - ungeklaert, aber unsichtbar. Also draussen lassen.
        if cat == "Sonstiges": offen.append(h); continue
        if h not in known: unknown.append(h); continue
        lab = r.get("labels") or []
        lab = ",".join(l.strip() for l in (lab if isinstance(lab, list) else str(lab).split(",")) if l.strip())
        beg = (r.get("begruendung") or "").strip()
        if not beg:
            print(f"  OHNE BEGRUENDUNG: '{h}' -> laedt, ist aber im Editor nicht pruefbar")
        ok.append((h, cat, lab, float(r.get("konfidenz") or 0.6), note, beg))
    for h, c in bad_cat:      print(f"  UNBEKANNTE KATEGORIE '{c}' bei '{h}' -> uebersprungen")
    for h in unknown:         print(f"  KEIN HAENDLER '{h}' in tx_enrich -> uebersprungen (Name exakt?)")
    if offen: print(f"  {len(offen)}x 'Sonstiges' -> nicht geladen, bleiben sichtbar offen")
    if dry:
        print(f"DRY-RUN: {len(ok)} wuerden geschrieben, "
              f"{len(bad_cat)+len(unknown)} verworfen, {len(offen)} bewusst offen")
    else:
        con.executemany("""INSERT OR REPLACE INTO ki_overrides
            (haendler_norm,category,labels,confidence,note,begruendung) VALUES (?,?,?,?,?,?)""", ok)
        con.commit()
        print(f"ki_overrides: {len(ok)} geschrieben (note={note}), "
              f"{len(bad_cat)+len(unknown)} verworfen, {len(offen)} bewusst offen")
        print("Jetzt run_all.py - erst danach stehen die Kategorien in der Statistik.")
    con.close()
    return len(ok)

if __name__ == "__main__":
    a = sys.argv[1:]
    if not a: print(__doc__); sys.exit(1)
    note = a[a.index("--note") + 1] if "--note" in a else "ki"
    run(a[0], note=note, dry="--dry" in a)

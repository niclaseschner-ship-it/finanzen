#!/usr/bin/env python3
"""Schritt 1 der Pipeline: alle Kontoexporte einlesen und zu EINER CSV vereinheitlichen.

Liest jede `*.csv` aus dem Eingangsordner (`db.BANK_DIR`) und schreibt einen
vereinheitlichten Datensatz nach `db.BANK_CSV`. GLS- und DKB-Format werden am
Kopf der Datei automatisch erkannt.

Überlappende Exporte desselben Kontos (typisch: jeder Download enthält die
letzten Monate erneut) werden dedupliziert, ohne echte Doppelbuchungen zu
verlieren — siehe Kommentar in `run()`.

Aufruf:  python parse_konten.py        (oder als Teil von run_all.py)
"""
import csv, glob, os, re, sys
import db, konfig

# Pfade kommen aus der zentralen Config (db.py), nicht aus der Lage dieser Datei.
# So liegt der Eingangsordner dort, wo der Nutzer ihn haben will (Env FINANZEN_BANK).
KONTEN = db.BANK_DIR
OUT    = db.BANK_CSV

# IBAN -> sprechender Kontoname (aus konfig.json). Ohne Treffer: Bank + letzte 4 Stellen
# der IBAN, d.h. unbekannte Konten funktionieren, heißen nur weniger schön.
KONTO_NAMES = konfig.KONTO_NAMEN

def read_text(path):
    with open(path, "rb") as f:
        raw = f.read()
    txt = raw.decode("utf-8-sig", errors="replace")
    # Doppelt kodierte Umlaute (Ã¤, â¬) reparieren
    if "Ã" in txt or "â¬" in txt:
        try:
            txt = txt.encode("latin-1", "ignore").decode("utf-8", "ignore")
        except Exception:
            pass
    return txt

def num(s):
    s = (s or "").strip().replace("\xa0", "").replace(" ", "")
    if not s:
        return None
    s = s.replace(".", "").replace(",", ".")
    try:
        return round(float(s), 2)
    except ValueError:
        return None

def iso_date(s):
    s = (s or "").strip()
    m = re.match(r"(\d{2})\.(\d{2})\.(\d{2,4})$", s)
    if not m:
        return s
    d, mo, y = m.groups()
    if len(y) == 2:
        y = "20" + y
    return f"{y}-{mo}-{d}"

def parse_gls(txt, fname):
    rows = list(csv.reader(txt.splitlines(), delimiter=";"))
    out = []
    for r in rows[1:]:
        if len(r) < 13 or not r[4].strip():
            continue
        iban_own = r[1].strip()
        out.append({
            "konto": KONTO_NAMES.get(iban_own, "GLS-" + iban_own[-4:]),
            "datum": iso_date(r[4]),
            "betrag": num(r[11]),
            "gegenpartei": r[6].strip(),
            "verwendungszweck": r[10].strip(),
            "buchungstext": r[9].strip(),
            "iban_gegen": r[7].strip(),
            "glaeubiger_id": r[16].strip() if len(r) > 16 else "",
            "quelle": fname,
        })
    return out

def parse_dkb(txt, fname):
    lines = txt.splitlines()
    iban_own = ""
    hdr_idx = None
    for i, ln in enumerate(lines):
        if ln.startswith('"Girokonto"') or ln.startswith('"Kontonummer"'):
            parts = next(csv.reader([ln], delimiter=";"))
            if len(parts) > 1:
                iban_own = parts[1].strip()
        if "Buchungsdatum" in ln and "Verwendungszweck" in ln:
            hdr_idx = i
            break
    if hdr_idx is None:
        return []
    rows = list(csv.reader(lines[hdr_idx:], delimiter=";"))
    head = rows[0]
    col = {name.strip(): k for k, name in enumerate(head)}
    def g(r, key):
        i = col.get(key)
        return r[i].strip() if i is not None and i < len(r) else ""
    betrag_key = next((k for k in col if k.startswith("Betrag")), "Betrag (€)")
    out = []
    for r in rows[1:]:
        if len(r) < 3 or not g(r, "Buchungsdatum"):
            continue
        # Vorgemerkte Umsaetze sind noch nicht final: Datum und Empfaengertext aendern
        # sich beim Buchen. Sie mitzunehmen erzeugt beim naechsten Export eine zweite
        # Zeile, die die Dedup nicht als dieselbe Buchung erkennt (anderer Schluessel).
        if g(r, "Status").lower().startswith("vorgemerkt"):
            continue
        out.append({
            "konto": KONTO_NAMES.get(iban_own, "DKB-" + iban_own[-4:]),
            "datum": iso_date(g(r, "Buchungsdatum")),
            "betrag": num(g(r, betrag_key)),
            "gegenpartei": g(r, "Zahlungsempfänger*in") or g(r, "Zahlungspflichtige*r"),
            "verwendungszweck": g(r, "Verwendungszweck"),
            "buchungstext": g(r, "Umsatztyp"),
            "iban_gegen": g(r, "IBAN"),
            "glaeubiger_id": g(r, "Gläubiger-ID"),
            "quelle": fname,
        })
    return out

def format_of(txt):
    """'gls' | 'dkb' — am Kopf der Datei erkannt (wie in run())."""
    head = txt.splitlines()[0] if txt else ""
    return "gls" if "Auftragskonto" in head else "dkb"

def eigene_iban(txt):
    """IBAN des Kontos, DEM der Export gehoert (nicht die der Gegenseite).
    Wird fuer die Einrichtung gebraucht: daraus entsteht die Kontenkarte.
    GLS schreibt sie in jede Datenzeile, DKB einmal in den Kopf."""
    if format_of(txt) == "gls":
        for r in list(csv.reader(txt.splitlines(), delimiter=";"))[1:]:
            if len(r) > 1 and r[1].strip():
                return r[1].strip()
        return ""
    for ln in txt.splitlines():
        if ln.startswith('"Girokonto"') or ln.startswith('"Kontonummer"'):
            parts = next(csv.reader([ln], delimiter=";"))
            if len(parts) > 1:
                return parts[1].strip()
    return ""

def _norm_partner(s):
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())

def _selber_partner(a, b):
    """Meinen zwei Empfaengertexte denselben Haendler? Entweder steckt der eine im
    anderen ('EDEKA' in 'M14.EDEKA.BAUR/LITZELSTETTEN') oder beide teilen einen langen
    gemeinsamen Anfang ('anthropicclaudesub...')."""
    na, nb = _norm_partner(a), _norm_partner(b)
    if not na or not nb:
        return False
    if na in nb or nb in na:
        return True
    i = 0
    while i < min(len(na), len(nb)) and na[i] == nb[i]:
        i += 1
    return i >= 6

def kartentext_vereinheitlichen(rows):
    """Sorgt fuer EINEN Anzeigenamen je Buchung, wenn die Bank ihn zwischendurch
    umgeschrieben hat: aus 'EDEKA.AKTIV.MARKT/KIRCHZARTEN' wird spaeter 'EDEKA Aktiv
    Markt'. Der lesbarere Text gewinnt.

    Fuer die Wiedererkennung ist das NICHT mehr noetig — der Schluessel in key() und in
    ingest_transactions.tx_key() kommt ohne den Empfaengertext aus. Ohne diesen Schritt
    haenge es aber vom Zufall ab, welcher der beiden Texte in der Anzeige landet.

    Die Anzahl aendert sich hier nicht: zwei echte gleiche Zahlungen bleiben zwei Zeilen,
    darueber entscheidet die Max-pro-Datei-Regel in run()."""
    from collections import defaultdict
    grp = defaultdict(list)
    for r in rows:
        if (r.get("iban_gegen") or "").strip():
            grp[(r["konto"], r["datum"], r["betrag"], r["iban_gegen"])].append(r)
    angeglichen = 0
    for mitglieder in grp.values():
        if len(mitglieder) < 2:
            continue
        if len({r["quelle"] for r in mitglieder}) < 2:
            continue                       # nur aus EINER Datei -> echte Doppelzahlung
        texte = {_norm_partner(r["gegenpartei"]) for r in mitglieder}
        if len(texte) < 2:
            continue                       # schon einheitlich
        basis = mitglieder[0]["gegenpartei"]
        if not all(_selber_partner(basis, r["gegenpartei"]) for r in mitglieder[1:]):
            continue                       # verschiedene Haendler -> nicht anfassen
        # Der lesbarste Text gewinnt: am wenigsten Punkte und Schraegstriche.
        wahl = min(mitglieder,
                   key=lambda r: (len(re.findall(r"[./]", r["gegenpartei"] or "")),
                                  -len(r["gegenpartei"] or "")))["gegenpartei"]
        for r in mitglieder:
            if r["gegenpartei"] != wahl:
                r["gegenpartei"] = wahl
                angeglichen += 1
    if angeglichen:
        print(f"Kartentext vereinheitlicht: {angeglichen} Zeilen "
              f"(sonst zaehlten sie als neue Buchung)")

def lese_alle():
    """Alle Exporte aus KONTEN als (dateiname, format, eigene_iban, zeilen).
    Getrennt von run(), damit die Einrichtung die Rohdaten ansehen kann, ohne
    etwas zu schreiben oder eine Datenbank zu brauchen."""
    out = []
    for path in sorted(glob.glob(os.path.join(KONTEN, "*.csv"))):
        fname = os.path.basename(path)
        txt = read_text(path)
        fmt = format_of(txt)
        rows = parse_gls(txt, fname) if fmt == "gls" else parse_dkb(txt, fname)
        out.append((fname, fmt, eigene_iban(txt), rows))
    return out

def run():
    files = sorted(glob.glob(os.path.join(KONTEN, "*.csv")))
    if not files:
        # Kein Abbruch, wenn schon eine zusammengeführte CSV existiert: dann war der
        # Eingang nur leer (z.B. Re-Run ohne neuen Export) und die Pipeline kann mit
        # dem bisherigen Stand weiterlaufen. Ohne beides ist es ein echter Fehler.
        if os.path.exists(OUT):
            print(f"Keine CSV in {KONTEN} — nutze bestehende {os.path.basename(OUT)} weiter.")
            return
        raise RuntimeError(
            f"Keine Kontoexporte gefunden und keine bestehende {OUT}.\n"
            f"Bitte Bank-CSVs ablegen in: {KONTEN}\n"
            f"(Ordner umstellbar über die Umgebungsvariable FINANZEN_BANK.)")
    all_rows = []
    leer = []
    dateien_info = []
    for path in files:
        fname = os.path.basename(path)
        txt = read_text(path)
        fmt = format_of(txt)
        rows = parse_gls(txt, fname) if fmt == "gls" else parse_dkb(txt, fname)
        dateien_info.append((fname, fmt, eigene_iban(txt), rows))
        print(f"{fname}: {len(rows)} Buchungen")
        if not rows:
            leer.append(fname)
        all_rows.extend(rows)
    # Eine Datei, aus der NICHTS gelesen wurde, ist fast immer ein nicht unterstütztes
    # Bankformat — und das darf nicht als Erfolg durchgehen. Vorher lief die Pipeline
    # mit Exit-Code 0 weiter und zeigte (aus alten Daten) plausible Zahlen.
    if leer:
        print(f"WARNUNG: keine Buchungen gelesen aus: {', '.join(leer)}")
        print("         Vermutlich ein nicht unterstütztes Format (erkannt werden DKB und GLS).")
    if not all_rows:
        raise RuntimeError(
            f"Aus {len(files)} Datei(en) in {KONTEN} wurde keine einzige Buchung gelesen.\n"
            f"Betroffen: {', '.join(leer)}\n"
            f"Erkannt werden die CSV-Exporte von DKB und GLS. Passt das Format nicht, "
            f"muss parse_konten.py erweitert werden.")

    # Beträge, die sich nicht lesen lassen (fremdes Zahlenformat, Währungszeichen),
    # fielen bisher stillschweigend weg -> Ausgaben zu niedrig, ohne jeden Hinweis.
    unlesbar = [r for r in all_rows if r["betrag"] is None]
    if unlesbar:
        print(f"WARNUNG: {len(unlesbar)} Buchung(en) ohne lesbaren Betrag übersprungen, z.B.:")
        for r in unlesbar[:3]:
            print(f"         {r.get('datum')} {r.get('gegenpartei','')[:40]} ({r.get('quelle')})")
    all_rows = [r for r in all_rows if r["betrag"] is not None]
    from collections import defaultdict, Counter
    kartentext_vereinheitlichen(all_rows)
    # Robuste Dedup bei ueberlappenden Exporten desselben Kontos:
    # behalte pro Transaktion die MAX-Anzahl aus EINER Datei.
    # -> echte Doppelbuchungen (in jedem Export 2x) bleiben; Overlap-Dubletten fallen weg.
    def key(r):
        # Dieselbe Identitaet wie ingest_transactions.tx_key: nur Felder, die die Bank
        # nicht nachtraeglich umschreibt. Der Empfaengertext gehoert ausdruecklich NICHT
        # dazu — genau daran scheiterte die Dedup bisher.
        return (r["konto"], r["datum"], r["betrag"], (r["iban_gegen"] or "").strip())
    per_file = defaultdict(Counter)
    rep = {}
    for r in all_rows:
        per_file[r["quelle"]][key(r)] += 1
        rep.setdefault(key(r), r)
    maxc = {}
    for c in per_file.values():
        for k, n in c.items():
            if n > maxc.get(k, 0):
                maxc[k] = n
    before = len(all_rows)
    all_rows = []
    for k, n in maxc.items():
        all_rows.extend([rep[k]] * n)
    print(f"Dedup ueberlappende Exporte: {before} -> {len(all_rows)}")
    # Konten, für die ein Export vorliegt, die aber in keiner Rubrik der Kontenkarte
    # stehen. Das ist der häufigste Einrichtungsfehler und bisher völlig unsichtbar:
    # ohne Eintrag zählen Umbuchungen von/zu diesem Konto als echte Ausgaben.
    bekannt = set(konfig.KONTO_NAMEN) | set(konfig.ZUORDNUNG)
    fehlend = sorted({iban for _f, _fmt, iban, _r in dateien_info if iban and iban not in bekannt})
    if fehlend:
        print("WARNUNG: Für diese Konten liegt ein Export vor, sie stehen aber in keiner")
        print("         Rubrik der konfig.json (eigene_giro / weitere_intern / zuordnung):")
        for iban in fehlend:
            print(f"           {iban}")
        print("         Solange sie fehlen, zählen eigene Umbuchungen als Ausgaben.")

    all_rows.sort(key=lambda r: (r["datum"], r["konto"]), reverse=True)
    cols = ["konto", "datum", "betrag", "gegenpartei", "verwendungszweck",
            "buchungstext", "iban_gegen", "glaeubiger_id", "quelle"]
    os.makedirs(os.path.dirname(OUT), exist_ok=True)   # frischer Clone hat den Ordner nicht
    with open(OUT, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=cols, delimiter=";")
        w.writeheader()
        w.writerows(all_rows)
    print(f"\n{len(all_rows)} Buchungen -> {OUT}")

if __name__ == "__main__":
    try:
        run()
    except RuntimeError as e:
        print(e); sys.exit(1)

#!/usr/bin/env python3
"""Einrichtung: erzeugt `konfig.json` aus den vorhandenen Kontoexporten.

Die App braucht keine Installation (nur Python 3.10+), aber sie braucht eine
Kontenkarte: welche IBAN ist ein eigenes Girokonto, welche ist Depot/Darlehen/Gehalt.
Das steht in keiner CSV — es weiß nur der Mensch. Dieses Skript liest alles aus den
Exporten heraus, was maschinell erkennbar ist, und fragt den Rest.

  python einrichten.py            # interaktiv, schreibt konfig.json
  python einrichten.py --pruefen  # nur zeigen, was in den Exporten steht (schreibt nichts)
  python einrichten.py --mail     # nur den Mail-Teil (Thunderbird -> Belege)

Der Mail-Teil ist optional: E-Mails sind ausschließlich Beleg-Kontext ("was war in
dem Amazon-Paket"), keine Buchungsquelle. Ohne sie funktioniert alles, nur die
Detailspalte bleibt leerer.
"""
import json, os, re, shutil, subprocess, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import db, enrich, parse_konten, rules

KONFIG   = os.path.join(db.BASE, "konfig.json")
BEISPIEL = os.path.join(db.BASE, "konfig.beispiel.json")

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


# ---- Ein-/Ausgabe ----------------------------------------------------------

def kopf(t):
    print(f"\n{t}\n{'-' * len(t)}")

def frage(text, default=""):
    """Eingabe mit Vorgabe. Leere Eingabe -> Vorgabe (die häufigste Antwort)."""
    hint = f" [{default}]" if default else ""
    try:
        a = input(f"{text}{hint}: ").strip()
    except EOFError:
        a = ""
    return a or default

def ja_nein(text, default=True):
    d = "J/n" if default else "j/N"
    a = frage(f"{text} ({d})", "").lower()
    if not a:
        return default
    return a.startswith(("j", "y"))

def liste_frage(text, vorschlag):
    """Komma-Liste bestätigen oder ersetzen."""
    print(f"  Vorschlag: {', '.join(vorschlag) if vorschlag else '(keiner)'}")
    a = frage(f"  {text} (Enter = übernehmen, sonst Komma-Liste)", "")
    if not a:
        return list(vorschlag)
    return [s.strip() for s in a.split(",") if s.strip()]


# ---- Inventar aus den Exporten --------------------------------------------

def inventar():
    """Was steht in den Kontoexporten? Rein lesend, ohne Datenbank."""
    dateien = parse_konten.lese_alle()
    if not dateien:
        return None
    eigene = {}      # IBAN des Kontos, dem der Export gehört -> [Dateien, Buchungen]
    gegen = {}       # IBAN der Gegenseite -> Zähler/Summe/Namen
    orte = {}        # Ort -> {n, monate}: die Monate entscheiden über Heimat vs. Urlaub
    monate = set()
    for fname, fmt, iban_own, rows in dateien:
        if iban_own:
            e = eigene.setdefault(iban_own, {"fmt": fmt, "dateien": [], "n": 0})
            e["dateien"].append(fname)
            e["n"] += len(rows)
        for r in rows:
            gi = (r.get("iban_gegen") or "").strip().upper()
            if gi:
                g = gegen.setdefault(gi, {"n": 0, "summe": 0.0, "namen": {}})
                g["n"] += 1
                g["summe"] += r.get("betrag") or 0.0
                nm = (r.get("gegenpartei") or "").strip()
                if nm:
                    g["namen"][nm] = g["namen"].get(nm, 0) + 1
            monat = (r.get("datum") or "")[:7]
            if monat:
                monate.add(monat)
            art = enrich.zahlungsart(r.get("gegenpartei"), r.get("verwendungszweck"),
                                     r.get("buchungstext"), r.get("glaeubiger_id"))
            ort = enrich.ort_of(r.get("gegenpartei"), art)
            if ort:
                o = re.sub(r"\s+", " ", ort).strip().lower()
                if len(o) >= 4 and not _kein_ort(o):
                    e = orte.setdefault(o, {"n": 0, "monate": set()})
                    e["n"] += 1
                    if monat:
                        e["monate"].add(monat)
    return {"dateien": dateien, "eigene": eigene, "gegen": gegen,
            "orte": orte, "monate": monate}


# Ortsfelder aus dem Kartentext enthalten auch Nicht-Orte: Online-Händler schreiben
# ihre Domain hin, und Automaten/zentrale Abrechnungsstellen einen immer gleichen Ort,
# an dem man nie war (rules.TRIP_EXC_ORT kennt die schon für die Reise-Erkennung).
def _kein_ort(o):
    if any(x in o for x in rules.TRIP_EXC_ORT):
        return True
    return bool(re.search(r"\b(com|net|de|www|org|app|io)\b", o))


def heimat_vorschlag(inv, min_anteil=0.25, max_n=8):
    """Heimatorte an der Verteilung über die MONATE erkennen, nicht an der Anzahl.
    Zuhause kauft man das ganze Jahr über ein; ein Urlaubsort hat viele Buchungen in
    zwei Wochen und danach nie wieder. Reine Häufigkeit würde genau das verwechseln."""
    gesamt = len(inv["monate"]) or 1
    kand = [(o, e) for o, e in inv["orte"].items()
            if len(e["monate"]) >= max(3, gesamt * min_anteil)]
    return [o for o, _ in sorted(kand, key=lambda x: -x[1]["n"])[:max_n]]

def top_namen(g, k=2):
    return ", ".join(n for n, _ in sorted(g["namen"].items(), key=lambda x: -x[1])[:k])

def ist_sammelkonto(g):
    """Sammel-/Durchlaufkonten der Bank (Kartenzahlungen, PayPal) sehen aus wie ein
    wichtiges Gegenkonto, sind aber keins: unter EINER IBAN laufen hunderte Händler.
    Erkennbar an der Zahl verschiedener Namen — würde man sie als eigenes Konto
    markieren, fielen alle Kartenzahlungen aus der Auswertung."""
    return len(g["namen"]) >= 10

def sammel_hinweis(g):
    return "  <- Sammelkonto, überspringen" if ist_sammelkonto(g) else ""

def zeige_inventar(inv):
    kopf(f"Gefunden in {db.BANK_DIR}")
    for fname, fmt, iban_own, rows in inv["dateien"]:
        print(f"  {fname}  [{fmt}]  {len(rows)} Buchungen  {iban_own or '(IBAN unklar)'}")
    kopf("Konten, denen die Exporte gehören")
    for iban, e in sorted(inv["eigene"].items(), key=lambda x: -x[1]["n"]):
        print(f"  {iban}  {e['n']:5} Buchungen  [{e['fmt']}]")
    kopf("Häufigste Gegenkonten (Kandidaten für die Kontenkarte)")
    print("  'Namen' = wie viele verschiedene Zahlungsempfänger unter der IBAN liefen.")
    print("  Viele Namen = Sammelkonto der Bank (Kartenzahlungen, PayPal) — kein eigenes Konto.")
    for iban, g in kandidaten(inv):
        print(f"  {iban}  {g['n']:4}x  {g['summe']:11.2f} €  "
              f"{len(g['namen']):4} Namen  {top_namen(g, 1)[:40]}{sammel_hinweis(g)}")
    gesamt = len(inv["monate"]) or 1
    kopf(f"Orte aus Kartenzahlungen ({gesamt} Monate im Zeitraum)")
    print("  'Monate' = in wie vielen verschiedenen Monaten dort gezahlt wurde.")
    print("  Viele Monate = Alltag/zuhause. Wenige Monate trotz vieler Buchungen = Urlaub.")
    vorschlag = set(heimat_vorschlag(inv))
    for o, e in sorted(inv["orte"].items(), key=lambda x: -x[1]["n"])[:15]:
        marke = " <- Heimat?" if o in vorschlag else ""
        print(f"  {o:28} {e['n']:4}x  in {len(e['monate']):2} Monaten{marke}")

def kandidaten(inv, min_n=3, min_summe=500):
    """Gegenkonten, die eine Zuordnung wert sind: oft genutzt ODER viel Geld.
    Ein Depot fällt über die Summe auf (wenige, große Buchungen), die Miete über
    die Anzahl. Beides mitnehmen, sonst fehlt das eine oder das andere."""
    aus = [(i, g) for i, g in inv["gegen"].items()
           if g["n"] >= min_n or abs(g["summe"]) >= min_summe]
    return sorted(aus, key=lambda x: -abs(x[1]["summe"]))[:25]


# ---- Interaktive Einrichtung ----------------------------------------------

def standard_kategorien():
    try:
        with open(BEISPIEL, encoding="utf-8") as f:
            return [k for k in json.load(f).get("kategorien", []) if k]
    except Exception:
        return ["Lebensmittel/Drogerie", "Mobilität", "Wohnen", "Einnahme",
                "Sparen/Invest", "Kredit/Immobilie", "Umbuchung intern", "Sonstiges"]

def bankname(fmt, iban):
    return f"{fmt.upper()}-{iban[-4:]}" if iban else fmt.upper()

def einrichten(inv):
    kfg = {"_hinweis": "Erzeugt von scripts/einrichten.py. Bleibt lokal (siehe .gitignore)."}

    kopf("1/5  Haushalt")
    name = frage("  Name des Haushalts (erscheint in der Vermögensansicht)", "Mein Haushalt")
    print("\n  Eigene Nachnamen und die von Vermietern/WG/Familie.")
    print("  Zweck: verhindert, dass Privatmails als Beleg an einer Buchung landen.")
    namen = [s.strip().lower() for s in frage("  Namen (Komma-Liste)", "").split(",") if s.strip()]
    print("\n  Heimatregion: ein Einkauf hier gilt als 'zuhause' und beendet eine Reise.")
    print("  Ohne diese Liste ist der Alltag eine Dauerreise.")
    heimat = liste_frage("Heimatorte", heimat_vorschlag(inv))
    ohne_wert = liste_frage("Orte, die als Suchwort nichts unterscheiden (Region, Stadt "
                            "eigener Immobilien)", [])
    kfg["haushalt"] = {"name": name, "eigene_namen": namen,
                       "heimat_orte": heimat, "orte_ohne_suchwert": ohne_wert}

    kopf("2/5  Kategorien")
    kats = liste_frage("Kategorien", standard_kategorien())
    kfg["kategorien"] = kats
    print(f"  -> {len(kats)} Kategorien")

    kopf("3/5  Eigene Girokonten (die Systemgrenze)")
    print("  Überweisungen zwischen diesen Konten sind keine Ausgaben.")
    print("  Fehlt hier ein Konto, ist die Ausgabenstatistik zu hoch.\n")
    giro = {}
    for iban, e in sorted(inv["eigene"].items(), key=lambda x: -x[1]["n"]):
        print(f"  {iban}  ({e['n']} Buchungen, Export vorhanden)")
        if ja_nein("    eigenes Girokonto?", True):
            giro[iban] = frage("    Anzeigename", bankname(e["fmt"], iban))
    # Auch Gegenkonten können eigene Girokonten sein (Export liegt nur nicht vor).
    weitere = {}
    kopf("4/5  Gegenkonten zuordnen")
    print("  [1] eigenes Girokonto (intern, fällt aus der Auswertung)")
    print("  [2] zugeordnet: Depot / Darlehen / Gehalt / Kindergeld — zählt mit,")
    print("      bekommt eine feste Kategorie, die keine Händlerregel überschreibt")
    print("  [3] überspringen (normaler Zahlungsempfänger)")
    print("  Achtung: Konten Dritter (Vermieter!) NICHT als intern markieren —")
    print("  die Miete fiele sonst aus der Auswertung.\n")
    zuordnung = {}
    for iban, g in kandidaten(inv):
        if iban in giro:
            continue
        print(f"  {iban}  {g['n']}x  {g['summe']:.2f} €  "
              f"{len(g['namen'])} Namen  {top_namen(g, 1)[:44]}{sammel_hinweis(g)}")
        w = frage("    [1/2/3]", "3")
        if w == "1":
            weitere[iban] = frage("    Anzeigename", bankname("konto", iban))
        elif w == "2":
            print(f"    Kategorien: {', '.join(kats)}")
            cat = frage("    Kategorie", "Sparen/Invest")
            while cat not in kats:
                print(f"    '{cat}' ist keine der Kategorien oben.")
                cat = frage("    Kategorie", "Sparen/Invest")
            zuordnung[iban] = {"kategorie": cat,
                               "notiz": frage("    Notiz (frei)", top_namen(g, 1)[:40])}
    kfg["kategorien_immer_vertrag"] = []
    kfg["kategorien_nicht_reise"] = []
    kfg["kategorien_kein_konsum"] = []
    kfg["konten"] = {"eigene_giro": giro, "weitere_intern": weitere, "zuordnung": zuordnung}

    kopf("5/5  Eigene Regeln")
    print("  Für Händler, die nur dich betreffen (Hausverwaltung, Vermieter, Stammlokal).")
    print("  Die breiten Regeln für gängige Händler sind schon eingebaut.")
    print("  Kann man später jederzeit in konfig.json ergänzen.")
    regeln = []
    while ja_nein("  Regel hinzufügen?", False):
        muster = frage("    Text im Händlernamen (klein)", "")
        if not muster:
            break
        cat = frage("    Kategorie", kats[0])
        if cat not in kats:
            print(f"    '{cat}' ist keine der Kategorien — übersprungen.")
            continue
        regeln.append({"name": frage("    Name der Regel", muster[:20]), "prio": 12,
                       "typ": "haendler_kw", "muster": muster, "kategorie": cat,
                       "labels": frage("    Labels (Komma, optional)", "")})
    kfg["eigene_regeln"] = regeln
    return kfg


def schreiben(kfg):
    if os.path.exists(KONFIG):
        print(f"\n{KONFIG} existiert bereits.")
        if not ja_nein("  Überschreiben? (eine Sicherung wird angelegt)", False):
            print("  Abgebrochen, nichts geändert.")
            return False
        shutil.copy2(KONFIG, KONFIG + ".bak")
        print(f"  Sicherung: {KONFIG}.bak")
    with open(KONFIG, "w", encoding="utf-8") as f:
        json.dump(kfg, f, ensure_ascii=False, indent=2)
    print(f"\n-> {KONFIG} geschrieben")
    # Frisch importieren, damit die Prüfung die NEUE Datei sieht (konfig.py liest beim Import).
    for m in ("konfig",):
        sys.modules.pop(m, None)
    import konfig
    try:
        konfig.pruefen()
        print("   Prüfung: ok")
        return True
    except konfig.KonfigFehler as e:
        print(f"   PRÜFUNG FEHLGESCHLAGEN: {e}")
        print("   Datei von Hand korrigieren, dann: python konfig.py")
        return False


# ---- Thunderbird / Belege -------------------------------------------------
# E-Mails sind der Beleg-Kontext (Produktzeile zu einer Amazon-Buchung). Der Import
# liest mbox-Dateien; Thunderbird legt genau die an, wenn man dort die Postfächer
# einrichtet. Deshalb ist Thunderbird der Weg und nicht ein eigener IMAP-Client:
# nichts selbst gebaut, kein Passwort in dieser App, und die Mails liegen lokal.

TB_EXE = [r"C:\Program Files\Mozilla Thunderbird\thunderbird.exe",
          r"C:\Program Files (x86)\Mozilla Thunderbird\thunderbird.exe"]

def tb_pfad():
    for p in TB_EXE:
        if os.path.exists(p):
            return p
    return shutil.which("thunderbird")

def tb_profile():
    basis = os.path.join(os.environ.get("APPDATA", ""), "Thunderbird", "Profiles")
    if not os.path.isdir(basis):
        return []
    return [os.path.join(basis, d) for d in sorted(os.listdir(basis))
            if os.path.isdir(os.path.join(basis, d))]

def tb_mboxen(profil, min_bytes=200_000):
    """mbox-Dateien im Profil: liegen unter Mail/ und ImapMail/, haben KEINE Endung
    (die .msf daneben ist nur der Index). Kleine Ordner (leer/Papierkorb) auslassen."""
    treffer = []
    for unter in ("ImapMail", "Mail"):
        wurzel = os.path.join(profil, unter)
        for dirpath, _dirs, files in os.walk(wurzel):
            for fn in files:
                if os.path.splitext(fn)[1]:      # alles mit Endung ist kein mbox
                    continue
                p = os.path.join(dirpath, fn)
                try:
                    size = os.path.getsize(p)
                except OSError:
                    continue
                if size >= min_bytes:
                    treffer.append((p, size))
    return sorted(treffer, key=lambda x: -x[1])

def mail_schritt():
    kopf("Belege aus E-Mails (optional)")
    print("E-Mails liefern nur Kontext zu Buchungen (z.B. was im Amazon-Paket war).")
    print("Ohne sie läuft alles — die Detailspalte bleibt nur leerer.\n")

    exe = tb_pfad()
    if not exe:
        print("Thunderbird ist nicht installiert. Es liefert die mbox-Dateien, die der")
        print("Import liest — deshalb der Weg über Thunderbird und nicht über einen")
        print("eigenen Mailzugriff (kein Passwort in dieser App, Mails bleiben lokal).\n")
        print("  1) Installieren:")
        print("       winget install --id Mozilla.Thunderbird")
        print("     (oder von https://www.thunderbird.net herunterladen)")
        print("  2) Thunderbird starten, Postfächer einrichten (Gmail/GMX/…).")
        print("  3) Wichtig: Warten, bis die Ordner offline verfügbar sind —")
        print("     Konten-Einstellungen > Synchronisation & Speicherplatz >")
        print("     'Mails in diesem Konto auf diesem Computer speichern'.")
        print("     Bei großen Postfächern dauert der erste Abgleich lange.")
        print("  4) Danach hier weiter:  python einrichten.py --mail")
        return False

    print(f"Thunderbird gefunden: {exe}")
    profile = tb_profile()
    if not profile:
        print("Aber noch kein Profil — Thunderbird einmal starten und ein Postfach")
        print("einrichten, dann: python einrichten.py --mail")
        return False

    gefunden = []
    for prof in profile:
        for p, size in tb_mboxen(prof):
            gefunden.append((p, size))
    if not gefunden:
        print("Profil vorhanden, aber keine mbox-Dateien mit Inhalt gefunden.")
        print("Meist fehlt der Offline-Abgleich: Konten-Einstellungen >")
        print("Synchronisation & Speicherplatz > Mails lokal speichern. Dann erneut.")
        return False

    print(f"\n{len(gefunden)} Mail-Ordner gefunden (größte zuerst):")
    for i, (p, size) in enumerate(gefunden[:12], 1):
        kurz = os.path.join(os.path.basename(os.path.dirname(p)), os.path.basename(p))
        print(f"  [{i}] {kurz:44} {size/1e6:7.1f} MB")
    print("\nImportieren heißt: Mails + PDF-Anhänge landen in der lokalen Datenbank.")
    print("Der Import ist idempotent — abbrechen und später fortsetzen ist gefahrlos.")
    a = frage("Nummern importieren (Komma-Liste, leer = keiner)", "")
    if not a:
        print("Übersprungen. Später: python ingest_mail.py <mbox-pfad> <label>")
        return False

    wahl = []
    for teil in [t.strip() for t in a.split(",") if t.strip()]:
        if not teil.isdigit() or not (1 <= int(teil) <= len(gefunden[:12])):
            print(f"  '{teil}' ist keine der Nummern — übersprungen.")
            continue
        wahl.append(gefunden[int(teil) - 1])
    if not wahl:
        return False
    # Vor dem Start zeigen, was das bedeutet: ein GB-großes Postfach läuft lange und
    # ist mit einem Tippfehler schnell ausgelöst. Lieber einmal zu viel nachfragen.
    mb = sum(s for _p, s in wahl) / 1e6
    print(f"\n  Ausgewählt: {len(wahl)} Ordner, zusammen {mb:.0f} MB")
    if mb > 500:
        print("  Das dauert bei dieser Größe lange (Anhänge werden gespeichert und")
        print("  PDFs ausgelesen). Ein gezielter Unterordner statt der ganzen INBOX")
        print("  reicht für Belege meist völlig.")
    if not ja_nein("  Jetzt importieren?", mb <= 500):
        print("  Übersprungen. Später: python ingest_mail.py <mbox-pfad> <label>")
        return False

    import ingest_mail
    for pfad, _size in wahl:
        # Label = Postfach-Kennung; steckt im Servernamen (imap.gmail.com -> gmail).
        server = os.path.basename(os.path.dirname(pfad))
        label = re.sub(r"^(imap|pop|mail)[.-]", "", server).split(".")[0] or "mail"
        label = frage(f"  Label für {server}", label)
        print(f"  Import {os.path.basename(pfad)} als '{label}' ...")
        try:
            ingest_mail.run(pfad, label)
        except Exception as e:
            print(f"  FEHLER beim Import: {type(e).__name__}: {e}")
    return True


# ---- Ablauf ---------------------------------------------------------------

def main(argv):
    nur_pruefen = "--pruefen" in argv
    nur_mail = "--mail" in argv

    if nur_mail:
        mail_schritt()
        return 0

    inv = inventar()
    if inv is None:
        print(f"Keine Kontoexporte in {db.BANK_DIR}.")
        print("Bank-CSV (DKB/GLS) dort ablegen und erneut starten.")
        print("Der Ordner ist über die Umgebungsvariable FINANZEN_BANK umstellbar.")
        return 1
    zeige_inventar(inv)
    if nur_pruefen:
        print("\n(--pruefen: nichts geschrieben)")
        return 0

    if not sys.stdin.isatty():
        # Vorbereitete Eingaben (Pipe/Heredoc) sind erlaubt — so lässt sich die
        # Einrichtung skripten und testen. Fehlt die Eingabe ganz, greift überall die
        # Vorgabe; die Prüfung am Ende fängt ab, was daraus unbrauchbar wäre.
        print("\nHinweis: Eingabe kommt nicht vom Terminal — bei fehlender Antwort")
        print("gilt jeweils die Vorgabe in [Klammern].")

    print("\nJetzt die Fragen, die keine CSV beantworten kann.")
    print("Enter übernimmt jeweils die Vorgabe in [Klammern].")
    kfg = einrichten(inv)
    if not schreiben(kfg):
        return 1
    mail_schritt()
    kopf("Fertig")
    print("Als nächstes:")
    print("  python run_all.py     # Pipeline: Konten -> Datenbank -> Auswertung")
    print("  python app.py         # Editor/Statistik auf http://localhost:8765")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

#!/usr/bin/env python3
"""Beispieldaten: ein vollständiger, erfundener Haushalt zum Ausprobieren.

Wer das Projekt zum ersten Mal sieht, hat keine Lust, erst die eigenen Kontoauszüge
zu exportieren, nur um zu erfahren, ob sich das lohnt. Dieses Skript erzeugt einen
kompletten Demo-Haushalt — Kontoexporte im echten Bankformat plus passende
Konfiguration — und fährt die Pipeline durch.

    python beispieldaten/erzeugen.py

Danach liegt unter `beispieldaten/demo/` ein eigenständiger Projektordner. Die echten
Daten bleiben unberührt: die Demo hat ihre eigene Datenbank und ihre eigene Konfiguration.

Die Daten sind erfunden, aber nicht beliebig — sie decken absichtlich genau die Fälle
ab, an denen sich die Anwendung zeigt: wiederkehrende Fixkosten (Vertragserkennung),
eine Urlaubsreise am Stück (Reiseerkennung), eine interne Umbuchung aufs eigene
Sparkonto (Systemgrenze) und ein paar bewusst unbekannte Händler (der ehrliche Rest).
"""
import datetime, os, random, subprocess, sys

HIER = os.path.dirname(os.path.abspath(__file__))
WURZEL = os.path.dirname(HIER)
DEMO = os.path.join(HIER, "demo")
KONTEN = os.path.join(DEMO, "konten")

GIRO   = "DE00111100000000000001"      # Haushaltskonto (DKB-Format)
ZWEIT  = "DE00222200000000000002"      # zweites eigenes Konto (GLS-Format)
SPAREN = "DE00333300000000000003"      # zugeordnet: Sparen/Invest
GEHALT = "DE00444400000000000004"      # Arbeitgeber
MIETE  = "DE00555500000000000005"      # Vermieter — ausdrücklich NICHT intern
TAGES  = "DE00666600000000000006"      # Tagesgeld: Ziel des Sparplans, nur in der Vermögensansicht
DARLEHEN = "DE00777700000000000007"    # Darlehen der vermieteten Wohnung (Bausparkasse)
MIETER = "DE00888800000000000008"      # Mieter der eigenen Wohnung

R = random.Random(20260730)   # fester Startwert: gleiche Demo bei jedem Lauf


def betrag(lo, hi):
    return -round(R.uniform(lo, hi), 2)


def karte(haendler, ort):
    """Kartenzahlung: der Ort steckt hinter dem Schrägstrich im Händlerfeld, genau wie
    es die Banken liefern — daraus liest die Anreicherung später den Ort."""
    return f"{haendler}/{ort}", "VISA Debitkartenumsatz"


def monate_rueckwaerts(n):
    """Die letzten n vollen Monate, damit die Demo immer aktuell wirkt."""
    heute = datetime.date.today()
    erster = heute.replace(day=1)
    aus = []
    for i in range(n, 0, -1):
        m = erster.month - i
        j = erster.year + (m - 1) // 12
        aus.append((j, (m - 1) % 12 + 1))
    return aus


def buchungen():
    """-> [(datum, empfaenger, zweck, betrag, iban_gegen, typ)]"""
    b = []
    monate = monate_rueckwaerts(18)
    urlaub_monat = monate[-4]          # eine Reise, gut sichtbar in der Statistik

    for jahr, monat in monate:
        letzter = (datetime.date(jahr + (monat // 12), monat % 12 + 1, 1)
                   - datetime.timedelta(days=1)).day

        def d(tag):
            return datetime.date(jahr, monat, min(tag, letzter))

        # --- Einnahmen und Fixkosten: gleicher Empfänger, gleicher Tag, jeden Monat.
        # Genau daran erkennt die Anwendung Verträge.
        b.append((d(28), "Musterfirma GmbH", "Gehalt", round(R.uniform(3200, 3300), 2),
                  GEHALT, "Eingang"))
        b.append((d(1), "Hausverwaltung Musterstadt", "Miete Wohnung", -1150.00, MIETE, "Ausgang"))
        b.append((d(3), "Muster Versicherung AG", "Hausrat + Haftpflicht", -38.90, "", "Ausgang"))
        b.append((d(5), "Stadtwerke Musterstadt", "Abschlag Strom", -95.00, "", "Ausgang"))
        b.append((d(8), "Telekom Deutschland GmbH", "Mobilfunk", -29.99, "", "Ausgang"))
        b.append((d(10), "Netflix International", "Abo", -13.99, "", "Ausgang"))
        # Kontoführung am Monatsletzten: ein Monat gilt erst als abgeschlossen, wenn ALLE
        # Konten bis zu seinem Ende reichen — ohne diese Buchung endete das Zweitkonto am 10.
        b.append((d(31), "Musterbank eG", "Kontoführungsentgelt", -4.90, "", "Ausgang"))
        b.append((d(15), "Sparen", "Sparplan", -400.00, SPAREN, "Ausgang"))
        # --- Die vermietete Eigentumswohnung: Miete kommt, Darlehensrate geht. Daran
        # zeigen Vermögen (Restschuld) und Vorsorge (Mietrendite) echte Zahlen.
        b.append((d(3), "Jana Schmidt", "Miete Musterstraße 1, 2. OG", 720.00, MIETER, "Eingang"))
        b.append((d(30), "Bausparkasse Muster", "Darlehen 000000 Rate", -550.00, DARLEHEN, "Ausgang"))

        # --- Alltag: Lebensmittel, Drogerie, ab und zu essen gehen, tanken.
        for _ in range(R.randint(9, 14)):
            laden = R.choice(["REWE SAGT DANKE", "ALDI SUED", "EDEKA MUSTER", "DM-DROGERIE MARKT"])
            ort = R.choice(["Musterstadt", "Musterdorf", "Nachbarhausen"])
            emp, zweck = karte(laden, ort)
            b.append((d(R.randint(1, 28)), emp, zweck, betrag(12, 85), "", "Ausgang"))
        for _ in range(R.randint(1, 4)):
            emp, zweck = karte(R.choice(["Restaurant Sonne", "Cafe Central", "Pizzeria Bella"]),
                               "Musterstadt")
            b.append((d(R.randint(1, 28)), emp, zweck, betrag(18, 70), "", "Ausgang"))
        for _ in range(R.randint(1, 3)):
            emp, zweck = karte(R.choice(["ARAL TANKSTELLE", "SHELL"]), "Musterstadt")
            b.append((d(R.randint(1, 28)), emp, zweck, betrag(55, 95), "", "Ausgang"))

        # --- Bewusst unbekannte Händler: die müssen sichtbar offen bleiben, statt
        # geraten zu werden. Ohne die sähe die Demo unrealistisch sauber aus.
        if R.random() < 0.5:
            b.append((d(R.randint(1, 28)), R.choice(["Kqrst Handel 88", "P. Vogelsang",
                                                     "Zahlung 4711"]),
                      f"ReNr {R.randint(1000, 9999)}", betrag(25, 300), "", "Ausgang"))

        # --- Onlinebestellungen MIT Bestellnummer im Verwendungszweck. Genau daran
        # haengt die Belegverknuepfung: die Nummer steht auch in der Bestellmail, und
        # darueber weiss die Anwendung hinterher, WAS gekauft wurde. Ohne solche
        # Buchungen liefe der Mail-Teil der Demo ins Leere.
        for _ in range(R.randint(1, 2)):
            tag = R.randint(2, 26)
            nr = f"{R.randint(100,999)}-{R.randint(1000000,9999999)}-{R.randint(1000000,9999999)}"
            produkt = R.choice(PRODUKTE)
            wert = -round(R.uniform(12, 140), 2)
            b.append((d(tag), "AMAZON PAYMENTS EUROPE S.C.A",
                      f"{nr} AMZN Mktp DE", wert, "", "Ausgang"))
            BESTELLUNGEN.append((d(tag), nr, produkt, wert))

        # --- Ein verlängertes Wochenende am See: bleibt als Kandidat offen, damit die
        # Reisen-Seite beide Zustände zeigt (bestätigt und noch zu prüfen).
        if (jahr, monat) == monate[-6]:
            for tag in range(16, 20):
                emp, zweck = karte(R.choice(["Hotel Seeblick", "Fischerstube", "Faehre Konstanz",
                                             "Bodensee Schifffahrt"]), R.choice(["Lindau", "Konstanz"]))
                b.append((d(tag), emp, zweck, betrag(20, 140), "", "Ausgang"))

        # --- Die Reise: acht Tage am Stück außerhalb der Heimatregion.
        if (jahr, monat) == urlaub_monat:
            for tag in range(6, 14):
                ort = R.choice(["Riomaggiore", "La Spezia", "Vernazza"])
                emp, zweck = karte(R.choice(["Panificio Raso", "Trattoria da Mario",
                                             "Conad Market", "Autostrade per l Italia"]), ort)
                b.append((d(tag), emp, zweck, betrag(15, 120), "", "Ausgang"))
    return b


# Bestellungen, zu denen es eine Mail gibt — waehrend buchungen() gefuellt.
BESTELLUNGEN = []

PRODUKTE = [
    "Wanderschuhe Trekking Mid GTX, Gr. 43",
    "Kaffeemuehle mit Kegelmahlwerk, edelstahl",
    "Regentonne 210 l inkl. Wasserhahn",
    "Fahrradanhaenger-Kupplung, universal",
    "Buch: Der lange Weg nach Hause (Taschenbuch)",
    "LED-Lichterkette 20 m, warmweiss, aussen",
    "Ersatzfilter fuer Wasserfilterkanne, 6er-Pack",
    "Thermoskanne 1,0 l, doppelwandig",
]


def mbox_schreiben(pfad):
    """Beleg-Mails im echten mbox-Format — dasselbe, was Thunderbird anlegt.

    Der Import liest mbox, deshalb wird hier eines geschrieben statt eines eigenen
    Formats: der Demo-Weg ist damit exakt der spaetere Ernstfall.
    """
    import email.utils
    teile = []
    for datum, nr, produkt, wert in BESTELLUNGEN:
        betrag_de = f"{abs(wert):.2f}".replace(".", ",")
        gesendet = email.utils.format_datetime(
            datetime.datetime.combine(datum, datetime.time(9, 14)))
        rumpf = (
            f"Guten Tag,\r\n\r\n"
            f"vielen Dank fuer Ihre Bestellung.\r\n\r\n"
            f"Bestellnummer: {nr}\r\n"
            f"Artikel: {produkt}\r\n"
            f"Gesamtbetrag: {betrag_de} EUR\r\n"
            f"Voraussichtliche Lieferung: in 2 Werktagen\r\n\r\n"
            f"Ihre Bestelluebersicht finden Sie in Ihrem Konto.\r\n")
        teile.append(
            f"From bestellung@beispiel-shop.test {datum.strftime('%a %b %d 09:14:00 %Y')}\r\n"
            f"From: Beispiel Shop <bestellung@beispiel-shop.test>\r\n"
            f"To: familie.muster@beispiel.test\r\n"
            f"Subject: Ordered: {produkt}\r\n"
            f"Date: {gesendet}\r\n"
            f"Message-ID: <{nr}@beispiel-shop.test>\r\n"
            f"Content-Type: text/plain; charset=utf-8\r\n"
            f"Content-Transfer-Encoding: 8bit\r\n\r\n"
            f"{rumpf}\r\n")
    with open(pfad, "w", encoding="utf-8", newline="") as f:
        f.write("".join(teile))
    return len(teile)


def de_betrag(x):
    return f"{x:,.2f}".replace(",", "·").replace(".", ",").replace("·", ".")


def dkb_datei(pfad, iban, zeilen, art="Girokonto", start=2500.0):
    """DKB-Umsatzliste. Der Kontostand im Kopf passt zu den Buchungen (Startwert plus
    Summe) und steht auf dem Tag der letzten Buchung — so wie die Bank ihn liefert."""
    stand = start + sum(z[3] for z in zeilen)
    letzter = max(z[0] for z in zeilen).strftime("%d.%m.%Y")
    kopf = (f'"{art}";"{iban}"\n\n"Kontostand vom {letzter}:";"{de_betrag(stand)} €"\n""\n'
            '"Buchungsdatum";"Wertstellung";"Status";"Zahlungspflichtige*r";'
            '"Zahlungsempfänger*in";"Verwendungszweck";"Umsatztyp";"IBAN";"Betrag (€)";'
            '"Gläubiger-ID";"Mandatsreferenz";"Kundenreferenz"\n')
    aus = []
    for datum, emp, zweck, wert, ig, typ in zeilen:
        d = datum.strftime("%d.%m.%y")
        w = f"{wert:.2f}".replace(".", ",")
        aus.append(f'"{d}";"{d}";"Gebucht";"Familie Muster";"{emp}";"{zweck}";"{typ}";'
                   f'"{ig}";"{w}";"";"";""')
    with open(pfad, "w", encoding="utf-8-sig", newline="") as f:
        f.write(kopf + "\n".join(aus) + "\n")


def gls_datei(pfad, iban, zeilen, start=900.0):
    kopf = ("Bezeichnung Auftragskonto;IBAN Auftragskonto;BIC Auftragskonto;"
            "Bankname Auftragskonto;Buchungstag;Valutadatum;Name Zahlungsbeteiligter;"
            "IBAN Zahlungsbeteiligter;BIC (SWIFT-Code) Zahlungsbeteiligter;Buchungstext;"
            "Verwendungszweck;Betrag;Waehrung;Saldo nach Buchung;Bemerkung;"
            "Gekennzeichneter Umsatz;Glaeubiger ID;Mandatsreferenz\n")
    aus, saldo = [], start
    for datum, emp, zweck, wert, ig, _typ in sorted(zeilen, key=lambda z: z[0]):
        saldo += wert                                   # 'Saldo nach Buchung' laeuft mit
        d = datum.strftime("%d.%m.%Y")
        w = f"{wert:.2f}".replace(".", ",")
        sd = f"{saldo:.2f}".replace(".", ",")
        aus.append(f"Musterbank;{iban};GENODEM1XXX;Musterbank eG;{d};{d};{emp};{ig};BICXXX;"
                   f"Umsatz;{zweck};{w};EUR;{sd};;;;")
    aus.reverse()                                       # GLS liefert neueste zuerst
    with open(pfad, "w", encoding="utf-8-sig", newline="") as f:
        f.write(kopf + "\n".join(aus) + "\n")


KONFIG = {
    "_hinweis": "Konfiguration der Beispieldaten. Erzeugt von beispieldaten/erzeugen.py.",
    "haushalt": {
        "name": "Familie Muster (Beispieldaten)",
        "eigene_namen": ["muster"],
        "heimat_orte": ["musterstadt", "musterdorf", "nachbarhausen"],
        "orte_ohne_suchwert": [],
    },
    "kategorien": ["Lebensmittel/Drogerie", "Restaurant/Café", "Mobilität", "Versicherung",
                   "Gesundheit", "Kinder", "Freizeit/Hobby", "Urlaub", "Shopping/Haushalt",
                   "Abo/Digital", "Wohnen", "Gebühren", "Dienstleistung",
                   "Spenden/Geschenke", "Bargeld", "Einnahme", "Sparen/Invest",
                   "Kredit/Immobilie", "Immobilie Musterstadt", "Umbuchung intern",
                   "PayPal (ungeklärt)", "Sonstiges"],
    "kategorien_immer_vertrag": [],
    "kategorien_nicht_reise": [],
    "kategorien_kein_konsum": ["Immobilie Musterstadt"],
    "konten": {
        "eigene_giro": {GIRO: "Muster-Giro", ZWEIT: "Muster-Zweitkonto"},
        "weitere_intern": {},
        "zuordnung": {
            SPAREN: {"kategorie": "Sparen/Invest", "notiz": "Sparplan"},
            GEHALT: {"kategorie": "Einnahme", "notiz": "Gehalt"},
            DARLEHEN: {"kategorie": "Immobilie Musterstadt", "notiz": "Darlehen vermietete Wohnung"},
            MIETER: {"kategorie": "Immobilie Musterstadt", "notiz": "Miete vermietete Wohnung"},
        },
    },
    "eigene_regeln": [
        {"name": "Miete", "prio": 12, "typ": "haendler_kw", "muster": "hausverwaltung",
         "kategorie": "Wohnen", "labels": "wohnen,miete,fixkosten"},
        {"name": "Strom", "prio": 12, "typ": "haendler_kw", "muster": "stadtwerke",
         "kategorie": "Wohnen", "labels": "strom,fixkosten"},
        {"name": "Kontoführung", "prio": 12, "typ": "haendler_kw", "muster": "musterbank",
         "kategorie": "Gebühren", "labels": "bank,fixkosten"},
    ],
}


def vermoegen_schreiben(haupt):
    """Vermögensansicht des Demo-Haushalts: Tagesgeld (Ziel des Sparplans), ein Depot,
    die vermietete Wohnung mit Darlehen. Gleiche Dateiformate wie im Ernstfall."""
    import json
    stichtag = max(z[0] for z in haupt)
    # Tagesgeld: die Sparraten kommen hier an (Gegenbuchung zum Sparplan auf dem Giro)
    sparen = [(z[0], "Familie Muster", "Sparplan", -z[3], GIRO, "Eingang") for z in haupt if z[4] == SPAREN]
    eingang = os.path.join(DEMO, "vermoegen", "eingang")
    depot = os.path.join(DEMO, "vermoegen", "depot")
    os.makedirs(eingang, exist_ok=True); os.makedirs(depot, exist_ok=True)
    dkb_datei(os.path.join(eingang, "Umsatzliste_Tagesgeld_Beispiel.csv"), TAGES, sparen,
              art="Tagesgeld", start=6000.0)
    # Depot: drei breit gestreute Fonds, erfundene Kennungen
    pos = [("Welt-Aktien-ETF (Beispiel)", "XX0000000001", 210.0, 118.40, 96.20, "ETFs"),
           ("Schwellenländer-ETF (Beispiel)", "XX0000000002", 150.0, 31.75, 29.10, "ETFs"),
           ("Euro-Staatsanleihen-ETF (Beispiel)", "XX0000000003", 40.0, 148.90, 152.30, "ETFs")]
    k = ["Datum der Erstellung", "Wertpapierbezeichnung", "ISIN", "Stückzahl",
         "Bewertungskurs", "Einstiegskurs", "Assetklasse"]
    zeilen = [";".join(k)] + [";".join([stichtag.strftime("%d.%m.%Y"), n, i,
              f"{st:.4f}".replace(".", ","), f"{ku:.2f}".replace(".", ","),
              f"{ei:.2f}".replace(".", ","), a]) for n, i, st, ku, ei, a in pos]
    with open(os.path.join(depot, "depot-export-Beispiel.csv"), "w", encoding="utf-8-sig") as f:
        f.write("\n".join(zeilen) + "\n")
    erste_rate = min(z[0] for z in haupt if z[4] == DARLEHEN)
    cfg = {
        "_hinweis": "Vermögensaufstellung des Demo-Haushalts (erfunden). Vorlage für die eigene: "
                    "vermoegen/positionen.beispiel.json im Repo.",
        "stichtag": stichtag.isoformat(),
        "sicht": "Familie Muster (Beispieldaten)",
        "sicht_hinweis": "Erfundener Haushalt. Die vermietete Wohnung gehört beiden je zur Hälfte "
                         "und wird voll gezählt.",
        "spanne_hinweis": "aus der Bewertung der Wohnung",
        "nicht_enthalten": "Auto (abgeschrieben), Mietkaution (Durchlaufposten).",
        "konten": [
            {"name": "Girokonto Haushalt", "iban": GIRO, "format": "dkb",
             "datei": "konten/Umsatzliste_Girokonto_Beispiel.csv"},
            {"name": "Zweitkonto", "iban": ZWEIT, "format": "gls",
             "datei": "konten/Umsaetze_Zweitkonto_Beispiel.csv"},
            {"name": "Tagesgeld", "iban": TAGES, "format": "dkb",
             "datei": "vermoegen/eingang/Umsatzliste_Tagesgeld_Beispiel.csv"}],
        "depots": [{"name": "Depot (Beispiel)", "datei": "vermoegen/depot/depot-export-Beispiel.csv"}],
        "immobilien": [{
            "id": "musterstadt", "name": "Musterstadt, Musterstraße 1",
            "detail": "Eigentumswohnung, 68 m², 2. OG, Baujahr 1994, vermietet",
            "anteil": 1.0, "anteil_text": "je 1/2 zwei Personen = 1/1 Haushalt", "guete": "gut",
            "methode": "vergleichswert_index", "anker_wert": 210000,
            "anker_datum": (erste_rate.replace(day=1)).strftime("%Y-%m"),
            "anker_quelle": "Kaufpreis lt. Kaufvertrag, ohne Nebenkosten (erfunden)",
            "index_name": "Beispiel-Preisindex, Eigentumswohnungen",
            "index_von": 100.0, "index_von_stand": erste_rate.strftime("%Y-%m"),
            "index_bis": 103.5, "index_bis_stand": stichtag.strftime("%Y-%m"),
            "spanne_pct": 0.06,
            "gegenprobe": "210.000 € / 68 m² = 3.088 €/m², im Rahmen vergleichbarer Wohnungen vor Ort."}],
        "darlehen": [{
            "id": "darlehen-musterstadt", "objekt": "musterstadt",
            "name": "Bausparkasse Muster, Darlehen Nr. 000000", "konto": DARLEHEN,
            "betrag": 160000.0, "zins_nominal": 0.021, "rate": 550.0,
            "erste_rate": (erste_rate.replace(day=1) - datetime.timedelta(days=365 * 4)).replace(day=1).isoformat(),
            "zinsbindung_bis": f"{stichtag.year + 7}-06-30", "anteil": 1.0,
            "verifikation": "Erfundene Beispielwerte."}],
    }
    with open(os.path.join(DEMO, "vermoegen", "positionen.json"), "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def reisen_entscheiden(umgebung):
    """So, wie es nach ein paar Wochen Nutzung aussieht: die große Reise ist bestätigt und
    benannt, das Wochenende bleibt offen; die offensichtlichen Verträge sind bestätigt,
    zwei bleiben zur Prüfung stehen. Alles über dieselben Funktionen wie in der App."""
    code = ("import app, db\n"
            "con=db.connect(); t=con.execute(\"select id from trips where orte like '%Vernazza%' "
            "or orte like '%Spezia%' or orte like '%Riomaggiore%'\").fetchone()\n"
            "offen=('telekom','netflix')\n"
            "vtg=[r[0] for r in con.execute('select id,lower(name) from contracts') if not any(o in r[1] for o in offen)]\n"
            "con.close()\n"
            "t and app.trip_edit({'id': t[0], 'status': 'confirmed', 'name': 'Cinque Terre'})\n"
            "[app.contract_edit({'id': c, 'status': 'confirmed'}) for c in vtg]\n")
    subprocess.run([sys.executable, "-c", code], cwd=os.path.join(WURZEL, "scripts"), env=umgebung,
                   stdout=subprocess.DEVNULL)


def main():
    import json
    os.makedirs(KONTEN, exist_ok=True)
    alle = buchungen()
    # Zwei Konten, damit die Systemgrenze und beide Bankformate vorkommen.
    zweit = [b for b in alle if b[1] in ("Netflix International", "Muster Versicherung AG",
                                          "Musterbank eG")]
    haupt = [b for b in alle if b not in zweit]
    dkb_datei(os.path.join(KONTEN, "Umsatzliste_Girokonto_Beispiel.csv"), GIRO, haupt)
    vermoegen_schreiben(haupt)
    gls_datei(os.path.join(KONTEN, "Umsaetze_Zweitkonto_Beispiel.csv"), ZWEIT, zweit, start=1800.0)
    with open(os.path.join(DEMO, "konfig.json"), "w", encoding="utf-8") as f:
        json.dump(KONFIG, f, ensure_ascii=False, indent=2)
    mbox = os.path.join(DEMO, "beleg-mails.mbox")
    n_mails = mbox_schreiben(mbox)
    print(f"{len(alle)} Buchungen erzeugt -> {KONTEN}")
    print(f"{n_mails} Beleg-Mails erzeugt -> {os.path.basename(mbox)}")
    print(f"Konfiguration -> {os.path.join(DEMO, 'konfig.json')}")

    # Pipeline im Demo-Ordner laufen lassen: eigene Datenbank, eigene Konfiguration.
    # FINANZEN_MAILDB leer: nie die zentrale Mail-DB eines Pi einblenden (echte Mails).
    umgebung = dict(os.environ, FINANZEN_BASE=DEMO, FINANZEN_BANK=KONTEN, FINANZEN_MAILDB="")
    umgebung.pop("FINANZEN_BANK_CSV", None)

    # Mails VOR der Pipeline importieren — der Matcher (Schritt 4) braucht sie schon.
    print("\nBeleg-Mails importieren ...")
    subprocess.run([sys.executable, "ingest_mail.py", mbox, "demo-postfach"],
                   cwd=os.path.join(WURZEL, "scripts"), env=umgebung)

    print("\nPipeline läuft ...\n")
    e = subprocess.run([sys.executable, "run_all.py"],
                       cwd=os.path.join(WURZEL, "scripts"), env=umgebung)
    if e.returncode != 0:
        return e.returncode
    reisen_entscheiden(umgebung)

    eigene = any(os.path.exists(os.path.join(WURZEL, n)) for n in ("konfig.json", "finanzen.db"))
    print("\nFertig. Ansehen:")
    if not eigene:
        # Ohne eigene Daten zeigt die App von selbst den Demo-Haushalt (db.DEMO_MODUS).
        print("  python scripts/app.py   ->  http://localhost:8765/finanzen/")
    else:
        # Eigene Daten vorhanden: die Demo auf eigenem Port, damit nichts verwechselt wird.
        if os.name == "nt":
            # PowerShell: `set` ist dort ein Alias für Set-Variable und erzeugt KEINE
            # Umgebungsvariable — der Server liefe kommentarlos gegen die echten Daten.
            print(f'  $env:FINANZEN_BASE = "{DEMO}"; $env:FINANZEN_PORT = "8766"; python scripts/app.py')
        else:
            print(f'  FINANZEN_BASE="{DEMO}" FINANZEN_PORT=8766 python scripts/app.py')
        print("  ->  http://localhost:8766/finanzen/")
    return 0

if __name__ == "__main__":
    sys.exit(main())

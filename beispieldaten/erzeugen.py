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
        b.append((d(15), "Sparen", "Sparplan", -400.00, SPAREN, "Ausgang"))

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


def dkb_datei(pfad, iban, zeilen):
    kopf = (f'"Girokonto";"{iban}"\n\n"Kontostand vom 31.12.2099:";"2.480,00 €"\n""\n'
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


def gls_datei(pfad, iban, zeilen):
    kopf = ("Bezeichnung Auftragskonto;IBAN Auftragskonto;BIC Auftragskonto;"
            "Bankname Auftragskonto;Buchungstag;Valutadatum;Name Zahlungsbeteiligter;"
            "IBAN Zahlungsbeteiligter;BIC (SWIFT-Code) Zahlungsbeteiligter;Buchungstext;"
            "Verwendungszweck;Betrag;Waehrung;Saldo nach Buchung;Bemerkung;"
            "Gekennzeichneter Umsatz;Glaeubiger ID;Mandatsreferenz\n")
    aus = []
    for datum, emp, zweck, wert, ig, _typ in zeilen:
        d = datum.strftime("%d.%m.%Y")
        w = f"{wert:.2f}".replace(".", ",")
        aus.append(f"Musterbank;{iban};GENODEM1XXX;Musterbank eG;{d};{d};{emp};{ig};BICXXX;"
                   f"Umsatz;{zweck};{w};EUR;900,00;;;;")
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
                   "Kredit/Immobilie", "Umbuchung intern", "PayPal (ungeklärt)", "Sonstiges"],
    "kategorien_immer_vertrag": [],
    "kategorien_nicht_reise": [],
    "kategorien_kein_konsum": [],
    "konten": {
        "eigene_giro": {GIRO: "Muster-Giro", ZWEIT: "Muster-Zweitkonto"},
        "weitere_intern": {},
        "zuordnung": {
            SPAREN: {"kategorie": "Sparen/Invest", "notiz": "Sparplan"},
            GEHALT: {"kategorie": "Einnahme", "notiz": "Gehalt"},
        },
    },
    "eigene_regeln": [
        {"name": "Miete", "prio": 12, "typ": "haendler_kw", "muster": "hausverwaltung",
         "kategorie": "Wohnen", "labels": "wohnen,miete,fixkosten"},
        {"name": "Strom", "prio": 12, "typ": "haendler_kw", "muster": "stadtwerke",
         "kategorie": "Wohnen", "labels": "strom,fixkosten"},
    ],
}


def main():
    import json
    os.makedirs(KONTEN, exist_ok=True)
    alle = buchungen()
    # Zwei Konten, damit die Systemgrenze und beide Bankformate vorkommen.
    zweit = [b for b in alle if b[1] in ("Netflix International", "Muster Versicherung AG")]
    haupt = [b for b in alle if b not in zweit]
    dkb_datei(os.path.join(KONTEN, "Umsatzliste_Girokonto_Beispiel.csv"), GIRO, haupt)
    gls_datei(os.path.join(KONTEN, "Umsaetze_Zweitkonto_Beispiel.csv"), ZWEIT, zweit)
    with open(os.path.join(DEMO, "konfig.json"), "w", encoding="utf-8") as f:
        json.dump(KONFIG, f, ensure_ascii=False, indent=2)
    mbox = os.path.join(DEMO, "beleg-mails.mbox")
    n_mails = mbox_schreiben(mbox)
    print(f"{len(alle)} Buchungen erzeugt -> {KONTEN}")
    print(f"{n_mails} Beleg-Mails erzeugt -> {os.path.basename(mbox)}")
    print(f"Konfiguration -> {os.path.join(DEMO, 'konfig.json')}")

    # Pipeline im Demo-Ordner laufen lassen: eigene Datenbank, eigene Konfiguration.
    umgebung = dict(os.environ, FINANZEN_BASE=DEMO, FINANZEN_BANK=KONTEN)
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
    print("\nDemo ansehen — Umgebungsvariable setzen, dann Server starten:")
    if os.name == "nt":
        # PowerShell ist unter Windows 11 das Standard-Terminal. Dort ist `set` ein
        # Alias fuer Set-Variable und erzeugt KEINE Umgebungsvariable — kommentarlos.
        # Der Server liefe dann gegen die echten Daten statt gegen die Demo.
        print("  PowerShell:")
        print(f'    $env:FINANZEN_BASE = "{DEMO}"')
        print('    $env:FINANZEN_PORT = "8766"')
        print('    python scripts/app.py')
        print("  cmd.exe:")
        print(f'    set FINANZEN_BASE={DEMO}')
        print('    set FINANZEN_PORT=8766')
        print('    python scripts/app.py')
    else:
        print(f'  FINANZEN_BASE="{DEMO}" FINANZEN_PORT=8766 python scripts/app.py')
    print("\n  ->  http://localhost:8766   (eigener Port, damit eine laufende Instanz")
    print("      mit den echten Daten auf 8765 nicht gestoert wird)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

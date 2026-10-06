"""Gemeinsame Testumgebung.

**Muss als Erstes importiert werden** — vor `db`, `konfig` oder irgendeinem anderen
Projektmodul. Grund: `db.py` liest die Pfade und `konfig.py` die Konfiguration beim
*Import*. Wer zuerst `db` importiert, hat den echten Projektordner und damit die echte
Datenbank am Haken; Tests dürfen die niemals anfassen.

Legt einen eigenen Projektordner im Temp-Verzeichnis an, mit einer kleinen, festen
Konfiguration. Damit sind die Tests unabhängig von der `konfig.json` des Nutzers —
sonst würden sie beim Freund anders ausfallen als hier.
"""
import atexit, json, os, shutil, sys, tempfile

BASE = tempfile.mkdtemp(prefix="finanzen-test-")
KONTEN = os.path.join(BASE, "konten")
os.makedirs(KONTEN, exist_ok=True)
os.environ["FINANZEN_BASE"] = BASE
os.environ["FINANZEN_BANK"] = KONTEN
os.environ.pop("FINANZEN_BANK_CSV", None)
# Nie die zentrale Mail-DB des Rechners (Pi: /srv/mail-db) in Tests einblenden.
os.environ["FINANZEN_MAILDB"] = ""
atexit.register(lambda: shutil.rmtree(BASE, ignore_errors=True))

# Testkonfiguration: bewusst klein und erfunden. Die IBANs sind Platzhalter.
GIRO_A = "DE00000000000000000001"      # eigenes Girokonto
GIRO_B = "DE00000000000000000002"      # zweites eigenes Girokonto
DEPOT  = "DE00000000000000000003"      # zugeordnet: Sparen
FREMD  = "DE00000000000000000009"      # normaler Zahlungsempfänger

KONFIG = {
    "haushalt": {
        "name": "Testhaushalt",
        "eigene_namen": ["mustermann"],
        "heimat_orte": ["musterstadt", "musterdorf"],
        "orte_ohne_suchwert": ["musterland"],
    },
    "kategorien": ["Lebensmittel/Drogerie", "Mobilität", "Wohnen", "Abo/Digital",
                   "Versicherung", "Einnahme", "Sparen/Invest", "Kredit/Immobilie",
                   "Umbuchung intern", "PayPal (ungeklärt)", "Sonstiges"],
    "kategorien_immer_vertrag": [],
    "kategorien_nicht_reise": [],
    "kategorien_kein_konsum": [],
    "konten": {
        "eigene_giro": {GIRO_A: "Test-Giro-A", GIRO_B: "Test-Giro-B"},
        "weitere_intern": {},
        "zuordnung": {DEPOT: {"kategorie": "Sparen/Invest", "notiz": "Testdepot"}},
    },
    "eigene_regeln": [
        {"name": "Testvermieter", "prio": 12, "typ": "haendler_kw",
         "muster": "hausverwaltung mustermann", "kategorie": "Wohnen",
         "labels": "wohnen,miete"}
    ],
}

def konfig_schreiben(daten=None):
    """Konfiguration in den Test-Projektordner schreiben. Vor dem Import von `konfig`."""
    with open(os.path.join(BASE, "konfig.json"), "w", encoding="utf-8") as f:
        json.dump(daten if daten is not None else KONFIG, f, ensure_ascii=False)

konfig_schreiben()

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                "scripts"))


# ---- Beispiel-Exporte -----------------------------------------------------
# Aufbau exakt wie bei den echten Banken (Kopfzeilen, Spaltenreihenfolge,
# deutsche Zahlen/Datumsformate), aber mit erfundenen Daten.

def dkb_csv(iban, zeilen):
    """zeilen: (datum, zahlungspflichtig, empfaenger, zweck, typ, iban_gegen, betrag, glaeubiger)"""
    kopf = ('"Girokonto";"%s"\n\n"Kontostand vom 31.01.2026:";"1.234,56 €"\n""\n'
            '"Buchungsdatum";"Wertstellung";"Status";"Zahlungspflichtige*r";'
            '"Zahlungsempfänger*in";"Verwendungszweck";"Umsatztyp";"IBAN";"Betrag (€)";'
            '"Gläubiger-ID";"Mandatsreferenz";"Kundenreferenz"\n') % iban
    aus = []
    for d, zp, emp, zw, typ, ig, betrag, gid in zeilen:
        aus.append(f'"{d}";"{d}";"Gebucht";"{zp}";"{emp}";"{zw}";"{typ}";"{ig}";'
                   f'"{betrag}";"{gid}";"";""')
    return kopf + "\n".join(aus) + "\n"

def gls_csv(iban, zeilen):
    """zeilen: (datum, name, iban_gegen, buchungstext, zweck, betrag, glaeubiger)"""
    kopf = ("Bezeichnung Auftragskonto;IBAN Auftragskonto;BIC Auftragskonto;"
            "Bankname Auftragskonto;Buchungstag;Valutadatum;Name Zahlungsbeteiligter;"
            "IBAN Zahlungsbeteiligter;BIC (SWIFT-Code) Zahlungsbeteiligter;Buchungstext;"
            "Verwendungszweck;Betrag;Waehrung;Saldo nach Buchung;Bemerkung;"
            "Gekennzeichneter Umsatz;Glaeubiger ID;Mandatsreferenz\n")
    aus = []
    for d, name, ig, bt, zw, betrag, gid in zeilen:
        aus.append(f"Testkonto;{iban};GENODEM1GLS;Testbank;{d};{d};{name};{ig};BICXX;"
                   f"{bt};{zw};{betrag};EUR;1000,00;;;{gid};")
    return kopf + "\n".join(aus) + "\n"

def export_ablegen(dateiname, inhalt):
    pfad = os.path.join(KONTEN, dateiname)
    with open(pfad, "w", encoding="utf-8-sig", newline="") as f:
        f.write(inhalt)
    return pfad

def exporte_leeren():
    for f in os.listdir(KONTEN):
        os.remove(os.path.join(KONTEN, f))

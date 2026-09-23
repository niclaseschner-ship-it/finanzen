"""Schritt 1 der Pipeline: Bank-Exporte einlesen und zusammenführen.

Hier entscheidet sich, ob Buchungen überhaupt korrekt in der Datenbank landen —
deutsche Zahlen, zweistellige Jahre, und vor allem die Deduplizierung überlappender
Exporte. Ein Fehler hier verdoppelt stillschweigend Ausgaben.
"""
import unittest
import helfer
import parse_konten


class TestFormate(unittest.TestCase):
    def setUp(self):
        helfer.exporte_leeren()

    def test_dkb_wird_gelesen(self):
        helfer.export_ablegen("dkb.csv", helfer.dkb_csv(helfer.GIRO_A, [
            ("15.01.26", "Testhaushalt", "REWE Musterstadt", "Einkauf", "Ausgang",
             helfer.FREMD, "-42,50", ""),
        ]))
        (_f, fmt, iban, zeilen), = parse_konten.lese_alle()
        self.assertEqual(fmt, "dkb")
        self.assertEqual(iban, helfer.GIRO_A)
        self.assertEqual(len(zeilen), 1)
        z = zeilen[0]
        self.assertEqual(z["datum"], "2026-01-15", "zweistelliges Jahr -> ISO")
        self.assertEqual(z["betrag"], -42.50, "deutsche Zahl mit Komma")
        self.assertEqual(z["gegenpartei"], "REWE Musterstadt")
        self.assertEqual(z["iban_gegen"], helfer.FREMD)

    def test_gls_wird_gelesen(self):
        helfer.export_ablegen("gls.csv", helfer.gls_csv(helfer.GIRO_B, [
            ("15.01.2026", "Arbeitgeber GmbH", helfer.FREMD, "Gutschrift",
             "Gehalt 01/2026", "2500,00", ""),
        ]))
        (_f, fmt, iban, zeilen), = parse_konten.lese_alle()
        self.assertEqual(fmt, "gls")
        self.assertEqual(iban, helfer.GIRO_B)
        self.assertEqual(zeilen[0]["betrag"], 2500.00)
        self.assertEqual(zeilen[0]["datum"], "2026-01-15")

    def test_tausenderpunkt_und_vorzeichen(self):
        helfer.export_ablegen("dkb.csv", helfer.dkb_csv(helfer.GIRO_A, [
            ("01.02.26", "X", "Y", "gross", "Ausgang", helfer.FREMD, "-1.234,56", ""),
            ("02.02.26", "X", "Y", "eingang", "Eingang", helfer.FREMD, "2.000,00", ""),
        ]))
        (_f, _fmt, _i, zeilen), = parse_konten.lese_alle()
        betraege = sorted(z["betrag"] for z in zeilen)
        self.assertEqual(betraege, [-1234.56, 2000.00])

    def test_kontoname_aus_konfiguration(self):
        """Der Anzeigename kommt aus konfig.json; unbekannte Konten bekommen einen
        Ersatznamen, statt den Import scheitern zu lassen."""
        helfer.export_ablegen("dkb.csv", helfer.dkb_csv(helfer.GIRO_A, [
            ("01.03.26", "X", "Y", "z", "Ausgang", helfer.FREMD, "-1,00", ""),
        ]))
        (_f, _fmt, _i, zeilen), = parse_konten.lese_alle()
        self.assertEqual(zeilen[0]["konto"], "Test-Giro-A")


class TestDedup(unittest.TestCase):
    """Zwei Exporte desselben Kontos überlappen fast immer (jeder Download enthält
    die letzten Monate erneut). Die Überlappung muss weg, echte Doppelbuchungen
    (zweimal derselbe Betrag am selben Tag) müssen bleiben."""

    def setUp(self):
        helfer.exporte_leeren()

    def _buchung(self, datum, zweck, betrag):
        return (datum, "Testhaushalt", "Laden", zweck, "Ausgang", helfer.FREMD, betrag, "")

    def test_ueberlappung_faellt_weg(self):
        a = [self._buchung("05.01.26", "Einkauf A", "-10,00"),
             self._buchung("06.01.26", "Einkauf B", "-20,00")]
        b = [self._buchung("06.01.26", "Einkauf B", "-20,00"),      # Überlappung
             self._buchung("07.01.26", "Einkauf C", "-30,00")]
        helfer.export_ablegen("export1.csv", helfer.dkb_csv(helfer.GIRO_A, a))
        helfer.export_ablegen("export2.csv", helfer.dkb_csv(helfer.GIRO_A, b))
        parse_konten.run()
        import csv
        with open(parse_konten.OUT, encoding="utf-8-sig") as f:
            zeilen = list(csv.DictReader(f, delimiter=";"))
        self.assertEqual(len(zeilen), 3, "A, B, C — B nur einmal")
        zwecke = sorted(z["verwendungszweck"] for z in zeilen)
        self.assertEqual(zwecke, ["Einkauf A", "Einkauf B", "Einkauf C"])

    def test_echte_doppelbuchung_bleibt(self):
        """Zweimal derselbe Kaffee am selben Tag ist keine Dublette. Der Unterschied
        zur Überlappung: sie steht in EINER Datei zweimal."""
        zeilen = [self._buchung("05.01.26", "Kaffee", "-3,50"),
                  self._buchung("05.01.26", "Kaffee", "-3,50")]
        helfer.export_ablegen("export1.csv", helfer.dkb_csv(helfer.GIRO_A, zeilen))
        parse_konten.run()
        import csv
        with open(parse_konten.OUT, encoding="utf-8-sig") as f:
            self.assertEqual(len(list(csv.DictReader(f, delimiter=";"))), 2)

    def test_doppelbuchung_ueberlebt_auch_mit_ueberlappendem_export(self):
        """Der harte Fall: eine echte Doppelbuchung, die in beiden Exporten steht.
        Erwartet: zweimal — nicht vier-, nicht einmal."""
        doppelt = [self._buchung("05.01.26", "Kaffee", "-3,50"),
                   self._buchung("05.01.26", "Kaffee", "-3,50")]
        helfer.export_ablegen("export1.csv", helfer.dkb_csv(helfer.GIRO_A, doppelt))
        helfer.export_ablegen("export2.csv", helfer.dkb_csv(helfer.GIRO_A, doppelt))
        parse_konten.run()
        import csv
        with open(parse_konten.OUT, encoding="utf-8-sig") as f:
            self.assertEqual(len(list(csv.DictReader(f, delimiter=";"))), 2)


class TestUmbenannterHaendler(unittest.TestCase):
    """Der Fall, der 09/2026 real 37 Doppelbuchungen und 1426 € zu viel erzeugt hat.

    Die DKB schreibt denselben Kartenumsatz in einem späteren Export anders: aus
    'EDEKA.AKTIV.MARKT/KIRCHZARTEN' wird 'EDEKA Aktiv Markt'. Solange der
    Empfängertext Teil der Buchungs-Kennung war, galt die Zahlung danach als neu."""

    def setUp(self):
        helfer.exporte_leeren()

    def _mit_namen(self, name):
        return ("05.01.26", "Testhaushalt", name, "VISA Debitkartenumsatz vom 05.01.2026",
                "Ausgang", helfer.FREMD, "-42,50", "")

    def _zeilen(self):
        import csv
        with open(parse_konten.OUT, encoding="utf-8-sig") as f:
            return list(csv.DictReader(f, delimiter=";"))

    def test_umbenannter_haendler_ist_keine_neue_buchung(self):
        helfer.export_ablegen("alt.csv", helfer.dkb_csv(
            helfer.GIRO_A, [self._mit_namen("EDEKA.AKTIV.MARKT/KIRCHZARTEN")]))
        helfer.export_ablegen("neu.csv", helfer.dkb_csv(
            helfer.GIRO_A, [self._mit_namen("EDEKA Aktiv Markt")]))
        parse_konten.run()
        self.assertEqual(len(self._zeilen()), 1,
                         "derselbe Umsatz, nur anders geschrieben -> EINE Buchung")

    def test_lesbarer_name_gewinnt(self):
        helfer.export_ablegen("alt.csv", helfer.dkb_csv(
            helfer.GIRO_A, [self._mit_namen("EDEKA.AKTIV.MARKT/KIRCHZARTEN")]))
        helfer.export_ablegen("neu.csv", helfer.dkb_csv(
            helfer.GIRO_A, [self._mit_namen("EDEKA Aktiv Markt")]))
        parse_konten.run()
        self.assertEqual(self._zeilen()[0]["gegenpartei"], "EDEKA Aktiv Markt",
                         "der Text ohne Punkte/Schrägstriche ist der lesbarere")

    def test_zwei_echte_zahlungen_bleiben_zwei(self):
        """Der gefährliche Fall: zweimal derselbe Betrag am selben Tag, und die Bank
        benennt zwischendurch um. Erwartet: zwei Buchungen, nicht eine."""
        helfer.export_ablegen("alt.csv", helfer.dkb_csv(
            helfer.GIRO_A, [self._mit_namen("MAINAU.GMBH/INSEL.MAINAU")] * 2))
        helfer.export_ablegen("neu.csv", helfer.dkb_csv(
            helfer.GIRO_A, [self._mit_namen("Insel Mainau")] * 2))
        parse_konten.run()
        self.assertEqual(len(self._zeilen()), 2)

    def test_verschiedene_haendler_werden_nicht_verschmolzen(self):
        """Gleicher Tag, gleicher Betrag, aber echte verschiedene Gegenseiten:
        unterschiedliche IBAN -> zwei Buchungen."""
        a = ("05.01.26", "Testhaushalt", "Bäckerei Müller", "Brot", "Ausgang",
             helfer.FREMD, "-42,50", "")
        b = ("05.01.26", "Testhaushalt", "Buchladen Schmidt", "Buch", "Ausgang",
             "DE00000000000000000008", "-42,50", "")
        helfer.export_ablegen("export.csv", helfer.dkb_csv(helfer.GIRO_A, [a, b]))
        parse_konten.run()
        self.assertEqual(len(self._zeilen()), 2)


class TestStabileKennung(unittest.TestCase):
    """tx_key darf nur aus Feldern bestehen, die die Bank nicht umschreibt."""

    def test_kennung_haengt_nicht_am_empfaengertext(self):
        import ingest_transactions
        basis = {"konto": "DKB-Haushalt", "datum": "2026-01-05", "betrag": "-42.50",
                 "iban_gegen": helfer.FREMD, "verwendungszweck": "VISA", "buchungstext": "Ausgang"}
        a = dict(basis, gegenpartei="EDEKA.AKTIV.MARKT/KIRCHZARTEN")
        b = dict(basis, gegenpartei="EDEKA Aktiv Markt")
        self.assertEqual(ingest_transactions.tx_key(a), ingest_transactions.tx_key(b))

    def test_andere_gegenseite_ist_andere_buchung(self):
        import ingest_transactions
        basis = {"konto": "DKB-Haushalt", "datum": "2026-01-05", "betrag": "-42.50",
                 "gegenpartei": "Laden"}
        a = dict(basis, iban_gegen=helfer.FREMD)
        b = dict(basis, iban_gegen="DE00000000000000000008")
        self.assertNotEqual(ingest_transactions.tx_key(a), ingest_transactions.tx_key(b))


class TestLeererEingang(unittest.TestCase):
    def test_ohne_exporte_und_ohne_csv_klarer_fehler(self):
        import os
        helfer.exporte_leeren()
        if os.path.exists(parse_konten.OUT):
            os.remove(parse_konten.OUT)
        with self.assertRaises(RuntimeError) as ctx:
            parse_konten.run()
        self.assertIn("konten", str(ctx.exception).lower(),
                      "Die Meldung muss den erwarteten Ordner nennen")


if __name__ == "__main__":
    unittest.main()

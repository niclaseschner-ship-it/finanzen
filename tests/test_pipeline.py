"""Die Pipeline von Ende zu Ende auf einer frischen Datenbank.

Genau der Fall, der beim echten Erstnutzer schiefging: auf einer gewachsenen Datenbank
existieren Tabellen aus früheren Läufen, auf einer leeren nicht. Dieser Test läuft
immer auf leer und hält damit fest, dass der allererste Lauf durchkommt.

Prüft außerdem den Kategorisierungs-Trichter an einem kleinen, vollständig
durchschaubaren Datensatz: Systemgrenze, eingebaute Regel, eigene Regel aus der
Konfiguration, und der ehrliche Rest ('Sonstiges'/unkategorisiert statt geraten).
"""
import os
import unittest
import helfer
import db, run_all


def zeile(datum, empfaenger, zweck, betrag, iban=helfer.FREMD, typ="Ausgang"):
    return (datum, "Testhaushalt", empfaenger, zweck, typ, iban, betrag, "")


class TestErstlauf(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        helfer.exporte_leeren()
        for p in (db.DB_PATH, db.DB_PATH + "-wal", db.DB_PATH + "-shm"):
            if os.path.exists(p):
                os.remove(p)
        helfer.export_ablegen("dkb.csv", helfer.dkb_csv(helfer.GIRO_A, [
            # eingebaute Regel (gilt für jeden Haushalt)
            zeile("05.01.26", "REWE SAGT DANKE/Musterstadt", "Einkauf", "-42,50"),
            zeile("06.01.26", "ALDI SUED/Musterstadt", "Einkauf", "-18,20"),
            # eigene Regel aus konfig.json
            zeile("01.01.26", "Hausverwaltung Mustermann", "Miete Januar", "-850,00"),
            # Systemgrenze: eigenes Konto -> darf keine Ausgabe sein
            zeile("02.01.26", "Eigenes Konto", "Umbuchung", "-1.000,00", helfer.GIRO_B),
            # zugeordnetes Konto -> zählt mit, feste Kategorie
            zeile("03.01.26", "Depotübertrag", "Sparplan", "-500,00", helfer.DEPOT),
            # Einnahme
            zeile("31.01.26", "Arbeitgeber GmbH", "Gehalt", "2.500,00", helfer.FREMD, "Eingang"),
            # bewusst unbekannt -> muss sichtbar offen bleiben
            zeile("07.01.26", "Zrxq Qwertz 88", "ReNr 4711", "-63,00"),
        ]))
        # Bewusst run_all.main() statt einer nachgebauten Reihenfolge: eine Kopie der
        # Schritte würde grün bleiben, wenn jemand run_all.py umsortiert — und genau
        # eine falsche Reihenfolge war der Fehler, den dieser Test festhalten soll.
        # Damit läuft auch branche.run() mit, dessentwegen ensure_schema existiert.
        run_all.main()
        cls.con = db.connect()

    @classmethod
    def tearDownClass(cls):
        cls.con.close()

    def kategorie(self, teil):
        r = self.con.execute("""select c.category, c.status from transactions t
            join tx_category c on c.tx_id=t.id where t.gegenpartei like ?""",
            (f"%{teil}%",)).fetchone()
        self.assertIsNotNone(r, f"keine Buchung für '{teil}' gefunden")
        return r

    def test_alle_buchungen_haben_genau_eine_kategorie(self):
        """Nichts fällt weg — das Kernversprechen der Anwendung."""
        n_tx = self.con.execute("select count(*) from transactions").fetchone()[0]
        n_kat = self.con.execute("select count(*) from tx_category").fetchone()[0]
        self.assertEqual(n_tx, 7)
        self.assertEqual(n_kat, n_tx)

    def test_interne_umbuchung_ist_keine_ausgabe(self):
        flow, intern = self.con.execute(
            "select flow, is_internal from transactions where iban_gegen=?",
            (helfer.GIRO_B,)).fetchone()
        self.assertEqual((flow, intern), ("intern", 1))
        summe = self.con.execute(
            "select coalesce(sum(-betrag),0) from transactions where flow='ausgabe'").fetchone()[0]
        self.assertNotIn(1000.0, [summe], "die Umbuchung darf nicht in den Ausgaben stecken")
        self.assertAlmostEqual(summe, 42.50 + 18.20 + 850.00 + 500.00 + 63.00, places=2)

    def test_eingebaute_regel_greift(self):
        self.assertEqual(self.kategorie("REWE")[0], "Lebensmittel/Drogerie")
        self.assertEqual(self.kategorie("ALDI")[0], "Lebensmittel/Drogerie")

    def test_eigene_regel_aus_konfiguration_greift(self):
        kat, _st = self.kategorie("Hausverwaltung Mustermann")
        self.assertEqual(kat, "Wohnen")

    def test_zugeordnetes_konto_schlaegt_haendlerregel(self):
        kat, _st = self.kategorie("Depot")
        self.assertEqual(kat, "Sparen/Invest")

    def test_einnahme_wird_nicht_zur_ausgabe(self):
        flow = self.con.execute(
            "select flow from transactions where gegenpartei like '%Arbeitgeber%'").fetchone()[0]
        self.assertEqual(flow, "einnahme")

    def test_unbekanntes_bleibt_sichtbar_offen(self):
        """Lieber ehrlich 'unkategorisiert' als eine geratene Kategorie."""
        kat, status = self.kategorie("Zrxq")
        self.assertEqual(kat, "Sonstiges")
        self.assertEqual(status, "unkategorisiert")

    def test_seiten_werden_erzeugt(self):
        for datei in ("statistik.html", "liste.html"):
            p = os.path.join(db.OUTPUT_DIR, datei)
            self.assertTrue(os.path.exists(p), f"{datei} fehlt")
            self.assertGreater(os.path.getsize(p), 1000)

    def test_zweiter_lauf_aendert_nichts(self):
        """Idempotenz: dieselben Daten zweimal einlesen darf nicht doppeln."""
        vorher = self.con.execute("select count(*) from transactions").fetchone()[0]
        run_all.main()
        nachher = self.con.execute("select count(*) from transactions").fetchone()[0]
        self.assertEqual(vorher, nachher)


if __name__ == "__main__":
    unittest.main()

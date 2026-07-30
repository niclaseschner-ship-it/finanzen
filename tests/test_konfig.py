"""Die Konfigurationsprüfung.

Sie ist absichtlich streng: ein Tippfehler in einem Kategorienamen würde sonst still
eine neue Kategorie erzeugen, die als eigene Zeile in der Statistik auftaucht. Lieber
ein Abbruch mit klarer Meldung als eine Auswertung, die falsch aussieht wie richtig.
"""
import copy
import importlib
import unittest
import helfer
import konfig


def mit_konfig(aenderung):
    """Konfiguration ändern, konfig neu laden, geprüftes Modul zurückgeben."""
    daten = copy.deepcopy(helfer.KONFIG)
    aenderung(daten)
    helfer.konfig_schreiben(daten)
    return importlib.reload(konfig)


class TestPruefung(unittest.TestCase):
    def tearDown(self):
        # Gute Konfiguration wiederherstellen — sonst arbeiten nachfolgende Tests
        # (und andere Testmodule im selben Prozess) auf einem kaputten Stand.
        helfer.konfig_schreiben()
        importlib.reload(konfig)

    def test_gute_konfiguration_besteht(self):
        self.assertTrue(konfig.pruefen())

    def test_unbekannte_kategorie_in_zuordnung(self):
        k = mit_konfig(lambda d: d["konten"]["zuordnung"].__setitem__(
            helfer.DEPOT, {"kategorie": "Gibt Es Nicht", "notiz": ""}))
        with self.assertRaises(k.KonfigFehler) as ctx:
            k.pruefen()
        self.assertIn("Gibt Es Nicht", str(ctx.exception))

    def test_unbekannte_kategorie_in_eigener_regel(self):
        def aendern(d):
            d["eigene_regeln"][0]["kategorie"] = "Tippfehler"
        k = mit_konfig(aendern)
        with self.assertRaises(k.KonfigFehler):
            k.pruefen()

    def test_iban_gleichzeitig_intern_und_zugeordnet(self):
        """Ein Konto kann nicht beides sein. Unbemerkt gewinnt sonst die
        Reihenfolge im Code statt einer Entscheidung."""
        def aendern(d):
            d["konten"]["zuordnung"][helfer.GIRO_A] = {"kategorie": "Sparen/Invest"}
        k = mit_konfig(aendern)
        with self.assertRaises(k.KonfigFehler) as ctx:
            k.pruefen()
        self.assertIn(helfer.GIRO_A, str(ctx.exception))

    def test_ohne_eigene_girokonten(self):
        k = mit_konfig(lambda d: d["konten"].__setitem__("eigene_giro", {}))
        with self.assertRaises(k.KonfigFehler) as ctx:
            k.pruefen()
        self.assertIn("Systemgrenze", str(ctx.exception),
                      "Die Meldung muss die Folge erklären, nicht nur 'leer'")

    def test_ohne_kategorien(self):
        k = mit_konfig(lambda d: d.__setitem__("kategorien", []))
        with self.assertRaises(k.KonfigFehler):
            k.pruefen()

    def test_zuordnung_ohne_kategorie_wird_abgefangen(self):
        """Fehlt das Pflichtfeld, muss der Fehler beim Laden kommen — nicht später
        als KeyError irgendwo in der Pipeline.

        Geprüft wird auf RuntimeError (die Basisklasse) statt auf KonfigFehler: der
        Fehler entsteht hier WÄHREND des Neuladens, und dabei wird die Klasse neu
        definiert — die alte Referenz würde nicht mehr passen."""
        def aendern(d):
            d["konten"]["zuordnung"][helfer.DEPOT] = {"notiz": "ohne Kategorie"}
        with self.assertRaises(RuntimeError) as ctx:
            mit_konfig(aendern)
        self.assertIn("kategorie", str(ctx.exception))


class TestLaden(unittest.TestCase):
    def test_normalisiert_ibans(self):
        def aendern(d):
            d["konten"]["eigene_giro"] = {"de00 0000 0000 0000 0000 01": "Mit Leerzeichen"}
        k = mit_konfig(aendern)
        self.assertIn(helfer.GIRO_A, k.EIGENE_GIRO,
                      "Leerzeichen und Kleinschreibung dürfen keinen Treffer verhindern")
        helfer.konfig_schreiben()
        importlib.reload(konfig)

    def test_orte_kleingeschrieben(self):
        def aendern(d):
            d["haushalt"]["heimat_orte"] = ["MusterSTADT", "  musterdorf  "]
        k = mit_konfig(aendern)
        self.assertEqual(k.HEIMAT_ORTE, ["musterstadt", "musterdorf"])
        helfer.konfig_schreiben()
        importlib.reload(konfig)

    def test_eigene_regeln_haben_seed_form(self):
        """Die Regeln aus der Konfiguration müssen dieselbe Form haben wie die
        eingebauten, sonst passen sie nicht in dieselbe Tabelle."""
        r = konfig.EIGENE_REGELN[0]
        self.assertEqual(len(r), 6)
        name, prio, typ, muster, kategorie, labels = r
        self.assertEqual(typ, "haendler_kw")
        self.assertIsInstance(prio, int)
        self.assertEqual(kategorie, "Wohnen")


if __name__ == "__main__":
    unittest.main()

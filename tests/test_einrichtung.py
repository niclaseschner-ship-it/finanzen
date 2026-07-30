"""Die Heuristiken der Einrichtung.

Beide Vorschläge, die `einrichten.py` macht, waren im ersten Wurf falsch — deshalb
sind sie hier festgenagelt:
- Heimatorte über die Zahl der MONATE statt über die Häufigkeit (sonst landet der
  Urlaubsort im Vorschlag, weil man dort in zwei Wochen viel bezahlt).
- Sammelkonten der Bank erkennen (sonst trägt jemand das Verrechnungskonto für
  Kartenzahlungen als eigenes Konto ein und verliert sämtliche Kartenumsätze).
"""
import unittest
import helfer
import einrichten


def inv(orte, monate_gesamt=24):
    """Minimales Inventar: {ort: (anzahl, in wie vielen verschiedenen Monaten)}"""
    return {"orte": {o: {"n": n, "monate": {f"2026-{i % 12 + 1:02d}-x"[:7] for i in range(m)}}
                     for o, (n, m) in orte.items()},
            "monate": {f"m{i}" for i in range(monate_gesamt)}}


class TestHeimatorte(unittest.TestCase):
    def test_urlaubsort_faellt_raus_trotz_vieler_buchungen(self):
        """Der Fall, der die Heuristik nötig gemacht hat: im Urlaub wird oft und viel
        gezahlt — aber nur in einem einzigen Monat."""
        i = inv({"musterstadt": (50, 20), "urlaubsort": (80, 1)})
        v = einrichten.heimat_vorschlag(i)
        self.assertIn("musterstadt", v)
        self.assertNotIn("urlaubsort", v, "häufigster Ort, aber nur ein Monat")

    def test_seltener_nachbarort_wird_erkannt(self):
        """Nachbarorte haben wenige Buchungen, aber verteilt über das ganze Jahr."""
        i = inv({"musterstadt": (200, 22), "nachbardorf": (9, 9)})
        self.assertIn("nachbardorf", einrichten.heimat_vorschlag(i))

    def test_einmaliger_ort_faellt_raus(self):
        i = inv({"musterstadt": (50, 20), "einmal": (1, 1)})
        self.assertNotIn("einmal", einrichten.heimat_vorschlag(i))

    def test_ohne_daten_kein_absturz(self):
        self.assertEqual(einrichten.heimat_vorschlag({"orte": {}, "monate": set()}), [])

    def test_kurzer_zeitraum_verlangt_mindestens_drei_monate(self):
        """Bei nur zwei Monaten Historie darf nicht jeder Ort als Heimat gelten."""
        i = inv({"a": (10, 2), "b": (10, 2)}, monate_gesamt=2)
        self.assertEqual(einrichten.heimat_vorschlag(i), [])


class TestNichtOrte(unittest.TestCase):
    def test_automaten_sammelort_wird_verworfen(self):
        """Kelsterbach steht im Kartentext von Automatenzahlungen, obwohl man nie
        dort war — rules.py kennt den Fall schon für die Reise-Erkennung."""
        self.assertTrue(einrichten._kein_ort("kelsterbach"))

    def test_domains_sind_keine_orte(self):
        for s in ("anthropic com", "shop de", "www beispiel"):
            self.assertTrue(einrichten._kein_ort(s), s)

    def test_echter_ort_bleibt(self):
        for s in ("musterstadt", "freiburg im b", "sankt georgen"):
            self.assertFalse(einrichten._kein_ort(s), s)


class TestSammelkonto(unittest.TestCase):
    def test_viele_namen_unter_einer_iban(self):
        g = {"n": 1500, "summe": -45000.0, "namen": {f"Haendler {i}": 3 for i in range(681)}}
        self.assertTrue(einrichten.ist_sammelkonto(g))
        self.assertIn("Sammelkonto", einrichten.sammel_hinweis(g))

    def test_echtes_gegenkonto_ist_keins(self):
        """Ein Depot oder der Arbeitgeber hat immer denselben Namen."""
        g = {"n": 40, "summe": 27000.0, "namen": {"Arbeitgeber GmbH": 40}}
        self.assertFalse(einrichten.ist_sammelkonto(g))
        self.assertEqual(einrichten.sammel_hinweis(g), "")

    def test_wenige_schreibweisen_sind_kein_sammelkonto(self):
        """Derselbe Zahler taucht mit unterschiedlichen Schreibweisen auf — das darf
        nicht schon als Sammelkonto durchgehen."""
        g = {"n": 30, "summe": 5000.0,
             "namen": {"Muster GmbH": 10, "MUSTER GMBH": 10, "Muster G.m.b.H.": 10}}
        self.assertFalse(einrichten.ist_sammelkonto(g))


class TestInventar(unittest.TestCase):
    def setUp(self):
        helfer.exporte_leeren()

    def test_findet_eigene_und_gegenkonten(self):
        helfer.export_ablegen("dkb.csv", helfer.dkb_csv(helfer.GIRO_A, [
            ("05.01.26", "Testhaushalt", "Laden Musterstadt", "Einkauf", "Ausgang",
             helfer.FREMD, "-20,00", ""),
            ("06.01.26", "Testhaushalt", "Depotübertrag", "Sparen", "Ausgang",
             helfer.DEPOT, "-500,00", ""),
        ]))
        i = einrichten.inventar()
        self.assertIn(helfer.GIRO_A, i["eigene"])
        self.assertIn(helfer.FREMD, i["gegen"])
        self.assertIn(helfer.DEPOT, i["gegen"])
        self.assertEqual(i["gegen"][helfer.DEPOT]["summe"], -500.0)

    def test_ohne_exporte_none(self):
        helfer.exporte_leeren()
        self.assertIsNone(einrichten.inventar())


if __name__ == "__main__":
    unittest.main()

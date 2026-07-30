"""Die Systemgrenze: welche Buchung ist überhaupt eine Ausgabe?

Der teuerste Fehler der ganzen Anwendung. Eine Umbuchung aufs eigene Sparkonto ist
keine Ausgabe — zählt man sie mit, ist die Statistik doppelt so hoch und sieht dabei
völlig plausibel aus. Umgekehrt: markiert man das Konto des Vermieters als "eigenes",
verschwindet die Miete, der größte Posten überhaupt.
"""
import unittest
import helfer
import ingest_transactions as ing


class TestKontenkarte(unittest.TestCase):
    def test_eigenes_giro_ist_intern(self):
        flow, intern, cat, note = ing.classify(helfer.GIRO_A, -1000.0)
        self.assertEqual(flow, "intern")
        self.assertEqual(intern, 1)
        self.assertEqual(cat, "Umbuchung intern")
        self.assertEqual(note, "Test-Giro-A", "Anzeigename aus der Konfiguration")

    def test_richtung_egal_bei_intern(self):
        """Eine interne Umbuchung ist in beide Richtungen intern — sonst taucht die
        Gegenbuchung als Einnahme auf und das Einkommen ist zu hoch."""
        for betrag in (-500.0, 500.0):
            self.assertEqual(ing.classify(helfer.GIRO_B, betrag)[0], "intern")

    def test_zugeordnetes_konto_zaehlt_mit_vorgabe(self):
        flow, intern, cat, note = ing.classify(helfer.DEPOT, -250.0)
        self.assertEqual(flow, "ausgabe", "zählt mit, ist nicht intern")
        self.assertEqual(intern, 0)
        self.assertEqual(cat, "Sparen/Invest")
        self.assertEqual(note, "Testdepot")

    def test_unbekanntes_konto_nach_vorzeichen(self):
        self.assertEqual(ing.classify(helfer.FREMD, -19.99)[0], "ausgabe")
        self.assertEqual(ing.classify(helfer.FREMD, 19.99)[0], "einnahme")
        self.assertIsNone(ing.classify(helfer.FREMD, -19.99)[2],
                          "ohne Eintrag keine Vorgabe-Kategorie")

    def test_leere_iban_bricht_nicht(self):
        """Bargeldabhebungen und manche Kartenumsätze haben keine Gegen-IBAN."""
        for iban in ("", None, "   "):
            flow, intern, cat, _n = ing.classify(iban, -50.0)
            self.assertEqual((flow, intern, cat), ("ausgabe", 0, None))

    def test_iban_schreibweise_egal(self):
        """IBANs kommen mal mit Leerzeichen, mal klein geschrieben aus dem Export.
        Die Konfiguration normalisiert beim Laden — classify muss dasselbe tun, sonst
        ist der Vergleich asymmetrisch und die Systemgrenze fällt still aus.

        (Der Vorgänger dieses Tests prüfte nur `GIRO_A == GIRO_A.upper()` — eine
        Aussage über ein Literal, die auch ohne classify grün gewesen wäre.)"""
        gruppiert = "DE00 0000 0000 0000 0000 01"
        klein = helfer.GIRO_A.lower()
        self.assertEqual(gruppiert.replace(" ", "").upper(), helfer.GIRO_A, "Testdaten ok")
        for schreibweise in (helfer.GIRO_A, gruppiert, klein, f"  {helfer.GIRO_A}  "):
            self.assertEqual(ing.classify(schreibweise, -1000.0)[0], "intern",
                             f"Schreibweise {schreibweise!r} muss die Kontenkarte treffen")


if __name__ == "__main__":
    unittest.main()

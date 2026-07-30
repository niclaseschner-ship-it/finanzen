"""Die Vorsorge-Ansicht muss ihre Annahmen sichtbar machen.

Eine Hochrechnung über Jahrzehnte ist nur so viel wert wie die Annahmen, die man ihr
ansieht. Deshalb wird hier festgehalten, dass Steuersatz, Steuerbehandlung von
Entnahmen und die Sonderrolle von Erbschaften auf der Seite stehen — nicht nur im Kopf
dessen, der sie gebaut hat.

Hinweis: `helfer` MUSS zuerst importiert werden, sonst zieht `app` beim Import die
echte Konfiguration und die echte Datenbank.
"""
import unittest
import helfer            # noqa: F401  (setzt die Testumgebung, muss vor app stehen)
import app
import konfig


class TestVorsorgeSeite(unittest.TestCase):
    def setUp(self):
        self.html = app.VORSORGE_HTML

    def test_steuersatz_ist_eingabefeld(self):
        self.assertIn("id=abgaben", self.html)

    def test_steuerannahme_wird_benannt(self):
        self.assertIn("Steuern auf Entnahmen", self.html)

    def test_erbschaften_ohne_steuer_ist_erklaert(self):
        self.assertIn("Erbschaften/Übertragungen werden hier ausdrücklich ohne Steuern "
                      "modelliert", self.html)

    def test_einkommen_getrennt_ausgewiesen(self):
        self.assertIn("Einkommen · Miete + Rente", self.html)

    def test_erbe_zaehlt_nicht_als_einkommen(self):
        self.assertIn("Erbe nicht enthalten", self.html)


class TestSeitenAuslagerung(unittest.TestCase):
    """Die Seiten liegen als Dateien in scripts/seiten/. Fehlt eine, soll das ein Test
    sagen — nicht ein Absturz beim ersten Aufruf im Browser."""

    def test_alle_seiten_vorhanden_und_nicht_leer(self):
        for name in ("APP_HTML", "VTG_HTML", "REISEN_HTML", "IMPORT_HTML",
                     "SHARED_JS", "VORSORGE_HTML", "VERMOEGEN_HTML"):
            self.assertGreater(len(getattr(app, name)), 500, f"{name} ist verdächtig kurz")

    def test_import_seite_hat_platzhalter(self):
        """Die Import-Seite zeigt den Eingangsordner an; der wird beim Ausliefern
        ersetzt. Fehlt der Platzhalter, steht dort nichts."""
        self.assertIn("__KONTEN__", app.IMPORT_HTML)

    def test_kategorien_kommen_aus_der_konfiguration(self):
        self.assertEqual(app.CATS, konfig.KATEGORIEN)


if __name__ == "__main__":
    unittest.main()

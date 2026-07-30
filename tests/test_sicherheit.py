"""Absicherung gegen Einschleusen von Fremdcode über Buchungstexte.

Der Angriff, um den es geht: Wer die IBAN kennt, überweist einen Cent mit einem
Verwendungszweck wie `</script><img src=x onerror=...>`. Der Text steht im nächsten
Kontoexport, läuft durch die Pipeline und landet in der erzeugten Statistikseite.
Wird er dort unmaskiert in einen <script>-Block geschrieben, beendet der Browser das
Skript-Element vorzeitig und führt den Rest als HTML aus — ohne dass der Nutzer
irgendetwas anklicken müsste.

Dieselbe Quelle gilt für Händlernamen, Mail-Betreffe und Text aus PDF-Anhängen.
"""
import json
import unittest
import helfer            # noqa: F401  (Testumgebung, muss vor den Projektmodulen stehen)
import frontend, liste


ANGRIFFE = [
    "</script><img src=x onerror=alert(1)>",
    "</SCRIPT ><script>fetch('https://boese.example')</script>",
    "<!--</script>-->",
    "Zahlung & Co </script>",
]


class TestSkriptEinbettung(unittest.TestCase):
    """json.dumps allein genügt nicht: es maskiert '<' und '>' nicht."""

    def _pruefen(self, fn, nutzlast):
        aus = fn({"vz": nutzlast, "h": nutzlast})
        self.assertNotIn("</script", aus.lower(),
                         "Skript-Element lässt sich vorzeitig beenden")
        self.assertNotIn("<", aus, "unmaskiertes < im eingebetteten JSON")
        self.assertNotIn(">", aus, "unmaskiertes > im eingebetteten JSON")
        # Und das Wichtigste: der Wert selbst darf sich nicht verändern.
        self.assertEqual(json.loads(aus), {"vz": nutzlast, "h": nutzlast})

    def test_frontend_maskiert(self):
        for n in ANGRIFFE:
            with self.subTest(nutzlast=n):
                self._pruefen(frontend.json_fuer_script, n)

    def test_liste_maskiert(self):
        for n in ANGRIFFE:
            with self.subTest(nutzlast=n):
                self._pruefen(liste.json_fuer_script, n)

    def test_umlaute_bleiben_lesbar(self):
        """Die Maskierung darf nicht alles unleserlich machen — sonst wird sie
        beim nächsten Umbau wieder entfernt."""
        aus = frontend.json_fuer_script({"h": "Bäckerei Müller & Söhne"})
        self.assertIn("Bäckerei Müller", aus)


class TestServerAbsicherung(unittest.TestCase):
    """Der Server hört nur auf 127.0.0.1. Das schützt nicht gegen Anfragen einer
    fremden Seite im selben Browser — dafür sind Host- und Origin-Prüfung da."""

    def setUp(self):
        import app
        self.H = app.H

    def test_erlaubte_hosts_enthalten_loopback(self):
        self.assertTrue(any(h.startswith("127.0.0.1") for h in self.H.ERLAUBTE_HOSTS))
        self.assertFalse(any("evil" in h for h in self.H.ERLAUBTE_HOSTS))

    def test_koerpergroesse_ist_gedeckelt(self):
        self.assertGreater(self.H.MAX_BODY, 1_000_000, "Kontoexporte müssen durchpassen")
        self.assertLess(self.H.MAX_BODY, 1_000_000_000, "aber nicht unbegrenzt")

    def test_pruefmethoden_vorhanden(self):
        for name in ("_host_ok", "_origin_ok"):
            self.assertTrue(callable(getattr(self.H, name, None)), f"{name} fehlt")


if __name__ == "__main__":
    unittest.main()

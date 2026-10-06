"""Die Online-Demo (demo/) und der Demo-Modus.

demo/ wird von demo/bauen.py aus den echten Seiten gebaut und eingecheckt. Diese Tests
prüfen den eingecheckten Stand: jede Seite lenkt ihre Anfragen über demo.js um, verweist
nur auf Dateien, die es gibt, und enthält keine Spur eines Servers (absolute /api/-Pfade,
Weiterleitungen über ?ansicht=).
"""
import os, re, unittest
import helfer            # noqa: F401
import db

DEMO = os.path.join(db.PROJEKT, "demo")
SEITEN = ["start.html", "handy.html", "editor.html", "statistik.html", "vertraege.html",
          "reisen.html", "vermoegen.html", "vorsorge.html"]


def lesen(name):
    with open(os.path.join(DEMO, name), encoding="utf-8") as f:
        return f.read()


class TestDemoSeiten(unittest.TestCase):
    def test_alle_seiten_da_und_umgelenkt(self):
        for s in SEITEN:
            with self.subTest(seite=s):
                html = lesen(s)
                # demo.js muss vor jedem anderen Skript laufen, sonst geht fetch ins Leere
                kopf = html[html.index("<head"):]
                self.assertTrue(re.match(r'<head[^>]*><script src="daten.js"></script><script src="demo.js">', kopf))

    def test_verweise_zeigen_auf_vorhandene_dateien(self):
        vorhanden = set(os.listdir(DEMO))
        for s in SEITEN:
            for ziel in re.findall(r'(?:href|src)="([^"#:?]+)"', lesen(s)):
                with self.subTest(seite=s, ziel=ziel):
                    self.assertIn(ziel, vorhanden)

    def test_keine_serverpfade(self):
        for s in SEITEN:
            with self.subTest(seite=s):
                html = lesen(s)
                self.assertNotRegex(html, r"""(href|src)="/|\?ansicht=|fetch\(\s*['"`]/""")

    def test_daten_sind_erfunden(self):
        daten = lesen("daten.js")
        self.assertIn("Familie Muster", daten)
        self.assertIn("Muster-Giro", daten)


class TestVermoegenPfade(unittest.TestCase):
    def test_vermoegen_liest_aus_dem_datenordner(self):
        import sys
        sys.path.insert(0, os.path.join(db.PROJEKT, "vermoegen"))
        import vermoegen
        p = vermoegen.resolve("vermoegen/eingang/x.csv")
        self.assertTrue(p.startswith(db.BASE), p)


if __name__ == "__main__":
    unittest.main()

"""Finanz-App unter /finanzen/: PWA-Dateien ohne Cookie, Seiten und Daten nur mit;
/finanzen/ erkennt Handy oder Rechner.

Der Browser holt das Manifest ohne Cookie; liefe es hinter der Anmeldung, waere die
App nicht installierbar (Leitfaden im Gedaechtnis: werkzeuge/pwa-leitfaden.md).
Umgekehrt darf nichts mit Buchungen ohne Cookie herausgehen.
"""
import contextlib, hashlib, hmac, http.client, io, json, os, socketserver, threading, time, unittest
import helfer
import db, run_all
import app, handy

TOKEN = "123456:test-token"
HANDY_UA = "Mozilla/5.0 (Linux; Android 14; Pixel 9a) AppleWebKit/537.36 Chrome/129.0 Mobile Safari/537.36"
RECHNER_UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/129.0 Safari/537.36"


def cookie(subjekt="geraet-test"):
    exp = int(time.time()) + 600
    sig = hmac.new(TOKEN.encode(), f"session\n{subjekt}\n{exp}".encode(), hashlib.sha256).hexdigest()
    return f"xbuddy_session={subjekt}.{exp}.{sig}"


def setUpModule():
    # Frische Testdatenbank mit zwei Buchungen, damit die Daten-Routen echte Tabellen sehen.
    helfer.exporte_leeren()
    for p in (db.DB_PATH, db.DB_PATH + "-wal", db.DB_PATH + "-shm"):
        if os.path.exists(p):
            os.remove(p)
    helfer.export_ablegen("dkb.csv", helfer.dkb_csv(helfer.GIRO_A, [
        ("05.01.26", "Testhaushalt", "REWE SAGT DANKE/Musterstadt", "Einkauf", "Ausgang", helfer.FREMD, "-42,50", ""),
        ("07.01.26", "Testhaushalt", "Zrxq Qwertz 88", "ReNr 4711", "Ausgang", helfer.FREMD, "-63,00", ""),
    ]))
    with contextlib.redirect_stdout(io.StringIO()):
        run_all.main()


class TestHandyZugang(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.alt = (app.AUTH_AKTIV, app.BOT_TOKEN, app.ERLAUBTE_IDS)
        app.AUTH_AKTIV, app.BOT_TOKEN, app.ERLAUBTE_IDS = True, TOKEN, frozenset({"*"})
        cls.srv = socketserver.ThreadingTCPServer(("127.0.0.1", 0), app.H)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown(); cls.srv.server_close()
        app.AUTH_AKTIV, app.BOT_TOKEN, app.ERLAUBTE_IDS = cls.alt

    def holen(self, weg, mit_cookie=False, host="localhost", ua=None, extra_cookie=""):
        c = http.client.HTTPConnection("127.0.0.1", self.srv.server_address[1], timeout=10)
        kopf = {"Host": host}
        if mit_cookie:
            kopf["Cookie"] = cookie() + ("; " + extra_cookie if extra_cookie else "")
        if ua:
            kopf["User-Agent"] = ua
        c.request("GET", weg, headers=kopf)
        r = c.getresponse(); body = r.read(); c.close()
        return r.status, dict(r.getheaders()), body

    def test_pwa_dateien_ohne_cookie(self):
        for name in handy.OEFFENTLICH:
            with self.subTest(name=name):
                self.assertEqual(self.holen("/finanzen/" + name)[0], 200)

    def test_seite_und_daten_nur_mit_cookie(self):
        for weg in ("/finanzen/", "/finanzen/api/handy/uebersicht", "/finanzen/api/handy/buchungen?offen=1",
                    "/finanzen/api/handy/vertraege", "/finanzen/api/handy/vermoegen",
                    "/finanzen/api/handy/kategorien", "/finanzen/editor", "/finanzen/stil.css",
                    "/finanzen/vertraege", "/finanzen/api/rows", "/finanzen/api/meta"):
            with self.subTest(weg=weg):
                self.assertEqual(self.holen(weg)[0], 401)
                self.assertEqual(self.holen(weg, mit_cookie=True)[0], 200)

    def test_import_gibt_es_nicht_mehr(self):
        # Kontoexporte spielt der Monatsimport-Skill ein, nicht der Browser (06.10.2026).
        self.assertEqual(self.holen("/finanzen/import", mit_cookie=True)[0], 404)
        self.assertEqual(self.holen("/finanzen/api/sources", mit_cookie=True)[0], 404)
        _, _, body = self.holen("/finanzen/", mit_cookie=True, ua=RECHNER_UA)
        self.assertNotIn(b'href="import"', body)

    def test_unbekannte_datei_nicht_oeffentlich(self):
        # Nur die Liste in handy.OEFFENTLICH geht ohne Cookie raus, kein Pfad-Durchgriff.
        self.assertEqual(self.holen("/finanzen/index.html")[0], 401)
        self.assertEqual(self.holen("/finanzen/../finanzen.db")[0], 401)

    def test_ohne_schraegstrich_weiter(self):
        status, kopf, _ = self.holen("/finanzen")
        self.assertEqual(status, 301)
        self.assertEqual(kopf.get("Location"), "/finanzen/")

    def test_manifest_eigener_bereich_und_feste_id(self):
        m = json.loads(self.holen("/finanzen/manifest.webmanifest")[2])
        self.assertEqual(m["scope"], "./")
        self.assertEqual(m["start_url"], "./")
        self.assertTrue(m["id"].startswith("/") and m["id"] != "/")

    def test_handy_seite_mit_csp(self):
        status, kopf, _ = self.holen("/finanzen/", mit_cookie=True, ua=HANDY_UA)
        self.assertEqual(status, 200)
        self.assertEqual(kopf.get("X-Finanzen-Ansicht"), "handy")
        self.assertIn("frame-ancestors 'none'", kopf.get("Content-Security-Policy", ""))

    def test_rechner_bekommt_uebersicht(self):
        status, kopf, body = self.holen("/finanzen/", mit_cookie=True, ua=RECHNER_UA)
        self.assertEqual(kopf.get("X-Finanzen-Ansicht"), "desktop")
        self.assertIn(b"class=fkopf", body)            # Kopfleiste eingesetzt
        self.assertNotIn(b"<!--FNAV", body)

    def test_umschalter_merkt_sich_die_wahl(self):
        status, kopf, _ = self.holen("/finanzen/?ansicht=desktop", mit_cookie=True, ua=HANDY_UA)
        self.assertEqual(status, 303)
        self.assertEqual(kopf.get("Location"), "./")
        self.assertIn("finanzen_ansicht=desktop", kopf.get("Set-Cookie", ""))
        self.assertIn("HttpOnly", kopf.get("Set-Cookie", ""))
        _, kopf, _ = self.holen("/finanzen/", mit_cookie=True, ua=HANDY_UA, extra_cookie="finanzen_ansicht=desktop")
        self.assertEqual(kopf.get("X-Finanzen-Ansicht"), "desktop")
        _, kopf, _ = self.holen("/finanzen/", mit_cookie=True, ua=RECHNER_UA, extra_cookie="finanzen_ansicht=handy")
        self.assertEqual(kopf.get("X-Finanzen-Ansicht"), "handy")

    def test_desktop_seiten_relativ(self):
        # Unter /finanzen/ funktionieren nur relative Verweise; ein "/api/..." liefe ins Leere.
        for weg in ("/finanzen/editor", "/finanzen/vertraege", "/finanzen/reisen",
                    "/finanzen/vermoegen", "/finanzen/vorsorge", "/finanzen/shared.js"):
            with self.subTest(weg=weg):
                body = self.holen(weg, mit_cookie=True)[2].decode()
                self.assertNotRegex(body, r"""(href|src)="/[a-z]|fetch\(\s*['"`]/""")


class TestFunnel(TestHandyZugang):
    """Oeffentlich (Funnel-Host) ist nur /finanzen/ erreichbar, die Desktop-Seiten nicht.
    Im Tailnet leiten alte und neue Handy-Adresse auf die oeffentliche weiter."""
    FUNNEL = "finanzen.test"

    @classmethod
    def setUpClass(cls):
        cls.alt_funnel = (app.FUNNEL_HOST, app.H.ERLAUBTE_HOSTS)
        app.FUNNEL_HOST = cls.FUNNEL
        app.H.ERLAUBTE_HOSTS = set(app.H.ERLAUBTE_HOSTS) | {cls.FUNNEL}
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        app.FUNNEL_HOST, app.H.ERLAUBTE_HOSTS = cls.alt_funnel

    def holen(self, weg, mit_cookie=False, host=None, **kw):
        return super().holen(weg, mit_cookie, host or self.FUNNEL, **kw)

    def test_ausserhalb_von_finanzen_nichts(self):
        for weg in ("/", "/api/rows", "/vermoegen", "/import", "/menu", "/finanzenx"):
            with self.subTest(weg=weg):
                self.assertEqual(self.holen(weg, mit_cookie=True)[0], 404)

    def test_tailnet_leitet_auf_oeffentlich(self):
        for weg, ziel in (("/handy/", ""), ("/finanzen/", ""), ("/", ""), ("/menu", ""),
                          ("/vertraege", "vertraege"), ("/finanzen/editor", "editor")):
            with self.subTest(weg=weg):
                status, kopf, _ = self.holen(weg, host="localhost")
                self.assertEqual(status, 301)
                self.assertEqual(kopf.get("Location"), f"https://{self.FUNNEL}/finanzen/{ziel}")


class TestGeraet(unittest.TestCase):
    def test_erkennung(self):
        self.assertTrue(app.ist_handy(HANDY_UA))
        self.assertTrue(app.ist_handy("Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) Mobile/15E148"))
        self.assertTrue(app.ist_handy("", "?1"))
        self.assertFalse(app.ist_handy(RECHNER_UA))
        self.assertFalse(app.ist_handy("Mozilla/5.0 (Linux; Android 14; SM-X710) AppleWebKit/537.36 Safari/537.36"))  # Tablet
        self.assertFalse(app.ist_handy(None))


class TestHandyDaten(unittest.TestCase):
    def test_uebersicht_zaehlt_ausgaben(self):
        u = handy.uebersicht()
        jan = next(m for m in u["monate"] if m["ym"] == "2026-01")
        self.assertAlmostEqual(jan["konsum"], 105.5)

    def test_kategorie_vom_handy(self):
        tid = handy.buchungen(q="zrxq")[0]["id"]
        row = handy.bearbeiten({"tx_id": tid, "category": handy.kategorien()[0], "reviewed": 1})["row"]
        self.assertEqual(row["cat"], handy.kategorien()[0])
        self.assertEqual(row["rev"], 1)
        self.assertNotIn(tid, [r["id"] for r in handy.buchungen(offen=True)])

    def test_nur_erlaubte_felder(self):
        self.assertIn("fehler", handy.bearbeiten({"tx_id": "x", "scope": "merchant"}))

    def test_unbekannte_kategorie(self):
        self.assertEqual(handy.bearbeiten({"tx_id": "x", "category": "Gibt es nicht"}),
                         {"fehler": "unbekannte Kategorie"})


if __name__ == "__main__":
    unittest.main()

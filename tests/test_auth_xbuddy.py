"""Cookie-Anmeldung ueber xbuddy: Signatur wie bei xbuddy, aber nur fuer erlaubte Subjekte.

Die Referenz unten ist die Formel aus xbuddy tools/initdata/session_cookie.py
(HMAC-SHA256, Schluessel Bot-Token, Text "session\n<subjekt>\n<exp>"). Aendert xbuddy sie,
muss dieser Test absichtlich mitgezogen werden — sonst waere die Anmeldung still kaputt.
"""
import hashlib, hmac, unittest
import helfer            # noqa: F401
import auth_xbuddy as a

TOKEN = "123456:test-token"
JETZT = 1_800_000_000


def cookie(subjekt, exp, token=TOKEN, domain="session"):
    sig = hmac.new(token.encode(), f"{domain}\n{subjekt}\n{exp}".encode(), hashlib.sha256).hexdigest()
    return f"{subjekt}.{exp}.{sig}"


class TestPruefe(unittest.TestCase):
    def test_gueltig(self):
        self.assertEqual(a.pruefe(cookie("100000001", JETZT + 60), TOKEN, JETZT), "100000001")

    def test_abgelaufen(self):
        self.assertIsNone(a.pruefe(cookie("100000001", JETZT - 1), TOKEN, JETZT))

    def test_falscher_schluessel(self):
        self.assertIsNone(a.pruefe(cookie("100000001", JETZT + 60, token="anderer"), TOKEN, JETZT))

    def test_pairing_token_ist_kein_session_cookie(self):
        self.assertIsNone(a.pruefe(cookie("100000001", JETZT + 60, domain="pair"), TOKEN, JETZT))

    def test_manipuliertes_subjekt(self):
        c = cookie("100000002", JETZT + 60).replace("100000002", "100000001", 1)
        self.assertIsNone(a.pruefe(c, TOKEN, JETZT))

    def test_muell(self):
        for c in (None, "", "x", "a.b", "a.b.c", "a.1.", ".1.x", "a.b.c.d"):
            with self.subTest(c=c):
                self.assertIsNone(a.pruefe(c, TOKEN, JETZT))
        self.assertIsNone(a.pruefe(cookie("1", JETZT + 60), "", JETZT))


class TestErlaubt(unittest.TestCase):
    def hdr(self, subjekt):
        return f"foo=bar; xbuddy_session={cookie(subjekt, JETZT + 60)}; x=y"

    def test_erlaubte_id(self):
        self.assertTrue(a.erlaubt(self.hdr("100000001"), TOKEN, {"100000001"}, JETZT))

    def test_gueltig_aber_nicht_erlaubt(self):
        # Zweites Elternteil und Kindertablet haben gueltige Cookies, sehen aber keine Finanzen.
        self.assertFalse(a.erlaubt(self.hdr("100000002"), TOKEN, {"100000001"}, JETZT))
        self.assertFalse(a.erlaubt(self.hdr("tablet-kind-01"), TOKEN, {"100000001"}, JETZT))

    def test_stern_laesst_jeden_gueltigen_cookie_durch(self):
        self.assertTrue(a.erlaubt(self.hdr("geraet-69b947c8f45d"), TOKEN, {"*"}, JETZT))
        self.assertTrue(a.erlaubt(self.hdr("100000001"), TOKEN, {"*"}, JETZT))

    def test_stern_braucht_trotzdem_gueltigen_cookie(self):
        self.assertFalse(a.erlaubt("foo=bar", TOKEN, {"*"}, JETZT))
        self.assertFalse(a.erlaubt(None, TOKEN, {"*"}, JETZT))
        falsch = f"xbuddy_session={cookie('100000001', JETZT + 60)}0"
        self.assertFalse(a.erlaubt(falsch, TOKEN, {"*"}, JETZT))

    def test_kein_cookie(self):
        self.assertFalse(a.erlaubt("foo=bar", TOKEN, {"100000001"}, JETZT))
        self.assertFalse(a.erlaubt(None, TOKEN, {"100000001"}, JETZT))


class TestUmgebung(unittest.TestCase):
    def test_aus_ohne_variable(self):
        self.assertFalse(a.aus_umgebung({})[0])

    def test_vollstaendig(self):
        env = {"FINANZEN_AUTH": "xbuddy", "ELTERNCHAT_BOT_TOKEN": "t",
               "FINANZEN_ERLAUBTE_IDS": "1, 2", "FINANZEN_OEFFENTLICHER_HOST": "H.example:8447"}
        self.assertEqual(a.aus_umgebung(env), (True, "t", frozenset({"1", "2"}), "h.example:8447"))

    def test_unvollstaendig_ist_fehler_nicht_offen(self):
        voll = {"FINANZEN_AUTH": "xbuddy", "ELTERNCHAT_BOT_TOKEN": "t",
                "FINANZEN_ERLAUBTE_IDS": "1", "FINANZEN_OEFFENTLICHER_HOST": "h"}
        for fehlt in ("ELTERNCHAT_BOT_TOKEN", "FINANZEN_ERLAUBTE_IDS", "FINANZEN_OEFFENTLICHER_HOST"):
            with self.subTest(fehlt=fehlt):
                env = {k: v for k, v in voll.items() if k != fehlt}
                with self.assertRaises(ValueError):
                    a.aus_umgebung(env)


if __name__ == "__main__":
    unittest.main()

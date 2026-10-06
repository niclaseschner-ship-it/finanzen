"""Zentrale Mail-DB: Einblenden als TEMP-Views, Anhangspfade, Schreibschutz.

Gebaut wird eine kleine zentrale DB im Temp-Ordner; db.py liest den Pfad beim Import, deshalb
wird das Modul danach neu geladen. Am Ende wird der Ausgangszustand wiederhergestellt, damit
die uebrigen Tests wieder ohne zentrale DB laufen.
"""
import importlib, os, shutil, sqlite3, tempfile, unittest
import helfer            # noqa: F401
import db


class TestZentraleMailDB(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp(prefix="maildb-test-")
        os.makedirs(os.path.join(cls.dir, "attachments", "gmx"))
        with open(os.path.join(cls.dir, "attachments", "gmx", "a_beleg.pdf"), "wb") as f:
            f.write(b"%PDF-")
        c = sqlite3.connect(os.path.join(cls.dir, "mails.db"))
        c.executescript("""
            CREATE TABLE mails (id TEXT PRIMARY KEY, mailbox TEXT, msg_date TEXT, subject TEXT, body_text TEXT);
            CREATE TABLE attachments (id INTEGER PRIMARY KEY, mail_id TEXT, saved_path TEXT);
            INSERT INTO mails VALUES ('m1','gmx','2026-09-01 10:00','Rechnung','Betrag 12,34');
            INSERT INTO attachments VALUES (1,'m1','gmx/a_beleg.pdf');""")
        c.commit(); c.close()
        cls.alt = os.environ["FINANZEN_MAILDB"]
        os.environ["FINANZEN_MAILDB"] = cls.dir
        importlib.reload(db)

    @classmethod
    def tearDownClass(cls):
        os.environ["FINANZEN_MAILDB"] = cls.alt
        importlib.reload(db)
        shutil.rmtree(cls.dir, ignore_errors=True)

    def test_views_lesen_zentrale_db(self):
        con = db.connect(); self.addCleanup(con.close)
        self.assertEqual(con.execute("select subject from mails").fetchone(), ("Rechnung",))
        self.assertEqual(con.execute("select count(*) from attachments").fetchone(), (1,))

    def test_lokale_tabellen_werden_verdeckt(self):
        db.init()
        lokal = sqlite3.connect(db.DB_PATH)
        lokal.execute("insert into mails(id,mailbox) values ('lokal','x')")
        lokal.commit(); lokal.close()
        con = db.connect(); self.addCleanup(con.close)
        self.assertEqual(con.execute("select count(*) from mails where id='lokal'").fetchone(), (0,))

    def test_schreiben_schlaegt_fehl(self):
        con = db.connect(); self.addCleanup(con.close)
        with self.assertRaises(sqlite3.OperationalError):
            con.execute("insert into mails(id) values ('x')")
        with self.assertRaises(sqlite3.OperationalError):
            con.execute("delete from attachments")

    def test_anhang_pfad_relativ(self):
        p = db.anhang_pfad("gmx/a_beleg.pdf")
        self.assertEqual(p, os.path.realpath(os.path.join(self.dir, "attachments", "gmx", "a_beleg.pdf")))
        self.assertTrue(os.path.exists(p))

    def test_anhang_pfad_alter_windows_pfad(self):
        p = db.anhang_pfad(r"C:\Users\x\finanzen\attachments\gmx\a_beleg.pdf")
        self.assertTrue(os.path.exists(p))

    def test_anhang_pfad_ausbruch_und_leer(self):
        for boese in ("../../etc/passwd", "gmx/../../mails.db", "/etc/passwd", "", None):
            with self.subTest(pfad=boese):
                p = db.anhang_pfad(boese)
                self.assertTrue(p is None or p.startswith(os.path.realpath(os.path.join(self.dir, "attachments"))))
                if p:
                    self.assertFalse(os.path.exists(p))


if __name__ == "__main__":
    unittest.main()

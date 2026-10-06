"""Gemeinsame DB-Helfer + Schema fuer die Ausgaben-Datenbank.
Eine SQLite-DB ist die Wahrheitsschicht; Rohdaten bleiben unangetastet.
"""
import os, sqlite3, datetime, re, pathlib

# ---- Konfiguration: ALLE Pfade an einer Stelle -----------------------------
# Per Umgebungsvariable überschreibbar -> niemand muss den Quellcode editieren.
# Defaults = bisheriges Setup (damit ein bestehender Lauf unverändert weiterläuft).
# BASE = der Projektordner. Default: der Ordner, in dem dieses Repo liegt (nicht ein
# fester Pfad) -> ein Clone läuft ohne Env-Variablen und ohne Code-Änderung.
BASE     = os.environ.get("FINANZEN_BASE", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# Eingang für Bank-CSV-Exporte (= Upload-Ziel der Import-Seite). Liegt im Projekt,
# damit das Projekt keine Ordner außerhalb braucht.
BANK_DIR = os.environ.get("FINANZEN_BANK", os.path.join(BASE, "konten"))
# Zusammengeführte Konto-CSV, die parse_konten.py aus allen Exporten baut.
BANK_CSV = os.environ.get("FINANZEN_BANK_CSV", os.path.join(BASE, "output", "transaktionen.csv"))
# Elternordner des Bank-Eingangs. Nur noch von vermoegen.py genutzt, um relative
# 'konten/...'-Pfade aus positionen.json aufzulösen. Name ist historisch (Steuerprojekt);
# wird mit der Konfig-Umstellung (Schritt 3) abgelöst.
STEUER_DIR = os.path.dirname(BANK_DIR)
# Zentrale Mail-DB (Pi: /srv/mail-db, Projekt maildb). Existiert sie, liest die Finanz-App
# Mails und Anhaenge von dort; die eigenen Tabellen mails/attachments in finanzen.db bleiben
# dann unbenutzt. Fehlt sie (Laptop, Demo, frischer Clone), laeuft alles wie bisher mit den
# eigenen Tabellen. Mit FINANZEN_MAILDB="" laesst sich die zentrale DB abschalten.
# Mit eigenem Datenordner (FINANZEN_BASE: Demo-Haushalt, Tests, zweite Instanz) nie still die
# zentrale DB einblenden — dort liegen echte Mails, die Demo bekaeme sonst echte Belege.
# Dann gilt sie nur, wenn FINANZEN_MAILDB ausdruecklich gesetzt ist.
_MAILDB_STANDARD = "" if os.environ.get("FINANZEN_BASE") else "/srv/mail-db"
MAILDB_DIR = os.environ.get("FINANZEN_MAILDB", _MAILDB_STANDARD)
MAILDB_PATH = os.path.join(MAILDB_DIR, "mails.db") if MAILDB_DIR else ""
MAILDB_AKTIV = bool(MAILDB_PATH) and os.path.exists(MAILDB_PATH)

_PP_PREFIX = re.compile(r"^\s*\d{6,}/PP\.\d+\.PP/\.?\s*")
_PP_INLINE = re.compile(r"/PP\.\d+\.PP/\.?")
_CODE_TAIL = re.compile(r"(?i)\b(EREF|MREF|CRED|IBAN|BIC|SVWZ|MANDATE|GLA?EUBIGER)\b.*$")
_PP_SENDER = re.compile(r"(?i)\s*·?\s*PayPal Europe.*$")
def clean_disp(s):
    """Kryptische Bank-/PayPal-Codes für die ANZEIGE entfernen (Händler/Zweck lesbar machen).
    Verändert NICHT die gespeicherten Daten – nur was im Frontend gezeigt wird."""
    s = s or ""
    s = _PP_PREFIX.sub("", s)        # '1049.../PP.2794.PP/.' am Anfang
    s = _CODE_TAIL.sub("", s)        # ab EREF/MREF/CRED/IBAN/BIC abschneiden
    s = _PP_INLINE.sub(" ", s)
    s = _PP_SENDER.sub("", s)        # '· PayPal Europe S a r l …' am Ende
    s = re.sub(r"\bVISA Debitkartenumsatz vom\b", "Karte", s, flags=re.I)
    s = re.sub(r"\s+", " ", s).strip(" .,/-")
    return s
DB_PATH = os.path.join(BASE, "finanzen.db")
ATTACH_DIR = os.path.join(BASE, "attachments")
OUTPUT_DIR = os.path.join(BASE, "output")

def current_month(today=None):
    """Laufender Monat als 'YYYY-MM' = obere Grenze der Analysen, wenn period_bis leer ist.
    Der laufende Monat zaehlt bewusst MIT (frisch importierter Monat soll sofort sichtbar
    sein). Er ist angebrochen - Monatsvergleiche und Durchschnitte enthalten ihn also als
    Teilmonat, der je nach Importdatum zu niedrig ausfaellt."""
    d = today or datetime.date.today()
    return f"{d.year}-{d.month:02d}"

# Buchungen, die NICHT in eine Reise gehoeren, obwohl sie in ihrem Zeitraum liegen: per X
# ignoriert. Eine Quelle fuer trip_detect (Zuordnung) und die Kosten-Anzeige (Reise-Seite,
# Statistik) - sonst laufen die beiden auseinander, sobald im Editor etwas geaendert wird.
# Bewusst NICHT ueber die Kategorie: Reise-Buchungen sind durchgehend feinkategorisiert
# (Restaurant/Freizeit/Lebensmittel), das ist die Aufschluesselung INNERHALB der Reise und
# kein Ausschluss. Nur das X sagt "gehoert nicht dazu".
TRIP_TX_EXCL_SQL = """coalesce(m.ignore,0)=1"""

def trip_costs(con):
    """{trip_id: kosten} live aus den Labels, mit manueller Schicht. Nicht aus trips.kosten
    lesen - die Spalte ist der Stand des letzten trip_detect-Laufs, waehrend ein Editor-Save
    nur tx_manual schreibt."""
    # distinct tx_id: eine Buchung kann dasselbe Trip-Label doppelt tragen (trip-detect
    # automatisch + manual von Hand) - ohne das zaehlt sie doppelt.
    return {tid: round(k or 0) for tid, k in con.execute(f"""
        select l.label, sum(-t.betrag)
        from (select distinct tx_id, label from tx_labels where label like 'TRIP-%') l
        join transactions t on t.id=l.tx_id
        left join tx_manual m on m.tx_id=t.id
        where t.flow='ausgabe' and not ({TRIP_TX_EXCL_SQL})
        group by l.label""")}

def _ensure_settings(con):
    con.execute("CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, val TEXT)")

def get_setting(key, default=None, con=None):
    own = con is None
    if own: con = connect()
    _ensure_settings(con)
    r = con.execute("select val from settings where key=?", (key,)).fetchone()
    if own: con.close()
    return r[0] if r and r[0] not in (None, "") else default

def set_setting(key, val, con=None):
    own = con is None
    if own: con = connect()
    _ensure_settings(con)
    con.execute("insert or replace into settings(key,val) values(?,?)", (key, val))
    con.commit()
    if own: con.close()

def last_full_month(date_iso):
    """Letzter VOLLSTAENDIG abgedeckter Monat zu einem Datum: reicht die Deckung nicht bis
    Monatsende, zaehlt nur der Vormonat als vollstaendig."""
    import calendar
    if not date_iso or len(date_iso) < 10: return ""
    y, m, d = int(date_iso[:4]), int(date_iso[5:7]), int(date_iso[8:10])
    if d < calendar.monthrange(y, m)[1]:
        m -= 1
        if m < 1: m = 12; y -= 1
    return f"{y}-{m:02d}"

def period_autoset(con=None):
    """Setzt period_bis auf den letzten Monat, den ALLE Konten lueckenlos decken.

    Laeuft am Ende jedes Imports, damit ein frisch importierter Monat von selbst in der
    Statistik steht. Vorher blieb hier der beim letzten Import von Hand gesetzte Wert
    stehen und deckelte die Auswertung still (August fehlte, obwohl die Daten da waren).

    Nur Konten zaehlen, keine Mail-Quellen. Die Import-Seite schlaegt ihr 'bis' ueber
    ALLE Quellen vor, inklusive Postfaechern -- ein hinterherhinkendes Postfach wuerde die
    Statistik sonst um Monate zurueckwerfen, obwohl kein einziger Kontoumsatz fehlt.
    Mails sind Belegkontext, kein Geld.

    Angefangene Monate bleiben draussen: ein Monat mit drei Tagen sieht in der Monatsreihe
    aus wie ein Einbruch. Wer den Deckel selbst setzt, schaltet die Automatik damit ab
    (period_bis_auto=0, gesetzt von der Import-Seite); ein leeres 'bis' schaltet sie
    wieder ein.
    Rueckgabe: der gesetzte Monat, oder '' wenn nichts gesetzt wurde.
    """
    own = con is None
    if own: con = connect()
    try:
        if (get_setting("period_bis_auto", "1", con) or "1") != "1":
            return ""
        enden = [r[0] for r in con.execute(
            "select max(datum) from transactions where coalesce(konto,'')<>'' group by konto")
            if r[0]]
        if not enden: return ""
        bis = last_full_month(min(enden))      # so weit reichen ALLE Konten
        if not bis: return ""
        if bis != (get_setting("period_bis", "", con) or ""):
            set_setting("period_bis", bis, con)
        return bis
    finally:
        if own: con.close()

def period_bounds():
    """Berücksichtigter Analyse-Zeitraum als ('YYYY-MM','YYYY-MM').
    von = settings.period_von (sonst '' = unbegrenzt nach unten);
    bis = settings.period_bis (sonst der laufende Monat).
    Kein Kalender-Deckel mehr: der laufende Monat zaehlt mit, damit ein frisch importierter
    Monat sofort in der Statistik steht. Wer nur vollstaendige Monate auswerten will, setzt
    period_bis auf der Import-Seite auf den Vormonat."""
    von = get_setting("period_von", "") or ""
    bis = get_setting("period_bis", "") or current_month()
    return von, bis

SCHEMA = """
CREATE TABLE IF NOT EXISTS transactions (
    id              TEXT PRIMARY KEY,   -- hash, idempotent
    konto           TEXT,
    datum           TEXT,               -- ISO YYYY-MM-DD
    jahr            INTEGER,
    monat           TEXT,               -- YYYY-MM
    betrag          REAL,
    gegenpartei     TEXT,
    verwendungszweck TEXT,
    buchungstext    TEXT,
    iban_gegen      TEXT,
    glaeubiger_id   TEXT,
    quelle          TEXT,
    flow            TEXT,               -- intern | ausgabe | einnahme
    is_internal     INTEGER,            -- 0/1 (zwischen eigenen Giro-Konten/GEZ -> raus)
    preset_category TEXT,               -- aus Kontenkarte (z.B. Sparen/Invest, Kredit, Einnahme:*)
    preset_note     TEXT
);
CREATE INDEX IF NOT EXISTS ix_tx_datum  ON transactions(datum);
CREATE INDEX IF NOT EXISTS ix_tx_betrag ON transactions(betrag);
CREATE INDEX IF NOT EXISTS ix_tx_monat  ON transactions(monat);
CREATE INDEX IF NOT EXISTS ix_tx_flow   ON transactions(flow);

CREATE TABLE IF NOT EXISTS mails (
    id              TEXT PRIMARY KEY,   -- hash, idempotent
    mailbox         TEXT,               -- gmail | gmx
    message_id      TEXT,
    msg_date        TEXT,               -- ISO
    jahr            INTEGER,
    from_name       TEXT,
    from_addr       TEXT,
    sender_domain   TEXT,
    subject         TEXT,
    body_text       TEXT,               -- decodiert, gekuerzt
    has_attachment  INTEGER
);
CREATE INDEX IF NOT EXISTS ix_mail_date   ON mails(msg_date);
CREATE INDEX IF NOT EXISTS ix_mail_jahr   ON mails(jahr);
CREATE INDEX IF NOT EXISTS ix_mail_domain ON mails(sender_domain);

CREATE TABLE IF NOT EXISTS attachments (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    mail_id         TEXT,
    filename        TEXT,
    content_type    TEXT,
    size            INTEGER,
    saved_path      TEXT,
    extracted_text  TEXT
);
CREATE INDEX IF NOT EXISTS ix_att_mail ON attachments(mail_id);

-- Verarbeitungsprotokoll, damit nichts still verschwindet
CREATE TABLE IF NOT EXISTS ingest_log (
    ts      TEXT,
    step    TEXT,
    detail  TEXT
);
"""

def connect(zentral=True):
    # URI-Modus nur, damit die zentrale Mail-DB schreibgeschuetzt (?mode=ro) angehaengt
    # werden kann; die eigene DB wird ganz normal geoeffnet.
    con = sqlite3.connect(pathlib.Path(DB_PATH).as_uri(), uri=True)
    con.execute("PRAGMA journal_mode=WAL;")
    con.execute("PRAGMA synchronous=NORMAL;")
    if zentral and MAILDB_AKTIV:
        _mails_zentral(con)
    return con

def _mails_zentral(con):
    """mails/attachments aus der zentralen Mail-DB einblenden, nur lesend.

    TEMP-Views gehen bei unqualifizierten Namen vor die gleichnamigen Tabellen in
    finanzen.db: so lesen match.py, build_context.py und app.py ohne Aenderung von dort.
    Schreibzugriffe auf mails/attachments schlagen damit bewusst fehl, Mails kommen nur ueber
    `maildb.py ingest` hinein. Die zentrale DB wird schreibgeschuetzt angehaengt (mode=ro)."""
    con.execute("ATTACH DATABASE ? AS maildb", (pathlib.Path(MAILDB_PATH).as_uri() + "?mode=ro",))
    con.execute("CREATE TEMP VIEW mails AS SELECT * FROM maildb.mails")
    con.execute("CREATE TEMP VIEW attachments AS SELECT * FROM maildb.attachments")

def anhang_pfad(saved_path):
    """Absoluter Pfad zu einem gespeicherten Anhang oder None (leer / ausserhalb des Ordners).

    Zentrale DB: relativ zu <MAILDB_DIR>/attachments. Sonst: attachments/ im Projekt. In beiden
    Faellen zaehlt nur der Teil nach 'attachments', auch bei alten Zeilen mit absolutem
    Windows-Pfad (Laufwerk, Benutzerordner, attachments, Postfach, Datei): die laufen so auch
    auf dem Pi."""
    if not saved_path:
        return None
    basis = os.path.join(MAILDB_DIR, "attachments") if MAILDB_AKTIV else ATTACH_DIR
    teile = re.split(r"[\\/]+", saved_path)
    if "attachments" in teile:
        teile = teile[teile.index("attachments") + 1:]
    p = os.path.realpath(os.path.join(basis, *teile))
    b = os.path.realpath(basis)
    return p if p.startswith(b + os.sep) else None

def init():
    os.makedirs(ATTACH_DIR, exist_ok=True)
    os.makedirs(OUTPUT_DIR, exist_ok=True)   # sonst scheitert frontend/liste im frischen Clone
    con = connect(zentral=False)
    con.executescript(SCHEMA)
    con.commit()
    con.close()
    print("Schema ok ->", DB_PATH)

if __name__ == "__main__":
    init()

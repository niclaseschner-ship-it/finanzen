"""Lokaler Mini-Service (nur Python-Standardbibliothek) fuer direktes Editieren.
Start:  python app.py    ->  http://localhost:8765
Performance: rendert nur gefilterte Zeilen (gedeckelt); Einzel-Edit ist schnell
(kein voller Neu-Lauf); nur 'ganzer Vertrag' rechnet komplett neu.
"""
import json, os, sys, http.server, socketserver, datetime, re
import db, rules, auth_xbuddy, handy

# Die Seiten (HTML/JS) liegen als Dateien in scripts/seiten/ statt als Riesen-Strings
# in dieser Datei. Gleicher Inhalt, aber mit Syntax-Highlighting editierbar und in
# app.py bleibt die Logik sichtbar. Einmal beim Start gelesen: der Server ist ein
# Arbeitswerkzeug, kein Produktivsystem — nach einer Seitenänderung neu starten.
SEITEN_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "seiten")

def _seite(datei):
    with open(os.path.join(SEITEN_DIR, datei), encoding="utf-8") as f:
        return f.read()


def vermoegen_daten():
    """Vermoegens-Snapshot aus dem eigenstaendigen Modul (liest nur Saldenl, nie Umsaetze).
    Lazy importiert, damit die App auch startet, wenn das Modul fehlt."""
    if not os.path.exists(os.path.join(db.BASE, "vermoegen", "positionen.json")):
        return {"fehler": "Noch nicht eingerichtet: vermoegen/positionen.json fehlt. Vorlage: "
                          "vermoegen/positionen.beispiel.json (kopieren und ausfüllen)."}
    try:
        p = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "vermoegen")
        if p not in sys.path:
            sys.path.insert(0, p)
        import vermoegen as _v
        import importlib
        importlib.reload(_v)          # Positionen/Exporte koennen sich zwischen Aufrufen aendern
        return _v.daten()
    except Exception as e:
        return {"fehler": f"{type(e).__name__}: {e}"}

def clean_email(s):
    """Mail-Body lesbar machen: HTML + (als Text eingebettetes) CSS entfernen, Klartext behalten."""
    s = s or ""
    s = re.sub(r"(?is)<style.*?</style>", " ", s)
    s = re.sub(r"(?is)<script.*?</script>", " ", s)
    s = re.sub(r"<[^>]+>", " ", s)                       # HTML-Tags
    s = re.sub(r"/\*.*?\*/", " ", s, flags=re.S)         # CSS-Kommentare
    for _ in range(6):                                   # CSS-Regeln (auch @font-face/@media)
        s = re.sub(r"@?[a-zA-Z0-9_\-#.,:\s\[\]()=\"'%>+~*]*\{[^{}]*\}", " ", s)
    s = re.sub(r"url\([^)]*\)", " ", s)
    s = re.sub(r"[a-zA-Z\-]+\s*:\s*[^;\n]{0,60};", " ", s)   # übrige prop:value;
    s = re.sub(r"&nbsp;|&#160;", " ", s); s = re.sub(r"&[a-z]+;", " ", s)
    s = re.sub(r"https?://\S+", " ", s)
    s = "\n".join(ln.strip() for ln in s.splitlines()
                  if len(ln.strip()) > 1 and re.search(r"[A-Za-zÄÖÜäöü]{3}", ln))
    s = re.sub(r"[ \t]+", " ", s); s = re.sub(r"\n{2,}", "\n", s)
    return s.strip()

_LEGAL2 = re.compile(r"(?i)\b(gmbh|mbh|co|kg|ag|se|sl|srl|sas|bv|ltd|inc|sarl|services|retail|"
                     r"europe|deutschland|com|de|the|und|and)\b")
def merchant_tokens(h):
    s = re.sub(r"[^\w\s]", " ", (h or "").lower())
    s = _LEGAL2.sub(" ", s)
    return [w for w in s.split() if len(w) >= 4][:3]

def related_mails(con, tid, exclude_id, days=5):
    """Eigene Bestell-/Versandmails DESSELBEN Händlers im Zeitfenster (±Tage) – zeigt das PRODUKT,
    das im PayPal-Beleg fehlt. Heuristisch (Händlername + Datum), bewusst als Kandidaten."""
    row = con.execute("""select t.datum, coalesce(e.haendler_norm,t.gegenpartei), t.verwendungszweck
        from transactions t left join tx_enrich e on e.tx_id=t.id where t.id=?""", (tid,)).fetchone()
    if not row: return []
    datum, hn, vz = row
    toks = merchant_tokens(hn)
    mm = re.search(r"(?i)einkauf bei ([a-zäöü0-9 .&-]{3,})", vz or "")
    if mm: toks += merchant_tokens(mm.group(1))
    toks = list(dict.fromkeys([t for t in toks if t]))[:3]
    if not toks: return []
    d0 = datetime.date.fromisoformat(datum[:10])
    lo = (d0 - datetime.timedelta(days=days)).isoformat()
    hi = (d0 + datetime.timedelta(days=2)).isoformat() + " 23:59"
    cond = " or ".join(["lower(from_addr) like ? or lower(from_name) like ? or lower(subject) like ?"] * len(toks))
    params = []
    for t in toks: params += [f"%{t}%", f"%{t}%", f"%{t}%"]
    rows = con.execute(f"""select id,msg_date,from_addr,subject,body_text from mails
        where msg_date between ? and ? and ({cond})
        and lower(from_addr) not like '%paypal%' and id<>?
        order by msg_date desc limit 20""", [lo, hi] + params + [exclude_id or ""]).fetchall()
    # Nach Nutzen sortieren statt nur nach Datum. Der Zweck dieser Liste ist, das PRODUKT
    # zu zeigen, das im Zahlungsbeleg fehlt — das steht in der Bestell- oder Versandmail.
    # Werbemails desselben Absenders trafen den Namensfilter genauso und standen, weil sie
    # taeglich kommen, immer ganz oben und verdeckten die eine nuetzliche Mail.
    KAUF = re.compile(r"(?i)bestell|rechnung|beleg|auftrag|versand|liefer|zahlung|storno|"
                      r"retoure|r[uü]cksend|zustell|quittung|order|invoice")
    # Bewusst NUR Werbe-Merkmale. "no-reply" oder "info@" gehoeren NICHT dazu: darueber
    # verschickt fast jeder Haendler auch seine Bestellbestaetigungen.
    WERB = re.compile(r"(?i)newsletter|marketing|angebot|rabatt|%\s*(on top|rabatt)|sale\b|"
                      r"gutschein|deal|nur heute|letzte chance")
    def istwerbung(r):
        betreff, absender = (r[3] or ""), (r[2] or "")
        if KAUF.search(betreff): return False        # ein Kaufbeleg ist nie Werbung
        return bool(WERB.search(betreff) or WERB.search(absender))
    def rang(r):
        if KAUF.search(r[3] or ""): return -2        # Kaufbeleg zuerst
        return 2 if istwerbung(r) else 0             # Werbung ans Ende
    # Zwei Durchgaenge, weil Pythons sort stabil ist: erst neueste zuerst, dann nach
    # Nutzen umsortieren. In einem Schluessel ginge das nicht, Datum ist ein String
    # und liesse sich nicht zugleich absteigend sortieren.
    rows = sorted(rows, key=lambda r: r[1] or "", reverse=True)
    rows = sorted(rows, key=rang)[:8]
    # Anhaenge der Begleitmails MIT ausliefern. Der Zahlungsbeleg selbst traegt fast nie
    # eine Rechnung — die PDF haengt an der Bestell- oder Rechnungsmail daneben. Ohne das
    # hier war sie ueber die Oberflaeche ueberhaupt nicht erreichbar.
    aus = []
    for r in rows:
        att = [{"id": a[0], "name": a[1] or "(ohne Namen)", "typ": a[2], "size": a[3],
                "zeigbar": a[2] in INLINE_TYPEN, "da": _anhang_da(a[4])}
               for a in con.execute("""select id, filename, coalesce(content_type,''),
                   coalesce(size,0), coalesce(saved_path,'') from attachments
                   where mail_id=? order by id""", (r[0],))]
        aus.append({"date": r[1][:16], "from": (r[2] or "")[:30], "subject": r[3] or "",
                    "werbung": istwerbung(r), "kauf": bool(KAUF.search(r[3] or "")),
                    "anhaenge": att, "snippet": clean_email(r[4])[:280]})
    return aus

# Typen, die der Browser gefahrlos direkt anzeigen darf. Alles andere geht als Download
# raus. Wichtig: NIE text/html o.ae. inline ausliefern — das liefe im selben Ursprung wie
# der Editor und duerfte dann alle Buchungen mitlesen.
def _anhang_da(pfad):
    p = db.anhang_pfad(pfad)
    return bool(p) and os.path.exists(p)

INLINE_TYPEN = {"application/pdf", "image/png", "image/jpeg", "image/jpg",
                "image/gif", "image/webp", "image/bmp"}
MAX_ANHANG = 40 * 1024 * 1024

def attachment_datei(aid):
    """Rohdaten eines Anhangs. Liefert (bytes, content_type, dateiname, inline) oder
    (None, Fehlertext, '', False). Der Pfad kommt aus der DB, wird aber trotzdem gegen
    den Anhang-Ordner geprueft: eine manipulierte Zeile soll nicht das Dateisystem oeffnen."""
    con = db.connect()
    row = con.execute("""select filename, coalesce(content_type,''), coalesce(saved_path,'')
        from attachments where id=?""", (aid,)).fetchone()
    con.close()
    if not row:
        return None, "unbekannter Anhang", "", False
    fn, ct, pfad = row
    if not pfad:
        return None, "keine Datei gespeichert", "", False
    # db.anhang_pfad loest relativ zum Anhang-Ordner auf (zentrale Mail-DB oder Projekt) und
    # liefert None, wenn der Pfad daraus ausbricht.
    echt = db.anhang_pfad(pfad)
    if not echt:
        return None, "Pfad ausserhalb des Anhang-Ordners", "", False
    if not os.path.exists(echt):
        return None, "Datei fehlt auf der Platte", "", False
    if os.path.getsize(echt) > MAX_ANHANG:
        return None, "Datei zu gross fuer die Anzeige", "", False
    with open(echt, "rb") as f:
        roh = f.read()
    inline = ct in INLINE_TYPEN
    return roh, (ct if inline else "application/octet-stream"), (fn or "anhang"), inline

def mail_for_tx(tid):
    """Verknüpfte Mail + zusätzlich nahe Händler-eigene Mails (zeigt Produkt bei PayPal/eBay)."""
    con = db.connect()
    m = con.execute("""select m.id,m.subject,m.from_name,m.from_addr,m.msg_date,m.body_text,
        ml.method,ml.score
        from mails m join tx_mail_links ml on ml.mail_id=m.id
        where ml.tx_id=? order by ml.score desc limit 1""", (tid,)).fetchone()
    rel = related_mails(con, tid, m[0] if m else None)
    if not m:
        con.close(); return {"found": False, "related": rel}
    # sicher (Bestellnr/TxnID) vs. geschätzt (über Betrag)
    sure = m[6] in ("amazon-order", "paypal-txn")
    art = {"amazon-order": "Bestellnummer (sicher)", "paypal-txn": "PayPal-TxnID (sicher)",
           "paypal-merchant-amount": "Händler+Betrag", "paypal-amount-date": "nur Betrag+Datum (Schätzung!)",
           "amount-merchant-date": "Händler+Betrag+Datum (Schätzung)"}.get(m[6], m[6] or "")
    # ALLE Anhaenge, nicht nur die mit ausgelesenem Text. Vorher fielen Bilder und
    # Office-Dateien komplett aus der Anzeige — betroffen war knapp die Haelfte.
    att = []
    for r in con.execute("""select id, filename, coalesce(content_type,''), coalesce(size,0),
            coalesce(extracted_text,''), coalesce(saved_path,'') from attachments
            where mail_id=? order by id""", (m[0],)):
        aid, fn, ct, size, txt, pfad = r
        att.append({"id": aid, "name": fn or "(ohne Namen)", "typ": ct, "size": size,
                    "text": clean_email(txt)[:2500] if txt else "",
                    "da": _anhang_da(pfad),
                    "zeigbar": ct in INLINE_TYPEN})
    con.close()
    return {"found": True, "subject": m[1], "from": (m[2] or "") + " <" + (m[3] or "") + ">",
            "date": m[4], "body": clean_email(m[5])[:6000], "attachments": att, "related": rel,
            "match_art": art, "sure": sure}
# Kategorien: eine Quelle (konfig.json über liste.CATS). Der frühere Fallback war eine
# zweite, veraltete Liste im Code — sie wich von liste.CATS ab und hätte im Editor
# stillschweigend andere Kategorien angeboten als die Statistik kennt.
import konfig, liste
CATS = liste.CATS
PORT = int(os.environ.get("FINANZEN_PORT", "8765"))   # zweite Instanz (z.B. Demo) parallel
# Der Server hoert normalerweise NUR auf 127.0.0.1. Wer die Seiten von einem anderen
# Geraet ansehen will (Handy), setzt FINANZEN_HOST auf die Adresse, unter der dieser
# Rechner dort erreichbar ist — sinnvoll ist die Tailscale-IP, dann kommt nur das
# eigene Tailnet dran und nicht jedes Geraet im WLAN. ACHTUNG: die App hat KEINE
# Anmeldung. Wer die Adresse erreicht, sieht und aendert alle Buchungen.
EXTRA_HOST = (os.environ.get("FINANZEN_HOST") or "").strip()
# Betrieb hinter einem Reverse-Proxy mit Anmeldung (Pi: tailscale serve + xbuddy-Cookie).
# FINANZEN_AUTH=xbuddy schaltet die Cookie-Pruefung ein, siehe auth_xbuddy.py. Der Server
# bleibt dabei auf 127.0.0.1; die Pruefung ersetzt nicht die Bindung, sie kommt dazu.
AUTH_AKTIV, BOT_TOKEN, ERLAUBTE_IDS, OEFFENTLICHER_HOST = auth_xbuddy.aus_umgebung(os.environ)
# Oeffentliche Adresse (tailscale funnel auf :443). Ueber diesen Host ist nur BASIS
# erreichbar; die alte Tailnet-Adresse (OEFFENTLICHER_HOST, :8447) leitet dorthin weiter.
FUNNEL_HOST = (os.environ.get("FINANZEN_FUNNEL_HOST") or "").strip().lower() if AUTH_AKTIV else ""
# Seit 06.10.2026 liegt die ganze App unter BASIS: /finanzen/ erkennt Handy oder Rechner,
# alle Seiten verweisen relativ. Oeffentlich ueber den Funnel, geschuetzt durch den Cookie
# (Standard fuer Pi-Apps, Gedaechtnis werkzeuge/pwa-leitfaden.md).
BASIS = "/finanzen"
KEYS = ["id","d","effm","b","h","art","cat","status","src","labels","ctx","cred","hkey","ignore",
        "dov","vz","vtg","prod","note","reviewed","why"]

def seed_labels():
    con = db.connect()
    con.execute("""CREATE TABLE IF NOT EXISTS tx_manual (tx_id TEXT PRIMARY KEY, category TEXT,
        labels TEXT, ignore INTEGER DEFAULT 0, datum_override TEXT, note TEXT, reviewed INTEGER DEFAULT 0)""")
    try: con.execute("ALTER TABLE tx_manual ADD COLUMN reviewed INTEGER DEFAULT 0")  # Migration
    except Exception: pass
    con.execute("CREATE TABLE IF NOT EXISTS labels_catalog (name TEXT PRIMARY KEY)")
    for (l,) in con.execute("select distinct label from tx_labels where label not like 'TRIP-%'"):
        if l: con.execute("insert or ignore into labels_catalog values(?)", (l.strip(),))
    seed_cats(con)
    con.commit(); con.close()

def seed_cats(con):
    """Kategorien-Katalog (vom Nutzer erweiterbar). Einmalig aus liste.CATS + benutzten
    Kategorien befüllt; Reihenfolge über ord."""
    con.execute("CREATE TABLE IF NOT EXISTS cats_catalog (name TEXT PRIMARY KEY, ord INTEGER)")
    have = set(r[0] for r in con.execute("select name from cats_catalog"))
    nxt = (con.execute("select coalesce(max(ord),0) from cats_catalog").fetchone()[0] or 0)
    for c in CATS:                                    # Seed-Reihenfolge aus liste.CATS
        if c not in have: nxt += 1; con.execute("insert into cats_catalog values(?,?)", (c, nxt)); have.add(c)
    for (c,) in con.execute("select distinct category from tx_category where category is not null"):
        if c and c not in have: nxt += 1; con.execute("insert into cats_catalog values(?,?)", (c, nxt)); have.add(c)

def all_cats(con):
    rows = [r[0] for r in con.execute("select name from cats_catalog order by ord")]
    return rows or CATS

def get_rows(con, tid=None, trip=None, contract=None):
    """Kanonische Buchungs-Objekte für ALLE Detail-Ansichten (Editor/Statistik/Reisen/Verträge).
    Filter: tid (eine Buchung), trip (Reise-Label), contract (Vertrag-ID inkl. Policen-Ref)."""
    import contracts
    q = """select t.id,t.datum,c.eff_monat,t.betrag,coalesce(e.haendler_norm,t.gegenpartei),
        coalesce(e.zahlungsart,''),c.category,c.status,c.source_rule,
        coalesce(group_concat(distinct l.label),''),substr(coalesce(x.ctx,''),1,140),
        coalesce(e.creditor_id,''),lower(coalesce(e.haendler_norm,'')),
        coalesce(m.ignore,0),coalesce(m.datum_override,''),
        trim(coalesce(t.verwendungszweck,'')||' · '||coalesce(t.gegenpartei,'')),
        coalesce(e.ist_vertrag,0),coalesce(x.produkt,''),coalesce(m.note,''),
        coalesce(m.reviewed,0),coalesce(c.reason,'')
      from transactions t join tx_category c on c.tx_id=t.id
      left join tx_enrich e on e.tx_id=t.id
      left join tx_labels l on l.tx_id=t.id and l.label not like 'TRIP-%'
      left join (select tx_id, betreff||' '||snippet ctx, produkt from tx_context) x on x.tx_id=t.id
      left join tx_manual m on m.tx_id=t.id"""
    where, params, reffilter = [], [], None
    if tid: where.append("t.id=?"); params.append(tid)
    if trip: where.append("t.id in (select tx_id from tx_labels where label=?)"); params.append(trip)
    if contract:
        row = con.execute("select key_type,key_val,coalesce(ref,'') from contracts where id=?",
                          (contract,)).fetchone()
        if row:
            kt, kv, reffilter = row
            col = "e.creditor_id" if kt == "creditor" else "e.haendler_norm"
            where.append(f"lower({col})=?"); params.append((kv or "").lower())
        else:
            where.append("0")
    if where: q += " where " + " and ".join(where)
    q += " group by t.id order by t.datum desc"
    rows = con.execute(q, params).fetchall()
    out = []
    for r in rows:
        d = dict(zip(KEYS, r))
        if reffilter and contracts.policy_ref(d["vz"]) != reffilter:
            continue                                   # nur Buchungen DIESER Police
        d["h"] = db.clean_disp(d["h"]) or d["h"]       # kryptische Codes aus Anzeige raus
        d["vz"] = db.clean_disp(d["vz"])
        out.append(d)
    return out

def meta():
    con = db.connect()
    seed_cats(con); con.commit()
    cats = all_cats(con)
    labels = [r[0] for r in con.execute("select name from labels_catalog order by name")]
    con.close()
    return {"cats": cats, "labels": labels}

def add_cat(name):
    name = (name or "").strip()
    con = db.connect()
    con.execute("CREATE TABLE IF NOT EXISTS cats_catalog (name TEXT PRIMARY KEY, ord INTEGER)")
    if name:
        nxt = (con.execute("select coalesce(max(ord),0) from cats_catalog").fetchone()[0] or 0) + 1
        con.execute("insert or ignore into cats_catalog values(?,?)", (name, nxt))
    cats = all_cats(con)
    con.commit(); con.close()
    return {"cats": cats}

def add_label(name):
    name = (name or "").strip()
    con = db.connect()
    con.execute("CREATE TABLE IF NOT EXISTS labels_catalog (name TEXT PRIMARY KEY)")
    if name: con.execute("insert or ignore into labels_catalog values(?)", (name,))
    labels = [r[0] for r in con.execute("select name from labels_catalog order by name")]
    con.commit(); con.close()
    return {"labels": labels}

def save_edit(p):
    con = db.connect()
    for l in (p.get("labels") or "").split(","):
        if l.strip(): con.execute("insert or ignore into labels_catalog values(?)", (l.strip(),))
    if p.get("scope") == "merchant":          # gilt für ganzen Vertrag/Händler -> voller Lauf
        kt = "creditor" if p.get("cred") else "haendler"
        kv = p.get("cred") or p.get("hkey") or ""
        con.execute("""insert or replace into merchant_rules(key_type,key_val,category,labels)
            values(?,?,?,?)""", (kt, kv, p.get("category"), p.get("labels") or ""))
        con.commit(); con.close(); rules.apply_rules(); return {"full": True}
    # Einzelbuchung: schnell, ohne vollen Lauf
    tid = p["tx_id"]
    # Änderungs-Protokoll (nachvollziehbar, für späteres Filter-Tuning): alt -> neu festhalten
    con.execute("""CREATE TABLE IF NOT EXISTS edit_log (ts TEXT, tx_id TEXT, src TEXT,
        haendler TEXT, alt_kat TEXT, neu_kat TEXT, alt_labels TEXT, neu_labels TEXT, ctx TEXT)""")
    pre = con.execute("""select c.category, coalesce(group_concat(distinct l.label),''),
        coalesce(e.haendler_norm,t.gegenpartei), substr(trim(coalesce(t.verwendungszweck,'')),1,80)
        from transactions t join tx_category c on c.tx_id=t.id
        left join tx_enrich e on e.tx_id=t.id left join tx_labels l on l.tx_id=t.id
        where t.id=? group by t.id""", (tid,)).fetchone()
    old_cat, old_lab, hdl, vz = pre if pre else ("", "", "", "")
    new_cat = p.get("category") or old_cat; new_lab = p.get("labels") or ""
    if new_cat != old_cat or new_lab != (old_lab or ""):
        con.execute("insert into edit_log values(?,?,?,?,?,?,?,?,?)",
            (datetime.datetime.now().isoformat(timespec="seconds"), tid, p.get("src") or "editor",
             hdl, old_cat, new_cat, old_lab, new_lab, vz))
    # MERGE: bestehende manuelle Schicht lesen, NICHT gesendete Felder bleiben erhalten
    # (verhindert, dass z.B. ein Kommentar-Save die Kategorie wegräumt o.ä.)
    prev = con.execute("""select category,labels,ignore,datum_override,note,coalesce(reviewed,0)
        from tx_manual where tx_id=?""", (tid,)).fetchone()
    pc, pl, pig, pdo, pn, prv = prev if prev else (None, "", 0, "", "", 0)
    m_cat  = p.get("category")        if "category" in p        else pc
    m_lab  = p.get("labels")          if "labels" in p          else pl
    m_ign  = (1 if p.get("ignore") else 0) if "ignore" in p     else (pig or 0)
    m_dov  = p.get("datum_override")  if "datum_override" in p  else pdo
    m_note = p.get("note")            if "note" in p            else pn
    m_rev  = (1 if p.get("reviewed") else 0) if "reviewed" in p else (prv or 0)
    con.execute("""insert or replace into tx_manual
        (tx_id,category,labels,ignore,datum_override,note,reviewed) values(?,?,?,?,?,?,?)""",
        (tid, m_cat, m_lab or "", m_ign, m_dov or "", m_note or "", m_rev))
    if m_cat:
        con.execute("""update tx_category set category=?,source_rule='manual',reason='manuell',
            confidence=1.0 where tx_id=?""", (m_cat, tid))
    mon = con.execute("select monat from transactions where id=?", (tid,)).fetchone()
    eff = (m_dov or "")[:7] or (mon[0] if mon else None)
    con.execute("update tx_category set eff_monat=?, status=? where tx_id=?",
                (eff, "ignoriert" if m_ign else "ok", tid))
    con.execute("delete from tx_labels where tx_id=? and source_rule='manual'", (tid,))
    for l in (m_lab or "").split(","):
        if l.strip(): con.execute("insert into tx_labels values(?,?,?)", (tid, l.strip(), "manual"))
    con.commit()
    row = get_rows(con, tid)
    con.close()
    return {"row": row[0] if row else None}

# --- Verträge (Übersicht + Anpassen) -------------------------------------
# Monatsfaktor je Rhythmus -> monatliche Belastung vergleichbar machen
MFAK = {"wöchentlich":4.33,"14-tägig":2.17,"monatlich":1.0,"2-monatlich":0.5,
        "quartalsweise":1/3,"halbjährlich":1/6,"jährlich":1/12,"unregelmäßig":0.0}
CKEYS = ["id","name","kategorie","rhythmus","betrag","bmin","bmax","letzter","anzahl",
         "richtung","typ","status","erste","letzte","naechste","monatlich","zweck",
         "aktiv","aktiv_auto","aktiv_manual","seit","jaehrlich"]

def contracts_rows():
    con = db.connect()
    out = []
    for r in con.execute("""select id,name,kategorie,rhythmus,betrag_typ,betrag_min,betrag_max,
        coalesce(betrag_letzter,0),anzahl,richtung,key_type,status,erste,letzte,naechste,
        coalesce(zweck,''),coalesce(aktiv,1),coalesce(tage_seit_letzter,0),aktiv_user from contracts"""):
        (cid,name,kat,rh,bt,bmin,bmax,bletzt,anz,ri,kt,st,erste,letzte,nxt,zweck,aktiv,seit,au) = r
        typ = "SEPA-Lastschrift" if kt == "creditor" else "Überweisung/Karte"
        # Auf EINE vergleichbare Groesse normieren: der typische Betrag mal Takt-Faktor
        # ergibt die Monatsbelastung, mal zwoelf die Jahresbelastung. Nur so stehen ein
        # monatliches Abo und eine Jahrespraemie in derselben Spalte nebeneinander.
        meq = round(abs(bt or 0) * MFAK.get(rh, 0.0), 2)
        jahr = round(meq * 12, 2)
        eff = aktiv if au is None else au          # manueller Override gewinnt über Mechanik
        out.append(dict(zip(CKEYS, [cid,name,kat,rh,round(bt or 0,2),round(bmin or 0,2),
            round(bmax or 0,2),round(bletzt or 0,2),anz,ri,typ,st,erste,letzte,nxt,meq,zweck,
            eff,aktiv,(au is not None),seit,jahr])))
    con.close()
    # bestätigte + aktive zuerst, dann nach Höhe; ausgelaufene/abgelehnte nach unten
    order = {"confirmed":0,"candidate":1,"rejected":2}
    out.sort(key=lambda c: (order.get(c["status"],1), 0 if c["aktiv"] else 1, -c["monatlich"]))
    return out

def trips_rows():
    con = db.connect()
    con.execute("""CREATE TABLE IF NOT EXISTS trips
        (id TEXT PRIMARY KEY, start TEXT, ende TEXT, orte TEXT, kosten REAL, status TEXT, name TEXT)""")
    out = []
    kost = db.trip_costs(con)      # live, nicht die eingefrorene Spalte trips.kosten
    for tid, start, ende, orte, kosten, status, name in con.execute(
            "select id,start,ende,orte,kosten,status,coalesce(name,'') from trips order by start desc"):
        n = con.execute(f"""select count(distinct l.tx_id) from tx_labels l
            left join tx_manual m on m.tx_id=l.tx_id
            where l.label=? and not ({db.TRIP_TX_EXCL_SQL})""", (tid,)).fetchone()[0]
        tage = (datetime.date.fromisoformat(ende) - datetime.date.fromisoformat(start)).days + 1
        out.append({"id": tid, "start": start, "ende": ende, "orte": orte,
                    "kosten": kost.get(tid, 0),
                    "status": status or "candidate", "name": name, "n": n, "tage": tage})
    con.close()
    order = {"confirmed": 0, "candidate": 1, "rejected": 2}
    out.sort(key=lambda t: order.get(t["status"], 1))   # stabil -> Datum-desc bleibt je Gruppe
    return out

def trip_edit(p):
    con = db.connect()
    row = con.execute("select status,name from trips where id=?", (p["id"],)).fetchone()
    if not row: con.close(); return {"error": "unbekannt"}
    st, nm = row
    new_st, new_nm = p.get("status", st), p.get("name", nm)
    con.execute("update trips set status=?, name=? where id=?", (new_st, new_nm, p["id"]))
    con.commit(); con.close()
    if new_st != st or new_nm != nm:        # Urlaubsstempel setzen/entfernen -> mechanischer Re-Lauf
        rules.apply_rules(); import frontend; frontend.run()
    return {"ok": True, "trips": trips_rows()}

def trip_tx(tid):
    """Buchungen einer Reise (Label = TRIP-id), neueste zuerst."""
    con = db.connect()
    rows = con.execute("""select t.datum, t.betrag, coalesce(e.haendler_norm,t.gegenpartei),
        e.ort, c.category, coalesce(x.produkt,'')
        from tx_labels l join transactions t on t.id=l.tx_id
        join tx_category c on c.tx_id=t.id left join tx_enrich e on e.tx_id=t.id
        left join tx_context x on x.tx_id=t.id
        where l.label=? order by t.datum""", (tid,)).fetchall()
    return [{"d": r[0], "b": round(r[1], 2), "h": db.clean_disp(r[2]) or (r[2] or ""),
             "ort": r[3] or "", "cat": r[4], "prod": r[5]} for r in rows]

def contract_tx(cid):
    """Alle Buchungen eines Vertrags (für Popup), neueste zuerst.
    Bei gesplitteten Policen (ref gesetzt) nur die Buchungen DIESER Police."""
    import contracts
    con = db.connect()
    row = con.execute("select key_type,key_val,coalesce(ref,'') from contracts where id=?",
                      (cid,)).fetchone()
    if not row: con.close(); return []
    kt, kv, ref = row
    col = "creditor_id" if kt == "creditor" else "haendler_norm"
    rows = con.execute(f"""select t.datum, t.betrag, coalesce(e.haendler_norm,t.gegenpartei),
        trim(coalesce(t.verwendungszweck,'')), c.category, c.eff_monat
        from tx_enrich e join transactions t on t.id=e.tx_id
        join tx_category c on c.tx_id=e.tx_id
        where lower(e.{col})=? order by t.datum desc""", (str(kv).lower(),)).fetchall()
    con.close()
    if ref:   # nur Buchungen mit passender Policen-/Vertragsreferenz
        rows = [r for r in rows if contracts.policy_ref(r[3]) == ref]
    return [{"d": r[0], "b": round(r[1], 2), "h": r[2], "vz": r[3][:90],
             "cat": r[4], "effm": r[5]} for r in rows]

def contract_edit(p):
    """Status/Name/Kategorie/Aktiv eines Vertrags setzen. Kategorie propagiert über
    merchant_rules auf ALLE Buchungen (voller Re-Lauf); Status/Name/Aktiv sind schnell.
    aktiv: 1/0 = manueller Override, null = zurück auf Mechanik."""
    cid = p["id"]; con = db.connect()
    row = con.execute("""select key_type,key_val,name,kategorie,status
        from contracts where id=?""", (cid,)).fetchone()
    if not row: con.close(); return {"error": "unbekannt"}
    kt, kv, name, kat, st = row
    new_name = p.get("name", name); new_kat = p.get("category", kat); new_st = p.get("status", st)
    cat_changed = bool(p.get("category")) and p["category"] != kat
    con.execute("update contracts set name=?,kategorie=?,status=? where id=?",
                (new_name, new_kat, new_st, cid))
    if "aktiv" in p:   # manueller Aktiv/Ausgelaufen-Override (gewinnt über Mechanik)
        av = p["aktiv"]
        con.execute("update contracts set aktiv_user=? where id=?",
                    (None if av is None else (1 if av else 0), cid))
    if cat_changed:    # nur Kategorie braucht den vollen, mechanischen Neu-Lauf
        con.execute("""insert or replace into merchant_rules(key_type,key_val,category,labels)
            values(?,?,?,coalesce((select labels from merchant_rules where key_type=? and key_val=?),''))""",
            (kt, kv, new_kat, kt, kv))
        con.commit(); con.close()
        rules.apply_rules(); import frontend; frontend.run()
        return {"ok": True, "full": True, "contracts": contracts_rows()}
    con.commit(); con.close()
    return {"ok": True, "contracts": contracts_rows()}

# Import gibt es in der App nicht mehr (seit 06.10.2026): neue Kontoexporte
# spielt der Monatsimport-Skill ein (.claude/skills/finanz-monatsimport), nicht der Browser. Damit
# entfallen Upload, "Daten verarbeiten" und der Zeitraum-Regler samt ihrer API.

APP_HTML = _seite("editor.html")

VTG_HTML = _seite("vertraege.html")

REISEN_HTML = _seite("reisen.html")

SHARED_JS = _seite("shared.js")

# ---- Vorsorge / Ruhestandsplanung ----------------------------------------
# Reine Planungsseite (nicht an die Bankdaten gekoppelt). Der eingegebene Plan
# wird als EIN JSON-Blob in der settings-Tabelle abgelegt -> überlebt Browser-
# Cache-Löschen und wandert ins Home-Backup. localStorage ist nur Sofort-Cache.
def vorsorge_load():
    raw = db.get_setting("vorsorge_plan")
    try:
        plan = json.loads(raw) if raw else None
    except Exception:
        plan = None
    return {"plan": plan}

def vorsorge_save(p):
    plan = p.get("plan") or {}
    db.set_setting("vorsorge_plan", json.dumps(plan, ensure_ascii=False))
    return {"ok": True}

def ist_werte():
    """Ist-Werte fuer die Vorsorge-Vorbelegung, die NICHT aus der Vermoegensseite kommen
    koennen, weil sie aus den Buchungen stammen: monatlicher Bedarf, Sparrate und der
    Netto-Ueberschuss der Immobilien.

    vermoegen.py liest bewusst nur Salden und nie Umsaetze — deshalb ein eigener
    Endpunkt statt einer Erweiterung von /api/vermoegen.

    Fenster: die letzten 12 VOLLEN Monate. Der juengste Monat faellt raus, weil er fast
    immer angebrochen ist und den Schnitt sonst nach unten zieht."""
    con = db.connect()
    neuester = con.execute("select max(monat) from transactions where monat is not null").fetchone()[0]
    if not neuester:
        con.close(); return {"fehler": "keine Buchungen"}
    j, m = int(neuester[:4]), int(neuester[5:7])
    bis_i = j * 12 + (m - 1) - 1                      # letzter VOLLER Monat
    von_i = bis_i - 11                                # 12 Monate insgesamt
    fmt = lambda i: "%04d-%02d" % (i // 12, i % 12 + 1)
    von, bis = fmt(von_i), fmt(bis_i)
    zeit = "t.monat between ? and ?"

    # Konsum: identische Abgrenzung wie die Auswertungen in extra/ (eine Definition,
    # siehe konfig.KAT_NICHT_KONSUM). Zusaetzlich fliegen ignorierte Buchungen raus —
    # was der Nutzer aus der Statistik genommen hat, ist auch kein Lebenshaltungsbedarf.
    excl = konfig.KAT_NICHT_KONSUM
    ph = ",".join("?" * len(excl))
    bedarf_sum, bedarf_n = con.execute(f"""select coalesce(sum(-t.betrag),0), count(*)
        from transactions t join tx_category c on c.tx_id=t.id
        where t.flow='ausgabe' and c.category not in ({ph})
          and coalesce(c.status,'') <> 'ignoriert' and {zeit}""",
        tuple(excl) + (von, bis)).fetchone()

    # Sparrate: was tatsaechlich vom Giro in Richtung Sparen/Depot abgeflossen ist.
    spar_sum, spar_n = con.execute(f"""select coalesce(sum(-t.betrag),0), count(*)
        from transactions t join tx_category c on c.tx_id=t.id
        where c.category='Sparen/Invest' and t.flow='ausgabe'
          and coalesce(c.status,'') <> 'ignoriert' and {zeit}""", (von, bis)).fetchone()

    # Immobilien: Mieteinnahmen MINUS Objektkosten ueber die eigenen Immobilien-Kategorien.
    # Vorzeichen kommt aus betrag selbst (Einnahme positiv).
    #
    # ACHTUNG Doppelzaehlung: die Darlehensrate wird als Ausgabe in genau diesen Kategorien
    # gebucht, steht im Vorsorge-Modell aber schon separat als immo_tilgung und wird dort
    # vom Depot abgezogen. Bliebe sie hier drin, zoege der Kredit die Rendite ein zweites
    # Mal nach unten. Die Darlehenskonten stehen in vermoegen/positionen.json.
    dar_konten = []
    try:
        with open(os.path.join(db.BASE, "vermoegen", "positionen.json"), encoding="utf-8") as f:
            dar_konten = [d["konto"] for d in json.load(f).get("darlehen", []) if d.get("konto")]
    except Exception:
        pass                                          # ohne Datei: dann eben ohne Bereinigung
    immo_netto, immo_n, schuldendienst = 0.0, 0, 0.0
    if konfig.KAT_KEIN_KONSUM:
        iph = ",".join("?" * len(konfig.KAT_KEIN_KONSUM))
        basis = (f"""from transactions t join tx_category c on c.tx_id=t.id
            where c.category in ({iph}) and coalesce(c.status,'') <> 'ignoriert' and {zeit}""")
        immo_netto, immo_n = con.execute(
            f"select coalesce(sum(t.betrag),0), count(*) {basis}",
            tuple(konfig.KAT_KEIN_KONSUM) + (von, bis)).fetchone()
        if dar_konten:
            kph = ",".join("?" * len(dar_konten))
            schuldendienst = con.execute(
                f"select coalesce(sum(-t.betrag),0) {basis} and t.iban_gegen in ({kph})",
                tuple(konfig.KAT_KEIN_KONSUM) + (von, bis) + tuple(dar_konten)).fetchone()[0]
    con.close()
    immo_ohne_kredit = immo_netto + schuldendienst     # Schuldendienst wieder hinzurechnen
    return {"von": von, "bis": bis, "monate": 12,
            "bedarf": round(bedarf_sum / 12.0),
            "bedarf_n": bedarf_n,
            "sparrate": round(spar_sum / 12.0),
            "sparrate_n": spar_n,
            # Fuer die Mietrendite: OHNE Schuldendienst, sonst zaehlt der Kredit doppelt.
            # Frontend teilt durch immo_wert.
            "immo_netto_jahr": round(immo_ohne_kredit),
            "immo_netto_roh": round(immo_netto),      # mit Schuldendienst, nur zur Anzeige
            "immo_schuldendienst": round(schuldendienst),
            "immo_n": immo_n,
            "immo_kategorien": list(konfig.KAT_KEIN_KONSUM)}

VORSORGE_HTML = _seite("vorsorge.html")

# Startseite am Rechner: Monat, Kennzahlen, Wege zu den Seiten (am Handy: handy/index.html).
START_HTML = _seite("start.html")
STIL_CSS = _seite("stil.css")

VERMOEGEN_HTML = _seite("vermoegen.html")

# Gemeinsame Kopfleiste der Desktop-Seiten. Die Seiten tragen nur den Platzhalter
# <!--FNAV:schluessel-->, damit die Navigation an einer Stelle gepflegt wird.
NAVIGATION = [("start", "./", "Übersicht"), ("editor", "editor", "Buchungen"),
              ("statistik", "statistik.html", "Statistik"), ("vertraege", "vertraege", "Verträge"),
              ("reisen", "reisen", "Reisen"), ("vermoegen", "vermoegen", "Vermögen"),
              ("vorsorge", "vorsorge", "Vorsorge")]
_FNAV = re.compile(r"<!--FNAV:(\w+)-->")

def kopfleiste(aktiv):
    links = "".join(f'<a href="{ziel}"' + (' class=an aria-current=page' if k == aktiv else "") + f">{text}</a>"
                    for k, ziel, text in NAVIGATION)
    return ('<header class=fkopf><div class=fkopf-in>'
            '<a class=marke href="./"><img src="icon-192.png" alt=""><span>Finanzen</span></a>'
            f'<nav class=fnav aria-label="Bereiche">{links}</nav>'
            + ('<span class=demo-hinweis title="Erfundener Demo-Haushalt. Eigene Daten einrichten: '
               'python scripts/einrichten.py oder der Skill finanz-einrichtung.">Beispieldaten</span>'
               if db.DEMO_MODUS else '') +
            '<a class=ansicht href="./?ansicht=handy" title="Zur Handy-Ansicht wechseln">'
            '<svg width=16 height=16 viewBox="0 0 24 24" fill=none stroke=currentColor stroke-width=2 '
            'stroke-linecap=round><rect x=7 y=2.5 width=10 height=19 rx=2.5 /><path d="M11 18.5h2"/></svg>'
            '<span>Handy-Ansicht</span></a></div></header>')

_MOBIL = re.compile(r"Mobi|iPhone|iPod|Android.+Mobile|Windows Phone", re.I)

def ist_handy(user_agent, ch_mobil=None):
    """Grobe Geraeteerkennung fuer /finanzen/. Tablets (iPad, Android ohne 'Mobile')
    bekommen die Desktop-Ansicht; der Umschalter in beiden Ansichten ueberstimmt das."""
    if (ch_mobil or "").strip() == "?1":
        return True
    return bool(_MOBIL.search(user_agent or ""))


class H(http.server.BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json", extra=None):
        if ctype.startswith("text/html") and code == 200:
            text = body.decode("utf-8") if isinstance(body, bytes) else body
            body = _FNAV.sub(lambda m: kopfleiste(m.group(1)), text)
        b = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code); self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")  # immer frisch
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
    def log_message(self, *a): pass

    # --- Absicherung gegen fremde Webseiten -------------------------------
    # Der Server hört nur auf 127.0.0.1. Das schützt aber NICHT davor, dass eine
    # beliebige Seite im selben Browser Anfragen hierher schickt:
    #  * schreibend (CSRF): ein POST mit Content-Type text/plain löst keinen
    #    Preflight aus — ohne Prüfung könnte eine fremde Seite Buchungen ändern
    #    oder die Pipeline anstoßen.
    #  * lesend (DNS-Rebinding): zeigt eine Angreiferdomain kurzzeitig auf
    #    127.0.0.1, hält der Browser sie für denselben Ursprung und darf alle
    #    Antworten lesen. Dagegen hilft nur, den Host-Header zu prüfen.
    # Zusaetzliche Adresse, unter der der Server erreichbar sein soll — z.B. die
    # eigene Tailscale-IP, um die Seiten am Handy anzusehen. Ohne die Variable
    # bleibt alles wie bisher: nur der eigene Rechner. Siehe HOST unten.
    ERLAUBTE_HOSTS = {f"127.0.0.1:{PORT}", f"localhost:{PORT}",
                      f"[::1]:{PORT}", "127.0.0.1", "localhost"}
    if EXTRA_HOST:
        ERLAUBTE_HOSTS |= {EXTRA_HOST.lower(), f"{EXTRA_HOST.lower()}:{PORT}"}
    ORIGIN_HOSTS = ("127.0.0.1", "localhost", "[::1]") + ((EXTRA_HOST,) if EXTRA_HOST else ())
    if OEFFENTLICHER_HOST:
        # Hinter dem Proxy kommt der Host-Header des oeffentlichen Namens an (mit Port).
        # Genau dieser eine Name, nicht die Loopback-Adressen: wer die App ueber den
        # Proxy erreicht, soll nicht mit einem anderen Host-Header durchkommen.
        ERLAUBTE_HOSTS = {OEFFENTLICHER_HOST}
        ORIGIN_HOSTS = ()
    if FUNNEL_HOST:
        ERLAUBTE_HOSTS = ERLAUBTE_HOSTS | {FUNNEL_HOST}

    def _host_ok(self):
        return (self.headers.get("Host") or "").lower() in self.ERLAUBTE_HOSTS

    def _ueber_funnel(self):
        return bool(FUNNEL_HOST) and (self.headers.get("Host") or "").lower() == FUNNEL_HOST

    def _origin_ok(self):
        """Schreibende Anfragen nur ohne Origin (eigenes fetch same-origin schickt
        keinen) oder mit einem Origin, der auf diesen Server zeigt."""
        o = self.headers.get("Origin") or self.headers.get("Referer") or ""
        if not o:
            return True
        if OEFFENTLICHER_HOST:
            return any(o == f"https://{h}" or o.startswith(f"https://{h}/")
                       for h in (OEFFENTLICHER_HOST, FUNNEL_HOST) if h)
        return any(o.startswith(f"http://{h}") for h in self.ORIGIN_HOSTS)

    def _angemeldet(self):
        """Ohne FINANZEN_AUTH immer True (lokaler Betrieb wie bisher). Sonst nur mit
        gueltigem xbuddy-Cookie eines erlaubten Subjekts."""
        if not AUTH_AKTIV:
            return True
        return auth_xbuddy.erlaubt(self.headers.get("Cookie"), BOT_TOKEN, ERLAUBTE_IDS)

    def _nicht_angemeldet(self):
        # Bewusst knapp und ohne Hinweis, welcher Teil gefehlt hat (kein Orakel fuer
        # Fremde). 401 statt Weiterleitung: die Anmeldung findet bei xbuddy statt.
        # Den Grund gibt es nur im Journal: fehlender/ungueltiger Cookie, oder ein Subjekt,
        # das nicht in FINANZEN_ERLAUBTE_IDS steht (bei `*` kommt Letzteres nicht vor).
        subjekt = auth_xbuddy.pruefe(auth_xbuddy.cookie_aus_header(self.headers.get("Cookie")), BOT_TOKEN)
        if subjekt:
            print(f"Anmeldung abgewiesen: gueltiger Cookie, Subjekt {subjekt} nicht in FINANZEN_ERLAUBTE_IDS")
        else:
            print("Anmeldung abgewiesen: kein oder ungueltiger xbuddy-Cookie")
        return self._send(401, "<!doctype html><meta charset=utf-8><title>Anmeldung</title>"
                               "<p>Nicht angemeldet. Bitte zuerst bei xbuddy anmelden und "
                               "diese Seite dann erneut öffnen.</p>",
                          "text/html; charset=utf-8")

    def _abweisen(self, grund):
        self._send(403, json.dumps({"fehler": grund}, ensure_ascii=False))

    def do_GET(self):
        if not self._host_ok():
            return self._abweisen("Unerwarteter Host-Header — Zugriff nur über "
                                  "127.0.0.1 oder localhost.")
        weg = self._intern()
        if weg is None:
            return
        from urllib.parse import urlparse, parse_qs
        u = urlparse(weg)
        name = u.path[1:]
        if name in handy.OEFFENTLICH:
            # Ohne Cookie: der Browser holt das Manifest ohne, sonst waere die App nicht
            # installierbar. Darin steht nichts Vertrauliches.
            return self._send(200, handy.datei(name), handy.OEFFENTLICH[name],
                              {"X-Content-Type-Options": "nosniff"})
        if not self._angemeldet():
            return self._nicht_angemeldet()
        self.path = weg
        if u.path == "/":
            return self._start(parse_qs(u.query))
        if u.path.startswith("/api/handy/"):
            return self._handy_api(u.path[len("/api/handy/"):], {k: v[0] for k, v in parse_qs(u.query).items()})
        if self.path == "/editor": return self._send(200, APP_HTML, "text/html; charset=utf-8")
        if self.path == "/stil.css": return self._send(200, STIL_CSS, "text/css; charset=utf-8")
        if self.path == "/shared.js": return self._send(200, SHARED_JS, "application/javascript; charset=utf-8")
        if self.path == "/vertraege": return self._send(200, VTG_HTML, "text/html; charset=utf-8")
        if self.path == "/reisen": return self._send(200, REISEN_HTML, "text/html; charset=utf-8")
        if self.path == "/vorsorge":
            return self._send(200, VORSORGE_HTML, "text/html; charset=utf-8")
        if self.path == "/vermoegen":
            return self._send(200, VERMOEGEN_HTML, "text/html; charset=utf-8")
        if self.path == "/api/vermoegen":
            return self._send(200, json.dumps(vermoegen_daten(), ensure_ascii=False))
        if self.path == "/api/vorsorge":
            return self._send(200, json.dumps(vorsorge_load(), ensure_ascii=False))
        if self.path == "/api/ist_werte":
            return self._send(200, json.dumps(ist_werte(), ensure_ascii=False))
        if self.path == "/api/contracts":
            return self._send(200, json.dumps(contracts_rows(), ensure_ascii=False))
        if self.path == "/api/trips":
            return self._send(200, json.dumps(trips_rows(), ensure_ascii=False))
        if self.path.startswith("/api/trip_tx"):
            from urllib.parse import urlparse, parse_qs
            tid = parse_qs(urlparse(self.path).query).get("id", [""])[0]
            return self._send(200, json.dumps(trip_tx(tid), ensure_ascii=False))
        if self.path.startswith("/api/contract_tx"):
            from urllib.parse import urlparse, parse_qs
            cid = parse_qs(urlparse(self.path).query).get("id", [""])[0]
            return self._send(200, json.dumps(contract_tx(cid), ensure_ascii=False))
        if self.path.startswith("/api/anhang"):
            from urllib.parse import urlparse, parse_qs, quote
            aid = parse_qs(urlparse(self.path).query).get("id", [""])[0]
            try:
                roh, ctype, fn, inline = attachment_datei(int(aid))
            except (TypeError, ValueError):
                roh, ctype = None, "ungueltige Kennung"
            if roh is None:
                return self._send(404, ctype, "text/plain; charset=utf-8")
            # nosniff: der Browser soll den Typ nicht selbst raten und z.B. eine als Bild
            # deklarierte Datei doch noch als HTML ausfuehren.
            return self._send(200, roh, ctype, {
                "X-Content-Type-Options": "nosniff",
                "Content-Disposition": "%s; filename*=UTF-8''%s" % (
                    "inline" if inline else "attachment", quote(fn))})
        if self.path.startswith("/api/mail"):
            from urllib.parse import urlparse, parse_qs
            tid = parse_qs(urlparse(self.path).query).get("tx_id", [""])[0]
            return self._send(200, json.dumps(mail_for_tx(tid), ensure_ascii=False))
        if self.path == "/api/meta": return self._send(200, json.dumps(meta(), ensure_ascii=False))
        if self.path.startswith("/api/rows"):
            from urllib.parse import urlparse, parse_qs
            qs = parse_qs(urlparse(self.path).query)
            con = db.connect()
            r = get_rows(con, trip=qs.get("trip", [None])[0], contract=qs.get("contract", [None])[0])
            con.close()
            return self._send(200, json.dumps(r, ensure_ascii=False))
        if self.path == "/chart.min.js":
            # Liegt im Projekt statt beim CDN: die Statistikseite traegt alle Buchungen
            # als JSON in sich, ein fremdes Skript darin koennte sie mitlesen.
            with open(os.path.join(SEITEN_DIR, "chart.min.js"), "rb") as f:
                return self._send(200, f.read(), "application/javascript; charset=utf-8")
        if self.path == "/statistik.html":        # immer frisch aus DB bauen -> kein alter Schnappschuss
            try:
                import frontend; frontend.run()
            except Exception as e:
                print("statistik rebuild:", e)
        if self.path.endswith(".html"):
            fp = os.path.join(db.BASE, "output", os.path.basename(self.path))
            if os.path.exists(fp):
                with open(fp, "rb") as f:
                    return self._send(200, f.read(), "text/html; charset=utf-8")
        self._send(404, "nicht gefunden", "text/plain")
    # Adressen vor dem 06.10.2026 (ohne /finanzen/) -> neue Adresse
    ALTE_WEGE = {"/": "", "/menu": "", "/handy": "", "/handy/": ""}

    def _intern(self):
        """Pfad unterhalb von BASIS (mit fuehrendem '/'), oder None, wenn die Anfrage
        schon beantwortet ist (Weiterleitung oder 404)."""
        roh, _, query = self.path.partition("?")
        q = ("?" + query) if query else ""
        draussen = f"https://{FUNNEL_HOST}" if FUNNEL_HOST else ""
        if FUNNEL_HOST and not self._ueber_funnel():
            # Tailnet-Adresse (:8447): alles auf die oeffentliche. Android unterscheidet
            # keine Ports, eine zweite Installation unter demselben Pfad soll es nicht geben.
            if roh == BASIS or roh.startswith(BASIS + "/"):
                ziel = roh[len(BASIS) + 1:]
            elif roh.startswith("/handy/"):
                ziel = ""
            else:
                ziel = self.ALTE_WEGE.get(roh, roh.lstrip("/"))
            self._send(301, "", "text/plain", {"Location": f"{draussen}{BASIS}/{ziel}{q}"})
            return None
        if roh == BASIS:                             # ohne Schraegstrich laegen relative
            self._send(301, "", "text/plain", {"Location": f"{BASIS}/{q}"})   # Verweise eine Ebene zu hoch
            return None
        if roh.startswith(BASIS + "/"):
            return self.path[len(BASIS):]
        if self._ueber_funnel():
            self._send(404, "nicht gefunden", "text/plain")
            return None
        ziel = self.ALTE_WEGE.get(roh, roh.lstrip("/"))   # lokaler Betrieb ohne Funnel
        self._send(301, "", "text/plain", {"Location": f"{BASIS}/{ziel}{q}"})
        return None

    def _start(self, qs):
        """/finanzen/: Handy-App am Telefon, Uebersicht am Rechner. ?ansicht=handy|desktop
        merkt sich die Wahl im Cookie finanzen_ansicht, ?ansicht=auto vergisst sie."""
        import http.cookies
        wahl = (qs.get("ansicht") or [""])[0]
        if wahl in ("handy", "desktop", "auto"):
            sicher = "; Secure" if AUTH_AKTIV else ""
            alter = 0 if wahl == "auto" else 365 * 86400
            return self._send(303, "", "text/plain", {
                "Location": "./",
                "Set-Cookie": f"finanzen_ansicht={wahl}; Path={BASIS}/; Max-Age={alter}; "
                              f"SameSite=Lax; HttpOnly{sicher}"})
        keks = http.cookies.SimpleCookie()
        try:
            keks.load(self.headers.get("Cookie") or "")
        except http.cookies.CookieError:
            pass
        gemerkt = keks["finanzen_ansicht"].value if "finanzen_ansicht" in keks else ""
        if gemerkt not in ("handy", "desktop"):
            gemerkt = "handy" if ist_handy(self.headers.get("User-Agent"),
                                           self.headers.get("Sec-CH-UA-Mobile")) else "desktop"
        kopf = {"Vary": "User-Agent, Sec-CH-UA-Mobile, Cookie", "X-Finanzen-Ansicht": gemerkt}
        if gemerkt == "handy":
            kopf.update({"Content-Security-Policy": handy.CSP, "X-Content-Type-Options": "nosniff",
                         "Referrer-Policy": "no-referrer"})
            return self._send(200, handy.datei("index.html"), "text/html; charset=utf-8", kopf)
        return self._send(200, START_HTML, "text/html; charset=utf-8", kopf)

    def _handy_api(self, name, qs):
        """Verdichtete Daten fuer die Handy-App und die Startseite (handy.py)."""
        j = lambda obj: self._send(200, json.dumps(obj, ensure_ascii=False))
        if name == "uebersicht": return j(handy.uebersicht())
        if name == "buchungen":
            return j(handy.buchungen(monat=qs.get("monat"), kat=qs.get("kat"), q=qs.get("q"),
                                     offen=qs.get("offen") == "1"))
        if name == "kategorien": return j(handy.kategorien())
        if name == "vertraege": return j(handy.vertraege())
        if name == "vermoegen": return j(handy.vermoegen())
        if name == "vertrag": return j(contract_tx(qs.get("id", "")))
        return self._send(404, "nicht gefunden", "text/plain")

    MAX_BODY = 1024 * 1024           # nur noch kleine JSON-Aenderungen (Kontoexporte laufen nicht mehr ueber die App)

    def do_POST(self):
        if not self._host_ok():
            return self._abweisen("Unerwarteter Host-Header.")
        if not self._angemeldet():
            return self._nicht_angemeldet()
        if not self._origin_ok():
            return self._abweisen("Schreibende Anfrage von einer fremden Seite abgewiesen.")
        if not self.path.startswith(BASIS + "/"):
            return self._send(404, "{}")
        self.path = self.path[len(BASIS):]
        n = int(self.headers.get("Content-Length", 0))
        if n > self.MAX_BODY:
            # Ohne Deckel liest der Server einen beliebig großen Rumpf komplett in den
            # Speicher — eine fremde Seite könnte damit RAM und Platte volllaufen lassen.
            return self._abweisen(f"Anfrage zu groß ({n} Bytes, erlaubt {self.MAX_BODY}).")
        body = self.rfile.read(n).decode("utf-8") if n else "{}"
        if self.path == "/api/handy/bearbeiten":
            return self._send(200, json.dumps(handy.bearbeiten(json.loads(body)), ensure_ascii=False))
        if self.path == "/api/edit":
            return self._send(200, json.dumps(save_edit(json.loads(body)), ensure_ascii=False))
        if self.path == "/api/addcat":
            return self._send(200, json.dumps(add_cat(json.loads(body).get("name")), ensure_ascii=False))
        if self.path == "/api/addlabel":
            return self._send(200, json.dumps(add_label(json.loads(body).get("name")), ensure_ascii=False))
        if self.path == "/api/contract_edit":
            return self._send(200, json.dumps(contract_edit(json.loads(body)), ensure_ascii=False))
        if self.path == "/api/trip_edit":
            return self._send(200, json.dumps(trip_edit(json.loads(body)), ensure_ascii=False))
        if self.path == "/api/rebuild":
            import frontend; frontend.run(); return self._send(200, '{"ok":true}')
        if self.path == "/api/vorsorge":
            return self._send(200, json.dumps(vorsorge_save(json.loads(body)), ensure_ascii=False))
        self._send(404, "{}")

if __name__ == "__main__":
    if db.DEMO_MODUS and not os.path.exists(db.DB_PATH):
        # Frischer Klon ohne eigene Daten: den Demo-Haushalt einmal anlegen, dann laeuft
        # die App sofort. Eigene Daten richtet einrichten.py bzw. der Skill ein.
        print("Noch keine eigenen Daten — lege den Demo-Haushalt an (einmalig, ~1 Minute) ...")
        import subprocess
        subprocess.run([sys.executable, os.path.join(db.PROJEKT, "beispieldaten", "erzeugen.py")], check=True)
    if db.DEMO_MODUS:
        print("DEMO-MODUS: erfundener Haushalt aus beispieldaten/demo/. Eigene Daten: python einrichten.py")
    seed_labels()
    print(f"Finanzen:  http://127.0.0.1:{PORT}{BASIS}/   (NICHT 'localhost' -> langsam; Strg+C beendet)")
    socketserver.ThreadingTCPServer.allow_reuse_address = True
    # Ohne FINANZEN_HOST wie bisher: nur der eigene Rechner. Mit gesetzter Variable
    # kommt GENAU EINE weitere Adresse dazu, in einem zweiten Socket. Bewusst nicht
    # 0.0.0.0 — sonst haengt der Dienst am ganzen WLAN und der Host-Header waere die
    # einzige Bremse, und den kann jeder faelschen.
    if EXTRA_HOST:
        import threading
        zweit = socketserver.ThreadingTCPServer((EXTRA_HOST, PORT), H)
        threading.Thread(target=zweit.serve_forever, daemon=True).start()
        print(f"Auch erreichbar: http://{EXTRA_HOST}:{PORT}")
        print("ACHTUNG: die App hat KEINE Anmeldung. Wer diese Adresse erreicht, sieht")
        print("und aendert alle Buchungen. Danach wieder ohne FINANZEN_HOST starten.")
    with socketserver.ThreadingTCPServer(("127.0.0.1", PORT), H) as srv:
        srv.serve_forever()

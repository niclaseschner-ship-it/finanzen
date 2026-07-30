"""Baut tx_context: Beleg-/Mail-Stichworte je Buchung (fuer die Detail-Liste).
- verknuepfte Buchung -> Betreff+Snippet der gematchten Mail
- sonst (Sonstiges oder groesserer Betrag) -> Mailsuche nach Haendlername
"""
import re, db, konfig

def declutter(t):
    t = t or ""
    t = re.sub(r"/\*.*?\*/", " ", t, flags=re.S)          # CSS-Kommentare
    # ab erstem CSS/Style-Marker abschneiden (Rest ist Style-Muell)
    m = re.search(r"\{|@charset|@media|@font-face|<!--|html\s*\*|\*\s*:\s*(?:before|after)"
                  r"|font-family\s*:|-webkit-|mso-|doctype|#outlook", t, re.I)
    if m: t = t[:m.start()]
    t = re.sub(r"\{[^{}]*\}", " ", t)
    t = re.sub(r"https?://\S+", " ", t)
    t = re.sub(r"\s+", " ", t)
    return t.strip()

# --- Produkt aus der Mail ziehen (vor allem Amazon/eBay-Betreff nennt das Produkt direkt) ---
_SUBJ = [
    re.compile(r"(?i)^\W*(?:delivered|dispatched|ordered|out for delivery|in zustellung|"
              r"bestellung zugestellt|zugestellt)\s*[:\-]\s*(.+)$"),
    re.compile(r"(?i)^\W*(?:update zur bestellung|versandbest[aä]tigung)\s*[:\-]\s*(.+)$"),
    re.compile(r"(?i)^\W*bestellung best[aä]tigt\s*[:\-]\s*(.+)$"),
    re.compile(r"(?i)ihre amazon\.de[- ]?bestellung von\s+(.+)$"),
    re.compile(r"(?i)amazon\.de[- ]?bestellung mit\s+[\"“'‘](.+?)[\"”'’]"),
    re.compile(r"(?i)did\s+[\"“'‘](.+?)[\"”'’]\s+meet your expectations"),   # Bewertungs-Mail nennt Produkt
    re.compile(r"(?i)^\W*(?:ihre|deine)\s+(.+?)\s+(?:sendung|bestellung)\b"),
]
_NOISE_PROD = re.compile(r"(?i)order\s*#|order number|bestellnummer|sendungsnummer|tracking|"
                         r"^\d+\s+items?\b|^\W*\d[\d\- ]{6,}\W*$")
def _ok_product(p):
    return len(p) >= 3 and re.search(r"[A-Za-zÄÖÜäöü]{3}", p) and not _NOISE_PROD.search(p)

def product_from_mail(subject, body):
    s = (subject or "").strip()
    for rx in _SUBJ:
        m = rx.search(s)
        if m:
            p = m.group(1).strip(" '‘’\"“”")
            p = re.sub(r"(?i)\s*(?:and|und)\s+(\d+)\s+(?:more|weitere?).*$",
                       lambda mm: f" (+{mm.group(1)} weitere)", p)
            p = re.sub(r"[…]+|\.\.\.+", "", p).strip(" '‘’\"“”.-")
            if _ok_product(p): return p[:90]
    # Fallback: Amazon-Body "* Produkt ... Quantity"
    b = declutter(body)
    m = re.search(r"\*\s*([A-Za-z0-9ÄÖÜäöü][^\n*]{6,70}?)\s*(?:Quantity|Menge|Stück|EUR|\d+[.,]\d{2})", b)
    if m and _ok_product(m.group(1).strip()): return m.group(1).strip()[:90]
    return ""

def merchant_tokens(h):
    s = re.sub(r"[^\w\s]", " ", (h or "").lower())
    for w in ("gmbh","mbh","kg","co","ag"," se","sl","srl","sas","services","retail",
              "europe","deutschland","com","de","unlimited","company","ltd","bv","inc"):
        s = re.sub(r"\b" + w.strip() + r"\b", " ", s)
    return [w for w in s.split() if len(w) >= 4][:2]

def merchant_order_product(con, haendler, datum, days=4):
    """Produkt aus der HÄNDLER-EIGENEN Bestellmail (Name+Datum), nicht nur PayPal-Beleg.
    eBay ausgenommen (Bündelung -> mehrdeutig, nur Kandidaten im ✉-Fenster)."""
    import datetime
    if not haendler or not datum or "ebay" in haendler.lower(): return ""
    toks = merchant_tokens(haendler)
    if not toks: return ""
    try: d0 = datetime.date.fromisoformat(datum[:10])
    except Exception: return ""
    lo = (d0 - datetime.timedelta(days=days)).isoformat()
    hi = (d0 + datetime.timedelta(days=2)).isoformat() + " 23:59"
    cond = " or ".join(["lower(from_addr) like ? or lower(from_name) like ? or lower(subject) like ?"] * len(toks))
    params = []
    for t in toks: params += [f"%{t}%", f"%{t}%", f"%{t}%"]
    rows = con.execute(f"""select subject, body_text from mails where msg_date between ? and ?
        and ({cond}) and lower(from_addr) not like '%paypal%' order by msg_date""",
        [lo, hi] + params).fetchall()
    for sub, body in rows:
        p = product_from_mail(sub, body)
        if p: return p
    return ""

def snip(text, term, n=170):
    t = declutter(text)
    # wenn nach dem Saeubern kaum echter Text bleibt -> lieber leer als Muell
    if len(re.sub(r"[^a-zA-ZäöüßÄÖÜ ]", "", t).strip()) < 15:
        return ""
    i = t.lower().find((term or "").lower())
    if i < 0: return t[:n]
    return ("..." if i > 25 else "") + t[max(0, i-30):i+n]

# Woerter, die als Suchbegriff nichts unterscheiden. Allgemeiner Teil hier im Code;
# eigene Orte und Namen kommen aus konfig.json (sonst landen Privatmails als 'Kontext'
# an einer Buchung, nur weil der Nachname vorkommt).
STOP = {"deutschland","europe","payment","ireland","limited","service","station",
        "markt","market","center","online","shop","store","filiale","gmbh",
        "strasse","strase","paypal","google","klarna"}
STOP |= set(konfig.HEIMAT_ORTE) | set(konfig.ORTE_OHNE_SUCHWERT) | set(konfig.EIGENE_NAMEN)

COMPANY = ("gmbh"," ag","e.v","e v"," kg"," ug","mbh"," co ","gesellschaft","e.k","srl",
           "ltd"," bv","inc"," sas"," snc"," spa","ohg","gbr"," ev","verlag","verein"," se")
def is_person(hn):
    h = (hn or "").strip()
    if any(c in (" "+h.lower()+" ") for c in COMPANY): return False
    parts = h.split()
    return 2 <= len(parts) <= 3 and all(re.fullmatch(r"[A-ZÄÖÜ][a-zäöüß-]+", p) for p in parts)

def search_term(hn):
    words = [w for w in re.findall(r"[a-zA-Zäöüß]+", (hn or "").lower())
             if len(w) >= 5 and w not in STOP]
    return max(words, key=len) if words else None

def run():
    con = db.connect()
    con.execute("DROP TABLE IF EXISTS tx_context")
    con.execute("""CREATE TABLE tx_context
        (tx_id TEXT PRIMARY KEY, quelle TEXT, betreff TEXT, snippet TEXT, produkt TEXT)""")
    out = []

    # 1) verknuepfte Buchungen -> gematchte Mail (+ Produkt aus Betreff/Body, sonst Händler-Bestellmail)
    links = con.execute("""select l.tx_id, l.method, m.subject, m.body_text,
        coalesce(e.haendler_norm,t.gegenpartei), t.datum, e.zahlungsart
        from tx_mail_links l join mails m on m.id=l.mail_id
        join transactions t on t.id=l.tx_id left join tx_enrich e on e.tx_id=l.tx_id
        group by l.tx_id""").fetchall()
    have = set()
    for tid, method, sub, body, hn, datum, art in links:
        prod = product_from_mail(sub, body)
        if not prod:                       # PayPal-Beleg nennt oft nur Händler -> Bestellmail suchen
            prod = merchant_order_product(con, hn, datum)
        out.append((tid, "mail:"+method, (sub or "")[:120], snip(body, "", 170), prod))
        have.add(tid)

    # 2) unverknuepfte, wo Kontext am meisten hilft (Sonstiges oder >=50 EUR)
    #    NUR Mails im Zeitfenster +-60 Tage, datumsnaechste gewinnt (kein 4-Jahre-Mismatch)
    import datetime
    rows = con.execute("""select t.id, e.haendler_norm, t.datum, e.zahlungsart from transactions t
        join tx_category c on c.tx_id=t.id left join tx_enrich e on e.tx_id=t.id
        where t.flow='ausgabe' and (c.status='unkategorisiert' or abs(t.betrag)>=50
              or e.zahlungsart='PayPal')""").fetchall()
    for tid, hn, datum, art in rows:
        if tid in have or not hn or not datum: continue
        if is_person(hn): continue          # Privatpersonen: keine Haendler-Mail -> kein Kontext
        term = search_term(hn)
        if not term: continue
        try: d0 = datetime.date.fromisoformat(datum)
        except Exception: continue
        lo = (d0 - datetime.timedelta(days=60)).isoformat()
        hi = (d0 + datetime.timedelta(days=60)).isoformat() + " 23:59"
        t = f"%{term.lower()}%"
        # nur Mails VOM Haendler (Absender-Domain enthaelt das Suchwort) -> praezise statt Zufall
        cand = con.execute("""select msg_date, subject, body_text from mails
            where msg_date between ? and ? and lower(from_addr) like ?""",
            (lo, hi, t)).fetchall()
        if not cand: continue
        best = min(cand, key=lambda c: abs((datetime.date.fromisoformat(c[0][:10]) - d0).days))
        prod = product_from_mail(best[1], best[2]) or merchant_order_product(con, hn, datum)
        out.append((tid, "mail:suche", (best[1] or "")[:120], snip(best[2], term, 170), prod))

    con.executemany("INSERT OR REPLACE INTO tx_context VALUES (?,?,?,?,?)", out)
    con.commit()
    print("Kontext gesetzt:", len(out), "| davon aus Match:", len(have))
    con.close()

if __name__ == "__main__":
    run()

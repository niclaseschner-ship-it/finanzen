"""mbox -> mails + attachments. Einmalig; danach nie wieder die mbox anfassen.
Aufruf:  python ingest_mail.py <mbox_pfad> <label gmail|gmx>
Idempotent: bereits importierte Mails (per id) werden uebersprungen -> resumebar.
PDF-Anhaenge werden gespeichert + Text extrahiert (fitz).
"""
import sys, os, re, hashlib, html, mailbox, datetime
import email.utils, email.header
import db

SKIP_EXT = {".p7s", ".vcf", ".ics", ".asc"}
SAVE_MIN_IMG = 30000          # kleine Inline-Bilder/Logos nicht speichern
BODY_MAX = 50000

def dec(s):
    try:
        return str(email.header.make_header(email.header.decode_header(s)))
    except Exception:
        return str(s or "")

def get_body(m):
    txt, htmltxt = "", ""
    try:
        parts = m.walk() if m.is_multipart() else [m]
        for p in parts:
            ct = p.get_content_type()
            if p.get_filename():
                continue
            if ct == "text/plain":
                pl = p.get_payload(decode=True)
                if pl:
                    txt += pl.decode(p.get_content_charset() or "utf-8", "replace")
            elif ct == "text/html":
                pl = p.get_payload(decode=True)
                if pl:
                    htmltxt += pl.decode(p.get_content_charset() or "utf-8", "replace")
    except Exception:
        pass
    if not txt and htmltxt:
        htmltxt = re.sub(r"(?is)<(style|script|head)[^>]*>.*?</\1>", " ", htmltxt)
        txt = html.unescape(re.sub(r"<[^>]+>", " ", htmltxt))
    return re.sub(r"[ \t]+", " ", txt).strip()[:BODY_MAX]

def pdf_text(path):
    try:
        import fitz
        d = fitz.open(path)
        t = "\n".join(p.get_text() for p in d)
        d.close()
        return t[:BODY_MAX]
    except Exception:
        return ""

def safe(fn):
    return re.sub(r"[^A-Za-z0-9._-]", "_", fn)[:80]

def mail_id(mailbox_label, m):
    mid = (m.get("Message-ID") or "").strip()
    if mid:
        return hashlib.md5((mailbox_label + mid).encode()).hexdigest()
    key = mailbox_label + (m.get("Date","")) + (m.get("From","")) + (m.get("Subject",""))
    return hashlib.md5(key.encode("utf-8", "replace")).hexdigest()

def run(mbox_path, label, min_year=None):
    db.init()
    con = db.connect()
    existing = set(r[0] for r in con.execute(
        "SELECT id FROM mails WHERE mailbox=?", (label,)))
    outdir = os.path.join(db.ATTACH_DIR, label)
    os.makedirs(outdir, exist_ok=True)
    # create=False: sonst oeffnet mailbox die Datei schreibend und legt bei einem
    # falschen Pfad sogar eine neue mbox an - in einem laufenden Thunderbird-Profil.
    mb = mailbox.mbox(mbox_path, create=False)
    n = att = skipped = 0
    for k in mb.keys():
        try:
            m = mb.get_message(k)
        except Exception:
            continue
        mid = mail_id(label, m)
        if mid in existing:
            skipped += 1
            continue
        frm = dec(m.get("From", ""))
        name, addr = email.utils.parseaddr(frm)
        dom = addr.split("@")[-1].lower() if "@" in addr else ""
        try:
            dt = email.utils.parsedate_to_datetime(m.get("Date", ""))
            iso = dt.strftime("%Y-%m-%d %H:%M"); yr = dt.year
        except Exception:
            iso, yr = "", None
        if min_year and yr and yr < min_year:   # alte Mails überspringen (Fokus aktuelle Jahre)
            skipped += 1; continue
        subject = dec(m.get("Subject", ""))
        body = get_body(m)
        atts = []
        if m.is_multipart():
            for p in m.walk():
                fn = p.get_filename()
                if not fn:
                    continue
                fn = dec(fn)
                ext = os.path.splitext(fn)[1].lower()
                if ext in SKIP_EXT:
                    continue
                try:
                    payload = p.get_payload(decode=True)
                except Exception:
                    payload = None
                if not payload:
                    continue
                size = len(payload)
                if ext in (".png", ".jpg", ".jpeg", ".gif") and size < SAVE_MIN_IMG:
                    continue
                path = os.path.join(outdir, f"{mid[:10]}_{safe(fn)}")
                try:
                    with open(path, "wb") as fh:
                        fh.write(payload)
                except Exception:
                    path = ""
                etext = pdf_text(path) if (ext == ".pdf" and path) else ""
                atts.append((mid, fn, p.get_content_type(), size, path, etext))
        con.execute(
            """INSERT OR REPLACE INTO mails
            (id,mailbox,message_id,msg_date,jahr,from_name,from_addr,sender_domain,
             subject,body_text,has_attachment) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (mid, label, (m.get("Message-ID") or "").strip(), iso, yr,
             name, addr, dom, subject, body, 1 if atts else 0))
        for a in atts:
            con.execute("""INSERT INTO attachments
                (mail_id,filename,content_type,size,saved_path,extracted_text)
                VALUES (?,?,?,?,?,?)""", a)
            att += 1
        n += 1
        if n % 500 == 0:
            con.commit()
            print(f"  {label}: {n} neue Mails, {att} Anhaenge ...", flush=True)
    con.execute("INSERT INTO ingest_log VALUES (?,?,?)",
                (datetime.datetime.now().isoformat(timespec="seconds"), "mail:" + label,
                 f"{n} neu, {att} Anhaenge, {skipped} schon vorhanden"))
    con.commit(); con.close()
    print(f"FERTIG {label}: {n} neue Mails, {att} Anhaenge, {skipped} uebersprungen")

if __name__ == "__main__":
    run(sys.argv[1], sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else None)

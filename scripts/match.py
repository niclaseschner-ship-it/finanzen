"""Matcher: verknuepft Buchungen mit Mails/Belegen. Deterministisch zuerst.
Schreibt tx_mail_links (nachvollziehbar: method + reason + score).
"""
import datetime
import db

LINK_SCHEMA = """
CREATE TABLE IF NOT EXISTS tx_mail_links (
  tx_id TEXT, mail_id TEXT, method TEXT, score REAL, reason TEXT
);
CREATE INDEX IF NOT EXISTS ix_link_tx ON tx_mail_links(tx_id);
"""

def daterange(iso_date, days):
    d = datetime.date.fromisoformat(iso_date)
    lo = (d - datetime.timedelta(days=days)).isoformat()
    hi = (d + datetime.timedelta(days=days)).isoformat() + " 23:59"
    return lo, hi

def run():
    con = db.connect()
    con.executescript(LINK_SCHEMA)
    con.execute("DELETE FROM tx_mail_links")
    tx = con.execute("""select t.id,t.datum,t.betrag,t.gegenpartei,e.zahlungsart,
        e.haendler_norm,e.kauf_datum,e.ref_amazon,e.ref_paypal_txn,e.paypal_haendler
        from transactions t join tx_enrich e on e.tx_id=t.id
        where t.flow='ausgabe'""").fetchall()
    links = []; done = set()

    def add(tid, mailrow, method, score, reason):
        links.append((tid, mailrow[0], method, score, reason)); done.add(tid)

    for (tid, datum, betrag, gp, art, hn, kdat, refam, reftxn, pph) in tx:
        amt = f"{abs(betrag):.2f}".replace(".", ",")
        base = kdat or datum
        # 1) Amazon ueber Bestellnummer (stark) - in Body ODER Anhangstext.
        #    Bei mehreren Treffern: PRODUKT-Mail (Delivered/Dispatched/Ordered/Bestellung) bevorzugen,
        #    Bewertungs-/Werbe-Mails ganz nach hinten -> Betreff nennt dann das gekaufte Produkt.
        if refam:
            r = con.execute("""select id from mails where body_text like ? or subject like ?
                   or id in (select mail_id from attachments where extracted_text like ?)
                   order by case
                     when subject like 'Delivered%' then 1
                     when subject like 'Dispatched%' then 2
                     when subject like 'Ordered%' then 3
                     when subject like 'Out for delivery%' then 4
                     when lower(subject) like '%bestellung%' or lower(subject) like '%versand%' then 5
                     when lower(subject) like '%meet your expectations%' or lower(subject) like '%prime day%'
                       or lower(subject) like '%we found%' or lower(subject) like '%deals%'
                       or lower(subject) like '%business%' or lower(subject) like '%benefits%' then 99
                     else 50 end, msg_date desc
                   limit 1""", (f"%{refam}%", f"%{refam}%", f"%{refam}%")).fetchone()
            if r: add(tid, r, "amazon-order", 1.0, f"Bestellnr {refam}"); continue
        # 2) PayPal ueber Transaktions-ID
        if reftxn:
            r = con.execute("""select id from mails where body_text like ? limit 1""",
                            (f"%{reftxn}%",)).fetchone()
            if r: add(tid, r, "paypal-txn", 0.95, f"PP-TxnID {reftxn}"); continue
        # 3) PayPal: Haendler + Betrag im Zeitfenster
        if art == "PayPal" and pph and base:
            lo, hi = daterange(base, 4)
            r = con.execute("""select id from mails where msg_date between ? and ?
                   and (lower(from_addr) like '%paypal%' or lower(subject) like '%paypal%')
                   and (body_text like ? or subject like ?)
                   and body_text like ? limit 1""",
                   (lo, hi, f"%{pph[:18]}%", f"%{pph[:18]}%", f"%{amt}%")).fetchone()
            if r: add(tid, r, "paypal-merchant-amount", 0.8,
                      f"{pph[:18]} + {amt} EUR"); continue
        # 3b) PayPal OHNE Haendler im Buchungstext ("Ihr Einkauf bei" leer): ueber Betrag+Datum.
        #     NUR verknüpfen, wenn EINDEUTIG (eine Händler-Beleg-Mail ODER genau ein Kandidat) –
        #     bei runden Beträgen (mehrere 5€-Zahlungen) sonst Fehlzuordnung -> lieber offen lassen.
        if art == "PayPal" and base:
            lo, hi = daterange(base, 4)
            cands = con.execute("""select id, subject from mails where msg_date between ? and ?
                   and lower(from_addr) like '%paypal%'
                   and (subject like 'Beleg%Zahlung an %' or lower(subject) like '%zahlung gesendet%')
                   and body_text like ? order by msg_date""", (lo, hi, f"%{amt}%")).fetchall()
            belege = [c for c in cands if c[1] and c[1].startswith("Beleg")]
            pick = belege[0] if len(belege) == 1 else (cands[0] if len(cands) == 1 else None)
            if pick:
                add(tid, (pick[0],), "paypal-amount-date", 0.7, f"PayPal {amt} EUR ±4d eindeutig"); continue
        # 4) Generisch: Haendler-Token + Betrag im Zeitfenster
        if hn and base and len(hn) >= 4:
            tok = hn.split()[0]
            if len(tok) >= 4:
                lo, hi = daterange(base, 5)
                r = con.execute("""select id from mails where msg_date between ? and ?
                       and (lower(subject) like ? or lower(from_name) like ? or lower(from_addr) like ?)
                       and body_text like ? limit 1""",
                       (lo, hi, f"%{tok.lower()}%", f"%{tok.lower()}%", f"%{tok.lower()}%",
                        f"%{amt}%")).fetchone()
                if r: add(tid, r, "amount-merchant-date", 0.6,
                          f"{tok} + {amt} EUR ±5d")

    con.executemany("INSERT INTO tx_mail_links VALUES (?,?,?,?,?)", links)
    con.commit()
    print(f"Ausgaben gesamt: {len(tx)} | verknuepft: {len(done)} ({100*len(done)//max(1,len(tx))}%)")
    print("Methoden:", dict(con.execute(
        "select method,count(*) from tx_mail_links group by method").fetchall()))
    con.close()

if __name__ == "__main__":
    run()

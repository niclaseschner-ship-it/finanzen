"""Fuellt fehlende PayPal-Haendler aus den PayPal-Mails (Betrag+Datum -> Haendler aus Betreff)."""
import re, datetime, db

def daterange(iso_date, days):
    d = datetime.date.fromisoformat(iso_date)
    return ((d-datetime.timedelta(days=days)).isoformat(),
            (d+datetime.timedelta(days=days)).isoformat()+" 23:59")

def merchant_from_subject(s):
    s = s or ""
    m = re.search(r"\ban\s+(.+?)(?:\s+autorisiert|\s+gesendet|\s+über|\s+ist\b|\s+bezahlt|$)", s, re.I)
    return m.group(1).strip() if m else None

def run():
    con = db.connect()
    todo = con.execute("""select t.id,t.datum,t.betrag from transactions t
        join tx_enrich e on e.tx_id=t.id
        where e.zahlungsart='PayPal' and e.paypal_haendler is null""").fetchall()
    fixed = 0
    for tid, datum, betrag in todo:
        amt = f"{abs(betrag):.2f}".replace(".", ",")
        lo, hi = daterange(datum, 3)
        r = con.execute("""select subject from mails where msg_date between ? and ?
            and lower(from_addr) like '%paypal%' and body_text like ?
            order by msg_date limit 1""", (lo, hi, f"%{amt}%")).fetchone()
        if not r:
            continue
        merch = merchant_from_subject(r[0])
        if merch and 2 < len(merch) < 60:
            con.execute("update tx_enrich set paypal_haendler=?, haendler_norm=? where tx_id=?",
                        (merch, merch, tid))
            fixed += 1
    con.commit()
    rest = con.execute("""select count(*) from tx_enrich where zahlungsart='PayPal'
                          and paypal_haendler is null""").fetchone()[0]
    print(f"PayPal-Haendler aus Mails ergaenzt: {fixed} | noch ohne Haendler: {rest}")
    con.close()

if __name__ == "__main__":
    run()

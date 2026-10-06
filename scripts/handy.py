"""Handy-App (PWA unter /finanzen/): verdichtete Daten und Auslieferung der App-Dateien.

Die Desktop-Seiten laden alle Buchungen auf einmal (/api/rows, ~1,5 MB). Fuers Handy
rechnet der Server vor: Monatssummen und Kategorien fuer die Uebersicht, Buchungen nur
je Monat, Suche oder Pruefliste. Geschrieben wird ueber dieselbe Funktion wie im
Editor (app.save_edit), damit es genau eine Logik fuer Aenderungen gibt.

Die Einteilung Einnahme / Konsum / Sparen ist dieselbe wie in der Statistik
(frontend.btyp), sonst zeigte das Handy andere Ausgaben als der Rechner.

PWA-Regeln: Gedaechtnis `werkzeuge/pwa-leitfaden.md`. Eigener Pfad /finanzen/, nie die
Wurzel; oeffentlich ueber tailscale funnel, geschuetzt durch den xbuddy-Cookie. Manifest, Icons, sw.js und app-installieren.js gehen ohne Cookie raus (der
Browser holt das Manifest ohne), Seite und Daten nur mit.
"""
import datetime, json, os
from collections import defaultdict

import db
from frontend import btyp

HANDY_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "seiten", "handy")

# Ohne Cookie erreichbar. Darin steht nichts Vertrauliches.
OEFFENTLICH = {
    "manifest.webmanifest": "application/manifest+json",
    "sw.js": "application/javascript; charset=utf-8",
    "app-installieren.js": "application/javascript; charset=utf-8",
    "icon-192.png": "image/png",
    "icon-512.png": "image/png",
    "icon-maskable-512.png": "image/png",
    "apple-touch-icon.png": "image/png",
}

# Die Seite selbst: ein einziges HTML mit eingebettetem Skript (Leitfaden Regel 5a).
CSP = ("default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; "
       "img-src 'self' data:; connect-src 'self'; manifest-src 'self'; worker-src 'self'; "
       "frame-ancestors 'none'; base-uri 'none'; form-action 'none'")


def datei(name):
    with open(os.path.join(HANDY_DIR, name), "rb") as f:
        return f.read()


# ---- Daten -------------------------------------------------------------------

_BASIS = """from transactions t join tx_category c on c.tx_id=t.id
    left join tx_enrich e on e.tx_id=t.id
    left join tx_manual m on m.tx_id=t.id
    left join tx_context x on x.tx_id=t.id"""

_SPALTEN = """t.id, t.datum, c.eff_monat, t.betrag, t.flow, c.category, coalesce(c.status,''),
    coalesce(e.haendler_norm, t.gegenpartei), coalesce(e.zahlungsart,''),
    trim(coalesce(t.verwendungszweck,'')), coalesce(x.produkt,''),
    coalesce(m.note,''), coalesce(m.reviewed,0), coalesce(m.ignore,0), t.konto,
    coalesce(c.source_rule,'')"""


def _buchung(r):
    (tid, datum, effm, b, flow, cat, st, h, art, vz, prod, note, rev, ign, konto, src) = r
    return {"id": tid, "d": datum, "m": effm, "b": round(b, 2), "h": db.clean_disp(h) or (h or ""),
            "cat": cat, "st": st, "art": art, "vz": db.clean_disp(vz)[:220], "prod": prod,
            "note": note, "rev": rev, "ign": ign, "konto": konto, "src": src,
            "typ": btyp(cat, flow) or "intern"}


def _monate_zurueck(ym, n):
    j, m = int(ym[:4]), int(ym[5:7])
    i = j * 12 + m - 1 - n
    return "%04d-%02d" % (i // 12, i % 12 + 1)


# "Offen" heisst: die Mechanik ist sich nicht sicher und niemand hat es angesehen.
_OFFEN_SQL = """coalesce(m.reviewed,0)=0 and coalesce(m.ignore,0)=0
    and c.status in ('unkategorisiert','ki-vorschlag','branche-osm')"""


def uebersicht():
    """Monatssummen je Einnahme/Konsum/Sparen und Konsum je Kategorie, dazu der
    Durchschnitt der letzten zwoelf vollstaendigen Monate."""
    con = db.connect()
    von, bis = db.period_bounds()
    rows = con.execute("""select c.eff_monat, t.flow, c.category, sum(t.betrag), count(*)
        from transactions t join tx_category c on c.tx_id=t.id
        where c.eff_monat is not null and c.status<>'ignoriert' and (?='' or c.eff_monat >= ?)
        group by c.eff_monat, t.flow, c.category""", (von, von)).fetchall()
    offen = con.execute(f"select count(*) {_BASIS} where {_OFFEN_SQL}").fetchone()[0]
    letzte = con.execute("select max(datum) from transactions").fetchone()[0] or ""
    con.close()

    monate = defaultdict(lambda: {"ein": 0.0, "konsum": 0.0, "sparen": 0.0, "n": 0,
                                  "kat": defaultdict(float)})
    for ym, flow, cat, summe, n in rows:
        bt = btyp(cat, flow)
        if not bt:
            continue
        mo = monate[ym]
        mo["n"] += n
        if bt == "Einnahme":
            mo["ein"] += summe
        elif bt == "Sparen":
            mo["sparen"] += -summe
        else:
            mo["konsum"] += -summe
            mo["kat"][cat] += -summe

    # Durchschnitt: die letzten 12 vollen Monate im eingestellten Zeitraum.
    voll = sorted(ym for ym in monate if ym <= bis)[-12:]
    def schnitt(f):
        return round(sum(f(monate[ym]) for ym in voll) / len(voll), 2) if voll else 0
    kat_schnitt = defaultdict(float)
    for ym in voll:
        for k, v in monate[ym]["kat"].items():
            kat_schnitt[k] += v / len(voll)

    aus = []
    for ym in sorted(monate):
        mo = monate[ym]
        aus.append({"ym": ym, "ein": round(mo["ein"], 2), "konsum": round(mo["konsum"], 2),
                    "sparen": round(mo["sparen"], 2), "n": mo["n"], "voll": ym <= bis,
                    "kat": {k: round(v, 2) for k, v in mo["kat"].items() if abs(v) >= 0.005}})
    return {"monate": aus, "bis": bis, "von": von, "offen": offen, "letzte": letzte,
            "schnitt": {"monate": voll, "ein": schnitt(lambda m: m["ein"]),
                        "konsum": schnitt(lambda m: m["konsum"]),
                        "sparen": schnitt(lambda m: m["sparen"]),
                        "kat": {k: round(v, 2) for k, v in kat_schnitt.items()}},
            "stand": datetime.datetime.now().isoformat(timespec="minutes")}


def buchungen(monat=None, kat=None, q=None, offen=False, limit=300):
    """Buchungen nach Monat, Kategorie, Suchtext oder als Pruefliste, neueste zuerst."""
    where, params = [], []
    if monat:
        where.append("c.eff_monat=?"); params.append(monat)
    if kat:
        where.append("c.category=?"); params.append(kat)
    if q:
        like = "%" + q.lower() + "%"
        where.append("""(lower(coalesce(e.haendler_norm,t.gegenpartei,'')) like ?
            or lower(coalesce(t.verwendungszweck,'')) like ? or lower(coalesce(x.produkt,'')) like ?
            or lower(coalesce(m.note,'')) like ? or lower(c.category) like ?)""")
        params += [like] * 5
    if offen:
        where.append(_OFFEN_SQL)
    sql = f"select {_SPALTEN} {_BASIS}"
    if where:
        sql += " where " + " and ".join(where)
    sql += " order by t.datum desc, t.id limit ?"
    params.append(int(limit))
    con = db.connect()
    rows = [_buchung(r) for r in con.execute(sql, params)]
    con.close()
    return rows


def buchung(tid):
    con = db.connect()
    r = con.execute(f"select {_SPALTEN} {_BASIS} where t.id=?", (tid,)).fetchone()
    con.close()
    return _buchung(r) if r else None


def kategorien():
    import app
    return app.meta()["cats"]


def bearbeiten(p):
    """Nur die Felder, die das Handy aendern darf, an die Editor-Logik durchreichen."""
    import app
    erlaubt = {"category", "note", "reviewed", "ignore"}
    patch = {k: v for k, v in p.items() if k in erlaubt}
    tid = p.get("tx_id")
    if not tid or not patch:
        return {"fehler": "nichts zu speichern"}
    if "category" in patch and patch["category"] not in kategorien():
        return {"fehler": "unbekannte Kategorie"}
    app.save_edit(dict(patch, tx_id=tid, scope="tx", src="handy"))
    return {"row": buchung(tid)}


def vertraege():
    import app
    aus = []
    for c in app.contracts_rows():
        aus.append({k: c[k] for k in ("id", "name", "kategorie", "rhythmus", "betrag", "monatlich",
                                      "jaehrlich", "richtung", "status", "aktiv", "letzte",
                                      "naechste", "zweck", "anzahl")})
    return aus


def vermoegen():
    import app
    v = app.vermoegen_daten()
    if "fehler" in v:
        return v
    zeilen = [{k: z.get(k) for k in ("gruppe", "name", "a_min", "a_max", "guete", "stand", "anteil_text")}
              for z in v.get("zeilen", [])]
    return {"stichtag": v.get("stichtag"), "summen": v.get("summen"), "zeilen": zeilen,
            "depot": v.get("depot", []), "nicht_enthalten": v.get("nicht_enthalten", ""),
            "sicht": v.get("sicht", "")}

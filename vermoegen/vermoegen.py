#!/usr/bin/env python3
"""Vermoegensansicht: Snapshot aus Konto-CSVs, Depot-Export und gepflegten Positionen.

Bewusst getrennt von der Ausgaben-Pipeline:
- liest NUR Salden/Bestaende, nie Umsaetze -> keine Doppelzaehlung, keine Aenderung
  an transactions/parse_konten/Systemgrenze.
- die laufende Statistik bleibt unberuehrt.

Aufruf:  python vermoegen.py      (erzeugt vermoegen.html neben diesem Skript)
"""
import csv, json, os, re, sys, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.dirname(HERE)                      # ...\finanzen
sys.path.insert(0, os.path.join(BASE, "scripts"))
import db                                          # eine Wahrheitsquelle fuer Pfade

STEUER = db.STEUER_DIR                             # ...\steuer\2025
# Relativ zum PROJEKTORDNER (db.BASE), nicht zur Lage dieser Datei: sonst liest eine
# Demo-Instanz mit eigenem FINANZEN_BASE die Positionen des echten Haushalts.
CFG    = os.path.join(db.BASE, "vermoegen", "positionen.json")
OUT    = os.path.join(HERE, "vermoegen.html")


# ---- Helfer ---------------------------------------------------------------

def read_text(path):
    """Bank-Exporte kommen mal als UTF-8, mal als Windows-1252."""
    with open(path, "rb") as f:
        raw = f.read()
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", "replace")


def num(s, nd=2):
    """'4.211,02 EUR' / '350,655' / '-5000,00' -> float.
    nd hochsetzen, wo Nachkommastellen zaehlen (Stueckzahlen aus Sparplaenen)."""
    s = (s or "").strip().strip('"')
    s = s.replace("€", "").replace("EUR", "").replace("\xa0", "").replace(" ", "")
    if not s:
        return None
    s = s.replace(".", "").replace(",", ".")
    try:
        return round(float(s), nd)
    except ValueError:
        return None


def iso(s):
    """'29.07.2026' / '29.07.26' -> '2026-07-29'."""
    m = re.match(r"(\d{2})\.(\d{2})\.(\d{2,4})", (s or "").strip().strip('"'))
    if not m:
        return ""
    d, mo, y = m.groups()
    if len(y) == 2:
        y = "20" + y
    return f"{y}-{mo}-{d}"


def resolve(rel):
    """Pfad aus positionen.json aufloesen: 'konten/...' liegt unter STEUER,
    'vermoegen/...' unter dem Projektordner."""
    rel = rel.replace("/", os.sep)
    if rel.startswith("konten" + os.sep):
        return os.path.join(STEUER, rel)
    if rel.startswith("vermoegen" + os.sep):
        return os.path.join(BASE, rel)
    return os.path.join(HERE, rel)


def eur(x, cent=False):
    """Deutsche Zahlformatierung ohne locale."""
    if x is None:
        return "–"
    s = f"{abs(x):,.2f}" if cent else f"{abs(round(x)):,.0f}"
    s = s.replace(",", "·").replace(".", ",").replace("·", ".")
    return ("-" if x < 0 else "") + s


def stk(x):
    """Stueckzahlen ungerundet zeigen (Bruchstuecke aus Sparplaenen)."""
    s = f"{x:,.3f}".rstrip("0").rstrip(".")
    return s.replace(",", "·").replace(".", ",").replace("·", ".")


# ---- Quellen lesen --------------------------------------------------------

def saldo_dkb(path):
    """DKB-Export traegt den Kontostand im Kopf: '"Kontostand vom 29.07.2026:";"4.211,02 EUR"'."""
    for ln in read_text(path).splitlines()[:12]:
        if "Kontostand" in ln:
            teile = next(csv.reader([ln], delimiter=";"))
            datum = iso(re.search(r"\d{2}\.\d{2}\.\d{4}", teile[0]).group(0)) if len(teile) else ""
            betrag = num(teile[1]) if len(teile) > 1 else None
            if betrag is not None:
                return datum, betrag
    raise ValueError(f"Kein Kontostand im Kopf gefunden: {os.path.basename(path)}")


def saldo_gls(path):
    """GLS-Export fuehrt 'Saldo nach Buchung' je Zeile -> juengste Buchung gewinnt."""
    zeilen = list(csv.reader(read_text(path).splitlines(), delimiter=";"))
    kopf = zeilen[0]
    i_tag = kopf.index("Buchungstag")
    i_saldo = next(k for k, n in enumerate(kopf) if n.startswith("Saldo"))
    best = None
    for r in zeilen[1:]:
        if len(r) <= i_saldo:
            continue
        d, s = iso(r[i_tag]), num(r[i_saldo])
        if d and s is not None and (best is None or d > best[0]):
            best = (d, s)      # Export ist neueste-zuerst; > haelt den juengsten Stand
    if best is None:
        raise ValueError(f"Kein Saldo gefunden: {os.path.basename(path)}")
    return best


def depot_lesen(path):
    """Depot-Export -> Positionen mit Kurswert. Summe = Stueckzahl x Bewertungskurs."""
    zeilen = list(csv.reader(read_text(path).splitlines(), delimiter=";"))
    kopf = zeilen[0]
    idx = {n.strip(): k for k, n in enumerate(kopf)}
    pos, datum = [], ""
    for r in zeilen[1:]:
        if len(r) < len(kopf) or not r[idx["ISIN"]].strip():
            continue
        stueck = num(r[idx["Stückzahl"]], 6)
        kurs = num(r[idx["Bewertungskurs"]])
        einstieg = num(r[idx["Einstiegskurs"]])
        if stueck is None or kurs is None:
            continue
        datum = datum or iso(r[idx["Datum der Erstellung"]])
        pos.append({
            "name": r[idx["Wertpapierbezeichnung"]].strip(),
            "isin": r[idx["ISIN"]].strip(),
            "stueck": stueck,
            "kurs": kurs,
            "wert": round(stueck * kurs, 2),
            "gv": round(stueck * (kurs - einstieg), 2) if einstieg else None,
            "klasse": r[idx["Assetklasse"]].strip() if "Assetklasse" in idx else "",
        })
    return datum, pos


# ---- Rechnen --------------------------------------------------------------

def monate(von, bis):
    """Anzahl Monatsraten von 'YYYY-MM' bis 'YYYY-MM' einschliesslich."""
    y1, m1 = int(von[:4]), int(von[5:7])
    y2, m2 = int(bis[:4]), int(bis[5:7])
    return (y2 - y1) * 12 + (m2 - m1) + 1


def restschuld(d, stichtag):
    """Annuitaetendarlehen, exakt: R_n = (R0 - A/i)(1+i)^n + A/i."""
    i = d["zins_nominal"] / 12.0
    n = max(0, monate(d["erste_rate"], stichtag[:7]))
    if n == 0:
        return d["betrag"], 0
    r = (d["betrag"] - d["rate"] / i) * (1 + i) ** n + d["rate"] / i
    return max(0.0, round(r, 2)), n


def immo_wert(im):
    """-> (min, max) Marktwert des GESAMTEN Objekts, vor Anteil."""
    if im["methode"] == "vergleichswert_index":
        w = im["anker_wert"] * im["index_bis"] / im["index_von"]
        s = im.get("spanne_pct", 0.05)
        return w * (1 - s), w * (1 + s)
    if im["methode"] == "vergleichswert_qm":
        basis = im["wohnflaeche"] * im["qm_preis"]
        return basis * im["faktor_min"], basis * im["faktor_max"]
    raise ValueError("Unbekannte Methode: " + im["methode"])


def bilanz(cfg):
    stichtag = cfg["stichtag"]
    zeilen, quellen = [], []

    for k in cfg["konten"]:
        p = resolve(k["datei"])
        datum, betrag = (saldo_dkb if k["format"] == "dkb" else saldo_gls)(p)
        zeilen.append({"gruppe": "anlagen", "name": k["name"], "detail": k["iban"],
                       "min": betrag, "max": betrag, "anteil": 1.0,
                       "guete": "exakt", "stand": datum})
        quellen.append(os.path.basename(p))

    depot_pos = []
    for dp in cfg["depots"]:
        p = resolve(dp["datei"])
        datum, pos = depot_lesen(p)
        summe = round(sum(x["wert"] for x in pos), 2)
        depot_pos = pos
        zeilen.append({"gruppe": "anlagen", "name": dp["name"],
                       "detail": f"{len(pos)} Positionen", "min": summe, "max": summe,
                       "anteil": 1.0, "guete": "exakt", "stand": datum})
        quellen.append(os.path.basename(p))

    for im in cfg["immobilien"]:
        lo, hi = immo_wert(im)
        zeilen.append({"gruppe": "immobilien", "name": im["name"], "detail": im["detail"],
                       "min": lo, "max": hi, "anteil": im["anteil"],
                       "anteil_text": im.get("anteil_text", ""),
                       "guete": im["guete"], "stand": stichtag, "id": im["id"]})

    for d in cfg["darlehen"]:
        r, n = restschuld(d, stichtag)
        zeilen.append({"gruppe": "schulden", "name": d["name"],
                       "detail": f"{d['rate']:.0f} €/Mon · {d['zins_nominal']*100:.1f} % fest bis "
                                 f"{d['zinsbindung_bis'][8:10]}.{d['zinsbindung_bis'][5:7]}.{d['zinsbindung_bis'][:4]}"
                                 f" · {n} Raten gezahlt",
                       "min": -r, "max": -r, "anteil": d.get("anteil", 1.0),
                       "guete": "exakt", "stand": stichtag, "id": d["id"]})

    for z in zeilen:
        z["a_min"] = z["min"] * z["anteil"]
        z["a_max"] = z["max"] * z["anteil"]
    return zeilen, depot_pos, quellen


def methodik(cfg):
    """Herleitung je Bewertung als strukturierter Text (fuer beide Renderer)."""
    out = []
    for im in cfg["immobilien"]:
        lo, hi = immo_wert(im)
        if im["methode"] == "vergleichswert_index":
            p = [f'Anker {eur(im["anker_wert"])} € ({im["anker_datum"]}, {im["anker_quelle"]}), '
                 f'fortgeschrieben mit {im["index_name"]}: {im["index_von"]} '
                 f'({im["index_von_stand"]}) → {im["index_bis"]} ({im["index_bis_stand"]}) = '
                 f'{(im["index_bis"]/im["index_von"]-1)*100:+.1f} %.']
            note = im.get("gegenprobe", "")
        else:
            p = [f'{im["wohnflaeche"]} m² × {eur(im["qm_preis"])} €/m² × '
                 f'{im["faktor_min"]:.2f}–{im["faktor_max"]:.2f}. Quelle: {im["qm_preis_quelle"]}.']
            note = im.get("faktor_begruendung", "")
        out.append({"titel": im["name"], "text": p, "note": note,
                    "ergebnis": f'Marktwert gesamt {eur(lo)} – {eur(hi)} € · Anteil '
                                f'{im["anteil_text"]} → {eur(lo*im["anteil"])} – '
                                f'{eur(hi*im["anteil"])} €'})
    for d in cfg["darlehen"]:
        r, n = restschuld(d, cfg["stichtag"])
        out.append({"titel": d["name"],
                    "text": [f'Annuität aus dem Kreditvertrag: {eur(d["betrag"])} € zu '
                             f'{d["zins_nominal"]*100:.1f} % nominal, {d["rate"]:.0f} €/Monat '
                             f'ab {d["erste_rate"]}. Nach {n} Raten verbleiben {eur(r)} €.'],
                    "note": d["verifikation"], "ergebnis": ""})
    return out


def daten():
    """Ein Aufruf -> alles, was Seite und App brauchen. JSON-tauglich."""
    with open(CFG, encoding="utf-8") as f:
        cfg = json.load(f)
    zeilen, depot_pos, quellen = bilanz(cfg)
    g = lambda gr, k: sum(z[k] for z in zeilen if z["gruppe"] == gr)
    summen = {
        "anlagen":   round(g("anlagen", "a_min"), 2),
        "immo_min":  round(g("immobilien", "a_min"), 2),
        "immo_max":  round(g("immobilien", "a_max"), 2),
        "schulden":  round(g("schulden", "a_min"), 2),
        "netto_min": round(sum(z["a_min"] for z in zeilen), 2),
        "netto_max": round(sum(z["a_max"] for z in zeilen), 2),
    }
    # Startwerte fuer die Vorsorge-Simulation (Mittelwerte, uebernehmbar)
    tilgung = sum(d["rate"] for d in cfg["darlehen"])
    vorsorge = {
        "etf_start":   round(sum(z["a_min"] for z in zeilen
                                 if z["gruppe"] == "anlagen" and "Depot" in z["name"])),
        "immo_wert":   round((summen["immo_min"] + summen["immo_max"]) / 2),
        "immo_schuld": round(-summen["schulden"]),
        "immo_tilgung": round(tilgung),
    }
    return {"stichtag": cfg["stichtag"], "sicht": cfg["sicht"],
            "sicht_hinweis": cfg.get("sicht_hinweis", ""),
            # Freitexte aus positionen.json statt fest im Code: was die Spannbreite treibt
            # und was bewusst nicht mitgezaehlt wird, ist von Haushalt zu Haushalt anders.
            "spanne_hinweis": cfg.get("spanne_hinweis", ""),
            "nicht_enthalten": cfg.get("nicht_enthalten", ""),
            "zeilen": zeilen, "depot": depot_pos, "summen": summen,
            "methodik": methodik(cfg), "quellen": sorted(set(quellen)),
            "vorsorge": vorsorge}


# ---- Ausgabe --------------------------------------------------------------

GUETE_TEXT = {
    "exakt": "exakt — Kontostand bzw. berechnet",
    "gut":   "gut — realer Ankerpreis, indexiert und gegengeprüft",
    "grob":  "grob — Spanne aus Vergleichsverkäufen",
}


def html(cfg, zeilen, depot_pos, quellen):
    anlagen = [z for z in zeilen if z["gruppe"] == "anlagen"]
    immos   = [z for z in zeilen if z["gruppe"] == "immobilien"]
    schuld  = [z for z in zeilen if z["gruppe"] == "schulden"]

    s_anl = sum(z["a_min"] for z in anlagen)
    netto_min = sum(z["a_min"] for z in zeilen)
    netto_max = sum(z["a_max"] for z in zeilen)
    s_imm_min = sum(z["a_min"] for z in immos)
    s_imm_max = sum(z["a_max"] for z in immos)
    s_sch = sum(z["a_min"] for z in schuld)

    # Balkensegmente (Mittelwerte): Anlagen, je Immobilie netto nach zugeordnetem Darlehen
    seg = [{"label": "Anlagen & Konten", "wert": s_anl, "slot": 1}]
    for i, z in enumerate(immos):
        tilgung = sum(s["a_min"] for s in schuld if s.get("id") == z.get("id"))
        seg.append({"label": z["name"].split(",")[0],
                    "wert": (z["a_min"] + z["a_max"]) / 2 + tilgung,
                    "slot": 2 + i})
    gesamt_seg = sum(s["wert"] for s in seg)
    for s in seg:
        s["pct"] = s["wert"] / gesamt_seg * 100 if gesamt_seg else 0

    def zeile(z):
        wert = (eur(z["a_min"]) if abs(z["a_max"] - z["a_min"]) < 1
                else f"{eur(z['a_min'])} – {eur(z['a_max'])}")
        anteil = z.get("anteil_text") or ("" if z["anteil"] == 1.0 else f"{z['anteil']*100:.0f} %")
        neg = " neg" if z["a_min"] < 0 else ""
        return (f'<tr><td class="nm">{z["name"]}<span class="sub">{z["detail"]}</span></td>'
                f'<td class="an">{anteil}</td>'
                f'<td class="vl{neg}">{wert} €</td>'
                f'<td class="gt"><span class="badge b-{z["guete"]}">{z["guete"]}</span></td></tr>')

    segs_html = "".join(
        f'<div class="seg s{s["slot"]}" style="flex:{s["pct"]:.4f}"></div>' for s in seg)
    legend_html = "".join(
        f'<div class="lg"><span class="dot s{s["slot"]}"></span>'
        f'<span class="lgl">{s["label"]}</span>'
        f'<span class="lgv">{eur(s["wert"])} €</span>'
        f'<span class="lgp">{s["pct"]:.0f} %</span></div>' for s in seg)

    depot_html = "".join(
        f'<tr><td class="nm">{p["name"]}<span class="sub">{p["isin"]} · {p["klasse"]}</span></td>'
        f'<td class="an">{stk(p["stueck"])}</td>'
        f'<td class="vl">{eur(p["wert"])} €</td>'
        f'<td class="gt {"pos" if (p["gv"] or 0) >= 0 else "neg"}">'
        f'{"+" if (p["gv"] or 0) >= 0 else ""}{eur(p["gv"])} €</td></tr>'
        for p in depot_pos)

    methodik = []
    for im in cfg["immobilien"]:
        lo, hi = immo_wert(im)
        if im["methode"] == "vergleichswert_index":
            kern = (f'Anker {eur(im["anker_wert"])} € ({im["anker_datum"]}, {im["anker_quelle"]}), '
                    f'fortgeschrieben mit {im["index_name"]}: {im["index_von"]} ({im["index_von_stand"]}) '
                    f'→ {im["index_bis"]} ({im["index_bis_stand"]}) = '
                    f'{(im["index_bis"]/im["index_von"]-1)*100:+.1f} %.')
            extra = im.get("gegenprobe", "")
        else:
            kern = (f'{im["wohnflaeche"]} m² × {eur(im["qm_preis"])} €/m² '
                    f'× {im["faktor_min"]:.2f}–{im["faktor_max"]:.2f}. '
                    f'Quelle: {im["qm_preis_quelle"]}.')
            extra = im.get("faktor_begruendung", "")
        methodik.append(
            f'<div class="mk"><h3>{im["name"]}</h3>'
            f'<p>{kern}</p>{f"<p class=note>{extra}</p>" if extra else ""}'
            f'<p class="res">Marktwert gesamt {eur(lo)} – {eur(hi)} € '
            f'· Anteil {im["anteil_text"]} → <b>{eur(lo*im["anteil"])} – '
            f'{eur(hi*im["anteil"])} €</b></p></div>')
    for d in cfg["darlehen"]:
        r, n = restschuld(d, cfg["stichtag"])
        methodik.append(
            f'<div class="mk"><h3>{d["name"]}</h3>'
            f'<p>Annuität aus dem Kreditvertrag: {eur(d["betrag"])} € zu '
            f'{d["zins_nominal"]*100:.1f} % nominal, {d["rate"]:.0f} €/Monat ab {d["erste_rate"]}. '
            f'Nach {n} Raten verbleiben <b>{eur(r)} €</b>.</p>'
            f'<p class="note">{d["verifikation"]}</p></div>')

    stand = cfg["stichtag"]
    stand_de = f"{stand[8:10]}.{stand[5:7]}.{stand[:4]}"
    # Optionale Freitexte aus positionen.json. Leer = Satzteil faellt weg, statt eine
    # halbe Zeile ("Nicht enthalten:") ohne Inhalt stehen zu lassen.
    _sp = (cfg.get("spanne_hinweis") or "").strip()
    spanne_zusatz = f", {_sp}" if _sp else ""
    _ne = (cfg.get("nicht_enthalten") or "").strip()
    nicht_enthalten_zusatz = f"<br>\n  Nicht enthalten: {_ne}" if _ne else ""
    return f"""<!doctype html>
<html lang="de"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Vermögen · Stand {stand_de}</title>
<style>
:root{{
  color-scheme:light;
  --plane:#f9f9f7; --surface:#fcfcfb; --ink:#0b0b0b; --ink2:#52514e; --muted:#898781;
  --grid:#e1e0d9; --ring:rgba(11,11,11,.10); --good:#006300; --bad:#d03b3b;
  --s1:#2a78d6; --s2:#eb6834; --s3:#1baf7a;
}}
@media (prefers-color-scheme:dark){{ :root:where(:not([data-theme=light])){{
  color-scheme:dark;
  --plane:#0d0d0d; --surface:#1a1a19; --ink:#fff; --ink2:#c3c2b7; --muted:#898781;
  --grid:#2c2c2a; --ring:rgba(255,255,255,.10); --good:#0ca30c; --bad:#e66767;
  --s1:#3987e5; --s2:#d95926; --s3:#199e70;
}}}}
:root[data-theme=dark]{{
  color-scheme:dark;
  --plane:#0d0d0d; --surface:#1a1a19; --ink:#fff; --ink2:#c3c2b7; --muted:#898781;
  --grid:#2c2c2a; --ring:rgba(255,255,255,.10); --good:#0ca30c; --bad:#e66767;
  --s1:#3987e5; --s2:#d95926; --s3:#199e70;
}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--plane);color:var(--ink);
  font:15px/1.55 system-ui,-apple-system,"Segoe UI",sans-serif;
  -webkit-font-smoothing:antialiased}}
.wrap{{max-width:1080px;margin:0 auto;padding:40px 24px 72px}}
header{{margin-bottom:32px}}
h1{{font-size:26px;font-weight:650;margin:0 0 4px;letter-spacing:-.01em}}
.sup{{color:var(--ink2);font-size:14px}}
.sup b{{color:var(--ink);font-weight:600}}
.card{{background:var(--surface);border:1px solid var(--ring);border-radius:14px;
  padding:26px 28px;margin-bottom:20px}}
.hero .lbl{{color:var(--ink2);font-size:13px;text-transform:uppercase;
  letter-spacing:.07em;font-weight:600}}
.hero .big{{font-size:44px;font-weight:650;letter-spacing:-.02em;margin:6px 0 2px;
  line-height:1.1}}
.hero .mid{{color:var(--ink2);font-size:14px}}
.tiles{{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));
  gap:14px;margin-top:24px}}
.tile{{border:1px solid var(--ring);border-radius:11px;padding:15px 17px}}
.tile .t{{color:var(--ink2);font-size:12.5px;font-weight:600;margin-bottom:5px}}
.tile .v{{font-size:22px;font-weight:620;letter-spacing:-.01em}}
.tile .v.neg{{color:var(--bad)}}
.tile .s{{color:var(--muted);font-size:12px;margin-top:3px}}
h2{{font-size:16px;font-weight:640;margin:0 0 16px;letter-spacing:-.005em}}
.bar{{display:flex;height:34px;border-radius:7px;overflow:hidden;gap:2px;
  background:var(--surface)}}
.seg{{min-width:3px}}
.s1{{background:var(--s1)}} .s2{{background:var(--s2)}} .s3{{background:var(--s3)}}
.legend{{margin-top:16px;display:grid;gap:9px}}
.lg{{display:flex;align-items:center;gap:10px;font-size:14px}}
.dot{{width:11px;height:11px;border-radius:3px;flex:none}}
.lgl{{flex:1;color:var(--ink2)}}
.lgv{{font-weight:600;font-variant-numeric:tabular-nums}}
.lgp{{color:var(--muted);width:44px;text-align:right;font-variant-numeric:tabular-nums}}
table{{width:100%;border-collapse:collapse;font-variant-numeric:tabular-nums}}
th{{text-align:left;font-size:12px;font-weight:600;color:var(--muted);
  text-transform:uppercase;letter-spacing:.05em;padding:0 10px 9px 0;
  border-bottom:1px solid var(--grid)}}
th:nth-child(2),th:nth-child(3),th:nth-child(4){{text-align:right;padding-right:0}}
td{{padding:12px 10px 12px 0;border-bottom:1px solid var(--grid);vertical-align:top}}
tr:last-child td{{border-bottom:none}}
.nm{{font-weight:530}}
.sub{{display:block;color:var(--muted);font-size:12.5px;font-weight:400;
  margin-top:2px;max-width:52ch}}
.an{{text-align:right;color:var(--ink2);font-size:13px;white-space:nowrap;padding-right:0}}
.vl{{text-align:right;font-weight:600;white-space:nowrap;padding-right:0}}
.vl.neg{{color:var(--bad)}}
.gt{{text-align:right;white-space:nowrap;padding-right:0}}
.gt.pos{{color:var(--good);font-weight:600}} .gt.neg{{color:var(--bad);font-weight:600}}
.badge{{font-size:11.5px;font-weight:600;padding:3px 9px;border-radius:20px;
  border:1px solid var(--ring);color:var(--ink2)}}
.grp{{font-size:12px;font-weight:650;color:var(--muted);text-transform:uppercase;
  letter-spacing:.06em;padding:22px 0 8px}}
.sumrow td{{border-top:2px solid var(--grid);border-bottom:none;padding-top:14px;
  font-weight:650;font-size:17px}}
.mk{{padding:16px 0;border-bottom:1px solid var(--grid)}}
.mk:last-child{{border-bottom:none;padding-bottom:0}}
.mk h3{{font-size:14px;font-weight:620;margin:0 0 6px}}
.mk p{{margin:0 0 6px;color:var(--ink2);font-size:13.5px}}
.mk .note{{color:var(--muted);font-size:13px}}
.mk .res{{color:var(--ink);font-size:13.5px}}
footer{{color:var(--muted);font-size:12.5px;margin-top:26px;line-height:1.7}}
@media (max-width:640px){{ .hero .big{{font-size:32px}} .sub{{max-width:none}} }}
</style></head><body>
<div class="wrap">
<header>
  <h1>Vermögen</h1>
  <div class="sup"><b>{cfg["sicht"]}</b> · Stand {stand_de}</div>
</header>

<div class="card hero">
  <div class="lbl">Nettovermögen</div>
  <div class="big">{eur(netto_min)} – {eur(netto_max)} €</div>
  <div class="mid">Mittelwert {eur((netto_min+netto_max)/2)} € · Spannbreite
    {eur(netto_max-netto_min)} €{spanne_zusatz}</div>
  <div class="tiles">
    <div class="tile"><div class="t">Anlagen &amp; Konten</div>
      <div class="v">{eur(s_anl)} €</div>
      <div class="s">{s_anl/((netto_min+netto_max)/2)*100:.0f} % des Vermögens</div></div>
    <div class="tile"><div class="t">Immobilien (Marktwert)</div>
      <div class="v">{eur(s_imm_min)} – {eur(s_imm_max)} €</div>
      <div class="s">Anteile bereits berücksichtigt</div></div>
    <div class="tile"><div class="t">Verbindlichkeiten</div>
      <div class="v neg">{eur(s_sch)} €</div>
      <div class="s">1,8 % fest bis 04/2032</div></div>
  </div>
</div>

<div class="card">
  <h2>Zusammensetzung</h2>
  <div class="bar">{segs_html}</div>
  <div class="legend">{legend_html}</div>
</div>

<div class="card">
  <h2>Bilanz</h2>
  <table>
    <thead><tr><th>Position</th><th>Anteil</th><th>Wert bei uns</th><th>Güte</th></tr></thead>
    <tbody>
      <tr><td class="grp" colspan="4">Anlagen &amp; Konten</td></tr>
      {"".join(zeile(z) for z in anlagen)}
      <tr><td class="grp" colspan="4">Immobilien</td></tr>
      {"".join(zeile(z) for z in immos)}
      <tr><td class="grp" colspan="4">Verbindlichkeiten</td></tr>
      {"".join(zeile(z) for z in schuld)}
      <tr class="sumrow"><td>Nettovermögen</td><td></td>
        <td class="vl">{eur(netto_min)} – {eur(netto_max)} €</td><td></td></tr>
    </tbody>
  </table>
</div>

<div class="card">
  <h2>Depot im Detail</h2>
  <table>
    <thead><tr><th>Position</th><th>Stück</th><th>Kurswert</th><th>G/V</th></tr></thead>
    <tbody>{depot_html}</tbody>
  </table>
</div>

<div class="card">
  <h2>Wie die Immobilienwerte zustande kommen</h2>
  {"".join(methodik)}
</div>

<footer>
  Quellen: {", ".join(sorted(set(quellen)))}.<br>
  Güte: {" · ".join(GUETE_TEXT[k] for k in ("exakt","gut","grob"))}.{nicht_enthalten_zusatz}
</footer>
</div></body></html>"""


def main():
    with open(CFG, encoding="utf-8") as f:
        cfg = json.load(f)
    zeilen, depot_pos, quellen = bilanz(cfg)
    open(OUT, "w", encoding="utf-8").write(html(cfg, zeilen, depot_pos, quellen))

    lo = sum(z["a_min"] for z in zeilen)
    hi = sum(z["a_max"] for z in zeilen)
    print(f"Stichtag {cfg['stichtag']} — {cfg['sicht']}\n")
    for z in zeilen:
        w = eur(z["a_min"]) if abs(z["a_max"] - z["a_min"]) < 1 \
            else f"{eur(z['a_min'])} - {eur(z['a_max'])}"
        print(f"  {z['name']:<42} {w:>22} EUR   [{z['guete']}]")
    print(f"\n  {'NETTOVERMOEGEN':<42} {eur(lo)+' - '+eur(hi):>22} EUR")
    print(f"\n-> {OUT}")


if __name__ == "__main__":
    main()

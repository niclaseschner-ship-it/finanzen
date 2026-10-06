#!/usr/bin/env python3
"""Baut die Online-Demo: die echten Seiten der App mit dem erfundenen Demo-Haushalt.

    python demo/bauen.py

Ergebnis liegt in diesem Ordner und läuft ohne Server — per Doppelklick auf index.html
oder über GitHub Pages. Nichts davon ist nachgebaut: die Seiten kommen aus
scripts/seiten/ (samt Kopfleiste und Statistik, genau wie app.py sie ausliefert), die
Daten aus den Funktionen, die sonst hinter /api/ stehen. demo.js beantwortet im Browser
die Anfragen der Seiten aus daten.js.

Nach jeder Änderung an Seiten oder Daten-Funktionen neu bauen und mit committen.
"""
import json, os, re, shutil, subprocess, sys

HIER = os.path.dirname(os.path.abspath(__file__))
WURZEL = os.path.dirname(HIER)
DEMO_DATEN = os.path.join(WURZEL, "beispieldaten", "demo")
REPO_URL = "https://github.com/niclaseschner-ship-it/finanzen"

# Immer gegen den Demo-Haushalt, nie gegen eigene Daten — auch wenn im Projektordner
# welche liegen. Und nie eine zentrale Mail-Datenbank einblenden.
os.environ["FINANZEN_BASE"] = DEMO_DATEN
os.environ["FINANZEN_MAILDB"] = ""
for k in ("FINANZEN_AUTH", "FINANZEN_HOST", "FINANZEN_FUNNEL_HOST", "FINANZEN_OEFFENTLICHER_HOST"):
    os.environ.pop(k, None)

if not os.path.exists(os.path.join(DEMO_DATEN, "finanzen.db")):
    print("Demo-Haushalt fehlt — wird erzeugt ...")
    subprocess.run([sys.executable, os.path.join(WURZEL, "beispieldaten", "erzeugen.py")], check=True)

sys.path.insert(0, os.path.join(WURZEL, "scripts"))
import db, app, handy, frontend  # noqa: E402  (erst nach den Umgebungsvariablen)

SEITEN = {  # Datei in der Demo -> (HTML, Schlüssel der Kopfleiste)
    "start.html": app.START_HTML,
    "editor.html": app.APP_HTML,
    "vertraege.html": app.VTG_HTML,
    "reisen.html": app.REISEN_HTML,
    "vermoegen.html": app.VERMOEGEN_HTML,
    "vorsorge.html": app.VORSORGE_HTML,
}
LINKS = [  # Verweise der App -> Dateien der Demo (ohne Server gibt es keine Weiterleitung)
    (r'href="\./\?ansicht=handy"', 'href="handy.html"'),
    (r'href="\./\?ansicht=desktop"', 'href="start.html"'),
    (r'href="\./"', 'href="start.html"'),
    (r'href="(editor|vertraege|reisen|vermoegen|vorsorge)"', r'href="\1.html"'),
]
EINBINDEN = '<script src="daten.js"></script><script src="demo.js"></script>'
HINWEIS = ('<a class=demo-hinweis href="%s" title="Erfundener Haushalt. Änderungen bleiben nur in '
           'diesem Browser-Tab. Zum Projekt auf GitHub.">Demo · zum Projekt</a>' % REPO_URL)


def seite(html):
    html = app._FNAV.sub(lambda m: app.kopfleiste(m.group(1)), html)
    html = re.sub(r'<span class=demo-hinweis[^>]*>Beispieldaten</span>', HINWEIS, html)
    for muster, ersatz in LINKS:
        html = re.sub(muster, ersatz, html)
    # Vor allen anderen Skripten, damit fetch schon umgelenkt ist
    return re.sub(r"(<head[^>]*>)", r"\1" + EINBINDEN, html, count=1)


def schreiben(name, inhalt):
    modus = "wb" if isinstance(inhalt, bytes) else "w"
    with open(os.path.join(HIER, name), modus, **({} if modus == "wb" else {"encoding": "utf-8"})) as f:
        f.write(inhalt)


def daten():
    con = db.connect()
    rows = app.get_rows(con)
    vertraege = app.contracts_rows()
    trips = app.trips_rows()
    d = {
        "uebersicht": handy.uebersicht(),
        "alle": handy.buchungen(limit=10 ** 6),
        "handy_vertraege": handy.vertraege(),
        "handy_vermoegen": handy.vermoegen(),
        "vertrag": {c["id"]: app.contract_tx(c["id"]) for c in vertraege},
        "rows": rows,
        "rows_reise": {t["id"]: app.get_rows(con, trip=t["id"]) for t in trips},
        "rows_vertrag": {c["id"]: app.get_rows(con, contract=c["id"]) for c in vertraege},
        "meta": app.meta(),
        "contracts": vertraege,
        "trips": trips,
        "vermoegen": app.vermoegen_daten(),
        "vorsorge": app.vorsorge_load(),
        "ist_werte": app.ist_werte(),
        "mail": {},
    }
    con.close()
    for r in rows:   # nur Buchungen mit Beleg oder Händler-Mails, der Rest ist "nichts gefunden"
        m = app.mail_for_tx(r["id"])
        if m.get("found") or m.get("related"):
            d["mail"][r["id"]] = m
    return d


def main():
    # Alte Fassung (nachgebaute Einzelseite) und alte Bauergebnisse weg
    for alt in os.listdir(HIER):
        if alt.endswith((".html", ".png", ".webmanifest")) or alt in (
                "daten.js", "shared.js", "stil.css", "chart.min.js", "app-installieren.js"):
            os.remove(os.path.join(HIER, alt))

    for name, html in SEITEN.items():
        schreiben(name, seite(html))
    frontend.run()                                       # Statistik wie in der App
    with open(os.path.join(db.OUTPUT_DIR, "statistik.html"), encoding="utf-8") as f:
        schreiben("statistik.html", seite(f.read()))
    # Ohne Server kein Service Worker (Offline-Polster); die Anmeldung liefe ins Leere.
    handy_html = re.sub(r"\nif \('serviceWorker' in navigator\)[^\n]*", "", handy.datei("index.html").decode("utf-8"))
    schreiben("handy.html", seite(handy_html))

    for name in ("shared.js", "stil.css", "chart.min.js"):
        shutil.copy(os.path.join(app.SEITEN_DIR, name), os.path.join(HIER, name))
    for name in ("app-installieren.js", "icon-192.png", "icon-512.png", "icon-maskable-512.png",
                 "apple-touch-icon.png"):
        shutil.copy(os.path.join(handy.HANDY_DIR, name), os.path.join(HIER, name))
    manifest = json.loads(handy.datei("manifest.webmanifest"))
    manifest.update({"start_url": "handy.html", "name": "Finanzen (Demo)", "id": "/finanzen-demo"})
    schreiben("manifest.webmanifest", json.dumps(manifest, ensure_ascii=False, indent=2))

    # Einstieg: Gerät erkennen wie /finanzen/ in der App
    schreiben("index.html", """<!doctype html><html lang=de><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1"><title>Finanzen · Demo</title>
<script>location.replace((/Mobi|iPhone|iPod|Android.+Mobile/i.test(navigator.userAgent)?'handy.html':'start.html')+location.hash)</script>
<p>Weiter zur <a href="start.html">Demo am Rechner</a> oder zur <a href="handy.html">Handy-Ansicht</a>.</p></html>
""")
    d = daten()
    schreiben("daten.js", "/* Erzeugt von bauen.py aus dem erfundenen Demo-Haushalt. */\nwindow.DEMO_DATEN="
              + json.dumps(d, ensure_ascii=False, separators=(",", ":")) + ";\n")
    groesse = sum(os.path.getsize(os.path.join(HIER, f)) for f in os.listdir(HIER))
    print(f"Demo gebaut: {len(d['rows'])} Buchungen, {len(d['mail'])} mit Mails, "
          f"{len(os.listdir(HIER))} Dateien, {groesse // 1024} KB -> {HIER}")


if __name__ == "__main__":
    main()

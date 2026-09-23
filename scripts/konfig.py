"""Persönliche Konfiguration — alles, was von Haushalt zu Haushalt anders ist.

Vorher stand das im Quellcode verteilt (Kontenkarte in `ingest_transactions.py`,
Heimatregion in `rules.py`, Kategorien in `liste.py`, Namen in `build_context.py`).
Wer die App mit eigenen Daten nutzt, musste Python editieren. Jetzt steht alles in
**einer** Datei `konfig.json` im Projektordner.

Einrichten:  konfig.beispiel.json  ->  konfig.json  kopieren und ausfüllen.

Fehlt `konfig.json`, wird die **Beispieldatei** geladen und `IST_BEISPIEL` gesetzt:
Server und Tests laufen damit weiter (harmlos, es wird nur angezeigt), aber
`run_all.py` verweigert den Lauf — mit fremder Kontenkarte kategorisiert die
Pipeline sonst still falsch, und genau das soll nie passieren.
"""
import json, os, sys
import db

PFAD     = os.path.join(db.BASE, "konfig.json")
BEISPIEL = os.path.join(db.BASE, "konfig.beispiel.json")


class KonfigFehler(RuntimeError):
    """Konfiguration fehlt oder ist unbrauchbar — immer mit Hinweis, was zu tun ist."""


def _laden():
    """-> (daten, ist_beispiel). Lädt konfig.json, sonst die Beispieldatei."""
    for pfad, ist_beispiel in ((PFAD, False), (BEISPIEL, True)):
        if not os.path.exists(pfad):
            continue
        try:
            with open(pfad, encoding="utf-8") as f:
                daten = json.load(f)
        except json.JSONDecodeError as e:
            # Häufigster Fehler beim Ausfüllen von Hand: Komma zu viel/zu wenig.
            raise KonfigFehler(
                f"{os.path.basename(pfad)} ist kein gültiges JSON: {e}\n"
                f"Datei: {pfad}") from None
        if ist_beispiel:
            print(f"WARNUNG: keine konfig.json gefunden — Beispielkonfiguration geladen.\n"
                  f"         Zum Einrichten: {BEISPIEL}\n"
                  f"         kopieren nach: {PFAD}", file=sys.stderr)
        return daten, ist_beispiel
    raise KonfigFehler(
        f"Keine Konfiguration gefunden.\n"
        f"Erwartet: {PFAD}\n"
        f"Vorlage:  {BEISPIEL} (kopieren und ausfüllen)")


_D, IST_BEISPIEL = _laden()

# Auch eine unveränderte Kopie der Vorlage ist "die Beispielkonfiguration": wer
# `copy konfig.beispiel.json konfig.json` macht und nichts ausfüllt, hätte sonst eine
# Kontenkarte aus Platzhalter-IBANs — die Pipeline liefe durch und rechnete jede eigene
# Umbuchung als Ausgabe. Genau der stille Unsinn, den IST_BEISPIEL verhindern soll.
if not IST_BEISPIEL and os.path.exists(BEISPIEL):
    try:
        with open(BEISPIEL, encoding="utf-8") as _f:
            if json.load(_f) == _D:
                print("WARNUNG: konfig.json ist noch unverändert die Vorlage.", file=sys.stderr)
                IST_BEISPIEL = True
    except Exception:
        pass


def _teil(name, default=None):
    """Abschnitt lesen und den Typ pruefen.

    Ohne Typpruefung endet ein Vertipper nicht in einer verstaendlichen Meldung,
    sondern in einem rohen AttributeError beim IMPORT dieses Moduls — und dann startet
    auch `einrichten.py` nicht mehr, also genau das Werkzeug, mit dem man die Datei
    reparieren wuerde. Ein String statt einer Liste ist besonders tueckisch: Python
    iteriert ihn zeichenweise, aus "Lebensmittel" wird ['L','e','b',...]."""
    wert = _D.get(name)
    if wert is None:
        if default is None:
            raise KonfigFehler(f"Abschnitt '{name}' fehlt in {os.path.basename(PFAD)}.")
        return default
    if default is not None and not isinstance(wert, type(default)):
        erwartet = {list: "eine Liste [...]", dict: "ein Objekt {...}"}.get(
            type(default), type(default).__name__)
        raise KonfigFehler(
            f"'{name}' muss {erwartet} sein, ist aber {type(wert).__name__}.\n"
            f"Datei: {PFAD}")
    return wert


# ---- Haushalt --------------------------------------------------------------
_H = _teil("haushalt", {})
NAME = _H.get("name", "")
# Eigennamen (Familie, Vermieter, WG): verhindern, dass Privatmails als Beleg-Kontext
# an einer Buchung landen. Kleingeschrieben, weil überall lowercase verglichen wird.
EIGENE_NAMEN = [s.strip().lower() for s in _H.get("eigene_namen", []) if s.strip()]
# Heimatregion für die Reise-Erkennung: Einkauf in einem dieser Orte = "zuhause".
# Ohne das ist der Alltag eine Dauerreise.
HEIMAT_ORTE = [s.strip().lower() for s in _H.get("heimat_orte", []) if s.strip()]

# ---- Kategorien ------------------------------------------------------------
# Genau eine pro Buchung. Reihenfolge = Reihenfolge in den Auswahlfeldern.
KATEGORIEN = [s for s in _teil("kategorien", []) if s]

# Orte, die als Suchwort nichts unterscheiden, weil sie in eigenen Buchungen ständig
# vorkommen (Wohnort, Nachbarorte, Städte eigener Immobilien). Getrennt von
# HEIMAT_ORTE, weil das eine andere Frage ist: hier "taugt nicht als Suchbegriff",
# dort "zählt als zuhause". Ein Ort kann in beiden Listen stehen.
ORTE_OHNE_SUCHWERT = [s.strip().lower() for s in _H.get("orte_ohne_suchwert", []) if s.strip()]

# ---- Kategorie-Sonderfälle -------------------------------------------------
# Ergänzen die allgemeinen Listen im Code (rules.py), sie ersetzen sie nicht.
# Eigene Kategorien wie "Immobilie X" oder ein Nebengewerbe muss der Code nicht kennen.
KAT_IMMER_VERTRAG = [s for s in _teil("kategorien_immer_vertrag", []) if s]  # -> Label 'vertrag'
KAT_NICHT_REISE   = [s for s in _teil("kategorien_nicht_reise", []) if s]    # aus Reise-Erkennung raus
# Kein Konsum, sondern Vermögensumschichtung/Objektkosten: fliegt aus den Konsum-Auswertungen
# in scripts/extra/. Bewusst eine EIGENE Liste — "kein Konsum" ist eine andere Frage als
# "nie Reise" (eine Immobilie ist kein Reiseziel, taucht aber sehr wohl im Alltag auf).
KAT_KEIN_KONSUM   = [s for s in _teil("kategorien_kein_konsum", []) if s]

# Vollstaendige Ausschlussliste fuer JEDE Konsum-Auswertung: die fest eingebauten
# Nicht-Konsum-Kategorien plus die eigenen aus konfig.json. Stand bis 09/2026 wortgleich
# in extra/dashboard.py und extra/report.py — jetzt einmal hier, damit "Konsum" ueberall
# dasselbe heisst und eine neue Auswertung nicht versehentlich anders rechnet.
KAT_NICHT_KONSUM  = ("Sparen/Invest", "Kredit/Immobilie", "Camper",
                     "Umbuchung intern", "Einnahme") + tuple(KAT_KEIN_KONSUM)

# Eigene Zuordnung OSM-Branche -> Kategorie, ergaenzt/ueberschreibt die Vorgabe in
# branche.py. Damit bleiben persoenliche Eigenheiten (z.B. eine eigene Kategorie fuer
# Tierarztkosten) aus dem ausgelieferten Code.
BRANCHE_KATEGORIEN = {str(k): str(v) for k, v in (_teil("branche_kategorien", {}) or {}).items()}

# ---- Konten / Systemgrenze -------------------------------------------------
_K = _teil("konten", {})

def _iban_map(abschnitt):
    """{IBAN(ohne Leerzeichen, groß): Anzeigename}"""
    return {str(k).replace(" ", "").upper(): str(v)
            for k, v in (_K.get(abschnitt) or {}).items() if str(k).strip()}

# Eigene Giro-Konten = das "System": Überweisungen untereinander sind keine Ausgaben.
EIGENE_GIRO = _iban_map("eigene_giro")
# Weitere echte interne Umbuchungen (eigene Konten außerhalb der Giro-Karte).
WEITERE_INTERN = _iban_map("weitere_intern")

# Außen liegende, aber zugeordnete Konten: zählen mit, bekommen aber eine
# Vorgabe-Kategorie (Sparen, Kredit, Einnahme…), die keine Händlerregel treffen kann.
ZUORDNUNG, _NAMEN_AUS_ZUORDNUNG = {}, {}
for _iban, _e in (_K.get("zuordnung") or {}).items():
    _iban = str(_iban).replace(" ", "").upper()
    if not _iban:
        continue
    if not isinstance(_e, dict) or not _e.get("kategorie"):
        raise KonfigFehler(
            f"konten.zuordnung['{_iban}'] braucht mindestens ein Feld 'kategorie' "
            f"(erlaubt: {', '.join(KATEGORIEN)}).")
    ZUORDNUNG[_iban] = (_e["kategorie"], _e.get("notiz", ""))
    if _e.get("name"):
        _NAMEN_AUS_ZUORDNUNG[_iban] = _e["name"]

# IBAN -> sprechender Kontoname für die Spalte 'konto' (parse_konten.py).
KONTO_NAMEN = {**EIGENE_GIRO, **WEITERE_INTERN, **_NAMEN_AUS_ZUORDNUNG}

# ---- Eigene Regeln ---------------------------------------------------------
# Haushaltsspezifische Kategorisierungsregeln (eigene Immobilie, Vermieter, Stammlokal).
# Die breiten, allgemein gültigen Regeln bleiben als SEED in rules.py — die sind für
# jeden deutschen Haushalt brauchbar und keine Personendaten.
EIGENE_REGELN = []
for _r in _teil("eigene_regeln", []):
    fehlend = [f for f in ("name", "typ", "muster", "kategorie") if not _r.get(f)]
    if fehlend:
        raise KonfigFehler(f"eigene_regeln: Feld(er) {fehlend} fehlen bei {_r!r}")
    EIGENE_REGELN.append((_r["name"], int(_r.get("prio", 12)), _r["typ"], _r["muster"],
                          _r["kategorie"], _r.get("labels", "")))


def pruefen():
    """Sanity-Check vor dem Pipeline-Lauf. Wirft KonfigFehler mit klarem Text.
    Prüft vor allem Kategorien: ein Tippfehler würde sonst still eine neue Kategorie
    erzeugen und in der Statistik als eigene Zeile auftauchen."""
    if not KATEGORIEN:
        raise KonfigFehler("Liste 'kategorien' ist leer.")
    if not EIGENE_GIRO:
        raise KonfigFehler(
            "'konten.eigene_giro' ist leer — ohne eigene Giro-Konten kann die "
            "Systemgrenze interne Umbuchungen nicht erkennen und zählt sie als Ausgaben.")
    erlaubt = set(KATEGORIEN)
    for iban, (cat, _n) in ZUORDNUNG.items():
        if cat not in erlaubt:
            raise KonfigFehler(f"konten.zuordnung['{iban}']: Kategorie '{cat}' steht nicht "
                               f"in 'kategorien'.")
    for r in EIGENE_REGELN:
        if r[4] not in erlaubt:
            raise KonfigFehler(f"eigene_regeln '{r[0]}': Kategorie '{r[4]}' steht nicht "
                               f"in 'kategorien'.")
    for b, c in BRANCHE_KATEGORIEN.items():
        if c not in erlaubt:
            raise KonfigFehler(f"branche_kategorien['{b}']: Kategorie '{c}' steht nicht "
                               f"in 'kategorien'.")
    for feld, werte in (("kategorien_immer_vertrag", KAT_IMMER_VERTRAG),
                        ("kategorien_nicht_reise", KAT_NICHT_REISE),
                        ("kategorien_kein_konsum", KAT_KEIN_KONSUM)):
        for c in werte:
            if c not in erlaubt:
                raise KonfigFehler(f"{feld}: '{c}' steht nicht in 'kategorien'.")
    # Ein Konto kann nicht intern UND zugeordnet sein. Ungeprueft entscheidet sonst
    # still die Reihenfolge im Code (intern gewinnt) statt einer bewussten Wahl.
    for rubrik, menge in (("eigene_giro", EIGENE_GIRO), ("weitere_intern", WEITERE_INTERN)):
        doppelt = sorted(set(menge) & set(ZUORDNUNG))
        if doppelt:
            raise KonfigFehler(f"IBAN(s) {doppelt} stehen in '{rubrik}' UND in 'zuordnung' — "
                               f"intern und zugeordnet gleichzeitig geht nicht.")
    return True


if __name__ == "__main__":
    quelle = BEISPIEL if IST_BEISPIEL else PFAD
    print(f"Konfiguration: {quelle}")
    try:
        pruefen()
        print("  Prüfung: ok")
    except KonfigFehler as e:
        print(f"  FEHLER: {e}"); sys.exit(1)
    print(f"  Haushalt      : {NAME or '(ohne Namen)'}")
    print(f"  Kategorien    : {len(KATEGORIEN)}")
    print(f"  Eigene Giro   : {len(EIGENE_GIRO)}")
    print(f"  Weitere intern: {len(WEITERE_INTERN)}")
    print(f"  Zuordnung     : {len(ZUORDNUNG)}")
    print(f"  Heimatorte    : {len(HEIMAT_ORTE)}")
    print(f"  Eigene Regeln : {len(EIGENE_REGELN)}")

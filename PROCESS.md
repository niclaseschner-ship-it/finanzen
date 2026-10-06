# Ausgaben-Datenbank — Prozess / Runbook

Robuster, wiederholbarer Ablauf. Rohdaten bleiben unangetastet; alle Schritte sind
idempotent (neu ausführbar). Reihenfolge ist wichtig (jeder Schritt nutzt den vorherigen).
Schnellstart & Konfiguration: siehe [`README.md`](README.md). Pfade zentral in `scripts/db.py`.

## Konfiguration (Input, aber keine Daten)
`konfig.json` im Projektordner: Kontenkarte/Systemgrenze, Kategorienliste, Heimatregion,
eigene Namen, eigene Regeln. **Eine** Quelle für Pipeline, Editor und Statistik — vorher lag
das über vier Module verteilt im Quellcode. Vorlage: `konfig.beispiel.json`, Prüfung:
`python scripts/konfig.py`. Nicht im Git.

## Datenquellen (Input)
- **Konto:** Bank-CSV (DKB/GLS) in `konten/` → `parse_konten.py` führt zu `output/transaktionen.csv` zusammen.
- **Gmail / GMX / weitere Postfächer:** mbox aus dem **Thunderbird-Profil** (optional, nur
  Beleg-Kontext, nie Buchungsquelle). Thunderbird ist der Weg, weil es die mbox-Dateien
  liefert, die `ingest_mail.py` liest — kein eigener Mailzugriff, kein Passwort in dieser
  App, Mails bleiben lokal. Voraussetzung ist der **Offline-Abgleich** in Thunderbird
  (Konten-Einstellungen → Synchronisation & Speicherplatz), sonst sind die mbox-Dateien
  leer. Einsammeln + importieren: `python einrichten.py --mail`.

## Pipeline — `python run_all.py` (in dieser Reihenfolge)
| # | Schritt | Macht |
|---|--------|-------|
| 0 | `konfig.pruefen()` | Konfiguration prüfen, **bevor** Daten angefasst werden. Beispielkonfiguration → Abbruch (fremde Kontenkarte kategorisiert still falsch) |
| 1 | `parse_konten.py` | Alle Bank-Exporte aus `konten/` zusammenführen + Überlapp robust deduplizieren → `output/transaktionen.csv` |
| 2 | `ingest_transactions.py` | CSV → DB. **Systemgrenze/Kontenkarte**: interne Umbuchungen raus, Sparen/Kredit/Einnahmen markieren |
| 2b | `rules.ensure_schema()` | leere Kategorie-/Label-Tabellen anlegen (nur beim ersten Lauf relevant, s.u.) |
| 3 | `enrich.py` | Signale je Buchung: Zahlungsart, Händler (norm.), Ort, echtes Kaufdatum, Gläubiger-/Amazon-/PayPal-Refs, wiederkehrend |
| 4 | `match.py` | Buchung ↔ Mail/Beleg verknüpfen (Amazon-Nr / PayPal / Betrag+Händler+Datum) → `tx_mail_links` |
| 5 | `branche.py` | Branche unbekannter Händler via OpenStreetMap (gratis, **gecacht** in `merchant_branche`) |
| 6 | `rules.py` | Regeln (`rules`=SEED+SEED2+`eigene_regeln`) + KI-Fallback + **manuelle Schicht** + **Reise-Erkennung** + **Verträge** → `tx_category` (1 Kat.) + `tx_labels` (n) |
| 7 | `build_context.py` | Mail-Kontext + Produktzeile je Buchung → `tx_context` |
| 8 | `frontend.py` | Statistik-Seite → `output/statistik.html` |
| 9 | `liste.py` | Kategorien-Katalog + Alt-Liste; liefert `liste.CATS` für den Editor |

**Warum `branche` VOR und `build_context` NACH `rules` läuft:** beide wählen Buchungen über
deren Kategorie aus. `branche` sucht Händler, die noch `Sonstiges` sind, und liefert das
Ergebnis als Fallback wieder an `rules` — diese gegenseitige Abhängigkeit ist gewollt und
löst sich über die Läufe hinweg auf (jeder Lauf verbessert den Stand). `build_context` hat
diese Rückkopplung nicht: dort war die frühere Position schlicht falsch, frisch importierte
Buchungen bekamen ihren Beleg-Kontext erst einen Lauf später. Damit der allererste Lauf auf
leerer Datenbank nicht an der noch fehlenden Tabelle scheitert, legt Schritt 2b sie leer an.

Alle Schritte liegen in `scripts/` — die Pipeline braucht **kein Projekt außerhalb** dieses
Ordners. E-Mail-Import läuft separat/einmalig über `ingest_mail.py <mbox> <label>` (resumebar).

## Interaktiver Server — `python app.py` → http://localhost:8765/finanzen/
Der eigentliche Arbeitsplatz (reine Stdlib, kein Build). Eine geteilte JS-Library (`shared.js`,
`window.BK`) liefert überall dieselbe Detailtabelle + denselben Bestätigen/Ignorieren-Mechanismus.

Alles liegt unter `/finanzen/`, alle Verweise in den Seiten sind relativ. Alte Adressen ohne
`/finanzen/` leiten weiter. Aussehen: `seiten/stil.css` (gleiche Farben wie die Handy-App),
Kopfleiste setzt der Server ein (`<!--FNAV:…-->` → `app.kopfleiste`).

| Route (unter `/finanzen`) | Seite |
|---|---|
| `/` | **Übersicht** am Rechner, **Handy-App** am Telefon (Erkennung am User-Agent; `?ansicht=handy\|desktop\|auto` merkt sich die Wahl im Cookie) |
| `/editor` | **Buchungen** — prüfen, Kategorie/Labels/Kommentar setzen (Einzel-Edit, merge-sicher) |
| `/statistik.html` | **Statistik** — wird bei jedem Aufruf frisch aus der DB gebaut; Filter: Jahr·Kategorie·Vertrag·Label |
| `/vertraege` | **Verträge** (= Fixkosten) — Kandidaten bestätigen/ablehnen, aktiv/ausgelaufen |
| `/reisen` | **Reisen** — erkannte Reisen bestätigen → Urlaubsstempel |
| `/vermoegen`, `/vorsorge` | **Vermögen** (Salden, Depot, Immobilien) und **Vorsorge** (Planung) |
| `/api/handy/*` | verdichtete Daten für Handy-App und Übersicht (`handy.py`) |

**Filter** bleiben über Seitenwechsel erhalten (sessionStorage je Seite), Reset nur bei hartem
Neuladen (F5) oder „alle Buchungen". **Berücksichtigter Zeitraum** (`settings`-Tabelle; `run_all` setzt das Ende automatisch auf den letzten vollen Monat, von Hand über `db.set_setting`)
begrenzt alle Auswertungen; der laufende Monat bleibt immer draußen (nur vollendete Monate).

## Kategorisierungs-Trichter (so kategorisieren wir)
1. **Systemgrenze**: flow=intern → raus; preset (Sparen/Kredit/Einnahme) aus der Kontenkarte
   (`konfig.json` → `konten`).
2. **Regeln** (Gläubiger-ID > Händler-Keyword): Fixkosten + häufige Händler. Erst spezifisch, dann breit.
   Allgemeine Regeln = `SEED`/`SEED2` in `rules.py`, haushaltseigene = `konfig.json` → `eigene_regeln`
   (werden zuletzt angehängt und überstimmen bei gleicher Priorität die eingebauten).
3. **OSM-Branche** (gecacht) als mechanischer Fallback.
4. **KI-Fallback** (`ki_overrides`, Status `ki-vorschlag`): Long-Tail, reviewbar.
5. **Manuelle Schicht** (`tx_manual`/`user_overrides`): schlägt alles, tx-id-stabil.
6. **Reise-Bestätigung**: zuletzt — bestätigte Reise stempelt ihre Buchungen auf „Urlaub".
7. **Rest** → `Sonstiges`, Status `unkategorisiert` (sichtbar, nie gelöscht).

## Robustheits-Prinzipien (hart gelernt)
- **Nichts fällt weg**: Status statt Löschen; ohne Treffer → sichtbar markiert.
- **Rohdaten unantastbar**; Kategorien/Labels sind ableitbare Schicht (jederzeit neu rechenbar).
- **Buchungen 1:1 aus der Bank** — nie aus Mails „dazu erfinden".
- **Kollisionssichere IDs** (echte Doppelbuchungen bleiben erhalten).
- **Breite Muster-Regeln vor Einzel-Overrides** (generalisieren auf künftige Daten).
- **KI als Skalpell**, nicht als Bagger — nur für den Rest, mit Konfidenz + Review.
- **Server nicht neu starten, während editiert wird** (Edits gehen sonst verloren).
- Fallstricke: `DM-`(Bindestrich), `denn's`(Apostroph), `dkb ag`→Depot (greedy), EREF/MREF-Müll,
  PayPal nur am Namen (besser: Creditor-ID), „Urlaub = Label/Stempel, nicht Auto-Kategorie",
  Heim-Einkauf zählt immer als Heim-Tag (trennt zwei Reisen mit Heim-Woche dazwischen).

## Datenmodell (Kern)
- `transactions` (+ flow, is_internal, preset_category) — Rohbuchungen
- `tx_enrich` (Signale) · `tx_context` (Mail-Kontext/Produkt) · `tx_mail_links` (Beleg-Verknüpfung)
- `rules` (datengetrieben) · `ki_overrides` (KI-Schicht) · `merchant_branche` (OSM-Cache) · `merchant_rules`
- `tx_category` (genau 1 Kat. + Quelle/Begründung/Status) · `tx_labels` (n Labels) · `tx_manual` (manuelle Schicht)
- `contracts` (erkannte Verträge/Fixkosten) · `trips` (erkannte Reisen) · `settings` (Zeitraum) · `cats_catalog`/`labels_catalog`

## Schnell-Wege
- **Online-Demo neu bauen** (nach Änderungen an Seiten oder Daten-Funktionen):
  `python demo/bauen.py` — die echten Seiten mit dem Demo-Haushalt, ohne Server lauffähig.
- **Screenshots neu aufnehmen:** `python docs/bilder/aufnehmen.py` (braucht Playwright) —
  README-Auswahl in `docs/bilder/`, alle Ansichten hell/dunkel in `docs/bilder/alle/`.
- **Neuer Kontoexport:** CSV in `konten/` ablegen → `python run_all.py` (auf dem Pi macht das der Skill `finanz-monatsimport`; eine Import-Seite gibt es seit 06.10.2026 nicht mehr).
  Manuelle Entscheidungen bleiben erhalten (tx-id stabil).
- **Regeln ergänzen:** Zeile in `SEED2` (breites, allgemeines Muster) ODER `konfig.json` →
  `eigene_regeln` (haushaltsspezifisch) ODER `ki_overrides` (Einzelhändler) → `run_all.py`.
- **Neues Konto:** IBAN in `konfig.json` eintragen (`eigene_giro` wenn eigenes Girokonto,
  sonst `zuordnung` mit Vorgabe-Kategorie) → `python scripts/konfig.py` → `run_all.py`.
- **Nur Auswertung neu:** `python frontend.py` (oder Statistik-Seite einfach neu laden).
- `scripts/extra/`: optionale Werkzeuge (`report.py`, `ki_seed.py`, `paypal_from_mail.py`,
  `dashboard.py`) — nicht im Hauptlauf. **Aufruf als Modul** aus `scripts/`:
  `python -m extra.report`. Direkt (`python extra/report.py`) findet Python `db` nicht.

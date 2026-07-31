# Änderungen

Format angelehnt an [Keep a Changelog](https://keepachangelog.com/de/1.1.0/).
Versionen nach [SemVer](https://semver.org/lang/de/) — solange die Hauptversion 0 ist, können
sich Datenmodell und Konfigurationsformat noch ändern.

## [0.1.0] — 2026-07-31

Erste öffentliche Fassung. Die Anwendung lief vorher gut ein Jahr privat; dieser Stand ist
das Ergebnis der Aufräumarbeit, die sie weitergebbar gemacht hat.

### Enthalten
- **Pipeline** in neun Schritten: Bank-Exporte zusammenführen (DKB, GLS) mit robuster
  Deduplizierung überlappender Downloads → Systemgrenze aus der Kontenkarte → Anreicherung
  (Zahlungsart, Händler, Ort, echtes Kaufdatum, Referenzen) → Belegabgleich → Branchen-Fallback
  über OpenStreetMap → Kategorisierung → Beleg-Kontext → Statistik- und Listenseiten.
- **Belegverknüpfung mit E-Mails** über Bestellnummer, PayPal-Transaktions-ID oder
  Händler+Betrag+Datum. Jede Verknüpfung trägt ihre Methode und Konfidenz; mehrdeutige Fälle
  bleiben bewusst unverknüpft.
- **Lokaler Arbeitsplatz** (nur Standardbibliothek): Editor, Statistik, Verträge, Reisen,
  Import, Vermögen, Vorsorge.
- **Vertrags- und Reiseerkennung** allein aus den Buchungsmustern.
- **Geführte Einrichtung** (`einrichten.py`) — liest IBANs und Orte aus den Exporten und fragt
  nur, was in keiner CSV steht. Schlägt Heimatorte über die Monatsverteilung vor und markiert
  Sammelkonten der Bank.
- **Beispieldaten** (`beispieldaten/erzeugen.py`): erfundener Haushalt über 18 Monate samt
  Beleg-Mails als mbox — die Anwendung lässt sich ohne eigene Daten vollständig ausprobieren.
- **Konfiguration in einer Datei** (`konfig.json`), mit Prüfung vor jedem Pipeline-Lauf.
- 60 Tests, reine Standardbibliothek: `python -m unittest discover -s tests -t tests`.

### Sicherheit
- Der Server hört nur auf `127.0.0.1` und weist Anfragen mit fremdem `Host`- oder
  `Origin`-Header ab (DNS-Rebinding, CSRF). Rumpfgröße gedeckelt.
- Buchungstexte werden script-sicher in die erzeugten Seiten eingebettet. Ohne das könnte
  jemand, der die eigene IBAN kennt, per Verwendungszweck Code einschleusen.
- Chart.js liegt im Projekt statt beim CDN — die Seiten enthalten den kompletten
  Buchungsbestand.

### Bekannte Grenzen
- Bankformate: bisher nur **DKB** und **GLS**.
- Oberfläche und Dokumentation auf Deutsch (englische Kurzfassung: `README.en.md`).
- Kein Mehrbenutzerbetrieb, keine Budgets, kein automatischer Bankabruf (bewusst — das hieße
  Zugangsdaten).
- Die Branchenerkennung schlägt beim allerersten Lauf noch nicht an; sie greift ab dem
  zweiten (siehe `PROCESS.md`).

[0.1.0]: https://github.com/niclaseschner-ship-it/finanzen/releases/tag/v0.1.0

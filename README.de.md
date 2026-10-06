# Finanzen

*[English version](README.md) · die Anwendung selbst ist deutschsprachig.*

**Deine Kontoauszüge werden zu einer Statistik, die dir sagt, wohin das Geld geht —
auf deinem Rechner, ohne Konto bei irgendwem, und jede Zuordnung ist begründet.**

- 🔒 **Lokal.** Keine Cloud, kein Bankzugang, kein Konto. Die Daten verlassen den Rechner nicht.
- 🔍 **Nachvollziehbar.** Zu jeder Buchung steht da, *warum* sie in dieser Kategorie liegt. Was unklar ist, bleibt sichtbar unklar statt geraten zu werden.
- 🧾 **Belege statt Rätselraten.** Zu einer Buchung „AMAZON −57,50 €" steht da, *was* drin war —
  automatisch aus deinen eigenen Bestellmails verknüpft, über die Bestellnummer.
- ⚡ **Keine Installation.** Python 3.10 genügt — kein `pip install`, kein Build, kein Docker.
- 📱 **Am Rechner und am Handy.** Eine Adresse: am Rechner die Übersicht, am Telefon eine
  installierbare App. Hell und dunkel folgen der Systemeinstellung.

[![Übersicht](docs/bilder/uebersicht.png)](docs/bilder/uebersicht.png)

**[▶ Live-Demo im Browser](https://niclaseschner-ship-it.github.io/finanzen/demo/)** — die echte
App mit einem erfundenen Haushalt, ohne Installation. Am Handy öffnet sich die Handy-Ansicht.

## Ausprobieren — ohne eigene Daten

```bash
git clone https://github.com/niclaseschner-ship-it/finanzen.git
cd finanzen
python scripts/app.py        # -> http://localhost:8765/finanzen/
```

Solange keine eigenen Daten da sind, zeigt die App einen **kompletten erfundenen Haushalt**:
18 Monate, zwei Konten in zwei Bankformaten, Gehalt, Miete, Fixkosten, eine vermietete
Wohnung mit Darlehen, Tagesgeld und Depot, Bestellmails als echtes mbox, zwei Reisen. Er wird
beim ersten Start in `beispieldaten/demo/` angelegt — eigene Datenbank, eigene Konfiguration,
oben rechts als „Beispieldaten“ markiert. Neu erzeugen: `python beispieldaten/erzeugen.py`.

| Buchungen | Statistik | Verträge | Vermögen |
|---|---|---|---|
| [![Buchungen](docs/bilder/editor.png)](docs/bilder/editor.png) | [![Statistik](docs/bilder/statistik.png)](docs/bilder/statistik.png) | [![Verträge](docs/bilder/vertraege.png)](docs/bilder/vertraege.png) | [![Vermögen](docs/bilder/vermoegen.png)](docs/bilder/vermoegen.png) |
| Kategorie, Labels — und die Begründung | Einnahmen, Ausgaben, Kategorien im Verlauf | Fixkosten, allein aus der Wiederholung erkannt | Konten, Depot, Immobilie, Kredit |

### Am Handy

Dieselbe Adresse öffnet am Telefon eine installierbare App (PWA): der Monat gegen den
Zwölfmonatsschnitt, Buchungen mit Suche, und eine **Prüfliste** für alles, was die Automatik
nur geraten hat — „Passt“ oder „Ändern“ mit einem Tipp. Umschalten zwischen beiden Ansichten
geht jederzeit.

[![Handy-App](docs/bilder/handy.png)](docs/bilder/handy.png)

Die Demo zeigt absichtlich auch, was **nicht** aufgeht: ein paar Händler bleiben
`unkategorisiert`, statt geraten zu werden, eine erkannte Reise und zwei Verträge warten auf
Bestätigung.

## Wie es funktioniert

Rohe **Kontoauszüge** — ergänzt um **E-Mail-Belege** — werden zu einer durchsuchbaren,
kategorisierten Ausgaben-Statistik. Eine SQLite-Datei ist die einzige Wahrheit; alle
Auswertungen werden daraus **reproduzierbar** neu berechnet.

**Datenquellen**

- 🏦 **Bank-Konten (CSV)** — Format wird automatisch erkannt, Überlappungen mehrerer Exporte
  werden dedupliziert. Die Buchung ist die Wahrheit der Geldflüsse. Unterstützt: **DKB** und
  **GLS**; andere Banken brauchen ein paar Zeilen in
  [`scripts/parse_konten.py`](scripts/parse_konten.py) — Beiträge willkommen.
- 📧 **E-Mail-Postfächer** (mbox, z. B. aus Thunderbird) — liefern Belege und Produktdetails,
  „PayPal *Ref" wird so zu „Laufschuhe". Nur als Kontext, nie als Buchung.
- 🗺️ **OpenStreetMap** — unbekannte Kartenhändler werden einmalig nachgeschlagen (Branche →
  Kategorie) und zwischengespeichert. Kein Schlüssel, keine Beträge nach außen.
- 🧠 **KI, nur für den Rest** — für unklare Restposten ein prüfbarer Vorschlag mit Konfidenz
  und Begründung. Die eigene Korrektur schlägt immer alles.

**Ablauf** — eine idempotente Pipeline (`scripts/run_all.py`), beliebig oft wiederholbar;
manuelle Entscheidungen bleiben über stabile Buchungs-IDs erhalten:

1. **Konten zusammenführen** — alle Exporte vereinen, Überlappungen robust deduplizieren
2. **Einlesen + Systemgrenze** — interne Umbuchungen raus, Sparen/Kredit/Einnahme markieren
3. **Anreichern** — Zahlungsart, Händler, Ort, echtes Kaufdatum, Gläubiger-ID, wiederkehrend
4. **Belege abgleichen** — Buchung ↔ Mail (Bestellnummer, PayPal-ID, Betrag+Händler+Datum)
5. **Kategorisieren** — Regeln, Reisen, Verträge; genau eine Kategorie, beliebig viele Labels
6. **Auswerten** — jede Frage ist Filter + Gruppierung über dieselben Buchungen

**Der Kategorisierungs-Trichter** — von der sichersten Quelle zur unsichersten; was nicht
greift, fällt nie weg, sondern landet sichtbar in „Sonstiges":
Systemgrenze (eigene Konten, Kontenkarte) → Regeln (Gläubiger-ID vor Händler-Stichwort) →
Branchen-Nachschlag → KI-Vorschlag → manuelle Korrektur (schlägt alles) → Reise-Erkennung
(stempelt bestätigte Reisen auf „Urlaub").

**Prinzipien**

- **Rohdaten unantastbar** — Buchungen kommen 1:1 aus der Bank und werden nie erfunden.
  Kategorien und Labels sind eine ableitbare Schicht.
- **Nichts fällt still weg** — Status statt Löschen.
- **Mechanik vor KI** — deterministische Regeln zuerst; die KI ist das Skalpell für den Rest.
- **Alles lokal** — reine Standardbibliothek, kein Cloud-Dienst.

## 🧾 Belege aus E-Mails — was war eigentlich in dem Paket?

Der Kontoauszug sagt „AMAZON PAYMENTS EUROPE S.C.A, −57,50 €". Das ist die Stelle, an der
jedes Haushaltsbuch aufhört und man selbst im Postfach sucht. Diese App macht den Schritt
mit: sie verknüpft Buchungen mit deinen **eigenen Bestell- und Zahlungsmails** und zeigt
die Produktzeile direkt an der Buchung.

[![Belegverknüpfung](docs/bilder/belege.png)](docs/bilder/belege.png)

**Mechanisch, nicht geraten** — und jede Verknüpfung sagt, wie sicher sie ist:

| Weg | Sicherheit |
|---|---|
| Bestellnummer aus dem Verwendungszweck steht in der Mail | **sicher** |
| PayPal-Transaktions-ID | **sicher** |
| PayPal-Händler + Betrag im Zeitfenster | gut |
| Händler + Betrag + Datum (±5 Tage) | Schätzung, im Editor als solche markiert |

Bei mehrdeutigen Fällen wird **nicht** verknüpft — eine falsche Zuordnung wäre schlimmer
als gar keine. PDF-Anhänge werden gespeichert und ihr Text mitdurchsucht (dafür das
optionale `pymupdf`), sodass auch Rechnungen im Anhang gefunden werden.

**Woher die Mails kommen:** aus **Thunderbird**. Der Import liest mbox-Dateien, und
Thunderbird legt genau die an. Deshalb der Umweg statt eines eigenen Postfachzugriffs:
**diese App bekommt nie dein Mail-Passwort**, die Nachrichten liegen lokal, und du
entscheidest pro Ordner, was importiert wird.

```bash
python scripts/einrichten.py --mail    # findet die Profile, listet die Ordner mit Größe
```

Wichtig ist ein Schritt, den man leicht übersieht: In Thunderbird unter
*Konten-Einstellungen → Synchronisation & Speicherplatz* muss „Mails auf diesem Computer
speichern" aktiv sein — sonst sind die mbox-Dateien leer. Der Import ist idempotent,
abbrechen und später fortsetzen ist gefahrlos.

E-Mails sind dabei **ausschließlich Kontext, nie eine Buchungsquelle**: Beträge und
Buchungen kommen immer 1:1 aus der Bank. Ohne Mails funktioniert alles, die Detailspalte
bleibt nur leerer.

## Wann dieses Projekt — und wann ein anderes

Es gibt ausgereifte Alternativen, und für viele Leute sind sie die bessere Wahl. Diese
hier ist absichtlich klein und deckt einen schmalen Fall ab:

| Nimm … | wenn du … |
|---|---|
| **[Firefly III](https://github.com/firefly-iii/firefly-iii)** | doppelte Buchführung, Budgets, mehrere Nutzer, Handy-App und Anbindung an Banking-APIs willst. Der Platzhirsch — deutlich mehr Funktionen, dafür Server, Datenbank und Einarbeitung. |
| **[Actual Budget](https://github.com/actualbudget/actual)** | nach der Umschlagmethode budgetieren willst (YNAB-Stil), also **vorausplanen** statt rückblickend auswerten. |
| **[beancount](https://beancount.github.io/) / hledger** | Klartext-Buchhaltung magst und deine Auswertungen selbst schreibst. |
| **dieses Projekt** | wissen willst, **wo dein Geld hingegangen ist**, ohne dafür ein System aufzusetzen — und ohne dass eine Software je dein Bank- oder Mail-Passwort sieht. |

Was es hier gibt und dort nicht:

- **Belegverknüpfung aus dem eigenen Postfach.** Zu „AMAZON −57,50 €" steht die Produktzeile
  aus deiner Bestellmail. Belegabgleich existiert sonst vor allem als kommerzielles SaaS für
  Spesenabrechnung, oder bei [Midday](https://github.com/midday-ai/midday) für Selbstständige.
- **Begründungspflicht.** Jede Kategorie trägt ihre Quelle. Was unklar ist, bleibt sichtbar
  unklar — es wird nichts geraten, damit die Statistik hübsch aussieht.
- **Kein Setup.** Kein Server, kein Docker, keine Datenbank-Installation, kein `pip install`.
- **Reise- und Vertragserkennung** allein aus den Buchungsmustern, ohne dass du etwas anlegst.

Was es hier **nicht** gibt: Budgets und Sollwerte, Mehrbenutzerbetrieb, Handy-App,
automatischen Bankabruf (bewusst — das hieße Zugangsdaten), Fremdwährungskonten,
doppelte Buchführung. Und die CSV-Formate sind bisher **DKB und GLS**.

## Voraussetzungen
- **Python 3.10+** — der Kern nutzt nur die **Standardbibliothek** (kein `pip install` nötig).
- Optional: **PyMuPDF** (`pip install pymupdf`) — nur für Text aus PDF-Mailanhängen.
- **Kein Internet nötig.** Chart.js liegt im Projekt (`scripts/seiten/chart.min.js`) und
  wird neben die erzeugte Seite gelegt — die Seite trägt alle Buchungen in sich, da hat
  ein Skript von fremdem Server nichts zu suchen.

## Von der Demo zu den eigenen Zahlen

Es gibt **nichts zu installieren** außer Python — die Arbeit ist Konfiguration. Der Weg ist
derselbe Haushalt, Bereich für Bereich durch die eigenen Daten ersetzt:

1. **Konten und Kontenkarte** — eigene CSV-Exporte nach `konten/` (mindestens 12 Monate),
   dann `python scripts/einrichten.py`. Es liest die Exporte und fragt nur, was in keiner CSV
   steht (welche Konten die eigenen sind, Heimatorte). Sobald `konfig.json` im Projektordner
   liegt, zeigt die App die eigenen Zahlen; die Demo bleibt in `beispieldaten/demo/` liegen.
2. **Belege** (optional) — `python scripts/einrichten.py --mail` liest mbox-Dateien, z. B. aus
   Thunderbird.
3. **Vermögen** (optional) — `vermoegen/positionen.beispiel.json` nach
   `vermoegen/positionen.json` kopieren und ausfüllen; die Demo zeigt, wie es aussieht.
4. **Vorsorge** — direkt auf der Seite; die Istwerte kommen aus den Buchungen.

Wer Claude Code nutzt, startet den mitgelieferten Skill **`finanz-einrichtung`**
([`.claude/skills/`](.claude/skills/)): er geht diese Schritte mit, prüft die Vorschläge,
bevor sie in die Konfiguration wandern, und zweifelt das Ergebnis an.

```bash
cd scripts
python einrichten.py --pruefen   # rein lesend: was steckt in den Exporten?
python einrichten.py             # erzeugt konfig.json
python einrichten.py --mail      # optional: Belege aus Thunderbird
```

**Jeden Monat:** neue Exporte nach `konten/` und `python run_all.py`. Eine Import-Seite gibt
es bewusst nicht. Mit Claude Code übernimmt das der Skill `finanz-monatsimport`: er prüft,
ob die Exporte lückenlos anschließen, kategorisiert den unklaren Rest mit Begründung und
meldet, was auffällt — ausgebliebene Miete, ausgelaufene Verträge, neue Reisen.

## Konfiguration — `konfig.json`
Alles, was von Haushalt zu Haushalt anders ist, steht in **einer** Datei im Projektordner.
**Kein Quellcode-Editieren nötig.** Von Hand geht es auch:

```bash
copy konfig.beispiel.json konfig.json     # Vorlage kopieren, dann ausfüllen
cd scripts && python konfig.py            # prüft die Datei und zeigt, was gelesen wurde
```

| Abschnitt | Was drin steht | Warum es wichtig ist |
|---|---|---|
| `konten.eigene_giro` | eigene Girokonten (IBAN → Name) | **Systemgrenze.** Überweisungen zwischen diesen Konten sind keine Ausgaben. Fehlt hier ein Konto, ist die Statistik zu hoch. |
| `konten.zuordnung` | Depot, Darlehen, Gehalt, Kindergeld | zählen mit, bekommen aber eine feste Vorgabe-Kategorie, die keine Händlerregel überschreibt |
| `kategorien` | die feste Kategorienliste | genau eine pro Buchung; eigene ergänzen (z.B. „Immobilie X") |
| `haushalt.heimat_orte` | Wohnort + Nachbarorte | Reise-Erkennung. Ohne das ist der Alltag eine Dauerreise. |
| `haushalt.eigene_namen` | Familien-/Vermieternamen | verhindert, dass Privatmails als Beleg-Kontext an Buchungen landen |
| `eigene_regeln` | Hausverwaltung, Vermieter, Stammlokal | die breiten Regeln für gängige Händler sind in [`scripts/rules.py`](scripts/rules.py) eingebaut |

`konfig.json` ist **nicht** im Git (siehe [`.gitignore`](.gitignore)) — versioniert ist nur
die Vorlage. Solange keine `konfig.json` existiert, läuft die Beispielkonfiguration: Server
und Seiten starten, aber `run_all.py` **verweigert** den Lauf. Mit fremder Kontenkarte wären
die Auswertungen still falsch, und das ist schlimmer als ein Abbruch.

Die Vermögensansicht hat ihre eigene gepflegte Datei — Vorlage:
[`vermoegen/positionen.beispiel.json`](vermoegen/positionen.beispiel.json).

## Konfiguration (Pfade)
Alle Pfade stehen an **einer** Stelle in [`scripts/db.py`](scripts/db.py) und sind per
Umgebungsvariable überschreibbar:

| Env-Variable | Default | Bedeutung |
|---|---|---|
| `FINANZEN_BASE` | der Ordner dieses Repos — bzw. `beispieldaten/demo/`, solange dort keine eigenen Daten (`konfig.json`, `finanzen.db`) liegen | Datenordner: DB, `output/`, `attachments/` |
| `FINANZEN_BANK` | `<BASE>\konten` | Eingang für Bank-CSV-Exporte |
| `FINANZEN_BANK_CSV` | `<BASE>\output\transaktionen.csv` | zusammengeführte Konto-CSV |
| `FINANZEN_PORT` | `8765` | Port des Servers — eigener Port, wenn eine zweite Instanz (z.B. die Demo) parallel laufen soll |

Die Defaults sind **relativ zum Repo** — ein frischer Clone läuft ohne gesetzte
Umgebungsvariablen. Setzen muss man sie nur, wenn Daten woanders liegen sollen:

```bash
# Beispiel: Kontoexporte liegen auf einem anderen Laufwerk
set FINANZEN_BANK=D:\bank-exporte
```

## Schnellstart (eigene Daten, ohne Assistent)
1. DKB-/GLS-CSV nach `konten/` kopieren (mindestens 12 Monate).
2. `python scripts/einrichten.py` — oder die Vorlage `konfig.beispiel.json` als `konfig.json`
   von Hand ausfüllen. Prüfen: `python scripts/konfig.py`.
3. `cd scripts && python run_all.py` (idempotent, beliebig oft wiederholbar)
4. `python app.py` → http://localhost:8765/finanzen/

## Die Seiten (alle unter http://localhost:8765/finanzen/)
- **Übersicht** (`/finanzen/`) — der Monat gegen den Durchschnitt, Kennzahlen, Kategorien.
  Am Telefon öffnet dieselbe Adresse die Handy-App.
- **Buchungen** (`/finanzen/editor`) — jede Buchung prüfen, Kategorie/Labels/Kommentar setzen.
- **Statistik** (`/finanzen/statistik.html`) — Einnahmen/Ausgaben pro Monat, Kategorie-Stack,
  Ranking, Reisen. Filter: Jahr · Kategorien · Verträge · Label. Balken anklicken → Buchungen.
- **Verträge** (`/finanzen/vertraege`) — mechanisch erkannte wiederkehrende Zahlungen (= Fixkosten),
  bestätigen/ablehnen, aktiv/ausgelaufen.
- **Reisen** (`/finanzen/reisen`) — automatisch erkannte Reisen (zusammenhängend außerhalb der
  Heimatregion), bestätigen → Buchungen werden zu „Urlaub".
- **Vermögen** (`/finanzen/vermoegen`) — Konten, Depot, Immobilien mit Bewertungsspanne, Kredite.
- **Vorsorge** (`/finanzen/vorsorge`) — Ruhestandsplanung Jahr für Jahr, mit Istwerten aus den Buchungen.

## Aufbau
- `scripts/` — der Kern (Pipeline + Server). Details & Reihenfolge: [`PROCESS.md`](PROCESS.md).
- `scripts/extra/` — optionale/einmalige Werkzeuge (Text-Report, KI-Seed, Alt-Dashboard),
  nicht Teil des Hauptlaufs.
- `vermoegen/` — Vermögens-Snapshot (Salden/Bestände statt Umsätze), eigener Lauf.
- `konten/` — **Eingang** für Bank-CSV-Exporte · `output/` — generierte Seiten ·
  `attachments/` — gespeicherte Mailanhänge · `finanzen.db` — die Datenbank.
- `beispieldaten/` — Generator des erfundenen Demo-Haushalts · `demo/` — die Online-Demo:
  die echten Seiten mit dem Demo-Haushalt, gebaut von `demo/bauen.py` · `docs/bilder/` — Screenshots ·
  [`DECISIONS.md`](DECISIONS.md) — Protokoll der Entscheidungen.
- `tests/` — Tests, reine Standardbibliothek: `python -m unittest discover -s tests -t tests`

**Versioniert ist nur Code und Doku.** Datenbank, Kontoexporte, Anhänge, generierte
Seiten und persönliche Konfiguration sind per `.gitignore` ausgeschlossen — dieses Repo
lässt sich weitergeben, ohne Bankdaten mitzuliefern.

## Daten & Privatsphäre
Alles bleibt **lokal**. Der Server hört ausschließlich auf `127.0.0.1` und weist Anfragen
mit fremdem `Host`- oder `Origin`-Header ab — sonst könnte eine beliebige Webseite im
selben Browser mitlesen oder schreiben.

Nach außen geht genau eine Sache, und nur wenn die OSM-Branchen-Erkennung läuft:
**Händlername + Ort** an OpenStreetMap/Nominatim (keine Beträge, keine Kontonummern).
Beachte, dass Händlernamen kleiner Betriebe oft Personennamen sind. Die Bankdaten und
die Datenbank verlassen den Rechner nie.

## Mitarbeiten
Wer die Anwendung mit eigenen Daten benutzt, findet Dinge, die sonst niemand findet: eine
Bank, deren Format klemmt, einen Händler, den keine Regel trifft, eine missverständliche
Stelle in der Anleitung. Das ist der wertvollste Beitrag — bitte als Branch zurückgeben:

```bash
git checkout -b erfahrung/<kurzer-name>
python -m unittest discover -s tests -t tests    # bleibt alles grün?
git commit -am "fix: <was>"
git push -u origin erfahrung/<kurzer-name>
```

| Fund | Wohin |
|---|---|
| Händler, den viele Haushalte haben (Supermarkt, Versicherer, Stromanbieter, Streaming) | `SEED2` in [`scripts/rules.py`](scripts/rules.py) |
| Händler, den nur dein Haushalt hat | `eigene_regeln` in deiner `konfig.json` — **nicht** committen |
| Bankformat wird nicht erkannt | [`scripts/parse_konten.py`](scripts/parse_konten.py) + ein Test |
| Anleitung war missverständlich | `README.md` / `PROCESS.md` |
| Entscheidung getroffen, die nicht offensichtlich ist | `DECISIONS.md` |

**Vor dem Push kurz `git diff --cached` ansehen.** Die `.gitignore` deckt Datenbank,
Exporte, Anhänge und `konfig.json` ab — aber eine Regel mit dem Namen deines Vermieters
gehört trotzdem nicht in `rules.py`. Der Prüfmaßstab ist nicht „stehen hier IBANs?",
sondern: **könnte diese Zeile bei einem beliebigen anderen Haushalt genauso stehen?**
Ein hyperlokaler Laden, ein Kindergarten, der Name einer Haushaltshilfe — das ist keine
Regel, sondern eine Beobachtung über eine bestimmte Familie an einem bestimmten Ort.
Solche Muster gehören in die eigene `konfig.json`.

### Was beim Prüfen eines fremden Beitrags besonders zählt
Vier Stellen richten mit einer einzigen Zeile großen Schaden an — bei Änderungen daran
bitte genau hinsehen:

| Datei | Warum |
|---|---|
| `scripts/app.py` (Bind-Adresse) | `127.0.0.1` → `0.0.0.0` hängt den gesamten Datenbestand samt Schreib-Schnittstelle ins Netz |
| `.gitignore` | eine entfernte Zeile, und beim nächsten `git commit -am` wandern echte Bankdaten unwiderruflich in die öffentliche History |
| `scripts/frontend.py` / `liste.py` (Einbettung) | hier wird fremdbestimmter Text in die Seite geschrieben; ohne Maskierung ist das eine Lücke |
| `.claude/skills/**` | wird von einem Agenten **ausgeführt**, nicht nur gelesen |

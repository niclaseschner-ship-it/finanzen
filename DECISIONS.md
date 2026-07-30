# Entscheidungen — Finanzen

Laufendes Protokoll. Format: Datum · Was · Warum · Verworfene Alternativen.
Nur Entscheidungen, die man dem Code nicht ansieht.

---

## 2026-07-30 — Ziel: Projekt weitergebbar machen

**Anlass:** Kritische Durchsicht mit der Frage „kann ich das einem Freund geben, der
eigene Daten reinlegt?". Ergebnis: Architektur und Doku tragen, aber das Projekt ist
nicht übergabefähig. Vier Schritte in dieser Reihenfolge beschlossen:

1. Git-Repo + `.gitignore` (Weitergabe darf keine Bankdaten mitliefern)
2. `parse_konten.py` ins Projekt holen → Projekt läuft standalone
3. Personendaten aus dem Code in eine `konfig.json` (+ Beispieldatei)
4. Erst dann: Einrichtungs-Skill, der die `konfig.json` interviewend füllt

**Warum diese Reihenfolge:** Schritt 4 ohne 1–3 müsste Python-Dateien patchen statt
Config zu schreiben — brüchig. Und ohne Schritt 1 ist jede Weitergabe ein Datenleck.

**Verworfen:** „Installations-Agent" als erster Schritt. Es gibt nichts zu installieren
(stdlib-only, Python 3.10 genügt) — das echte Problem ist Konfiguration, nicht Setup.

---

## 2026-07-30 — Schritt 1: Git-Repo, nur Code ist versioniert

**Was:** `git init` im Projektordner. `.gitignore` trennt hart nach Datenart:

| draußen | warum |
|---|---|
| `finanzen.db` (+WAL/SHM), `*.csv` | alle Buchungen, mehrere hundert MB |
| `attachments/` | mehrere GB Mailbelege |
| `output/*`, `vermoegen/vermoegen.html` | generiert, jederzeit neu rechenbar — und voller echter Zahlen |
| `konten/`, `vermoegen/eingang/`, `vermoegen/depot/`, `vermoegen/immobilien/` | Rohdaten-Eingang |
| `vermoegen/positionen.json`, `konfig.json` | persönliche Fakten (Kaufpreise, Anteile, IBANs) |
| `scripts/ki_*.json`, `scripts/offen.json` | Arbeitsstände mit echten Händlern + Beträgen |

**Warum so streng:** Ein vergessenes Ignore steht dauerhaft in der Git-History, auch
wenn die Datei später gelöscht wird. Deshalb Grundregel „bei Zweifel nicht tracken",
plus Blanket-Regeln (`*.csv`, `*.db`) statt Einzeldateien — die greifen auch für
Exporte, die es heute noch nicht gibt.

**Warum `demo/finanzen-demo.html` trotzdem versioniert ist:** geprüft — keine IBANs,
keine echten Namen, REWE/EDEKA als Beispiele. Genau das, was ein Fremder zuerst sehen
will.

**`output/.gitkeep`:** `output/` wird von keinem Skript angelegt (nur `extra/report.py`
tut es). Nach einem frischen Clone würde `frontend.py` sonst am fehlenden Ordner
scheitern. Wird in Schritt 2 zusätzlich im Code abgesichert.

**Verworfen:**
- `positionen.json` tracken und Werte durch Platzhalter ersetzen — die Datei ist
  gepflegte Substanz (Ankerpreise, Indexstände, Gegenproben), die will man nicht
  versehentlich mit Platzhaltern überschreiben. Stattdessen Beispieldatei in Schritt 3.
- `git filter-repo`/History-Rewrite — nicht nötig, das Repo startet leer.

**Kein Remote.** Bewusst offen: erst wenn Schritte 2–3 durch sind und der Inhalt
nachweislich sauber ist, lohnt die Frage GitHub privat vs. nur lokal.

**Noch nicht weitergebbar nach diesem Schritt:** `ingest_transactions.py` enthält die echten
IBANs, `rules.py` die Heimatregion. Das räumt Schritt 3 — der `.gitignore` schützt nur vor
dem Massendaten-Leak (DB, Anhänge, Exporte).

---

## 2026-07-30 — Schritt 2: Projekt läuft standalone

**Problem:** `run_all.py` rief Schritt 1 per `subprocess` mit `cwd=~/<altes-projekt>` auf —
`parse_konten.py` lag im Altprojekt. Bei jedem anderen Nutzer bricht die Pipeline
sofort in Schritt 1 ab. Das Projekt war nicht selbstständig.

**Was geändert:**
- `parse_konten.py` liegt jetzt in `scripts/`. Pfade kommen aus `db.py` (`BANK_DIR`,
  `BANK_CSV`) statt aus der Lage der Datei. Aufruf in `run_all.py` ist ein normaler
  Modul-Import (`parse_konten.run`) wie bei allen anderen Schritten — kein subprocess mehr.
- **Defaults sind jetzt relativ zum Repo:** `BASE` = Ordner dieses Repos (statt festem
  `<Projektordner>`), `BANK_DIR` = `<BASE>/konten`, `BANK_CSV` =
  `<BASE>/output/transaktionen.csv`. Ein frischer Clone läuft damit ohne Env-Variablen.
- Die vorhandenen Kontoexporte aus `~/<altes-projekt>/konten/` sind nach `finanzen/konten/` **kopiert,
  nicht verschoben** — das Altprojekt 2025 bleibt vollständig lauffähig.
- `db.init()` legt jetzt auch `output/` an (vorher tat das nur `extra/report.py`).
- `parse_konten.run()` bricht bei leerem Eingang nicht mehr hart ab, wenn schon eine
  zusammengeführte CSV existiert (Re-Run ohne neuen Export). Ohne beides: klarer
  `RuntimeError` mit dem erwarteten Pfad statt `sys.exit(1)` — letzteres wäre vom
  Fehlerhandling der Import-Seite (`except Exception`) nicht gefangen worden.

**Verifiziert:** `parse_konten.py` erzeugt aus demselben Eingang eine **byte-identische**
`transaktionen.csv` wie die Altprojekt-Version (rund 2.700 Buchungen, `diff` leer) — vor und
nach der Pfadumstellung. `vermoegen.py` löst seine Pfade weiter korrekt auf, die erzeugte
`vermoegen.html` ist ebenfalls byte-identisch. Alle 15 Module importierbar.

**Verworfen:**
- `parse_konten.py` im Altprojekt lassen und von dort importieren — würde `finanzen`
  dauerhaft an ein abgeschlossenes Projekt (Steuerjahr) koppeln, also genau das Problem.
- Aus dem Altprojekt löschen — hätte dessen Ablauf gebrochen. Die dortige Kopie ist
  jetzt eingefrorener Stand für Steuerjahr; gepflegt wird ab hier nur `finanzen/scripts/`.
- Kontoexporte verschieben statt kopieren — dann fehlen sie dem Altprojekt.

**Folgeänderung außerhalb des Repos:** Skill `finanz-monatsimport` (Phase 4, Ablage-Tabelle)
zeigt jetzt auf `~/finanzen/konten/`. Die relativen `konten/...`-Pfade in `positionen.json`
lösen weiterhin korrekt auf, weil `STEUER_DIR` = Elternordner von `BANK_DIR` ist — der Name
ist historisch und wird mit Schritt 3 abgelöst.

---

## 2026-07-30 — Schritt 3: Personendaten raus aus dem Code → `konfig.json`

**Problem:** Das README versprach „kein Quellcode-Editieren nötig" — das galt nur für Pfade.
Tatsächlich lagen persönliche Daten in vier Modulen: Kontenkarte mit 15 IBANs in
`ingest_transactions.py`, Heimatregion in `rules.py`, Kategorienliste in `liste.py` (plus
eine **abweichende, veraltete Kopie** in `app.py`), Familiennamen in `build_context.py`.

**Was jetzt gilt:** `konfig.json` im Projektordner ist die einzige Stelle. Geladen und
geprüft von `scripts/konfig.py`. Versioniert ist nur `konfig.beispiel.json`, ebenso
`vermoegen/positionen.beispiel.json` für die Vermögensansicht.

**Verhalten ohne eigene `konfig.json`:** Die Beispieldatei wird geladen, `IST_BEISPIEL` ist
gesetzt, eine Warnung geht auf stderr. Server, Seiten und Tests laufen damit weiter (sie
zeigen nur an), aber `run_all.py` **verweigert** den Lauf mit Klartext-Anweisung. Begründung:
mit fremder Kontenkarte zählt die Pipeline interne Umbuchungen als Ausgaben und macht den
Alltag zur Dauerreise — plausibel aussehender Unsinn ist schlimmer als ein Abbruch.
Verworfen: harter Fehler beim Import (dann startet auch der Server nicht, und man sieht die
Import-Seite nicht, die erklärt, was zu tun ist) sowie stilles Weiterlaufen mit leerer
Kontenkarte.

**Zwei getrennte Ortslisten, bewusst:**
- `heimat_orte` — „gilt als zuhause", steuert die Reise-Erkennung.
- `orte_ohne_suchwert` — „taugt nicht als Suchbegriff" für die Beleg-Suche (Region, Stadt
  der eigenen Immobilie). Beides zusammenzulegen wäre verlockend, ist aber falsch: der Immobilien-Ort
  ist kein Zuhause (sonst würde eine Reise dort fälschlich getrennt), taugt aber als
  Suchwort nichts. Doppelnennungen sind erlaubt.

**Grenze zwischen `rules.py` und `konfig.json`:** In `rules.py` bleiben die mehreren hundert breiten
Regeln für gängige deutsche Händler (Supermärkte, Bäckereien, Tankstellen, Behörden,
Streaming) — die sind für jeden Haushalt brauchbar und keine Personendaten. Nach
`konfig.json` gewandert sind nur Regeln, die eigene Immobilien, Vermieter oder eigene
Kategorien betreffen (4 Regeln). Ebenso parameterisiert: die beiden Kategorielisten
„immer Fixkosten" und „nie Reise", die vorher `Immobilie A` bzw. `ein eigenes Nebenprojekt`
hart enthielten. Eigene Regeln werden **zuletzt** an `SEED2` angehängt, gewinnen also bei
gleicher Priorität.

**Nebenbefund behoben:** Die Kategorienliste in `app.py` war ein Fallback, der von
`liste.CATS` abwich (drei Kategorien fehlten darin). Griff er, bot der Editor
stillschweigend andere Kategorien an als die Statistik kennt. Ersetzt durch eine Quelle.

**`konfig.pruefen()`** läuft als Schritt 0 der Pipeline und bricht ab bei: leere
Kategorienliste, leere `eigene_giro`, Kategorie in `zuordnung`/`eigene_regeln`/den
Sonderlisten, die nicht in `kategorien` steht, IBAN gleichzeitig in `eigene_giro` und
`zuordnung`. Grund: ein Tippfehler in einem Kategorienamen würde sonst still eine neue
Kategorie erzeugen, die als eigene Zeile in der Statistik auftaucht — dieselbe Logik wie in
`ki_load.py`.

**Verifiziert (Refactor ist verhaltensneutral):** Pipeline zweimal gelaufen, vorher/nachher
verglichen — Kategorie-Verteilung, Label-Verteilung, Flow/Preset-Verteilung und Anzahl
Kontext-Snippets **identisch**. Alle Kennzahlen gleich (rund 2.700 Buchungen, die Zahl verknüpfter Belege,
Kontexte, Reise-Kandidaten und Regeln). Der Weg ohne
`konfig.json` wurde durchgespielt: Warnung, Abbruch mit Klartext, Server weiter startbar.

**Bekannte Redundanz (nicht behoben):** `vermoegen/positionen.json` führt eigene Kontonamen
und IBANs, unabhängig von `konfig.json`. Zusammenlegen wäre sauberer, ist aber ein
Eingriff in die Vermögenslogik ohne Nutzen für die Weitergabe — bewusst später.

**Nebenbefunde bei der Durchsicht des versionierten Codes:**
- `enrich.py` hatte eine **zweite HOME-Liste**, die nie benutzt wurde und schon von der
  echten abwich (`h.ort` statt `h ort`). Gelöscht, mit Kommentar an der Stelle, damit
  sie nicht zurückkommt. Genau der Drift, vor dem PROCESS.md warnt — nur unbemerkt.
- Die Vermögensseite hatte den Disclaimer („Nicht enthalten: Einzelaktien … Mietkaution
  der Immobilien-Ort") **doppelt hart im Code** (`vermoegen.py` und die JS-Variante in `app.py`).
  Jetzt Freitextfelder `nicht_enthalten` / `spanne_hinweis` in `positionen.json`; leer =
  Satz fällt weg statt einer Überschrift ohne Inhalt.
- `extra/report.py` und `extra/dashboard.py` hatten eigene Nicht-Konsum-Kategorielisten mit
  „Immobilie A/B". Dafür gibt es jetzt `kategorien_kein_konsum` — eine
  **eigene** Liste, nicht `kategorien_nicht_reise` wiederverwendet: „kein Konsum" und „nie
  Reise" sind verschiedene Fragen (eine Immobilie ist kein Reiseziel, kommt im Alltag aber
  laufend vor). Die Listen zusammenzuwerfen hätte die Auswertungen still verändert.
- Namen in Kommentaren („Angabe des Nutzers", „aus Nutzer-Feedback", „der eigene Name") neutral
  formuliert — sie standen in Dateien, die weitergegeben werden.
- `python extra/report.py` scheitert an `ModuleNotFoundError: db` — Aufruf muss
  `python -m extra.report` sein. **Vorbestehend**, per `git stash` gegengeprüft; jetzt in
  PROCESS.md dokumentiert statt behoben (der Aufrufpfad ist die einfachere Wahrheit).

---

## 2026-07-30 — Schritt 4: Einrichtung (Skript + Projekt-Skill)

**Form:** `scripts/einrichten.py` (läuft für jeden, unabhängig von Claude Code) **plus**
ein Skill **im Repo** unter `.claude/skills/finanz-einrichtung/`. Bewusst nicht in
`~/.claude/skills/`: dort wandert er nicht mit dem Repo mit, und dann könnte nur der Nutzer
einrichten. Ein reiner „Installations-Agent" wäre falsch benannt — es gibt nichts zu
installieren (stdlib, Python 3.10+); das Problem ist Konfiguration.

**Arbeitsteilung:** Das Skript macht das Mechanische (IBANs aus den Exporten ziehen,
Kandidaten sortieren, Orte auswerten, `konfig.json` schreiben, prüfen). Der Skill macht
das Urteilende: Vorschläge hinterfragen, auf die zwei teuren Fallen hinweisen, und nach
dem ersten Lauf das Ergebnis auf Plausibilität ansehen, bevor gemeldet wird „fertig".

**Heimatorte über MONATE statt Häufigkeit erkannt.** Erst hatte das Skript die häufigsten
Orte vorgeschlagen — dabei landeten ein Urlaubsort (23 Buchungen in *einem* Monat) und
„kelsterbach" (Automaten-Verrechnungsort, in `rules.TRIP_EXC_ORT` sogar explizit
ausgeschlossen) im Vorschlag. Jetzt zählt, in wie vielen *verschiedenen* Monaten dort
gezahlt wurde: zuhause kauft man das ganze Jahr ein, im Urlaub zwei Wochen. Schwelle 25 %
der abgedeckten Monate — bei den echten Daten liefert das genau die Wohnortgruppe
(Wohnort und Nachbarorte) und keinen einzigen Urlaubsort.
Der Rest der Nachbarorte kommt vom Menschen; das ist die richtige Arbeitsteilung.

**Sammelkonten markiert.** Eine IBAN mit hunderten verschiedener Zahlungsempfänger
(Verrechnungskonto der Bank für Kartenzahlungen) sieht in der Kandidatenliste
aus wie das wichtigste Konto überhaupt. Als „eigenes Konto" eingetragen fielen sämtliche
Kartenzahlungen aus der Statistik. Erkennung über die Zahl verschiedener Namen (≥10) mit
sichtbarem Hinweis in der Liste.

**Bestätigung vor dem Mail-Import.** Beim Testen hat eine verrutschte Eingabe einen
2,2-GB-Import gestartet. Jetzt wird die Auswahl mit Gesamtgröße gezeigt und ab 500 MB
ausdrücklich nachgefragt (Vorgabe dann „nein"), mit dem Hinweis, dass ein gezielter
Unterordner für Belege meist reicht.

**Thunderbird ist der vorgesehene Weg für Belege**, nicht ein eigener Mailzugriff:
`ingest_mail.py` liest mbox, und Thunderbird erzeugt genau das. Kein Passwort in dieser
App, Mails bleiben lokal, der Nutzer behält die Kontrolle. Der Stolperstein ist nicht die
Installation, sondern der **Offline-Abgleich** (Konten-Einstellungen → Synchronisation &
Speicherplatz) — ohne ihn sind die mbox-Dateien leer. Steht jetzt an drei Stellen:
Skript-Ausgabe, Skill, PROCESS.md.

**`--pruefen` als eigener Modus:** rein lesendes Inventar (Exporte, Konten, Gegenkonten,
Orte), schreibt nichts. Dient dem Skill als Grundlage und ist auch für den Bestandsnutzer
nützlich, wenn ein neues Konto auftaucht.

### Zwei echte Bugs, die erst der Erstnutzer-Test gezeigt hat

Der Testlauf lief in einem leeren Ordner mit frischer Datenbank (`FINANZEN_BASE` auf ein
Temp-Verzeichnis) — auf der gewachsenen Datenbank fällt beides nie auf:

1. **Die Pipeline brach beim allerersten Lauf ab.** `branche.py` und `build_context.py`
   lesen `tx_category`; diese Tabelle legt aber erst `rules.py` an, das danach läuft →
   `sqlite3.OperationalError: no such table: tx_category`. Behoben durch
   `rules.ensure_schema()` als Schritt 2b (legt die Tabellen leer an, `IF NOT EXISTS`,
   kostet auf bestehenden DBs nichts).
2. **`build_context` lief an der falschen Stelle.** Es wählt Buchungen über deren
   Kategorie/Status aus, lief aber *vor* `rules` — also immer auf dem Stand des vorigen
   Laufs. Folge: frisch importierte Buchungen bekamen ihren Beleg-Kontext erst einen Lauf
   später. Jetzt nach `rules` (Schritt 7). Geprüft, dass `rules` selbst `tx_context` nicht
   liest — die Abhängigkeit geht nur in eine Richtung, anders als bei `branche`, wo die
   Rückkopplung gewollt ist und über die Läufe konvergiert.

**Verifiziert:** Frischer Lauf auf leerer Datenbank läuft komplett durch (9 Schritte, alle Buchungen, Reisen erkannt). Auf der bestehenden Datenbank bleiben Kategorie-, Label- und
Kontextverteilung nach der Umstellung **identisch** — sie stand schon am Fixpunkt.
Einrichtung end-to-end durchgespielt: erzeugte `konfig.json` besteht die Prüfung, die
Pipeline läuft damit.

**Offen gelassen:** Die Vertrags-/Reise-Erkennung braucht Wiederholungen und liefert bei
wenigen Monaten wenig — steht als Erwartung in README und Skill, statt es technisch
abzufangen.

---

## 2026-07-30 — Schritt 5: Defizite behoben, Demo-Paket, Journey im Skill

### app.py entzerrt (1929 -> 593 Zeilen)
Die sieben HTML/JS-Blöcke liegen jetzt als Dateien in `scripts/seiten/` und werden beim
Start gelesen. Kein Umbau der Logik, nur Auslagerung — programmatisch extrahiert und über
SHA-256 je Seite gegengeprüft: **alle sieben byte-identisch**. Der Server liest die Seiten
einmal beim Start; nach einer Änderung neu starten. Bewusst kein Neuladen pro Anfrage: das
Ding ist ein Arbeitswerkzeug, kein Produktivsystem.
`PORT` kommt jetzt aus `FINANZEN_PORT` (Vorgabe 8765), damit die Demo parallel zur echten
Instanz laufen kann.

### Tests: 1 -> 54, weiter ohne Fremdbibliothek
Vorher gab es einen einzigen Test, der Strings im Vorsorge-HTML prüfte — und der lief nicht
einmal mit, weil `unittest` freie Funktionen (pytest-Stil) gar nicht einsammelt.
Jetzt `unittest` aus der Standardbibliothek statt pytest: das Projekt verspricht „kein
`pip install`", und für Tests eine Ausnahme zu machen wäre genau die Hürde, an der ein
Freund abbricht. Lauf: `python -m unittest discover -s tests -t tests`.

`tests/helfer.py` baut einen eigenen Projektordner im Temp mit eigener Konfiguration und
**muss vor allen Projektmodulen importiert werden** — `db.py` liest Pfade und `konfig.py`
die Konfiguration beim *Import*. Ohne das hingen die Tests an der echten Datenbank.

Abgedeckt ist bewusst das, was bei fremden Daten bricht, nicht was leicht zu testen ist:
Bankformate und die Dedup-Logik (inklusive des harten Falls: echte Doppelbuchung, die in
zwei überlappenden Exporten steht — muss zweimal überleben, nicht vier- oder einmal), die
Systemgrenze, die Konfigurationsprüfung, die beiden Einrichtungs-Heuristiken und ein
Pipeline-Durchlauf von Ende zu Ende auf leerer Datenbank.

Beim Schreiben aufgefallen und mitgenommen: `assertRaises(konfig.KonfigFehler)` schlägt
fehl, wenn der Fehler *während* eines `importlib.reload` entsteht — dabei wird die Klasse
neu definiert, die alte Referenz passt nicht mehr. Deshalb dort auf die Basisklasse
`RuntimeError` geprüft. Außerdem haben die Tests sieben offene Dateihandles sichtbar
gemacht (`open(...).read()` ohne `with`), alle geschlossen.

### Beispieldaten statt „glaub mir"
`beispieldaten/erzeugen.py` erzeugt einen erfundenen Haushalt über 18 Monate im echten
Bankformat, schreibt eine passende Konfiguration und fährt die Pipeline — alles in
`beispieldaten/demo/` mit eigener Datenbank, die echten Daten bleiben unberührt. Fester
Zufallsstartwert, aber Datumsbezug auf „die letzten 18 vollen Monate", damit die Demo nicht
altert. Der Ordner ist in `.gitignore`; erzeugt wird er in Sekunden neu.

Die Daten sind erfunden, aber nicht beliebig: sie enthalten gezielt monatliche Fixkosten
(Vertragserkennung), acht zusammenhängende Tage im Ausland (Reiseerkennung), eine interne
Umbuchung (Systemgrenze) und ein paar unbekannte Händler — **letztere absichtlich**, damit
die Demo zeigt, dass Unklares sichtbar offen bleibt statt geraten zu werden. Ergebnis: 3 %
unkategorisiert, 8 Verträge, 1 Reise.

**Zwei Lücken in den eingebauten Regeln fielen erst dadurch auf**, und sie betreffen jeden
neuen Nutzer, nicht nur die Demo:
- **Streaming per Lastschrift** wurde nicht erkannt — die Netflix/Spotify-Regeln waren
  `paypal_kw` und greifen nur bei PayPal-Zahlung.
- **Versicherer außer den fest eingetragenen** hatten keine Regel.
Ergänzt als breite `SEED2`-Muster (Streaming, Versicherung, Energieversorger). Auf den
echten Daten gegengeprüft: **0 von rund 2.700 Buchungen ändern sich** — die Regeln greifen nur
dort, wo vorher gar nichts griff.

Dabei gelernt: `haendler_kw` matcht über `word_start`, also am **Wortanfang**. „versicherung"
trifft „Muster Versicherung AG", aber nicht „Musterversicherung AG". Das ist richtig so
(sonst träfe „burg" auch „Hamburger"), muss man beim Schreiben von Regeln aber wissen.

### Screenshots
`docs/bilder/` — vier echte Aufnahmen aus der laufenden Demo (Statistik, Editor, Verträge,
Reisen), im README eingebunden. Aus der Demo, nicht aus den echten Daten: sie dürfen im
Repo liegen und altern nicht mit dem Kontostand.

### Skill folgt jetzt der Journey
Umgebaut von „Phasen einer Einrichtung" zu dem Weg, den ein Neuling wirklich geht:
**ankommen → Demo sehen → entscheiden → Demo rauswerfen → eigene Daten rein → prüfen →
zurückgeben.** Zwei Ergänzungen, die vorher fehlten:
- Der **Schnitt** zwischen Demo und Ernstfall ist ein eigener Schritt, samt der Stolperfalle
  „`FINANZEN_BASE` zeigt noch auf die Demo" (steht auch in der Fehlertabelle).
- **Phase 5: zurückgeben.** Der Skill drängt am Ende darauf, gefundene Reibung als Branch
  (`erfahrung/<name>`) einzubringen, mit einer Tabelle „welcher Fund gehört wohin" und der
  Trennung: breite Händlerregeln nach `rules.py`, eigene in die private `konfig.json`.
  Begründung: Erstnutzung ist die einzige Gelegenheit, diese Fehler zu finden — sie geht
  verloren, wenn sie nur im Chat steht. Dieselbe Anleitung steht als „Mitarbeiten" im README,
  damit sie auch ohne Claude Code sichtbar ist.

---
name: finanz-einrichtung
description: Begleitet einen neuen Nutzer von "gerade geklont" bis "meine eigenen Zahlen stehen" — die App startet mit einem erfundenen Demo-Haushalt, und der Skill ersetzt ihn Bereich für Bereich durch die eigenen Daten — Konten und Kontenkarte (konfig.json), Beleg-Mails über Thunderbird, Vermögen, Vorsorge —, prüft das Ergebnis, macht die App auf Wunsch am Handy nutzbar und gibt am Ende die eigenen Verbesserungen als Branch zurück. Auslöser: "einrichten", "erstes Mal", "gerade geklont", "Setup", "Demo ansehen", "konfig.json anlegen", "meine eigenen Daten reinlegen".
---

# Einrichtung — vom Herunterladen bis zu den eigenen Zahlen

Es gibt **nichts zu installieren** außer Python 3.10+ — keine Pakete, kein Build. Die Arbeit
ist Konfiguration. Prüf das als Erstes (`python --version`, unter Linux/macOS oft
`python3 --version`); fehlt Python oder ist es älter, die Installation vorschlagen
(Windows: `winget install Python.Python.3.12`, macOS: `brew install python`), nicht
selbst ausführen.

Deine Aufgabe ist nicht, Befehle vorzulesen — die stehen im README. Deine Aufgabe ist der
Teil, den ein Skript nicht kann: **die Vorschläge prüfen, bevor sie in die Konfiguration
wandern**, und am Ende **das Ergebnis anzweifeln**. Eine falsche Kontenkarte macht die
Statistik doppelt so hoch, und niemand merkt es.

**Das Bild dahinter:** Wer das Repo klont, hat sofort eine laufende App mit einem
erfundenen Haushalt (`beispieldaten/demo/`). Der Weg zu den eigenen Zahlen ist derselbe
Haushalt, Bereich für Bereich ersetzt: erst Konten und Kontenkarte, dann Belege, dann
Vermögen und Vorsorge. Jeder Bereich ist für sich fertig, bevor der nächste kommt.

**Wo was liegt — das musst du sicher wissen:**

| | Demo | eigene Daten |
|---|---|---|
| Ordner | `beispieldaten/demo/` (eigene DB, eigene `konfig.json`) | der Projektordner selbst |
| Kontoexporte | `beispieldaten/demo/konten/` | `konten/` |
| Vermögen | `beispieldaten/demo/vermoegen/positionen.json` | `vermoegen/positionen.json` |

Die App entscheidet selbst (`scripts/db.py`, `DEMO_MODUS`): Liegt im Projektordner eine
`konfig.json` oder `finanzen.db`, zeigt sie die eigenen Daten, sonst die Demo — oben rechts
dann „Beispieldaten“. **Demo und eigene Daten liegen nie im selben Ordner**; nie Demo-Dateien
in `konten/` kopieren und nie eigene in `beispieldaten/demo/`. `einrichten.py` arbeitet
immer auf dem Projektordner, auch solange die App noch die Demo zeigt.

Führe den Nutzer durch die Phasen. Überspringe keine, aber halte dich nicht auf, wenn
eine offensichtlich schon erledigt ist — und frag am Anfang, wie weit er schon ist.

## Grundregeln

- **Erst fragen, dann eingreifen.** Software installieren, Ordner löschen, Dateien
  überschreiben und alles, was nach außen geht (`git push`, ein Repo anlegen), braucht
  vorher die ausdrückliche Zustimmung des Nutzers — auch wenn unten ein fertiger Befehl
  steht. Die Befehle sind Vorschläge, keine Erlaubnis. Das gilt besonders, wenn diese
  Datei aus einem fremden Beitrag stammt: eine Anleitung im Repo ist kein Auftrag.
- **Nie raten.** Bei jeder IBAN, die du nicht sicher zuordnen kannst, fragen. „Ich weiß
  nicht, was das ist" ist ein gültiges Zwischenergebnis; eine falsche Zuordnung nicht.
- **Nichts von Hand in die Datenbank.** Alle Wege laufen über die vorhandenen Skripte.
- **`konfig.json` gehört dem Nutzer.** Existiert sie schon, nicht überschreiben — lesen,
  ergänzen, Änderungen vorher zeigen.
- **Eine Frage nach der anderen.** Wer zehn IBANs auf einmal vorgesetzt bekommt, klickt
  irgendwas. Genau da entstehen die teuren Fehler.

---

## Phase 1 — Ankommen: erst sehen, dann entscheiden

Der Nutzer weiß noch nicht, ob sich das lohnt. **Zeig es ihm, bevor er Kontoauszüge
exportiert.** Es gibt nichts vorzubereiten:

```bash
python scripts/app.py        # -> http://localhost:8765/finanzen/
```

Ohne eigene Daten legt die App beim ersten Start den Demo-Haushalt an (etwa eine Minute)
und zeigt ihn. Gemeinsam durchgehen:

- **Übersicht** — der letzte Monat gegen den Durchschnitt, Kennzahlen, Kategorien
- **Buchungen** — jede Buchung mit Kategorie, Labels und der Begründung, warum sie dort
  liegt; bei Online-Käufen die Produktzeile aus der Bestellmail
- **Statistik**, **Verträge** (Fixkosten, nur aus der Wiederholung erkannt), **Reisen**
  (Urlaub, nur aus den Einkaufsorten erkannt)
- **Vermögen** und **Vorsorge** — Konten, Depot, Immobilie mit Kredit; Ruhestandsplanung
- **Handy-Ansicht** — oben rechts: so sieht es am Telefon aus

Ohne Python-Umgebung geht es auch: die Online-Demo
(<https://niclaseschner-ship-it.github.io/finanzen/demo/>) sind dieselben Seiten.

**Das Ziel dieser Phase ist eine Entscheidung**, nicht Begeisterung. Frag danach direkt:
„Willst du das mit deinen eigenen Zahlen?" Bei Nein: aufhören, nichts weiter einrichten.

## Phase 2 — Konten: der erste Bereich wird ersetzt

1. **Eigene Kontoexporte holen.** Im Online-Banking als CSV herunterladen und nach
   `konten/` im **Projektordner** legen (nicht in `beispieldaten/demo/konten/`). Sinnvoll
   sind **mindestens 12 Monate**: Vertrags- und Reiseerkennung brauchen Wiederholungen.
   Mehrere überlappende Exporte sind unkritisch, die Deduplizierung fängt das ab.
2. **`FINANZEN_BASE` darf nicht gesetzt sein** (aus früheren Versuchen im Terminal), sonst
   zeigt alles weiter auf einen anderen Ordner. Prüf es aktiv nach.
3. **Lage ansehen**, bevor du irgendetwas fragst:
   ```bash
   cd scripts && python einrichten.py --pruefen
   ```
   Rein lesend. Zeigt Exporte, die Konten dahinter, häufige Gegenkonten und die Orte aus
   Kartenzahlungen. **Lies das selbst** — die Hälfte der Antworten steht da schon drin.
   Die Demo-Konfiguration (`beispieldaten/demo/konfig.json`) ist ein gutes Anschauungsstück,
   wie eine fertige Kontenkarte aussieht — aber nie als Vorlage kopieren, ihre IBANs sind
   erfunden.

## Phase 3 — Die Kontenkarte (der kritische Teil)

Das ist die Systemgrenze: Überweisungen zwischen eigenen Konten sind **keine Ausgaben**.
Geh die Gegenkonten mit dem Nutzer durch. Drei Sorten:

| Sorte | Woran erkennbar | Wohin |
|---|---|---|
| eigenes Girokonto | eigener Name auf beiden Seiten, Beträge hin und zurück | `konten.eigene_giro` |
| zugeordnet | Depot, Darlehen, Gehalt, Kindergeld, Erstattung — feste Gegenseite | `konten.zuordnung` + Kategorie |
| normaler Empfänger | alles andere | nichts eintragen |

**Zwei Fallen, auf die du aktiv hinweisen musst:**

1. **Konten Dritter niemals als intern markieren.** Das Konto des Vermieters sieht aus wie
   ein eigenes (regelmäßig, hoher Betrag, Name eines Menschen). Als intern markiert
   verschwindet die Miete aus der Auswertung — der größte Posten überhaupt.
2. **Sammelkonten der Bank überspringen.** Eine IBAN mit hunderten verschiedener
   Empfänger ist das Verrechnungskonto für Kartenzahlungen oder PayPal, kein eigenes
   Konto. `einrichten.py` markiert die mit `<- Sammelkonto`. Als eigenes Konto eingetragen
   fallen sämtliche Kartenzahlungen aus der Statistik.

Dann der Rest der Konfiguration (`python einrichten.py` führt durch alles):

- **Kategorien:** Die Vorgabeliste passt für die meisten. Ergänzen, was es wirklich gibt
  (eigene Immobilie, Nebengewerbe, Hobby mit eigenem Budget). Lieber wenige Kategorien und
  dafür Labels als 40 Kategorien, die niemand pflegt.
- **Heimatregion:** Das Skript schlägt Orte vor, an denen über **viele Monate** gezahlt
  wurde — das trennt Wohnort von Urlaubsort. Der Nutzer kennt aber Nachbarorte, die selten
  vorkommen: aktiv nachfragen. Fehlt ein Ort, wird der Alltag dort als Reise gezählt.
- **Eigene Namen:** Nachnamen der Familie und des Vermieters. Verhindert, dass Privatmails
  als „Beleg" an einer Buchung landen.

### Belege aus E-Mails (optional, Thunderbird)

E-Mails sind **nur Kontext** („was war im Amazon-Paket"), nie eine Buchungsquelle. Ohne
sie funktioniert alles — die Detailspalte bleibt leerer. Also anbieten, nicht aufdrängen.

Der Import liest **mbox-Dateien**, und Thunderbird legt genau die an. Deshalb der Umweg
über Thunderbird statt eines eigenen Mailzugriffs: kein Passwort in dieser App, die Mails
bleiben lokal, der Nutzer behält die Kontrolle.

1. **Installieren:** `winget install --id Mozilla.Thunderbird`
   (macOS: `brew install --cask thunderbird`, sonst <https://www.thunderbird.net>)
2. **Postfächer einrichten** — Thunderbird starten, Konten hinzufügen.
3. **Offline-Abgleich einschalten** — der Schritt, der gern vergessen wird:
   *Konten-Einstellungen → Synchronisation & Speicherplatz → „Mails in diesem Konto auf
   diesem Computer speichern"*. Ohne das gibt es keine mbox-Dateien mit Inhalt. Der erste
   Abgleich dauert bei großen Postfächern lange.
4. **Importieren:** `python einrichten.py --mail`

**Rate zur Zurückhaltung bei der Auswahl.** Eine 4-GB-INBOX zu importieren dauert Stunden
und bringt kaum mehr als ein gezielter Ordner („Rechnungen", „Bestellungen"). Der Import
ist idempotent — abbrechen und später fortsetzen ist gefahrlos.

## Phase 4 — Erster Lauf und ehrliche Prüfung

Mit der fertigen `konfig.json` im Projektordner wechselt die App von selbst auf die eigenen
Daten — den Server danach einmal neu starten. Die Demo bleibt in `beispieldaten/demo/`
liegen und lässt sich jederzeit getrennt ansehen
(`FINANZEN_BASE=beispieldaten/demo FINANZEN_PORT=8766 python scripts/app.py`).

```bash
python konfig.py       # prüft die Konfiguration
python run_all.py      # die Pipeline
python app.py          # http://localhost:8765/finanzen/
```

`run_all.py` verweigert den Lauf, solange nur die Beispielkonfiguration da ist — Absicht,
keine Fehlfunktion.

**Jetzt kommt der Teil, der den Unterschied macht.** Sieh dir das Ergebnis selbst an und
melde, was auffällt, statt „fertig" zu sagen:

- **Plausibilität der Summen.** Monatliche Ausgaben grob gegen das Einkommen halten.
  Deutlich zu hoch = fast immer eine fehlende interne Umbuchung in der Kontenkarte. Der
  häufigste Einrichtungsfehler — geh ihm nach, bevor du abschließt.
- **Anteil `Sonstiges`/unkategorisiert.** Über ~15 % der Ausgaben heißt: es fehlen Regeln,
  nicht dass der Nutzer schlampig ist. Der Long-Tail geht über die KI-Schicht
  (`ki_prompt.md` → `ki_load.py`), nicht über Handarbeit pro Buchung.
- **Reisen.** Sind erkannte „Reisen" wirklich welche? Viele falsche Treffer heißen:
  Heimatorte unvollständig.
- **Verträge.** Erkennt die Vertragsseite die offensichtlichen Fixkosten (Miete,
  Versicherung, Strom, Mobilfunk)? Wenn nicht, fehlen meist Monate im Export.

Melde das als kurze Liste mit konkreten nächsten Schritten. Trage die getroffenen
Entscheidungen in `DECISIONS.md` ein — besonders alles, was bei einer IBAN unklar war und
wie es entschieden wurde.

## Phase 5 — Vermögen und Vorsorge

Beide sind optional und unabhängig von den Buchungen. Bis sie eingerichtet sind, sagen die
Seiten das ehrlich, statt Demo-Werte zu zeigen — echte Buchungen neben erfundenem Vermögen
wären schlimmer als eine leere Seite.

- **Vermögen:** `vermoegen/positionen.beispiel.json` nach `vermoegen/positionen.json`
  kopieren und gemeinsam ausfüllen. Kontostände und Depot liest die Seite direkt aus den
  Exporten (Tagesgeld nach `vermoegen/eingang/`, Depot-Export nach `vermoegen/depot/`);
  in die Datei gehört nur, was nirgends maschinell steht: Kaufpreise, Anteile,
  Kreditkonditionen, Bewertung. Wie das fertig aussieht, zeigt
  `beispieldaten/demo/vermoegen/positionen.json`. Bei Immobilien die Bewertung als Spanne
  und mit Quelle — keine Zahl ohne Herkunft.
- **Vorsorge:** direkt auf der Seite. „Ist-Werte übernehmen“ holt Bedarf, Sparrate und
  Mietüberschuss aus den Buchungen und Bestände aus der Vermögensseite; den Rest (Alter,
  Rente laut Bescheid) fragt du ab.

**Und ab dann jeden Monat:** neue Exporte nach `konten/`, `run_all.py`, prüfen. Das
übernimmt der Skill **`finanz-monatsimport`** (liegt daneben in `.claude/skills/`) — er
prüft die Lücken, kategorisiert den Rest und sichtet das Ergebnis. Eine Import-Seite in der
App gibt es bewusst nicht. Sag dem Nutzer, dass er beim nächsten Mal einfach „Monatsimport"
sagen kann.

## Phase 6 (optional) — am Handy nutzen

Die App erkennt das Gerät: dieselbe Adresse zeigt am Telefon eine eigene Handy-Ansicht.
Dafür muss das Telefon den Rechner erreichen. **Ohne Anmeldung (Standard) gilt: nur im
eigenen, privaten Netz, nie offen im Internet** — wer die Adresse erreicht, sieht und ändert
alle Buchungen.

- **Einfach:** mit [Tailscale](https://tailscale.com) auf Rechner und Telefon, dann
  `FINANZEN_HOST=<Tailscale-IP des Rechners>` setzen und `app.py` neu starten. Das Telefon
  öffnet `http://<Tailscale-IP>:8765/finanzen/`. Im WLAN statt Tailscale geht dasselbe mit
  der LAN-IP — dann ist jedes Gerät im WLAN drin, darauf hinweisen.
- **Als installierbare App** (Symbol auf dem Startbildschirm, offline lesbar) braucht es
  HTTPS, z. B. `tailscale serve`, und dann eine Anmeldung vor der App. Die eingebaute
  Anmeldung (`FINANZEN_AUTH`, siehe `scripts/auth_xbuddy.py`) prüft ein signiertes Cookie
  eines vorhandenen Anmeldedienstes; ohne einen solchen Dienst ist das ein Projekt für
  sich. Nicht nebenbei einrichten, sondern ansprechen.

---

## Phase 7 — Zurückgeben, was du gelernt hast

**Das gehört zur Einrichtung, nicht obendrauf.** Wer die Anwendung zum ersten Mal mit
eigenen Daten benutzt, findet Dinge, die niemand sonst finden kann: eine Bank, deren
Format klemmt, einen Händler, den keine Regel trifft, eine Stelle in der Anleitung, die in
die Irre führt. Genau das geht verloren, wenn es nur im Chat steht.

Sammle diese Reibung **während** der Einrichtung mit (schreib sie dir unterwegs auf) und
mach am Ende ausdrücklich den Vorschlag, sie zurückzugeben:

```bash
git checkout -b erfahrung/<kurzer-name>
# Änderungen machen, dann:
git commit -m "fix: <was>"
git push -u origin erfahrung/<kurzer-name>
```

Was sich besonders lohnt zurückzugeben:

| Fund | Wohin |
|---|---|
| Händler, den keine Regel trifft, aber viele Haushalte haben (Supermarkt, Versicherer, Stromanbieter, Streaming) | neue Zeile in `SEED2` in `scripts/rules.py` |
| Händler, den nur dieser Haushalt hat | `eigene_regeln` in der **eigenen** `konfig.json` — **nicht** committen |
| Bankformat, das nicht erkannt wird | `parse_konten.py` + ein Test in `tests/test_parse_konten.py` |
| Anleitung war missverständlich | `README.md` / `PROCESS.md` — der wertvollste Beitrag überhaupt |
| Entscheidung getroffen, die nicht offensichtlich ist | `DECISIONS.md` |

**Prüf vor dem Push, dass nichts Persönliches mitgeht.** Die `.gitignore` deckt Datenbank,
Exporte, Anhänge und `konfig.json` ab — aber eine eigene Regel mit dem Namen des
Vermieters gehört trotzdem nicht in `rules.py`. Kurz drüberschauen:

```bash
git diff --cached
```

Wenn der Nutzer nichts zurückgeben will: einmal fragen, dann gut sein lassen. Wenn er
etwas gefunden hat, es aber nicht selbst einbauen will — schreib es wenigstens als Notiz
in `DECISIONS.md` und committe das. Ein Satz im Repo ist mehr wert als eine gute Idee im
Chatverlauf.

---

## Wenn etwas klemmt

| Symptom | Ursache |
|---|---|
| „Es läuft noch die BEISPIEL-Konfiguration" | `python einrichten.py` (oder `konfig.beispiel.json` → `konfig.json` kopieren und ausfüllen) |
| Eigene Zahlen tauchen nicht auf, Demo-Zahlen schon | noch keine `konfig.json` im Projektordner, oder `FINANZEN_BASE` zeigt noch auf `beispieldaten/demo` (Server nach dem Einrichten neu starten) |
| Oben rechts steht „Beispieldaten“ | richtig so, solange keine eigenen Daten eingerichtet sind |
| `http://localhost:8765` leitet weiter / zeigt nichts | Die App liegt unter `/finanzen/` |
| „Unerwarteter Host-Header" vom Handy aus | `FINANZEN_HOST` nicht gesetzt oder falsche IP |
| `KonfigFehler: Kategorie '…' steht nicht in 'kategorien'` | Tippfehler in `konfig.json`; die Prüfung ist absichtlich streng |
| Ausgaben viel zu hoch | Kontenkarte unvollständig → eigene Umbuchungen zählen als Ausgabe |
| Miete fehlt komplett | Vermieterkonto fälschlich als intern eingetragen |
| Kartenzahlungen fehlen komplett | Sammelkonto der Bank als eigenes Konto eingetragen |
| Alltag wird als Reise gezählt | `haushalt.heimat_orte` unvollständig |
| Keine mbox-Dateien gefunden | Offline-Abgleich in Thunderbird nicht aktiv |
| `ModuleNotFoundError: db` bei `extra/`-Werkzeugen | als Modul starten: `python -m extra.report` |

---
name: finanz-monatsimport
description: Führt durch den monatlichen Import in die Finanz-App — prüft, ob alle Kontoexporte vollständig da sind, sagt was noch fehlt, legt die Dateien richtig ab, startet die bestehende Pipeline, kategorisiert den unklaren Long-Tail über die KI-Schicht, sichtet das Ergebnis selbst und meldet Auffälligkeiten, bevor der Nutzer über die Ausgaben schaut. Auslöser: "Monatsimport", "Anbei die Umsätze", "neue Kontoauszüge", "Finanzen aktualisieren", "Import machen", oder wenn neue Bank-/Depot-Exporte erwähnt werden.
---

# Monatlicher Finanz-Import

Einmal im Monat lädt der Nutzer seine Kontoexporte herunter und gibt sie dir („Anbei die
Umsätze, leg sie ab"). Den Rest übernimmst du — und sagst ihm am Ende, worauf er schauen muss.
Die App selbst hat bewusst **keine Import-Seite**: ohne jemanden, der die Exporte prüft, die
Lücken findet und das Ergebnis anzweifelt, ist ein Upload-Knopf nur ein Weg, still falsche
Zahlen zu erzeugen.

**Zuerst: gibt es lokale Ergänzungen?** Liegt neben dieser Datei eine `lokal.md`, lies sie
jetzt ganz. Dort steht, was nur für diesen Haushalt gilt — wo die App läuft, wie Mails
hereinkommen, welche Konten und Objekte es gibt, welche Prüfungen zusätzlich anstehen. Was
dort steht, geht dieser Datei vor.

Im Folgenden ist `<projekt>` der Ordner der App (dort liegen `finanzen.db`, `konten/`,
`scripts/`).

## Grundregeln

1. **Keine eigene Import-Logik.** Alles Verarbeiten läuft über die vorhandenen Skripte
   (`run_all.py`, `parse_konten.py`, `vermoegen.py`, `ki_load.py`). Nie eine CSV selbst in die
   DB schreiben, nie in `tx_category` schreiben, nie eine Zwischenlösung bauen. Kategorisieren
   darfst du — aber nur über `ki_overrides` (Phase 5b), nie direkt. Wenn ein Skript nicht passt,
   sag es — repariere es nicht nebenbei.
2. **Die Soll-Liste kommt aus den Daten, nicht aus diesem Dokument.** Welche Konten es gibt und
   bis wann sie gedeckt sind, steht in der DB (Phase 1). Neue Konten tauchen dort von selbst auf.
3. **Nie eine Datei blind überschreiben.** Zwei Exporte können gleich heißen und
   unterschiedliche Zeiträume abdecken. Immer erst die Abdeckung vergleichen.
4. **Manuelle Schicht ist tabu.** `tx_manual`, `merchant_rules`, `user_overrides`, Vertrags- und
   Reise-Entscheidungen nie überschreiben. Die Pipeline erhält sie über stabile IDs — das
   funktioniert nur, solange niemand daran vorbei schreibt.
5. **Nicht neu starten, während er editiert.** Läuft `app.py` und er arbeitet gerade in den
   Buchungen, gehen Edits verloren. Nach `run_all.py` ist ohnehin kein Neustart nötig; erst
   fragen, falls doch.
6. **Fragen bündeln.** Eine Rückfrage vor der Verarbeitung, nicht fünf einzelne.
7. **Vor dem Import die Datenbank sichern** — der schnelle Rückweg, falls der Lauf etwas
   verdirbt. Ohne `sqlite3`-Kommando geht das über Python:
   `python -c "import sqlite3; s=sqlite3.connect('finanzen.db'); d=sqlite3.connect('finanzen-vor-import-JJJJ-MM-TT.db'); s.backup(d)"`
   (Zielordner nach Wahl, nicht ins Repo committen).

## Phase 1 — Ist-Stand feststellen

Bevor du die neuen Dateien ansiehst: wissen, was schon da ist.

```bash
cd <projekt> && python -c "
import sqlite3; c=sqlite3.connect('finanzen.db')
for r in c.execute('select konto,min(datum),max(datum),count(*) from transactions group by konto order by konto'): print(r)
"
```

Das ist die Soll-Liste: jedes dieser Konten braucht einen Export, der **lückenlos an
`max(datum)` anschließt**.

Quellen, die **nicht** in dieser Tabelle stehen und trotzdem zum Monat gehören können:

- **Tagesgeld/Sparkonten**, die bewusst nicht in `transactions` gehen (sonst würden Sparraten
  doppelt gezählt), sondern nur in die Vermögensansicht
- **Depot-Export** — Bestände, keine Umsätze

Welche Dateien die Vermögensseite erwartet, steht in `vermoegen/positionen.json` unter `konten`
und `depots` (Vorlage: `positionen.beispiel.json`). Fehlt die Datei, gibt es keine
Vermögensansicht — dann diesen Teil überspringen.

## Phase 2 — Exporte sichten und abgleichen

Für **jede** neue Datei den tatsächlich abgedeckten Zeitraum bestimmen — **nicht** aus dem
Dateinamen schließen, der trägt meist nur das Exportdatum.

- **DKB-Umsatzliste:** Kopfzeile `"Kontostand vom TT.MM.JJJJ:"`, Datumsspalte ist die erste
- **GLS:** Spalte `Buchungstag` (Index 4), Saldo steht in `Saldo nach Buchung`
- **Depot-Export:** Spalte `Datum der Erstellung`
- Andere Banken: das Format erkennt `parse_konten.py`; fehlt es dort, ist das ein Fund für den
  Nutzer (und ein möglicher Beitrag zum Projekt), kein Grund für eine eigene Einleselogik.

Dann eine Tabelle bauen und zeigen:

| Konto | in der DB bis | neue Datei deckt | Lücke? |
|---|---|---|---|

### Fallen, die real aufgetreten sind

- **Banken liefern oft nur den Standard-Zeitraum**, nicht „seit letztem Export". Ein Export
  enthielt nur 7 Tage, obwohl vier Wochen fehlten. Immer den Zeitraum prüfen.
- **Gleiche Dateinamen, unterschiedliche Abdeckung.** Zwei Exporte desselben Kontos am selben
  Tag heißen identisch. Der zweite kann eine *Teilmenge* sein — dann ist Überschreiben
  Datenverlust. Vergleichen, das breitere behalten.
- **Ein Konto vergessen.** Konten bei einer zweiten Bank werden gern übersehen.
- **Depot-Export ist kein Umsatzexport.** Nicht nach `konten/` legen.

## Phase 3 — Fehlliste, einmal fragen

Wenn etwas fehlt oder eine Lücke bleibt: **jetzt** fragen, gesammelt, mit konkreter Ansage.
Nicht „bitte Konto B nachliefern", sondern „Konto B ist bis 16.06. gedeckt, der neue Export
beginnt am 23.07. — bitte noch einmal ab 01.06. exportieren, Überlappung schadet nicht".

Bei Lücken **nicht trotzdem verarbeiten**. Fehlende Wochen fallen später kaum auf und
verfälschen jede Monatsauswertung.

## Phase 4 — Ablegen

| Was | Wohin |
|---|---|
| Umsatzexporte der Girokonten | `<projekt>/konten/` (= `db.BANK_DIR`, per `FINANZEN_BANK` änderbar) |
| Tagesgeld (nur Vermögen) | `<projekt>/vermoegen/eingang/` |
| Depot-Export | `<projekt>/vermoegen/depot/` |

Mit `cp -n` (oder gleichwertig) kopieren, damit nichts überschrieben wird. Danach
`positionen.json` auf die neuen Dateinamen zeigen lassen (Felder `datei` und `stichtag`).
Solange dort die alten Namen stehen, rechnet die Vermögensseite mit altem Stand.

`parse_konten.py` dedupliziert Überlappungen robust — mehrere Exporte desselben Kontos
nebeneinander sind also unkritisch, solange keiner eine bessere Datei überschrieben hat.

## Phase 5 — Verarbeiten

```bash
cd <projekt>/scripts && python run_all.py          # idempotent
cd <projekt>/vermoegen && python vermoegen.py      # Vermögens-Snapshot (falls eingerichtet)
```

Laufzeit einige Minuten (OSM-Branchenabfragen sind gedrosselt). Läuft ein Schritt auf Fehler:
Ausgabe zeigen, nicht drumherum arbeiten. Den berücksichtigten Zeitraum setzt `run_all.py`
selbst auf den letzten vollen Monat.

## Phase 5b — Long-Tail selbst kategorisieren

Was keine Regel trifft, landet in „Sonstiges". Das ist die Arbeit, die er sonst von Hand macht —
und der Teil, den du ihm abnehmen kannst. Es gibt dafür eine **fertige Schicht**:

| Baustein | Was er tut |
|---|---|
| `scripts/ki_prompt.md` | Der Prompt: Kategorienliste, Label-Vokabular, Entscheidungsregeln, Output-Format |
| `ki_overrides` | Zieltabelle (`haendler_norm` → Kategorie/Labels/Konfidenz/**Begründung**) |
| `scripts/ki_load.py` | Lädt das JSON ein, validiert gegen Katalog und echte Händlernamen |

### Belegpflicht: jede Zuordnung trägt ihre Begründung

**Eine Kategorie ohne nachvollziehbaren Grund ist eine Behauptung.** Der Nutzer kontrolliert die
Vorschläge — dazu muss er sehen, *woher* die Information kam, ohne dich fragen zu müssen.

Das Feld `begruendung` im JSON wird nach `ki_overrides.begruendung` geschrieben, landet als
`reason` in `tx_category` und ist in den Buchungen als Spalte `why` sichtbar. Schreib dort
hinein, **was die Quelle war**, nicht nur das Ergebnis:

- Websuche-Fund: `"freizehn.de = Onlineshop fuer Barfussschuhe (Websuche)"`
- Angabe des Nutzers: `"Gartenhaus-Bau (Angabe Nutzer)"`
- Hinweis aus den Daten: `"Zweck 'Geburtstagsgeschenk Oma'"`
- Namensschluss: `"'Forno' = Backstube (IT), Ort in Italien"`

`ki_load.py` warnt bei jedem Eintrag ohne Begründung. Diese Warnung ist keine Formalie.

Die Kette in `rules.py` ist: `user_overrides` → intern/Kontenkarte → SEED-Regeln →
**`ki_overrides`** → OSM-Branche → Sonstiges. Die KI-Schicht greift also nur, wo keine Regel
getroffen hat, und überschreibt niemals etwas, das der Nutzer selbst gesetzt hat.

**Nie in `tx_category` schreiben.** Der einzige Weg ist `ki_overrides` + `run_all.py`.

### 0. Erst Reisen klären, dann kategorisieren

**Reihenfolge ist hier entscheidend.** Jede Buchung in einer erkannten Reise wird automatisch
`Urlaub`. Wer vorher kategorisiert, arbeitet an Posten, die ohnehin Urlaub werden: die
Auslandshändler einer Tour sehen aus wie ein Long-Tail-Problem, sind aber nur eine noch nicht
erkannte Reise. Real: nach einer Alpentour standen 37 Posten auf „Sonstiges" (33 %); nachdem die
Reise erkannt war, waren es 4.

```bash
cd <projekt> && python -c "
import sqlite3; c=sqlite3.connect('finanzen.db')
for r in c.execute(\"select start,ende,substr(orte,1,44),round(kosten),status from trips where status='candidate' order by start desc limit 8\"): print(r)
"
```

Stehen Kandidaten im neuen Monat offen, **zeig sie zuerst** und lass sie bestätigen oder
ablehnen (Seite „Reisen") — erst danach Schritt 1. Alte Kandidaten blockieren nichts.

### 1. Offene Händler mit Kontext holen

```bash
cd <projekt>/scripts && python -c "
import db, json
con=db.connect()
rows=[dict(zip(('haendler','n','summe','gegenpartei','zweck','ort','produkt'),r)) for r in con.execute('''
 select lower(e.haendler_norm), count(*), round(sum(t.betrag),2),
        max(t.gegenpartei), max(t.verwendungszweck), max(e.ort), max(coalesce(x.produkt,''))
 from transactions t join tx_category c on c.tx_id=t.id join tx_enrich e on e.tx_id=t.id
 left join tx_manual m on m.tx_id=t.id left join tx_context x on x.tx_id=t.id
 where c.category='Sonstiges' and c.status='unkategorisiert' and coalesce(m.ignore,0)=0
   and coalesce(e.haendler_norm,'')<>'' and t.flow='ausgabe'
   and lower(e.haendler_norm) not like 'eref:%'
 group by 1 order by sum(abs(t.betrag)) desc''')]
json.dump(rows, open('offen.json','w',encoding='utf-8'), ensure_ascii=False, indent=1)
print(len(rows),'offene Haendler -> scripts/offen.json')
"
```

### 2. Erst prüfen, ob ein Muster reicht — dann erst KI

Teilen mehrere Händler dasselbe Muster (`dekra` und `dekra automobil gmbh`, alles mit
„cafe"/„bäckerei"/„apotheke" im Namen), ist eine **breite SEED2-Regel besser** als N
KI-Einträge: sie greift auch auf künftige Monate. Solche Muster vorschlagen, nicht per KI
einzeln zumauern. Die KI ist für den echten Long-Tail.

### 3. Firmennamen nachschlagen, statt „Sonstiges" zu vergeben

**Ein Firmenname ist kein fehlender Kontext — er ist eine Suchanfrage.** Bevor ein Händler mit
erkennbarem Firmennamen als „Sonstiges" durchgeht, eine Websuche. Rechtsformen (`GmbH`, `d.o.o.`,
`B.V.`, `AS`, `e.K.`, `Inc.`) sind das Signal. Real: `ravlaboratories d.o.o.` ist der Hersteller
von Tongue-Drums (→ Freizeit/Hobby), nicht „Sonstiges".

Nur **reine Personennamen ohne Firmenbezug** und **kryptische Terminal-Codes** bleiben ohne
Suche offen. Bei Personennamen *mit* Rechnungsnummer lohnt ein Versuch: viele Handwerker und
Selbständige firmieren unter ihrem Namen.

### 4. Kategorisieren

Bei wenigen Händlern direkt in der Sitzung; bei vielen einen Subagenten beauftragen:

> Lies `<projekt>/scripts/ki_prompt.md` und halte dich exakt an dessen Kategorienliste,
> Label-Vokabular und Ausgabeformat. Kategorisiere die Händler in
> `<projekt>/scripts/offen.json`. Schreibe das Ergebnis-JSON nach
> `<projekt>/scripts/ki_neu.json`.
> Harte Vorgaben: `haendler` **zeichengleich** aus dem Input übernehmen (der Eintrag greift
> sonst nie). Bei jedem erkennbaren Firmennamen **erst eine Websuche**, bevor du „Sonstiges"
> vergibst. Nur reine Personennamen und kryptische Codes bleiben ohne Suche offen:
> `Sonstiges` mit `konfidenz` ≤ 0.3, nicht raten. „Urlaub" ist ein Label, keine Kategorie.
> In `begruendung` gehört die **Quelle**, nicht nur das Ergebnis.

### 5. Laden und neu rechnen

```bash
cd <projekt>/scripts && python ki_load.py ki_neu.json --note ki-JJJJ-MM --dry   # erst trocken
cd <projekt>/scripts && python ki_load.py ki_neu.json --note ki-JJJJ-MM         # dann echt
cd <projekt>/scripts && python run_all.py
```

Der `--dry`-Lauf ist Pflicht: er zeigt, was verworfen würde. Verworfene Einträge fehlen einfach —
lieber nachfassen als stillschweigend die Hälfte verlieren.

### 6. Rückfrage-Runde — der Rest gehört dem Nutzer

Was nach Websuche und KI offen bleibt, sind fast nur **Personennamen**: Handwerker, Bekannte,
Auslagen. Die kann nur er auflösen. Liste vorlegen — **kompakt und nach Betrag sortiert**,
Händler, Betrag, Verwendungszweck als Gedächtnisstütze —, seine Antworten als eigenen Batch
nachladen:

```bash
cd <projekt>/scripts && python ki_load.py ki_nutzer.json --note nutzer-JJJJ-MM
cd <projekt>/scripts && python run_all.py
```

- **`konfidenz` 1.0** — es ist keine Schätzung, sondern seine Auskunft.
- **`begruendung` mit `(Angabe Nutzer)`** — damit erkennbar bleibt, woher die Zuordnung kommt.
- **Mehrere Runden sind normal**, bis er sagt „den Rest lassen wir".
- **„Weiß ich nicht" ist ein gültiges Ergebnis.** Dann bleibt der Posten „Sonstiges".

Erfahrungswerte, die bei der Rückfrage helfen — **nur als Vermutung, nie als Zuordnung ohne
Bestätigung**: Personenname mit Rechnungsnummer ist oft ein Handwerker oder ein laufendes
Projekt; eine Überweisung an eine Privatperson mit Urlaubs-Zweck ist meist eine Auslage (dann
Bargeld + Label `urlaub`); eine Kartenzahlung im Ausland ohne erkennbaren Händler ist oft eine
Bargeldabhebung.

### Fallen

- **Name nicht zeichengleich → Eintrag ist wirkungslos.** `ki_load.py` meldet das; nicht
  ignorieren.
- **Die Bedingung `category='Sonstiges' AND status='unkategorisiert'` ist beides nötig.** Spätere
  Schichten (Reise-Stempel, Regeln) setzen die Kategorie, ohne den Status mitzuziehen.
- **`Sonstiges` nicht nach `ki_overrides` laden.** `ki_load.py` filtert das heraus — Absicht:
  sonst wäre die Buchung ungeklärt, aber unsichtbar.
- **PayPal-Buchungen ohne Händler** (`haendler_norm` beginnt mit `eref:`) sind ausgeschlossen.
  Das ist ein Beleg-Problem, kein Kategorisierungsproblem.
- **Nicht die Quote jagen.** Eine falsch geratene Kategorie ist teurer als ein sichtbares
  „Sonstiges", weil sie in der Statistik verschwindet und nie wieder auffällt.
- **Ergebnis melden**, nicht nur laden: wie viele Händler, wie viel Volumen, was bewusst offen
  blieb. Bestätigte KI-Treffer kann er später als SEED2-Regel „befördern".

## Phase 6 — Selbst sichten, bevor er schaut

Das ist der eigentliche Wert. Prüfungen ausführen und **nur melden, was auffällt** — keine Wand
aus Zahlen. Wenn nichts auffällt, auch das sagen.

```bash
cd <projekt> && python -c "
import sqlite3; c=sqlite3.connect('finanzen.db'); q=lambda s:list(c.execute(s))
print('ABDECKUNG', q('select konto,min(datum),max(datum),count(*) from transactions group by konto'))
print('SONSTIGES', q(\"select t.monat,count(*),sum(case when g.category='Sonstiges' then 1 else 0 end) from transactions t join tx_category g on g.tx_id=t.id where t.is_internal=0 group by t.monat order by t.monat desc limit 6\"))
print('GROSS', q(\"select t.datum,t.betrag,t.gegenpartei,g.category from transactions t join tx_category g on g.tx_id=t.id where t.is_internal=0 and t.monat=(select max(monat) from transactions) order by abs(t.betrag) desc limit 10\"))
print('UNKLAR', q(\"select t.gegenpartei,count(*),round(sum(t.betrag),2) from transactions t join tx_category g on g.tx_id=t.id where g.category='Sonstiges' and t.monat=(select max(monat) from transactions) group by t.gegenpartei order by sum(abs(t.betrag)) desc limit 15\"))
print('AUSGELAUFEN', q(\"select name,round(betrag_typ,2),tage_seit_letzter,med_gap from contracts where status<>'rejected' and coalesce(aktiv_user,aktiv)=0 order by tage_seit_letzter desc limit 8\"))
print('PREIS', q(\"select name,round(betrag_typ,2),round(betrag_letzter,2),round((betrag_letzter-betrag_typ)/betrag_typ*100,1) from contracts where status<>'rejected' and betrag_typ<>0 and abs(betrag_letzter-betrag_typ)/abs(betrag_typ)>0.05 order by abs(betrag_letzter-betrag_typ)/abs(betrag_typ) desc limit 8\"))
print('REISEN', q(\"select start,ende,substr(orte,1,50),round(kosten) from trips where status='candidate' order by start desc limit 6\"))
"
```

### Wohnen und Miete — eigene Prüfung

Miete ist der Posten, bei dem ein Ausfall am teuersten und am unauffälligsten ist: eine
ausgebliebene Mieteinnahme geht in der Monatssumme unter, eine fehlende Rate fällt erst auf, wenn
die Bank sich meldet. Deshalb eine Matrix aller wiederkehrenden Wohn- und Immobilienposten der
letzten acht Monate, ohne Namen im Skript, damit neue Posten von selbst auftauchen:

```bash
cd <projekt> && python -c "
import sqlite3,collections; c=sqlite3.connect('finanzen.db')
m=c.execute('select max(monat) from transactions').fetchone()[0]
von=c.execute(\"select strftime('%Y-%m',date(?||'-01','-7 months'))\",(m,)).fetchone()[0]
rows=c.execute('''select g.category,t.gegenpartei,t.monat,t.betrag from transactions t
 join tx_category g on g.tx_id=t.id where t.is_internal=0
 and (g.category='Wohnen' or g.category like 'Immobilie%') and abs(t.betrag)>=200
 and t.monat>=? order by t.monat''',(von,)).fetchall()
d=collections.OrderedDict()
for cat,gp,mo,b in rows: d.setdefault((cat,gp),collections.OrderedDict()).setdefault(mo,0); d[(cat,gp)][mo]+=b
mons=sorted({r[2] for r in rows})
print('MIETE  Monate:',' '.join(x[2:] for x in mons))
for (cat,gp),v in sorted(d.items(),key=lambda kv:-len(kv[1])):
    if len(v)<3: continue
    print('%-22s %-34s %s'%(cat[:22],gp[:34],' '.join(('%5d'%round(v[x])) if x in v else '    .' for x in mons)))
"
```

Jede Zeile mit einem `.` in der letzten Spalte ist ein Kandidat — **aber erst nachsehen**:

- **Buchung am Monatsletzten gehört oft zum Folgemonat.** Das sieht aus wie „Doppelmonat, dann
  Loch", ist aber lückenlos — erkennbar am doppelten Betrag im Vormonat. Einzeldaten holen:
  `select datum,konto,betrag,verwendungszweck from transactions where gegenpartei like '…%' order by datum`
- **Der Export endet vor dem Buchungstag.** Gegen die Abdeckung aus Phase 1 prüfen, nicht gegen
  den Kalendermonat.
- **Betragswechsel ist kein Ausfall.** Eine Zahlung, die auf zwei Buchungen aufgeteilt wird,
  taucht in der Vertragsprüfung als Preissturz auf. Erst summieren, dann bewerten.

Worauf du sonst achtest:

- **Abdeckung** — schließt jedes Konto an den neuen Monat an?
- **Sonstiges-Quote** — normal sind wenige Prozent. Springt sie, ist die erste Frage **„gibt es
  eine unerkannte Reise?"**, erst danach „neue Händler?".
- **Große Buchungen** — jede ungewöhnlich große Einzelbuchung benennen, mit Kategorie.
- **Unklare Händler** — nach Betrag sortiert, nicht nach Anzahl.
- **Ausgelaufene Verträge** — gekündigt (bestätigen) oder vergessen/geplatzt (handeln).
- **Preisänderungen** — Beitragserhöhungen findet man hier zuerst.
- **Reise-Kandidaten** — neue erkannte Reisen zum Bestätigen oder Ablehnen.
- **Vermögen** (falls eingerichtet) — Depotwert gegen den Vormonat, Kontostände plausibel.

## Phase 7 — Übergeben

Die App läuft unter `http://localhost:8765/finanzen/` (bzw. der Adresse aus `lokal.md`). Dort
ist die Reihenfolge, in der er schaut:

1. **Übersicht** — der neue Monat gegen den Durchschnitt
2. **Buchungen** — die unklaren Buchungen, gefiltert auf „nur Sonstiges" (am Handy: **Prüfen**)
3. **Verträge** — neue Kandidaten und ausgelaufene bestätigen
4. **Reisen** — Kandidaten bestätigen, das setzt den Urlaubsstempel
5. **Statistik** und **Vermögen**

Fass das Ergebnis in wenigen Sätzen zusammen: wie viele Buchungen dazugekommen sind, was
auffällt, was er entscheiden muss. Keine Erfolgsmeldung ohne Zahlen, und wenn eine Prüfung nicht
gelaufen ist, sag welche. Wenn Phase 5b gelaufen ist: wie viele Händler die KI-Schicht übernommen
hat, wie viel Volumen, was offen blieb — die Vorschläge tragen `source_rule='ki'` und sind in den
Buchungen filterbar. **Die offene Restliste gehört in dieselbe Nachricht**, sonst versandet sie.

Den **Wohn- und Mietstatus nennst du immer** — auch wenn alles da ist, dann in einem Satz.
Schweigen heißt sonst entweder „geprüft und gut" oder „vergessen zu prüfen".

## Wenn er Regeln ergänzen will

Wiederkehrende unklare Händler gehören als **breites Muster** in `SEED2` in `rules.py` (wenn sie
viele Haushalte betreffen) oder in `eigene_regeln` der eigenen `konfig.json` (wenn nur diesen).
Danach `run_all.py` erneut. Einzelfälle bleiben in der manuellen Schicht, die er in den Buchungen
selbst setzt.

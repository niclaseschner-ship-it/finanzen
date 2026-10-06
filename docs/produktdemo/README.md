# Finanzen – Produktdemo

Sechs Produktmotive mit Konto und Mail als Kern: Die Bank liefert den Geldfluss, die passende Bestellmail ergänzt das gekaufte Produkt. Die übrigen Motive zeigen Monatsüberblick, Prüfung, wiederkehrende Zahlungen, Statistik und Vermögen.

1. [Konto trifft Mail](01-konto-mail.png)
2. [Dein Monat](02-monat.png)
3. [Du hast das letzte Wort](03-pruefen.png)
4. [Fixkosten erkennen](04-fixkosten.png)
5. [Wohin geht dein Geld?](05-statistik.png)
6. [Das ganze Bild](06-vermoegen.png)

## Herkunft und Datenschutz

Aufgenommen am 06.10.2026 aus den echten, statischen App-Seiten unter `demo/`. Alle Beträge, Namen, Konto- und Bestellnummern stammen aus dem vollständig erfundenen Demohaushalt, dessen Erzeuger unter `beispieldaten/erzeugen.py` liegt. Die Produktionsdatenbank und das persönliche Postfach wurden für die Aufnahmen nicht geöffnet oder kopiert. Es wurde keine Schwärzung echter Daten als Sicherheitsmaßnahme verwendet: Die Aufnahmequelle selbst enthält ausschließlich Demodaten.

Die Aufnahmeautomation lädt nur Dateien aus dem Demo-Verzeichnis und eingebettete Daten. Andere Netzwerkanfragen werden blockiert; es besteht keine Verbindung zur Produktions-API. Die Originale liegen unter [originale/](originale/), der reproduzierbare Ablauf in [aufnehmen.py](aufnehmen.py).

Die Motive wurden mit dem nativen ImageGen-Werkzeug aus diesen Originalaufnahmen gestaltet. [Prompts](prompts.txt) beschreiben Texte und Gestaltung. Kleine UI-Schriften können durch ImageGen neu gerendert werden; maßgeblich für genaue Produktdetails sind die Originalaufnahmen. Jede finale Grafik ist als erfundene Beispieldaten gekennzeichnet.

## Aufnahmen wiederholen

Benötigt vorhandenes Python-Playwright und Chromium. Vom Repo aus:

```bash
python docs/produktdemo/aufnehmen.py
```

Optional bezeichnet `FINANZEN_DEMO` ein anderes Verzeichnis mit derselben statischen Demo. Das Skript nimmt keine Daten aus dem laufenden App-Server auf. Die Produktbilder verändern keine App-Funktion.

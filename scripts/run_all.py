"""Gesamter Prozess in einem Befehl (angestoßen durch neue Daten in konten/).
   python run_all.py
Reihenfolge = der besprochene Prozess; alle Schritte idempotent.
Manuelle Schicht (tx_manual/merchant_rules) bleibt erhalten (tx-id stabil).
"""
import sys, time
import db, konfig, parse_konten, ingest_transactions, enrich, match, build_context, branche, rules, frontend, liste

# Windows setzt bei umgeleiteter Ausgabe (> log.txt, | more) cp1252 statt UTF-8 – die
# Pfeile/Häkchen im Fortschritt lassen die Pipeline dann mit UnicodeEncodeError abstürzen,
# obwohl inhaltlich alles in Ordnung ist. Einmal hart auf UTF-8 stellen.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

def step(name, fn):
    t = time.time(); print(f"→ {name} ...", flush=True)
    fn(); print(f"  ✓ {name} ({time.time()-t:.1f}s)", flush=True)

def main():
    print("=== Finanz-Pipeline ===")
    # Erst die Konfiguration, dann Daten anfassen. Mit fremder Kontenkarte wären die
    # Ergebnisse still falsch (interne Umbuchungen als Ausgaben, Alltag als Dauerreise) —
    # lieber gar nicht laufen als plausibel aussehenden Unsinn produzieren.
    if konfig.IST_BEISPIEL:
        raise RuntimeError(
            "Es läuft noch die BEISPIEL-Konfiguration.\n"
            f"  kopieren: {konfig.BEISPIEL}\n"
            f"      nach: {konfig.PFAD}\n"
            "  und die eigenen Konten/Kategorien eintragen.\n"
            "  Prüfen mit: python konfig.py")
    konfig.pruefen()
    print(f"Konfiguration: {konfig.NAME or konfig.PFAD}")
    step("1 Konten zusammenführen + dedup (parse_konten)", parse_konten.run)
    step("2 Konto -> DB + Systemgrenze (ingest_transactions)", ingest_transactions.run)
    # Leere Kategorie-/Label-Tabellen anlegen, bevor jemand sie liest. Nur beim ersten
    # Lauf relevant, kostet sonst nichts (CREATE TABLE IF NOT EXISTS).
    rules.ensure_schema()
    step("3 Anreichern (enrich: Zahlungsart/Refs/Vertrag/wiederkehrend)", enrich.run)
    step("4 Belege/Mails mechanisch matchen (match)", match.run)
    step("5 Branche unbekannter Händler via OSM (branche, gecacht)", branche.run)
    step("6 Kategorisieren + Regeln + manuelle Schicht (rules)", rules.apply_rules)
    # build_context NACH rules: es wählt die Buchungen über deren Kategorie/Status aus
    # (tx_category). Davor lief es auf dem Stand des VORIGEN Laufs — frisch importierte
    # Buchungen bekamen ihren Beleg-Kontext erst einen Lauf später, und beim allerersten
    # Lauf brach es ab, weil die Tabelle noch gar nicht existierte. rules selbst nutzt
    # tx_context nicht, die Abhängigkeit geht also nur in diese Richtung.
    step("7 Mail-Kontext je Buchung (build_context)", build_context.run)
    step("8 Statistik-Seite (frontend)", frontend.run)
    step("9 Editor-/Listendaten (liste)", liste.run)
    print("FERTIG. Editor: python app.py  ->  http://localhost:8765")

if __name__ == "__main__":
    # Erwartbare Fehler (Konfiguration fehlt/unbrauchbar, kein Kontoexport) sind für den
    # Nutzer eine Anweisung, kein Programmierfehler -> Klartext statt Traceback. Innerhalb
    # von main() wird weiterhin geworfen, damit die Import-Seite den Text anzeigen kann.
    try:
        main()
    except (RuntimeError, konfig.KonfigFehler) as e:
        print(f"\nABBRUCH: {e}"); sys.exit(1)

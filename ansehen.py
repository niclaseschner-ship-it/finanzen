"""Schiesst Bildschirmfotos der App in Handy- und Desktopbreite.

Damit laesst sich eine Layoutaenderung wirklich ansehen, statt sie nur auszuliefern.
Braucht Playwright und das installierte Chrome, beides schon vorhanden.

Aufruf:
  python ansehen.py                 # alle Seiten, beide Breiten
  python ansehen.py / /vertraege    # nur diese Seiten
"""
import os
import sys
import tempfile

from playwright.sync_api import sync_playwright

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
BASIS = "http://127.0.0.1:8765/finanzen"
SEITEN = ["/", "/editor", "/statistik.html", "/vertraege", "/reisen", "/vermoegen", "/vorsorge"]
BREITEN = [("handy", 390, 844, 2), ("desktop", 1440, 900, 1)]


def name(pfad):
    return (pfad.strip("/").replace("/", "_") or "start").replace(".html", "")


def main(seiten):
    ziel = os.path.join(tempfile.gettempdir(), "finanzen-ansicht")
    os.makedirs(ziel, exist_ok=True)
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=CHROME)
        for art, w, h, skal in BREITEN:
            s = b.new_page(viewport={"width": w, "height": h}, device_scale_factor=skal)
            for pfad in seiten:
                try:
                    s.goto(BASIS + pfad, wait_until="networkidle", timeout=20000)
                    s.wait_for_timeout(1000)
                    datei = os.path.join(ziel, f"{art}_{name(pfad)}.png")
                    s.screenshot(path=datei)
                    print(f"  {art:8s} {pfad:14s} -> {datei}")
                except Exception as e:
                    print(f"  {art:8s} {pfad:14s} FEHLER: {type(e).__name__}: {e}")
            s.close()
        b.close()
    print("\nAlle Bilder in:", ziel)


if __name__ == "__main__":
    main([a for a in sys.argv[1:]] or SEITEN)

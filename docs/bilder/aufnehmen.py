#!/usr/bin/env python3
"""Screenshots aus der Online-Demo (demo/) aufnehmen.

    python docs/bilder/aufnehmen.py

Braucht Playwright für Python und ein Chromium (`pip install playwright`, dann
`playwright install chromium` — oder CHROMIUM=/pfad/zu/chromium setzen). Nimmt die
statische Demo direkt aus dem Dateisystem auf, also genau das, was man online sieht:
erfundene Daten, echte Seiten.

- docs/bilder/*.png       — die Auswahl fürs README
- docs/bilder/alle/*.png  — jede Seite am Rechner (1440×900) und am Handy (390×844),
                            hell und dunkel, in doppelter Auflösung
Vorher `python demo/bauen.py`, damit die Demo aktuell ist.
"""
import asyncio, os

from playwright.async_api import async_playwright

HIER = os.path.dirname(os.path.abspath(__file__))
DEMO = "file://" + os.path.join(os.path.dirname(os.path.dirname(HIER)), "demo") + "/"
ALLE = os.path.join(HIER, "alle")
CHROMIUM = os.environ.get("CHROMIUM") or ("/usr/bin/chromium" if os.path.exists("/usr/bin/chromium") else None)
HANDY_UA = ("Mozilla/5.0 (Linux; Android 14; Pixel 9a) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/129.0 Mobile Safari/537.36")
DESKTOP = ["start", "editor", "statistik", "vertraege", "reisen", "vermoegen", "vorsorge"]
HANDY = ["monat", "buchungen", "pruefen", "vertraege", "vermoegen"]


async def desktop(br, schema):
    seite = await br.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=2,
                              color_scheme=schema)
    for name in DESKTOP:
        await seite.goto(DEMO + name + ".html")
        await seite.wait_for_timeout(2200 if name == "statistik" else 1400)
        await seite.screenshot(path=os.path.join(ALLE, f"rechner-{schema}-{name}.png"))
    # Belege: Buchungen auf eine Online-Bestellung gefiltert, mit Produktzeile aus der Mail
    await seite.goto(DEMO + "editor.html")
    await seite.wait_for_timeout(1400)
    await seite.fill("#fsearch", "amazon")
    await seite.wait_for_timeout(700)
    await seite.screenshot(path=os.path.join(ALLE, f"rechner-{schema}-belege.png"))
    await seite.close()


async def handy(br, schema):
    seite = await br.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=2,
                              user_agent=HANDY_UA, is_mobile=True, has_touch=True, color_scheme=schema)
    for name in HANDY:
        await seite.goto(DEMO + "handy.html#" + name)
        await seite.wait_for_timeout(1300)
        await seite.screenshot(path=os.path.join(ALLE, f"handy-{schema}-{name}.png"))
    await seite.goto(DEMO + "handy.html#buchungen")
    await seite.wait_for_timeout(1300)
    await seite.locator("#b-liste .zeile").nth(3).click()
    await seite.wait_for_timeout(900)
    await seite.screenshot(path=os.path.join(ALLE, f"handy-{schema}-buchung.png"))
    await seite.close()


def readme_auswahl():
    """Die README-Bilder: helle Rechner-Seiten und drei Handys nebeneinander."""
    import shutil
    from PIL import Image, ImageDraw
    for name, ziel in [("start", "uebersicht"), ("editor", "editor"), ("statistik", "statistik"),
                       ("vertraege", "vertraege"), ("vermoegen", "vermoegen"), ("belege", "belege"),
                       ("reisen", "reisen")]:
        shutil.copy(os.path.join(ALLE, f"rechner-light-{name}.png"), os.path.join(HIER, ziel + ".png"))
    bilder = [Image.open(os.path.join(ALLE, f"handy-light-{n}.png")).convert("RGB")
              for n in ("monat", "pruefen", "buchung")]
    w, h = bilder[0].size
    rand, luecke, r = 60, 50, 56
    ges = Image.new("RGB", (rand * 2 + w * 3 + luecke * 2, rand * 2 + h), (232, 230, 224))
    for i, b in enumerate(bilder):
        maske = Image.new("L", (w, h), 0)
        ImageDraw.Draw(maske).rounded_rectangle([0, 0, w - 1, h - 1], radius=r, fill=255)
        ges.paste(b, (rand + i * (w + luecke), rand), maske)
    ges.resize((ges.width // 2, ges.height // 2), Image.LANCZOS).save(os.path.join(HIER, "handy.png"), optimize=True)


async def main():
    os.makedirs(ALLE, exist_ok=True)
    async with async_playwright() as p:
        br = await p.chromium.launch(**({"executable_path": CHROMIUM} if CHROMIUM else {}))
        for schema in ("light", "dark"):
            await desktop(br, schema)
            await handy(br, schema)
        await br.close()
    readme_auswahl()
    print(f"{len(os.listdir(ALLE))} Bilder in {ALLE}, README-Auswahl in {HIER}")


if __name__ == "__main__":
    asyncio.run(main())

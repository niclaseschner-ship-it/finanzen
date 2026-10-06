"""Nur die statische App-Demo mit erfundenen Daten aufnehmen; keine Produktions-API."""
from pathlib import Path
import os
from playwright.sync_api import sync_playwright

OUT = Path(__file__).resolve().parent / 'originale'
DEMO = Path(os.environ.get('FINANZEN_DEMO', str(Path(__file__).resolve().parents[2] / 'demo'))).resolve().as_uri() + '/'
OUT.mkdir(parents=True, exist_ok=True)
with sync_playwright() as p:
    browser = p.chromium.launch(executable_path='/usr/bin/chromium', headless=True, args=['--disable-dev-shm-usage'])
    def safe(route):
        if route.request.url.startswith((DEMO, 'data:')):
            route.continue_()
        else:
            route.abort()
    desktop = browser.new_context(viewport={'width':1280,'height':900}, color_scheme='light', service_workers='block')
    desktop.route('**/*', safe)
    page = desktop.new_page()
    for name in ['statistik','vertraege','vermoegen','vorsorge']:
        page.set_viewport_size({'width':1280,'height':1400 if name == 'vorsorge' else 900})
        page.goto(DEMO+name+'.html'); page.wait_for_timeout(1800)
        page.screenshot(path=str(OUT/(name+'.png')))
    page.set_viewport_size({'width':1280,'height':900})
    page.goto(DEMO+'editor.html'); page.wait_for_timeout(1000)
    page.locator('#fsearch').fill('amazon'); page.wait_for_timeout(500)
    page.screenshot(path=str(OUT/'konto-mail.png'))
    mobile = browser.new_context(viewport={'width':390,'height':844}, device_scale_factor=2, is_mobile=True, has_touch=True, color_scheme='light', service_workers='block')
    mobile.route('**/*', safe)
    phone = mobile.new_page()
    phone.goto(DEMO+'handy.html#monat'); phone.wait_for_timeout(1300)
    phone.screenshot(path=str(OUT/'monat.png'))
    phone.goto(DEMO+'handy.html#pruefen'); phone.wait_for_timeout(1300)
    phone.screenshot(path=str(OUT/'pruefen.png'))
    phone.goto(DEMO+'handy.html#buchungen'); phone.wait_for_timeout(1300)
    rows = phone.locator('#b-liste .zeile')
    target = rows.filter(has_text='Amazon').first
    if not target.count(): target = rows.filter(has_text='AMAZON').first
    target.click(); phone.wait_for_timeout(700)
    phone.screenshot(path=str(OUT/'kauf-detail.png'))
    print('Demo-Aufnahmen:',len(list(OUT.glob('*.png'))))
    browser.close()

"""Branche eines Händlers mechanisch über OpenStreetMap (Nominatim, gratis, kein Key).
- Nur unbekannte Karten-Händler (aktuell 'Sonstiges') werden nachgeschlagen.
- Ergebnis wird in `merchant_branche` GECACHT -> jeder Händler nur EINMAL abgefragt,
  Folgeläufe bleiben offline. OSM-Typ wird auf unsere Kategorie gemappt.
- rules.py wendet den Cache als Fallback an (unter deinen manuellen Entscheidungen),
  Status 'branche-osm' = Vorschlag, jederzeit überschreibbar.
Datenschutz: es geht NUR Händlername + Ort an OSM (keine Beträge/Kontonummern).
"""
import time, json, re, urllib.request, urllib.parse
import db, konfig

NOMINATIM = "https://nominatim.openstreetmap.org/search"
UA = "buddyboard-finanzen/1.0 (persönliche, lokale Ausgaben-Auswertung)"
MAX_PRO_LAUF = 150          # höflich + zeitlich begrenzt; Rest kommt im nächsten Lauf dran
PAUSE = 1.1                 # Nominatim-Policy: max ~1 Anfrage/Sekunde

# OSM-Typ (oder -Klasse) -> unsere Kategorie
MAP = {
 "supermarket":"Lebensmittel/Drogerie","convenience":"Lebensmittel/Drogerie","greengrocer":"Lebensmittel/Drogerie",
 "bakery":"Lebensmittel/Drogerie","pastry":"Lebensmittel/Drogerie","butcher":"Lebensmittel/Drogerie",
 "deli":"Lebensmittel/Drogerie","beverages":"Lebensmittel/Drogerie","confectionery":"Lebensmittel/Drogerie",
 "cheese":"Lebensmittel/Drogerie","dairy":"Lebensmittel/Drogerie","farm":"Lebensmittel/Drogerie",
 "chemist":"Lebensmittel/Drogerie","kiosk":"Lebensmittel/Drogerie","health_food":"Lebensmittel/Drogerie",
 "restaurant":"Restaurant/Café","cafe":"Restaurant/Café","fast_food":"Restaurant/Café","bar":"Restaurant/Café",
 "pub":"Restaurant/Café","ice_cream":"Restaurant/Café","biergarten":"Restaurant/Café","food_court":"Restaurant/Café",
 "fuel":"Mobilität","car_repair":"Mobilität","car":"Mobilität","car_parts":"Mobilität","tyres":"Mobilität",
 "parking":"Mobilität","charging_station":"Mobilität","bicycle":"Mobilität","motorcycle":"Mobilität",
 "pharmacy":"Gesundheit","doctors":"Gesundheit","dentist":"Gesundheit","hospital":"Gesundheit",
 "clinic":"Gesundheit","optician":"Gesundheit",
 "veterinary":"Gesundheit",
 "hairdresser":"Dienstleistung","beauty":"Dienstleistung","laundry":"Dienstleistung","dry_cleaning":"Dienstleistung",
 "post_office":"Dienstleistung","travel_agency":"Freizeit/Hobby","bank":"Gebühren",
 "cinema":"Freizeit/Hobby","theatre":"Freizeit/Hobby","fitness_centre":"Freizeit/Hobby",
 "sports_centre":"Freizeit/Hobby","swimming_pool":"Freizeit/Hobby","museum":"Freizeit/Hobby",
 "sports":"Freizeit/Hobby","books":"Freizeit/Hobby","music":"Freizeit/Hobby","art":"Freizeit/Hobby",
 "hotel":"Freizeit/Hobby","guest_house":"Freizeit/Hobby","hostel":"Freizeit/Hobby","motel":"Freizeit/Hobby","camp_site":"Freizeit/Hobby","apartment":"Freizeit/Hobby",
 "toys":"Kinder","baby_goods":"Kinder",
 "farmyard":"Lebensmittel/Drogerie","farm":"Lebensmittel/Drogerie","winery":"Lebensmittel/Drogerie",
 "clothes":"Shopping/Haushalt","shoes":"Shopping/Haushalt","furniture":"Shopping/Haushalt","hardware":"Shopping/Haushalt",
 "doityourself":"Shopping/Haushalt","electronics":"Shopping/Haushalt","department_store":"Shopping/Haushalt",
 "variety_store":"Shopping/Haushalt","stationery":"Shopping/Haushalt","garden_centre":"Shopping/Haushalt",
 "florist":"Shopping/Haushalt","mobile_phone":"Shopping/Haushalt","jewelry":"Shopping/Haushalt",
 "newsagent":"Shopping/Haushalt","houseware":"Shopping/Haushalt","gift":"Shopping/Haushalt",
}
# Eigene Zuordnungen aus konfig.json gewinnen: wer eine eigene Kategorie fuer eine
# Branche fuehrt, traegt sie dort ein statt hier im Code.
MAP.update(konfig.BRANCHE_KATEGORIEN)
CLASS_FALLBACK = {"shop":"Shopping/Haushalt","tourism":"Urlaub","leisure":"Freizeit/Hobby"}

_NOISE = re.compile(r"(?i)\b(visa|debitkartenumsatz|vom|kartenzahlung|girocard|contactless|nr|ec)\b")
_PROC = re.compile(r"(?i)^\s*(sumup|zettle|izettle|paypal|klarna|payone|concardis)\s+")
def clean_name(hn):
    s = _PROC.sub("", hn or "")                  # Zahlungs-Dienstleister-Präfix raus -> echter Händler
    s = _NOISE.sub(" ", s)
    s = re.sub(r"\d{2}\.\d{2}\.\d{2,4}", " ", s)
    s = re.sub(r"\b\d{3,}\b", " ", s)            # lange Nummern raus
    s = re.sub(r"[\\/|]+", " ", s)
    # Rechtsformen entfernen – sie killen die OSM-Suche (OSM-POIs heißen ohne GmbH/KG)
    s = re.sub(r"(?i)\bg\.?\s?m\.?\s?b\.?\s?h\b\.?", " ", s)
    s = re.sub(r"(?i)\s*&?\s*\bco\.?\s*kg\b", " ", s)
    s = re.sub(r"(?i)\b(mbh|kgaa|kg|ohg|gbr|ug|ag|se|sarl|srl|bv|ltd|inc|e\.?\s?[vk]\.?)\b\.?", " ", s)
    s = re.sub(r"(?i)\s*&\s*co\b\.?", " ", s)
    s = re.sub(r"\s+", " ", s).strip(" .,&-")
    return s

def osm_to_cat(cls, typ):
    return MAP.get(typ) or CLASS_FALLBACK.get(cls)

def _umlaut(s):   # Karten-Schreibweise -> echte Umlaute (für OSM besser auffindbar)
    return (s.replace("ue", "ü").replace("oe", "ö").replace("ae", "ä")
             .replace("Ue", "Ü").replace("Oe", "Ö").replace("Ae", "Ä").replace("ss", "ß"))

def _query(q):
    # KEIN Länderfilter: Urlaubs-Buchungen (Italien/Skandinavien…) sollen auch treffen
    params = urllib.parse.urlencode({"q": q, "format": "jsonv2", "limit": 1, "addressdetails": 0})
    req = urllib.request.Request(NOMINATIM + "?" + params, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=20) as r:
        data = json.loads(r.read())
    if not isinstance(data, list) or not data: return None
    d = data[0]
    return (d.get("category") or d.get("class"), d.get("type"), d.get("display_name", "")[:80])

def lookup(query):
    res = _query(query)
    if res is None and any(x in query for x in ("ue", "oe", "ae", "ss")):
        time.sleep(PAUSE); res = _query(_umlaut(query))   # 2. Versuch mit Umlauten
    return res if res else (None, None, None)

def run():
    con = db.connect()
    con.execute("""CREATE TABLE IF NOT EXISTS merchant_branche (
        haendler_norm TEXT PRIMARY KEY, query TEXT, osm_class TEXT, osm_type TEXT,
        osm_name TEXT, category TEXT, ts TEXT)""")
    cached = set(r[0] for r in con.execute("select lower(haendler_norm) from merchant_branche"))
    # Ziel: häufigste noch unbekannte Karten-Händler (aktuell 'Sonstiges')
    targets = con.execute("""select e.haendler_norm, max(e.ort), count(*) n
        from tx_enrich e join tx_category c on c.tx_id=e.tx_id
        where c.category='Sonstiges' and e.zahlungsart in ('Karte','PayPal')
          and coalesce(e.haendler_norm,'')<>''
        group by lower(e.haendler_norm) order by n desc""").fetchall()
    todo = [(hn, ort) for hn, ort, n in targets if hn.lower() not in cached]
    print(f"Branche-Lookup: {len(todo)} unbekannte Händler offen, cache={len(cached)}")
    done = 0
    for hn, ort in todo[:MAX_PRO_LAUF]:
        name = clean_name(hn)
        if len(name) < 3: continue
        city = ort.split()[0] if (ort and ort.lower() != "none") else ""
        # zweistufig: erst Name + Stadt (präzise), sonst Name allein (mehr Treffer)
        variants = ([f"{name} {city}"] if city else []) + [name]
        cls = typ = oname = cat = None; usedq = name
        try:
            for q in variants:
                res = lookup(q)
                if res != (None, None, None):
                    cls, typ, oname = res; cat = osm_to_cat(cls, typ); usedq = q
                    if cat: break          # Business-Treffer -> fertig
                time.sleep(PAUSE)
        except Exception as e:
            print(f"  ! Fehler bei '{name[:30]}': {e}"); time.sleep(PAUSE); continue
        con.execute("""insert or replace into merchant_branche
            (haendler_norm,query,osm_class,osm_type,osm_name,category,ts)
            values(?,?,?,?,?,?,datetime('now'))""", (hn, usedq, cls, typ, oname, cat))
        con.commit()
        if cat: done += 1
        time.sleep(PAUSE)
    rest = max(0, len(todo) - MAX_PRO_LAUF)
    hits = con.execute("select count(*) from merchant_branche where category is not null and category<>''").fetchone()[0]
    print(f"  abgefragt {min(len(todo),MAX_PRO_LAUF)}, davon {done} mit Branche; Cache-Treffer gesamt {hits}"
          + (f"; NOCH {rest} offen (nächster Lauf)" if rest else "; alle abgearbeitet"))
    con.close()

if __name__ == "__main__":
    run()

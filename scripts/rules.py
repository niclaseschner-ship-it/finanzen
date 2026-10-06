"""Regelwerk (datengetrieben, erweiterbar) + Anwendung mit Nachvollziehbarkeit.
- rules-Tabelle = Daten -> neue Regel = neue Zeile, kein Code noetig.
- Jede Buchung: genau 1 Kategorie (tx_category) + n Labels (tx_labels),
  immer mit Quelle/Begruendung/Konfidenz. Nichts faellt weg: ohne Treffer
  -> Kategorie 'Sonstiges', Status 'unkategorisiert' (sichtbar markiert).
"""
import re, db, konfig

def word_start(pat, hay):
    # Treffer nur am Wortanfang: 'baeck'->'baeckerei' ja, 'burg'->'Hamburger' nein
    return re.search(r"\b" + re.escape(pat.strip()), hay) is not None

SCHEMA = """
CREATE TABLE IF NOT EXISTS rules (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT, prio INTEGER, match_type TEXT, pattern TEXT,
  category TEXT, labels TEXT, aktiv INTEGER DEFAULT 1
);
CREATE TABLE IF NOT EXISTS tx_category (
  tx_id TEXT PRIMARY KEY, category TEXT, source_rule TEXT,
  reason TEXT, confidence REAL, status TEXT, eff_monat TEXT
);
-- DEINE manuelle Schicht (über Service editierbar, non-destruktiv):
CREATE TABLE IF NOT EXISTS tx_manual (
  tx_id TEXT PRIMARY KEY, category TEXT, labels TEXT,
  ignore INTEGER DEFAULT 0, datum_override TEXT, note TEXT, reviewed INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS merchant_rules (   -- gilt für ganzen Vertrag/Händler
  key_type TEXT, key_val TEXT, category TEXT, labels TEXT,
  PRIMARY KEY (key_type, key_val)
);
CREATE TABLE IF NOT EXISTS labels_catalog ( name TEXT PRIMARY KEY );
CREATE TABLE IF NOT EXISTS tx_labels (
  tx_id TEXT, label TEXT, source_rule TEXT
);
CREATE INDEX IF NOT EXISTS ix_lbl_tx ON tx_labels(tx_id);
CREATE TABLE IF NOT EXISTS ki_overrides (
  -- begruendung = WARUM diese Kategorie (Websuche-Fund, Angabe des Nutzers, Namenshinweis).
  -- Landet als reason in tx_category und ist damit im Editor pruefbar. Ohne sie waere eine
  -- KI-Zuordnung eine Behauptung ohne Beleg.
  haendler_norm TEXT PRIMARY KEY, category TEXT, labels TEXT, confidence REAL, note TEXT,
  begruendung TEXT
);
"""

# match_type: haendler_kw | verwendung_kw | creditor | paypal_kw
# (preset/flow/intern werden vorrangig im Code behandelt)
SEED = [
 # name, prio, match_type, pattern, category, labels
 ("Wertpapier/Depot",8,"verwendung_kw","wertp.abrechn","Sparen/Invest","invest,wertpapier"),
 # Die eigene Depotnummer als Muster gehoert in konfig.json -> eigene_regeln,
 # nicht in den ausgelieferten Code.
 ("Telefon/Internet",15,"haendler_kw","telekom","Abo/Digital","vertrag,telekom"),
 ("Telefon/Internet",15,"haendler_kw","drillisch","Abo/Digital","vertrag"),
 ("Telefon/Internet",15,"haendler_kw","blacksim","Abo/Digital","vertrag"),
 ("Rundfunk",15,"haendler_kw","rundfunk","Gebühren","vertrag,rundfunk"),
 ("Bankgebuehr",16,"haendler_kw","dkb ag","Gebühren","bank"),
 # Lebensmittel/Drogerie
 ("Supermarkt",20,"haendler_kw","aldi","Lebensmittel/Drogerie","lebensmittel"),
 ("Supermarkt",20,"haendler_kw","lidl","Lebensmittel/Drogerie","lebensmittel"),
 ("Supermarkt",20,"haendler_kw","edeka","Lebensmittel/Drogerie","lebensmittel"),
 ("Supermarkt",20,"haendler_kw","rewe","Lebensmittel/Drogerie","lebensmittel"),
 ("Supermarkt",20,"haendler_kw","penny","Lebensmittel/Drogerie","lebensmittel"),
 ("Supermarkt",20,"haendler_kw","netto","Lebensmittel/Drogerie","lebensmittel"),
 ("Supermarkt",20,"haendler_kw","kaufland","Lebensmittel/Drogerie","lebensmittel"),
 ("Supermarkt",20,"haendler_kw","denns","Lebensmittel/Drogerie","lebensmittel,bio"),
 ("Supermarkt",20,"haendler_kw","bioladen","Lebensmittel/Drogerie","lebensmittel,bio"),
 ("Supermarkt",20,"haendler_kw","rema1000","Lebensmittel/Drogerie","lebensmittel"),
 ("Supermarkt",20,"haendler_kw","coop","Lebensmittel/Drogerie","lebensmittel"),
 ("Drogerie",20,"haendler_kw","dm ","Lebensmittel/Drogerie","drogerie,dm"),
 ("Drogerie",20,"haendler_kw","rossmann","Lebensmittel/Drogerie","drogerie"),
 # Restaurant/Cafe
 ("Restaurant",25,"haendler_kw","mcdonald","Restaurant/Café","essen-ausser-haus"),
 ("Restaurant",25,"haendler_kw","restaurant","Restaurant/Café","essen-ausser-haus"),
 ("Restaurant",25,"haendler_kw","pizza","Restaurant/Café","essen-ausser-haus"),
 ("Restaurant",25,"haendler_kw","gelato","Restaurant/Café","essen-ausser-haus,just-for-fun"),
 ("Restaurant",25,"haendler_kw","cafe","Restaurant/Café","essen-ausser-haus,just-for-fun"),
 ("Restaurant",25,"haendler_kw","café","Restaurant/Café","essen-ausser-haus,just-for-fun"),
 ("Restaurant",25,"haendler_kw","americano","Restaurant/Café","essen-ausser-haus,just-for-fun"),
 # Mobilitaet
 ("Tankstelle",30,"haendler_kw","tankst","Mobilität","auto,sprit"),
 ("Tankstelle",30,"haendler_kw","shell","Mobilität","auto,sprit"),
 ("Tankstelle",30,"haendler_kw","aral","Mobilität","auto,sprit"),
 ("Tankstelle",30,"haendler_kw","calpam","Mobilität","auto,sprit"),
 ("Tankstelle",30,"haendler_kw","esso","Mobilität","auto,sprit"),
 ("Bahn",30,"haendler_kw","db vertrieb","Mobilität","bahn"),
 ("Bahn",30,"haendler_kw","deutsche bahn","Mobilität","bahn"),
 ("Faehre/Maut",30,"haendler_kw","scandlines","Mobilität","faehre,reise"),
 ("Faehre/Maut",30,"verwendung_kw","storebael","Mobilität","faehre,reise"),
 ("Parken",30,"haendler_kw","parken","Mobilität","parken"),
 # Camper
 ("Camper",18,"haendler_kw","camping","Camper","camper"),
 ("Camper",18,"haendler_kw","camp","Camper","camper"),
 ("Camper",18,"haendler_kw","hafa","Camper","camper,anschaffung,ausbau"),
 ("Camper",18,"verwendung_kw","aufstelldach","Camper","camper,anschaffung,ausbau"),
 ("Camper",18,"haendler_kw","mobyvan","Camper","camper,ausbau"),
 ("Camper",18,"haendler_kw","thule","Camper","camper,ausbau"),
 ("Camper",18,"haendler_kw","nordmobil","Camper","camper,ausbau"),
 # Gesundheit
 ("Gesundheit",22,"haendler_kw","apotheke","Gesundheit","gesundheit"),
 ("Gesundheit",22,"haendler_kw","pvs","Gesundheit","gesundheit"),
 ("Gesundheit",22,"haendler_kw","klinik","Gesundheit","gesundheit"),
 # Spenden
 ("Spende",14,"haendler_kw","betterplace","Spenden/Geschenke","spende"),
 ("Spende",14,"haendler_kw","herzklopfen","Spenden/Geschenke","spende"),
 ("Spende",14,"haendler_kw","falknerei","Spenden/Geschenke","spende"),
 # Shopping / Haushalt
 ("Online-Marktplatz",35,"haendler_kw","amazon","Shopping/Haushalt","online,amazon"),
 ("Online-Marktplatz",35,"verwendung_kw","amzn","Shopping/Haushalt","online,amazon"),
 ("Online-Marktplatz",35,"haendler_kw","ebay","Shopping/Haushalt","online,ebay"),
 ("Moebel/Haushalt",35,"haendler_kw","ikea","Shopping/Haushalt","haushalt"),
 ("Sport/Outdoor",35,"haendler_kw","decathlon","Shopping/Haushalt","sport"),
 ("Buch",35,"haendler_kw","thalia","Shopping/Haushalt","buch"),
 # Abo / Digital
 ("KI-Abo",15,"paypal_kw","anthropic","Abo/Digital","ki,vertrag,arbeit"),
 ("KI-Abo",15,"haendler_kw","anthropic","Abo/Digital","ki,vertrag,arbeit"),
 ("KI-Abo",15,"paypal_kw","openai","Abo/Digital","ki,vertrag,arbeit"),
 ("Apple",15,"paypal_kw","apple","Abo/Digital","apple"),
 ("Streaming",15,"paypal_kw","spotify","Abo/Digital","streaming"),
 ("Streaming",15,"paypal_kw","netflix","Abo/Digital","streaming"),
 # Wohnen: eigene Immobilie/Hausverwaltung/Vermieter stehen in konfig.json
 # ("eigene_regeln") — hier bleiben nur Regeln, die für jeden Haushalt gelten.
 # --- Erweiterung Runde 2 (aus Sonstiges-Analyse) ---
 ("Snack-Automat",26,"haendler_kw","selecta","Restaurant/Café","snack,arbeit"),
 ("Restaurant",25,"haendler_kw","asia house","Restaurant/Café","essen-ausser-haus"),
 ("Restaurant",25,"haendler_kw","streetfood","Restaurant/Café","essen-ausser-haus"),
 ("Restaurant",25,"haendler_kw","grill","Restaurant/Café","essen-ausser-haus"),
 ("Restaurant",25,"haendler_kw","euphrat","Restaurant/Café","essen-ausser-haus"),
 ("Restaurant",25,"haendler_kw","meet eat","Restaurant/Café","essen-ausser-haus"),
 ("Restaurant",25,"haendler_kw","ruestem","Restaurant/Café","essen-ausser-haus"),
 ("Restaurant",25,"haendler_kw","colombo","Restaurant/Café","essen-ausser-haus"),
 ("Eisdiele",25,"haendler_kw","eismanufaktu","Restaurant/Café","essen-ausser-haus,just-for-fun"),
 ("Baeckerei",20,"haendler_kw","baeck","Lebensmittel/Drogerie","lebensmittel,baeckerei"),
 ("Metzgerei",20,"haendler_kw","metzg","Lebensmittel/Drogerie","lebensmittel"),
 ("Bio-Supermarkt",20,"haendler_kw","alnatura","Lebensmittel/Drogerie","lebensmittel,bio"),
 ("Supermarkt-Ausland",20,"haendler_kw","supermercato","Lebensmittel/Drogerie","lebensmittel,ausland"),
 ("Supermarkt",20,"haendler_kw","spar fil","Lebensmittel/Drogerie","lebensmittel"),
 ("Agrar/Garten",34,"haendler_kw","zg raiffeisen","Shopping/Haushalt","garten"),
 ("Garten",34,"haendler_kw","dehner","Shopping/Haushalt","garten"),
 ("Baumarkt",34,"haendler_kw","obi","Shopping/Haushalt","heimwerken"),
 ("Buchhandlung",34,"haendler_kw","buecher","Shopping/Haushalt","buch"),
 ("Kleinanzeigen",34,"haendler_kw","kleinanzeigen","Shopping/Haushalt","gebraucht"),
 ("Parken",30,"haendler_kw","easypark","Mobilität","parken"),
 ("Sportverein",28,"haendler_kw","sportverein","Freizeit/Hobby","sport,vertrag"),
 ("Turnverein",28,"haendler_kw","turnerschaft","Freizeit/Hobby","sport,vertrag"),
 # --- Runde 3: allgemeine Muster (breit, auch Urlaubsorte) ---
 ("Restaurant-gen",25,"haendler_kw","gaststaette","Restaurant/Café","essen-ausser-haus"),
 ("Restaurant-gen",25,"haendler_kw","gasthaus","Restaurant/Café","essen-ausser-haus"),
 ("Restaurant-gen",25,"haendler_kw","gasthof","Restaurant/Café","essen-ausser-haus"),
 ("Restaurant-gen",25,"haendler_kw","ristorante","Restaurant/Café","essen-ausser-haus"),
 ("Restaurant-gen",25,"haendler_kw","trattoria","Restaurant/Café","essen-ausser-haus"),
 ("Restaurant-gen",25,"haendler_kw","pizzeria","Restaurant/Café","essen-ausser-haus"),
 ("Restaurant-gen",25,"haendler_kw","osteria","Restaurant/Café","essen-ausser-haus"),
 ("Restaurant-gen",25,"haendler_kw","bistro","Restaurant/Café","essen-ausser-haus"),
 ("Restaurant-gen",25,"haendler_kw","biergarten","Restaurant/Café","essen-ausser-haus"),
 ("Drogerie",20,"haendler_kw","budni","Lebensmittel/Drogerie","drogerie"),
 ("Hofladen",20,"haendler_kw","hofladen","Lebensmittel/Drogerie","lebensmittel,bio,regional"),
 ("Baumarkt",34,"haendler_kw","bauhaus","Shopping/Haushalt","heimwerken"),
 ("Buchhandlung",34,"haendler_kw","buchhandlung","Shopping/Haushalt","buch"),
 ("Post/Versand",36,"haendler_kw","deutsche post","Shopping/Haushalt","porto-versand"),
 ("Post/Versand",36,"haendler_kw","dhl","Shopping/Haushalt","porto-versand"),
 ("Drogerie",20,"haendler_kw","drogerie markt","Lebensmittel/Drogerie","drogerie"),
 ("Bio-Supermarkt",20,"haendler_kw","biomarkt","Lebensmittel/Drogerie","lebensmittel,bio"),
]

# --- Runde 4: breite Long-Tail-Muster (greifen auch bei kuenftigen Daten) ---
SEED2 = []
def _add(catspec, prio, labels, *kw):
    name, cat = catspec.split("|")
    for k in kw: SEED2.append((name, prio, "haendler_kw", k, cat, labels))
_add("Digital|Abo/Digital",15,"ki,vertrag","openai","mistral ai","gamma app"," google",
     "google payment","kinguin")
_add("Dienstleistung|Dienstleistung",12,"","ingenieurbüro","ingenieurbuero")
_add("Kultur|Freizeit/Hobby",16,"ausflug","theater","museum"," kino","kino ","zoo",
     "schmetterling","seilbahn","bergstation","strandbad","schwimmbad","alpenresort","tourispo",
     "wanderhuett","luftseilbahn","seilbahnges","geocenter","magicpark","naturpaerlor","mainau")
_add("Behoerde|Gebühren",17,"behoerde","bundeskasse","landratsamt","gemeinde","ville de",
     "zollamt","zoll ","finanzamt","buergerservice","barschalter","eigenbetrieb")
_add("Baeckerei|Lebensmittel/Drogerie",20,"lebensmittel,baeckerei","boulangerie","laboulangerie",
     "back shop","backshop","backhaus","backstube","brezen","backwaren","heberer",
     "armbrust back","biobackst","brotbruder","backerei","dallmayr","frischem strecker",
     "biokaeserei","feinkost","bauerntafel","panificio","crobag")
_add("Supermarkt-Ausland|Lebensmittel/Drogerie",20,"lebensmittel,ausland","carrefour","crf ",
     "conad","esselunga","intermarche","supermarche","mpreis","billa","leclerc"," mercato",
     "mercat ","go asia","mercato cdc","crf market","crf ipe","crf express")
_add("Drogerie|Lebensmittel/Drogerie",21,"drogerie","budni","biokeller","naturkost",
     "reform martin")
_add("Gesundheit|Gesundheit",22,"gesundheit","apotek","pharmacie","fielmann","medpex",
     "innonature","zahnarzt")
_add("Restaurant|Restaurant/Café",25,"essen-ausser-haus","one trick pony","kebab","doener",
     "döner","burger","sushi","dumpling"," pho","pita","focacceria","gelateria","konditori",
     "wirtshaus","curry","go asia"," asia ","nordsee","haferkater","coffee","kaffee","espresso",
     "canteen"," deli","fries","flammkuchen","baretto","il pane","non solo pane","il banco",
     "mangal","mr nice","tofu standpun","matsch mit sahne","eis bacio","duck it","yi east",
     "yum yum","thats burger","real greek","layaly","siripiri","spicetrails","mai garden",
     "tokio sushi","rosa eck","lesbar","lammstraa","schwarzwaelder hof","alten abtei",
     "pilgergast","das quartier","front food","caffe","bonne femme","bodrum","kebap","mr doener",
     "gunter coffee","elephant beans","kaffee-kiste","brot trifft","baguette","makan",
     "indian curry","croustillant","cerinotti","caffe porto","gelatto","pho1986","botannica",
     "brodijnen","laederach","sutogo")
_add("Auto|Mobilität",29,"auto","carglass","auto-böhler","auto boehler","mietpark","kuhner avis",
     "tuev"," tüv","ersatzteile","kh teile","domo ersatz")
_add("Tankstelle|Mobilität",30,"auto,sprit","station total","total ","avia"," eni","agip",
     "turmoel","tankcenter"," jet ","raststaette","raststätte","star garding","europoint")
_add("Maut|Mobilität",30,"maut,ausland","aspit","sanef","gavio","tratta","cdt a","direz",
     "nuova sidap","autostrad","forbindelsen","ges karlsbau","via j da")
_add("OePNV|Mobilität",30,"bahn"," s bahn","s-bahn"," bvg","lagardere","bahn berlin")
_add("Parken|Mobilität",31,"parken","parkhaus","parkraum","contipark","p r noord","smile p",
     "vorderkaser")
_add("Bargeld|Bargeld",33,"bargeld","sparkasse","volksbank","raiffeisenbank",
     "wiesbadener volksbank"," vb ")
_add("Shopping|Shopping/Haushalt",35,"shopping","h m de"," h m ","hennes","woolworth","tedi",
     "jysk","manufactum","galeria","media markt","birkenstock","wildling","namuk","new balance",
     "uniqlo","intersport","sportwelt","bergfreunde","boardshop","elitebikes","canyon bicycles",
     "wolle roedel","creativmarkt","kreativ markt","home24","procave","expert","momox","zoxs",
     "multiecom","dogeo","fab store","fabrique","kitsch bitch","freispiel","jadeo","maas natur",
     "mode aus der natur","fair couture","young and brave","zuendstoff","fraulein smilla",
     "glaskiste","annis bunte","holzpferd","babajaga","kids-world","kids coolshop","babyone",
     "kinderstube","spielwaren","arbeitsschutz","alphaflor","blumen","bloemen","plantenkwek",
     "gartencenter","green city","dilling","sostrene","soestrene","fischerbeck","uhrenwerkstatt",
     "kinguin","used-elitebikes","fahrradanhaeng","bikable","hermes germany","amisco","clarijs",
     "hema ","fritz berger","naturkosmetik","idee creativ","maxbean")
_add("Abo|Abo/Digital",15,"vertrag,software","buhl data")
_add("Camper|Camper",18,"camper","fritz berger")
_add("Mobilitaet|Mobilität",29,"auto,vertrag,adac","adac")
_add("Supermarkt-Ausland|Lebensmittel/Drogerie",20,"lebensmittel,ausland","esselunga")
_add("Restaurant|Restaurant/Café",25,"essen-ausser-haus","maxbean")
# --- Runde 5: aus Nutzer-Feedback gelernt (befördert aus user_overrides) ---
_add("Amazon-Digital|Abo/Digital",13,"amazon,digital,vertrag","amazon digital")
# Streaming zusaetzlich per Lastschrift: die paypal_kw-Regeln oben greifen nur, wenn
# ueber PayPal gezahlt wurde. Wer direkt abbucht, landete vorher in 'Sonstiges'.
_add("Streaming|Abo/Digital",15,"streaming,vertrag","netflix","spotify","disney","dazn","wow tv")
# Versicherer: die Einzelregeln oben decken nur die eigenen Anbieter ab. Diese Muster
# treffen die gaengigen Namen und das Wort selbst (viele Anbieter heissen "... Versicherung").
_add("Versicherung|Versicherung",11,"vertrag","versicherung","assekuranz","allianz","huk",
     "debeka","signal iduna","provinzial","barmenia","gothaer","wuerttembergische")
# Energie/Grundversorgung: fast jeder Haushalt hat einen davon.
_add("Energie|Wohnen",12,"strom,fixkosten","stadtwerke","energieversorgung","vattenfall","enbw",
     "yello strom","lichtblick")
# Haushaltsspezifische Regeln (Vermieter, eigene Immobilie, …) kommen aus konfig.json.
# Bewusst zuletzt angehängt, damit sie bei gleicher prio die eingebauten überstimmen.
SEED2 += konfig.EIGENE_REGELN

CONF = {"creditor":0.95,"haendler_kw":0.8,"verwendung_kw":0.75,"paypal_kw":0.8}
HOME = konfig.HEIMAT_ORTE   # Heimatregion aus konfig.json -> Reise-Erkennung

def seed(con):
    con.execute("DELETE FROM rules")
    con.executemany("""INSERT INTO rules(name,prio,match_type,pattern,category,labels,aktiv)
        VALUES (?,?,?,?,?,?,1)""", SEED + SEED2)
    con.commit()

def apply_manual(con):
    """Überlagert die Auto-Kategorisierung mit DEINER manuellen Schicht.
    merchant_rules (ganzer Vertrag/Händler) zuerst, dann tx_manual (einzelne Buchung, gewinnt)."""
    for kt, kv, cat, labels in con.execute(
            "select key_type,key_val,category,labels from merchant_rules"):
        col = "creditor_id" if kt == "creditor" else "haendler_norm"
        ids = [r[0] for r in con.execute(
            f"select tx_id from tx_enrich where lower({col})=?", (str(kv).lower(),))]
        for tid in ids:
            if cat:
                con.execute("""update tx_category set category=?,source_rule='merchant',
                    reason=?,confidence=1.0 where tx_id=? and status<>'ignoriert'""",
                    (cat, f"Vertrag/Händler '{str(kv)[:22]}'", tid))
            for l in (labels or "").split(","):
                if l.strip(): con.execute("insert into tx_labels values(?,?,?)", (tid, l.strip(), "merchant"))
    for tid, cat, labels, ign, dov, note in con.execute(
            "select tx_id,category,labels,ignore,datum_override,note from tx_manual"):
        if cat:
            con.execute("""update tx_category set category=?,source_rule='manual',
                reason='manuell',confidence=1.0 where tx_id=?""", (cat, tid))
        if ign:
            con.execute("update tx_category set status='ignoriert' where tx_id=?", (tid,))
        if dov:
            con.execute("update tx_category set eff_monat=? where tx_id=?", (dov[:7], tid))
        for l in (labels or "").split(","):
            if l.strip(): con.execute("insert into tx_labels values(?,?,?)", (tid, l.strip(), "manual"))

def ensure_schema(con=None):
    """Nur die Tabellen anlegen, ohne Regeln anzuwenden.

    Gebraucht für den ALLERERSTEN Lauf: `branche` (OSM) sucht Händler, die aktuell
    'Sonstiges' sind, und liest dafür `tx_category` — eine Tabelle, die erst
    `apply_rules` erzeugt. Auf einer gewachsenen Datenbank fällt das nie auf, bei einer
    frischen bricht die Pipeline ab. Die gegenseitige Abhängigkeit (branche liefert
    Kategorien-Fallback, braucht aber Kategorien zum Aussuchen) ist gewollt und löst
    sich über die Läufe hinweg auf — sie braucht nur einen leeren Startzustand."""
    own = con is None
    if own:
        con = db.connect()
    con.executescript(SCHEMA)
    con.commit()
    if own:
        con.close()


def apply_rules():
    con = db.connect()
    con.execute("DROP TABLE IF EXISTS tx_category")   # Schema (eff_monat) sicher aktualisieren
    con.executescript(SCHEMA); seed(con)
    try: con.execute("ALTER TABLE tx_manual ADD COLUMN reviewed INTEGER DEFAULT 0")  # Migration
    except Exception: pass
    con.execute("DELETE FROM tx_labels")
    rules = con.execute("""select name,prio,match_type,pattern,category,labels
                           from rules where aktiv=1 order by prio""").fetchall()
    rows = con.execute("""select t.id,t.flow,t.preset_category,t.preset_note,
        lower(coalesce(t.gegenpartei,'')),lower(coalesce(t.verwendungszweck,'')),
        lower(coalesce(e.haendler_norm,'')),coalesce(e.creditor_id,''),
        lower(coalesce(e.paypal_haendler,'')),e.zahlungsart,e.wiederkehrend,
        coalesce(e.ist_vertrag,0)
        from transactions t left join tx_enrich e on e.tx_id=t.id""").fetchall()
    linked = set(r[0] for r in con.execute("select distinct tx_id from tx_mail_links"))
    try: con.execute("ALTER TABLE ki_overrides ADD COLUMN begruendung TEXT")   # Migration
    except Exception: pass
    ki = {r[0].lower(): (r[1], r[2], r[3], r[4]) for r in
          con.execute("select haendler_norm,category,labels,confidence,coalesce(begruendung,'') from ki_overrides")}
    con.execute("""CREATE TABLE IF NOT EXISTS merchant_branche (haendler_norm TEXT PRIMARY KEY,
        query TEXT, osm_class TEXT, osm_type TEXT, osm_name TEXT, category TEXT, ts TEXT)""")
    branche = {r[0].lower(): (r[1], r[2]) for r in   # OSM-Branche (mechanischer Fallback)
          con.execute("select haendler_norm,category,osm_type from merchant_branche where coalesce(category,'')<>''")}
    con.execute("""CREATE TABLE IF NOT EXISTS user_overrides
        (tx_id TEXT PRIMARY KEY, category TEXT, labels TEXT)""")
    uo = {r[0]: (r[1], r[2]) for r in
          con.execute("select tx_id,category,labels from user_overrides")}
    cat_rows=[]; lab_rows=[]
    for (tid,flow,preset,pnote,gp,vz,hn,cred,pph,art,wk,vtg) in rows:
        cat=None; src=None; reason=None; conf=None; status="ok"; labels=set()
        if tid in uo:                       # Nutzer-Korrektur schlaegt alles
            ucat, ulab = uo[tid]
            cat,src,reason,conf,status = ucat,"user","manuell korrigiert",1.0,"user"
            if ulab:
                for l in str(ulab).split(","):
                    if l.strip(): labels.add(l.strip())
        elif flow=="intern":
            cat,src,reason,conf,status = "Umbuchung intern","systemgrenze",pnote or "intern",1.0,"intern_excl"
        elif preset:
            cat,src,reason,conf = preset,"kontenkarte",pnote or preset,1.0
        elif flow=="einnahme":
            cat,src,reason,conf = "Einnahme","flow","Eingang",0.6
        else:
            if art == "PayPal" and not pph:
                cat,src,reason,conf,status = ("PayPal (ungeklärt)","paypal-block",
                    "PayPal-Ausgabe ohne Händler/Beleg",0.3,"ki-vorschlag")
                labels.update(["paypal-ungeklaert","beleg_fehlt"])
            for (name,prio,mt,pat,rcat,rlabels) in rules:
                hay = {"haendler_kw":hn+" "+gp,"verwendung_kw":vz,
                       "paypal_kw":pph,"creditor":cred}.get(mt,"")
                ok = (cred==pat) if mt=="creditor" else word_start(pat, hay)
                if ok:
                    if cat is None and rcat:
                        cat,src,reason,conf = rcat,name,f"{mt}~'{pat}'",CONF.get(mt,0.7)
                    if rlabels:
                        for l in rlabels.split(","): labels.add(l.strip())
            if cat is None and hn in ki:
                rc, rl, rconf, rbeg = ki[hn]
                # Begruendung als reason -> im Editor als 'why' sichtbar und pruefbar
                reason = f"KI: {rbeg}" if rbeg else f"KI: Haendler '{hn[:24]}'"
                cat,src,conf,status = rc,"ki",rconf or 0.6,"ki-vorschlag"
                if rl:
                    for l in rl.split(","): labels.add(l.strip())
            if cat is None and hn in branche:
                bc, btyp = branche[hn]
                cat,src,reason,conf,status = bc,"osm",f"OSM-Branche: {btyp}",0.5,"branche-osm"
            if cat is None:
                cat,src,reason,conf,status = "Sonstiges","-","kein Regel-Treffer",0.0,"unkategorisiert"
        # programmatische Labels: Vertrag (Kadenz) vs. wiederkehrend. fixkosten kommt NICHT mehr
        # hier, sondern aus der contracts-Tabelle (apply_fixkosten) = EINE Wahrheitsquelle.
        if vtg:
            labels.add("vertrag")
        elif wk:
            labels.add("wiederkehrend")
        # Kategorien, die immer Fixkosten sind. Eigene (z.B. "Immobilie X") aus konfig.json.
        if cat in ("Versicherung","Abo/Digital","Kredit/Immobilie") or cat in konfig.KAT_IMMER_VERTRAG:
            labels.add("vertrag")
        # Beleg-Status (ehrlich markieren)
        if flow=="ausgabe" and art in ("PayPal","Karte") and tid not in linked \
           and cat in ("Shopping/Haushalt","Abo/Digital","Sonstiges"):
            labels.add("beleg_fehlt")
        cat_rows.append((tid,cat,src,reason,conf,status))
        for l in labels: lab_rows.append((tid,l,src or "auto"))
    con.executemany("""INSERT OR REPLACE INTO tx_category
        (tx_id,category,source_rule,reason,confidence,status) VALUES (?,?,?,?,?,?)""", cat_rows)
    con.executemany("INSERT INTO tx_labels VALUES (?,?,?)",lab_rows)
    con.commit()
    con.execute("""UPDATE tx_category SET eff_monat=
        (SELECT monat FROM transactions t WHERE t.id=tx_category.tx_id)""")
    apply_manual(con)                     # manuelle Schicht zuerst
    trip_detect(con)                      # DANN Urlaub-Stempel -> bestätigte Reise gewinnt über manuell
    import contracts                      # mechanisch, Teil jedes Neulaufs (reproduzierbar)
    contracts.derive(con)
    contracts.normalize_months(con)
    contracts.apply_fixkosten(con)        # Fixkosten-Label = Vertrags-Buchungen (eine Quelle)
    con.commit(); con.close()

TRIP_EXC_ORT = ("kelsterbach", "internet")   # Automat/Online, kein Reiseort
TRIP_BRIDGE = 4        # Lücke (Tage ohne Auswärts-Einkauf) bis zu der eine Reise zusammenbleibt
TRIP_MIN_SPAN = 2      # > 2 Tage am Stück (Start..Ende >= 2 -> mind. 3 Kalendertage)

def _ortclean(o):
    o = re.sub(r"[\d.]+", " ", o or "")
    return re.sub(r"\s+", " ", o).strip().title()

def trip_detect(con):
    """Reise = zusammenhängend außerhalb der Heimatregion > 2 Tage (Kandidat -> Nutzer bestätigt).
    Robust: Lücken bis TRIP_BRIDGE Tage überbrücken, aber bei Heimat-Einkauf dazwischen trennen.
    Eine Reise = EIN Trip mit mehreren Orten."""
    import datetime
    from collections import Counter, defaultdict
    D = lambda s: datetime.date.fromisoformat(s[:10])
    # Online/Abo/Nicht-Reise-Buchungen ausklammern (haben oft einen falschen 'ort' aus dem
    # Karten-Text, z.B. Anthropic/Mistral/OpenAI). Digitale Abos + wiederkehrende raus.
    # Eigene Nicht-Reise-Kategorien (z.B. ein Nebengewerbe) kommen aus konfig.json.
    EXCL_CAT = ("Abo/Digital", "Sparen/Invest", "Versicherung", "Gebühren",
                "Kredit/Immobilie", "Umbuchung intern", "Einnahme", "PayPal (ungeklärt)"
                ) + tuple(konfig.KAT_NICHT_REISE)
    excl = set(r[0] for r in con.execute(
        f"select tx_id from tx_category where category in ({','.join('?'*len(EXCL_CAT))})", EXCL_CAT))
    excl |= set(r[0] for r in con.execute(
        "select tx_id from tx_labels where label in ('vertrag','wiederkehrend','abo')"))
    # Manuelle Schicht gewinnt bei der ZUORDNUNG (Pass 1): was per X ignoriert oder auf eine
    # andere Kategorie als Urlaub gesetzt wurde, bekommt weder Trip-Label noch Kosten.
    # Bewusst NICHT in der Tages-/Run-Erkennung unten: eine einzelne Umkategorisierung darf
    # keinen Reisetag loeschen, sonst zerfaellt die Reise und ihre Bestaetigung geht verloren.
    excl_tx = excl | set(r[0] for r in con.execute(
        f"select t.id from transactions t join tx_manual m on m.tx_id=t.id where {db.TRIP_TX_EXCL_SQL}"))
    rows = con.execute("""select t.id,t.datum,e.ort from transactions t join tx_enrich e on e.tx_id=t.id
        where e.zahlungsart='Karte' and t.flow='ausgabe' and e.ort is not null and e.ort<>''""").fetchall()
    away_days, home_days = set(), set()
    for tid, datum, ort in rows:
        o = (ort or "").lower()
        if not o: continue
        # Heim-Einkauf zählt IMMER als Heim-Tag (auch wiederkehrend/abo): an dem Tag warst du
        # nachweislich zuhause -> trennt zwei echte Reisen, zwischen denen du daheim warst.
        if any(h in o for h in HOME): home_days.add(datum)
        elif tid not in excl and not any(x in o for x in TRIP_EXC_ORT): away_days.add(datum)
    away = sorted(away_days)
    # Runs bilden (Lücke<=BRIDGE überbrücken, bei Heim-Einkauf dazwischen trennen)
    runs, cur = [], []
    for d in away:
        if cur:
            prev = cur[-1]
            gap = (D(d) - D(prev)).days
            home_between = any(prev < hd < d for hd in home_days)
            split = any(prev < sd <= d for sd in konfig.REISE_TRENNUNGEN)
            if gap > TRIP_BRIDGE or home_between or split:
                runs.append(cur); cur = []
        cur.append(d)
    if cur: runs.append(cur)

    # Pass 1: je Run die Auswärts-Buchungen + Orte sammeln
    cand = []
    for run in runs:
        start, ende = run[0], run[-1]
        if (D(ende) - D(start)).days < TRIP_MIN_SPAN: continue   # Tagesausflug -> kein Urlaub
        txs = con.execute("""select t.id,t.betrag,e.ort from transactions t join tx_enrich e on e.tx_id=t.id
            where t.datum between ? and ? and t.flow='ausgabe' and e.ort is not null""", (start, ende)).fetchall()
        ids, orte, cost = [], Counter(), 0.0
        for tid, b, ort in txs:
            o = (ort or "").lower()
            if tid in excl_tx: continue
            if o and not any(h in o for h in HOME) and not any(x in o for x in TRIP_EXC_ORT):
                ids.append(tid); orte[_ortclean(ort)] += 1; cost += -b
        if ids: cand.append({"start": start, "ende": ende, "ids": ids, "orte": orte, "cost": round(cost)})
    # Orte, die in >=3 Reisen vorkommen, sind keine Reiseorte (Transit) -> raus
    ort_trips = Counter()
    for c in cand:
        for o in c["orte"]: ort_trips[o] += 1
    GEN = {"Internet", "Paypal"}
    good = lambda o: ort_trips[o] < 3 and o not in GEN

    # trips-Tabelle (Status/Name über Re-Runs erhalten)
    con.execute("""CREATE TABLE IF NOT EXISTS trips
        (id TEXT PRIMARY KEY, start TEXT, ende TEXT, orte TEXT, kosten REAL, status TEXT, name TEXT)""")
    prev = {r[0]: (r[1], r[2]) for r in con.execute("select id,status,name from trips")}
    prev_ranges = con.execute("select start,ende,status,name from trips").fetchall()
    con.execute("DELETE FROM trips")
    n = 0
    for c in cand:
        tid = "TRIP-" + c["start"]
        orte = ", ".join(o for o, _ in c["orte"].most_common() if good(o))[:120] or c["start"][:7]
        st, nm = prev.get(tid, (None, None))
        if st is None:                 # neuer Trip (z.B. durch Split entstanden):
            for ps, pe, pst, pnm in prev_ranges:   # erbt 'confirmed', wenn er VOLL in einer
                if pst == "confirmed" and ps <= c["start"] and c["ende"] <= pe:  # früher bestätigten
                    st, nm = "confirmed", pnm; break                            # Reise lag
            if st is None: st = "candidate"
        con.execute("INSERT INTO trips VALUES (?,?,?,?,?,?,?)",
                    (tid, c["start"], c["ende"], orte, c["cost"], st, nm))
        if st == "rejected":
            n += 1; continue
        src = "trip-confirm" if st == "confirmed" else "trip-detect"
        for txid in c["ids"]:
            con.execute("INSERT INTO tx_labels VALUES (?,?,?)", (txid, tid, "trip-detect"))  # nur Gruppierung
            # URLAUBSSTEMPEL für JEDE erkannte Reise, Kandidat wie bestätigt: was in einer Reise
            # liegt, IST Urlaub -> Kategorie->Urlaub + Label(s). Damit ist die Reisezugehörigkeit
            # die einzige Quelle der Kategorie; wer eine Buchung herausnehmen will, nimmt sie mit
            # dem X raus (siehe db.TRIP_TX_EXCL_SQL), nicht über eine abweichende Kategorie.
            # 'rejected' oben ist der einzige Weg, den Stempel wieder loszuwerden.
            con.execute("INSERT INTO tx_labels VALUES (?,?,?)", (txid, "urlaub", src))
            if nm: con.execute("INSERT INTO tx_labels VALUES (?,?,?)", (txid, nm, src))
            con.execute("update tx_category set category='Urlaub',source_rule='urlaub',reason=? "
                        "where tx_id=?", ("Reise bestätigt" if st == "confirmed" else "Reise erkannt", txid))
        n += 1
    print(f"Reise-Kandidaten: {n}")

if __name__ == "__main__":
    apply_rules()
    con=db.connect()
    tot=con.execute("select count(*) from tx_category").fetchone()[0]
    print("kategorisiert:",tot)
    print("Status:",dict(con.execute("select status,count(*) from tx_category group by status").fetchall()))
    print("Top-Kategorien:")
    for c,n in con.execute("select category,count(*) from tx_category group by category order by 2 desc").fetchall():
        print(f"   {c:22} {n}")
    con.close()

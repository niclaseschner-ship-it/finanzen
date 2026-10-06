"""Anmeldung ueber den xbuddy-Cookie (`xbuddy_session`, xbuddy auth.md AUTH-2).

Gleicher Cookie, gleiche Signatur wie bei xbuddy: HMAC-SHA256 mit dem Bot-Token als
Schluessel ueber "session\\n<subjekt>\\n<exp>", Form "<subjekt>.<exp>.<hmac_hex>".
Es gibt kein zweites Geheimnis und keine eigene Anmeldeseite — wer bei xbuddy
angemeldet ist, ist es hier auch, sofern der Browser den Cookie mitschickt (Cookies
gelten je Hostname, nicht je Port: gleicher Tailscale-Name, anderer Port genuegt).

Das Subjekt ist eine Telegram-user_id (Eltern) oder eine Geraete-Kennung (`geraet-…`,
vergeben bei "Geraet anlegen", auch fuer Kindertablets). FINANZEN_ERLAUBTE_IDS legt
fest, welche Subjekte durchkommen: eine Liste einzelner Subjekte, oder `*` fuer jeden
gueltigen xbuddy-Cookie (dann funktioniert jedes neu gekoppelte Geraet ohne
Einzelfreigabe).

Reines Standard-Python. Das Verfahren ist bewusst nachgebaut statt aus dem
xbuddy-Repo importiert, damit die Finanz-App nicht an dessen Deploys haengt; bricht
xbuddy die Signatur um, schlaegt test_auth_xbuddy hier an.
"""
import hashlib, hmac, time

COOKIE_NAME = "xbuddy_session"
_DOMAIN = "session"


def _signatur(subjekt, exp, bot_token):
    msg = "%s\n%s\n%d" % (_DOMAIN, subjekt, exp)
    return hmac.new(bot_token.encode("utf-8"), msg.encode("utf-8"), hashlib.sha256).hexdigest()


def pruefe(cookie_wert, bot_token, jetzt=None):
    """Subjekt des Cookies, wenn Signatur und Ablauf stimmen, sonst None."""
    if not cookie_wert or not bot_token:
        return None
    teile = cookie_wert.split(".")
    if len(teile) != 3:
        return None
    subjekt, exp_s, sig = teile
    if not subjekt or not sig:
        return None
    try:
        exp = int(exp_s)
    except ValueError:
        return None
    if not hmac.compare_digest(_signatur(subjekt, exp, bot_token), sig):
        return None
    if int(jetzt if jetzt is not None else time.time()) > exp:
        return None
    return subjekt


def cookie_aus_header(cookie_header):
    """Wert von xbuddy_session aus einem Cookie-Header, sonst None."""
    for teil in (cookie_header or "").split(";"):
        name, _, wert = teil.strip().partition("=")
        if name == COOKIE_NAME:
            return wert
    return None


def erlaubt(cookie_header, bot_token, erlaubte_ids, jetzt=None):
    """True nur, wenn der Cookie gueltig ist UND sein Subjekt auf der Liste steht
    (oder die Liste `*` enthaelt: dann genuegt jeder gueltige Cookie)."""
    subjekt = pruefe(cookie_aus_header(cookie_header), bot_token, jetzt)
    return subjekt is not None and ("*" in erlaubte_ids or subjekt in erlaubte_ids)


def aus_umgebung(env):
    """(aktiv, bot_token, erlaubte_ids, oeffentlicher_host) aus der Umgebung.

    Aktiv ist die Pruefung mit FINANZEN_AUTH=xbuddy. Fehlen dann Token oder
    Erlaubtenliste, ist das ein Konfigurationsfehler und kein stilles Offen:
    ValueError, die App startet nicht.
    """
    if (env.get("FINANZEN_AUTH") or "").strip().lower() != "xbuddy":
        return False, "", frozenset(), ""
    token = (env.get("ELTERNCHAT_BOT_TOKEN") or "").strip()
    ids = frozenset(i.strip() for i in (env.get("FINANZEN_ERLAUBTE_IDS") or "").split(",") if i.strip())
    host = (env.get("FINANZEN_OEFFENTLICHER_HOST") or "").strip().lower()
    if not token:
        raise ValueError("FINANZEN_AUTH=xbuddy, aber ELTERNCHAT_BOT_TOKEN fehlt")
    if not ids:
        raise ValueError("FINANZEN_AUTH=xbuddy, aber FINANZEN_ERLAUBTE_IDS ist leer")
    if not host:
        raise ValueError("FINANZEN_AUTH=xbuddy, aber FINANZEN_OEFFENTLICHER_HOST fehlt")
    return True, token, ids, host

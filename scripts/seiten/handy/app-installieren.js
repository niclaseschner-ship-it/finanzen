/**
 * app-installieren.js — Standard-Installationsleiste fuer alle Web-Apps auf dem Pi.
 *
 * Vorbild ist das gemeinsame Skript der xbuddy-Apps (xbuddy, seiten/static/
 * app-installieren.js, #1955). Diese Fassung ist davon unabhaengig, damit keine
 * App an xbuddys Deploys haengt. Jede App bekommt eine Kopie dieser Datei und
 * bindet sie ein:
 *
 *   <script src="app-installieren.js" data-name="Unsere To-do" defer></script>
 *
 * Attribute (alle optional):
 *   data-name   Name in der Leiste; sonst short_name aus dem Manifest, sonst <title>.
 *   data-farbe  Knopffarbe; sonst <meta name="theme-color">.
 *   data-nur-auf-wunsch  Leiste nur bei ?installieren=1 in der Adresse (xbuddy-Verhalten).
 *
 * Verhalten:
 *   - Laeuft die Seite schon als App (standalone), zeigt sie nichts.
 *   - Android, Chrome, Edge: wartet auf `beforeinstallprompt`, dann Knopf "App installieren".
 *     Kommt das Ereignis nicht (App schon installiert, Firefox), bleibt alles still.
 *   - iPhone/iPad: Hinweis "Teilen, dann Zum Home-Bildschirm".
 *   - Telegram-WebView: Knopf, der die Seite im Browser oeffnet.
 *   - "Spaeter" blendet die Leiste fuer 30 Tage aus (je App-Pfad, im localStorage).
 *   - Solange die Leiste steht, traegt <html> die Klasse `app-installieren-sichtbar`
 *     und die CSS-Variable `--app-installieren-hoehe`; damit kann eine App eigene
 *     unten fixierte Knoepfe nach oben schieben.
 *
 * Leitfaden: Gedaechtnis `werkzeuge/pwa-leitfaden.md`.
 * Quelle: ~/repos/werkzeugkasten/vorlagen/pwa/app-installieren.js
 */
(function () {
  "use strict";

  var skript = document.currentScript;
  var PAUSE_TAGE = 30;
  var schluessel = "app-installieren-spaeter:" + location.pathname.replace(/[^/]*$/, "");

  function attr(name) { return skript ? skript.getAttribute(name) : null; }

  if (attr("data-nur-auf-wunsch") !== null) {
    try {
      if (new URLSearchParams(location.search).get("installieren") !== "1") return;
    } catch (e) { return; }
  }

  function laeuftAlsApp() {
    return window.matchMedia("(display-mode: standalone)").matches ||
      window.matchMedia("(display-mode: fullscreen)").matches ||
      window.navigator.standalone === true;
  }

  function pausiert() {
    try {
      var bis = parseInt(localStorage.getItem(schluessel) || "0", 10);
      return bis > Date.now();
    } catch (e) { return false; }
  }

  function pausieren() {
    try { localStorage.setItem(schluessel, String(Date.now() + PAUSE_TAGE * 864e5)); } catch (e) {}
  }

  function farbe() {
    var f = attr("data-farbe");
    if (f) return f;
    var meta = document.querySelector('meta[name="theme-color"]:not([media])') ||
      document.querySelector('meta[name="theme-color"]');
    return (meta && meta.content) || "#2f6f5e";
  }

  var name = attr("data-name") || document.title || "Diese Seite";

  function nameAusManifest() {
    if (attr("data-name")) return Promise.resolve();
    var link = document.querySelector('link[rel="manifest"]');
    if (!link) return Promise.resolve();
    return fetch(link.href).then(function (r) { return r.json(); }).then(function (m) {
      name = m.short_name || m.name || name;
    }).catch(function () {});
  }

  function stil() {
    var s = document.createElement("style");
    s.textContent =
      ".ai-leiste{position:fixed;left:0;right:0;bottom:0;z-index:2147483000;margin:0;" +
      "background:Canvas;color:CanvasText;border-top:2px solid var(--ai-farbe);" +
      "padding:12px 16px calc(12px + env(safe-area-inset-bottom,0px));" +
      "font:15px/1.4 system-ui,-apple-system,'Segoe UI',Roboto,sans-serif;" +
      "box-shadow:0 -2px 12px rgba(0,0,0,.18);color-scheme:light dark}" +
      ".ai-innen{max-width:640px;margin:0 auto}" +
      ".ai-leiste p{margin:0 0 10px}" +
      ".ai-knoepfe{display:flex;gap:8px}" +
      ".ai-knopf{flex:1;box-sizing:border-box;padding:12px 16px;font:inherit;font-size:16px;" +
      "font-weight:600;border:none;border-radius:10px;background:var(--ai-farbe);color:#fff;cursor:pointer}" +
      ".ai-spaeter{flex:0 0 auto;background:transparent;color:inherit;border:1px solid currentColor;" +
      "opacity:.75;font-weight:500}" +
      ".ai-knopf:active{opacity:.85}";
    document.head.appendChild(s);
  }

  var leiste = null;

  function zeigen(text, knopfText, aktion) {
    entfernen();
    stil();
    leiste = document.createElement("section");
    leiste.className = "ai-leiste";
    leiste.setAttribute("aria-label", "Als App installieren");
    leiste.style.setProperty("--ai-farbe", farbe());
    var innen = document.createElement("div");
    innen.className = "ai-innen";
    var p = document.createElement("p");
    var stark = document.createElement("strong");
    stark.textContent = name + " als App";
    p.appendChild(stark);
    p.appendChild(document.createTextNode(" – " + text));
    innen.appendChild(p);
    var knoepfe = document.createElement("div");
    knoepfe.className = "ai-knoepfe";
    if (knopfText) {
      var k = document.createElement("button");
      k.type = "button"; k.className = "ai-knopf"; k.textContent = knopfText;
      k.addEventListener("click", aktion);
      knoepfe.appendChild(k);
    }
    var spaeter = document.createElement("button");
    spaeter.type = "button"; spaeter.className = "ai-knopf ai-spaeter";
    spaeter.textContent = knopfText ? "Später" : "Verstanden";
    spaeter.addEventListener("click", function () { pausieren(); entfernen(); });
    knoepfe.appendChild(spaeter);
    innen.appendChild(knoepfe);
    leiste.appendChild(innen);
    document.body.appendChild(leiste);
    var wurzel = document.documentElement;
    wurzel.classList.add("app-installieren-sichtbar");
    wurzel.style.setProperty("--app-installieren-hoehe", leiste.offsetHeight + "px");
  }

  function entfernen() {
    if (leiste) { leiste.remove(); leiste = null; }
    document.documentElement.classList.remove("app-installieren-sichtbar");
    document.documentElement.style.removeProperty("--app-installieren-hoehe");
  }

  function haupt() {
    if (laeuftAlsApp() || pausiert()) return;

    var tg = window.Telegram && window.Telegram.WebApp;
    if (tg) {
      nameAusManifest().then(function () {
        zeigen("in Telegram geht das nicht. Öffne die Seite im Browser und installiere sie dort.",
          "Im Browser öffnen", function () {
            if (typeof tg.openLink === "function") tg.openLink(location.href, { tryBrowser: "chrome" });
            else window.open(location.href, "_blank", "noopener,noreferrer");
          });
      });
      return;
    }

    var ios = /iphone|ipad|ipod/i.test(navigator.userAgent) ||
      (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
    if (ios) {
      nameAusManifest().then(function () {
        zeigen("unten auf „Teilen“ tippen, dann „Zum Home-Bildschirm“.", null, null);
      });
      return;
    }

    var aufschub = null;
    window.addEventListener("beforeinstallprompt", function (ev) {
      ev.preventDefault();
      aufschub = ev;
      nameAusManifest().then(function () {
        zeigen("mit eigenem Symbol auf dem Startbildschirm.", "App installieren", function () {
          if (!aufschub) return;
          aufschub.prompt();
          aufschub.userChoice.catch(function () { return null; }).then(function () {
            aufschub = null;
            entfernen();
          });
        });
      });
    });
    window.addEventListener("appinstalled", entfernen);
  }

  if (document.body) haupt();
  else document.addEventListener("DOMContentLoaded", haupt);
})();

// Service Worker der Finanz-Handy-App (/finanzen/, Handy-Ansicht).
//
// Die Seite ist eine einzige Datei mit eingebettetem Skript (Leitfaden Regel 5a):
// immer zuerst das Netz, der Cache ist nur das Polster fuer offline. Gecacht wird
// nur, was mit 200 zurueckkommt — eine 401 (kein xbuddy-Cookie) landet nie im
// Cache. Schreibende Anfragen (POST) gehen nie durch den Cache.
'use strict';

const CACHE = 'finanzen-handy-v3';
const WURZEL = new URL('./', self.registration.scope).pathname;
const SCHALE = ['app-installieren.js', 'manifest.webmanifest', 'icon-192.png', 'icon-512.png', 'apple-touch-icon.png']
  .map((weg) => WURZEL + weg);

self.addEventListener('install', (e) => {
  e.waitUntil(caches.open(CACHE).then(async (c) => {
    await c.addAll(SCHALE);
    // Die Seite selbst nur, wenn sie mit 200 kommt (ohne Cookie gibt es 401).
    try {
      const seite = await fetch(WURZEL, { cache: 'no-store', credentials: 'same-origin' });
      if (seite.status === 200 && seite.headers.get('X-Finanzen-Ansicht') === 'handy') await c.put(WURZEL, seite);
    } catch (_) { /* offline beim Installieren: dann beim naechsten Laden */ }
  }));
});

// Eine einzige Datei: alte und neue Fassung koennen sich nicht mischen. Deshalb
// darf der Worker gleich uebernehmen, sonst laege beim ersten Oeffnen nichts im Polster.
self.addEventListener('activate', (e) => {
  e.waitUntil(caches.keys().then((namen) =>
    Promise.all(namen.filter((n) => n !== CACHE).map((n) => caches.delete(n))))
    .then(() => self.clients.claim()));
});

// Die Startseite nur ablegen, wenn der Server die Handy-Ansicht geliefert hat.
async function startseite(anfrage) {
  const cache = await caches.open(CACHE);
  try {
    const antwort = await fetch(anfrage, { cache: 'no-store' });
    if (antwort.status === 200 && antwort.headers.get('X-Finanzen-Ansicht') === 'handy') {
      cache.put(WURZEL, antwort.clone());
    }
    return antwort;
  } catch (fehler) {
    const alt = await cache.match(WURZEL);
    if (!alt) throw fehler;
    return alt;
  }
}

async function netzZuerst(anfrage, schluessel) {
  const cache = await caches.open(CACHE);
  try {
    const antwort = await fetch(anfrage, { cache: 'no-store' });
    if (antwort.status === 200) cache.put(schluessel, antwort.clone());
    return antwort;
  } catch (fehler) {
    const alt = await cache.match(schluessel);
    if (!alt) throw fehler;
    const kopf = new Headers(alt.headers);
    kopf.set('X-Finanzen-Offline', '1');
    return new Response(alt.body, { status: alt.status, headers: kopf });
  }
}

// Unter /finanzen/ liegen auch die Desktop-Seiten. Abgelegt wird nur, was die Handy-App
// braucht: die Startseite in der Handy-Ansicht, ihre Dateien und api/handy/*.
const HANDY_DATEIEN = new Set(SCHALE);

self.addEventListener('fetch', (e) => {
  const anfrage = e.request;
  if (anfrage.method !== 'GET') return;
  const url = new URL(anfrage.url);
  if (url.origin !== self.location.origin || !url.pathname.startsWith(WURZEL)) return;
  if (anfrage.mode === 'navigate') {
    if (url.pathname !== WURZEL || url.search) return;     // Desktop-Seiten und ?ansicht=… nie abfangen
    e.respondWith(startseite(anfrage));
    return;
  }
  if (!HANDY_DATEIEN.has(url.pathname) && !url.pathname.startsWith(WURZEL + 'api/handy/')) return;
  // Suchergebnisse nicht ablegen, sonst waechst der Cache mit jedem Tastendruck.
  if (url.searchParams.has('q')) return;
  e.respondWith(netzZuerst(anfrage, url.pathname + url.search));
});

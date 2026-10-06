/* Demo ohne Server: beantwortet die Anfragen der echten Seiten aus daten.js.
 *
 * Die Seiten in diesem Ordner sind die echten Seiten der App (gebaut von bauen.py), nur
 * mit dem erfundenen Demo-Haushalt. Statt an app.py gehen ihre fetch('api/...')-Aufrufe
 * hierher. Lesen kommt aus window.DEMO_DATEN, Ändern (Kategorie, Notiz, geprüft,
 * Verträge, Reisen, Vorsorge) wird im sessionStorage dieses Tabs gemerkt — so bleibt es
 * beim Seitenwechsel erhalten, geht aber nirgendwohin. Summen und Statistik werden nicht
 * neu gerechnet; das macht in der echten App die Pipeline.
 */
(function () {
  'use strict';
  var D = window.DEMO_DATEN || {};
  var SCHLUESSEL = 'finanzen-demo-v1';
  var z = {};
  try { z = JSON.parse(sessionStorage.getItem(SCHLUESSEL) || '{}'); } catch (e) { z = {}; }
  z.tx = z.tx || {}; z.vtg = z.vtg || {}; z.reise = z.reise || {};
  function merken() { try { sessionStorage.setItem(SCHLUESSEL, JSON.stringify(z)); } catch (e) {} }

  function json(obj, status) {
    return Promise.resolve(new Response(JSON.stringify(obj), {
      status: status || 200, headers: { 'Content-Type': 'application/json' } }));
  }
  function kopie(o) { return JSON.parse(JSON.stringify(o)); }
  function hat(o, k) { return Object.prototype.hasOwnProperty.call(o, k); }

  // ---- Änderungen über die Ausgangsdaten legen --------------------------------
  // Eine Änderung setzt den Status wie save_edit in app.py: 'ok', bei ignoriert 'ignoriert'.
  function zustand(o) { return o.ign ? 'ignoriert' : 'ok'; }
  function desktop(r) {
    var o = z.tx[r.id]; if (!o) return r;
    r = kopie(r);
    if (hat(o, 'cat')) { r.cat = o.cat; r.src = 'manual'; r.why = 'manuell'; }
    if (hat(o, 'labels')) r.labels = o.labels;
    if (hat(o, 'note')) r.note = o.note;
    if (hat(o, 'rev')) r.reviewed = o.rev;
    if (hat(o, 'ign')) r.ignore = o.ign;
    r.status = zustand(o);
    return r;
  }
  function handy(r) {
    var o = z.tx[r.id]; if (!o) return r;
    r = kopie(r);
    if (hat(o, 'cat')) { r.cat = o.cat; r.src = 'manual'; }
    if (hat(o, 'note')) r.note = o.note;
    if (hat(o, 'rev')) r.rev = o.rev;
    if (hat(o, 'ign')) r.ign = o.ign;
    r.st = zustand(o);
    return r;
  }
  function vertraege(liste) {
    return liste.map(function (c) { return z.vtg[c.id] ? Object.assign(kopie(c), z.vtg[c.id]) : c; });
  }
  function reisen(liste) {
    return liste.map(function (t) { return z.reise[t.id] ? Object.assign(kopie(t), z.reise[t.id]) : t; });
  }
  function meta() { return z.meta || D.meta; }

  // Handy-Buchungen wie handy.buchungen(): Monat, Kategorie, Suchtext, Prüfliste
  var OFFEN = { 'unkategorisiert': 1, 'ki-vorschlag': 1, 'branche-osm': 1 };
  function handyBuchungen(q) {
    var such = (q.get('q') || '').toLowerCase();
    var aus = D.alle.map(handy).filter(function (r) {
      if (q.get('monat') && r.m !== q.get('monat')) return false;
      if (q.get('kat') && r.cat !== q.get('kat')) return false;
      if (q.get('offen') === '1' && !(!r.rev && !r.ign && OFFEN[r.st])) return false;
      if (such) {
        var text = [r.h, r.vz, r.prod, r.note, r.cat].join(' ').toLowerCase();
        if (text.indexOf(such) < 0) return false;
      }
      return true;
    });
    return aus.slice(0, 300);
  }

  function lesen(weg, q) {
    switch (weg) {
      case 'handy/uebersicht': return json(D.uebersicht);
      case 'handy/kategorien': return json(meta().cats);
      case 'handy/vertraege': return json(vertraege(D.handy_vertraege));
      case 'handy/vermoegen': return json(D.handy_vermoegen);
      case 'handy/buchungen': return json(handyBuchungen(q));
      case 'handy/vertrag': return json(D.vertrag[q.get('id')] || []);
      case 'rows':
        var basis = q.get('trip') ? D.rows_reise[q.get('trip')] : q.get('contract') ? D.rows_vertrag[q.get('contract')] : D.rows;
        return json((basis || []).map(desktop));
      case 'meta': return json(meta());
      case 'contracts': return json(vertraege(D.contracts));
      case 'trips': return json(reisen(D.trips));
      case 'mail': return json(D.mail[q.get('tx_id')] || { found: false, related: [] });
      case 'vermoegen': return json(D.vermoegen);
      case 'vorsorge': return json(z.vorsorge ? { plan: z.vorsorge } : D.vorsorge);
      case 'ist_werte': return json(D.ist_werte);
    }
    return Promise.resolve(new Response('In der Demo nicht enthalten', { status: 404 }));
  }

  function zeileDesktop(id) {
    for (var i = 0; i < D.rows.length; i++) if (D.rows[i].id === id) return desktop(D.rows[i]);
    return null;
  }
  function zeileHandy(id) {
    for (var i = 0; i < D.alle.length; i++) if (D.alle[i].id === id) return handy(D.alle[i]);
    return null;
  }
  function aendern(id, p) {
    var o = z.tx[id] || (z.tx[id] = {});
    if (hat(p, 'category') && p.category) o.cat = p.category;
    if (hat(p, 'labels')) o.labels = p.labels;
    if (hat(p, 'note')) o.note = p.note;
    if (hat(p, 'reviewed')) o.rev = p.reviewed ? 1 : 0;
    if (hat(p, 'ignore')) o.ign = p.ignore ? 1 : 0;
  }

  function schreiben(weg, p) {
    var res;
    switch (weg) {
      case 'handy/bearbeiten':
        aendern(p.tx_id, p); merken(); return json({ row: zeileHandy(p.tx_id) });
      case 'edit':
        if (p.scope === 'merchant') {               // gilt für alle Buchungen des Händlers
          D.rows.forEach(function (r) {
            if ((p.cred && r.cred === p.cred) || (!p.cred && r.hkey === p.hkey))
              aendern(r.id, { category: p.category, labels: p.labels });
          });
          merken(); return json({ full: true });
        }
        aendern(p.tx_id, p); merken(); return json({ row: zeileDesktop(p.tx_id) });
      case 'addcat':
        res = kopie(meta()); if (p.name && res.cats.indexOf(p.name) < 0) res.cats.push(p.name);
        z.meta = res; merken(); return json({ cats: res.cats });
      case 'addlabel':
        res = kopie(meta()); if (p.name && res.labels.indexOf(p.name) < 0) { res.labels.push(p.name); res.labels.sort(); }
        z.meta = res; merken(); return json({ labels: res.labels });
      case 'contract_edit':
        var v = z.vtg[p.id] || (z.vtg[p.id] = {});
        if (hat(p, 'name')) v.name = p.name;
        if (hat(p, 'status')) v.status = p.status;
        if (hat(p, 'category')) v.kategorie = p.category;
        if (hat(p, 'aktiv')) { v.aktiv = p.aktiv == null ? 1 : (p.aktiv ? 1 : 0); v.aktiv_manual = p.aktiv != null; }
        merken(); return json({ ok: true, contracts: vertraege(D.contracts) });
      case 'trip_edit':
        var t = z.reise[p.id] || (z.reise[p.id] = {});
        if (hat(p, 'status')) t.status = p.status;
        if (hat(p, 'name')) t.name = p.name;
        merken(); return json({ ok: true, trips: reisen(D.trips) });
      case 'vorsorge':
        z.vorsorge = p.plan || {}; merken(); return json({ ok: true });
      case 'rebuild':
        return json({ ok: true });
    }
    return json({ fehler: 'in der Demo nicht möglich' }, 404);
  }

  var echt = window.fetch ? window.fetch.bind(window) : null;
  window.fetch = function (eingabe, opt) {
    var adresse = typeof eingabe === 'string' ? eingabe : (eingabe && eingabe.url) || '';
    var u;
    try { u = new URL(adresse, location.href); } catch (e) { return echt(eingabe, opt); }
    var i = u.pathname.indexOf('/api/');
    if (i < 0) return echt(eingabe, opt);
    var weg = u.pathname.slice(i + 5);
    var methode = ((opt && opt.method) || 'GET').toUpperCase();
    if (methode === 'GET') return lesen(weg, u.searchParams);
    var p = {};
    try { p = JSON.parse((opt && opt.body) || '{}'); } catch (e) {}
    return schreiben(weg, p);
  };
})();

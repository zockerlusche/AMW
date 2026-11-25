/* --- Sprachen: alle festen Texte der Oberfläche; Inhalte aus der Datenbank bleiben in ihrer Sprache. --- */
const TEXTE = {
@@TEXTE_DE@@
@@TEXTE_EN@@
};
let sprache = "de", spracheGewaehlt = false;      /* gewählt = im Browser gemerkt oder per Adresse – dann gilt die Vorgabe der Installation nicht */
const t = (k, v = {}) => (TEXTE[sprache][k] ?? TEXTE.de[k] ?? k).replace(/\{(\w+)\}/g, (_, n) => v[n] ?? "");

let zustand = { sicht: "start", start: null, fragenSicht: "offen", arbeit: { sicht: "listen", agent: "", q: "" }, wissenQ: "", wissenReiter: "beschluesse" };

/* Elemente nur über textContent – Inhalte aus der Datenbank werden nie als HTML gesetzt. */
function el(tag, attr, ...kinder) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attr || {})) {
    if (v == null || v === false) continue;
    if (k === "class") e.className = v;
    else if (k.startsWith("on")) e.addEventListener(k.slice(2), v);
    else e.setAttribute(k, v === true ? "" : v);
  }
  for (const k of kinder.flat()) if (k != null && k !== false) e.append(k instanceof Node ? k : document.createTextNode(String(k)));
  return e;
}
const gebiet = () => (sprache === "en" ? "en-GB" : "de-DE");
const zeit = x => { if (!x) return "–"; return new Date(x).toLocaleString(gebiet(), { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" }); };
function seit(x) {
  if (!x) return t("nie"); const s = (Date.now() - new Date(x)) / 1000;
  if (s < 90) return t("gerade"); if (s < 3600) return t("vor_min", { n: Math.round(s / 60) });
  if (s < 86400) return t("vor_h", { n: Math.round(s / 3600) });
  const tage = Math.round(s / 86400); return tage === 1 ? t("vor_t1") : t("vor_t", { n: tage });
}
/* A1907: Lade-Nummer je Seitenwechsel und je neuem Zeichnen der Seite (zeige, rahmen – also auch ein Reiter derselben
   Seite). Was vorher angefragt wurde und erst danach ankommt, verwirft holen() still – das Versprechen bleibt offen, das
   Alte zeichnet nicht weiter. Sonst zeichnete eine langsam geladene Seite (z. B. die Startseite beim ersten Laden) über die
   inzwischen gewählte (L2882), und ein Reiter hängte sein Ergebnis an den nächsten. Was nicht zum Inhalt der Seite gehört
   (Projektliste, Kopfzeile, Übertragung online, Dialoge, Gespräch am Objekt), holt abrufen() ohne diese Regel. */
let wechselNr = 0, seitenNr = 0;                       /* seitenNr: nur echte Wechsel (zeige, nicht still) – fürs erste Laden */
const veraltet = () => new Promise(() => {});
/* A2037 (D1515 v2 §2.3): unter Last scheitert selten ein Lese-Abruf als Netzfehler (fetch wirft TypeError, Status 0) – dann
   einmal nach kurzer Pause wiederholen. Nie bei einer HTTP-Antwort (auch nicht 4xx/5xx) und nie beim Schreiben (schicken):
   ein GET ändert nichts, die Wiederholung ist gefahrlos. */
const NETZ_WIEDER_MS = 300;
async function lesenMitWiederholung(url) {
  try { return await fetch(url, { cache: "no-store" }); }
  catch (e) {
    if (!(e instanceof TypeError)) throw e;
    await new Promise(r => setTimeout(r, NETZ_WIEDER_MS));
    return await fetch(url, { cache: "no-store" });
  }
}
async function abrufen(weg, p = projekt) {               /* p: anderes Projekt (A1889: Nachrichten über alle Projekte) */
  const fuerDich = Date.now() - laden.eingabe < 1500;   /* A1676: nur Abrufe, die du ausgelöst hast – nie der Takt im Hintergrund */
  if (fuerDich) laden.an();
  try { const r = await lesenMitWiederholung(ziel(weg, p)); if (!r.ok) { const j = await r.json().catch(() => ({})); throw Object.assign(new Error(j.leer ? t(j.leer) : (j.fehler || r.status)), { leer: j.leer || null }); }   /* A1998 */
        return await r.json(); }
  finally { if (fuerDich) laden.aus(); }
}
/* A2117: zwischen Drücken und Loslassen nicht neu zeichnen – sonst ist der Knopf weg und der Klick verloren (höchstens 3 s) */
let gedrueckt = 0;
window.addEventListener("pointerdown", () => { gedrueckt = Date.now(); }, true);
for (const art of ["pointerup", "pointercancel"]) window.addEventListener(art, () => { setTimeout(() => { gedrueckt = 0; }, 0); }, true);
const haeltGedrueckt = () => gedrueckt > 0 && Date.now() - gedrueckt < 3000;
async function holen(weg, p = projekt) {
  const nr = wechselNr;
  let d;
  try { d = await abrufen(weg, p); } catch (e) { if (nr === wechselNr) throw e; return veraltet(); }   /* auch Fehler der alten Seite nicht zeigen */
  while (haeltGedrueckt()) await new Promise(r => setTimeout(r, 60));     /* A2117: die Antwort kam mitten im Drücken */
  return nr === wechselNr ? d : veraltet();
}
/* Ladeanzeige (A1676, Marcel W2076, F5341 A): das AMW-Logo, die zwei Kreise wandern auf den Linien des Schriftzugs, der
   Farbverlauf zieht mit. Erscheint erst nach 0,3 s (kurze Abrufe flackern nicht); bei „Bewegung reduzieren“ nur sanftes
   Heller/Dunkler. Ein Baustein für alle: holen() schaltet sie ein, sobald ein Abruf auf eine Eingabe folgt. */
const LOGO_PFAD = "M2 24 L8 3 L14 24 L18.5 3 L23 15 L27.5 3 L32 24 L36.5 13 L41 24 L45.5 3";
let logoNr = 0;
function ladeLogo(text = t("lade_text")) {
  const ruhig = matchMedia("(prefers-reduced-motion: reduce)").matches, id = "lg" + (++logoNr);
  const spline = 'calcMode="spline" keySplines=".45 0 .55 1; .45 0 .55 1"';
  const wandern = vor => ruhig ? "" : `<animateMotion dur="2.4s" repeatCount="indefinite" ${spline} keyPoints="${vor ? "0;1;0" : "1;0;1"}" keyTimes="0;.5;1" path="${LOGO_PFAD}"/>`;
  const x = el("div", { class: "laden" + (ruhig ? " ruhig" : ""), role: "status", "aria-live": "polite" });
  x.innerHTML = `<svg viewBox="-2 -3 50 31" aria-hidden="true">
    <defs><linearGradient id="${id}" gradientUnits="userSpaceOnUse" x1="0" y1="0" x2="48" y2="0" spreadMethod="reflect">
      <stop offset="0" style="stop-color:var(--bernstein)"/><stop offset=".5" style="stop-color:var(--glut)"/><stop offset="1" style="stop-color:var(--blau)"/>
      ${ruhig ? "" : `<animateTransform attributeName="gradientTransform" type="translate" values="-30 0; 30 0; -30 0" dur="2.4s" repeatCount="indefinite" ${spline}/>`}
    </linearGradient></defs>
    <path d="${LOGO_PFAD}" stroke="url(#${id})" stroke-width="3.2" stroke-linejoin="round" stroke-linecap="round" fill="none"/>
    <path d="M4.6 16.6 H11.4" stroke="url(#${id})" stroke-width="2.6" stroke-linecap="round"/>
    <circle ${ruhig ? 'cx="2" cy="24"' : ""} r="2.5" style="fill:var(--grund);stroke:var(--bernstein)" stroke-width="1.8">${wandern(true)}</circle>
    <circle ${ruhig ? 'cx="45.5" cy="3"' : ""} r="2.5" style="fill:var(--grund);stroke:var(--blau)" stroke-width="1.8">${wandern(false)}</circle>
  </svg>`;
  x.append(el("span", {}, text));
  return x;
}
const laden = {
  eingabe: Date.now(), offen: 0, uhr: null,         /* Start der Seite zählt wie eine Eingabe */
  an() { if (this.offen++ === 0) this.uhr = setTimeout(() => {
    if (this.offen && !document.getElementById("ladeanzeige")) document.body.append(el("div", { id: "ladeanzeige" }, ladeLogo())); }, 300); },
  aus() { if (--this.offen > 0) return; this.offen = 0; clearTimeout(this.uhr); document.getElementById("ladeanzeige")?.remove(); },
};
for (const art of ["pointerdown", "keydown", "hashchange", "popstate"]) window.addEventListener(art, () => { laden.eingabe = Date.now(); }, true);
/* A2117 (Marcel 25.11.): nach einem Neustart der Workbench gilt das alte Zeichen der Seite nicht mehr. Die Seite holt sich dann
   einmal das neue und schickt dasselbe genau einmal noch – der Server hatte vorher nichts getan. Die Leiste bleibt danach stehen. */
let frischesZeichen = null;
async function zeichenHolen() {
  try { const r = await fetch("/", { cache: "no-store" }); const m = r.ok && (await r.text()).match(/const TOKEN = "([^"]+)"/);
    return m && m[1] !== "__AMW_" + "TOKEN__" ? m[1] : null; } catch (e) { return null; }
}
/* A2117: ein Knopf, der freigibt oder abnimmt, wirkt je Klick einmal – solange seine Anfrage läuft, ist er aus; bei einem Fehler
   wieder an. Rückgabe von tun() oder null (lief schon, oder Fehler – dann steht der Satz da). */
let letzterKnopf = null;
window.addEventListener("click", e => { letzterKnopf = e.target.closest?.("button") || null; }, true);
const einmalLaeuft = new Set();
async function einmalTun(schluessel, tun) {
  if (einmalLaeuft.has(schluessel)) return null;
  einmalLaeuft.add(schluessel);
  const knopf = letzterKnopf; if (knopf) knopf.disabled = true;
  const frei = () => { einmalLaeuft.delete(schluessel); if (knopf) knopf.disabled = false; };
  try { const r = await tun(); setTimeout(frei, 1500); return r === undefined ? true : r; }       /* meist ist dann schon neu gezeichnet */
  catch (e) { frei(); toast(fehlerSatz(e), true); return null; }
}
/* A2117: ein Satz ohne Technik: kein „Failed to fetch“, keine nackte Zahl */
const fehlerSatz = e => e instanceof TypeError && /fetch|network|load failed/i.test(e.message) ? t("ohne_verbindung") : /^\d*$/.test(String(e.message)) ? t("ging_nicht") : t("fehler", { x: e.message });
async function schicken(weg, daten, p = projekt) {      /* p: Projekt, an das es geht (Nachrichten über alle Projekte) */
  const knopf = document.activeElement?.tagName === "BUTTON" ? document.activeElement : null;   /* die Stelle für „wird übertragen …“ */
  const ab = () => fetch(ziel(weg, p), { method: "POST", headers: { "Content-Type": "application/json", "X-AMW-Token": frischesZeichen || TOKEN }, body: JSON.stringify(daten) });
  let r = await ab(), j = await r.json().catch(() => ({}));
  if (j.neu_laden && !API) {
    const neu = await zeichenHolen();
    if (neu && neu !== (frischesZeichen || TOKEN)) { frischesZeichen = neu; r = await ab(); j = await r.json().catch(() => ({})); }
    neuLadenLeiste();
  }
  if (j.neu_laden) { neuLadenLeiste(); throw new Error(t("neu_laden")); }
  if (!r.ok) throw new Error(j.fehler || r.status);
  if (j.unterwegs) uebertragung.merken(j.eingang, knopf);
  nachAktion(); return j;
}
/* Online geht jede Eingabe über den Briefkasten; der PC führt sie Sekunden später aus. Ein Baustein für alle Eingaben:
   an der Stelle „wird übertragen …“, dann „gespeichert“ – oder „nicht gespeichert: Grund“. Ausstehende Nummern stehen im
   Browser und überleben ein Neuladen; den neuen Wert zeigt die Seite schon vorher (der Webhoster legt ihn über die Ansicht). */
const uebertragung = (() => {
  const ablageName = () => "amw-unterwegs";            /* fest, nicht je Projekt: beim Laden der Seite ist das Projekt noch nicht gewählt */
  let offen = []; try { offen = JSON.parse(localStorage.getItem(ablageName()) || "[]").filter(x => Date.now() - x.seit < 10 * 60000); } catch (e) {}
  let uhr = null;
  const sichern = () => { try { localStorage.setItem(ablageName(), JSON.stringify(offen)); } catch (e) {} };
  /* Ort eines Knopfs, der ein Neuzeichnen (und ein Neuladen) übersteht: nächster Behälter mit id/data-k + Aufschrift */
  const ortVon = knopf => { if (!knopf) return null; const a = knopf.closest("[id], [data-k]");
    return { anker: a ? (a.id ? "#" + CSS.escape(a.id) : `[data-k="${CSS.escape(a.dataset.k)}"]`) : null, text: knopf.textContent.trim(), sicht: zustand.sicht }; };
  const knopfAm = o => { if (!o || o.sicht !== zustand.sicht) return null; const a = o.anker ? document.querySelector(o.anker) : document.body;
    return a ? [...a.querySelectorAll("button")].find(b => b.textContent.trim() === o.text) || null : null; };
  const marke = (o, text, art) => { const knopf = knopfAm(o); if (!knopf) return null;
    let m = knopf.nextElementSibling?.classList.contains("ue-marke") ? knopf.nextElementSibling : null;
    if (!m) { m = el("span", { class: "ue-marke", role: "status" }); knopf.after(m); }
    m.className = "ue-marke " + art; m.textContent = text; return m; };
  const anbringen = () => { for (const o of offen) {                 /* nach jedem Neuzeichnen wieder an die Stelle */
    if (marke(o.ort, t("ue_laeuft"), "bernstein-text")) continue;
    if (!o.gemeldet) { o.gemeldet = true; toast(t("ue_laeuft"), false, true); } } };     /* Stelle weg (Dialog zu): einmal als Hinweis */
  async function nachsehen() {
    uhr = null; if (!offen.length) return;
    anbringen();
    let r; try { r = await abrufen("/api/eingang?ids=" + offen.map(x => x.id).join(",")); } catch (e) { uhr = setTimeout(nachsehen, 5000); return; }
    for (const x of r) {
      if (x.status === "neu") continue;
      const o = offen.find(y => y.id === x.id); offen = offen.filter(y => y.id !== x.id);
      if (x.status === "fehler") { const text = t("ue_fehler", { x: x.fehler }); if (!marke(o?.ort, text, "rot-text")) toast(text, true, true); }
      else { const ok = marke(o?.ort, "\u2713 " + t("ue_ok"), "gruen-text");      /* Knopf nicht mehr zu sehen: kurzer Hinweis */
             if (ok) setTimeout(() => ok.isConnected && ok.classList.contains("gruen-text") && ok.remove(), 5000); else toast("\u2713 " + t("ue_ok"), false, true);
             frischZeichnen(true); }
    }
    offen = offen.filter(o => r.some(x => x.id === o.id && x.status === "neu") || !r.some(x => x.id === o.id));
    sichern(); if (offen.length) uhr = setTimeout(nachsehen, 3000);
  }
  if (API && offen.length) uhr = setTimeout(nachsehen, 1500);
  return { zuletzt: 0, merken(id, knopf) {
    this.zuletzt = Date.now();
    if (!id) { toast(t("unterwegs"), false, true); return; }
    const ort = ortVon(knopf);
    offen.push({ id, seit: Date.now(), ort }); sichern();
    if (!marke(ort, t("ue_laeuft"), "bernstein-text")) toast(t("ue_laeuft"), false, true);
    setTimeout(anbringen, 1200);                               /* die Aktion zeichnet meist neu – Marke wieder anbringen */
    clearTimeout(uhr); uhr = setTimeout(nachsehen, 2500); } };
})();
function neuLadenLeiste() {          // bleibt stehen, bis neu geladen wird – Eingaben auf der Seite bleiben bis dahin
  if (document.getElementById("neu-laden")) return;
  const k = el("button", { class: "knopf haupt", type: "button" }, t("neu_laden_knopf"));
  k.addEventListener("click", () => location.reload());
  document.body.append(el("div", { class: "karte neu-laden", id: "neu-laden", role: "alert" },
    el("span", {}, t("neu_laden")), k));
}
function toast(text, fehler, stand) {
  if (text.includes(t("neu_laden")) && document.getElementById("neu-laden")) return;   // steht schon oben
  /* online: eine Erfolgsmeldung direkt nach dem Absenden wäre verfrüht – der PC hat noch nichts getan; den echten Stand
     („wird übertragen …“ → „gespeichert“ / „nicht gespeichert“) zeigt uebertragung an der Stelle */
  if (API && !fehler && !stand && Date.now() - (uebertragung?.zuletzt || 0) < 2000) return;
  const x = el("div", { class: "karte toast" }, text); if (fehler) x.style.borderColor = "var(--rot)";
  document.body.append(x); setTimeout(() => x.remove(), 3800);
}


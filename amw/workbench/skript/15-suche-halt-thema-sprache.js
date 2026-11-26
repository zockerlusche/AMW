/* --- Suche, Halt, Thema, Sprache ----------------------------------------------------------- */
async function suchen(q) {
  const m = rahmen(t("suche_titel"), el("span", { class: "leise" }, t("zitat", { x: q }))); let l; try { l = await holen("/api/suche?q=" + encodeURIComponent(q)); } catch (e) { m.append(el("div", { class: "leer" }, String(e))); return; }
  for (const a of document.querySelectorAll("nav a")) a.classList.remove("an");
  if (!l.length) { m.append(el("div", { class: "leer" }, t("nichts_gefunden"))); return; }
  const liste = (k, xs) => xs.length ? el("div", { class: k }, xs.map(x => { const auf = () => refOeffnen(x.ref, x.aufgabe);
    return el("div", { class: "zeile klickbar", role: "button", tabindex: "0", "data-ref": x.ref, onclick: auf,
        onkeydown: e => { if (e.key === "Enter") { e.preventDefault(); auf(); } } },
      el("span", { class: "ref" }, x.ref), el("span", { class: "leise" }, t("sa_" + x.art)),
      el("span", {}, x.titel || ""), el("span", { class: "sehrleise mono" }, x.zeit ? zeit(x.zeit) : "")); })) : null;
  m.append(...[liste("liste suche-genau", l.filter(x => x.genau)), liste("liste", l.filter(x => !x.genau))].filter(Boolean));
}
/* --- A2115: jede Nummer öffnet das Ding selbst (Suche, Verweise im Text) – mit den Dialogen und Ansichten, die es dafür gibt --- */
/* Eine Seite statt eines Dialogs: offene Dialoge gehen zu; steht darin schon Text, fragt die Seite vorher */
function dialogeZu() {
  const offen = [...document.querySelectorAll(".dialog-hg, .vb")];
  const text = offen.some(d => [...d.querySelectorAll("textarea, input:not([type=checkbox]):not([type=radio])")].some(x => x.value !== x.defaultValue));
  if (text && !confirm(t("dk_verwerfen"))) return false;
  offen.forEach(d => d.remove());
  return true;
}
/* Den Eintrag mit dieser Nummer auf der gezeigten Seite ins Bild holen; false = er steht nicht dort */
function refInsBild(ref) {
  const z = [...document.querySelectorAll("#inhalt .karte .ref")].find(e => e.textContent === ref)?.closest(".karte")
    || document.querySelector(`#inhalt .tc-eintrag[data-ref="${ref}"]`);
  if (!z) return false;
  z.scrollIntoView({ block: "center" });
  z.classList.remove("blink"); void z.offsetWidth; z.classList.add("blink");
  return true;
}
const refFehlt = ref => toast(t("rf_nicht_da", { x: ref }), true);
async function refOeffnen(ref, aufgabe) {
  const m = /^(TH|[DAFBWMLP#])(\d+)$/.exec(ref); if (!m) return;
  const [, art, zahl] = m, nr = +zahl;
  try {
    if (art === "D") return await dokumentDialog(nr);
    if (art === "A") return await aufgabeDialog(nr);
    if (art === "L") { if (!API) return await laufAusgabeDialog(nr); if (dialogeZu()) await zeige("betrieb"); return; }   /* die Ausgabe gibt es nur am PC */
    if (art === "P") {                                   /* eine Prüfung steht auf der Karte ihrer Aufgabe */
      const a = aufgabe === undefined ? (await abrufen("/api/suche?q=" + ref)).find(x => x.ref === ref)?.aufgabe : aufgabe;
      return a ? await aufgabeDialog(a) : refFehlt(ref);
    }
    if (art === "M") {
      const id = Object.entries(zustand.start?.bogen_nr || {}).find(([, n]) => n === nr)?.[0];
      if (!id) return refFehlt(ref);
      if (!dialogeZu()) return;
      zustand.planReiter = "zeitleiste"; await zeige("planung"); return await zuSchritt(null, +id);
    }
    if (art === "TH") {
      if (!(await abrufen("/api/themen")).some(x => x.id === nr)) return refFehlt(ref);
      if (!dialogeZu()) return;
      zustand.themaOffen = nr; return await zeige("themen");
    }
    if (art === "F") {
      const alle = await abrufen("/api/fragen?alle=1"), f = alle.find(x => x.id === nr);
      if (!f && !(await abrufen("/api/fragen?erledigt=1")).some(x => x.id === nr)) return refFehlt(ref);
      if (!dialogeZu()) return;
      zustand.fragenSicht = f ? (f.geparkt_utc ? "geparkt" : "offen") : "erledigt"; await zeige("fragen");
      return refInsBild(ref);
    }
    if (art === "B" || art === "W") {
      const r = art === "B" ? "beschluesse" : "wortlaut";
      if (!(await abrufen("/api/wissen?q=" + ref))[r].some(x => x.id === nr)) return refFehlt(ref);
      if (!dialogeZu()) return;
      zustand.wissenReiter = r; zustand.wissenQ = ref; await zeige("wissen");
      return refInsBild(ref);
    }
    const d = await abrufen("/api/nachrichten");         /* „#“: an dich oder von dir – sonst zwischen Agenten (Team-Chat) */
    const reiter = ["eingang", "gesendet"].find(k => d[k].some(x => x.id === nr));
    const x = reiter && d[reiter].find(y => y.id === nr);
    if (!x && !(await abrufen("/api/teamchat")).nachrichten.some(y => y.id === nr)) return refFehlt(ref);
    if (!dialogeZu()) return;
    if (!x) { await zeige("teamchat"); return refInsBild(ref) || refFehlt(ref); }
    nrMerk = { reiter, gewaehlt: `${x.projekt || projekt}:${nr}`, projektWahl: "", nurOffen: { eingang: true, gesendet: false }, gesehen: [], links: 0, rechtsOben: 0, detail: true };
    await zeige("nachrichten");
  } catch (e) { toast(t("fehler", { x: e.message || e }), true); }
}
/* Nummern in einem Text als Verweise: [Text, Verweis, Text …]. Ab zwei Ziffern (F5, A4, M2 sind meist etwas anderes), nie
   mitten in Wörtern, Pfaden und Versionsnummern; ein „/“ davor nur zwischen zwei Nummern („TH163/TH164“). Ohne Lookbehind (ältere iPads). */
function mitRefs(s) {
  if (typeof s !== "string") return [s];
  const aus = [], re = /(^|[^\p{L}\d_#&.-])((?:TH|[DAFBWMLP]|#)[1-9]\d{1,6})(?![\p{L}\d_]|[.,]\d)/gu;
  let pos = 0, m;
  while ((m = re.exec(s))) {
    const von = m.index + m[1].length, ref = m[2];
    if (m[1] === "/" && !/\d/.test(s[m.index - 1] || "")) continue;      /* /A1234 in einem Pfad */
    if (von > pos) aus.push(s.slice(pos, von));
    aus.push(el("a", { href: "#", class: "verweis", "data-ref": ref, onclick: e => { e.preventDefault(); e.stopPropagation(); refOeffnen(ref); } }, ref));
    pos = von + ref.length;
  }
  if (pos < s.length) aus.push(s.slice(pos));
  return aus;
}
function haltDialog() {
  const agenten = (zustand.start?.agenten || []).filter(a => a.soll !== "aus").map(a => a.kennung);
  const fuer = el("select", {}, el("option", { value: "alle" }, t("alle_agenten")), agenten.map(k => el("option", { value: k }, k)));
  const text = el("textarea", { placeholder: t("grund_ph") });
  const hg = el("div", { class: "dialog-hg", onclick: e => { if (e.target === hg) hg.remove(); } },
    el("div", { class: "karte dialog" }, el("h3", {}, t("halt_setzen")),
      el("p", { class: "leise" }, t("halt_erkl")),
      el("div", { style: "margin:10px 0" }, fuer), text,
      el("div", { class: "aktionen" }, el("button", { class: "knopf haupt", style: "background:var(--rot);border-color:var(--rot);color:#fff", type: "button", onclick: async () => {
        try { await schicken("/api/halt", { fuer: fuer.value, text: text.value.trim() || t("halt_vom") }); hg.remove(); toast(t("halt_gesetzt")); zeige(zustand.sicht); }
        catch (e) { toast(t("fehler", { x: e.message }), true); } } }, t("halt_setzen")),
        el("button", { class: "knopf", type: "button", onclick: () => hg.remove() }, t("abbrechen")))));
  document.body.append(hg); text.focus();
}
/* Schirm-Schalter: frei nur am PC mit Grund (optional „spätestens zu um“), zu überall mit einem Klick */
/* Darf diese Sitzung den Bildschirm freigeben? Am PC immer; online nur ein System-Admin (sonst nur belegen). */
const darfFreigeben = () => !API || zustand.start?.online?.ich?.rolle === "system_admin";
function schirmDialog(nurBis) {
  const sz = zustand.start?.schirm || { frei: 0 };
  let hg;
  const setzen = async daten => {
    try { const r = await schicken("/api/schirm", daten); hg.remove(); toast(r.text || t(daten.frei ? "schirm_ist_frei" : "schirm_ist_zu")); zeige(zustand.sicht, true); }
    catch (e) { toast(t("fehler", { x: e.message }), true); } };
  const stand = () => el("p", { class: "leise" }, [t("schirm_seit", { x: seit(sz.seit_utc) }), sz.bis_utc ? t("schirm_bis", { x: zeit(sz.bis_utc) }) : null, sz.grund].filter(Boolean).join(" · "));
  if (sz.frei && nurBis && darfFreigeben()) {
    /* A1745: „bis“ direkt ändern, ohne erst zu beenden – eigener Dialog, Hauptknopf „Übernehmen“ (TL P181: beenden ist hier
       nicht der Weg); seit und Grund bleiben */
    const hhmm = d => `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
    const bis = el("input", { type: "time", value: sz.bis_utc ? hhmm(new Date(sz.bis_utc)) : "" });
    const abend = new Date(); abend.setHours(22, 0, 0, 0);
    const bisSetzen = wert => setzen({ frei: true, bis: wert });
    hg = dialog(t("schirm_bis_knopf"), stand(),
      el("div", { class: "feld" }, el("label", {}, t("schirm_bis_titel")), el("div", {}, bis)),
      el("div", { class: "zeile schirm-schnell" },
        el("button", { class: "klein-knopf", type: "button", onclick: () => bisSetzen(hhmm(new Date(Math.max(Date.now(), sz.bis_utc ? +new Date(sz.bis_utc) : 0) + 3600e3))) }, t("schirm_bis_plus")),
        el("button", { class: "klein-knopf", type: "button", disabled: Date.now() >= +abend ? "disabled" : null, onclick: () => bisSetzen("22:00") }, t("schirm_bis_abend")),
        el("button", { class: "klein-knopf", type: "button", disabled: sz.bis_utc ? null : "disabled", onclick: () => bisSetzen(null) }, t("schirm_bis_offen"))),
      el("p", { class: "sehrleise" }, t("schirm_bis_h")),
      el("div", { class: "aktionen" }, el("button", { class: "knopf haupt", type: "button", onclick: () => bisSetzen(bis.value || null) }, t("schirm_bis_setzen")),
        el("button", { class: "knopf", type: "button", onclick: () => hg.remove() }, t("abbrechen"))));
    bis.focus();
    return;
  }
  if (sz.frei) {
    hg = dialog(t("schirm_titel"), stand(), el("p", {}, t("schirm_zu_erkl")),
      el("div", { class: "aktionen" }, el("button", { class: "knopf haupt", type: "button", onclick: () => setzen({ frei: false, grund: "wieder belegt vom Entwickler" }) }, t("schirm_zumachen")),
        el("button", { class: "knopf", type: "button", onclick: () => hg.remove() }, t("abbrechen"))));
    return;
  }
  if (API && !darfFreigeben()) {
    hg = dialog(t("schirm_titel"), el("p", {}, t("schirm_ist_zu") + (sz.grund ? ` · ${sz.grund}` : "")), el("p", { class: "leise" }, t("schirm_nur_admin")),
      el("div", { class: "aktionen" }, el("button", { class: "knopf", type: "button", onclick: () => hg.remove() }, t("abbrechen"))));
    return;
  }
  const grund = el("input", { placeholder: t("schirm_grund_ph") }), bis = el("input", { type: "time" });
  hg = dialog(t("schirm_titel"), el("p", { class: "leise", style: "margin-top:0" }, t("schirm_ist_zu") + (sz.grund ? ` · ${sz.grund}` : "")),
    el("p", {}, t("schirm_erkl")), el("div", { class: "feld" }, el("label", {}, t("schirm_grund_l")), el("div", {}, grund)),
    el("div", { class: "feld" }, el("label", {}, t("schirm_bis_l")), el("div", {}, bis)),
    el("div", { class: "aktionen" }, el("button", { class: "knopf haupt", type: "button", onclick: () => {
        if (!grund.value.trim()) { toast(t("schirm_grund_fehlt"), true); grund.focus(); return; }
        if (API && !confirm(bis.value ? t("schirm_frei_frage", { x: bis.value }) : t("schirm_frei_frage_offen"))) return;
        setzen({ frei: true, grund: grund.value.trim(), bis: bis.value || null }); } }, t("schirm_freigeben").replace(" …", "")),
      el("button", { class: "knopf", type: "button", onclick: () => hg.remove() }, t("abbrechen"))));
  grund.focus();
}
async function weiterGeben() {
  const halte = zustand.start?.halt || []; const fuer = [...new Set(halte.map(h => h.gilt_fuer))];
  try { let n = 0; for (const f of fuer) n += (await schicken("/api/weiter", { fuer: f })).aufgehoben; if (!API) toast(t("halt_aufgehoben", { n })); zeige(zustand.sicht); }
  catch (e) { toast(t("fehler", { x: e.message }), true); }
}
if (API) { const b = $("#abmelden"); b.hidden = false; b.addEventListener("click", async () => {
  await fetch("index.php?abmelden=1", { method: "POST", headers: { "X-AMW-Token": TOKEN } }).catch(() => {}); location.reload(); }); }
$("#suche").addEventListener("keydown", e => { if (e.key === "Enter" && kzAuswahl < 0 && e.target.value.trim().length > 1) suchen(e.target.value.trim()); });   /* A2014: ein gewählter Treffer öffnet sich selbst */
for (const a of document.querySelectorAll("nav a[data-sicht]")) a.addEventListener("click", () => zeige(a.dataset.sicht));
/* Handy: unten Start, Fragen, Plan, Arbeit und „Mehr“ (48-px-Ziele statt neun schmaler). „Mehr“ öffnet ein Blatt von unten mit
   den übrigen Bereichen, Hell/Dunkel und Sprache – so ist am Handy alles erreichbar, auch der Verlauf. */
$("#mehr").addEventListener("click", () => {
  const knoepfe = [...document.querySelectorAll("nav a.im-mehr")].map(a => el("button", { type: "button", class: a.classList.contains("an") ? "an" : "",
    onclick: () => { hg.remove(); zeige(a.dataset.sicht); } }, el("span", { class: "sym" }, a.querySelector(".sym").textContent),
    el("span", {}, a.querySelector("[data-t-lang]")?.textContent || a.querySelector("[data-t]").textContent),
    a.querySelector(".zahl")?.textContent ? el("span", { class: "zahl" }, a.querySelector(".zahl").textContent) : null));
  const liste = el("div", { class: "pw-liste karte", role: "dialog", "aria-label": t("n_mehr") }, el("h3", {}, t("n_mehr")),
    el("div", { class: "mehr-liste" }, knoepfe),
    el("div", { class: "mehr-fuss" }, el("button", { class: "klein-knopf", type: "button", onclick: () => $("#thema").click() }, t("thema")),
      el("button", { class: "klein-knopf", type: "button", onclick: () => { hg.remove(); $("#sprache").click(); } }, "DE / EN"),
      el("span", { class: "version" }, $("#version").textContent)));
  const hg = el("div", { class: "dialog-hg pw-hg", onclick: e => { if (e.target === hg) hg.remove(); } }, liste);
  document.body.append(hg);
});
function thema(x) { document.documentElement.dataset.thema = x; try { localStorage.setItem("amw-thema", x); } catch (e) {} }
$("#thema").addEventListener("click", () => thema(document.documentElement.dataset.thema === "hell" ? "dunkel" : "hell"));
$("#sprache").addEventListener("click", () => sprache_setzen(sprache === "de" ? "en" : "de"));
try { thema(localStorage.getItem("amw-thema") || (matchMedia("(prefers-color-scheme: light)").matches ? "hell" : "dunkel")); } catch (e) { thema("dunkel"); }
try { spracheGewaehlt = !!localStorage.getItem("amw-sprache");
  sprache = localStorage.getItem("amw-sprache") || ((navigator.language || "de").startsWith("de") ? "de" : "en"); } catch (e) {}
if (new URLSearchParams(location.search).get("sprache") in TEXTE) { sprache = new URLSearchParams(location.search).get("sprache"); spracheGewaehlt = true; }
feste_texte();


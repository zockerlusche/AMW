/* --- Suche, Halt, Thema, Sprache ----------------------------------------------------------- */
async function suchen(q) {
  const m = rahmen(t("suche_titel"), el("span", { class: "leise" }, t("zitat", { x: q }))); let l; try { l = await holen("/api/suche?q=" + encodeURIComponent(q)); } catch (e) { m.append(el("div", { class: "leer" }, String(e))); return; }
  for (const a of document.querySelectorAll("nav a")) a.classList.remove("an");
  if (!l.length) { m.append(el("div", { class: "leer" }, t("nichts_gefunden"))); return; }
  m.append(el("div", { class: "liste" }, l.map(x => el("div", { class: "zeile", ...(x.art === "dokument" ? { style: "cursor:pointer", onclick: () => dokumentDialog(+x.ref.slice(1)) } : {}) },
    el("span", { class: "ref" }, x.ref), el("span", { class: "leise" }, x.art),
    el("span", {}, x.titel || ""), el("span", { class: "sehrleise mono" }, zeit(x.zeit))))));
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
$("#suche").addEventListener("keydown", e => { if (e.key === "Enter" && e.target.value.trim().length > 1) suchen(e.target.value.trim()); });
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


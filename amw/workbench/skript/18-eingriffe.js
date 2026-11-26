/* A2159 (Abschlussprüfung M16, D1994; Probe D1481 v4): die vorhandenen Eingriffe als Knöpfe – ohne neue Logik, die Grenzen rechnet
   die AMW (paket_schieben, herausnehmen, zwischenpruefung, pause). Paket: Früher/Später mit der gesperrten Stelle und ihrem Grund,
   Prüfpunkt „Marcel testet“ dahinter bzw. wegnehmen (in aufgabeDialog). Agent: herausnehmen mit Vorschau der Folgen, wieder freigeben
   (in agentDialog). Pause für alles mit optionalem Ende (Projektweg › Planung, der Leitstand nimmt denselben Knopf). Nach jedem
   Eingriff rechnet die AMW neu; die Seite zeichnet neu, der Verlauf nennt Person und Grund. */
const egSperre = s => { if (!s || s.geht) return ""; const k = "egr_sp_" + s.art, w = t(k, { x: s.x || "" }); return w === k ? (s.grund || "") : w; };   /* unbekannte Art: der Satz der AMW */
async function egTun(weg, daten, ok, danach) {
  return einmalTun(weg + JSON.stringify(daten), async () => { const r = await schicken(weg, daten); toast(ok(r)); danach && danach(r); zeige(zustand.sicht, true); return r; });
}
/* Paket: Früher/Später (gesperrt mit Grund) und Prüfpunkt dahinter – im Fenster der Aufgabe */
function eingriffePaket(a, neu) {
  const e = a.eingriffe; if (!e) return null;
  const s = e.schieben, knopf = r => {
    const x = s && s[r];
    return el("button", { class: "klein-knopf", type: "button", "data-eg": r, disabled: x && x.geht ? null : "disabled", title: x && !x.geht ? egSperre(x) : t("egr_" + r + "_h"),
      onclick: () => egTun("/api/plan/schieben", { aufgabe: a.id, richtung: r }, () => t("egr_" + r + "_ok", { a: a.id, x: x.x || "" }), neu) }, t("egr_" + r)); };
  const sperren = s ? ["frueher", "spaeter"].filter(r => s[r] && !s[r].geht).map(r => `${t("egr_" + r)}: ${egSperre(s[r])}`) : [];
  const einmalig = s && !s.frueher.geht && !s.spaeter.geht && s.frueher.grund === s.spaeter.grund;   /* gar nicht schiebbar: ein Grund */
  const pp = e.ist_pruefpunkt ? a.id : e.pruefpunkt;
  const pruefKnopf = pp
    ? el("button", { class: "klein-knopf", type: "button", "data-eg": "pruefpunkt-weg", onclick: async () => {
        const grund = await rueckfrage(t("egr_pp_weg_frage", { a: pp }), { ja: t("egr_pp_weg"), eingabe: t("egr_grund_ph") }); if (!grund) return;
        egTun("/api/plan/pruefpunkt", { aufgabe: pp, entfernen: true, grund }, () => t("egr_pp_weg_ok", { a: pp }), neu); } }, t("egr_pp_weg"))
    : el("button", { class: "klein-knopf", type: "button", "data-eg": "pruefpunkt", disabled: a.bogen_id ? null : "disabled",
        title: a.bogen_id ? t("egr_pp_h") : t("egr_sp_ohne"), onclick: async () => {
          const hinweis = await rueckfrage(t("egr_pp_frage", { x: a.titel }), { ja: t("egr_pp_setzen"), eingabe: t("egr_pp_ph") }); if (!hinweis) return;
          egTun("/api/plan/pruefpunkt", { aufgabe: a.id, grund: hinweis, hinweis }, r => t("egr_pp_ok", { a: r.paket, n: (r.wartet || []).length }), neu); } }, t("egr_pp"));
  return el("div", { class: "au-block eg-block" }, el("h4", {}, t("egr_titel")),
    el("div", { class: "dk-aktionen" }, knopf("frueher"), knopf("spaeter"), pruefKnopf),
    sperren.length ? el("p", { class: "sehrleise eg-sperre", style: "margin:6px 0 0" }, einmalig ? egSperre(s.frueher) : sperren.join(" · ")) : null,
    el("p", { class: "sehrleise", style: "margin:4px 0 0" }, t("egr_neu_h")));
}
/* Agent: herausnehmen (mit Vorschau, was mit seinen Paketen geschieht) oder wieder freigeben – im Fenster des Agenten */
function eingriffeAgent(d, neu) {
  if (!d || d.kennung === "Entwickler") return null;
  const h = d.heraus;
  if (h) return el("section", { class: "abschnitt eg-block" }, el("h4", {}, t("egr_ag_titel")),
    el("p", { class: "bernstein-text", style: "margin:0 0 6px" }, t("egr_ag_ist", { x: zeit(h.seit_utc) }) + (h.grund ? ` · ${h.grund}` : "")),
    el("button", { class: "klein-knopf", type: "button", "data-eg": "freigeben", onclick: async () => {
      const grund = await rueckfrage(t("egr_ag_frei_frage", { x: d.kennung }), { ja: t("egr_ag_frei"), eingabe: t("egr_grund_ph") }); if (!grund) return;
      egTun("/api/plan/agent", { was: "freigeben", kennung: d.kennung, grund }, () => t("egr_ag_frei_ok", { x: d.kennung }), neu); } }, t("egr_ag_frei")));
  return el("section", { class: "abschnitt eg-block" }, el("h4", {}, t("egr_ag_titel")),
    el("button", { class: "klein-knopf", type: "button", "data-eg": "herausnehmen", onclick: () => herausnehmenDialog(d, neu) }, t("egr_ag_raus")),
    el("p", { class: "sehrleise", style: "margin:6px 0 0" }, t("egr_ag_h")));
}
/* TH164: was mit dem laufenden Paket geschieht, wählt Marcel – zu Ende oder mit Übergabe-Notiz zurück; die Vorschau rechnet die AMW je Wahl */
async function herausnehmenDialog(d, neu) {
  const vorschau = el("div", { class: "eg-folgen" }), grund = el("input", { placeholder: t("egr_grund_ph"), maxlength: 300 });
  let art = "zu_ende", laufend = false;
  const wahl = el("div", { class: "eg-wahl", hidden: true, style: "display:grid;gap:8px;min-width:0;margin-bottom:10px" },   /* am Handy umbrechen, nie seitwärts */
    ["zu_ende", "zurueck"].map(x => el("label", { class: "eg-wahl-zeile", style: "display:flex;gap:8px;align-items:flex-start;min-width:0;overflow-wrap:anywhere" },
      el("input", { type: "radio", name: "eg-laufend", value: x, checked: x === art, style: "flex:none;margin-top:3px", onchange: () => { art = x; zeigen(); } }),
      el("span", { style: "min-width:0" }, t("egr_ag_l_" + x)))));
  async function zeigen() {
    let f; try { f = await schicken("/api/plan/agent", { was: "folgen", kennung: d.kennung, laufendes: art }); }
    catch (e) { toast(fehlerSatz(e), true); return; }
    laufend = !!f.laufend; wahl.hidden = !laufend;
    const zeilen = [f.laufend ? t("egr_ag_laufend_" + art, { a: f.laufend.id, x: f.laufend.titel }) : t("egr_ag_nichts_laeuft"),
      f.wartend.length ? t("egr_ag_pool", { n: f.wartend.length, x: f.wartend.slice(0, 4).map(w => "A" + w.id).join(", ") + (f.wartend.length > 4 ? " …" : "") }) : t("egr_ag_kein_pool"),
      f.bleibt.length ? t("egr_ag_bleibt", { x: f.bleibt.map(x => "A" + x).join(", ") }) : null, ...(f.hinweise || [])].filter(Boolean);
    vorschau.replaceChildren(...zeilen.map(z => el("div", { class: "au-zeile" }, "• " + z)));
  }
  await zeigen();
  const hg = dialog(t("egr_ag_frage", { x: d.kennung }), wahl, vorschau,
    el("div", { class: "feld" }, el("label", {}, t("egr_pa_grund")), el("div", {}, grund)),
    el("div", { class: "aktionen" }, el("button", { class: "knopf haupt", type: "button", "data-eg": "herausnehmen-ja", onclick: () => {
        if (!grund.value.trim()) { toast(t("egr_grund_fehlt"), true); grund.focus(); return; }
        egTun("/api/plan/agent", { was: "herausnehmen", kennung: d.kennung, laufendes: art, grund: grund.value.trim() },
          () => t("egr_ag_raus_ok", { x: d.kennung }), () => { hg.remove(); neu && neu(); }); } }, t("egr_ag_raus")),
      el("button", { class: "knopf", type: "button", onclick: () => hg.remove() }, t("abbrechen"))));
  grund.focus();
  return hg;
}
/* Pause für alles: an mit Grund und optionalem Ende, aus mit einem Klick */
function pauseKnopf(p) {
  if (!p) return null;
  return p.an
    ? el("button", { class: "knopf eg-pause an", type: "button", "data-eg": "pause-aus", title: p.grund || "",
        onclick: () => egTun("/api/pause", { an: false }, () => t("egr_pa_aus_ok")) }, p.bis ? t("egr_pa_bis", { x: zeit(p.bis) }) : t("egr_pa_an"))
    : el("button", { class: "knopf eg-pause", type: "button", "data-eg": "pause", onclick: () => pauseDialog() }, t("egr_pa"));
}
function pauseDialog() {
  const grund = el("input", { placeholder: t("egr_grund_ph"), maxlength: 300 }), bis = el("input", { placeholder: t("egr_pa_bis_ph"), maxlength: 10 });
  const schnell = w => el("button", { class: "klein-knopf", type: "button", onclick: () => { bis.value = w; } }, w);
  const hg = dialog(t("egr_pa_titel"), el("p", { class: "leise", style: "margin-top:0" }, t("egr_pa_erkl")),
    el("div", { class: "feld" }, el("label", {}, t("egr_pa_grund")), el("div", {}, grund)),
    el("div", { class: "feld" }, el("label", {}, t("egr_pa_ende")), el("div", {}, bis, el("div", { class: "zeile", style: "margin-top:6px;gap:6px;display:flex;flex-wrap:wrap" },
      schnell("30min"), schnell("1h"), schnell("2h")))),
    el("p", { class: "sehrleise" }, t("egr_pa_ende_h")),
    el("div", { class: "aktionen" }, el("button", { class: "knopf haupt", type: "button", "data-eg": "pause-an", onclick: () => {
        if (!grund.value.trim()) { toast(t("egr_grund_fehlt"), true); grund.focus(); return; }
        egTun("/api/pause", { an: true, grund: grund.value.trim(), bis: bis.value.trim() || null }, r => r.bis ? t("egr_pa_ok_bis", { x: zeit(r.bis) }) : t("egr_pa_ok"), () => hg.remove()); } }, t("egr_pa_setzen")),
      el("button", { class: "knopf", type: "button", onclick: () => hg.remove() }, t("abbrechen"))));
  grund.focus();
  return hg;
}

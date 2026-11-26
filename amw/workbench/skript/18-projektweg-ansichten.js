/* A2011 (Kleinprobe A2007, D1481 v4, TH156): Unteransichten im Projektweg – Schritt 3 · Feinplanung „Feinplan · Gesamtplan“,
   Schritt 4 · Umsetzung „Pakete · Reihenfolge · Zeitplan“. „Feinplan“ und „Pakete“ sind die bisherigen Ansichten (pwFein,
   pwUmsetzung). Reihenfolge und Zeitplan rechnet /api/zeitplan (A2045), der Gesamtplan nimmt die Meilensteine des Projektwegs und
   die Prognose je Meilenstein aus /api/leitstand. Beides wird erst beim Öffnen des Reiters geholt. */
const PW_REITER = { 2: ["feinplan", "gesamtplan"], 3: ["pakete", "reihenfolge", "zeitplan"] };
const PW_REIHE_ERST = 14;
/* A2011 (Lead #34150): eigene Adressen der drei Ansichten – Schritt (Index wie PW_SCHRITTE) und Reiter */
const PW_ADRESSEN = { reihenfolge: [3, "reihenfolge"], zeitplan: [3, "zeitplan"], gesamtplan: [2, "gesamtplan"] };
function pwAdresse(sicht) {
  const [schritt, wahl] = PW_ADRESSEN[sicht];
  zustand.pwSicht = schritt; zustand.pwOffen = true; zustand.pwReiter = { ...(zustand.pwReiter || {}), [schritt]: wahl };
  pwStand = null;
  return zeige("projektweg");
}                         /* so viele Pakete „als Nächstes“, der Rest hinter „n weitere“ */
function pwReiterWahl(v) {
  const r = PW_REITER[v];
  if (!r) return null;
  const w = (zustand.pwReiter || {})[v];
  return r.includes(w) ? w : r[0];
}
function pwMitReitern(v, d) {
  const alt = [pwKonzept, pwGrob, pwFein, pwUmsetzung, pwAbschluss][v];
  const r = PW_REITER[v];
  if (!r) return alt(d);
  const wahl = pwReiterWahl(v);
  const reiter = el("div", { class: "pjw-seg", role: "tablist" }, r.map(k => el("button", { type: "button", role: "tab", "data-reiter": k,
    class: k === wahl ? "an" : "", "aria-selected": k === wahl ? "true" : "false",
    onclick: () => { zustand.pwReiter = { ...(zustand.pwReiter || {}), [v]: k }; pwStand = null; zeige("projektweg", true); } }, t("pjw_t_" + k))));
  if (wahl === r[0]) return [reiter, ...alt(d)];
  const platz = el("div", { class: "pjw-unter", "data-ansicht": wahl }, el("div", { class: "sehrleise" }, t("pjw_laedt")));
  (wahl === "gesamtplan" ? pwGesamtplan(d) : pwZeitplanDaten().then(z => wahl === "reihenfolge" ? pwReihenfolge(d, z) : pwZeitplan(d, z)))
    .then(x => platz.replaceChildren(...[].concat(x)))
    .catch(e => platz.replaceChildren(el("div", { class: "leer" }, t("fehler", { x: e.message || e }))));
  return [reiter, platz];
}
async function pwZeitplanDaten() { return holen("/api/zeitplan"); }
/* Pakete aller Meilensteine des Projektwegs: Nummer → {status, bogen-Nr} – für M… und „blockiert“ */
function pwPaketInfo(d) {
  const info = {};
  for (const m of [...(d.fein?.meilensteine || []), ...(d.umsetzung?.meilensteine || [])])
    for (const p of m.pakete || []) info[p.id] = { status: p.status, nr: m.nr, aktiv: m.status === "aktiv" };
  return info;
}
const pwWoTag = iso => new Date(iso).toLocaleString(gebiet(), { weekday: "short", hour: "2-digit", minute: "2-digit" });
const pwChip = (text, art) => el("span", { class: "pjw-chip-s" + (art ? " " + art : "") }, text);
/* Reihenfolge: was läuft und was als Nächstes kommt, in der Reihenfolge des Zeitplans */
/* nur Pakete aktiver Meilensteine – was erst geplant ist, kommt nicht gleich (wie im Leitstand, Lead #34119) */
const pwNurAktiv = (info, z) => (z.pakete || []).filter(p => info[p.aid]?.aktiv);
function pwReihenfolge(d, z) {
  const info = pwPaketInfo(d), pakete = pwNurAktiv(info, z);
  const zeile = (p, i) => {
    const s = info[p.aid]?.status, blockiert = s === "blockiert", ohne = !!p.hinweis;
    return el("button", { type: "button", class: "pjw-rf-zeile", "data-ref": `A${p.aid}`, onclick: () => aufgabeDialog(p.aid) },
      el("span", { class: "sehrleise" }, String(i + 1)), el("span", { class: "leise" }, info[p.aid] ? `M${info[p.aid].nr}` : ""),
      el("span", { class: "pjw-rf-titel" }, p.titel),
      el("span", { class: "leise" }, p.art === "headless" ? "Headless" : (p.agent || t("pjw_ohne_agent"))),
      el("span", { class: "leise" }, blockiert || ohne ? "–" : t(p.zustand === "laeuft" ? "pjw_bis" : "pjw_ab", { x: pwWoTag(p.zustand === "laeuft" ? p.ende_utc : p.start_utc) })),
      p.zustand === "laeuft" ? pwChip(t("laeuft"), "an") : blockiert ? pwChip(t("blockiert"), "bernstein") : pwChip(t("pjw_wartet")));
  };
  const laeuft = pakete.filter(p => p.zustand === "laeuft"), danach = pakete.filter(p => p.zustand !== "laeuft");
  if (!pakete.length) return el("div", { class: "leer" }, t("pjw_rf_leer"));
  const liste = el("div", { class: "pjw-rf" }, danach.slice(0, PW_REIHE_ERST).map((p, i) => zeile(p, laeuft.length + i)));
  const mehr = danach.length > PW_REIHE_ERST ? el("button", { type: "button", class: "knopf", onclick: () => {
    liste.append(...danach.slice(PW_REIHE_ERST).map((p, i) => zeile(p, laeuft.length + PW_REIHE_ERST + i))); mehr.remove(); } },
    t("pjw_n_weitere", { n: danach.length - PW_REIHE_ERST })) : null;
  return [laeuft.length ? el("div", { class: "pjw-lbl" }, t("pjw_rf_laeuft", { n: laeuft.length })) : null,
    laeuft.length ? el("div", { class: "pjw-rf" }, laeuft.map(zeile)) : null,
    danach.length ? el("div", { class: "pjw-lbl" }, t("pjw_rf_naechstes", { n: danach.length })) : null, liste, mehr].filter(Boolean);
}
/* Zeitplan: je Agent bzw. Headless-Platz eine Spur, Balken von Start bis Ende; was keine Zeit hat (blockiert, ohne Agent oder
   Platz), steht rechts unter „ohne Zeit“. Kurze Balken ohne Text – der Titel kommt beim Darüberfahren und im Dialog. */
function pwZeitplan(d, z) {
  const info = pwPaketInfo(d), pakete = pwNurAktiv(info, z);
  if (!pakete.length) return el("div", { class: "leer" }, t("pjw_rf_leer"));
  const mitZeit = pakete.filter(p => !p.hinweis && info[p.aid]?.status !== "blockiert"), ohne = pakete.filter(p => !mitZeit.includes(p));
  const von = Math.min(Date.parse(z.jetzt), ...mitZeit.map(p => Date.parse(p.start_utc))), bis = Math.max(von + 3600e3, ...mitZeit.map(p => Date.parse(p.ende_utc)));
  const pos = iso => 100 * (Date.parse(iso) - von) / (bis - von);
  const spuren = {};
  for (const p of mitZeit) (spuren[p.art === "headless" ? "Headless" : (p.agent || "–")] ??= []).push(p);
  const stunden = [];
  for (let h = Math.ceil(von / 7200e3) * 7200e3; h < bis; h += 7200e3) stunden.push(h);
  const achse = el("div", { class: "pjw-zp-achse" }, stunden.map(h => el("span", { style: `left:${100 * (h - von) / (bis - von)}%` },
    new Date(h).toLocaleTimeString(gebiet(), { hour: "2-digit" }))), el("i", { class: "pjw-zp-jetzt", style: `left:${pos(z.jetzt)}%` }));
  const balken = p => el("button", { type: "button", class: "pjw-zp-balken" + (p.zustand === "laeuft" ? " laeuft" : ""), title: `A${p.aid} ${p.titel}`,
    "data-ref": `A${p.aid}`, style: `left:${pos(p.start_utc)}%;width:${Math.max(0.6, pos(p.ende_utc) - pos(p.start_utc))}%`, onclick: () => aufgabeDialog(p.aid) },
    el("span", {}, p.titel));
  const zeilen = Object.entries(spuren).map(([wer, ps]) => {           /* Headless: so viele Reihen wie gleichzeitig laufen */
    const reihen = [];
    for (const p of ps.sort((a, b) => a.start_utc.localeCompare(b.start_utc))) {
      const r = reihen.find(x => x.ende <= p.start_utc) || (reihen.push({ ende: "", ps: [] }), reihen[reihen.length - 1]);
      r.ps.push(p); r.ende = p.ende_utc;
    }
    return el("div", { class: "pjw-zp-zeile" }, el("b", {}, wer), el("div", { class: "pjw-zp-spuren" }, reihen.map(r => el("div", { class: "pjw-zp-spur" }, r.ps.map(balken)))));
  });
  const rechts = el("div", { class: "pjw-zp-ohne" }, el("div", { class: "pjw-lbl" }, t("pjw_ohne_zeit")),
    ohne.length ? ohne.map(p => el("button", { type: "button", class: "pjw-zp-ohne-k" + (info[p.aid]?.status === "blockiert" ? " bernstein" : ""),
      "data-ref": `A${p.aid}`, title: p.hinweis || t("blockiert"), onclick: () => aufgabeDialog(p.aid) }, el("span", { class: "pjw-zp-ohne-t" }, p.titel))) : el("div", { class: "sehrleise" }, "–"));
  const zp = el("div", { class: "pjw-zp" }, el("div", { class: "pjw-zp-links" }, el("div", { class: "pjw-zp-kopf" }, el("span"), achse), ...zeilen), rechts);
  requestAnimationFrame(() => zp.querySelectorAll(".pjw-zp-balken").forEach(b => { if (b.clientWidth < 80) b.querySelector("span").textContent = ""; }));
  return zp;
}
/* Gesamtplan: alle Meilensteine mit Status, Fortschritt und Prognose; offene zuerst (jüngste oben), aufklappbar bis zu den offenen
   Paketen; abgenommene eingeklappt unten. */
async function pwGesamtplan(d) {
  let prognose = {};
  try { prognose = Object.fromEntries(((await holen("/api/leitstand")).zeitplan || []).map(m => [m.nr, m])); } catch (e) {}
  const bei = Object.fromEntries((d.abschluss || []).map(a => [a.nr, a]));
  const ms = [...(d.fein?.meilensteine || [])].sort((a, b) => b.nr - a.nr);
  const offen = ms.filter(m => m.status !== "fertig"), fertig = ms.filter(m => m.status === "fertig");
  const status = m => bei[m.nr]?.bei_dir ? pwChip(t("pjw_wartet_dich"), "bernstein") : pwChip(t("pjw_gs_" + (m.status === "aktiv" ? "arbeit" : m.status)));
  const fort = m => { const n = (m.pakete || []).length, f = (m.pakete || []).filter(p => p.status === "fertig").length;
    return el("span", { class: "pjw-gs-fort" }, el("span", { class: "pjw-balken" }, el("span", { style: `width:${n ? Math.round(100 * f / n) : 0}%` })), t("pjw_f_von_n", { f, n })); };
  const prog = m => { const p = prognose[m.nr]; return p ? datumKurz(p.p50) : m.status === "aktiv" ? t("pjw_gs_offen") : "–"; };
  const zeile = m => {
    const pakete = (m.pakete || []).filter(p => p.status !== "fertig");
    const kopf = [el("span", { class: "pjw-gs-name" }, `M${m.nr} ${m.titel}`), status(m), fort(m), el("span", { class: "pjw-gs-prog" }, prog(m))];
    return pakete.length ? el("details", { class: "pjw-gs-m", "data-nr": m.nr }, el("summary", { class: "pjw-gs-zeile" }, ...kopf),
        pakete.map(p => el("button", { type: "button", class: "pjw-gs-zeile pjw-gs-paket", "data-ref": `A${p.id}`, onclick: () => aufgabeDialog(p.id) },
          el("span", { class: "pjw-gs-name" }, p.titel), pwChip(t(p.status === "laeuft" ? "laeuft" : p.status === "blockiert" ? "blockiert" : "pjw_wartet"), p.status === "laeuft" ? "an" : ""),
          el("span", { class: "leise" }, p.wer || p.agent || t("pjw_ohne_agent")), el("span"))))
      : el("div", { class: "pjw-gs-m pjw-gs-zeile", "data-nr": m.nr }, ...kopf);
  };
  return el("div", { class: "pjw-gs" }, el("div", { class: "pjw-gs-zeile pjw-gs-titel" }, ...["pjw_gs_meilenstein", "pjw_gs_status", "pjw_gs_fortschritt", "pjw_gs_prognose"].map(k => el("span", {}, t(k)))),
    ...offen.map(zeile),
    fertig.length ? el("details", { class: "pjw-gs-m pjw-gs-alt" }, el("summary", { class: "pjw-gs-zeile" }, el("span", { class: "pjw-gs-name" }, t("pjw_gs_abgenommen", { n: fertig.length })),
      el("span"), el("span", { class: "leise" }, t("pjw_gs_pakete", { n: fertig.reduce((s, m) => s + (m.pakete || []).length, 0) })), el("span")),
      fertig.map(m => el("div", { class: "pjw-gs-zeile pjw-gs-paket", "data-nr": m.nr }, el("span", { class: "pjw-gs-name" }, `M${m.nr} ${m.titel}`), pwChip(t("pjw_gs_fertig")), fort(m), el("span")))) : null);
}

/* --- Verlauf: was wann passiert ist (aus den vorhandenen Daten), je Tag, filterbar ------------- */
async function sichtVerlauf() {
  const f = zustand.verlauf ||= { tage: 3, agent: "", arten: [] };
  let d; try { d = await holen("/api/verlauf?tage=" + f.tage); } catch (e) { rahmen(t("n_verlauf")).append(el("div", { class: "leer" }, String(e))); return; }
  /* online liegt ein fester Zeitraum (3 Tage) im Spiegel: dort nur kürzere Zeiträume anbieten und hier zuschneiden */
  if (f.tage > d.tage) f.tage = d.tage;
  const beginn = new Date(); beginn.setHours(0, 0, 0, 0); beginn.setDate(beginn.getDate() - (f.tage - 1));
  const m = rahmen(t("n_planung"), el("span", { class: "leise" }, t("vl_zeitraum", { n: f.tage })));
  m.append(planReiter("verlauf"));
  const arten = ["nachricht", "erledigt", "lauf", "pruefung", "frage", "beschluss", "plan", "sitzung", "dokument"];
  const tage = el("select", { onchange: e => { f.tage = Number(e.target.value); sichtVerlauf(); } }, [1, 3, 7, 14].filter(n => !API || n <= d.tage).map(n => el("option", { value: n, ...(n === f.tage ? { selected: true } : {}) }, t("vl_tage", { n }))));
  const agent = el("select", { onchange: e => { f.agent = e.target.value; sichtVerlauf(); } }, el("option", { value: "" }, t("alle_agenten")),
    [...d.agenten, "Entwickler", "AMW"].map(k => el("option", { value: k, ...(k === f.agent ? { selected: true } : {}) }, wer(k))));
  const chips = arten.map(a => el("button", { class: "vl-chip" + (f.arten.includes(a) ? " an" : ""), type: "button",
    onclick: () => { f.arten = f.arten.includes(a) ? f.arten.filter(x => x !== a) : [...f.arten, a]; sichtVerlauf(); } }, t("vl_" + a)));
  m.append(el("div", { class: "vl-filter" }, tage, agent, ...chips));
  const liste = d.ereignisse.filter(x => new Date(x.zeit) >= beginn && (!f.agent || x.wer === f.agent) && (!f.arten.length || f.arten.includes(x.art)));
  if (!liste.length) { m.append(el("div", { class: "leer" }, t("vl_leer"))); return; }
  const gruppen = {};
  for (const x of liste) (gruppen[new Date(x.zeit).toLocaleDateString(gebiet(), { weekday: "long", day: "2-digit", month: "2-digit" })] ||= []).push(x);
  const farbe = x => x.art === "pruefung" ? (x.zusatz === "rot" ? "rot" : "gruen") : x.art === "erledigt" ? (x.zusatz === "fertig" ? "gruen" : "") :
    x.art === "frage" ? "bernstein" : x.art === "plan" ? "bernstein" : x.art === "lauf" && /rc [1-9]|abgebrochen/.test(x.zusatz || "") ? "rot" : "";
  m.append(el("div", { class: "vl" }, Object.entries(gruppen).map(([tag, xs]) => el("section", {}, el("h2", {}, tag, el("span", { class: "sehrleise mono", style: "margin-left:8px" }, xs.length)),
    el("div", { class: "vl-tag" }, xs.slice(0, 400).map(x => el("div", { class: "vl-zeile" },
      el("span", { class: "mono sehrleise" }, new Date(x.zeit).toLocaleTimeString(gebiet(), { hour: "2-digit", minute: "2-digit" })),
      el("span", { class: "punkt " + farbe(x) }),
      el("span", { class: "vl-wer" }, wer(x.wer) || "–"),
      el("span", { class: "vl-text" }, x.art === "dokument" ? el("a", { class: "ref verweis", onclick: () => dokumentDialog(+x.ref.slice(1)) }, x.ref) : el("span", { class: "ref" }, x.ref), " ", x.text,
        x.zusatz && !["nachricht"].includes(x.art) ? el("span", { class: "etikett", style: "margin-left:6px" }, t("vz_" + x.zusatz) !== "vz_" + x.zusatz ? t("vz_" + x.zusatz) : x.zusatz) : null))))))));
  if (liste.length >= 2500) m.append(el("p", { class: "sehrleise" }, t("vl_grenze")));
}


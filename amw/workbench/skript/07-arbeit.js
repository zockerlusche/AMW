/* --- Arbeit -------------------------------------------------------------------------------- */
/* Arbeitsliste je Agent (von oben nach unten, eins nach dem anderen) und der Eingang – ordnen tut der Lead (amw liste) */
async function arbeitslisten(m, a) {
  let d; try { d = await holen("/api/listen"); } catch (e) { m.append(el("div", { class: "leer" }, String(e))); return; }
  const q = (a.q || "").toLowerCase(), passt = x => !q || `A${x.id} ${x.titel}`.toLowerCase().includes(q);
  const agenten = d.agenten.filter(g => !a.agent || g.kennung === a.agent);
  m.append(el("p", { class: "leise kurztext", style: "margin:0 0 12px", title: t("aufklappen"), onclick: e => e.currentTarget.classList.toggle("auf") }, t("li_erkl")));
  if (!agenten.length) m.append(el("div", { class: "leer" }, t("li_leer")));
  m.append(el("div", { class: "board listen" }, agenten.map(g => el("div", { class: "spalte" },
    el("h4", {}, g.rolle === "entwickler" ? t("li_deine", { x: g.name || g.kennung }) : g.kennung, el("span", { class: "sehrleise mono" }, g.liste.length)),
    g.liste.filter(passt).map(x => el("div", { class: "karte aufgabe klickbar" + (x.status === "laeuft" ? " in-arbeit" : ""), onclick: () => aufgabeDialog(x.id) },
      el("div", {}, el("span", { class: "mono sehrleise" }, `${x.pos}.`), " ", el("span", { class: "ref" }, `A${x.id}`),
        x.status === "laeuft" ? el("span", { class: "etikett gruen", style: "margin-left:6px" }, t("li_in_arbeit"))
          : x.status === "blockiert" ? el("span", { class: "etikett", style: "margin-left:6px" }, t("sp_blockiert")) : null),
      el("div", { class: "t" }, x.titel.length > 160 ? x.titel.slice(0, 160) + " …" : x.titel),
      (x.gruende || []).length ? el("div", { class: "w bernstein-text" }, "⇢ " + x.gruende.join(", "))
        : x.wartet_auf && x.status !== "laeuft" ? el("div", { class: "w" }, "⇢ " + x.wartet_auf.slice(0, 120)) : null))))));
  const pool = d.pool.filter(passt);
  m.append(el("h3", { style: "margin:22px 0 8px" }, t("li_pool"), " ", el("span", { class: "sehrleise mono" }, pool.length), " ", hilfeKnopf("reihenfolge")),
    pool.length ? el("div", { class: "liste" }, pool.map(x => el("div", { class: "zeile klickbar", onclick: () => aufgabeDialog(x.id) }, el("span", { class: "ref" }, `A${x.id}`),
      el("span", { class: "leise" }, x.agent || "–"), el("span", {}, x.titel)))) : el("div", { class: "leer" }, t("li_pool_leer")));
}
async function sichtArbeit() {
  const a = zustand.arbeit; const m = rahmen(t("n_planung"));
  m.append(planReiter("arbeit"));
  const agenten = (zustand.start?.agenten || []).map(x => x.kennung);
  const suche = el("input", { placeholder: t("filtern"), value: a.q, onkeydown: e => { if (e.key === "Enter") { a.q = e.target.value; sichtArbeit(); } } });
  m.append(el("div", { class: "reiter" },
    ["listen", "offen", "geparkt", "pool", "erledigt", "pakete"].map(s => el("button", { class: s === a.sicht ? "an" : "", type: "button", onclick: () => { a.sicht = s; sichtArbeit(); } }, t("t_" + s))),
    el("div", { class: "rechts" },
      el("select", { onchange: e => { a.agent = e.target.value; sichtArbeit(); } }, el("option", { value: "" }, t("alle_agenten")),
        agenten.map(k => el("option", { value: k, ...(k === a.agent ? { selected: true } : {}) }, k))), suche)));
  if (a.sicht === "listen") return arbeitslisten(m, a);
  if (a.sicht === "pakete") return arbeitPakete(m);                 /* A1850 */
  let liste; try { liste = await holen(`/api/aufgaben?sicht=${a.sicht}&agent=${encodeURIComponent(a.agent)}&q=${encodeURIComponent(a.q)}`); }
  catch (e) { m.append(el("div", { class: "leer" }, String(e))); return; }
  if (!liste.length) { m.append(el("div", { class: "leer" }, t("keine_aufgaben"))); return; }
  if (a.sicht === "offen") {
    /* „Läuft“ = Status läuft oder ein Agent arbeitet gerade daran (Tätigkeit/letzte Meldung) */
    const sp = { laeuft: [], wartet: [], blockiert: [] }; for (const x of liste) (x.jetzt ? sp.laeuft : sp[x.status] || sp.wartet).push(x);
    m.append(el("div", { class: "board" }, [["laeuft", "sp_laeuft"], ["wartet", "sp_wartet"], ["blockiert", "sp_blockiert"]].map(([k, titel]) =>
      el("div", { class: "spalte" }, el("h4", {}, t(titel), el("span", { class: "sehrleise mono" }, sp[k].length)),
        sp[k].slice(0, 120).map(x => el("div", { class: "karte aufgabe klickbar", onclick: () => aufgabeDialog(x.id) },
          el("div", {}, el("span", { class: "ref" }, `A${x.id}`), " ", el("span", { class: "leise" }, x.agent || "–"),
            x.einstufung === "keine_prio" ? el("span", { class: "etikett", style: "margin-left:6px" }, t("keine_prio")) : null,
            x.jetzt ? el("span", { class: "etikett gruen", style: "margin-left:6px" }, t("jetzt_bei", { x: x.jetzt })) : null,
            el("span", { class: "sehrleise", style: "float:right;font-size:12px", title: t("geaendert") + " " + zeit(x.geaendert_utc) },
              seit(x.geaendert_utc || x.angelegt_utc))),
          el("div", { class: "t" }, x.titel.length > 200 ? x.titel.slice(0, 200) + " …" : x.titel),
          x.wartet_auf ? el("div", { class: "w" }, "⇢ " + x.wartet_auf.slice(0, 160)) : null))))));
  } else {
    m.append(el("div", { class: "liste" }, liste.map(x => el("div", { class: "zeile klickbar", onclick: () => aufgabeDialog(x.id) }, el("span", { class: "ref" }, `A${x.id}`),
      el("span", { class: "leise" }, x.agent || "–"), el("span", {}, x.titel), el("span", { class: "sehrleise mono" }, zeit(x.fertig_utc || x.angelegt_utc))))));
  }
}

/* A1850 (M50 S7, D1258 v15 §10): Arbeit › Pakete – die Arbeitspakete mit Art, Zustand, Kosten und dem Grund, warum eines nicht
   startet. Eingriffe (vorziehen, zurückstellen, Pause, Notbremse) und Mitlesen nur am PC; online/Handy nur lesen (§10). */
const PK_GRUPPE = { fertig: "gruen", laeuft: "bernstein", wartet: "", blockiert: "rot" };
/* A1858 (D1258 §6.5, §6a.5): Liste „bereit zum Merge“ – je Paket diff --stat und gekürzter Diff; eine Freigabe über alle (am PC).
   Pakete, die laut Einstellung einen Blick brauchen (Server-Code), gibst du einzeln frei, nachdem du hineingesehen hast. */
function pkMerge(m, mg, tun) {
  if (!mg || !(mg.pakete || []).length) return;
  const offen = mg.pakete.filter(e => !e.freigegeben && !e.fehler);
  const ohneBlick = offen.filter(e => !e.blick);
  const karte = e => el("div", { class: "pk-merge-paket", "data-a": e.aufgabe },
    el("div", { class: "pk-merge-kopf" }, el("a", { class: "ref", onclick: () => aufgabeDialog(e.aufgabe) }, `A${e.aufgabe}`),
      el("b", { class: "pk-titel" }, e.titel), el("span", { class: "mono sehrleise" }, `${e.zweig}@${(e.kopf || "–").slice(0, 8)}`),
      e.freigegeben ? el("span", { class: "etikett gruen" }, t("mg_freigegeben")) : null,
      e.server.length ? el("span", { class: "etikett bernstein", title: e.server.join(", ") }, t("mg_server")) : null,
      e.blick && !e.freigegeben ? el("span", { class: "etikett bernstein" }, t("mg_blick")) : null),
    e.fehler ? el("p", { class: "rot-text pk-hinweis" }, e.fehler) : null,
    e.stat ? el("pre", { class: "pk-merge-stat mono" }, e.stat) : null,
    e.aussen.length ? el("p", { class: "bernstein-text pk-hinweis" }, t("mg_aussen", { x: e.aussen.join(" · ") })) : null,
    e.ohne_regression ? el("p", { class: "leise pk-hinweis" }, t("mg_ohne_regression")) : null,
    e.diff ? el("details", { class: "pk-merge-diff" }, el("summary", {}, t(e.gekuerzt ? "mg_diff_gekuerzt" : "mg_diff")),
      el("pre", { class: "mono" }, e.diff)) : null,
    !API && e.blick && !e.freigegeben && !e.fehler ? el("div", { class: "pk-knoepfe" }, el("button", { class: "klein-knopf", type: "button",
      onclick: () => tun("/api/paket/freigeben", { aufgabe: e.aufgabe, blick: true },
        t("mg_blick_frage", { x: e.aufgabe, l: mg.pruefliste.join(" · ") }), r => r.text) }, t("mg_blick_freigeben"))) : null);
  m.append(el("section", { class: "pk-merge" }, el("h3", {}, t("mg_titel", { n: mg.pakete.length })),
    el("p", { class: "leise pk-hinweis" }, t("mg_erklaerung_" + mg.merge_blick) + (mg.merge_aussen_pruefung === "aus" ? " " + t("mg_aussen_aus") : "")),
    ...mg.pakete.map(karte),
    !API && ohneBlick.length ? el("div", { class: "pk-knoepfe pk-merge-alle" }, el("button", { class: "knopf", type: "button", id: "mg-alle",
      onclick: () => tun("/api/paket/freigeben", {}, t("mg_alle_frage", { n: ohneBlick.length }), r => r.text) }, t("mg_alle", { n: ohneBlick.length }))) : null,
    API && offen.length ? el("p", { class: "sehrleise pk-hinweis" }, t("mg_nur_pc")) : null));
}
async function arbeitPakete(m) {
  let d; try { d = await holen("/api/pakete"); } catch (e) { m.append(el("div", { class: "leer" }, String(e.message || e))); return; }
  const tun = async (weg, daten, frage, ok) => { if (frage && !confirm(frage)) return;
    try { const r = await schicken(weg, daten); if (ok) toast(ok(r)); sichtArbeit(); } catch (e) { toast(t("fehler", { x: e.message }), true); } };
  const kopf = [];
  if (d.aus) kopf.push(el("p", { class: "leise pk-hinweis" }, t("pk_aus")));
  if (d.wartung) kopf.push(el("p", { class: "bernstein-text pk-hinweis" }, t("pk_wartung", { x: d.wartung.grund || "" })));
  kopf.push(el("div", { class: "pk-leiste" },
    el("span", {}, d.pause ? el("b", { class: "bernstein-text" }, t("pk_pausiert", { x: zeit(d.pause.seit) })) : t("pk_laeuft_frei")),
    d.pause && d.pause.grund ? el("span", { class: "sehrleise" }, d.pause.grund) : null,
    !API ? el("button", { class: "klein-knopf", type: "button", id: "pk-pause", onclick: () => d.pause
      ? tun("/api/paket/pause", { an: false }, t("pk_weiter_frage"), () => t("pk_weiter_ok"))
      : tun("/api/paket/pause", { an: true }, t("pk_pause_frage"), () => t("pk_pause_ok")) }, t(d.pause ? "pk_weiter" : "pk_pause")) : null,
    ...d.plaetze.map(p => el("span", { class: "pk-platz" }, el("b", {}, t("pk_platz", { n: p.nr })), " ",
      p.laeuft === true ? el("span", { class: "etikett bernstein" }, t("pk_arbeitet")) : p.laeuft === false ? el("span", { class: "etikett" }, t("pk_frei")) : null,
      !API ? el("button", { class: "klein-knopf", type: "button", onclick: () => mitlesenDialog(p.nr) }, t("pk_mitlesen")) : null,
      !API && p.laeuft ? el("button", { class: "klein-knopf rot", type: "button", onclick: () =>
        tun("/api/paket/notbremse", { platz: p.nr }, t("pk_notbremse_frage", { n: p.nr }), r => r.text) }, t("pk_notbremse")) : null)),
    API ? el("span", { class: "sehrleise" }, t("pk_nur_pc")) : null));
  m.append(el("div", { class: "pk-kopf" }, ...kopf));
  if (!d.pakete.length) { m.append(el("div", { class: "leer" }, t("pk_leer"))); return pkTabelle(m, d); }
  const pkSpanne = (p, f) => p[0] == null ? "–" : (p[1] == null || p[1] === p[0]) ? `${f(p[0])}` : `${f(p[0])}–${f(p[1])}`;   // A1955: P50–P85
  const grund = x => {
    if (x.zustand === "startklar" && x.grund) return el("span", {}, t("pk_startet_nicht", { x: x.grund.text }), " ",
      el("span", { class: "sehrleise", title: zeit(x.grund.zeit) }, `(${t("pk_regel", { n: x.grund.regel })})`));
    if (x.zustand === "wartet_interaktiv") return el("span", { class: x.dran === "mensch" ? "bernstein-text" : "" }, t(x.dran === "mensch" ? "pk_dran_du" : "pk_dran_lead"),
      x.letzter_grund ? el("span", { class: "sehrleise" }, " – " + x.letzter_grund) : null);
    if (["blockiert", "unklar", "abgebrochen"].includes(x.zustand) && x.letzter_grund) return el("span", { class: "sehrleise" }, x.letzter_grund);
    return null; };
  const zeile = x => el("div", { class: `pk-zeile gruppe-${x.gruppe}`, "data-a": x.id },
    el("a", { class: "ref", onclick: () => aufgabeDialog(x.id) }, `A${x.id}`),
    el("span", { class: "pk-titel" }, x.titel),
    el("span", { class: "etikett" }, x.art === "p" ? t("pk_art_p") : t("pk_art_sitzung")),
    el("span", { class: "pk-zustand" }, el("span", { class: "etikett " + PK_GRUPPE[x.gruppe] }, t("pk_g_" + x.gruppe)), " ",
      x.zustand ? el("span", { class: "leise", title: x.seit ? zeit(x.seit) : "" }, t("pk_z_" + x.zustand)) : null),
    (() => {   /* A1955 + TH156 Regel 7: ein Wert in der Spalte (gemessen, sonst ≈ P50); die Spanne nur im Tooltip und auf Antippen */
      const geld = v => v.toLocaleString(gebiet(), { minimumFractionDigits: 2, maximumFractionDigits: 2 });
      if (!x.spanne) return el("span", { class: "pk-kosten mono" }, x.usd ? `${geld(x.usd)} $` : "–");
      const k = pkSpanne(x.spanne.kosten, geld), d = pkSpanne(x.spanne.dauer_s, v => Math.round(v / 60));
      const mehr = el("div", { class: "sehrleise pk-spanne", hidden: true }, t("pk_spanne", { k, d }));
      return el("span", { class: "pk-kosten mono klickbar", title: t("pk_spanne_h", { n: x.spanne.n, k, d }), onclick: () => { mehr.hidden = !mehr.hidden; } },
        x.usd ? `${geld(x.usd)} $` : x.spanne.kosten[0] != null ? `≈ ${geld(x.spanne.kosten[0])} $` : "–", mehr);
    })(),
    el("span", { class: "pk-grund" }, grund(x)),
    !API && x.art === "p" && ["entwurf", "startklar", "zurueckgestellt"].includes(x.zustand) ? el("span", { class: "pk-knoepfe" },
      el("button", { class: "klein-knopf", type: "button", onclick: () => tun("/api/paket/vorziehen", { aufgabe: x.id }, null, () => t("pk_vorgezogen", { x: x.id })) }, t("pk_vorziehen")),
      x.zustand !== "zurueckgestellt" ? el("button", { class: "klein-knopf", type: "button", onclick: () =>
        tun("/api/paket/zurueckstellen", { aufgabe: x.id }, t("pk_zurueck_frage", { x: x.id }), () => t("pk_zurueckgestellt", { x: x.id })) }, t("pk_zurueckstellen")) : null)
      : el("span", { class: "pk-knoepfe" }));
  m.append(el("div", { class: "pk-liste" }, el("div", { class: "pk-zeile pk-kopfzeile sehrleise" }, el("span", {}, ""), el("span", {}, t("pk_s_titel")),
    el("span", {}, t("pk_s_art")), el("span", {}, t("pk_s_zustand")), el("span", {}, t("pk_s_kosten")), el("span", {}, t("pk_s_grund")), el("span", {}, "")),
    d.pakete.map(zeile)));
  pkMerge(m, d.merge, tun);
  pkTabelle(m, d);
}
/* Zuordnung Zustand → Gruppe (D1258 §4) als Tabelle – dieselbe Tabelle wie im Code (paketliste.GRUPPE) */
function pkTabelle(m, d) {
  const g = d.gruppen || {};
  m.append(el("details", { class: "pk-zuordnung" }, el("summary", {}, t("pk_zuordnung")),
    el("table", {}, el("tr", {}, el("th", {}, t("pk_s_zustand")), el("th", {}, t("pk_s_gruppe"))),
      Object.keys(g).map(z => el("tr", {}, el("td", {}, t("pk_z_" + z)), el("td", {}, el("span", { class: "etikett " + PK_GRUPPE[g[z]] }, t("pk_g_" + g[z]))))))));
}
/* A2044 (V4, D1531 §3): ein Fenster, das sich im Takt selbst nachlädt, solange es offen ist (und bis der Lauf zu Ende ist). Unten
   bleibt es unten, wenn du unten warst; hast du hochgescrollt, bleibt die Stelle. */
const MITLESEN_TAKT_MS = 3000;
function imTakt(hg, kasten, laden) {
  let ende = false;
  const schritt = async () => {
    if (!hg.isConnected || ende) return;
    const unten = kasten.scrollHeight - kasten.scrollTop - kasten.clientHeight < 24;
    ende = await laden();
    if (unten) kasten.scrollTop = kasten.scrollHeight;
    if (!ende && hg.isConnected) setTimeout(schritt, MITLESEN_TAKT_MS);
  };
  schritt();
}
async function mitlesenDialog(nr) {
  const inhalt = el("div", { class: "pk-mitlesen mono" }, t("lade_text"));
  const hg = dialog(t("pk_ml_titel", { n: nr }), el("p", { class: "leise", style: "margin:0 0 8px" }, t("pk_ml_h")), inhalt);
  imTakt(hg, inhalt, async () => {
    try { const r = await abrufen("/api/paket/mitlesen?platz=" + nr);
      inhalt.replaceChildren(...(r.zeilen.length ? r.zeilen.map(z => el("div", { class: "pk-ml " + z.art },
        el("b", {}, t("pk_ml_" + z.art)), " ", z.text)) : [el("div", { class: "sehrleise" }, t("pk_ml_leer"))]));
      return false; }                                   /* ein Platz arbeitet weiter – im Takt bleiben, solange offen */
    catch (e) { inhalt.replaceChildren(el("div", { class: "rot-text" }, String(e.message || e))); return true; } });
}
async function laufAusgabeDialog(lid) {
  const inhalt = el("div", { class: "pk-mitlesen mono" }, t("lade_text"));
  const kopf = el("p", { class: "leise", style: "margin:0 0 8px" }, t("la_h"));
  const hg = dialog(t("la_titel", { l: lid }), kopf, inhalt);
  imTakt(hg, inhalt, async () => {
    try { const r = await abrufen("/api/lauf/ausgabe?lauf=" + lid);
      const fertig = !["angemeldet", "laeuft"].includes(r.status);
      kopf.textContent = [r.beschreibung, fertig ? t("la_ende", { x: t("la_" + r.status) || r.status, rc: r.rc ?? "–" }) : t("la_laeuft"),
        r.gekuerzt ? t("la_gekuerzt", { n: r.zeilen.length }) : null].filter(Boolean).join(" · ");
      inhalt.replaceChildren(...(r.zeilen.length ? r.zeilen.map(z => el("div", {}, z)) : [el("div", { class: "sehrleise" }, t(r.datei ? "la_leer" : "la_ohne"))]));
      return fertig; }
    catch (e) { inhalt.replaceChildren(el("div", { class: "rot-text" }, String(e.message || e))); return true; } });
}


/* --- Planung ------------------------------------------------------------------------------- */
const datumKurz = x => x ? new Date(x + "T12:00:00").toLocaleDateString(gebiet(), { day: "2-digit", month: "2-digit" }) : "–";
const ampelKlasse = a => a === "gruen" ? "gruen" : a === "gelb" ? "bernstein" : a === "rot" ? "rot" : "";
const tmZeit = utc => new Date(utc).toLocaleString(gebiet(), { weekday: "short", day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
/* Terminplaner: Vorkommen nach Tagen; Testtermine mit Frist „Testbuild fertig“, Ampel des Bogens und Meldung „bereit“ */
/* KI-Fenster als Band über 24 h (Ortszeit) mit Strich für jetzt; darüber, ob es offen ist und was mit --nachts wartet */
function kiFensterBand(kf) {
  if (!kf) return null;
  const pz = m => `${(m / 1440 * 100).toFixed(2)}%`, jetzt = new Date(), jm = jetzt.getHours() * 60 + jetzt.getMinutes();
  const teile = kf.von == null ? [] : kf.von < kf.bis ? [[kf.von, kf.bis]] : [[kf.von, 1440], [0, kf.bis]];
  const zeile = (kf.von == null ? t("kf_keins") : t("kf_titel", { x: kf.text }) + " · " + (kf.termin ? t("kf_termin", { x: kf.termin }) : t(kf.offen ? "kf_offen" : "kf_zu")))
    + (kf.wartend ? " · " + t(kf.wartend === 1 ? "kf_wartend1" : "kf_wartend", { n: kf.wartend }) + (kf.sekunden ? t("kf_dauer", { x: Math.max(1, Math.round(kf.sekunden / 60)) }) : "") : "");
  return el("div", { class: "kf" }, el("div", { class: kf.wartend ? "" : "leise" }, zeile),
    teile.length ? el("div", { class: "kf-band", role: "img", "aria-label": t("kf_titel", { x: kf.text }) },
      teile.map(([a, b]) => el("div", { class: "kf-fenster", style: `left:${pz(a)};width:${pz(b - a)}` })),
      el("div", { class: "kf-jetzt", style: `left:${pz(jm)}`, title: jetzt.toLocaleTimeString(gebiet(), { hour: "2-digit", minute: "2-digit" }) })) : null,
    teile.length ? el("div", { class: "kf-skala" }, ["0", "6", "12", "18", "24"].map(x => el("span", {}, x))) : null,
    el("p", { class: "sehrleise", style: "margin:4px 0 0;font-size:12.5px" }, t("kf_erkl")));
}
function termineAnsicht(l, kf) {
  if (!l.length) return el("div", {}, kiFensterBand(kf), el("div", { class: "leer" }, t("tm_leer")), el("p", { class: "leise" }, t("tm_erkl"), " ", hilfeKnopf("termine")));
  const tage = {};
  for (const v of l) (tage[new Date(v.am_utc).toDateString()] ||= []).push(v);
  return el("div", {}, kiFensterBand(kf), el("p", { class: "leise", style: "margin:0 0 12px" }, t("tm_erkl"), " ", hilfeKnopf("termine")),
    Object.values(tage).map(vs => el("div", { class: "tm-tag" },
      el("h4", {}, new Date(vs[0].am_utc).toLocaleDateString(gebiet(), { weekday: "long", day: "2-digit", month: "2-digit" })),
      vs.map(v => el("div", { class: "karte tm-termin" + (new Date(v.am_utc) < new Date() ? " vorbei" : "") },
        el("div", {}, el("span", { class: "mono" }, new Date(v.am_utc).toLocaleTimeString(gebiet(), { hour: "2-digit", minute: "2-digit" })), " ",
          el("span", { class: "etikett" }, t("tm_art_" + v.art)), " ", el("b", {}, v.titel), " ", el("span", { class: "ref" }, `T${v.termin_id}`),
          v.woechentlich ? el("span", { class: "sehrleise" }, " · " + t("tm_woechentlich")) : null),
        v.frist_utc ? el("div", { class: "leise", style: "margin-top:4px" }, t("tm_frist", { x: tmZeit(v.frist_utc) }),
          v.ampel ? el("span", {}, " · ", el("span", { class: "punkt " + ampelKlasse(v.ampel) }), " ", t("tm_ampel", { b: bogenNr(v.bogen_id), a: t("ampel_" + v.ampel) })) : null) : null,
        v.bereit ? el("div", { class: "gruen-text", style: "margin-top:4px;white-space:pre-wrap" }, "✓ " + t("tm_bereit") + " – " + (v.bereit.text || ""))
          : v.art === "test" ? el("div", { class: "sehrleise", style: "margin-top:4px" }, t("tm_offen")) : null,
        v.notiz ? el("div", { class: "sehrleise", style: "margin-top:4px" }, v.notiz) : null)))));
}
/* A1950 (K6, TH164): Grob- und Feinplanung nach der abgenommenen Kleinprobe D1365 – Meilensteine aus Themen, Pakete je Meilenstein,
   „Jetzt starten“. Ein Status je Eintrag, nur mögliche Knöpfe, Werte statt Sätze; am Handy zuerst die Liste (W2431). */
function pmZeit(utc) { return utc ? new Date(utc).toLocaleString(gebiet(), { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" }) : ""; }
function pmGeld(x) { return x == null ? "–" : x.toFixed(2).replace(".", sprache === "de" ? "," : ".") + " $"; }
function toreLeiste(d, kurz) {                                        /* K7 (A1944): alle fünf Tore, abgeleitet – ✓ zu, ● jetzt */
  if (!d || !d.tore) return null;
  const text = x => x.tor === "grobplanung" ? t("tor_t_grob", { n: x.n, g: x.g }) + (x.mg ? " · " + t("tor_t_grob_m", { n: x.mn, g: x.mg }) : "")
    : x.tor === "feinplanung" ? (x.g ? t("tor_t_fein", { n: x.n, g: x.g }) : t("tor_t_fein_leer"))
    : x.tor === "umsetzung" ? (x.laufend ? t("tor_t_um", { n: x.n, g: x.g }) : t("tor_t_um_m", { n: x.mn, g: x.mg }))
    : x.tor === "abschluss" ? t("tor_t_ab", { n: x.n, g: x.g }) : t("th2_stand", { n: x.n, g: x.g });
  const jetzt = d.tore.find(x => x.tor === d.aktuell);
  const art = x => x.zu ? "zu" : x.tor === d.aktuell ? "jetzt" : "spaeter", zeichen = x => x.zu ? "✓" : x.tor === d.aktuell ? "●" : "○";
  if (kurz) {                                   /* A1972 (TH156 Regel 3/5/7): nur die fünf Chips – die Werte eines Tors auf Klick */
    const info = el("div", { class: "tore-info" }); info.hidden = true;
    let offen = null;
    const chips = d.tore.map(x => el("button", { type: "button", class: "tor " + art(x), "data-t": x.tor, "aria-expanded": "false",
      onclick: () => { offen = offen === x.tor ? null : x.tor; info.hidden = !offen;
        chips.forEach(c => c.setAttribute("aria-expanded", String(c.dataset.t === offen)));
        if (offen) info.replaceChildren(...(x.tor === "konzept" ? [text(x)] : [el("b", {}, t("tor_" + x.tor)), " · ", text(x)])); } },
      el("span", { class: "tor-zeichen" }, zeichen(x)), " ", t("tor_" + x.tor)));
    return el("div", { class: "tore-leiste kurz", "data-tor": d.aktuell || "fertig" }, el("div", { class: "tore" }, chips), info);
  }
  return el("div", { class: "tore-leiste", "data-tor": d.aktuell || "fertig" },
    el("ol", { class: "tore" }, ...d.tore.map(x => el("li", { class: "tor " + (x.zu ? "zu" : x.tor === d.aktuell ? "jetzt" : "spaeter"),
      "data-t": x.tor, title: text(x) }, el("span", { class: "tor-zeichen" }, x.zu ? "✓" : x.tor === d.aktuell ? "●" : "○"), " ", t("tor_" + x.tor)))),
    el("span", { class: "tore-text" }, jetzt ? (jetzt.tor === "konzept" ? text(jetzt) : `${t("tor_" + jetzt.tor)} · ${text(jetzt)}`) : t("tor_alle_zu")),
    (d.nichts_offen || []).length ? el("span", { class: "tore-text sehrleise" }, t("tor_nichts_offen", { n: d.nichts_offen.length })) : null);
}
function toreDich(f, zumThema) {                /* A1972 (TH156 Regel 6): höchstens EINE Zeile, nur wenn du handeln musst – Anzahl + Sprung */
  if (!f || !(f.themen || f.meilensteine)) return null;
  const sprung = (text, art, tun) => el("a", { href: "#", class: "verweis", "data-sprung": art, onclick: e => { e.preventDefault(); tun(); } }, text);
  const teile = [f.themen ? sprung(f.themen === 1 ? t("tor_dich_th1") : t("tor_dich_th", { n: f.themen }), "themen", zumThema) : null,
    f.meilensteine ? sprung(f.meilensteine === 1 ? t("tor_dich_ms1") : t("tor_dich_ms", { n: f.meilensteine }), "meilensteine",
      () => { zustand.planReiter = "meilensteine"; zeige("planung"); }) : null].filter(Boolean);
  return el("div", { class: "tore-dich" }, el("span", { class: "bernstein-text" }, t("tor_dich")), " ", teile[0], teile[1] ? " · " : null, teile[1] || null);
}
function pmStand(pa) {
  const ms = pa.meilensteine, offen = ms.filter(m => m.status === "geplant"), voll = offen.filter(m => m.pakete.length);
  const pakete = voll.reduce((n, m) => n + m.pakete.length, 0), summe = voll.reduce((n, m) => n + (m.summe || 0), 0);
  const text = pa.tor === "umsetzung" ? t("pm_stand_um", { n: ms.filter(m => m.status === "aktiv").length })
    : pa.tor === "fein" ? t("pm_stand_fein", { n: voll.filter(m => m.plan.frei).length, g: voll.length, p: pakete, k: pmGeld(summe) })
    : t("pm_stand_grob", { n: offen.filter(m => m.grob.frei).length, g: offen.length });
  return el("div", {}, toreLeiste(pa.tore), el("div", { class: "th-stand pm-stand", "data-tor": pa.tor }, el("span", {}, text)));
}
function pmAbschluss(x, tun) {                                 /* K7 (A1944): Abschlussbericht und Ja dazu */
  const ab = x.abschluss, k = el("div", { class: "th-kasten" }), ja = () => tun("freigeben", { art: "abschluss" }, t("pm_ab_ok"));
  const dagegen = pwDagegen(ab.lage, ab.lage_zaehlt, ab.vorbehalte, ab.alt), fragen = dagegen || [];   /* A2088: wie auf Projektweg */
  return el("div", { class: "pm-abschluss", "data-ab": ab.frei ? "frei" : !ab.bericht ? "kommt" : x.bei_dir || !ab.lage ? "wartet" : "ruhig" },   /* A2116: Farbe nur, wenn der Mensch dran ist (TH156 Regel 4) */
    el("div", { class: "pm-entwuerfe-kopf" }, t("pm_ab_kopf")),
    ab.bericht ? el("div", {}, el("a", { href: "#", class: "ref", onclick: e => { e.preventDefault(); dokumentDialog(ab.bericht); } }, "D" + ab.bericht),
      " ", t("pm_ab_bericht")) : el("div", { class: "sehrleise" }, t("pm_ab_kommt")),
    ab.frei ? el("div", { class: "sehrleise" }, t("pm_ab_frei", { x: ab.durch ? t("pm_co_lead", { x: ab.durch.join(", ") }) : ab.von === "Entwickler" ? t("pm_du") : ab.von }))
      : ab.ja_fehlt?.length ? el("div", { class: "pm-ja-fehlt sehrleise" }, t("pm_ja_fehlt", { x: ab.ja_fehlt.join(", ") })) : null,
    !ab.frei && ab.notiz ? el("div", { class: "th-grund" }, t("pm_zurueck_notiz", { x: ab.notiz })) : null,
    fragen.length ? el("div", { class: "pjw-vorbehalte" + (x.bei_dir || !ab.lage ? "" : " ruhig") }, el("div", { class: "pjw-lbl" }, t("pjw_vorbehalte")), el("ul", {}, fragen.map(v => el("li", {}, v)))) : null,
    !ab.frei && ab.bericht && !API ? el("div", { class: "th-knoepfe" },
      dagegen ? el("button", { class: "klein-knopf" + (ab.lage_zaehlt ? "" : " haupt"), type: "button", "data-h": "ab-ja", onclick: fragen.length ? pwTrotzdem(fragen, ja) : ja }, t(fragen.length ? "pjw_trotzdem" : "pm_ab_ja"))
        : el("span", { class: "leise" }, pwLageLang({ ...x, lage: ab.lage })),
      el("button", { class: "klein-knopf", type: "button", "data-h": "ab-zurueck", onclick: () => {
        const feld = el("textarea", { class: "th-feld", placeholder: t("th2_notiz_ph") });
        k.replaceChildren(feld, el("div", { class: "th-knoepfe" },
          el("button", { class: "klein-knopf haupt", type: "button", onclick: () => { if (!feld.value.trim()) { feld.focus(); return; }
            tun("zurueck", { art: "abschluss", notiz: feld.value }, t("th2_ok_zurueck")); } }, t("th2_zurueckgeben")),
          el("button", { class: "klein-knopf", type: "button", onclick: () => k.replaceChildren() }, t("abbrechen"))));
        feld.focus(); } }, t("th2_h_zurueck"))) : null, k);
}
function pmStatus(m, art) {                                       /* ein Status je Eintrag */
  if (m.status === "fertig") return art === "grob" && m.abschluss && m.abschluss.bericht && !m.abschluss.frei
    ? ["dich", t("pm_ab_wartet")] : ["frei", t("pm_fertig")];
  if (m.bereit) return m.bei_dir ? ["dich", t("pm_bereit")] : ["arbeit", pwLage(m)];   /* A2002: alle Pakete fertig, das Ja zum Abschluss fehlt; A2082: nur, wenn es geht */
  if (m.status === "aktiv") return ["frei", t("pm_laeuft")];
  if (art === "plan" && !m.pakete.length) return ["arbeit", t("pm_spaeter")];
  const z = m[art];
  return z.frei ? ["frei", t("th2_frei")] : z.notiz ? ["arbeit", t("pm_zurueck_an_lead")] : ["dich", t("th2_dich")];
}
async function pmPlanJa(e) {
  await einmalTun("plan-ja/" + e.eid, async () => { await schicken("/api/meilenstein/plan-ja", { thema: e.thema, eid: e.eid }); toast(e.ja ? pwDeltaOk(e.ja) : t("pm_ok_angelegt")); zeige("planung", true); });
}
function pmAnsicht(pa, art) {
  const m = el("div", { class: "pm-ansicht", "data-pm": art });
  m.append(pmStand(pa));
  if (art === "plan" && pa.starten && !API) m.append(el("div", { class: "pm-start" },   /* „Jetzt starten“ nur, wenn alles freigegeben ist */
    el("span", {}, t("pm_start_text", { n: pa.meilensteine.filter(x => x.status === "geplant" && x.pakete.length).length })),
    el("button", { class: "knopf pm-start-knopf", type: "button", onclick: async () => { if (!confirm(t("pm_start_frage"))) return;
      await einmalTun("ms/starten", async () => { const r = await schicken("/api/meilenstein/starten", {}); toast(t("pm_ok_start", { x: r.gestartet.join(", ") })); zeige("planung", true); }); } }, t("pm_start"))));
  if (art === "grob" && (pa.aenderungen || []).length) m.append(el("div", { class: "pm-entwuerfe pm-aenderungen" },   /* A1957 */
    el("div", { class: "pm-entwuerfe-kopf" }, t("pm_aenderungen", { n: pa.aenderungen.length })),
    ...pa.aenderungen.map(x => el("div", { class: "pm-entwurf", "data-ae": x.aenderung, "data-stand": x.stand },
      el("div", {}, el("b", {}, x.was), " · ", x.stand === "prueft" ? t("pm_ae_prueft", { z: pmZeit(x.seit_utc) })
        : x.stand === "fehler" ? t("pm_ae_fehler") : t("pm_ae_wartet", { x: x.beruehrt.join(", ") })),
      el("ul", { class: "pm-entwurf-zeilen" }, ...Object.keys(x.neu).map(k => el("li", {}, `${t("pm_feld_" + k)}: `, el("s", {}, String(x.alt[k] ?? "–")), " → ", String(x.neu[k] ?? "–"))),
        ...x.folgen.map(f => el("li", { class: "sehrleise" }, f))),
      x.stand !== "prueft" && !API ? el("div", { class: "th-knoepfe" },
        el("button", { class: "klein-knopf haupt", type: "button", "data-h": "ae-ja", onclick: async () => {
          await einmalTun("ae/" + x.aenderung, async () => { await schicken("/api/meilenstein/aenderung-ja", { aenderung: x.aenderung }); toast(t("pm_ae_ok_ja")); zeige("planung", true); }); } }, t("pm_ae_ja")),
        el("button", { class: "klein-knopf", type: "button", "data-h": "ae-weg", onclick: async () => {
          await einmalTun("ae/" + x.aenderung, async () => { await schicken("/api/meilenstein/aenderung-verwerfen", { aenderung: x.aenderung }); toast(t("pm_ae_ok_weg")); zeige("planung", true); }); } }, t("pm_ae_verwerfen"))) : null))));
  if (art === "grob" && ((pa.entwuerfe || []).length || (pa.planer_laeuft || []).length)) m.append(el("div", { class: "pm-entwuerfe" + (pa.entwuerfe.some(e => !e.wartet) ? "" : " ruhig") },   /* A1940: Entwürfe des Planers; A2118: Farbe nur, wenn einer auf das Ja wartet */
    el("div", { class: "pm-entwuerfe-kopf" }, t(pa.entwuerfe.some(e => e.ja) ? "pm_entwuerfe_n" : "pm_entwuerfe", { n: pa.entwuerfe.length })),   /* A2112: eine Änderung gibt man frei */
    ...pa.planer_laeuft.map(l => el("div", { class: "pm-entwurf sehrleise", "data-th": l.thema }, t("pm_planer_laeuft", { x: `TH${l.thema} ${l.name}`, z: pmZeit(l.seit_utc) }))),
    ...pa.entwuerfe.map(e => el("details", { class: "pm-entwurf", "data-th": e.thema },
      el("summary", {}, el("b", {}, `TH${e.thema} ${e.name}`), " · ",
        e.fehler ? t("pm_entwurf_fehler") : e.wartet ? t("pjw_wartet") : e.nichts ? t("pm_entwurf_nichts") : t("pm_entwurf_umfang", { m: e.meilensteine, p: e.pakete }),
        e.usd != null ? ` · ${pmGeld(e.usd)}` : ""),
      e.fehler ? el("ul", { class: "pm-entwurf-zeilen" }, ...e.fehler.map(f => el("li", {}, f)))
        : e.nichts ? el("p", { class: "sehrleise" }, e.grund) : el("ul", { class: "pm-entwurf-zeilen" }, ...e.zeilen.map(z => el("li", {}, z))),
      e.wartet && !e.fehler ? pwZurueckgestellt(e.wartet, () => pmPlanJa(e)) : null,                       /* A2118 */
      API ? (e.wartet ? null : el("span", { class: "sehrleise" }, t("pm_nur_pc"))) : el("div", { class: "th-knoepfe" },
        !e.fehler && !e.wartet ? el("button", { class: "klein-knopf haupt", type: "button", "data-h": "plan-ja", onclick: () => pmPlanJa(e) }, e.ja ? pwDeltaKnopfText(e.thema, e.ja) : e.nichts ? t("pm_ja_nichts") : t("pm_ja_anlegen")) : null,
        el("button", { class: "klein-knopf", type: "button", "data-h": "neu-planen", onclick: async () => {
          try { await schicken("/api/meilenstein/neu-planen", { thema: e.thema }); toast(t("pm_ok_neu_planen")); zeige("planung", true); }
          catch (x) { toast(t("fehler", { x: x.message }), true); } } }, t("pm_neu_planen")))))));
  const liste = pa.meilensteine.filter(x => art === "grob" || x.status !== "fertig");
  if (!liste.length) { m.append(el("div", { class: "leer" }, t("pm_leer"))); return m; }
  const schluessel = art === "grob" ? "msOffen" : "planOffen";
  let offen = zustand[schluessel] && liste.some(x => x.id === zustand[schluessel]) ? zustand[schluessel] : (liste.find(x => pmStatus(x, art)[0] === "dich") || liste[0]).id;
  const raster = el("div", { class: "th-raster" + (zustand[schluessel] ? " offen" : "") });   /* Handy: erst die Liste */
  const links = el("div", { class: "th-liste" }), rechts = el("div", { class: "th-thema" });
  const werte = x => art === "grob" ? [t(x.themen.length === 1 ? "pm_themen1" : "pm_themen", { n: x.themen.length }), x.endet_mit || null].filter(Boolean).join(" · ")
    : x.pakete.length ? `${t("pm_pakete_n", { n: x.pakete.length })} · ${t("pm_ca", { k: pmGeld(x.summe) })}` : t("pm_spaeter_h");
  const zeichneListe = () => links.replaceChildren(...liste.map(x => { const [k, s] = pmStatus(x, art); return el("div", {
      class: "th-zeile pm-zeile" + (x.id === offen ? " gewaehlt" : ""), "data-ms": x.id,
      onclick: () => { offen = x.id; zustand[schluessel] = x.id; raster.classList.add("offen"); zeichneListe(); zeichneDetail(); } },
    el("span", { class: "th-name" }, el("span", { class: "pm-nr" }, x.nr), " ", x.titel, el("span", { class: "th-grund-zeile" }, werte(x))),
    el("span", { class: "th-status " + k }, s)); }),
    art === "grob" && pa.ohne_meilenstein.length ? el("div", { class: "pm-ohne sehrleise" }, t("pm_ohne"), " ",
      pa.ohne_meilenstein.map(x => `TH${x.id} ${x.name}`).join(", ")) : "");
  function zeichneDetail() {
    const x = liste.find(y => y.id === offen), z = x[art], [k, s] = pmStatus(x, art), kasten = el("div", { class: "th-kasten" });
    const tun = async (was, extra, ok) => { zustand[schluessel] = x.id;   /* vor dem Senden: schicken zeichnet selbst neu */
      await einmalTun(`ms/${was}/${x.id}/${art}${JSON.stringify(extra)}`, async () => { await schicken(`/api/meilenstein/${was}`, { bogen: x.id, art, ...extra }); toast(ok); zeige("planung", true); }); };
    const offenNr = pa.meilensteine.filter(y => ["geplant", "aktiv"].includes(y.status)), i = offenNr.findIndex(y => y.id === x.id);
    const knoepfe = API ? [el("span", { class: "sehrleise" }, t("pm_nur_pc"))] : [
      x.status === "geplant" && !z.frei && (art === "grob" || (x.grob.frei && x.pakete.length)) ? el("button", { class: "klein-knopf haupt", type: "button",
        "data-h": art === "plan" ? "plan-starten" : "freigeben",                                  /* A2031: Feinplan-Ja = Start, ein Klick */
        onclick: () => art === "plan" ? tun("plan-starten", {}, t("pm_ok_plan_start", { x: x.nr })) : tun("freigeben", {}, t("th2_ok_freigeben")) },
        t(art === "plan" ? "pm_plan_starten" : "th2_h_freigeben")) : null,
      x.status === "geplant" && (art === "grob" || x.pakete.length) ? el("button", { class: "klein-knopf", type: "button", "data-h": "zurueck", onclick: () => {
        const feld = el("textarea", { class: "th-feld", placeholder: t("th2_notiz_ph") });
        kasten.replaceChildren(feld, el("div", { class: "th-knoepfe" },
          el("button", { class: "klein-knopf haupt", type: "button", onclick: () => { if (!feld.value.trim()) { feld.focus(); return; }
            tun("zurueck", { notiz: feld.value }, t("th2_ok_zurueck")); } }, t("th2_zurueckgeben")),
          el("button", { class: "klein-knopf", type: "button", onclick: () => kasten.replaceChildren() }, t("abbrechen"))));
        feld.focus(); } }, t("th2_h_zurueck")) : null,
      art === "grob" && i > 0 ? el("button", { class: "klein-knopf", type: "button", "data-h": "frueher", onclick: () => tun("frueher", {}, t("pm_ok_verschoben")) }, t("pm_frueher")) : null,
      art === "grob" && i >= 0 && i < offenNr.length - 1 ? el("button", { class: "klein-knopf", type: "button", "data-h": "spaeter", onclick: () => tun("spaeter", {}, t("pm_ok_verschoben")) }, t("pm_spaeter_k")) : null
    ].filter(Boolean);
    const tabelle_ = () => el("table", { class: "pm-pakete" },
      el("thead", {}, el("tr", {}, ...["#", t("pm_t_paket"), t("pm_t_wer"), t("pm_t_nach"), t("pm_t_pruefung"), t("pm_t_kosten")].map((h, j) => el("th", { class: j === 5 ? "zahl" : "" }, h)))),
      el("tbody", {}, ...x.pakete.map((p, j) => el("tr", { "data-a": p.id, onclick: e => e.currentTarget.classList.toggle("auf") },   /* Handy: Einzelkosten auf Klick */
        el("td", { class: "pm-nr-z" }, j + 1), el("td", { class: "pm-titel-z" }, el("span", { class: "ref" }, "A" + p.id), " ", p.titel),
        el("td", { "data-l": t("pm_t_wer") + ":" }, p.wer), el("td", { "data-l": t("pm_t_nach") + ":" }, p.nach.length ? p.nach.map(n => "A" + n).join(", ") : "–"),
        el("td", { "data-l": t("pm_t_pruefung") + ":" }, p.pruefung),
        el("td", { class: "zahl", title: p.usd == null ? "" : t(p.gemessen ? "pm_gemessen" : "pm_geschaetzt") }, (p.usd != null && !p.gemessen ? "≈ " : "") + pmGeld(p.usd)))),
        el("tr", { class: "pm-summe" }, el("td", { class: "pm-nr-z" }), el("td", { class: "pm-titel-z" }, t("pm_summe")), el("td"), el("td"), el("td"),
          el("td", { class: "zahl" }, pmGeld(x.summe)))));
    rechts.replaceChildren(...[
      el("div", { class: "th-kopf" }, el("button", { class: "klein-knopf th-zur-liste", type: "button",
        onclick: () => { zustand[schluessel] = null; raster.classList.remove("offen"); } }, "‹ " + t(art === "grob" ? "pm_meilensteine" : "pm_pakete")),
        el("h2", {}, `${x.nr} · ${x.titel}`), el("span", { class: "th-status " + k }, s)),
      el("div", { class: "pm-werte" }, art === "grob" ? [x.endet_mit ? el("span", {}, t("pm_endet"), " ", el("b", {}, x.endet_mit)) : null,
        el("span", {}, el("b", {}, x.pakete.length), " ", t("pm_pakete_kurz"))].filter(Boolean)
        : x.pakete.length ? [el("span", {}, el("b", {}, x.pakete.length), " ", t("pm_pakete_kurz")), el("span", { class: "pm-summe-oben" }, t("pm_summe_ca"), " ", el("b", {}, pmGeld(x.summe)))] : []),
      z.frei && z.von ? el("div", { class: "pm-frei-von sehrleise" }, t(art === "grob" ? "pm_frei_von" : "pm_plan_frei_von",
        { x: z.durch ? t("pm_co_lead", { x: z.durch.join(", ") }) : z.von === "Entwickler" ? t("pm_du") : z.von, z: pmZeit(z.zeit_utc) })) : null,
      !z.frei && z.ja_fehlt?.length && x.status === "geplant" ? el("div", { class: "pm-ja-fehlt sehrleise" }, t("pm_ja_fehlt", { x: z.ja_fehlt.join(", ") })) : null,   /* K1 (B2913) */
      !z.frei && z.notiz ? el("div", { class: "th-grund" }, t("pm_zurueck_notiz", { x: z.notiz })) : null,
      !z.frei && z.geaendert ? el("div", { class: "th-grund pm-seit-frei" }, t(art === "grob" ? "pm_geaendert_grob" : "pm_geaendert_plan")) : null,   /* P461 (1) */
      ...(x.geaendert || []).map(g => el("div", { class: "th-grund pm-geaendert", "data-th": g.id },   /* K8 (A1942): Thema geändert */
        t("pm_thema_geaendert", { x: `TH${g.id} ${g.name}`, n: g.fassung }),
        API ? null : el("span", { class: "pm-geaendert-knoepfe" },
          el("button", { class: "klein-knopf", type: "button", "data-h": "neu-planen-k8", onclick: async () => {
            try { await schicken("/api/meilenstein/neu-planen", { thema: g.id }); toast(t("pm_ok_neu_planen")); zeige("planung", true); }
            catch (e) { toast(t("fehler", { x: e.message }), true); } } }, t("pm_neu_planen")),
          g.offen?.length ? el("button", { class: "klein-knopf", type: "button", "data-h": "anhalten", onclick: async () => {
            if (!confirm(t("pm_anhalten_frage", { n: g.offen.length }))) return;
            zustand.msOffen = x.id;                                                     /* vor dem Senden: schicken zeichnet neu */
            try { const r = await schicken("/api/meilenstein/anhalten", { thema: g.id, bogen: x.id }); toast(t("pm_ok_angehalten", { n: r.angehalten.length }));
              zeige("planung", true); } catch (e) { toast(t("fehler", { x: e.message }), true); } } }, t("pm_anhalten")) : null))),
      el("div", { class: "th-knoepfe" }, ...knoepfe), kasten,
      art === "grob" && x.abschluss ? pmAbschluss(x, tun) : null,
      art === "grob" ? el("div", { class: "pm-themen" }, x.themen.length ? x.themen.map(th => el("span", { class: "pm-chip" }, el("b", {}, "TH" + th.id), " " + th.name))
        : el("span", { class: "sehrleise" }, t("pm_keine_themen")))
        : x.pakete.length ? tabelle_() : el("p", { class: "sehrleise" }, t("pm_spaeter_lang"))].filter(Boolean));
  }
  zeichneListe(); zeichneDetail();
  raster.append(links, rechts); m.append(raster);
  return m;
}
async function sichtPlanung() {
  if (!zustand.start) { try { await kopfAktualisieren(); } catch (e) {} }        /* A2089: bogenNr liest die Startdaten */
  let d; try { d = await holen("/api/planung"); } catch (e) { rahmen(t("n_planung")).append(el("div", { class: "leer" }, String(e))); return; }
  const r = zustand.planReiter || (d.planansicht?.hat_themen ? "meilensteine" : "zeitleiste");   /* A1950: mit Themen zuerst die Meilensteine */
  const chip = (name, wert, grund) => el("span", { class: "signal", title: grund || "" }, el("span", { class: "punkt " + ampelKlasse(wert) }),
    `${t("pl_" + name)}: ${wert ? t("ampel_" + wert) : "–"}`);
  const m = rahmen(t("n_planung"), el("span", { style: "display:flex;gap:8px;flex-wrap:wrap" },
    chip("termin", d.status.termin, d.status.begruendung.termin), chip("risiko", d.status.risiko, d.status.begruendung.risiko),
    chip("qualitaet", d.status.qualitaet, d.status.begruendung.qualitaet)),
    el("button", { class: "knopf haupt kopf-aktion", type: "button", onclick: () => bogenDialog(null) }, t("pl_bogen_neu")));   /* Hauptaktion oben, wie überall */
  /* was auf dich wartet, zuerst */
  const w = d.wartet, offen = w.spezifikationen.length + w.plaene.length;
  if (offen) m.append(el("div", { class: "band-warn" }, el("b", {}, t("pl_freigaben", { n: offen }).toUpperCase()),
    ...w.spezifikationen.map(s => el("div", {}, el("a", { class: "verweis", onclick: () => specDialog(d.boegen.find(b => b.id === s.bogen_id), s.teil) },
      t("pl_spec_frei", { b: bogenNr(s.bogen_id), x: s.titel, teil: t("teil_" + s.teil), v: s.version })))),
    ...w.plaene.map(p => el("div", {}, el("a", { class: "verweis", onclick: () => planDialog(p) }, t("pl_plan_frei", { a: p.id, x: p.titel, ag: p.agent || "–" }))))));
  const lu = d.luecken || { thema_ohne_paket: [], paket_ohne_thema: [] }, luT = lu.thema_ohne_paket.length, luP = lu.paket_ohne_thema.length;
  if (luT || luP) m.append(el("details", { class: "pl-luecken", "data-luecken": `${luT}/${luP}` },   /* A1947: Lücken Thema ↔ Paket als Fakt */
    el("summary", {}, el("b", {}, t("pl_luecken") + ": "), [luT ? t(luT === 1 ? "pl_luecken_t1" : "pl_luecken_t", { n: luT }) : null,
      luP ? t(luP === 1 ? "pl_luecken_p1" : "pl_luecken_p", { n: luP }) : null].filter(Boolean).join(" · ")),
    el("div", { class: "sehrleise" }, t("pl_luecken_h")),
    ...lu.thema_ohne_paket.map(x => el("div", { class: "pl-luecke" }, el("span", { class: "ref" }, "TH" + x.id), " ", x.name, " – ", t("pl_luecke_t"))),
    ...lu.paket_ohne_thema.map(x => el("div", { class: "pl-luecke" }, el("span", { class: "ref" }, "A" + x.id), " ", x.titel, " – ", t("pl_luecke_p")))));
  const reiter = [...(d.planansicht?.hat_themen ? ["meilensteine", "pakete"] : []), "zeitleiste", "termine", "leitbild", "risiken", "check", "protokoll"], offeneBefunde = d.pruefung.filter(x => !x.akzeptiert).length;
  m.append(planReiter(reiter.includes(r) ? r : "zeitleiste", { check: offeneBefunde, risiken: d.risiken.filter(x => x.status !== "erledigt").length,
    meilensteine: !!d.planansicht?.hat_themen }));
  if (r === "meilensteine" || r === "pakete") m.append(pmAnsicht(d.planansicht, r === "meilensteine" ? "grob" : "plan"));
  if (r === "zeitleiste") m.append(standJetzt(d), uebersicht(d) || "", rechnerHeute(d) || "", zeitleiste(d));
  if (r === "termine") m.append(termineAnsicht(d.termine || [], d.ki_fenster));
  if (r === "leitbild") m.append(leitbildAnsicht(d.leitbild));
  if (r === "risiken") m.append(risikoAnsicht(d));
  if (r === "check") m.append(checkAnsicht(d));
  if (r === "protokoll") m.append(d.ereignisse.length ? tabelle(["k_zeit", "k_von", "k_art", "k_text"], d.ereignisse.map(x =>
    [zeit(x.zeit_utc), x.von, x.art, (x.bogen_id ? `${bogenRef(x.bogen_id)} · ` : "") + (x.aufgabe_id ? `A${x.aufgabe_id} · ` : "") + (x.text || "")]))
    : el("div", { class: "leer" }, t("leer")));
}
/* Plan-Check: je Befund was los ist, was es bedeutet, was zu tun ist, wer; öffnen, an den Lead geben, bewusst akzeptieren */
function checkText(d, x, i, spr = sprache) {
  const k = d.check_texte[x.code] || {}, s = ((k[spr] || k.de || [])[i]) ?? (i ? "" : x.text);
  return s.replace(/\{(\w+)\}/g, (_, n) => x.werte?.[n] ?? "");
}
function checkAnsicht(d) {
  const offen = d.pruefung.filter(x => !x.akzeptiert), ok = d.pruefung.filter(x => x.akzeptiert);
  const zahl = s => offen.filter(x => x.stufe === s).length;
  const kopf = el("div", { class: "check-kopf" }, el("p", {}, t("ck_erklaerung")),
    el("div", { class: "check-zahlen" }, ["fehler", "warnung", "hinweis"].map(s => el("span", { class: "check-zahl " + (zahl(s) ? s : "") },
      el("b", {}, zahl(s)), " " + t((zahl(s) === 1 ? "ck_1_" : "ck_n_") + s))),
      ok.length ? el("span", { class: "check-zahl" }, el("b", {}, ok.length), " " + t("ck_n_ok")) : null),
    el("div", { class: "check-legende sehrleise" }, t("ck_legende")));
  const aus = el("div", {}, kopf);
  if (!offen.length) aus.append(el("div", { class: "leer" }, d.pruefung.length ? t("ck_alles_ok") : t("pl_check_ok")));
  const reihe = ["projekt", ...d.boegen.map(b => "bogen:" + b.id), "risiken"];
  const stufe = ["fehler", "warnung", "hinweis"];
  for (const g of reihe) {
    const liste = offen.filter(x => x.gruppe === g).sort((a, b) => stufe.indexOf(a.stufe) - stufe.indexOf(b.stufe));
    if (!liste.length) continue;
    const b = g.startsWith("bogen:") ? d.boegen.find(x => "bogen:" + x.id === g) : null;
    aus.append(el("section", { class: "check-gruppe" },
      el("h4", {}, b ? `${bogenRef(b.id)} · ${b.titel}` : t(g === "risiken" ? "ck_risiken" : "ck_projekt"),
        b ? el("a", { class: "verweis", onclick: () => zuSchritt(null, b.id) }, t("ck_zum_bogen")) : null),
      liste.map(x => befundKarte(d, x))));
  }
  if (ok.length) aus.append(el("details", { class: "check-gruppe" }, el("summary", { class: "tl-schritte" }, t("ck_akzeptiert", { n: ok.length })),
    ok.map(x => el("div", { class: "akzeptiert-zeile" },
      el("div", {}, el("span", { class: "etikett" }, t("st_" + x.stufe)), " ", checkText(d, x, 0),
        el("div", { class: "sehrleise" }, `${t("ck_grund")}: ${x.akzeptiert.grund} · ${x.akzeptiert.von} · ${zeit(x.akzeptiert.zeit_utc)}`)),
      el("button", { class: "klein-knopf", type: "button", onclick: async () => {
        try { await schicken("/api/plan/check", { schluessel: x.schluessel, wieder: true }); zeige("planung", true); }
        catch (e) { toast(t("fehler", { x: e.message }), true); } } }, t("ck_wieder"))))));
  return aus;
}
function befundKarte(d, x) {
  const b = d.boegen.find(y => y.id === x.bogen_id), wer = x.wer === "du" ? t("ck_du") : (d.lead || "Lead");
  const knopf = (text, fn) => el("button", { class: "klein-knopf", type: "button", onclick: fn }, text);
  const oeffnen = { leitbild: () => knopf(t("ck_o_leitbild"), () => { zustand.planReiter = "leitbild"; sichtPlanung(); }),
    bogen: () => b && knopf(t("ck_o_bogen"), () => bogenDialog(b)),
    spec_anforderungen: () => b && knopf(t("ck_o_spec"), () => specDialog(b, "anforderungen")),
    risiko: () => { const r = d.risiken.find(y => y.id === x.risiko_id); return r && knopf(t("ck_o_risiko"), () => risikoDialog(r)); },
    schritt: () => x.bogen_id && knopf(t("ck_o_schritt"), () => zuSchritt(x.aufgabe_id, x.bogen_id)),     // ohne Bogen nicht in der Zeitleiste
    zeitleiste: () => knopf(t("pl_bogen_neu"), () => bogenDialog(null)),
    versionen: () => knopf(t("ck_o_versionen"), () => zeige("releases")) }[x.ziel];
  const anLead = x.wer === "lead" && d.lead ? knopf(t("ck_an_lead", { x: d.lead }), async () => {
    try { await schicken("/api/nachricht", { an: d.lead, art: "auftrag", kurz: ("Plan-Check: " + checkText(d, x, 0, "de")).slice(0, 300),
      text: `${checkText(d, x, 1, "de")}\n\nTun: ${checkText(d, x, 2, "de")}\n\nSchlüssel: ${x.schluessel} (amw plan pruefen)` });
      toast(t("ck_gesendet", { x: d.lead })); } catch (e) { toast(t("fehler", { x: e.message }), true); } }) : null;
  return el("div", { class: "befund befund-" + x.stufe },
    el("div", { class: "befund-kopf" }, el("span", { class: "etikett " + (x.stufe === "fehler" ? "rot" : x.stufe === "warnung" ? "bernstein" : "") }, t("st_" + x.stufe)),
      el("b", {}, checkText(d, x, 0))),
    el("div", { class: "befund-zeile" }, el("span", { class: "sehrleise" }, t("ck_bedeutet")), " ", checkText(d, x, 1)),
    el("div", { class: "befund-zeile" }, el("span", { class: "sehrleise" }, `${t("ck_tun")} · ${wer}`), " ", checkText(d, x, 2)),
    el("div", { class: "befund-knoepfe" }, oeffnen ? oeffnen() : null, anLead,
      x.stufe !== "fehler" ? knopf(t("ck_akzeptieren"), () => akzeptierenDialog(d, x)) : null,
      el("span", { class: "befund-schluessel", title: "amw plan akzeptieren <…> --grund …" }, x.schluessel)));
}
function akzeptierenDialog(d, x) {
  const grund = el("textarea", { rows: 3, placeholder: t("ck_grund_ph") });
  const hg = dialog(t("ck_akz_titel"), el("p", { style: "margin-top:0" }, el("b", {}, checkText(d, x, 0))),
    el("p", { class: "leise" }, t("ck_akz_text")), grund,
    el("div", { class: "aktionen" }, el("button", { class: "knopf haupt", type: "button", onclick: async () => {
      if (!grund.value.trim()) { grund.focus(); return; }
      try { await schicken("/api/plan/check", { schluessel: x.schluessel, grund: grund.value.trim() }); hg.remove(); toast(t("ck_akz_fertig")); zeige("planung", true); }
      catch (e) { toast(t("fehler", { x: e.message }), true); } } }, t("ck_akz_ok"))));
  grund.focus();
}
/* zum Bogen (und Schritt) in der Zeitleiste springen und kurz hervorheben */
/* Stand jetzt (A1639): aktiver Meilenstein mit Fortschritt, nächstes Zieldatum, wer gerade an was arbeitet, was ohne Meilenstein ist */
function standJetzt(d) {
  const aktiv = d.boegen.filter(b => b.status === "aktiv"), offen = d.boegen.filter(b => ["aktiv", "geplant"].includes(b.status));
  const ziel = offen.filter(b => b.zieldatum && b.zieldatum >= d.heute).sort((a, b) => a.zieldatum.localeCompare(b.zieldatum))[0];
  const zielZeile = ziel && !(ziel.status === "aktiv" && aktiv.includes(ziel));   /* steht schon in der Zeile darüber: nicht doppelt (TL P167) */
  const fortschritt = b => { const g = b.gesamt - (b.verworfen || 0), f = b.fertig || 0;
    return el("span", {}, el("span", { class: "mb-spur" }, el("i", { style: `width:${g ? Math.round(100 * f / g) : 0}%;background:var(--gruen)` })),
      " " + t("sj_fertig", { f, g })); };
  const laeuft = d.laeuft || [], ohne = d.ohne_bogen || [];
  return el("div", { class: "stand-jetzt", id: "stand-jetzt" }, el("b", {}, t("sj_titel"), " ", hilfeKnopf("planung")),
    ...(aktiv.length ? aktiv.map(b => el("div", { class: "sj-zeile" }, el("a", { class: "verweis", onclick: () => zuSchritt(null, b.id) }, b.titel + ":"),
        fortschritt(b), b.zuwachs?.neu ? el("span", { class: "sehrleise", title: t("zw_satz", zwText(b.zuwachs)) + " – " + t("zw_h") }, "· " + t("zw_kurz", { n: b.zuwachs.neu })) : null,
        b.zieldatum ? el("span", { class: "sehrleise" }, "· " + t("sj_zielkurz", { x: datumKurz(b.zieldatum) })) : null))
      : [el("div", { class: "sj-zeile sehrleise" }, t("sj_kein_aktiv"))]),
    el("div", { class: "sj-zeile sehrleise" }, zielZeile ? t("sj_ziel", { x: datumKurz(ziel.zieldatum), b: ziel.titel }) : ziel ? null : t("sj_kein_ziel"),
      ohne.length ? el("a", { class: "verweis", onclick: () => { const o = document.getElementById("ohne-bogen"); if (o) { o.open = true; o.scrollIntoView({ behavior: "smooth", block: "start" }); } } },
        ohne.length === 1 ? t("sj_ohne1") : t("sj_ohne", { n: ohne.length })) : null),
    el("div", { class: "sj-dran" }, el("span", { class: "sehrleise" }, t("sj_dran") + ":"),
      laeuft.length ? laeuft.map(a => el("a", { class: "verweis", title: `A${a.id}`, onclick: () => aufgabeDialog(a.id) },
        t("sj_an", { a: a.agent === "Entwickler" ? t("pl_du") : (a.agent || "–"), x: a.titel }))) : el("span", { class: "sehrleise" }, t("sj_niemand"))));
}
async function zuSchritt(aid, bid) {
  if (zustand.planReiter !== "zeitleiste") { zustand.planReiter = "zeitleiste"; await sichtPlanung(); }
  const ziel = (aid && document.getElementById("schritt-" + aid)) || (bid && document.getElementById("bogen-" + bid));
  if (!ziel) { toast(t("ck_nicht_gefunden")); return; }
  for (let det = ziel.closest("details"); det; det = det.parentElement?.closest("details")) det.open = true;   /* auch „Fertige Meilensteine“ */
  ziel.scrollIntoView({ behavior: "smooth", block: aid ? "center" : "start" });
  ziel.classList.remove("blink"); void ziel.offsetWidth; ziel.classList.add("blink");
}
/* Wochenlimit des Kontos (alle Projekte dieses PCs): Stand in einem Satz, Rechenweg als Hinweistext, Stück \u29d7 am Datum.
   Die Pause ist ein eigenes Stück – das Prognose-Datum selbst bleibt, wie es ohne Grenze wäre. */
const TKZ = "\u29d7";
const tagZeit = utc => utc ? new Date(utc).toLocaleString(gebiet(), { weekday: "short", day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" }) : "\u2013";
function tokenStand(k) {
  if (!k) return null;
  const teile = [t("tk_wert", { w: Math.round(k.wert) })];
  if (k.tempo) teile.push(k.pause_tage > 0 ? t("tk_leer", { x: tagZeit(k.leer_utc) }) : t("tk_reicht"));
  if (k.reset_utc) teile.push(t("tk_reset", { x: tagZeit(k.reset_utc) }));
  if (k.pause_tage > 0) teile.push(TKZ + " " + t("tk_pause", { n: zahlKurz(k.pause_tage) }));
  if (k.unsicher) teile.push(t("tk_u_" + k.unsicher, { n: k.arbeitstage }));
  return teile.join(" · ");
}
const zahlKurz = x => (Math.round(x * 10) / 10).toLocaleString(gebiet());
function tokenRechenweg(k) {
  if (!k) return "";
  return [t("tk_r_konto", { w: Math.round(k.wert), x: tagZeit(k.gemessen_utc) }),
    k.tempo ? t("tk_r_tempo", { a: zahlKurz(k.tempo), b: zahlKurz(k.tempo_vorsichtig), n: k.arbeitstage }) : t("tk_u_kein_tempo"),
    k.tempo ? t("tk_r_leer", { r: Math.round(100 - k.wert), x: tagZeit(k.leer_utc) }) : null,
    k.reset_utc ? t("tk_r_reset", { x: tagZeit(k.reset_utc) }) + (k.letzter_reset_utc ? " " + t("tk_r_letzter", { x: tagZeit(k.letzter_reset_utc) }) : "") : null,
    k.tempo ? t("tk_r_woche", { a: zahlKurz(k.arbeitstage_je_woche), p: zahlKurz(k.pause_je_woche) }) : null,
    t("tk_r_hinweis")].filter(Boolean).join("\n");
}
/* „\u29d7 +6 T \u2192 \u2248 26.11.“ hinter einem Prognose-Datum; nichts, wenn bis dahin keine Pause anfällt */
const tokenStueck = (p, k = zustand.token) => p?.pause_tage ? el("span", { class: "tk-stueck", title: tokenRechenweg(k) },
  ` ${TKZ} ` + t("tk_plus", { n: p.pause_tage, x: datumKurz(p.p50_mit) })) : null;
/* Übersicht: echte Zeitachse, gepackt. Ein Block je Bogen von Start bis Prognose (Balken fest bis P50, schraffiert bis P85),
   gestrichelt weiter bis zum Zieldatum (◆). Bögen, die sich zeitlich nicht überschneiden, teilen sich eine Spur. ● deine Schritte, heute. */
/* A2096: hinter einem Prüfpunkt ist die Zeit unbekannt – „wartet auf <Name>“ statt eines Datums */
const ppWann = p => p.wartet_auf ? t("pp_wartet_auf", { x: p.wartet_auf }) : `≈ ${datumKurz(p.p50)}`;
function uebersicht(d) {
  const tagNr = x => Math.round(Date.parse(x + "T12:00:00Z") / 864e5), datum = n => new Date(n * 864e5).toISOString().slice(0, 10);
  const alle = d.boegen.filter(b => b.status !== "verworfen").map(b => {
    const p = b.prognose, fertig = b.status === "fertig" ? (b.fertig_utc || "").slice(0, 10) || null : null;
    const e50 = fertig || p?.p50 || null, e85 = fertig || p?.p85 || null;
    let start = b.beginn_ist || p?.start || fertig;
    if (start && e50 && start > e50) start = e50;
    const du = b.schritte.filter(s => s.agent === "Entwickler" && !["fertig", "verworfen"].includes(s.status) && s.prognose)
      .map(s => ({ id: s.id, titel: s.titel, tag: s.prognose.p50 }));
    return { b, start, e50, e85, ziel: b.zieldatum, du, pause: fertig ? 0 : p?.pause_tage || 0 };
  });
  const mitDaten = alle.filter(z => z.start && z.e50), ohne = alle.filter(z => !(z.start && z.e50));
  const nFertig = mitDaten.filter(z => z.b.status === "fertig").length, alleFertig = nFertig === mitDaten.length;
  const zeigFertige = !!zustand.uebFertige || alleFertig;        /* Wo stehen wir: Fertiges erst auf Wunsch (A1639) */
  const zeilen = mitDaten.filter(z => zeigFertige || z.b.status !== "fertig");
  if (!zeilen.length) return null;
  const rang = z => z.b.status === "aktiv" ? 0 : z.b.status === "fertig" ? 2 : 1;
  /* Zeitraum: bis zum Ende der Prognose – oder auf Wunsch bis zum letzten Zieldatum */
  const weit = !!zustand.uebWeit, zielWeiter = zeilen.some(z => z.ziel && z.ziel > z.e85);
  const daten = zeilen.flatMap(z => [z.start, z.e85, ...z.du.map(x => x.tag), weit ? z.ziel : null]).filter(Boolean).concat(d.heute);
  const mitPause = Math.max(...zeilen.map(z => tagNr(z.e85) + z.pause));          /* das Stück Token-Pause hängt hinten am Balken */
  const von = Math.min(...daten.map(tagNr)) - 2, bis = Math.max(...daten.map(tagNr), mitPause) + 3, spanne = bis - von;
  const pxTag = Math.max(240, ($("#inhalt")?.clientWidth || innerWidth) - 100) / spanne, H = 26;
  const pos = n => `${(100 * (n - von) / spanne).toFixed(3)}%`, breite = (a, b) => `${(100 * Math.max(0, b - a) / spanne).toFixed(3)}%`;
  /* packen: jeder Block kommt in die erste Spur, in der der vorige Block (samt Name und Linie zum Zieldatum) schon vorbei ist.
     Passt der Name nicht in den Balken, steht er rechts daneben (bis 250 px) – auch dafür hält die Spur Platz frei. */
  const spuren = [], mass = (() => { const c = document.createElement("canvas").getContext("2d");
    c.font = `12px ${getComputedStyle(document.body).fontFamily}`; return x => c.measureText(x).width; })();
  for (const z of zeilen.slice().sort((a, b) => rang(a) - rang(b) || a.start.localeCompare(b.start) || a.e85.localeCompare(b.e85))) {
    z.a = tagNr(z.start); z.m = tagNr(z.e50); z.e = Math.max(tagNr(z.e85), z.m); z.zn = z.ziel ? tagNr(z.ziel) : null; z.t = z.e + z.pause;
    const name = Math.min(mass(`${bogenRef(z.b.id)}  ${z.b.titel}`) + 14, 254);
    z.aussen = (z.e - z.a) * pxTag < name;
    const links = Math.min(z.a, z.zn ?? z.a), rechts = Math.max(z.t, z.zn === null ? 0 : Math.min(z.zn, bis), z.a + 36 / pxTag,
      z.aussen ? z.t + (name + 6) / pxTag : 0);
    let s = spuren.findIndex(ende => ende + 6 / pxTag < links);
    if (s < 0) { s = spuren.length; spuren.push(0); }
    spuren[s] = rechts; z.spur = s;
  }
  /* Achse: Wochen bei kurzen Plänen, sonst Monate (bei wenig Platz jeder zweite oder jedes Quartal); Jahr am Anfang und im Januar */
  const woche = spanne <= 75, alle_n = 30 * pxTag >= 44 ? 1 : 30 * pxTag >= 22 ? 2 : 3, ticks = [];
  for (let n = von + 1; n < bis; n++) {
    const dt = new Date(n * 864e5), mo = dt.getUTCMonth();
    if (woche ? dt.getUTCDay() === 1 : dt.getUTCDate() === 1 && mo % alle_n === 0)
      ticks.push({ n, text: woche ? datumKurz(datum(n)) : dt.toLocaleDateString(gebiet(), { month: "short", timeZone: "UTC" }),
        jahr: !woche && (!ticks.length || mo === 0) ? dt.getUTCFullYear() : null });
  }
  const offen = zeilen.filter(z => z.b.status !== "fertig");
  const start = zeilen.map(z => z.start).sort()[0];
  const ende50 = offen.map(z => z.e50).sort().pop(), ende85 = offen.map(z => z.e85).sort().pop();
  const uhrJetzt = new Date().toLocaleTimeString(gebiet(), { hour: "2-digit", minute: "2-digit" });
  /* Läuft die Jetzt-Linie durch den Namen im Balken? Dann beginnt der Name rechts von der Linie */
  const jetztDurch = z => { const off = (tagNr(d.heute) - z.a) * pxTag; return off > -4 && off < Math.min(mass(`${bogenRef(z.b.id)}  ${z.b.titel}`) + 8, (z.e - z.a) * pxTag); };
  const jetztTip = [t("ue_jetzt_tip", { x: `${datumKurz(d.heute)} ${uhrJetzt}` }),
    ...(d.laeuft || []).map(a => `${a.agent || "–"} → A${a.id} ${a.titel}`)].join("\n");
  /* Rechner: je Tag ein Stück auf derselben Achse – so hoch, wie viele Stunden er mit Läufen belegt war (8 Stunden = voll) */
  const rechnerTage = (d.rechner_heute?.tage || []).filter(x => x.stunden > 0 && tagNr(x.tag) > von && tagNr(x.tag) < bis);
  const flaeche = el("div", { class: "ueb-flaeche", style: `height:${spuren.length * H}px` },
    ticks.map(k => el("i", { class: "ueb-tick", style: `left:${pos(k.n)}` })),
    el("i", { class: "ueb-heute", style: `left:${pos(tagNr(d.heute))}` }),
    el("span", { class: "ueb-jetzt", style: `left:${pos(tagNr(d.heute))}`, title: jetztTip }),
    zeilen.flatMap(z => {
      const b = z.b, oben = z.spur * H, art = b.status === "fertig" ? "fertig" : b.prognose?.ampel === "rot" ? "rot" : b.prognose?.ampel === "gelb" ? "knapp" : b.status === "aktiv" ? "aktiv" : "";   /* A1777: knapp = wahrscheinlich vor dem Ziel, vorsichtig gerechnet danach */
      const lang = Math.max(z.e - z.a, 0), spaet = z.zn !== null && z.zn < z.m && b.status !== "fertig";
      const tip = [`${bogenRef(b.id)} · ${b.titel}`, `${t("bs_" + b.status)} · ${t("pl_fortschritt", { f: b.fertig || 0, g: b.gesamt - (b.verworfen || 0) })}`,
        `${t("ue_start")} ${datumKurz(z.start)}`, b.zuwachs ? t("zw_satz", zwText(b.zuwachs)) : null,
        b.status === "fertig" ? `${t("bs_fertig")} ${datumKurz(z.e50)}` : `${t("pl_prognose")} ${datumKurz(z.e50)} – ${datumKurz(z.e85)}`,
        z.pause ? `${TKZ} ${t("tk_plus", { n: z.pause, x: datumKurz(b.prognose.p50_mit) })}` : null,
        z.ziel ? `${t("pl_zieldatum")} ${datumKurz(z.ziel)}` : null].filter(Boolean).join(" · ");
      /* A1760 (Marcel, Mockup freigegeben): wer gerade an einer Aufgabe dieses Meilensteins arbeitet – pulsierender Rahmen + Kürzel */
      const wer = [...new Set((b.schritte || []).filter(s => s.status === "laeuft" && s.agent).map(s => s.agent))];
      const pillen = () => wer.map(a => el("span", { class: "ueb-wer", title: t("ue_wer_h", { a }) }, "▶ " + a));
      const teile = [el("button", { class: "ueb-block " + art + (wer.length ? " arbeitet" : ""), type: "button", title: tip, onclick: () => zuSchritt(null, b.id),
          style: `left:${pos(z.a)};top:${oben}px;width:${breite(z.a, z.e)}` },
        el("i", { class: "ueb-b50", style: `width:${lang ? (100 * (z.m - z.a) / lang).toFixed(1) : 100}%` }),
        z.e > z.m ? el("i", { class: "ueb-b85", style: `left:${(100 * (z.m - z.a) / lang).toFixed(1)}%` }) : null,
        z.aussen ? null : el("span", { class: "ueb-label", style: jetztDurch(z) ? `left:${Math.round((tagNr(d.heute) - z.a) * pxTag + 7)}px` : null },   /* nie durch den Text (TL #24368) */
          el("b", {}, (b.status === "fertig" ? "✓ " : "") + bogenRef(b.id)), b.titel, ...pillen()))];
      if (z.pause) teile.push(el("i", { class: "ueb-token", "data-b": b.id, style: `left:${pos(z.e)};top:${oben}px;width:${breite(z.e, z.t)}`,
        title: `${bogenRef(b.id)} · ${TKZ} ${t("tk_plus", { n: z.pause, x: datumKurz(b.prognose.p50_mit) })}\n${tokenRechenweg(d.token)}` }, el("b", {}, TKZ)));
      if (z.aussen) teile.push(el("span", { class: "ueb-name " + art, title: tip, onclick: () => zuSchritt(null, b.id),
        style: `left:calc(${pos(z.t)} + 5px);top:${oben + 2}px;max-width:min(250px, calc(100% - ${pos(z.t)} - 8px))` },
        el("b", {}, (b.status === "fertig" ? "✓ " : "") + bogenRef(b.id)), b.titel, ...pillen()));
      if (z.zn !== null) {
        const bisZiel = Math.min(z.zn, bis);
        if (bisZiel > z.e) teile.push(el("i", { class: "ueb-puffer", style: `left:${pos(z.e)};width:${breite(z.e, bisZiel)};top:${oben + 19}px` }));
        teile.push(z.zn > bis
          ? el("span", { class: "ueb-weiter", style: `top:${oben + 12}px`, title: `${t("pl_zieldatum")} ${datumKurz(z.ziel)}` }, `◆ ${datumKurz(z.ziel)} ›`)
          : el("i", { class: "ueb-ziel" + (spaet ? " rot" : ""), style: `left:${pos(z.zn)};top:${oben + 13}px`,
              title: `${bogenRef(b.id)} ${b.titel} · ${t("pl_zieldatum")} ${datumKurz(z.ziel)} · ${t("bs_" + b.status)}`
                + (b.status !== "fertig" && b.prognose ? ` · ${t("pl_prognose")} ${datumKurz(z.e50)} – ${datumKurz(z.e85)}` : "") + (spaet ? ` · ${t("ue_l_rot")}` : "") }));
      }
      return teile.concat(z.du.map(x => el("i", { class: "ueb-du", style: `left:${pos(tagNr(x.tag))};top:${oben + 16}px`,
        title: `A${x.id} ${x.titel} – ${t("ck_du")} ≈ ${datumKurz(x.tag)}` })));
    }));
  return el("div", { class: "ueb" },
    d.token ? el("div", { class: "tk-woche", id: "token-woche", title: tokenRechenweg(d.token) }, el("b", {}, TKZ + " " + t("tk_woche")), el("span", {}, tokenStand(d.token)),
      el("span", { class: "sehrleise" }, t("tk_konto"))) : null,
    el("div", { class: "ueb-kopf" }, el("b", {}, t("ue_titel")),
      el("span", {}, ende50 ? t("ue_summe", { a: datumKurz(start), b: datumKurz(ende50), c: datumKurz(ende85),
        n: Math.max(1, Math.round((tagNr(ende85) - tagNr(start < d.heute ? start : d.heute)) / 7)) }) : t("ue_teilweise")),
      el("span", { class: "sehrleise" }, t("ue_spuren", { n: zeilen.length, s: spuren.length })),
      zielWeiter || weit ? el("button", { class: "klein-knopf", type: "button", onclick: () => { zustand.uebWeit = !weit; sichtPlanung(); } },
        t(weit ? "ue_eng" : "ue_weit")) : null,
      nFertig && !alleFertig ? el("button", { class: "klein-knopf", type: "button", onclick: () => { zustand.uebFertige = !zustand.uebFertige; sichtPlanung(); } },
        zustand.uebFertige ? t("ue_fertige_aus") : t("ue_fertige_zeigen", { n: nFertig })) : null),
    el("p", { class: "sehrleise ueb-erkl", style: "margin:2px 0 6px;font-size:12px" }, t("ue_erkl")),
    el("div", { class: "ueb-achse" }, ticks.filter(k => Math.abs(k.n - tagNr(d.heute)) * pxTag > 52)        /* kein Datum direkt neben „Jetzt“ – sonst liest es sich wie „Jetzt 16.11.“ */
      .map(k => el("span", { style: `left:${pos(k.n)}` }, k.text, k.jahr ? el("small", {}, k.jahr) : null)),
      el("span", { class: "jetzt", style: `left:${pos(tagNr(d.heute))}`, title: jetztTip }, t("ue_jetzt"))),
    flaeche,
    rechnerTage.length ? el("div", { class: "ueb-rechner", id: "ueb-rechner" }, el("small", {}, t("rh_spur")),
      el("i", { class: "ueb-heute", style: `left:${pos(tagNr(d.heute))}` }),
      rechnerTage.map(x => el("i", { class: "tag", title: t(x.laeufe === 1 ? "rh_tag1" : "rh_tag", { x: datumKurz(x.tag), n: x.laeufe, h: zahlKurz(x.stunden) }),
        style: `left:${pos(tagNr(x.tag) - .5)};width:${breite(0, 1)};height:${Math.round(100 * Math.min(1, Math.max(.2, x.stunden / 8)))}%` }))) : null,
    ohne.length ? el("div", { class: "ueb-ohne-liste" }, el("span", { class: "sehrleise" }, t("ue_ohne_prognose")),
      ohne.map(z => el("button", { type: "button", title: z.ziel ? `${t("pl_zieldatum")} ${datumKurz(z.ziel)}` : "", onclick: () => zuSchritt(null, z.b.id) },
        el("span", { class: "ref" }, bogenRef(z.b.id)), " " + z.b.titel))) : null,
    el("div", { class: "ueb-legende" },
      el("span", {}, el("i", { class: "ueb-muster geplant" }), t("lg_geplant")), el("span", {}, el("i", { class: "ueb-muster aktiv" }), t("lg_arbeit")),
      zeilen.some(z => z.b.status !== "fertig" && z.b.prognose?.ampel === "gelb") ? el("span", {}, el("i", { class: "ueb-muster knapp" }), t("lg_knapp")) : null,
      el("span", {}, el("i", { class: "ueb-muster arbeitet" }), t("lg_puls")),
      el("span", {}, el("i", { class: "ueb-muster rot" }), t("lg_spaet")), el("span", {}, el("i", { class: "ueb-muster fertig" }), t("lg_erledigt")),
      el("span", {}, el("i", { class: "ueb-muster schraffur" }), t("lg_rahmen")), el("span", {}, el("i", { class: "ueb-puffer" }), t("lg_puffer")),
      el("span", {}, el("i", { class: "ueb-ziel" }), t("lg_ziel")),
      d.token ? el("span", { title: tokenRechenweg(d.token) }, el("i", { class: "ueb-muster token" }), TKZ + " " + t("tk_legende")) : null,
      zeilen.some(z => z.du.length) ? el("span", {}, el("i", { class: "ueb-du" }), t("ue_l_du")) : null,
      rechnerTage.length ? el("span", {}, el("i", { class: "ueb-muster rechner" }), t("rh_l_tage")) : null));
}
/* Rechner – heute: der Tagesablauf des Rechners als eigener Zeitstrahl unter der Übersicht. Ein Balken je Lauf (eigene
   mit Nummer und Agent, fremde nur „anderes Projekt“), Füllung = Arbeitsspeicher; was außerhalb der Warteschlange dauerhaft
   Speicher belegt, läuft als durchgehender Balken; Wartende hängen gestrichelt hinter „jetzt“. Einklappbar. */
function rechnerHeute(d) {
  const r = d.rechner_heute;
  if (!r) return null;
  const ms = x => Date.parse(x), STD = 36e5, H = 26, tagVon = ms(r.von_utc), tagBis = ms(r.bis_utc);
  const jetzt = Math.min(tagBis, Math.max(tagVon, ms(r.jetzt_utc), Date.now()));           /* die Uhr des Geräts: online liegt der Stand des letzten Abgleichs */
  const uhr = m => new Date(m).toLocaleTimeString(gebiet(), { hour: "2-digit", minute: "2-digit" });
  const gb = x => x ? ` · ${zahlKurz(x)} GB` : "";
  const lief = r.laeufe.filter(l => l.start_utc).map(l => ({ l, art: l.status, a: Math.max(ms(l.start_utc), tagVon),
    e: l.ende_utc ? ms(l.ende_utc) : Math.max(jetzt, ms(l.start_utc) + (l.erwartet_min || 0) * 6e4) }));
  let frei = Math.max(jetzt, ...lief.filter(x => x.art === "laeuft").map(x => x.e));        /* Wartende: nacheinander hinter dem, was läuft */
  const wartet = r.laeufe.filter(l => l.status === "wartet").map(l => { const a = frei; frei = a + (l.erwartet_min || 10) * 6e4; return { l, art: "wartet", a, e: frei }; });
  const von = Math.max(tagVon, Math.floor(Math.min(jetzt - 2 * STD, ...lief.map(x => x.a)) / STD) * STD);
  const bis = Math.max(von + 4 * STD, Math.ceil(Math.max(jetzt + STD, ...lief.map(x => x.e), ...wartet.map(x => x.e)) / STD) * STD), spanne = bis - von;
  const dauer = (r.dauer || []).map(x => ({ x, art: "dauer", a: Math.max(ms(x.seit_utc), von), e: bis }));
  const pos = m => `${(100 * (Math.min(Math.max(m, von), bis) - von) / spanne).toFixed(3)}%`;
  const breite = (a, e) => `${(100 * Math.max(0, Math.min(e, bis) - Math.max(a, von)) / spanne).toFixed(3)}%`;
  const spuren = [];
  for (const z of [...dauer, ...lief.sort((p, q) => p.a - q.a), ...wartet]) {
    let i = spuren.findIndex(ende => ende <= z.a);
    if (i < 0) { i = spuren.length; spuren.push(0); }
    spuren[i] = z.e + spanne / 400; z.spur = i;
  }
  const schritt = spanne / STD <= 8 ? 1 : spanne / STD <= 16 ? 2 : 3, ticks = [];
  for (let m = von; m < bis; m += schritt * STD) ticks.push(m);
  const flaecheBreit = Math.max(240, ($("#inhalt")?.clientWidth || innerWidth) - 60);
  const balken = z => {
    const l = z.l, fuell = z.art === "dauer" ? z.x.gb : l.gb;
    const vr = z.art !== "dauer" && l.vorrang === "hoch" ? "\u25b2 " : "";
    const name = z.art === "dauer" ? `${z.x.name}${gb(z.x.gb)}` : vr + (l.eigen ? `L${l.id} ${l.wer}${gb(l.gb)}` : `${t("rh_fremd")}${gb(l.gb)}`);
    const tip = z.art === "dauer" ? `${z.x.name}${gb(z.x.gb)} · ${t("rh_dauer")} · ${t("rh_seit", { x: zeit(z.x.seit_utc) })}`
      : [l.eigen ? `L${l.id} ${l.wer}` : t("rh_fremd"), l.eigen ? l.text : null, z.art === "wartet" ? t("rh_wartet") : `${uhr(z.a)}–${l.ende_utc ? uhr(z.e) : t("rh_laeuft")}`,
         z.art === "abgebrochen" ? t("rh_abgebrochen") : null, l.gb ? `${zahlKurz(l.gb)} GB` : null,
         l.vorrang ? `${t("rh_vorrang")}: ${t("vr_" + l.vorrang)}` : null].filter(Boolean).join(" · ");
    const eng = (Math.min(z.e, bis) - Math.max(z.a, von)) / spanne * flaecheBreit < name.length * 6.5 + 10;   /* Name nur, wo er hinpasst – sonst beim Drüberfahren */
    const ansehen = z.art !== "dauer" && !API && l.eigen && l.ausgabe;      /* A2044: Ausgabe des Laufs ansehen (nur am PC) */
    return el("div", { class: `rh-lauf ${z.art}${z.l?.eigen ? " eigen" : ""}${z.l?.vorrang === "hoch" ? " vorrang" : ""}${eng ? " eng" : ""}${ansehen ? " klickbar" : ""}`,
      title: tip + (ansehen ? " · " + t("la_klick") : ""), style: `left:${pos(z.a)};width:${breite(z.a, z.e)};top:${z.spur * H + 2}px`,
      onclick: ansehen ? () => laufAusgabeDialog(l.id) : null },
      z.art === "wartet" ? null : el("i", { style: `height:${Math.round(100 * Math.min(1, Math.max(.15, (fuell || 0) / (r.gesamt_gb || 32))))}%` }), el("span", {}, name));
  };
  const heute = r.tage.find(x => ms(x.tag + "T12:00:00") >= tagVon && ms(x.tag + "T12:00:00") < tagBis), n = lief.length;
  const leer = !n && !wartet.length && !dauer.length;
  return el("details", { class: "rh", id: "rechner-heute", open: zustand.rhAuf ? "" : null, ontoggle: e => { zustand.rhAuf = e.target.open; } },   /* eingeklappt, bis du es öffnest (A1639) */
    el("summary", {}, el("b", {}, t("rh_titel")), el("span", {}, r.rechner || ""),
      el("span", {}, leer ? t("rh_leer") : [n ? t(n === 1 ? "rh_summe1" : "rh_summe", { n, h: zahlKurz(heute?.stunden || 0) }) : null,
        wartet.length ? t(wartet.length === 1 ? "rh_warten1" : "rh_warten", { n: wartet.length }) : null].filter(Boolean).join(" · "))),
    leer ? null : el("div", { class: "rh-achse" }, ticks.map(m => el("span", { style: `left:${pos(m)}` }, uhr(m)))),
    leer ? null : el("div", { class: "rh-flaeche", style: `height:${spuren.length * H + 2}px` },
      ticks.map(m => el("i", { class: "ueb-tick", style: `left:${pos(m)}` })), el("i", { class: "ueb-heute", style: `left:${pos(jetzt)}` }),
      [...dauer, ...lief, ...wartet].map(balken)),
    leer ? null : el("div", { class: "ueb-legende" },
      el("span", {}, el("i", { class: "ueb-muster rh-eigen" }), t("rh_l_eigen")), el("span", {}, el("i", { class: "ueb-muster" }), t("rh_l_fremd")),
      el("span", {}, el("i", { class: "ueb-muster aktiv" }), t("rh_laeuft")), el("span", {}, el("i", { class: "ueb-muster rh-wartet" }), t("rh_l_wartet")),
      dauer.length ? el("span", {}, el("i", { class: "ueb-muster rh-dauer" }), t("rh_l_dauer")) : null,
      r.laeufe.some(l => l.vorrang === "hoch") ? el("span", {}, "\u25b2 ", t("rh_l_vorrang")) : null,
      el("span", {}, el("i", { class: "ueb-heute" }), t("rh_jetzt")), el("span", { class: "sehrleise" }, t("rh_l_fuellung"))));
}
/* Senkrechte Zeitleiste: ein Bogen je Station, Heute-Linie, Zieldatum/Baseline/Prognose, Spezifikation, Schritte in Wellen */
function zeitleiste(d) {
  zustand.token = d.token || null;                  /* für die Karten der Bögen: Stück Token-Pause am Datum */
  zustand.planBoegen = d.boegen; zustand.planLead = d.lead;   /* A1777: „Vorziehen“ (ein offener davor?) und „Lead anschreiben“ */
  if (!d.boegen.length) return el("div", { class: "leer" }, t("pl_keine_boegen"));
  const liste = el("div", { class: "zeitleiste" });
  let heuteGesetzt = false;
  const fertige = d.boegen.filter(b => ["fertig", "verworfen"].includes(b.status));
  if (fertige.length && fertige.length < d.boegen.length)
    liste.append(el("details", { class: "tl-fertige", open: zustand.tlFertige ? "" : null, ontoggle: e => { zustand.tlFertige = e.target.open; } },
      el("summary", { class: "tl-schritte" }, t("tl_fertige", { n: fertige.length })), fertige.map(bogenKarte)));
  for (const b of d.boegen) {
    if (fertige.length < d.boegen.length && fertige.includes(b)) continue;
    const bezug = b.status === "fertig" ? (b.fertig_utc || "").slice(0, 10) : (b.prognose?.p50 || b.zieldatum);
    if (!heuteGesetzt && b.status !== "fertig" && b.status !== "verworfen" && (!bezug || bezug >= d.heute)) {
      liste.append(el("div", { class: "tl-heute" }, el("span", {}, t("pl_heute", { x: datumKurz(d.heute) }))));
      heuteGesetzt = true;
    }
    liste.append(bogenKarte(b));
  }
  if (!heuteGesetzt) liste.append(el("div", { class: "tl-heute" }, el("span", {}, t("pl_heute", { x: datumKurz(d.heute) }))));
  const imEingang = d.neue_aufgaben === "eingang" ? (d.ohne_bogen || []).filter(a => a.einstufung === "pool") : [];   /* A1740 */
  const ohne = (d.ohne_bogen || []).filter(a => !imEingang.includes(a));
  if (imEingang.length) liste.append(el("details", { class: "tl-bogen karte ohne-bogen", id: "eingang", open: zustand.eingangAuf ? "" : null,
      ontoggle: e => { zustand.eingangAuf = e.target.open; } },
    el("summary", { class: "tl-kopf" }, el("b", { class: "tl-titel" }, t("eg_titel", { n: imEingang.length }))),
    el("div", { class: "sehrleise", style: "margin:4px 0 6px" }, t("eg_h")),
    imEingang.map(a => el("div", { class: `schritt status-${a.status}`, id: "schritt-" + a.id, onclick: () => aufgabeDialog(a.id) },
      el("span", { class: "ref" }, `A${a.id}`), el("span", { class: "schritt-titel" }, a.titel), a.agent ? el("span", { class: "sehrleise" }, a.agent) : null))));
  if (ohne.length) liste.append(el("details", { class: "tl-bogen karte ohne-bogen", id: "ohne-bogen", open: zustand.ohneAuf ? "" : null,
      ontoggle: e => { zustand.ohneAuf = e.target.open; } },
    el("summary", { class: "tl-kopf" }, el("b", { class: "tl-titel" }, t("ob_titel", { n: ohne.length }))),
    el("div", { class: "sehrleise", style: "margin:4px 0 6px" }, t("ob_h")),
    ohne.map(a => el("div", { class: `schritt status-${a.status}`, id: "schritt-" + a.id, onclick: () => aufgabeDialog(a.id) },
      el("span", { class: "ref" }, `A${a.id}`), el("span", { class: "schritt-titel" }, a.titel),
      el("span", { class: "etikett" + (a.status === "laeuft" ? " gruen" : "") }, t("sp_" + a.status) || a.status),
      el("span", { class: "schritt-meta sehrleise" }, a.agent === "Entwickler" ? t("pl_du") : (a.agent || t("pl_frei")))))));
  return liste;
}
const zwText = z => ({ x: datumKurz(z.seit.slice(0, 10)), n: z.neu, m: z.erledigt, k: z.offen });
/* A1777 (Marcel 15.11., B2816, Kleinprobe D1171 freigegeben F5342): die Meilenstein-Karte für den Menschen – Fakten zum
   Eingreifen statt Lead-Werkzeuge. Kopf (Verantwortlich, Ziel, „Vorziehen“; Aktivieren/Abschließen/Rückblick/Bearbeiten unter
   „Mehr … · Für den Lead“), Fortschritt als Satz, Zeitschiene, „was läuft, was hängt“ nach Ursache gebündelt mit dem Weg
   zum Eingreifen, dann die Aufgaben selbst (offen zuerst, mit Mini-Zeitlinie, „verschoben aus …“), Details unten in Worten. */
const mkMs = x => x ? Date.parse(x.length === 10 ? x + "T12:00:00" : x) : null;
const mkKurz = (x, n = 90) => !x ? "" : x.length > n ? x.slice(0, n - 1) + "…" : x;
/* Worauf eine offene Aufgabe hängt – eine Ursache je Aufgabe, in der Reihenfolge, in der der Mensch sie lösen kann */
function mkUrsache(s) {
  const g = s.gruende || [];
  if (s.status === "laeuft") return { art: "laeuft", key: "laeuft" };
  const dich = g.find(x => x.an_dich);
  if (dich || s.agent === "Entwickler") return { art: "dich", key: "dich", g: dich };
  const lauf = g.find(x => x.art === "lauf");
  if (lauf) return { art: "lauf", key: "lauf:" + lauf.bezug, g: lauf };
  if (s.pruefung) return { art: "pruefung", key: "pruefung" };
  const aufg = g.find(x => x.art === "aufgabe");
  if (aufg) return { art: "aufgabe", key: "aufgabe:" + aufg.bezug, g: aufg };
  if ((s.blockiert_durch || []).length) { const a = "A" + s.blockiert_durch[0]; return { art: "aufgabe", key: "aufgabe:" + a, g: { art: "aufgabe", bezug: a } }; }
  const ag = g.find(x => x.art === "agent");
  if (ag) return { art: "agent", key: "agent:" + ag.bezug, g: ag };
  if (g.length) return { art: "sonst", key: "sonst:" + g[0].bezug, g: g[0] };
  if (s.status === "blockiert") return { art: "sonst", key: "sonst:", g: null };   /* „wartet“ ohne Grund = noch nicht dran (Grundzustand einer neuen Aufgabe) */
  return { art: "offen", key: "offen" };
}
const mkSeit = s => s.status === "laeuft" ? s.begonnen_utc : (s.gruende || []).map(g => g.seit).filter(Boolean).sort()[0] || s.begonnen_utc || s.angelegt_utc;
function mkStatus(s, u) {
  if (s.status === "fertig") return t("mk_st_fertig", { x: s.fertig_utc ? datumKurz(s.fertig_utc.slice(0, 10)) : "" });
  if (s.status === "verworfen") return t("mk_st_verworfen");
  return { laeuft: () => t("mk_st_laeuft"), dich: () => u.g?.art === "frage" ? t("mk_st_dich_f", { f: u.g.bezug }) : t("mk_st_dich"),
    lauf: () => t("mk_st_lauf", { l: u.g.bezug }), pruefung: () => t("mk_st_pruefung", { p: "P" + s.pruefung.id }),
    aufgabe: () => t("mk_st_auf", { x: u.g.bezug }), agent: () => t("mk_st_auf", { x: u.g.bezug }),
    sonst: () => u.g ? t("mk_st_auf", { x: u.g.bezug }) : t("sp_" + s.status), offen: () => t(s.begonnen_utc ? "mk_st_pause" : "mk_st_offen") }[u.art]();
}
const mkZeichen = (s, u) => el("i", { class: "mk-z " + (s.status === "fertig" ? "fertig" : s.status === "verworfen" ? "offen" : u.art === "laeuft" ? "laeuft"
  : u.art === "offen" ? "offen" : "wartet") });
function bogenKarte(b) {
  const p = b.prognose, aktiv = b.status === "aktiv", offenB = ["aktiv", "geplant"].includes(b.status);
  /* A1742: alle Aufgaben fertig (oder verworfen) – Abschließen bleibt Sache des Leads (bzw. der Automatik), steht unter „Mehr …“ */
  const alleFertig = offenB && b.gesamt > 0 && (b.fertig || 0) + (b.verworfen || 0) === b.gesamt;
  const zahl = b.gesamt - (b.verworfen || 0);
  const statusSetzen = async (status, frage) => { if (frage && !confirm(frage)) return;
    try { await schicken("/api/plan/bogen", { aktion: "status", bogen: b.id, status }); zeige("planung", true); } catch (e) { toast(t("fehler", { x: e.message }), true); } };
  const boegen = zustand.planBoegen || [], lead = zustand.planLead;
  const davor = boegen.slice(0, boegen.findIndex(x => x.id === b.id)).some(x => ["aktiv", "geplant"].includes(x.status));
  const vorziehen = offenB && davor ? el("button", { class: "knopf haupt mk-vorziehen", type: "button", title: t("mk_vorziehen_h"), onclick: async () => {
      if (!confirm(t("mk_vorziehen_frage", { b: bogenNr(b.id), x: b.titel }))) return;
      try { await schicken("/api/plan/bogen", { aktion: "vorziehen", bogen: b.id }); toast(t("mk_vorgezogen")); zeige("planung", true); }
      catch (e) { toast(t("fehler", { x: e.message }), true); } } }, t("mk_vorziehen")) : null;
  const menue = el("div", { class: "mk-menue", hidden: "" }, el("span", {}, t("mk_fuer_lead")),
    b.status === "geplant" ? el("button", { class: "klein-knopf", type: "button", onclick: () => statusSetzen("aktiv", t("pl_aktivieren_frage")) }, t("pl_aktivieren")) : null,
    aktiv || alleFertig ? el("button", { class: "klein-knopf", type: "button", onclick: () => statusSetzen("fertig", t("pl_abschliessen_frage", { x: b.abnahme || "–" })) }, t("pl_abschliessen")) : null,
    el("button", { class: "klein-knopf", type: "button", onclick: () => rueckblickDialog(b) }, t("rb_knopf", { n: (b.rueckblick || []).length })),
    el("button", { class: "klein-knopf", type: "button", onclick: () => bogenDialog(b) }, t("bearbeiten")));
  const mehr = el("span", { class: "mk-mehr" }, el("button", { class: "klein-knopf", type: "button", "aria-haspopup": "true",
    onclick: e => { menue.hidden = !menue.hidden; e.stopPropagation(); } }, t("mk_mehr")), menue);
  const wer = b.federfuehrend || (lead ? t("mk_lead", { x: lead }) : null);

  /* Aufgaben mit ihrer Ursache; „was läuft, was hängt“ = Gruppen je Ursache */
  const offen = b.schritte.filter(s => !["fertig", "verworfen"].includes(s.status)).map(s => ({ s, u: mkUrsache(s) }));
  const gruppen = new Map();
  for (const x of offen) if (x.u.art !== "offen") { if (!gruppen.has(x.u.key)) gruppen.set(x.u.key, { u: x.u, a: [] }); gruppen.get(x.u.key).a.push(x.s); }
  const n = art => offen.filter(x => art.includes(x.u.art)).length;
  const satz = [t("mk_satz_fertig", { f: b.fertig || 0, g: zahl }),
    n(["laeuft"]) ? t(n(["laeuft"]) === 1 ? "mk_satz_laeuft1" : "mk_satz_laeuft", { n: n(["laeuft"]) }) : null, n(["dich"]) ? t(n(["dich"]) === 1 ? "mk_satz_dich1" : "mk_satz_dich", { n: n(["dich"]) }) : null,
    n(["lauf", "aufgabe", "agent", "sonst"]) ? t("mk_satz_blockiert", { n: n(["lauf", "aufgabe", "agent", "sonst"]) }) : null,
    n(["pruefung"]) ? t("mk_satz_pruefung", { n: n(["pruefung"]) }) : null, n(["offen"]) ? t("mk_satz_offen", { n: n(["offen"]) }) : null].filter(Boolean);
  const aufLink = (id, text) => el("a", { onclick: () => aufgabeDialog(id) }, text || "A" + id);
  const zeileA = s => [aufLink(s.id), " " + mkKurz(s.titel, 80)];
  const leadKnopf = (bezug, text) => lead ? el("button", { class: "klein-knopf", type: "button", onclick: () => nachrichtDialog(lead, { bezug, bezugText: text }) }, t("mk_k_lead")) : null;
  const lageZeile = (gr) => {
    const { u, a } = gr, eins = a.length === 1, s = a[0];
    const kopf = { laeuft: () => t(eins ? "mk_l_laeuft1" : "mk_l_laeuft", { n: a.length }), dich: () => t(eins ? "mk_l_dich1" : "mk_l_dich", { n: a.length }),
      lauf: () => t("mk_l_lauf", { n: a.length, l: u.g.bezug }), pruefung: () => t(eins ? "mk_l_pruefung1" : "mk_l_pruefung", { n: a.length }),
      aufgabe: () => t(eins ? "mk_l_auf1" : "mk_l_auf", { n: a.length, x: u.g.bezug }), agent: () => t(eins ? "mk_l_auf1" : "mk_l_auf", { n: a.length, x: u.g.bezug }),
      sonst: () => t(eins ? "mk_l_auf1" : "mk_l_auf", { n: a.length, x: u.g?.bezug || t("mk_unbekannt") }) }[u.art]();
    /* je Aufgabe eine Zeile mit dem Weg (läuft, wartet auf dich, Prüfung) – sonst eine Zeile für die ganze Ursache */
    const einzeln = ["laeuft", "dich", "pruefung"].includes(u.art);
    const detail = x => {
      if (u.art === "laeuft") return [x.agent === "Entwickler" ? t("pl_du") : (x.agent || t("pl_frei")), x.begonnen_utc ? t("mk_seit", { x: zeit(x.begonnen_utc) }) : null].filter(Boolean).join(" · ");
      if (u.art === "dich") { const g = (x.gruende || []).find(y => y.an_dich);
        return g?.art === "frage" ? [t("mk_frage", { f: g.bezug, x: mkKurz(g.kurz, 90) }), t("mk_seit", { x: zeit(g.seit) })].join(" · ")
          : g ? t("mk_dich_seit", { x: zeit(g.seit) }) : t("mk_dich_aufgabe"); }
      if (u.art === "pruefung") return t("mk_pruefbitte", { p: "P" + x.pruefung.id, x: x.pruefung.pruefer, z: zeit(x.pruefung.seit) });
      return ""; };
    const knopfFuer = x => {
      if (u.art === "dich") { const g = (x.gruende || []).find(y => y.an_dich);
        return g?.art === "frage" ? el("button", { class: "knopf haupt", type: "button", onclick: () => zeige("fragen") }, t("mk_k_frage"))
          : el("button", { class: "knopf haupt", type: "button", onclick: () => aufgabeDialog(x.id) }, t("mk_k_ansehen")); }
      if (u.art === "pruefung") return leadKnopf("A" + x.id, `A${x.id} ${x.titel}`);
      return null; };
    let knopf = null, unten;
    if (einzeln && eins) { knopf = knopfFuer(s); unten = el("div", { class: "mk-wer" }, detail(s)); }
    else if (einzeln) unten = el("div", { class: "mk-wer mk-einzeln" }, a.map(x => el("div", {}, el("span", {}, ...zeileA(x), el("span", { class: "sehrleise" }, " · " + detail(x))), knopfFuer(x))));
    else {                                         /* Lauf, Aufgabe, Agent, Sonstiges: eine Zeile für alle, die daran hängen */
      const teile = [];
      if (u.art === "lauf") {
        const g = u.g;
        if (g.status === "laeuft") teile.push(t("mk_lauf_laeuft"));
        else if (g.platz) teile.push(t("mk_lauf_platz", { p: g.platz, v: g.von }) + (g.vor_fremd ? " – " + t(g.vor_fremd === 1 ? "mk_lauf_fremd1" : "mk_lauf_fremd", { n: g.vor_fremd }) : ""));
        if (g.status === "angemeldet") knopf = el("button", { class: "klein-knopf", type: "button", onclick: async () => {
          if (!confirm(t("re_vorziehen_frage", { l: g.bezug.slice(1), x: g.kurz || "" }))) return;
          try { await schicken("/api/lauf/vorziehen", { lauf: Number(g.bezug.slice(1)) }); toast(t("re_vorgezogen", { l: g.bezug.slice(1) })); zeige("planung", true); }
          catch (e) { toast(t("fehler", { x: e.message }), true); } } }, t("mk_k_lauf"));
      } else if (u.art === "aufgabe" && u.g.kurz) {
        teile.push(el("span", {}, aufLink(Number(u.g.bezug.slice(1)), u.g.bezug), ` „${mkKurz(u.g.kurz, 70)}“`
          + (u.g.status ? ` · ${t("sp_" + u.g.status) || u.g.status}` : "") + (u.g.agent ? ` · ${u.g.agent === "Entwickler" ? t("pl_du") : u.g.agent}` : "")));
      } else if (u.art === "agent") knopf = leadKnopf("A" + s.id, `A${s.id} ${s.titel}`);
      teile.push(el("span", {}, t("mk_betrifft"), " ", ...a.slice(0, 3).flatMap((x, i) => i ? [", ", aufLink(x.id)] : [aufLink(x.id)]),
        eins ? " " + mkKurz(s.titel, 70) : a.length > 3 ? " " + t("mk_und_weitere", { n: a.length - 3 }) : ""));
      unten = el("div", { class: "mk-wer" }, ...teile.flatMap((x, i) => i ? [" · ", x] : [x]));
    }
    return el("div", { class: "mk-lg" + (u.art === "dich" ? " du" : "") },
      el("i", { class: "mk-z " + (u.art === "laeuft" ? "laeuft" : u.art === "pruefung" ? "offen" : "wartet") }),
      el("div", { class: "mk-was" }, el("b", {}, kopf), einzeln && eins ? el("span", {}, " ", ...zeileA(s))
        : u.art === "lauf" && u.g.kurz ? el("span", {}, ` (${mkKurz(u.g.kurz, 70)})`) : null),
      knopf || el("span"), unten);
  };
  const reihe = ["laeuft", "dich", "lauf", "pruefung", "aufgabe", "agent", "sonst"];
  const lage = [...gruppen.values()].sort((x, y) => reihe.indexOf(x.u.art) - reihe.indexOf(y.u.art));

  /* Zeitschiene: Beginn → heute → Ziel, Prognose als gestrichelter Rahmen */
  const heute = new Date().toISOString().slice(0, 10);
  const beginn = [b.beginn_ist, ...b.schritte.map(s => (s.angelegt_utc || "").slice(0, 10))].filter(Boolean).sort()[0] || heute;
  const ende = [b.zieldatum, p?.p85, heute, ...b.schritte.map(s => (s.fertig_utc || "").slice(0, 10))].filter(Boolean).sort().pop();
  /* Lage auf der Schiene: innen 6 px Rand, damit Raute und Prognose-Rahmen am Ende nicht aus der Karte ragen */
  const von = mkMs(beginn), bis = Math.max(mkMs(ende), von + 864e5), anteil = x => Math.max(0, Math.min(1, (mkMs(x) - von) / (bis - von)));
  const proz = x => `calc(6px + ${anteil(x).toFixed(4)} * (100% - 12px))`;
  const fertigB = b.status === "fertig";
  const schiene = el("div", { class: "mk-schiene", "aria-label": t("mk_schiene_h", { a: datumKurz(beginn), b: b.zieldatum ? datumKurz(b.zieldatum) : "–" }) },
    el("span", { class: "linie" }), el("span", { class: "bisher" + (fertigB ? " fertig" : ""), style: `width:${proz(fertigB ? (b.fertig_utc || heute).slice(0, 10) : heute)}` }),
    p && !fertigB ? el("span", { class: "prog " + (p.ampel === "rot" ? "spaet" : p.ampel === "gelb" ? "knapp" : "plan"), style: `left:${proz(p.p50)};width:calc(${proz(p.p85)} - ${proz(p.p50)})`,
      title: `${t("pl_prognose")} ${datumKurz(p.p50)} – ${datumKurz(p.p85)}` }) : null,
    fertigB ? null : el("span", { class: "heute", style: `left:${proz(heute)}` }),
    b.zieldatum ? el("span", { class: "ziel", style: `left:${proz(b.zieldatum)}`, title: `${t("pl_zieldatum")} ${datumKurz(b.zieldatum)}` }) : null,
    el("span", { class: "mk-marke l" }, t("mk_beginn", { x: datumKurz(beginn) })),
    el("span", { class: "mk-marke r" }, [b.zieldatum ? t("mk_ziel", { x: datumKurz(b.zieldatum) }) : null,
      p && !fertigB ? p.wartet_auf ? t("pp_wartet_auf", { x: p.wartet_auf }) : t("mk_prog", { a: datumKurz(p.p50), b: datumKurz(p.p85) }) : null, fertigB && b.fertig_utc ? t("mk_fertig_am", { x: datumKurz(b.fertig_utc.slice(0, 10)) }) : null]
      .filter(Boolean).join(" · ")));

  /* Mini-Zeitlinie je Aufgabe auf derselben Achse: angelegt (Strich), gearbeitet (voll), gewartet (gestrichelt), fertig */
  const mini = (s, u) => {
    if (!s.angelegt_utc) return null;
    const ms = x => Math.max(0, Math.min(100, 100 * (Date.parse(x) - von) / (bis - von)));
    const jetzt = Date.now(), a = s.begonnen_utc, f = s.fertig_utc;
    const w = !["laeuft", "offen"].includes(u.art) && !["fertig", "verworfen"].includes(s.status) ? mkSeit(s) : null;
    const stueck = (k, x, y) => x && y && Date.parse(y) > Date.parse(x) ? el("i", { class: k, style: `left:${ms(x).toFixed(1)}%;width:${Math.max(.6, ms(y) - ms(x)).toFixed(1)}%` }) : null;
    const jetztIso = new Date(jetzt).toISOString();
    return el("span", { class: "mk-mini", title: [t("mk_angelegt", { x: zeit(s.angelegt_utc) }), a ? t("mk_begonnen", { x: zeit(a) }) : null,
        w ? t("mk_wartet_seit", { x: zeit(w) }) : null, f ? t("mk_fertig_am", { x: zeit(f) }) : null].filter(Boolean).join(" · ") },
      el("b", { style: `left:${ms(s.angelegt_utc).toFixed(1)}%` }),
      f ? stueck("fert", a || s.angelegt_utc, f) : stueck("lief", a, w && w > (a || "") ? w : jetztIso), w ? stueck("wart", w > (a || "") ? w : a || s.angelegt_utc, jetztIso) : null);
  };
  const aufgabeZeile = (s, u) => el("div", { class: "mk-a", id: "schritt-" + s.id, onclick: e => { if (!e.target.closest("a,button")) aufgabeDialog(s.id); } },
    el("span", { class: "mk-nr" }, "A" + s.id), el("span", { class: "mk-t" }, s.titel),
    el("span", { class: "mk-st" }, mkZeichen(s, u), mkStatus(s, u)),
    el("span", { class: "mk-meta" }, [s.agent === "Entwickler" ? t("pl_du") : (s.agent || t("pl_frei")),
      s.status !== "fertig" && s.status !== "verworfen" && mkSeit(s) ? t("mk_seit", { x: zeit(mkSeit(s)) }) : null,
      (s.kriterien || []).length ? `✓ ${s.kriterien.filter(k => k.erfuellt).length}/${s.kriterien.length}` : null,
      s.prognose && !["fertig", "verworfen"].includes(s.status) ? ppWann(s.prognose) : null].filter(Boolean).join(" · "),
      s.dokumente ? el("a", { class: "verweis", style: "margin-left:6px", onclick: () => { zustand.dok = { status: "aktuell", bezug: `aufgabe:${s.id}` }; zeige("dokumente"); } }, `📎 ${s.dokumente}`) : null),
    s.verschoben_aus ? el("span", { class: "mk-verschoben" }, "↪ " + t("mk_verschoben_aus", { b: bogenNr(s.verschoben_aus.bogen), x: datumKurz(s.verschoben_aus.am.slice(0, 10)) })) : null,
    mini(s, u));
  const rang = { dich: 0, laeuft: 1, lauf: 2, pruefung: 3, aufgabe: 4, agent: 5, sonst: 6, offen: 7 };
  const offenSortiert = offen.slice().sort((x, y) => rang[x.u.art] - rang[y.u.art]);
  const erledigt = b.schritte.filter(s => ["fertig", "verworfen"].includes(s.status)).sort((x, y) => (y.fertig_utc || "").localeCompare(x.fertig_utc || ""));

  const verweisListe = vs => (vs || []).length ? el("div", { class: "mk-verweise" }, vs.map(v => el("div", { class: "sehrleise" },
    "→ " + (v.titel ? `${v.ref} ${v.titel} · ` + (v.ref.startsWith("TH") ? t("th2_" + v.stand) + (v.stand === "frei" && v.fassung ? " · " + t("mk_fassung", { n: v.fassung }) : "")
      : t("mk_fassung", { n: v.fassung })) : t("mk_verweis_fehlt", { r: v.ref }))))) : null;
  const spec = teil => { const s = b.specs[teil] || { status: "entwurf" };
    return [el("dt", {}, t("teil_" + teil)), el("dd", {}, el("a", { class: "verweis", onclick: () => specDialog(b, teil) }, t("ss_" + s.status)))]; };
  const wellen = {};
  for (const s of b.schritte) (wellen[s.welle] ||= []).push(s);
  const details = el("details", { class: "mk-details" }, el("summary", {}, t("mk_details")),
    el("dl", {},
      b.ziel ? [el("dt", {}, t("pl_ziel")), el("dd", {}, b.ziel, verweisListe((b.verweise || {}).ziel))] : null,
      el("dt", {}, t("pl_abnahme")), el("dd", {}, b.abnahme ? [b.abnahme, verweisListe((b.verweise || {}).abnahme)] : el("span", { class: "rot-text" }, t("pl_fehlt"))),
      (b.themen || []).length ? [el("dt", {}, t("mk_themen")), el("dd", { class: "mk-themen" }, b.themen.map(x =>
        el("a", { class: "verweis mk-thema", onclick: () => { zustand.themaOffen = x.id; zeige("themen"); } }, `TH${x.id} ${x.name} `,
          el("span", { class: "th-status " + x.status }, t("th2_" + x.status)))))] : null,
      ...(Object.keys(b.specs || {}).length ? ["anforderungen", "entwurf", "schritte"].flatMap(spec) : []),     /* alter Bestand */
      el("dt", {}, t("pl_zieldatum")), el("dd", {}, datumKurz(b.zieldatum),
        b.baseline_datum && b.baseline_datum !== b.zieldatum ? el("span", { class: "sehrleise", title: b.baseline_grund || "" }, ` · ${t("pl_baseline")} ${datumKurz(b.baseline_datum)}`) : null,
        p ? el("span", { class: "sehrleise" }, ` · ${t("pl_prognose")} ${p.wartet_auf ? t("pp_wartet_auf", { x: p.wartet_auf }) : `${datumKurz(p.p50)} – ${datumKurz(p.p85)}`}`, tokenStueck(p),
          p.ampel_ohne_pause ? el("span", { class: "sehrleise", title: t("tk_ampel_h") }, " " + t("tk_ampel")) : null) : null),
      b.zuwachs ? [el("dt", {}, t("mk_hinzu")), el("dd", { title: t("zw_h") }, t("zw_satz", zwText(b.zuwachs)))] : null,
      b.dokumente ? [el("dt", {}, t("mk_dokumente")), el("dd", {}, el("a", { class: "verweis", onclick: () => { zustand.dok = { status: "aktuell", bezug: `bogen:${b.id}` }; zeige("dokumente"); } }, t("dk_n", { n: b.dokumente })))] : null,
      b.klaerungen.filter(k => k.status === "offen").length ? [el("dt", {}, t("mk_klaerungen")), el("dd", {}, el("a", { class: "verweis", onclick: () => zeige("fragen") },
        t("pl_klaerungen", { n: b.klaerungen.filter(k => k.status === "offen").length })))] : null),
    b.schritte.length ? el("details", { class: "tl-schritte" }, el("summary", {}, t("mk_wellen")),
      Object.keys(wellen).sort((x, y) => x - y).map(nr => el("div", { class: "welle" },
        el("div", { class: "welle-kopf" }, t("pl_welle", { n: nr }) + (wellen[nr].length > 1 ? " · " + t("pl_parallel") : "")),
        wellen[nr].map(s => schrittZeile(s, true))))) : null);

  return el("div", { class: `tl-bogen karte mk status-${b.status}`, id: "bogen-" + b.id },
    el("span", { class: "tl-punkt " + (b.status === "fertig" ? "gruen" : ampelKlasse(p?.ampel)) }),
    el("div", { class: "mk-kopf" },
      el("div", {}, el("h3", { class: "mk-titel" }, el("span", { class: "ref" }, bogenRef(b.id)), " ", b.titel),
        el("div", { class: "mk-wer-kopf" }, wer ? [t("mk_verantwortlich") + " ", el("b", {}, wer), " · "] : null, t("bs_" + b.status),
          b.zieldatum ? " · " + t("mk_ziel", { x: datumKurz(b.zieldatum) }) : "")),
      el("div", { class: "mk-knoepfe" }, vorziehen, mehr)),
    alleFertig ? el("div", { class: "tl-zeile tl-alle-fertig" }, t("pl_alle_fertig")) : null,
    el("p", { class: "mk-satz" }, el("b", {}, satz[0]), satz.length > 1 ? " · " + satz.slice(1).join(" · ") : ""),
    zahl || b.zieldatum ? schiene : null,
    lage.length ? el("div", { class: "mk-lage" }, lage.map(lageZeile)) : null,
    b.schritte.length ? el("div", { class: "mk-liste" },
      offenSortiert.length ? [el("div", { class: "mk-gruppe" }, t("mk_offen", { n: offenSortiert.length })), ...offenSortiert.map(x => aufgabeZeile(x.s, x.u))] : null,
      erledigt.length ? el("details", { class: "mk-fertige", open: offenSortiert.length ? null : "" }, el("summary", { class: "mk-gruppe" }, t("mk_fertig", { n: erledigt.length })),
        erledigt.map(s => aufgabeZeile(s, { art: "fertig" }))) : null,
      (b.weg || []).length ? el("details", { class: "mk-fertige" }, el("summary", { class: "mk-gruppe" }, t("mk_weg", { n: b.weg.length })),
        b.weg.map(w => el("div", { class: "mk-a weg", onclick: () => aufgabeDialog(w.id) }, el("span", { class: "mk-nr" }, "A" + w.id), el("span", { class: "mk-t" }, w.titel),
          el("span", { class: "mk-verschoben" }, "↪ " + (w.nach ? t("mk_verschoben_nach", { b: bogenNr(w.nach), x: datumKurz(w.am.slice(0, 10)) }) : t("mk_herausgenommen", { x: datumKurz(w.am.slice(0, 10)) })))))) : null)
      : el("div", { class: "sehrleise", style: "margin-top:8px" }, t("pl_keine_schritte")),
    details);
}
function schrittZeile(s, ohneId) {         /* ohneId: in den Details der Meilenstein-Karte – die Zeile mit der Kennung steht oben in der Liste */
  const k = s.kriterien || [], erfuellt = k.filter(x => x.erfuellt).length, mensch = s.agent === "Entwickler";
  return el("div", { class: `schritt status-${s.status}${mensch ? " mensch" : ""}`, id: ohneId ? null : "schritt-" + s.id },
    el("span", { class: "ref" }, `A${s.id}`),
    el("span", { class: "schritt-titel" }, s.titel),
    el("span", { class: "etikett" + (s.status === "laeuft" ? " gruen" : s.blockiert_durch.length ? " rot" : "") },
      s.blockiert_durch.length ? t("pl_wartet_auf", { x: s.blockiert_durch.map(x => "A" + x).join(", ") }) : t("sp_" + s.status) || s.status),
    el("span", { class: "schritt-meta sehrleise" },
      [mensch ? t("pl_du") : (s.agent || t("pl_frei")), k.length ? `✓ ${erfuellt}/${k.length}` : null,
       s.komplexitaet ? `K${s.komplexitaet}` + (s.komplexitaet >= 7 ? (s.plan_status === "frei" ? " · Plan ✓" : " · " + t("pl_plan_fehlt")) : "") : null,
       s.prognose && s.status !== "fertig" ? ppWann(s.prognose) + (s.prognose.pause_tage && !s.prognose.wartet_auf ? ` ${TKZ} ${t("tk_plus", { n: s.prognose.pause_tage, x: datumKurz(s.prognose.p50_mit) })}` : "") : null,
       s.anforderungen].filter(Boolean).join(" · "),
      s.dokumente ? el("a", { class: "verweis", style: "margin-left:6px", onclick: () => { zustand.dok = { status: "aktuell", bezug: `aufgabe:${s.id}` }; zeige("dokumente"); } }, `📎 ${s.dokumente}`) : null));
}
/* Jeder Dialog bekommt oben rechts „✕“ – am Handy gibt es kein Esc, und der Hintergrund ist oft ganz verdeckt. ✕ und Esc
   wirken wie ein Klick daneben: so greift die eigene Schließ-Logik eines Dialogs (z. B. Rückfrage im Editor). */
new MutationObserver(ms => { for (const m of ms) for (const n of m.addedNodes) {
  if (!n.classList?.contains("dialog-hg") || n.querySelector(".dialog-zu") || !n.firstElementChild) continue;
  n.firstElementChild.prepend(el("button", { class: "dialog-zu", type: "button", title: t("vb_schliessen"), "aria-label": t("vb_schliessen"),
    onclick: () => n.dispatchEvent(new MouseEvent("click", { bubbles: true })) }, "✕")); } }).observe(document.body, { childList: true });
/* Enter in einem einzeiligen Feld (Strg+Enter auch im Textfeld) löst den Hauptknopf des obersten Dialogs aus */
window.addEventListener("keydown", e => { if (e.key !== "Enter" || e.defaultPrevented || e.isComposing) return;
  const x = e.target, hg = x.closest?.(".dialog-hg"); if (!hg || hg !== [...document.querySelectorAll(".dialog-hg")].pop()) return;
  const einzeilig = x.tagName === "INPUT" && !["checkbox", "radio", "file", "button", "submit"].includes(x.type);
  if (!einzeilig && !(x.tagName === "TEXTAREA" && (e.ctrlKey || e.metaKey))) return;
  const k = hg.querySelector(".knopf.haupt:not([disabled])"); if (k) { e.preventDefault(); k.click(); } });
/* Esc schließt nur den obersten Dialog (Vollbild und Editor fangen Esc vorher selbst ab) */
window.addEventListener("keydown", e => { if (e.key !== "Escape" || e.defaultPrevented) return;
  const oben = [...document.querySelectorAll(".dialog-hg")].pop(); if (oben) { e.preventDefault(); oben.dispatchEvent(new MouseEvent("click", { bubbles: true })); } });
/* Benutzer der Online-Seite (Stufe R1b, nur am PC): anlegen, Rolle und Projekte vergeben, freischalten, sperren.
   Der Freischalt-Code erscheint genau einmal im Dialog – die AMW speichert ihn nirgends. */
async function benutzerZeichnen(ziel) {
  let d; try { d = await holen("/api/benutzer"); } catch (e) { ziel.replaceChildren(el("div", { class: "rot-text" }, String(e.message || e))); return; }
  const neu = el("input", { type: "text", placeholder: t("bn_neu_ph"), maxlength: 60, autocomplete: "off", id: "bn-neu-name" });
  const tun = async (was, daten, knopf) => {
    if (knopf) knopf.disabled = true;
    try { const r = await schicken("/api/benutzer/" + was, daten); return r; }
    catch (e) { toast(t("fehler", { x: e.message }), true); return null; }
    finally { if (knopf) knopf.disabled = false; } };
  const anlegen = el("button", { class: "klein-knopf", type: "button", id: "bn-anlegen", onclick: async e => {
    const name = neu.value.trim(); if (!name) return;
    const mit = API && !d.rollen.includes("system_admin") && projekt ? { projekte: [projekt] } : {};   // Projekt-Admin online: im aktuellen Projekt
    const r = await tun("neu", { name, ...mit }, e.target); if (r) { if (r.unterwegs) toast(t("bn_unterwegs")); benutzerZeichnen(ziel); } } }, "+ " + t("bn_anlegen"));
  neu.addEventListener("keydown", e => { if (e.key === "Enter") anlegen.click(); });
  const stand = b => { const o = b.online || {};
    if (b.gesperrt) return [t("bn_st_gesperrt"), "rot-text"];
    if (o.stand === "eingerichtet") return [!b.rolle ? t("bn_st_freigabe") : o.angemeldet_utc ? t(o.firmenkonto ? "bn_st_firmenkonto" : "bn_st_angemeldet", { x: zeit(o.angemeldet_utc) }) : t("bn_st_eingerichtet"), !b.rolle ? "bernstein-text" : "sehrleise"];
    if (o.stand === "wartet_code") return [t("bn_st_wartet_code", { x: zeit(o.bis) }), "sehrleise"];
    if (o.stand === "code_abgelaufen") return [t("bn_st_code_abgelaufen"), "sehrleise"];
    return [t("bn_st_neu"), "sehrleise"]; };
  const zeile = b => {
    const rolle = el("select", { "aria-label": t("bn_rolle") }, el("option", { value: "" }, t("bn_wartet_rolle")),
      d.rollen.map(r => el("option", { value: r }, t("rolle_" + r))));
    rolle.value = b.rolle || "";
    const haken = d.projekte.map(p => { const x = el("input", { type: "checkbox", value: p.id }); x.checked = b.projekte.includes(p.id);
      return el("label", { class: "bn-projekt" }, x, " " + p.name); });
    const projekteFeld = el("div", { class: "bn-projekte" }, ...haken);
    const allePr = el("span", { class: "sehrleise" }, t("bn_alle_projekte"));
    const sichtbar = () => { const sa = rolle.value === "system_admin"; projekteFeld.hidden = sa; allePr.hidden = !sa; };
    rolle.addEventListener("change", sichtbar); sichtbar();
    const email = el("input", { type: "email", value: b.email || "", placeholder: t("bn_email_ph"), autocomplete: "off", spellcheck: "false", class: "bn-email" });
    const speichernK = el("button", { class: "klein-knopf", type: "button", onclick: async e => {
      const projekte = haken.map(h => h.querySelector("input")).filter(x => x.checked).map(x => API ? x.value : Number(x.value));   // online: Kennung (uid)
      const r = await tun("aendern", { name: b.name, rolle: rolle.value || null, projekte, email: email.value.trim() }, e.target);
      if (r) { toast(t(r.unterwegs ? "bn_unterwegs" : "gespeichert")); benutzerZeichnen(ziel); } } }, t("speichern"));
    const eingerichtet = b.online?.stand === "eingerichtet";
    const freiK = el("button", { class: "klein-knopf", type: "button", disabled: b.gesperrt || !d.online ? "disabled" : null, onclick: async e => {
      if (eingerichtet && !confirm(t("bn_neu_frage", { x: b.name }))) return;
      const r = await tun("freischalten", { name: b.name }, e.target); if (!r) return;
      benutzerCode(b.name, r); benutzerZeichnen(ziel); } }, t(eingerichtet ? "bn_neu_freischalten" : "bn_freischalten"));
    const sperrK = el("button", { class: "klein-knopf", type: "button", onclick: async e => {
      const r = await tun("aendern", { name: b.name, gesperrt: !b.gesperrt }, e.target); if (r) { if (r.unterwegs) toast(t("bn_unterwegs")); benutzerZeichnen(ziel); } } }, t(b.gesperrt ? "bn_entsperren" : "bn_sperren"));
    const [st, kl] = stand(b);
    return el("div", { class: "bn-zeile", "data-name": b.name },
      el("div", { class: "bn-kopf" }, el("b", {}, b.name), el("span", { class: kl }, st)),
      el("div", { class: "bn-felder" }, el("label", { class: "bn-label" }, t("bn_rolle"), rolle),
        el("div", { class: "bn-label" }, el("span", {}, t("bn_projekte")), projekteFeld, allePr),
        el("label", { class: "bn-label" }, t("bn_email"), email)),
      el("div", { class: "bn-knoepfe" }, speichernK, freiK, sperrK)); };
  ziel.replaceChildren(...[
    d.online ? null : el("p", { class: "bernstein-text", style: "margin:0 0 10px;font-size:13px" }, t("bn_ohne_speicher")),
    d.benutzer.length ? el("div", { class: "bn-liste" }, ...d.benutzer.map(zeile)) : el("div", { class: "sehrleise", style: "margin-bottom:10px" }, t("bn_keine")),
    el("div", { class: "bn-neu" }, neu, anlegen), ssoAbschnitt(d)].filter(Boolean));
}
/* Firmen-Anmeldung (Stufe R2, nur am PC): an/aus, Aussteller, Client-ID. Das Geheimnis des Anbieters trägt ein System-Admin
   auf der Online-Seite ein (sso.php?einrichten) – hier steht nur, ob es dort liegt, und die Adresse für den Anbieter. */
function ssoAbschnitt(d) {
  const s = d.sso;
  const kopf = el("h4", { style: "margin:18px 0 6px" }, t("sso_titel"), " ", hilfeKnopf("firmen-anmeldung"));
  if (!s) return el("div", { id: "e-sso" }, kopf, el("p", { class: "sehrleise", style: "margin:0" }, t("sso_ohne_speicher")));
  const an = el("input", { type: "checkbox", id: "sso-an" }); an.checked = !!s.an;
  const aus = el("input", { type: "text", value: s.aussteller || "", placeholder: "https://login.microsoftonline.com/…/v2.0", autocomplete: "off", spellcheck: "false", id: "sso-aussteller" });
  const cid = el("input", { type: "text", value: s.client_id || "", placeholder: "00000000-0000-0000-0000-000000000000", autocomplete: "off", spellcheck: "false", id: "sso-client" });
  const basis = d.seite_adresse ? d.seite_adresse.replace(/\/?$/, "/") : "";
  const rueck = s.rueckweg || (basis ? basis + "sso.php" : "");
  const zeile = (text, inhalt, hinweis) => el("label", { class: "bn-label", style: "margin-bottom:8px" }, text, inhalt,
    hinweis ? el("span", { class: "sehrleise" }, hinweis) : null);
  const knopf = el("button", { class: "klein-knopf", type: "button", id: "sso-speichern", onclick: async e => {
    e.target.disabled = true;
    try { await schicken("/api/einstellungen/sso", { an: an.checked, aussteller: aus.value.trim(), client_id: cid.value.trim() }); toast(t("gespeichert")); }
    catch (f) { toast(t("fehler", { x: f.message }), true); }
    finally { e.target.disabled = false; } } }, t("speichern"));
  return el("div", { id: "e-sso" }, kopf, el("p", { class: "leise", style: "margin:0 0 10px;font-size:13px" }, t("sso_h")),
    el("label", { class: "bn-projekt", style: "margin-bottom:10px;font-size:13px" }, an, " " + t("sso_an")),
    zeile(t("sso_aussteller"), aus, t("sso_aussteller_h")), zeile(t("sso_client"), cid),
    zeile(t("sso_rueckweg"), el("span", { class: rueck ? "mono" : "sehrleise", style: "overflow-wrap:anywhere;color:var(--text)" }, rueck || t("sso_rueckweg_fehlt")), rueck ? t("sso_rueckweg_h") : null),
    zeile(t("sso_geheimnis"), el("span", { class: s.zugang ? "" : "bernstein-text", style: "font-size:13px", id: "sso-zugang" }, t(s.zugang ? "sso_zugang_" + s.zugang : "sso_zugang_fehlt")),
      el("span", {}, t("sso_eintragen_h"), basis ? [" ", el("a", { href: basis + "sso.php?einrichten", target: "_blank", rel: "noopener", style: "color:var(--bernstein)" }, t("sso_eintragen"))] : null)),
    el("div", { class: "bn-knoepfe" }, knopf));
}
function benutzerCode(name, r) {
  const code = el("div", { class: "bn-code mono", id: "bn-code" }, r.code);
  const kopie = el("button", { class: "klein-knopf", type: "button", onclick: async e => {
    try { await navigator.clipboard.writeText(r.code); e.target.textContent = t("bn_kopiert"); } catch (f) { /* Zwischenablage gesperrt: Code steht da */ } } }, t("bn_kopieren"));
  let hg;
  const zu = el("button", { class: "knopf haupt", type: "button", onclick: () => hg.remove() }, t("bn_fertig"));
  hg = dialog(t("bn_code_titel", { x: name }), code,
    el("p", { class: "leise", style: "margin:12px 0" }, t("bn_code_h", { x: name, b: zeit(r.bis) })), el("div", { style: "display:flex;gap:8px" }, kopie, zu));
}
function dialog(titel, ...inhalt) {
  const hg = el("div", { class: "dialog-hg", onclick: e => { if (e.target === hg) hg.remove(); } },
    el("div", { class: "karte dialog einst", style: "width:min(820px,94vw);max-height:88vh;overflow-y:auto" }, el("h3", {}, titel), ...inhalt));
  document.body.append(hg);
  return hg;
}
const fragenStand = (o, n) => n === 1 ? t(o ? "au_frage_offen" : "au_frage_beantwortet")
  : o ? t("au_fragen_offen", { o, n }) : t("au_fragen_alle", { n });
/* Eine Aufgabe ganz: Auftrag, Stand, Wartegründe, Fragen (mit Antwort), Dokumente, Beschlüsse, Verlauf, Läufe, Prüfungen.
   Eigene Aufgaben des Entwicklers: erledigt (Notiz = Beleg) / später; zu jeder: Antwort an den Zuständigen. */
async function aufgabeDialog(id) {
  let a; try { a = await abrufen("/api/aufgabe?id=" + id); }
  catch (e) { toast(API ? t("au_nur_pc", { a: id }) : t("fehler", { x: e.message }), true); return; }
  const offen = !["fertig", "verworfen"].includes(a.status), an = a.angelegt_von && !["Entwickler", "AMW"].includes(a.angelegt_von) ? a.angelegt_von : (a.zustaendig || "Lead");
  const notiz = el("textarea", { rows: 3, placeholder: t(a.fuer_dich && offen ? "au_notiz_ph" : "au_antwort_ph", { x: an }) });
  const tun = async (was, mitText) => {
    const text = notiz.value.trim();
    if (mitText && !text) { notiz.focus(); toast(t(was === "erledigt" ? "au_notiz_fehlt" : "au_text_fehlt"), true); return; }
    try { const r = await schicken("/api/aufgabe/" + was, { id: a.id, text });
      if (!r.unterwegs) toast(t("au_" + was + "_ok", { a: a.id, x: r.an || an }));
      hg.remove(); if (was === "antwort") aufgabeDialog(a.id); else zeige(zustand.sicht, true); }
    catch (e) { toast(t("fehler", { x: e.message }), true); } };
  const block = (titel, n, inhalt) => n ? el("div", { class: "au-block" }, el("h4", {}, titel), inhalt) : null;
  const nOffen = a.fragen.filter(f => f.status === "offen").length;
  const fr = a.fragen.map(f => el("div", { class: "au-zeile" }, el("span", { class: "ref" }, `F${f.id}`), " ",
    el("span", { class: "etikett " + (f.status === "offen" ? (f.geparkt_utc ? "" : "bernstein") : "gruen") },
      f.status === "offen" ? t(f.geparkt_utc ? "au_geparkt" : "au_offen") : t("au_beantwortet")), " ", f.kurz,
    f.antwort ? el("div", { class: "leise", style: "margin-top:2px" }, "→ " + (f.antwort_art === "option" ? t("au_option", { x: f.antwort }) : f.antwort)) : null));
  const hg = dialog(`A${a.id} · ${a.titel}`,
    el("p", { class: "leise", style: "margin-top:0" }, [t("sp_" + a.status) || a.status, a.agent ? t("au_bei", { x: a.agent }) : t("au_ohne"),
      a.angelegt_von ? t("von", { x: a.angelegt_von }) : null, zeit(a.angelegt_utc), a.zustaendig ? t("au_zustaendig", { x: a.zustaendig }) : null,
      a.bogen_id ? bogenRef(a.bogen_id) + (a.bogen_titel ? " " + t("zitat", { x: a.bogen_titel }) : "") : null].filter(Boolean).join(" · ")),
    a.fragen.length ? el("p", {}, el("span", { class: "etikett " + (nOffen ? "bernstein" : "gruen") },
      fragenStand(nOffen, a.fragen.length))) : null,
    a.auftrag ? el("div", { class: "au-auftrag" }, markdown(a.auftrag)) : null,
    a.wartet_auf && offen ? el("p", { class: "bernstein-text" }, "⇢ " + a.wartet_auf) : null,
    block(t("au_wartegruende"), a.wartegruende.length, a.wartegruende.map(w => el("div", { class: "au-zeile" + (w.erledigt_utc ? " sehrleise" : "") },
      (w.erledigt_utc ? "✓ " : "⇢ ") + w.bezug + ` · ${w.angelegt_von} ${zeit(w.angelegt_utc)}` + (w.erledigt_utc ? ` · ${w.erledigt_durch || ""}` : "")))),
    block(t("au_fragen", { n: a.fragen.length }), a.fragen.length, fr),
    block(t("au_dokumente", { n: a.dokumente.length }), a.dokumente.length, a.dokumente.map(d => el("div", { class: "au-zeile" },
      el("a", { class: "verweis", onclick: () => dokumentDialog(d.id) }, `D${d.id}`), " ", d.titel, el("span", { class: "sehrleise" }, ` · ${t("dka_" + d.art)}`)))),
    block(t("au_beschluesse", { n: a.beschluesse.length }), a.beschluesse.length, a.beschluesse.map(b => el("div", { class: "au-zeile" + (b.status === "gilt" ? "" : " sehrleise") },
      el("span", { class: "ref" }, `B${b.id}`), " ", el("b", {}, b.stichwort), b.status === "gilt" ? "" : ` (${b.status})`, el("div", { class: "leise" }, b.regel)))),
    block(t("au_laeufe", { n: a.laeufe.length }), a.laeufe.length, a.laeufe.map(l => el("div", { class: "au-zeile" },
      `L${l.id} · ${l.agent} · ${l.status}` + (l.rc != null ? ` · rc ${l.rc}` : "") + ` · ${l.beschreibung}`))),
    block(t("au_pruefungen", { n: a.pruefungen.length }), a.pruefungen.length, a.pruefungen.map(p => el("div", { class: "au-zeile" },
      `P${p.id} · ${p.pruefer} · ${p.ergebnis}` + (p.bemerkung ? ` · ${p.bemerkung}` : "")))),
    a.messung && (a.messung.usd || a.messung.aktiv_s || a.messung.warten_s) ? block(t("au_verbrauch"), 1, el("div", {},   /* A1844 */
      el("b", { class: "mono" }, t("au_verbrauch_x", { x: dollar(a.messung.usd) })),
      a.verbrauch?.modelle?.length ? el("span", { class: "sehrleise" }, ` · ${a.verbrauch.modelle.join(", ")}`) : null,
      el("div", { class: "leise", style: "font-size:13px" }, t("au_zeiten", { a: dauerKurz(a.messung.aktiv_s), w: dauerKurz(a.messung.warten_s), l: dauerKurz(a.messung.liege_s) })
        + (Object.keys(a.messung.warten).length ? " (" + Object.entries(a.messung.warten).sort((x, y) => y[1] - x[1]).map(([k, s]) => `${t("au_wg_" + k)} ${dauerKurz(s)}`).join(", ") + ")" : "")),
      a.messung.erfasst.length ? el("div", { class: "sehrleise", style: "font-size:12px" }, t("au_erfasst", { n: a.messung.erfasst.length })) : null,
      a.messung.luecken.length ? el("div", { class: "sehrleise", style: "font-size:12px" }, t("au_luecken") + " " + a.messung.luecken.join(" · ")) : null,
      el("div", { class: "sehrleise", style: "font-size:12px" }, t("k_aufwand_h")))) : null,
    a.empfehlung ? block(t("au_empfehlung"), 1, el("div", {},
      el("b", {}, t("au_empf_x", { g: a.empfehlung.groesse, a: t("ga_" + a.empfehlung.art), x: modellStufe(a.empfehlung.modell, a.empfehlung.denkstufe) })),
      el("div", { class: "leise" }, a.empfehlung.zelle ? t("au_empf_zelle", { x: dollar(a.empfehlung.zelle.median), n: a.empfehlung.zelle.n, r: a.empfehlung.zelle.rot })
        : t("au_empf_keine_zelle")),
      a.empfehlung.passt === false ? el("div", { class: "bernstein-text" }, t("au_empf_profil", { a: a.empfehlung.agent,
        x: modellStufe(a.empfehlung.profil.modell, a.empfehlung.profil.denkstufe) })) : null,
      el("div", { class: "sehrleise", style: "font-size:12px" }, t("empf_h")))) : null,
    a.zusammenfassung ? block(t("au_zusammenfassung"), 1, el("div", {}, a.zusammenfassung, a.beleg ? el("div", { class: "sehrleise" }, t("au_beleg", { x: a.beleg })) : null)) : null,
    block(t("au_verlauf", { n: a.verlauf.length }), a.verlauf.length, a.verlauf.map(n => el("div", { class: "dk-nachricht" },
      el("div", { class: "sehrleise" }, `#${n.id} · ${wer(n.von)} · ${t("art_" + n.art) || n.art} · ${seit(n.zeit_utc)}`), el("div", {}, n.kurz),
      n.text ? el("div", { class: "leise kurztext", style: "white-space:pre-wrap", title: t("aufklappen"), onclick: e => e.currentTarget.classList.toggle("auf") }, n.text) : null))),
    el("div", { class: "au-block" }, el("h4", {}, a.fuer_dich && offen ? t("au_dein_teil") : t("au_antwort_titel", { x: an })), notiz,
      el("div", { class: "dk-aktionen", style: "margin-top:8px" },
        a.fuer_dich && offen ? el("button", { class: "knopf haupt", type: "button", onclick: () => tun("erledigt", true) }, t("au_erledigt")) : null,
        el("button", { class: a.fuer_dich && offen ? "klein-knopf" : "knopf haupt", type: "button", onclick: () => tun("antwort", true) }, t("au_antwort", { x: an })),
        a.fuer_dich && offen ? el("button", { class: "klein-knopf", type: "button", onclick: () => tun("spaeter", false) }, t("au_spaeter")) : null,
        a.laufend_id ? el("button", { class: "klein-knopf", type: "button", title: t("au_dazwischen_h", { x: a.agent, a: a.laufend_id }),
          onclick: () => tun("dazwischen", true) }, t("au_dazwischen")) : null),
      a.laufend_id ? el("p", { class: "sehrleise", style: "margin:6px 0 0" }, t("au_dazwischen_h", { x: a.agent, a: a.laufend_id })) : null));
}
/* Wer hat geschrieben, wer vorgelegt, wer freigegeben (Vorlage durch den Lead sichtbar) */
function specWer(s) {
  const teile = [];
  if (s.geschrieben_von) teile.push(t("sw_verfasst", { x: s.geschrieben_von }));
  if (s.vorgelegt_von && ["vorgelegt", "frei", "zurueck"].includes(s.status))
    teile.push(t(s.vorgelegt_von !== s.geschrieben_von ? "sw_vorgelegt_geprueft" : "sw_vorgelegt", { x: s.vorgelegt_von }));
  if (s.frei_von && s.status === "frei") teile.push(t("sw_frei", { x: s.frei_von }));
  return teile.length ? " · " + teile.join(" · ") : "";
}
function specDialog(b, teil) {
  const s = b.specs[teil] || { status: "entwurf", text: "" };
  const kommentar = el("textarea", { rows: 3, placeholder: t("pl_kommentar_ph") });
  const entscheiden = async frei => {
    try { await schicken("/api/plan/spec", { bogen: b.id, teil, frei, kommentar: kommentar.value }); hg.remove(); toast(frei ? t("pl_freigegeben") : t("pl_zurueck_gegeben")); zeige("planung", true); }
    catch (e) { toast(t("fehler", { x: e.message }), true); } };
  const klaer = b.klaerungen.filter(k => k.fundstellen === `bogen:${b.id}:${teil}`);
  const hg = dialog(`${bogenRef(b.id)} · ${t("teil_" + teil)}`,
    el("p", { class: "leise", style: "margin-top:0" }, `${t("ss_" + s.status)} · v${s.version || 1}` + specWer(s)
      + (s.geaendert_utc ? ` · ${seit(s.geaendert_utc)}` : "")),
    s.kommentar ? el("div", { class: "band-warn" }, el("b", {}, t("pl_letzter_kommentar")), s.kommentar) : null,
    klaer.length ? el("div", { class: "sehrleise" }, t("pl_klaerungen_liste") + " " + klaer.map(k => `F${k.id} (${k.status})`).join(", ")) : null,
    el("pre", { class: "spec-text" }, s.text || t("pl_leer_spec")),
    s.status === "vorgelegt" ? el("div", {}, kommentar, el("div", { class: "aktionen" },
      el("button", { class: "klein-knopf", type: "button", onclick: () => entscheiden(false) }, t("pl_zurueck")),
      el("button", { class: "knopf haupt", type: "button", onclick: () => entscheiden(true) }, t("pl_freigeben"))))
      : el("p", { class: "sehrleise" }, t("pl_nicht_vorgelegt")));
}
function planDialog(p) {
  const kommentar = el("textarea", { rows: 3, placeholder: t("pl_kommentar_ph") });
  const entscheiden = async frei => {
    try { await schicken("/api/plan/planfrei", { aufgabe: p.id, frei, kommentar: kommentar.value }); hg.remove(); zeige("planung", true); }
    catch (e) { toast(t("fehler", { x: e.message }), true); } };
  const hg = dialog(`A${p.id} · ${p.titel}`, el("p", { class: "leise" }, t("pl_plan_von", { x: p.agent || "–" })),
    el("pre", { class: "spec-text" }, p.plan || "…"), kommentar, el("div", { class: "aktionen" },
      el("button", { class: "klein-knopf", type: "button", onclick: () => entscheiden(false) }, t("pl_zurueck")),
      el("button", { class: "knopf haupt", type: "button", onclick: () => entscheiden(true) }, t("pl_freigeben"))));
}
function bogenDialog(b) {
  const ein = (wert, art) => el("input", { type: art || "text", value: wert || "" });
  const f = { titel: ein(b?.titel), ziel: ein(b?.ziel), abnahme: ein(b?.abnahme), zieldatum: ein(b?.zieldatum, "date"), grund: ein("") };
  const zeile = (l, x, h) => el("div", { class: "feld" }, el("label", {}, l), el("div", {}, x, h ? el("div", { class: "sehrleise", style: "font-size:12px" }, h) : null));
  const knopf = el("button", { class: "knopf haupt", type: "button" }, t("speichern"));
  const hg = dialog(b ? bogenRef(b.id) : t("pl_bogen_neu"), zeile(t("pl_titel"), f.titel), zeile(t("pl_ziel"), f.ziel),
    zeile(t("pl_abnahme"), f.abnahme, t("pl_abnahme_h")), zeile(t("pl_zieldatum"), f.zieldatum),
    b?.baseline_datum ? zeile(t("pl_grund"), f.grund, t("pl_grund_h", { x: datumKurz(b.baseline_datum) })) : null,
    el("div", { class: "aktionen" }, knopf, el("button", { class: "knopf", type: "button", onclick: () => hg.remove() }, t("abbrechen"))),
    b ? gespraechZu(`M${b.id}`, `M${b.nr} ${b.titel}`) : null);
  knopf.addEventListener("click", async () => {
    const daten = { titel: f.titel.value.trim(), ziel: f.ziel.value.trim(), abnahme: f.abnahme.value.trim(), zieldatum: f.zieldatum.value || null };
    try { await schicken("/api/plan/bogen", b ? { ...daten, bogen: b.id, grund: f.grund.value.trim() || null } : { ...daten, aktion: "neu" });
      hg.remove(); zeige("planung", true); } catch (e) { toast(t("fehler", { x: e.message }), true); }
  });
}
function leitbildAnsicht(lb) {
  const feld = (wert, zeilen) => el("textarea", { rows: zeilen || 3 }, wert);
  const f = { ziel: feld(lb.ziel, 2), kennzahlen: feld(lb.kennzahlen.join("\n")), nicht_ziele: feld(lb.nicht_ziele.join("\n")),
    prinzipien: feld(lb.prinzipien.map(p => p.text + (p.pruefung ? " | " + p.pruefung : "")).join("\n"), 4), dod: feld(lb.dod.join("\n"), 4) };
  const zeile = (l, x, h) => el("div", { class: "feld" }, el("label", {}, l), el("div", {}, x, h ? el("div", { class: "sehrleise", style: "font-size:12px" }, h) : null));
  const knopf = el("button", { class: "knopf haupt", type: "button" }, t("speichern"));
  knopf.addEventListener("click", async () => {
    try { await schicken("/api/plan/leitbild", { ziel: f.ziel.value.trim(), kennzahlen: f.kennzahlen.value, nicht_ziele: f.nicht_ziele.value,
      prinzipien: f.prinzipien.value.split("\n").map(z => z.replace(" | ", "|")).join("\n"), dod: f.dod.value }); toast(t("gespeichert")); }
    catch (e) { toast(t("fehler", { x: e.message }), true); }
  });
  return el("div", { class: "karte einst", style: "padding:16px 18px" }, el("p", { class: "leise", style: "margin-top:0" }, t("lb_h")),
    zeile(t("lb_ziel"), f.ziel, t("lb_ziel_h")), zeile(t("lb_kennzahlen"), f.kennzahlen, t("lb_zeilen")), zeile(t("lb_nicht"), f.nicht_ziele, t("lb_nicht_h")),
    zeile(t("lb_prinzipien"), f.prinzipien, t("lb_prinzipien_h")), zeile(t("lb_dod"), f.dod, t("lb_dod_h")), el("div", { style: "margin-top:12px" }, knopf));
}
function risikoAnsicht(d) {
  const offen = d.risiken.filter(r => r.status !== "erledigt");
  const zelle = (w, a) => { const n = offen.filter(r => r.wahrscheinlichkeit === w && r.auswirkung === a).length, wert = w * a;
    return el("div", { class: "rm-zelle " + (wert >= 15 ? "rm-rot" : wert >= 8 ? "rm-gelb" : "rm-gruen"), title: `W${w} × A${a} = ${wert}` }, n || ""); };
  const matrix = el("div", { class: "rm" }, el("div", { class: "rm-y sehrleise" }, t("rs_auswirkung")),
    el("div", { class: "rm-gitter" }, [5, 4, 3, 2, 1].flatMap(a => [el("div", { class: "rm-achse sehrleise" }, a), ...[1, 2, 3, 4, 5].map(w => zelle(w, a))]),
      el("div", {}), ...[1, 2, 3, 4, 5].map(w => el("div", { class: "rm-achse sehrleise" }, w))),
    el("div", { class: "rm-x sehrleise" }, t("rs_wahrscheinlichkeit")));
  return el("div", {}, el("div", { class: "rm-huelle" }, matrix, el("div", { class: "sehrleise", style: "max-width:360px" }, t("rs_h"))),
    el("div", { style: "margin:12px 0" }, el("button", { class: "klein-knopf", type: "button", onclick: () => risikoDialog(null) }, t("rs_neu"))),
    d.risiken.length ? el("div", { class: "eintraege" }, d.risiken.map(r => el("div", { class: "karte risiko status-" + r.status, onclick: () => risikoDialog(r) },
      el("div", {}, el("span", { class: "ref" }, `R${r.id}`), " ", el("b", {}, r.titel), " ",
        el("span", { class: "etikett " + (r.wert >= 15 ? "rot" : r.wert >= 8 ? "bernstein" : "gruen") }, `${r.wahrscheinlichkeit}×${r.auswirkung}=${r.wert}`), " ",
        el("span", { class: "etikett" }, t("rst_" + r.status))),
      el("div", { class: "sehrleise" }, [r.strategie ? t("str_" + r.strategie) : null, r.massnahme, r.verantwortlich].filter(Boolean).join(" · ") || t("rs_ohne"))))) : el("div", { class: "leer" }, t("rs_keine")));
}
function risikoDialog(r) {
  const ein = v => el("input", { type: "text", value: v || "" });
  const wahl = (werte, v) => { const s = el("select", {}, werte.map(([k, l]) => el("option", { value: k }, l))); s.value = v ?? werte[0][0]; return s; };
  const skala = [1, 2, 3, 4, 5].map(x => [String(x), String(x)]);
  const f = { titel: ein(r?.titel), ursache: ein(r?.ursache), wirkung: ein(r?.wirkung), w: wahl(skala, String(r?.wahrscheinlichkeit || 3)),
    a: wahl(skala, String(r?.auswirkung || 3)), strategie: wahl([["", "–"], ...["vermeiden", "mindern", "uebertragen", "akzeptieren"].map(s => [s, t("str_" + s)])], r?.strategie || ""),
    massnahme: ein(r?.massnahme), verantwortlich: ein(r?.verantwortlich), ausloeser: ein(r?.ausloeser),
    status: wahl(["offen", "eingetreten", "erledigt"].map(s => [s, t("rst_" + s)]), r?.status || "offen") };
  const zeile = (l, x) => el("div", { class: "feld" }, el("label", {}, l), el("div", {}, x));
  const knopf = el("button", { class: "knopf haupt", type: "button" }, t("speichern"));
  const hg = dialog(r ? `R${r.id}` : t("rs_neu"), zeile(t("rs_titel"), f.titel), zeile(t("rs_ursache"), f.ursache), zeile(t("rs_wirkung"), f.wirkung),
    zeile(t("rs_wahrscheinlichkeit"), f.w), zeile(t("rs_auswirkung"), f.a), zeile(t("rs_strategie"), f.strategie), zeile(t("rs_massnahme"), f.massnahme),
    zeile(t("rs_verantwortlich"), f.verantwortlich), zeile(t("rs_ausloeser"), f.ausloeser), zeile(t("k_status"), f.status),
    el("div", { class: "aktionen" }, knopf, el("button", { class: "knopf", type: "button", onclick: () => hg.remove() }, t("abbrechen"))));
  knopf.addEventListener("click", async () => {
    try { await schicken("/api/plan/risiko", { id: r?.id ?? null, titel: f.titel.value.trim(), ursache: f.ursache.value.trim(), wirkung: f.wirkung.value.trim(),
      wahrscheinlichkeit: Number(f.w.value), auswirkung: Number(f.a.value), strategie: f.strategie.value || null, massnahme: f.massnahme.value.trim(),
      verantwortlich: f.verantwortlich.value.trim(), ausloeser: f.ausloeser.value.trim(), status: f.status.value });
      hg.remove(); zeige("planung", true); } catch (e) { toast(t("fehler", { x: e.message }), true); }
  });
}

/* Rückblick je Bogen: gut / schlecht / Maßnahme / gelernt; Maßnahme → Aufgabe oder Beschluss */
function rueckblickDialog(b) {
  const arten = ["gut", "schlecht", "massnahme", "gelernt"];
  const liste = b.rueckblick || [];
  const art = el("select", {}, arten.map(a => el("option", { value: a }, t("rb_" + a))));
  const text = el("textarea", { rows: 2, placeholder: t("rb_ph") });
  const neu = el("button", { class: "knopf haupt", type: "button" }, t("rb_hinzu"));
  const uebernehmen = async (r, als) => {
    try { const x = await schicken("/api/plan/uebernehmen", { id: r.id, als }); toast(t(als === "aufgabe" ? "rb_als_aufgabe" : "rb_als_beschluss", { n: x.nr ?? "" }));
      hg.remove(); zeige("planung", true); } catch (e) { toast(t("fehler", { x: e.message }), true); } };
  const spalte = a => el("div", { class: "rb-spalte rb-" + a }, el("h4", {}, t("rb_" + a), el("span", { class: "anzahl" }, liste.filter(r => r.art === a).length)),
    ...liste.filter(r => r.art === a).map(r => el("div", { class: "rb-eintrag" }, el("div", {}, r.text),
      el("div", { class: "sehrleise", style: "font-size:12px" }, `${r.von} · ${seit(r.zeit_utc)}`,
        r.aufgabe_id ? ` · → A${r.aufgabe_id}` : "", r.beschluss_id ? ` · → B${r.beschluss_id}` : ""),
      a === "massnahme" && !r.aufgabe_id && !r.beschluss_id ? el("div", { style: "display:flex;gap:6px;margin-top:4px;flex-wrap:wrap" },
        el("button", { class: "klein-knopf", type: "button", onclick: () => uebernehmen(r, "aufgabe") }, t("rb_zu_aufgabe")),
        el("button", { class: "klein-knopf", type: "button", onclick: () => uebernehmen(r, "beschluss") }, t("rb_zu_beschluss"))) : null)));
  const hg = dialog(t("rb_titel", { b: bogenNr(b.id), x: b.titel }), el("p", { class: "leise", style: "margin-top:0" }, t("rb_h")),
    el("div", { class: "rb-raster" }, arten.map(spalte)),
    el("div", { class: "rb-neu" }, art, text, neu));
  neu.addEventListener("click", async () => {
    if (!text.value.trim()) return;
    try { await schicken("/api/plan/rueckblick", { bogen: b.id, art: art.value, text: text.value.trim() }); hg.remove(); zeige("planung", true); }
    catch (e) { toast(t("fehler", { x: e.message }), true); }
  });
}


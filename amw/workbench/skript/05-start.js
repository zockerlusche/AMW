/* --- Start --------------------------------------------------------------------------------- */
/* A1657 Übersicht (Marcel 14.11., Mockup D1066): vier Karten – „Für dich“ (nur, wo du etwas tun musst), „Läuft gerade“,
   „Stand“ (aktive Meilensteine), „Zustand“ (Dienst, Arbeitsspeicher, Platte, Synchronisierung, Kosten). Alles Weitere einen Klick tiefer. */
/* Zustand des Dienstes – eine Quelle für Kopfzeile und Karte „Zustand“ (TL P226): Störung eines Teils, sonst die
   Hauptschleife aus dem Herzschlag. [Farbe, Wort] */
function dienstLage(d) {
  const z = d.uebersicht?.dienst;
  if ((d.dienst_rot || []).length) return ["rot", t("uk_dienst_stoerung")];
  if (z === "aus") return ["", t("uk_sync_aus")];
  return [z === "gelb" ? "bernstein" : "gruen", t("ls_laeuft")];
}
const dauerKurz = s => { s = Math.round(s || 0); return s >= 3600 ? `${Math.floor(s / 3600)} h ${String(Math.floor(s % 3600 / 60)).padStart(2, "0")} min` : s >= 60 ? `${Math.floor(s / 60)} min` : `${s} s`; };
function ueKarte(schluessel, n, ...inhalt) {
  return el("section", { class: "ue-karte" + (schluessel === "uk_fuer_dich" && n ? " dran" : ""), id: "ue-" + schluessel.slice(3) },
    el("h3", {}, t(schluessel), n && schluessel !== "uk_fuer_dich" ? el("span", { class: "ue-zahl" }, String(n)) : null), ...inhalt);
  /* A1990 (F5370 Änderung 2, TH156 Regel 6): „Für dich“ ohne Zahl im Kopf – die Anzahl steht an der Gruppe (Fragen n) */
}
function ueZeile(ref, text, knopf, tun, extra) {
  return el("div", { class: "ue-zeile" }, ref ? el("span", { class: "ref" }, ref) : null, el("span", { class: "ue-text" }, text, extra || null),
    knopf ? el("button", { class: "klein-knopf ue-knopf", type: "button", onclick: tun }, knopf) : null);
}
/* A1867 (D1258 §6b): die AMW schlägt einen Start vor – „X starten?“ mit Grund; starten nur nach deiner Bestätigung am PC */
function startvorschlagZeile(v) {
  const grund = t("sv_" + v.grund, { a: v.aufgabe, x: v.text.length > 80 ? v.text.slice(0, 80) + " …" : v.text });
  const tun = async (weg, daten, frage, ok) => { if (frage && !confirm(frage)) return;
    try { const r = await schicken(weg, daten); toast(ok ? ok(r) : r.text); zeige("start", true); } catch (e) { toast(t("fehler", { x: e.message }), true); } };
  return el("div", { class: "ue-zeile sv-zeile", "data-k": v.kennung }, el("span", { class: "ref" }, v.kennung),
    el("span", { class: "ue-text" }, el("b", {}, t("sv_frage", { x: v.kennung })), " ", el("span", { class: "leise" }, grund)),
    API ? el("span", { class: "sehrleise" }, t("sv_nur_pc")) : el("span", { class: "sv-knoepfe" },
      el("button", { class: "klein-knopf ue-knopf", type: "button", onclick: () => tun("/api/agent/start", { kennung: v.kennung, vorschlag: grund },
        t("sv_bestaetigen_frage", { x: v.kennung, g: grund })) }, t("sv_starten")),
      el("button", { class: "klein-knopf", type: "button", onclick: () => tun("/api/agent/startvorschlag_nein", { kennung: v.kennung }, null,
        () => t("sv_nein_ok", { x: v.kennung })) }, t("sv_nicht_jetzt"))));
}
/* A1928 (TH158): ein fertiger Meilenstein wartet auf deine Abnahme – danach veröffentlicht die AMW (Push, GitHub-Release) */
function abnahmeZeile(b) {
  const tun = async () => { if (!confirm(t("ab_frage", { m: b.nr, x: b.titel }))) return;
    try { const r = await schicken("/api/bogen/abnehmen", { bogen: b.id }); toast(r.text); zeige("start", true); }
    catch (e) { toast(t("fehler", { x: e.message }), true); } };
  return el("div", { class: "ue-zeile ab-zeile", "data-bogen": b.id }, el("span", { class: "ref" }, `M${b.nr}`),
    el("span", { class: "ue-text" }, el("b", {}, t("ab_fertig", { x: b.titel })), " ", el("span", { class: "leise" }, t("ab_grund"))),
    API ? el("span", { class: "sehrleise" }, t("ab_nur_pc")) : el("button", { class: "klein-knopf ue-knopf", type: "button", onclick: tun }, t("ab_knopf")));
}
/* A1939 (K3): eine Aufgabe hängt an einem Urteil und ist bereit – ein Ja genügt, den Status setzt die AMW */
function urteilZeile(x) {
  const tun = async ja => { let grund = null;
    if (ja) { if (!confirm(t("ua_frage", { a: x.id, x: x.titel }))) return; }
    else { grund = prompt(t("ua_zurueck_frage", { a: x.id })); if (!grund || !grund.trim()) return; }
    try { const r = await schicken("/api/aufgabe/abnehmen", { aufgabe: x.id, ja, grund }); toast(t(r.text === "fertig" ? "ua_ok" : "ua_ok_zurueck", { a: x.id }));
      zeige("start", true); } catch (e) { toast(t("fehler", { x: e.message }), true); } };
  const g = t("ua_" + x.grund_art, { r: x.grund_ref }) + (x.offen.length ? " · " + t(x.offen.length === 1 ? "ua_offen1" : "ua_offen", { n: x.offen.length }) : "");
  return el("div", { class: "ue-zeile ua-zeile", "data-aufgabe": x.id }, el("span", { class: "ref" }, `A${x.id}`),
    el("span", { class: "ue-text" }, el("b", {}, t(x.pruefpunkt ? "ua_pruefpunkt" : "ua_bereit", { x: x.titel })), " ", el("span", { class: "leise" }, g)),   /* A2096 */
    API ? el("span", { class: "sehrleise" }, t("ua_nur_pc")) : el("span", { class: "sv-knoepfe" },
      el("button", { class: "klein-knopf ue-knopf", type: "button", onclick: () => tun(true) }, t("ua_ja")),
      el("button", { class: "klein-knopf", type: "button", onclick: () => tun(false) }, t("ua_zurueck")),
      el("a", { class: "verweis", style: "margin-left:6px", onclick: () => aufgabeDialog(x.id) }, t("uk_ansehen"))));
}
function uebersichtKarten(d) {
  const u = d.uebersicht || {}, pw = d.planung_wartet || { spezifikationen: [], plaene: [], eigene: [] };
  const kurz = (x, n) => x && x.length > n ? x.slice(0, n) + " …" : (x || "");
  /* Für dich */
  const fragenN = Math.max(d.fragen_anzahl ?? 0, (d.fragen || []).length);   /* A1993: alle offenen (geladen sind höchstens 20) */
  const fragen = [...(d.fragen || [])].sort((a, b) => (b.blockiert ? 1 : 0) - (a.blockiert ? 1 : 0) || String(a.zeit_utc).localeCompare(String(b.zeit_utc)));
  const seit = z => { const m = Math.max(0, Math.floor((Date.now() - Date.parse(z)) / 60000));    /* A1990: neu · min · h · Tage */
    return m < 1 ? t("uk_seit_neu") : m < 60 ? t("uk_seit_min", { n: m }) : m < 1440 ? t("uk_seit_h", { n: Math.floor(m / 60) }) : t("uk_seit_t", { n: Math.floor(m / 1440) }); };
  const frageZeile = f => el("div", { class: "ue-zeile", "data-frage": f.id, onclick: () => zeige("fragen") },
    el("span", { class: "ref" }, `F${f.id}`), el("span", { class: "ue-text" }, kurz(f.kurz, 150)),
    f.blockiert ? el("span", { class: "etikett bernstein" }, t("blockiert")) : el("span", { class: "ue-frage-zeit" }, seit(f.zeit_utc)));
  const fragenGruppe = fragen.length ? el("div", { class: "ue-gruppe", id: "ue-fragen" },     /* A1990: eine Gruppe, je Frage eine Zeile */
    el("h4", {}, t("uk_fragen_gruppe"), el("b", {}, String(fragenN))), fragen.slice(0, 6).map(frageZeile)) : null;
  const dran = [
    ...pw.spezifikationen.map(x => ueZeile(bogenRef(x.bogen_id), t("pl_spec_frei", { b: bogenNr(x.bogen_id), x: x.titel, teil: t("teil_" + x.teil), v: x.version }),
      t("uk_ansehen"), () => { zustand.planReiter = "zeitleiste"; zeige("planung"); })),
    ...pw.plaene.map(p => ueZeile(`A${p.id}`, t("pl_plan_frei", { a: p.id, x: p.titel, ag: p.agent || "–" }), t("uk_ansehen"), () => zeige("planung"))),
    ...pw.eigene.map(a => ueZeile(`A${a.id}`, a.titel, t("uk_oeffnen"), () => aufgabeDialog(a.id))),
    ...(d.startvorschlaege || []).map(startvorschlagZeile),
    ...(d.themen_fuer_dich || []).map(x => ueZeile(`TH${x.id}`, x.name, t("uk_oeffnen"), () => { zustand.themaOffen = x.id; zeige("themen"); },
      el("span", { class: "th-status " + x.status, style: "margin-left:8px" }, t("th2_" + x.status)))),
    ...(d.aufgaben_zur_abnahme || []).map(urteilZeile),                                                 /* A1939: bereit → Ja */
    ...(d.zur_abnahme || []).map(abnahmeZeile)];                                                    /* A1928: fertig → abnehmen */
  const anzahl = fragen.length + pw.spezifikationen.length + pw.plaene.length + pw.eigene.length + (d.startvorschlaege || []).length
    + (d.themen_fuer_dich || []).length + (d.aufgaben_zur_abnahme || []).length + (d.zur_abnahme || []).length;
  const frisch = (d.an_dich || []).filter(n => n.zaehlt), aelterIds = (d.an_dich || []).filter(n => n.abgelegt).map(n => n.id);
  const zuNachrichten = () => { try { localStorage.setItem(ablage("amw-nr"), "eingang"); } catch (e) {} zeige("nachrichten"); };
  const fuer = ueKarte("uk_fuer_dich", anzahl,
    fragenGruppe,
    dran.length ? el("div", { class: "ue-liste" }, dran) : fragenGruppe ? null : el("p", { class: "ue-leer" }, t("nichts_offen")),
    fragenN > 6 ? el("a", { class: "verweis ue-mehr", onclick: () => zeige("fragen") }, t("uk_mehr_fragen", { n: fragenN - 6 })) : null,
    frisch.length || aelterIds.length ? el("div", { class: "ue-fuss" },
      frisch.length ? el("a", { class: "verweis nr-start", onclick: zuNachrichten }, t(frisch.length === 1 ? "uk_nachricht1" : "uk_nachrichten", { n: frisch.length })) : null,
      aelterIds.length ? el("span", { class: "sehrleise", title: t("an_dich_alt_h") }, t("an_dich_alt", { n: aelterIds.length })) : null,
      aelterIds.length ? el("button", { class: "klein-knopf", type: "button", onclick: async () => {
        try { await schicken("/api/gelesen", { ids: aelterIds }); kopfAktualisieren(); zeige("start", true); } catch (x) { toast(t("fehler", { x: x.message }), true); } } },
        t("an_dich_alt_weg")) : null) : null);
  /* Läuft gerade */
  const aktiv = (d.agenten || []).filter(a => a.zustand === "aktiv");
  const laeufe = u.laeufe || [], r = d.rechner || {}, fremd = Math.max(0, (r.warten || 0) - (r.eigene_warten || 0));
  const laeuft = ueKarte("uk_laeuft", 0, aktiv.length || laeufe.length || r.warten ? el("div", { class: "ue-liste" },
    aktiv.map(a => el("div", { class: "ue-zeile klickbar", onclick: () => agentDialog(a.kennung) }, el("span", { class: "punkt bernstein" }),
      el("b", {}, a.kennung), el("span", { class: "ue-text leise" }, "→ " + (a.gerade_aufgabe ? `A${a.gerade_aufgabe} ` : "") + kurz(a.gerade || t("tm_keine"), 90)))),
    laeufe.map(l => el("div", { class: "ue-zeile klickbar", onclick: () => zeige("betrieb") }, el("span", { class: "punkt gruen" }),
      el("b", {}, `L${l.id}`), el("span", { class: "ue-text leise" }, [l.agent, kurz(l.beschreibung, 70), t("uk_seit", { x: seit(l.start_utc) })].filter(Boolean).join(" · ")))),
    r.warten ? el("div", { class: "ue-zeile" }, el("b", {}, t(r.warten === 1 ? "uk_wartet1" : "uk_warten", { n: r.warten })),
      el("span", { class: "ue-text leise" }, fremd ? t("uk_warten_fremd", { n: fremd }) : t("uk_warten_eigen"))) : null)
    : el("p", { class: "ue-leer" }, t("uk_ruhig")));
  /* Stand */
  const boegen = u.boegen || [];
  const stand = ueKarte("uk_stand", 0, boegen.length ? el("div", { class: "ue-liste" }, boegen.map(b => {
      const g = b.gesamt - (b.verworfen || 0), f = b.fertig || 0;
      return el("div", { class: "ue-bogen klickbar", onclick: () => zuSchritt(null, b.id) },
        el("div", { class: "ue-zeile" }, el("span", { class: "ref" }, bogenRef(b.id)), el("b", { class: "ue-text" }, b.titel),
          b.zieldatum ? el("span", { class: "sehrleise" }, t("uk_ziel", { x: datumKurz(b.zieldatum) })) : null),
        el("div", { class: "ue-spur" }, el("i", { style: `width:${g ? Math.round(100 * f / g) : 0}%` })),
        el("div", { class: "sehrleise" }, t("sj_fertig", { f, g }))); }))
    : el("p", { class: "ue-leer" }, t("sj_kein_aktiv")),
    el("div", { class: "ue-fuss" }, u.ohne_bogen ? el("span", { class: "sehrleise" }, t(u.ohne_bogen === 1 ? "uk_ohne1" : "uk_ohne", { n: u.ohne_bogen })) : null,
      el("a", { class: "verweis", onclick: () => { zustand.planReiter = "zeitleiste"; zeige("planung"); } }, t("uk_zur_planung"))));
  /* Zustand */
  const kachel = (farbe, titel, wert, tun) => el("div", { class: "ue-kachel" + (tun ? " klickbar" : ""), onclick: tun || null },
    el("div", { class: "leise" }, el("span", { class: "punkt " + farbe }), titel), el("b", {}, wert));
  const dienstRot = (d.dienst_rot || []).length, online = d.online;
  const pl = (r.platte || [])[0], sp = d.speicher?.frei;
  const sy = u.sync;
  const probleme = (d.warnungen || []).length + dienstRot + (pl ? 1 : 0);
  const tk = d.token;
  const zust = ueKarte("uk_zustand", 0,
    el("div", { class: "ue-kacheln" },
      online ? kachel(online.pc_frisch ? "gruen" : "bernstein", t("uk_pc"), online.pc_frisch ? t("uk_pc_da") : seit(online.pc_gesehen_utc))
        : (() => { const [f, x] = dienstLage(d); return kachel(f, t("uk_dienst"), x, () => zeige("betrieb")); })(),
      sp == null ? null : kachel(sp < 4 ? "rot" : sp < 8 ? "bernstein" : "gruen", t("uk_speicher"), t("uk_gb_frei", { n: zahlKurz(sp) })),
      kachel(pl ? (pl.stufe === "rot" ? "rot" : "bernstein") : "gruen", pl ? t("uk_platte_x", { x: pl.laufwerk }) : t("uk_platte"),
        pl ? t("uk_prozent_frei", { p: zahlKurz(pl.frei_prozent) }) : t("uk_platte_ok"), () => zeige("einstellungen")),
      kachel(!sy ? "" : sy.zustand === "rot" ? "rot" : sy.zustand === "gelb" ? "bernstein" : "gruen", t("uk_sync"),
        !sy ? t("uk_sync_aus") : typeof sy === "string" ? t("uk_sync_" + (sy === "rot" ? "stoerung" : "an")) : seit(sy.zeit_utc))),
    el("div", { class: "ue-fuss sehrleise" }, [u.kosten_heute != null ? t("uk_kosten", { x: dollar(u.kosten_heute) }) : null,
      tk?.wert != null ? t("uk_woche", { p: Math.round(tk.wert) }) : null,
      probleme ? t(probleme === 1 ? "uk_problem1" : "uk_probleme", { n: probleme }) : t("uk_keine_probleme")].filter(Boolean).join(" · "),
      el("a", { class: "verweis", style: "margin-left:auto", onclick: () => zeige("betrieb") }, t("uk_zum_betrieb"))));
  return el("div", { class: "ue-raster" }, fuer, laeuft, stand, zust);
}
async function sichtStart() {
  await kopfAktualisieren(); const d = zustand.start;
  if (!d) { if (zustand.startFehler) rahmen(t("n_start")).append(el("div", { class: "leer" }, zustand.startFehler)); return; }   /* A1998 */
  const m = rahmen(t("n_start"), el("span", { class: "leise" }, t("stand", { t: zeit(d.zeit) })));
  /* „Seit du weg warst“: letzter Besuch je Gerät (localStorage); in dieser Sitzung bleibt der Wert stehen */
  let seitBesuch = null;
  try {
    if (sessionStorage.getItem(ablage("amw-seit")) === null) { sessionStorage.setItem(ablage("amw-seit"), gemerkt("amw-besuch") || ""); }
    localStorage.setItem(ablage("amw-besuch"), new Date().toISOString().slice(0, 19) + "Z");
    seitBesuch = sessionStorage.getItem("amw-seit") || null;
  } catch (e) {}
  if (seitBesuch && Date.now() - new Date(seitBesuch) > 30 * 60 * 1000) {
    holen("/api/seit?ab=" + encodeURIComponent(seitBesuch)).then(z => {
      const band = el("div", { class: "band-seit" }, el("b", {}, t("seit_titel", { x: seit(seitBesuch) })),
        el("div", {}, [z.boegen_fertig ? t("seit_boegen", { n: z.boegen_fertig }) : null, t("seit_erledigt", { n: z.erledigt }),
          t("seit_laeufe", { n: z.laeufe }), t("seit_pruefungen", { g: z.gruen, r: z.rot }), t("seit_fragen", { n: z.fragen_neu }),
          z.beschluesse ? t("seit_beschluesse", { n: z.beschluesse }) : null].filter(Boolean).join(" · ")),
        z.highlights.length ? el("div", { class: "sehrleise" }, z.highlights.slice(0, 3).map(h => `A${h.id} ` + (h.titel.length > 60 ? h.titel.slice(0, 60) + " …" : h.titel)).join(" · ")) : null,
        el("span", { style: "display:flex;gap:8px;margin-top:4px" },
          el("button", { class: "klein-knopf", type: "button", onclick: () => zeige("verlauf") }, t("seit_verlauf")),
          el("button", { class: "klein-knopf", type: "button", onclick: () => { try { sessionStorage.setItem("amw-seit", ""); } catch (e) {} band.remove(); } }, t("seit_weg"))));
      m.querySelector(".kopf")?.after(band);
    }).catch(() => {});                                     /* noch keine Daten (online: erster Abgleich) – dann eben ohne */
  }
  if (d.halt.length) m.append(el("div", { class: "band-halt" }, el("b", {}, t("halt_an").toUpperCase()),
    el("div", {}, d.halt.map(h => `#${h.id} ${h.gilt_fuer === "alle" ? t("halt_band") : h.gilt_fuer} · ${h.von}: ${h.text} (${seit(h.seit_utc)})`).join(" | ")),
    el("button", { class: "knopf", style: "margin-left:auto", onclick: () => weiterGeben() }, t("weiter"))));
  if ((d.dienst_rot || []).length) m.append(el("div", { class: "band-halt" },      /* Dienst-Teil steht (A1655) */
    el("b", {}, t("gs_band", { x: d.dienst_rot.map(x => t("gs_k_" + x)).join(", ") })),
    el("button", { class: "klein-knopf", type: "button", style: "margin-left:auto", onclick: () => zeige("betrieb") }, t("gs_zum_betrieb"))));
  const sz = d.schirm, sl = sz?.laeufe || [];
  if (sz && (sz.frei || sl.length)) {                       /* frei: immer sichtbar; zu: nur, wenn Läufe darauf warten */
    const laeuft = sl.filter(l => l.status === "laeuft"), wartet = sl.filter(l => l.status === "angemeldet");
    m.append(el("div", { class: "band-schirm" + (sz.frei ? " frei" : "") }, el("b", {}, t(sz.frei ? "schirm_frei" : "schirm_zu_b")),
      el("div", {}, [sz.seit_utc ? t("schirm_seit", { x: seit(sz.seit_utc) }) : null, sz.bis_utc ? t("schirm_bis", { x: zeit(sz.bis_utc) }) : null,
        sz.grund, laeuft.length ? t("schirm_laeuft", { x: laeuft.map(l => `L${l.id} ${l.agent}`).join(", ") }) : null,
        wartet.length ? t("schirm_wartet", { n: wartet.length }) : null].filter(Boolean).join(" · ")),
      el("button", { class: "klein-knopf", type: "button", title: t("schirm_zum_leitstand_h"),
        onclick: () => document.getElementById("leitstand")?.scrollIntoView({ behavior: "smooth", block: "center" }) }, t("schirm_zum_leitstand"))));
  }
  const nt = d.naechster_test;                              /* Terminplaner: nächster Testtermin mit Frist und Ampel */
  if (nt) m.append(el("div", { class: "band-termin" + (nt.ampel === "rot" ? " rot" : "") }, el("b", {}, t("tm_naechster").toUpperCase()),
    el("div", {}, [`${tmZeit(nt.am_utc)} · ${nt.titel}`, nt.frist_utc ? t("tm_frist", { x: tmZeit(nt.frist_utc) }) : null,
      nt.ampel ? t("tm_ampel", { b: bogenNr(nt.bogen_id), a: t("ampel_" + nt.ampel) }) : null,
      nt.bereit ? t("tm_bereit") : null].filter(Boolean).join(" · ")),
    el("button", { class: "klein-knopf", type: "button", onclick: () => { zustand.planReiter = "termine"; zeige("planung"); } }, t("tm_alle"))));
  const ohne = (d.unangemeldet || []).filter(u => !u.doppelt);
  if (ohne.length) m.append(el("div", { class: "band-halt" }, el("b", {}, t("nicht_angemeldet")),
    el("div", {}, ohne.map(u => `${u.kennung || "?"} · ${t("sitzung_pid", { s: u.sitzung, p: u.pid })} · ${u.ordner}`).join(" | ")),
    el("span", { class: "leise" }, t("nicht_angemeldet_h")), hilfeKnopf("agenten")));
  /* Neustart per Startskript, das alte Fenster ist noch offen: kein „anmelden“-Rat (das holte die Sitzung zurück) */
  for (const u of (d.unangemeldet || []).filter(u => u.doppelt)) m.append(el("div", { class: "band-halt zwei-fenster" },
    el("b", {}, t("zf_titel", { x: u.kennung })), el("div", {}, `${t("zf_alt")}: ${t("sitzung_pid", { s: u.sitzung, p: u.pid })} · ${u.ordner}`),
    el("span", { class: "leise" }, t("zf_h")), (d.agenten || []).some(a => a.kennung === u.kennung)
      ? el("button", { class: "klein-knopf", type: "button", title: t("band_ansehen_h", { x: u.kennung }), onclick: () => agentDialog(u.kennung) }, t("band_ansehen", { x: u.kennung })) : null));
  /* Reihenfolge nach Dringlichkeit: Warnungen → Fragen an dich → Agenten → Nachrichten (gekürzt) */
  if ((d.warnungen || []).length) m.append(el("div", { class: "band-warn" }, el("b", {}, t("achtung").toUpperCase()),
    d.warnungen.map(w => el("div", { class: "band-zeile" }, el("span", {}, w.text),     /* je Warnung ein Sprung zu dem, den sie betrifft */
      w.an && (d.agenten || []).some(a => a.kennung === w.an)
        ? el("button", { class: "klein-knopf", type: "button", title: t("band_ansehen_h", { x: w.an }), onclick: () => agentDialog(w.an) }, t("band_ansehen", { x: w.an })) : null))));
  m.append(uebersichtKarten(d));                          /* A1657: Für dich · Läuft gerade · Stand · Zustand */
  m.append(el("h2", {}, t("tm_titel")));
  m.append(teamAnsicht(d));
  m.append(leitstand(d));

}
/* Aktionsmenü – ein Baustein: eintraege = Liste aus { titel } (Überschrift), "-" (Trennlinie) oder
   { text, tun, hinweis, rot, aus } (Befehl; aus = sichtbar, aber gerade nicht möglich). Klick daneben oder Esc schließt. */
/* Startbefehl zum Kopieren (A1610): Angaben, letzte Sitzung, „Fortsetzen“ und „Neu starten“ für PowerShell oder cmd */
const darfStartbefehl = () => !API || zustand.start?.online?.ich?.rolle === "system_admin";
const darfBenutzer = () => !API || ["projekt_admin", "system_admin"].includes(zustand.start?.online?.ich?.rolle);   // A1615 a
function startbefehlBlock(s) {
  if (!s) return null;
  if (s.grund) return el("p", { class: "leise", style: "margin:0" }, t("sb_grund_" + (s.grund === "kein_ordner" ? "ordner" : "weise")));
  let shell = gemerkt("amw-sb-shell") === "cmd" ? "cmd" : "powershell";
  const zeilen = el("div", { class: "sb-zeilen" });
  const kopieren = async (text, knopf) => {
    try { await navigator.clipboard.writeText(text); }
    catch (e) { const ta = el("textarea", { style: "position:fixed;opacity:0" }, text); document.body.append(ta); ta.select(); document.execCommand("copy"); ta.remove(); }
    const alt = knopf.textContent; knopf.textContent = t("sb_kopiert"); setTimeout(() => { knopf.textContent = alt; }, 1500); };
  const zeichnen = () => {
    zeilen.replaceChildren(...[["fortsetzen", s.befehle[shell].fortsetzen], ["neu", s.befehle[shell].neu]].map(([art, text]) =>
      el("div", { class: "sb-zeile" }, el("div", { class: "sb-kopf" }, el("b", {}, t("sb_" + art)),
          el("span", { class: "sehrleise" }, art === "fortsetzen" ? (s.letzte ? `${t("sb_sitzung")} ${s.letzte.sitzung.slice(0, 8)} · ${seit(s.letzte.zuletzt_utc)}` : "")
            : t("sb_neu_h", { x: s.neue_sitzung.slice(0, 8) })),
          text ? el("button", { class: "klein-knopf", type: "button", style: "margin-left:auto", onclick: e => kopieren(text, e.currentTarget) }, t("sb_kopieren")) : null),
        text ? el("pre", { class: "sb-befehl mono" }, text) : el("p", { class: "sehrleise", style: "margin:2px 0" }, t("sb_keine_sitzung")))));
    umschalter.querySelectorAll("button").forEach(b => b.classList.toggle("an", b.dataset.s === shell)); };
  const umschalter = el("div", { class: "reiter sb-umschalter" }, ["powershell", "cmd"].map(x => el("button", { type: "button", "data-s": x,
    onclick: () => { shell = x; try { localStorage.setItem(ablage("amw-sb-shell"), x); } catch (e) {} zeichnen(); } }, t("sb_" + x))));
  const angabe = (l, w) => w ? el("div", { class: "sb-angabe" }, el("span", { class: "leise" }, l), el("span", { class: "mono" }, w)) : null;
  zeichnen();
  return el("div", { class: "sb" },
    el("div", { class: "sb-angaben" }, angabe(t("pr_ordner"), s.ordner), angabe(t("pr_zusatz"), (s.zusatzordner || []).join("; ")),
      angabe(t("pr_modell"), s.modell || t("pr_vorgabe")), angabe(t("pr_denkstufe"), s.denkstufe || t("pr_vorgabe")), angabe(t("pr_rechte"), t("pr_r_" + s.rechte)),
      angabe(t("sb_letzte"), s.letzte ? `${s.letzte.sitzung} · ${t("sb_zuletzt")} ${zeit(s.letzte.zuletzt_utc)}` : t("sb_nie"))),
    umschalter, zeilen, el("p", { class: "sehrleise", style: "margin:6px 0 0;font-size:12px" }, t("sb_h")));
}
async function startbefehlDialog(k) {
  let d; try { d = await abrufen("/api/einstellungen"); } catch (e) { toast(t("fehler", { x: e.message }), true); return; }
  const a = (d.agenten || []).find(x => x.kennung === k);
  if (!a?.start) { toast(t("sb_fehlt"), true); return; }
  let e = null; try { e = (await abrufen("/api/agent?kennung=" + encodeURIComponent(k))).empfehlung; } catch (f) {}
  dialog(t("sb_titel", { x: k }), e && e.passt === false ? el("p", { class: "bernstein-text", style: "margin-top:0" },
    t("sb_empf", { x: modellStufe(e.modell, e.denkstufe), y: modellStufe(e.profil.modell, e.profil.denkstufe) })) : null, startbefehlBlock(a.start));
}
function menue(knopf, eintraege) {
  const offen = knopf.classList.contains("auf");
  document.querySelector(".menue")?.remove(); document.querySelectorAll(".auf[aria-haspopup]").forEach(b => b.classList.remove("auf"));
  if (offen) return;
  const zu = () => { m.remove(); knopf.classList.remove("auf"); document.removeEventListener("click", ausserhalb, true); document.removeEventListener("keydown", taste);
    $("#inhalt").removeEventListener("scroll", zu); };
  const ausserhalb = ev => { if (!m.contains(ev.target) && ev.target !== knopf) zu(); };
  const taste = ev => { if (ev.key === "Escape") { zu(); knopf.focus(); } };
  const m = el("div", { class: "menue", role: "menu" }, eintraege.filter(Boolean).map(x => x === "-" ? el("hr") : x.titel ? el("div", { class: "mt" }, x.titel)
    : el("button", { type: "button", role: "menuitem", class: x.rot ? "rot" : null, disabled: x.aus ? "" : null,
        onclick: ev => { ev.stopPropagation(); zu(); x.tun(); } }, x.text, x.hinweis ? el("small", {}, x.hinweis) : null)));
  document.body.append(m); knopf.classList.add("auf");
  const r = knopf.getBoundingClientRect();
  m.style.left = Math.max(8, Math.min(r.left, innerWidth - m.offsetWidth - 8)) + scrollX + "px";
  m.style.top = (r.bottom + m.offsetHeight + 8 > innerHeight && r.top > m.offsetHeight ? r.top - m.offsetHeight - 4 : r.bottom + 4) + scrollY + "px";
  setTimeout(() => { document.addEventListener("click", ausserhalb, true); document.addEventListener("keydown", taste); $("#inhalt").addEventListener("scroll", zu, { passive: true }); }, 0);
  m.querySelector("button:not([disabled])")?.focus();
}
/* Befehle zu einem Agenten: schreiben/lesen – steuern (anhalten überall; Sitzung starten/beenden nur am PC) – Profil */
function agentMenue(a, knopf) {
  const d = zustand.start || {}, k = a.kennung, lebt = a.zustand === "aktiv", ruht = a.zustand === "ruht";
  const eigenerHalt = (d.halt || []).some(h => h.gilt_fuer === k), ende = (d.ende || []).some(x => x.kennung === k);
  const tun = async (weg, daten, frage, ok) => { if (frage && !confirm(frage)) return;
    try { const r = await schicken(weg, daten); if (!r.unterwegs) toast(ok ? ok(r) : r.text || t("gespeichert")); zeige(zustand.sicht, true); setTimeout(() => zeige(zustand.sicht, true), 4000); }
    catch (x) { toast(t("fehler", { x: x.message }), true); } };
  menue(knopf, [{ titel: t("m_titel", { x: k }) },
    { text: t("m_nachricht"), tun: () => nachrichtDialog(k) },
    a.zustand && !a.chat ? { text: t("m_gespraech"), tun: () => agentDialog(k, "gespraech") } : null,
    { text: t("m_uebersicht"), tun: () => agentDialog(k) },
    "-", { titel: t("m_steuern") },
    eigenerHalt ? { text: t("m_weiter1"), tun: () => tun("/api/weiter", { fuer: k }, null, r => t("halt_aufgehoben", { n: r.aufgehoben })) }
      : { text: t("m_halt1"), tun: () => tun("/api/halt", { fuer: k, text: t("halt_vom") }, t("m_halt1_frage", { x: k }), () => t("halt_gesetzt")) },
    a.chat ? { text: t("m_chat"), tun: () => {}, aus: true } : !a.startbar ? { text: t("m_kein_ordner"), tun: () => {}, aus: true } : null,
    a.startbar && !API ? { text: t("m_sichern"), hinweis: t("m_sichern_h"), aus: !(lebt || ruht) || ende,
      tun: () => tun("/api/agent/ende", { kennung: k }, t("m_sichern_frage", { x: k }), r => t("m_sichern_ok", { x: zeit(r.bis_utc) })) } : null,
    a.startbar && !API ? { text: t("m_sofort"), hinweis: t("m_sofort_h"), rot: true, aus: !lebt, tun: () => tun("/api/agent/stop", { kennung: k }, t("st_beenden_frage", { x: k })) } : null,
    a.startbar && !API ? { text: t("m_start"), aus: lebt || ruht, tun: () => tun("/api/agent/start", { kennung: k }, t("m_start_frage", { x: k })) } : null,
    a.startbar && !API ? { text: t("m_neu"), aus: lebt || ruht, tun: () => tun("/api/agent/start", { kennung: k, neu: true }, t("st_neu_frage", { x: k })) } : null,
    a.startbar && API ? { text: t("m_nur_pc"), tun: () => {}, aus: true } : null,
    a.startbar && darfStartbefehl() ? { text: t("m_startbefehl"), tun: () => startbefehlDialog(k) } : null,
    "-", { text: t("m_profil"), tun: () => zeige("einstellungen") }]);
}
/* Leitstand: alles Steuerbare an einer Stelle – Arbeit anhalten, Bildschirm, Sitzungen (nur am PC), Wächter (nur am PC) */
function leitstand(d) {
  const feld = (titel, farbe, stand, erkl, ...knoepfe) => el("div", {}, el("div", { class: "lt" }, titel),
    el("div", { class: "stand" }, el("span", { class: "punkt " + farbe }), stand), el("div", { class: "erkl" }, erkl), el("div", { class: "zeile" }, knoepfe));
  const kn = (text, tun, klasse, gesperrt) => el("button", { class: "knopf " + (klasse || ""), type: "button", onclick: tun,
    ...(gesperrt ? { disabled: "disabled", title: gesperrt, "aria-label": `${text} – ${gesperrt}` } : {}) }, text);
  const nurPc = t("nur_pc_knopf");
  const pcTun = async (weg, frage, ok) => { if (!confirm(frage)) return;
    try { const r = await schicken(weg, {}); toast(ok(r)); zeige("start", true); setTimeout(() => zeige(zustand.sicht, true), 5000); }
    catch (x) { toast(t("fehler", { x: x.message }), true); } };
  const eigene = d.agenten.filter(a => a.startbar && a.soll === "an");
  const laufen = eigene.filter(a => a.zustand === "aktiv"), ruhen = eigene.filter(a => a.zustand === "ruht");
  const fehlen = eigene.filter(a => a.zustand !== "aktiv" && a.zustand !== "ruht");
  const ende = d.ende || [], halt = d.halt.length > 0, sz = d.schirm;
  const sitzStand = ende.length ? t("ls_sitz_ende", { n: ende.length, x: zeit(ende[0].bis_utc) })
    : [t(laufen.length === 1 ? "ls_sitz_laufen1" : "ls_sitz_laufen", { n: laufen.length }), ruhen.length ? t("ls_sitz_ruhen", { n: ruhen.length }) : null,
       fehlen.length ? t(fehlen.length === 1 ? "ls_sitz_fehlen1" : "ls_sitz_fehlen", { n: fehlen.length }) : null].filter(Boolean).join(" · ");
  return el("div", { class: "leitstand", id: "leitstand" },
    feld(t("ls_arbeit"), halt ? "rot" : "gruen", t(halt ? "ls_steht" : "ls_laeuft") + (d.eingang ? " · " + t(d.eingang === 1 ? "ls_eingang1" : "ls_eingang", { n: d.eingang }) : ""),
      [t("ls_arbeit_e"), d.eingang ? t("ls_eingang_e") : null].filter(Boolean).join(" "),
      halt ? kn(t("weiter"), () => weiterGeben(), "haupt") : kn(t("halt"), () => haltDialog(), "warn")),
    sz ? feld(t("ls_schirm"), sz.frei ? "bernstein" : "", sz.frei ? t("ls_schirm_frei") + (sz.bis_utc ? " " + t("schirm_bis", { x: zeit(sz.bis_utc) }) : "") : t("ls_schirm_belegt"),
      [sz.kurz_da_bis_utc ? t("ls_schirm_kurz", { x: zeit(sz.kurz_da_bis_utc) }) : null, sz.grund, t("ls_schirm_e")].filter(Boolean).join(" – "),
      kn(t(sz.frei ? "schirm_zumachen" : "schirm_freigeben"), () => schirmDialog(), "", !sz.frei && !darfFreigeben() ? t("schirm_nur_admin_kurz") : null),
      sz.frei ? kn(t("schirm_bis_knopf"), () => schirmDialog(true), "", !darfFreigeben() ? t("schirm_nur_admin_kurz") : null) : null) : null,
    feld(t("ls_sitz"), ende.length || fehlen.length ? "bernstein" : laufen.length ? "gruen" : "", sitzStand, t(API ? "ls_sitz_e_netz" : "ls_sitz_e"),
      kn(t("ls_sichern"), () => pcTun("/api/agent/ende", t("ls_sichern_frage", { n: laufen.length + ruhen.length }),
        r => r.agenten.length ? t("ls_sichern_ok", { n: r.agenten.length, x: zeit(r.bis_utc) }) : t("ls_sichern_keiner")), "", API ? nurPc : null),
      !fehlen.length ? null : kn(t("ls_starten"), () => pcTun("/api/agent/start-fehlende", t("ls_starten_frage", { x: fehlen.map(a => a.kennung).join(", ") }),
        r => t("ls_starten_ok", { n: r.agenten.length, s: r.abstand_s })), "", API ? nurPc : null)),
    feld(t("ls_wacht"), API && !d.online?.pc_frisch ? "bernstein" : "gruen", API ? t(d.online?.pc_frisch ? "s_pc" : "s_pc_weg", { x: seit(d.online?.pc_gesehen_utc) }) : t("ls_wacht_laeuft", { v: d.version }),
      t(API ? "ls_wacht_e_netz" : "ls_wacht_e"), kn(t("ls_wacht_neu"), () => pcTun("/api/dienst/neustart", t("ls_wacht_frage"), () => t("ls_wacht_ok")), "", API ? nurPc : null)),
    rechnerFeld(d.rechner, feld),
    d.token ? (() => { const k = d.token, f = feld(TKZ + " " + t("tk_woche"), k.pause_tage > 0 ? "bernstein" : k.wert >= 90 ? "rot" : "gruen", t("tk_wert", { w: Math.round(k.wert) }),
        [k.tempo ? (k.pause_tage > 0 ? t("tk_leer", { x: tagZeit(k.leer_utc) }) + " \u2013 " + t("tk_pause", { n: zahlKurz(k.pause_tage) }) : t("tk_reicht")) : null,
         k.reset_utc ? t("tk_reset", { x: tagZeit(k.reset_utc) }) : null, k.unsicher ? t("tk_u_" + k.unsicher, { n: k.arbeitstage }) : null, t("tk_konto")].filter(Boolean).join(" · "));
      f.id = "ls-token"; f.title = tokenRechenweg(k);
      f.querySelector(".stand").after(el("div", { class: "tk-balken" }, el("i", { style: `width:${Math.min(100, Math.max(0, k.wert))}%` })));
      return f; })() : null);
}
/* Leitstand › Rechner: schwere Läufe aller Projekte auf diesem PC teilen sich eine Warteschlange. Gezeigt werden nur
   Zahlen – wie viele laufen und warten, wie viele davon aus diesem Projekt, wann der Rechner voraussichtlich frei ist. */
function rechnerFeld(r, feld) {
  if (!r) return null;
  const heim = zustand.start?.heimnetz;                 /* Heimnetz offen (A1643): solange an, steht es hier */
  const stand = !r.laufen && !r.warten ? t("re_frei")
    : [r.laufen ? t(r.laufen === 1 ? "re_laeuft1" : "re_laeuft", { n: r.laufen }) : null, r.warten ? t(r.warten === 1 ? "re_wartet1" : "re_wartet", { n: r.warten }) : null].filter(Boolean).join(" · ");
  const dauer = (r.dauer || []).map(x => t("re_dauer_eintrag", { name: x.name + (x.art === "programm" ? "" : " (" + t("re_art_" + x.art) + ")"), n: zahlKurz(x.gb), x: zeit(x.seit_utc) })).join(", ");
  const knapp = r.platte || [];
  const dl = (r.dauerlaeufe || []).map(x => t((x.eigen ? "re_dl_eigen" : "re_dl_fremd") + (x.ist_gb == null ? "_o" : ""), { l: x.id, a: x.agent, n: zahlKurz(x.ist_gb ?? 0), g: zahlKurz(x.grenze_gb) })).join(", ");   /* A1759 */
  const erkl = [heim ? t("re_heimnetz", { x: heim }) : null, ...knapp.map(l => t("re_platte", { x: l.laufwerk, n: zahlKurz(l.frei_gb), p: zahlKurz(l.frei_prozent) })), dauer ? t("re_dauer", { x: dauer }) : null, dl ? t("re_dauerlaeufe", { x: dl }) : null, t("re_e"), r.eigene_laufen || r.eigene_warten ? t("re_eigene", { a: r.eigene_laufen, b: r.eigene_warten }) : null,
    r.frei_ab_utc ? t("re_frei_ab", { x: zeit(r.frei_ab_utc) }) : null, r.frei_gb != null ? t("re_speicher", { n: zahlKurz(r.frei_gb) }) : null,
    (r.vorrang || []).length ? t("re_vorrang", { x: r.vorrang.map(v => `${v.projekt} ${t("vr_" + v.stufe)}`).join(", ") }) : null].filter(Boolean).join(" ");
  const f = feld(t("re_titel"), knapp.some(l => l.stufe === "rot") ? "rot" : r.warten || knapp.length || heim ? "bernstein" : r.laufen ? "gruen" : "",
    (heim ? t("re_heimnetz", { x: heim }).split(" – ")[0] + " · " : "") + stand + (r.dauer_gb ? " · " + t("re_dauer_kurz", { n: zahlKurz(r.dauer_gb) }) : "") + (knapp.length ? " · " + t("re_platte_kurz", { x: knapp.map(l => l.laufwerk).join(", ") }) : ""), erkl);
  f.id = "ls-rechner";
  /* A1764: wartende Läufe dieses Projekts – vorziehen (nur der Mensch; online nur System-Admin, mit Rückfrage) */
  if ((r.eigene_wartend || []).length && darfFreigeben()) f.querySelector(".zeile")?.replaceWith(el("div", { class: "re-wartend" },
    r.eigene_wartend.map(w => el("div", { class: "re-w" }, el("span", { class: "re-w-text" }, `L${w.id} · ${w.agent} · ${t("re_platz", { p: w.platz })} – ${w.beschreibung}`),
      el("button", { class: "klein-knopf", type: "button", onclick: async () => {
        if (!confirm(t("re_vorziehen_frage", { l: w.id, x: w.beschreibung }))) return;
        try { await schicken("/api/lauf/vorziehen", { lauf: w.id }); toast(t("re_vorgezogen", { l: w.id })); zeige(zustand.sicht, true); }
        catch (e) { toast(t("fehler", { x: e.message }), true); } } }, t("re_vorziehen"))))));
  return f;
}
function zumLeitstand() { Promise.resolve(zustand.sicht === "start" ? null : zeige("start")).then(() => setTimeout(() => $("#leitstand")?.scrollIntoView({ behavior: "smooth", block: "center" }), 60)); }
/* „1204 · A1204 Titel“ → „A1204 Titel“ (alte Titel tragen die Nummer schon) */
function ohneDoppel(x) { const [nr, ...rest] = x.split(" · "); const titel = rest.join(" · "); return titel.startsWith("A" + nr) ? titel : `A${nr} · ${titel}`; }
/* Kachel: Zustand, was er gerade macht (eigene Angabe › laufende Aufgabe › Aufgabe aus der letzten Meldung),
   letzte Meldung, neue offene Nachrichten (Altbestand aus dem alten Bus getrennt). Klick → Übersicht. */
/* Alter der eigenen Angabe (amw taetigkeit): ab 2 h in Bernstein – vielleicht veraltet */
function taetigkeitAlter(utc) {
  const alt = (Date.now() - new Date(utc)) / 1000 > 7200;
  return el("span", { class: alt ? "bernstein-text" : "sehrleise", style: "font-size:11px;white-space:nowrap", title: alt ? t("t_alt") : "" },
    " · " + t("t_seit", { x: seit(utc) }) + (alt ? " ⚠" : ""));
}
/* Zustand eines Agenten in Worten: [Farbe, Text, seit]. Läuft er, genauer aus den Hooks (arbeitet / frei / wartet auf
   Freigabe oder Eingabe / Fehler). Ohne Arbeitsordner ist er ein Chat: Er wird nie gestartet und fehlt darum auch nie. */
function agentZustand(a) {
  const lebt = a.zustand === "aktiv", soll = a.soll === "an";
  const ez = { arbeitet: ["gruen", t("z_arbeitet")], frei: ["gruen", t("z_frei")], wartet_freigabe: ["bernstein", t("z_freigabe")],
               wartet_eingabe: ["bernstein", t("z_eingabe")], fehler: ["rot", t("z_fehler")] }[a.ereignis];
  const dauer = lebt && ez && ["wartet_freigabe", "wartet_eingabe", "fehler"].includes(a.ereignis) && a.ereignis_utc ? seit(a.ereignis_utc) : null;
  if (a.chat && !ez) return [lebt ? "gruen" : "", lebt ? t("tm_chat_da") : a.letzter_puls_utc ? t("tm_chat_zuletzt", { x: zeit(a.letzter_puls_utc) }) : t("tm_chat"), null];   /* A1831 */
  const z = lebt ? (ez || ["gruen", t("laeuft")]) : a.zustand === "ruht" ? ["bernstein", t("abgemeldet")]
    : soll ? ["rot", a.zustand ? t("beendet_soll") : t("nie_gestartet")] : ["", a.soll === "ruht" ? t("ruht") : t("aus")];
  return [z[0], z[1], dauer];
}
/* Kleine Zeichen der Team-Ansicht (als Elemente gebaut, nicht als Text eingesetzt) */
const TM_ZEICHEN = { sitzung: [["rect", { x: 1.5, y: 2.5, width: 13, height: 11, rx: 1.5 }], ["path", { d: "M4.5 6l2.5 2-2.5 2M8.500 10.500h3" }]],
  chat: [["path", { d: "M2 3.5h12v7.5H7l-3 2.5V11H2z" }]], desktop: [["rect", { x: 1.5, y: 2.5, width: 13, height: 8.5, rx: 1.5 }], ["path", { d: "M5.5 14h5M8 11v3" }]], mensch: [["circle", { cx: 8, cy: 5, r: 2.6 }], ["path", { d: "M2.800 14c.6-3 2.600-4.400 5.200-4.400s4.600 1.400 5.200 4.400" }]] };
function tmZeichen(art, titel) {
  const ns = "http://www.w3.org/2000/svg", svg = document.createElementNS(ns, "svg");
  svg.setAttribute("viewBox", "0 0 16 16"); svg.setAttribute("aria-hidden", "true");
  for (const [tag, attr] of TM_ZEICHEN[art]) { const e = document.createElementNS(ns, tag); for (const [k, v] of Object.entries(attr)) e.setAttribute(k, v); svg.append(e); }
  return el("span", { class: "tm-zeichen", title: titel }, svg);
}
const tmWeise = a => tmZeichen(a.arbeitsweise === "chat" || a.chat ? "chat" : a.arbeitsweise === "desktop" ? "desktop" : "sitzung",
  t(a.arbeitsweise === "chat" || a.chat ? "tm_w_chat" : a.arbeitsweise === "desktop" ? "tm_w_desktop" : "tm_w_sitzung"));
/* Lead ist ein Schalter, das Fachgebiet ein eigenes Feld: „Lead“ bzw. das Fachgebiet; fehlt beides, bleibt die Marke weg */
const tmFach = a => a.rolle === "lead" ? el("span", { class: "tm-fach lead", title: a.fachgebiet || null }, t("lead") + (a.fachgebiet ? " · " + a.fachgebiet : ""))
  : a.fachgebiet ? el("span", { class: "tm-fach" }, a.fachgebiet) : null;
const tmKurz = (x, n) => x && x.length > n ? x.slice(0, n) + " …" : x;
const agentName = a => a.co ? [t("co_entwickler"), el("span", { class: "sehrleise tm-kennung" }, " " + a.kennung)] : a.kennung;   /* A2019 */
const tmMehr = a => el("button", { class: "klein-knopf mehr-knopf", type: "button", title: t("m_titel", { x: a.kennung }), "aria-haspopup": "menu",
  onclick: e => { e.stopPropagation(); agentMenue(a, e.currentTarget); } }, "⋯");
const tmOffen = (a, kurz) => a.offen ? el("span", { class: "tm-offen" + (a.offen > 10 ? " viel" : ""), title: t("k_offen_n", { n: a.offen }) + " – " + t("k_offen_h", { n: a.offen_alt || 0 }) },
  kurz ? "✉ " + a.offen : t("k_offen_n", { n: a.offen })) : null;
const tmZustand = a => { const [farbe, text, dauer] = agentZustand(a);
  return el("div", { class: "tm-zustand", title: a.zustand === "aktiv" ? t("k_puls_seit", { t: seit(a.letzter_puls_utc) }) : null }, el("span", { class: "punkt " + farbe }),
    el("span", { class: farbe === "bernstein" ? "bernstein-text" : farbe === "rot" && a.zustand === "aktiv" ? "rot-text" : "" }, text), dauer ? el("span", { class: "sehrleise" }, dauer) : null); };
const tmAufgabe = (a, n) => a.gerade ? [el("span", { class: "sehrleise" }, t("k_gerade") + " "),   /* A1953: Quelle und Alter im Tooltip, veraltet grau */
    el("span", { class: a.gerade_veraltet ? "sehrleise" : "", title: t("k_quelle_" + a.gerade_quelle) + (a.gerade_seit ? " · " + seit(a.gerade_seit) : "")
      + (a.gerade_veraltet ? " · " + t("k_veraltet_h") : "") }, tmKurz(a.gerade, n)), a.gerade_veraltet ? el("span", { class: "bernstein-text" }, " " + t("k_veraltet")) : null]
  : [el("span", { class: "sehrleise" }, a.soll === "an" && !a.chat ? t("k_unbekannt") : (a.zustaendig || t("tm_keine")))];
/* Mit wem er gerade arbeitet (offene Prüfung) oder worauf er wartet – eine Zeile, der Rest steht in der Übersicht */
function tmNeben(a, d) {
  const ende = (d.ende || []).find(x => x.kennung === a.kennung);
  if (ende) return el("div", { class: "tm-neben bernstein-text" }, t("k_endet", { x: zeit(ende.bis_utc) }));
  const wp = a.warteplatz;
  if (wp) { const x = wp.auf?.[0], wer = x ? (x.projekt ? `${x.projekt} / ${x.agent || "–"}` : t("tm_fremd")) : null;
    return el("div", { class: "tm-neben bernstein-text", title: wp.grund ? `L${wp.lauf}: ${wp.grund}` : t("tm_warteplatz_h") },
      "⏳ " + t(wer ? "tm_platz_hinter" : "tm_platz", { p: wp.platz ?? "–", n: wp.von, x: wer })); }
  const z = (d.team?.zusammen || []).find(x => x.von === a.kennung || x.mit === a.kennung);
  if (z) return el("div", { class: "tm-neben tm-mit", title: t("tm_mit_h") }, "⇄ " + (z.von === a.kennung ? z.mit : z.von) + " · " + t("tm_pruefung") + (z.aufgabe ? ` A${z.aufgabe}` : ""));
  const w = a.wartet || [];
  return w.length ? el("div", { class: "tm-neben bernstein-text" }, t("k_wartet", { a: `A${w[0].aufgabe}`, x: w[0].auf }) + (w.length > 1 ? ` +${w.length - 1}` : "")) : null;
}
const tmFuss = a => [tmWeise(a), a.zustand === "aktiv" && a.kontext_prozent != null
  ? el("span", { class: "tm-balken" + (a.kontext_prozent > 85 ? " voll" : a.kontext_prozent > 60 ? " hoch" : ""), title: `${t("b_kontext")} ${Math.round(a.kontext_prozent)} %` }, el("span", { style: `width:${Math.min(100, a.kontext_prozent)}%` }))
  : el("span", { class: "tm-balken ohne" }), el("span", { class: "tm-liste-n", title: (a.fuehrt || []).length ? t("k_fuehrt", { x: a.fuehrt.join(", ") }) : null },
    (a.liste_n ? (a.liste_lauf ? t("tm_liste_lauf", { p: a.liste_lauf, n: a.liste_n }) : t("k_liste_n", { n: a.liste_n })) : "") + ((a.fuehrt || []).length ? " ◆" : ""))];
const teamArt = () => { const g = gemerkt("amw-team"); return g === "baum" || g === "liste" ? g : (matchMedia("(max-width: 760px)").matches ? "liste" : "baum"); };
/* Team auf der Startseite: Baum (du → Lead → Agenten; gestrichelte Bögen = arbeiten gerade zusammen) oder kompakte Liste */
function teamAnsicht(d) {
  const art = teamArt(), rang = a => (a.soll === "an" ? 0 : a.zustand === "aktiv" ? 1 : 2);
  const leads = d.agenten.filter(a => a.rolle === "lead"), rest = d.agenten.filter(a => a.rolle !== "lead").sort((x, y) => rang(x) - rang(y));
  const huelle = el("div", { class: "team", id: "team" });
  huelle.append(el("div", { class: "tm-schalter" }, ["baum", "liste"].map(x => el("button", { class: "klein-knopf" + (x === art ? " an" : ""), type: "button", title: t("tm_" + x + "_h"),
    onclick: () => { try { localStorage.setItem(ablage("amw-team"), x); } catch (e) {} huelle.replaceWith(teamAnsicht(d)); } }, t("tm_" + x)))),
    art === "baum" ? teamBaum(d, leads, rest) : teamListe(d, leads, rest));
  return huelle;
}
const tmDu = d => { const pw = d.planung_wartet || { spezifikationen: [], plaene: [], eigene: [] }, frei = pw.spezifikationen.length + pw.plaene.length;
  return [[pw.eigene.length, "tm_schritte"], [d.fragen.length, "tm_fragen"], [frei, "tm_freigaben"]].filter(([n]) => n); };
function tmLeadInfo(a, d) {
  const b = d.team?.bogen, takt = d.team?.takt_min;
  return [[t("tm_plant"), b ? t("tm_bogen", { nr: b.nr, x: tmKurz(b.titel, 70), f: b.fertig, n: b.n }) + (b.zieldatum ? " · " + t("tm_ziel", { x: datumKurz(b.zieldatum) }) : "") : t("tm_kein_bogen")],
    [t("tm_takt"), takt ? t("tm_takt_min", { n: takt }) : t("tm_takt_hand")],
    a.zuletzt ? [t("k_zuletzt"), `${seit(a.zuletzt_utc)}: ${tmKurz(a.zuletzt, 110)}`] : null].filter(Boolean);
}
function teamBaum(d, leads, rest) {
  let zeiger = "maus";
  const fokus = k => { if ((baum.dataset.fokus || "") === k) return; if (k) baum.dataset.fokus = k; else delete baum.dataset.fokus; zeichnen(); };
  const karte = (a, klasse, ...inhalt) => { const k = el("div", { class: `tm-knoten ${klasse} klickbar`, "data-k": a.kennung, title: t("k_details"), tabindex: 0 }, inhalt);
    k.addEventListener("pointerdown", e => { zeiger = e.pointerType; });
    k.addEventListener("click", () => { if (zeiger === "touch" && baum.dataset.fokus !== a.kennung) { fokus(a.kennung); return; } agentDialog(a.kennung); });
    k.addEventListener("mouseenter", () => fokus(a.kennung)); k.addEventListener("mouseleave", () => fokus(""));
    k.addEventListener("focusin", () => fokus(a.kennung)); k.addEventListener("focusout", () => fokus(""));
    k.addEventListener("keydown", e => { if (e.key === "Enter") agentDialog(a.kennung); });
    return k; };
  const du = el("div", { class: "tm-knoten tm-du", "data-k": "*du" }, tmZeichen("mensch", ""), el("span", { class: "tm-name" }, t("tm_du")), el("span", { class: "leise" }, t("tm_leitet")),
    tmDu(d).map(([n, k]) => el("span", { class: "tm-zahl" }, el("b", {}, n), " " + t(k))));
  const lead = a => karte(a, "tm-lead" + (agentZustand(a)[0] === "rot" ? " tot" : ""),
    el("div", { class: "tm-wer" }, el("span", { class: "tm-name" }, agentName(a)), tmFach(a), tmZustand(a)),
    el("dl", {}, tmLeadInfo(a, d).flatMap(([k, v]) => [el("dt", {}, k), el("dd", {}, v)])),
    el("div", { class: "tm-rechts" }, el("span", { class: "tm-zeile" }, tmOffen(a), tmMehr(a)), el("span", { class: "tm-zeile sehrleise" }, tmWeise(a), tmFuss(a)[2])));
  const agent = a => karte(a, "tm-agent" + (agentZustand(a)[0] === "rot" && a.zustand !== "aktiv" ? " tot" : "") + (a.soll !== "an" ? " aus" : ""),
    el("div", { class: "tm-wer" }, el("span", { class: "tm-name" }, agentName(a)), tmFach(a),
      (a.wartet_auf || []).includes("Entwickler") ? el("span", { class: "tm-auf-dich", title: t("tm_wartet_du_h") }, "\u23f3 " + t("tm_wartet_du"))
        : (a.wartet_auf || []).length ? el("span", { class: "tm-auf-andere", title: t("tm_wartet_andere_h") }, "\u23f3 " + t("wartet_auf_x", { x: a.wartet_auf.slice(0, 2).join(", ") }))
        : null,                                                   /* A1860: „wartet auf dich“ nur, wenn du wirklich dran bist */
      el("span", { class: "tm-zeile tm-ende" }, tmMehr(a))),
    tmZustand(a), el("div", { class: "tm-auf" }, tmAufgabe(a, 80)), tmNeben(a, d) || el("div", { class: "tm-neben" }, "\u00a0"), el("div", { class: "tm-fuss" }, tmFuss(a), tmOffen(a, true)));
  const strich = art => { const ns2 = "http://www.w3.org/2000/svg", g = document.createElementNS(ns2, "svg"), l = document.createElementNS(ns2, "path");
    g.setAttribute("viewBox", "0 0 34 10"); l.setAttribute("d", "M1 5 H26"); l.setAttribute("class", "tm-" + art);
    const sp = document.createElementNS(ns2, "path"); sp.setAttribute("d", "M24 0 L34 5 L24 10 z"); sp.setAttribute("class", "tm-spitze-" + art); g.append(l, sp); return g; };
  const legende = el("div", { class: "tm-legende sehrleise" }, el("span", {}, strich("ast"), t("tm_leg_ast")),
    el("span", { class: "tm-leg-mehr" }, strich("bogen"), t("tm_leg_bogen")), el("span", { class: "tm-leg-mehr" }, strich("warten"), t("tm_leg_warten")),
    el("span", {}, t("tm_leg_fokus")));
  const baum = el("div", { class: "tm-baum" }, du, leads.length ? el("div", { class: "tm-leads" }, leads.map(lead)) : null, el("div", { class: "tm-ebene" }, rest.map(agent)), legende);
  const ns = "http://www.w3.org/2000/svg", linien = document.createElementNS(ns, "svg"); linien.setAttribute("class", "tm-linien"); baum.prepend(linien);
  function zeichnen() { tmLinien(baum, linien, d); }
  requestAnimationFrame(zeichnen); setTimeout(zeichnen, 60); new ResizeObserver(zeichnen).observe(baum);   /* setTimeout: falls der Browser Animationen aussetzt (Tab im Hintergrund) */
  return baum;
}
/* Linien des Baums: rechtwinklige Äste von oben nach unten; gestrichelte, ebenfalls rechtwinklige Verbindung unter zwei Agenten
   derselben Reihe, die zusammenarbeiten – keine Bögen */
function tmLinien(baum, svg, d) {
  if (!baum.isConnected) return;
  const ns = "http://www.w3.org/2000/svg", o = baum.getBoundingClientRect();
  const ort = e => { const r = e.getBoundingClientRect(); return { x: r.left - o.left + r.width / 2, oben: r.top - o.top, unten: r.bottom - o.top }; };
  const knoten = k => baum.querySelector(`[data-k="${CSS.escape(k)}"]`);
  const teile = [], pfad = (klasse, dd) => { const p = document.createElementNS(ns, "path"); p.setAttribute("class", klasse); p.setAttribute("d", dd);
    p.setAttribute("marker-end", `url(#tm-spitze-${klasse.split(" ")[0].slice(3)})`); teile.push(p); return p; };
  const defs = document.createElementNS(ns, "defs");
  for (const art of ["ast", "bogen", "warten"]) {         /* Pfeilspitze: Aufträge laufen zum Pfeil, Arbeit geht zur Prüfung, wartet auf */
    const m = document.createElementNS(ns, "marker"), sp = document.createElementNS(ns, "path");
    for (const [k, v] of Object.entries({ id: "tm-spitze-" + art, viewBox: "0 0 10 10", refX: 8, refY: 5, markerWidth: 11, markerHeight: 11,
      markerUnits: "userSpaceOnUse", orient: "auto-start-reverse" })) m.setAttribute(k, v);
    sp.setAttribute("d", "M0 0 L10 5 L0 10 z"); sp.setAttribute("class", "tm-spitze-" + art); m.append(sp); defs.append(m); }
  teile.push(defs);
  const du = ort(knoten("*du")), leads = [...baum.querySelectorAll(".tm-lead")].map(ort), agenten = [...baum.querySelectorAll(".tm-agent")];
  const stamm = leads.length ? { x: leads.reduce((s, l) => s + l.x, 0) / leads.length, unten: Math.max(...leads.map(l => l.unten)) } : du;
  for (const l of leads) pfad("tm-ast", `M${du.x} ${du.unten} V${(du.unten + l.oben) / 2} H${l.x} V${l.oben - 1}`);
  const reihen = new Map(); for (const a of agenten) { const q = ort(a); const y = Math.round(q.oben); if (!reihen.has(y)) reihen.set(y, []); reihen.get(y).push(q); }
  const ys = [...reihen.keys()].sort((a, b) => a - b);
  for (const y of ys) { const xs = reihen.get(y).map(q => q.x), quer = y - 12;
    pfad("tm-ast", `M${Math.min(...xs, stamm.x)} ${quer} H${Math.max(...xs, stamm.x)}`).removeAttribute("marker-end");
    for (const x of xs) pfad("tm-ast", `M${x} ${quer} V${y - 1}`); }
  if (ys.length) pfad("tm-ast", `M${stamm.x} ${stamm.unten} V${ys[ys.length - 1] - 12}`).removeAttribute("marker-end");
  /* Prüfungen und Wartebeziehungen nur für die Karte im Fokus (Maus, Tastatur, erstes Antippen) – sonst überlagern sich die
     Linien. Jede Beziehung in eigener Spur mit festem Abstand; „wartet auf dich“ steht als Markierung an der Karte. */
  const f = baum.dataset.fokus || "";
  baum.querySelectorAll(".tm-knoten").forEach(k => k.classList.remove("im-fokus", "im-bezug"));
  if (f) {
    const bez = [];
    for (const z of d.team?.zusammen || []) if (z.von === f || z.mit === f) bez.push({ art: "bogen", von: z.von, nach: z.mit });
    for (const a of d.agenten || []) for (const ziel of a.wartet_auf || []) {
      if (ziel !== "Entwickler" && (a.kennung === f || ziel === f)) bez.push({ art: "warten", von: a.kennung, nach: ziel }); }
    const gesehen = new Set(), liste = bez.filter(b => { const s_ = b.art + b.von + ">" + b.nach; if (gesehen.has(s_)) return false; gesehen.add(s_); return true; });
    knoten(f)?.classList.add("im-fokus");
    liste.forEach((b, i) => {
      const a = knoten(b.von), z = knoten(b.nach); if (!a || !z) return;
      a.classList.add("im-bezug"); z.classList.add("im-bezug");
      const p = ort(a), q = ort(z), ver = (i - (liste.length - 1) / 2) * 16;     // eigene Spur: Ein- und Ausgang versetzt
      if (Math.abs(p.unten - q.unten) <= 4) {                                     // gleiche Reihe: unter den Karten, je Beziehung tiefer
        const y = Math.max(p.unten, q.unten) + 12 + 12 * i;
        pfad("tm-" + b.art + " stark", `M${p.x + ver} ${p.unten} V${y} H${q.x + ver} V${q.unten + 1}`);
      } else if (q.unten < p.oben) {                                              // nach oben (Lead)
        const zr = z.getBoundingClientRect(), x = p.x + ver + 30;                // senkrecht hinein, wenn die Karte darüber liegt
        if (x > zr.left - o.left + 8 && x < zr.right - o.left - 8) pfad("tm-" + b.art + " stark", `M${x} ${p.oben} V${q.unten + 1}`);
        else { const y = p.oben - 6 - 6 * i; pfad("tm-" + b.art + " stark", `M${p.x + ver} ${p.oben} V${y} H${q.x + ver} V${q.unten + 1}`); }
      } else {                                                                    // nach unten (vom Lead zum Agenten)
        const x = q.x + ver + 30, ar = a.getBoundingClientRect();
        if (x > ar.left - o.left + 8 && x < ar.right - o.left - 8) pfad("tm-" + b.art + " stark", `M${x} ${p.unten} V${q.oben - 1}`);
        else { const y = q.oben - 6 - 6 * i; pfad("tm-" + b.art + " stark", `M${p.x + ver} ${p.unten} V${y} H${q.x + ver} V${q.oben - 1}`); }
      }
    });
  }
  svg.replaceChildren(...teile);
}
function teamListe(d, leads, rest) {
  const zeile = (a, ast, klasse) => { const z = el("div", { class: `tm-z ${klasse || ""} klickbar` + (a.soll !== "an" ? " aus" : ""), "data-k": a.kennung, title: t("k_details") },
    el("div", { class: "tm-wer" }, el("span", { class: "tm-astz" }, ast), tmWeise(a), el("span", { class: "tm-name" }, agentName(a)), tmOffen(a)), el("span", {}, tmFach(a)), tmZustand(a),
    el("div", { class: "tm-auf" }, a.rolle === "lead" && d.team?.bogen ? [el("span", { class: "sehrleise" }, t("tm_plant") + ": "), tmLeadInfo(a, d)[0][1]] : tmAufgabe(a, 120)),
    tmNeben(a, d) || el("span", {}), el("span", { class: "tm-fuss" }, tmFuss(a).slice(1)), tmMehr(a));
    z.addEventListener("click", () => agentDialog(a.kennung)); return z; };
  return el("div", { class: "tm-liste" },
    el("div", { class: "tm-z tm-kopfz" }, ["tm_k_agent", "tm_k_fach", "tm_k_zustand", "tm_k_auf", "tm_k_mit", "tm_k_liste"].map(k => el("span", {}, t(k))), el("span", {})),
    el("div", { class: "tm-z tm-du" }, el("div", { class: "tm-wer" }, tmZeichen("mensch", ""), el("span", { class: "tm-name" }, t("tm_du"))), el("span", { class: "leise" }, t("tm_leitet")), el("span", {}),
      el("div", { class: "tm-auf" }, tmDu(d).flatMap(([n, k], i) => [i ? " · " : "", el("b", {}, n), " " + t(k)])), el("span", {}), el("span", {}), el("span", {})),
    leads.map(a => zeile(a, "└", "tm-lead")), rest.map((a, i) => zeile(a, "\u00a0\u00a0" + (i === rest.length - 1 ? "└" : "├"))));
}
/* Starten / Fortsetzen / Neu / Beenden – nur am PC (online gibt es keine Knöpfe), immer mit Rückfrage */
function steuerKnoepfe(d, schliessen) {
  if (API || !d.profil) return [];
  const aktion = async (weg, daten, frage) => {
    if (!confirm(frage)) return;
    try { const r = await schicken(weg, { kennung: d.kennung, ...daten }); toast(r.text || t("gespeichert")); schliessen(); setTimeout(() => zeige(zustand.sicht, true), 4000); }
    catch (e) { toast(t("fehler", { x: e.message }), true); }
  };
  if (!d.profil.ordner) return [el("button", { class: "klein-knopf", type: "button", title: t("st_profil_h"), onclick: () => { schliessen(); zeige("einstellungen"); } }, t("st_profil"))];
  if (d.prozess_laeuft) return [el("button", { class: "klein-knopf", type: "button",
    onclick: () => aktion("/api/agent/stop", {}, t("st_beenden_frage", { x: d.kennung })) }, t("st_beenden"))];
  const knoepfe = [el("button", { class: "knopf haupt", type: "button",
    onclick: () => aktion("/api/agent/start", {}, t(d.fortsetzbar ? "st_fortsetzen_frage" : "st_starten_frage", { x: d.kennung })) },
    t(d.fortsetzbar ? "st_fortsetzen" : "st_starten"))];
  if (d.fortsetzbar) knoepfe.push(el("button", { class: "klein-knopf", type: "button",
    onclick: () => aktion("/api/agent/start", { neu: true }, t("st_neu_frage", { x: d.kennung })) }, t("st_neu")));
  return knoepfe;
}
/* Übersicht: Zustand aus Hooks und Statusline – Modell, Denkstufe, Kontext, Grenzen (mit Rücksetzzeit), Kosten */
function zustandAbschnitt(d) {
  if (d.zustand !== "aktiv" || (!d.status_utc && !d.ereignis)) return el("section", { class: "abschnitt" }, el("h4", {}, t("k_zustand_titel")),
    el("div", { class: "sehrleise leer-klein" }, t(d.zustand !== "aktiv" ? "k_zustand_aus" : "k_zustand_leer")));
  const z = [];
  if (d.ereignis) z.push(el("div", {}, el("b", {}, t("z_" + { arbeitet: "arbeitet", frei: "frei", wartet_freigabe: "freigabe", wartet_eingabe: "eingabe",
    fehler: "fehler", beendet: "beendet" }[d.ereignis] || d.ereignis)), " ", el("span", { class: "sehrleise" }, seit(d.ereignis_utc)),
    d.ereignis_text ? el("div", { class: "sehrleise" }, d.ereignis_text) : null));
  const balk = [];
  if (d.kontext_prozent != null) balk.push(balken(t("b_kontext"), d.kontext_prozent));
  if (d.limit_5h != null) balk.push(balken(t("b_5h"), d.limit_5h));
  if (d.limit_7t != null) balk.push(balken(t("b_7t"), d.limit_7t));
  const neben = [d.modell, d.denkstufe ? t("k_denkstufe", { x: d.denkstufe }) : null,
    d.kosten_usd != null ? t("k_kosten", { x: d.kosten_usd.toFixed(2) }) : null,
    d.limit_5h_reset_utc ? t("k_reset", { x: zeit(d.limit_5h_reset_utc) }) : null].filter(Boolean).join(" · ");
  return el("section", { class: "abschnitt" }, el("h4", {}, t("k_zustand_titel")),
    el("div", { class: "eintrag " + (d.ereignis === "fehler" ? "blockiert" : d.ereignis?.startsWith("wartet") ? "wartet" : "laeuft") },
      ...z, balk.length ? el("div", { class: "mini-balken", style: "max-width:420px" }, ...balk) : null,
      neben ? el("div", { class: "sehrleise eintrag-zusatz" }, neben, d.status_utc ? ` · ${t("k_stand", { x: seit(d.status_utc) })}` : "") : null));
}
/* Verbrauch je Aufgabe (A1611 E1): Median der letzten fertigen Aufgaben, eingestelltes Profil, laufende Aufgabe bisher */
const dollar = x => x.toLocaleString(gebiet(), { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + " $";
const modellStufe = (m, s) => (m ? m[0].toUpperCase() + m.slice(1) : t("pr_vorgabe")) + " · " + t("k_denkstufe", { x: s || t("pr_vorgabe") });
/* Empfehlung je Agent (A1611 E2): häufigste Zelle Größe × Art seiner letzten Aufgaben; übernehmen nur am PC, wirkt beim nächsten Start */
function empfehlungZeile(d) {
  const e = d.empfehlung; if (!e) return null;
  const x = modellStufe(e.modell, e.denkstufe);
  const knopf = !API && e.passt !== true ? el("button", { class: "klein-knopf", type: "button", style: "margin-left:8px", onclick: async ev => {
    const b = ev.currentTarget; if (!confirm(t("k_empf_frage", { x, a: d.kennung }))) return;
    b.disabled = true;
    try { await schicken("/api/einstellungen/profil", { kennung: d.kennung, modell: e.modell, denkstufe: e.denkstufe }); toast(t("k_empf_ok")); b.remove(); }
    catch (f) { toast(t("fehler", { x: f.message }), true); b.disabled = false; } } }, t("k_empf_uebernehmen")) : null;
  return el("div", { class: e.passt === false ? "bernstein-text" : "" }, t("k_empf", { x, g: e.groesse, a: t("gg_" + e.gruppe), n: e.n, v: e.von }),
    e.passt === true ? el("span", { class: "sehrleise" }, " · " + t("k_empf_passt")) : null, knopf);
}
function aufwandAbschnitt(d) {
  const w = d.aufwand, p = d.profil;
  const eingestellt = p ? t("k_aufwand_eingestellt", { x: modellStufe(p.modell, p.denkstufe) }) : null;
  const kopf = el("h4", {}, t("k_aufwand_titel"));
  if (!w) return el("section", { class: "abschnitt" }, kopf, el("div", { class: "sehrleise leer-klein" }, t("k_aufwand_leer"),
    eingestellt ? el("div", {}, eingestellt) : null), empfehlungZeile(d));
  const zeile = x => el("div", { class: "au-zeile" }, el("a", { class: "verweis", onclick: () => aufgabeDialog(x.id) }, `A${x.id}`), " ",
    el("b", { class: "mono" }, dollar(x.usd)), el("span", { class: "sehrleise" }, x.modelle.length ? ` · ${x.modelle.join(", ")}` : ""), " ", x.titel);
  return el("section", { class: "abschnitt" }, kopf,
    el("div", {}, [w.median != null ? t("k_aufwand_median", { x: dollar(w.median), n: w.n }) : null, eingestellt].filter(Boolean).join(" · ")),
    empfehlungZeile(d),
    w.laufend ? el("div", { class: "leise" }, t("k_aufwand_laeuft", { a: w.laufend.id, x: dollar(w.laufend.usd) })) : null,
    w.aufgaben.length ? el("div", { style: "margin-top:6px" }, w.aufgaben.map(zeile)) : null,
    el("p", { class: "sehrleise", style: "margin:6px 0 0;font-size:12px" }, t("k_aufwand_h")));
}
/* schmaler Füllstandsbalken: grün < 60 %, bernstein < 85 %, sonst rot */
function balken(name, p) {
  const farbe = p < 60 ? "--gruen" : p < 85 ? "--bernstein" : "--rot";
  return el("div", { class: "mb", title: `${name} ${Math.round(p)} %` }, el("span", {}, name),
    el("div", { class: "mb-spur" }, el("i", { style: `width:${Math.min(100, Math.max(0, p))}%;background:var(${farbe})` })),
    el("span", { class: "mono" }, `${Math.round(p)} %`));
}
/* Gespräch je Agent: das Protokoll von Claude Code, ruhig gelesen – du rechts, Claude links, Arbeitsschritte eingeklappt
   (am PC mit Eingabe und Ergebnis), Weckrufe und Hinweise klein. Live: am PC alle 3 s das Neue, online alle 15 s alles. */
function gespraechAnsicht(kennung, profil) {
  const wurzel = el("div", { class: "gs" });
  let sitzung = null, gewaehlt = false, ab = null, vor = null, stand = null, uhrwerk = null;
  let schritteZeigen = true; try { schritteZeigen = localStorage.getItem("amw-gs-schritte") !== "0"; } catch (e) {}
  wurzel.classList.toggle("ohne-schritte", !schritteZeigen);
  const kopf = el("div", { class: "gs-kopf" });
  const liste = el("div", { class: "gs-liste", role: "log", "aria-label": t("g_tab") });
  const neuKnopf = el("button", { class: "klein-knopf gs-neu", type: "button", hidden: true,
    onclick: () => { liste.scrollTop = liste.scrollHeight; neuKnopf.hidden = true; } }, t("g_neu"));
  wurzel.append(kopf, el("div", { class: "gs-rahmen" }, liste, neuKnopf));
  liste.addEventListener("scroll", () => { if (unten()) neuKnopf.hidden = true; });
  const unten = () => liste.scrollHeight - liste.scrollTop - liste.clientHeight < 60;
  const uhr = x => x ? new Date(x).toLocaleTimeString(gebiet(), { hour: "2-digit", minute: "2-digit" }) : "";
  const tag = x => x ? new Date(x).toLocaleDateString(gebiet(), { weekday: "short", day: "2-digit", month: "2-digit" }) : "";
  const ergebnisse = new Map();                                  /* Werkzeug-id → [Schritt, Platz für das Ergebnis] */
  let letzterTag = null, gruppe = null;
  const gruppeBeschriften = g => {
    const namen = [...new Set(g.namen)];
    g.kopf.textContent = (g.namen.length === 1 ? t("g_schritt") : t("g_schritte", { n: g.namen.length })) + " · " +
      namen.slice(0, 5).join(", ") + (namen.length > 5 ? " …" : "");
  };
  /* Einträge → Knoten; ziel: Liste (anhängen) oder Fragment (Ältere, kommt nach oben) */
  function bauen(eintraege, ziel) {
    for (const e of eintraege) {
      if (e.art === "ergebnis") {
        const x = ergebnisse.get(e.id);
        if (x) { x[1].append(el("div", { class: "gs-pre-titel" }, t(e.fehler ? "g_fehler" : "g_ergebnis")),
          el("pre", { class: "gs-pre" + (e.fehler ? " fehler" : "") }, e.text || "–"));
          if (e.fehler) { x[0].classList.add("fehler"); x[2]?.classList.add("fehler"); } }
        continue;
      }
      const tg = tag(e.zeit);
      if (tg && tg !== letzterTag) { ziel.append(el("div", { class: "gs-tag" }, tg)); letzterTag = tg; gruppe = null; }
      if (e.art === "werkzeug") {
        if (!gruppe) {
          gruppe = { namen: [], kopf: el("summary"), koerper: el("div", { class: "gs-schritte" }) };
          gruppe.knoten = el("details", { class: "gs-gruppe" }, gruppe.kopf, gruppe.koerper);
          ziel.append(gruppe.knoten);
        }
        gruppe.namen.push(e.name); gruppeBeschriften(gruppe);
        const zeile = [el("span", { class: "gs-wz" }, e.name), e.kurz || ""];
        if (e.eingabe != null) {
          const platz = el("div");
          const schritt = el("details", { class: "gs-schritt" }, el("summary", { title: uhr(e.zeit) }, ...zeile),
            el("div", { class: "gs-pre-titel" }, t("g_eingabe")), el("pre", { class: "gs-pre" }, e.eingabe), platz);
          ergebnisse.set(e.id, [schritt, platz, gruppe.knoten]);
          gruppe.koerper.append(schritt);
        } else gruppe.koerper.append(el("div", { class: "gs-schritt ohne", title: uhr(e.zeit) }, ...zeile));
        continue;
      }
      gruppe = null;
      if (e.art === "mensch") ziel.append(el("div", { class: "gs-zeile gs-mensch" },
        el("div", { class: "gs-blase" }, e.text, el("span", { class: "gs-zeit" }, uhr(e.zeit)))));
      else if (e.art === "claude") ziel.append(el("div", { class: "gs-zeile gs-claude" },
        el("div", { class: "gs-blase" }, markdown(e.text), el("span", { class: "gs-zeit" }, uhr(e.zeit)))));
      else if (e.art === "weckruf") ziel.append(el("div", { class: "gs-zeile gs-weckruf" }, el("span", { class: "gs-etikett" }, t("g_weckruf")),
        el("span", { class: "gs-text", title: t("aufklappen"), onclick: ev => ev.currentTarget.classList.toggle("auf") }, e.text),
        el("span", { class: "gs-zeit" }, uhr(e.zeit))));
      else ziel.append(el("div", { class: "gs-hinweis" + (e.art === "fehler" ? " fehler" : "") + (e.art === "befehl" ? " mono" : "") },
        e.text, " · ", uhr(e.zeit)));
    }
  }
  function kopfBauen(d) {
    const teile = [];
    if (!API && d.sitzungen.length > 1) {
      const wahl = el("select", { "aria-label": t("g_sitzung"), onchange: () => { sitzung = wahl.value; gewaehlt = true; laden("voll"); } },
        d.sitzungen.map(s => el("option", { value: s.sitzung, selected: s.sitzung === d.sitzung },
          `${zeit(s.gestartet_utc)}${s.laeuft ? " · " + t("g_laeuft") : ""}`)));
      teile.push(wahl);
    }
    const lebt = d.laeuft, busy = d.status === "busy";
    teile.push(el("span", { class: "signal" }, el("span", { class: "punkt " + (lebt ? (busy ? "gruen" : "bernstein") : "") }),
      lebt ? t(busy ? "g_arbeitet" : "g_bereit") : t("g_beendet")));
    teile.push(el("label", {}, el("input", { type: "checkbox", checked: schritteZeigen, onchange: ev => {
      schritteZeigen = ev.target.checked; wurzel.classList.toggle("ohne-schritte", !schritteZeigen);
      try { localStorage.setItem("amw-gs-schritte", schritteZeigen ? "1" : "0"); } catch (e) {} } }), t("g_schritte_zeigen")));
    const rechts = el("span", { class: "gs-rechts" });
    if (!d.link && !API && d.sitzung) rechts.append(el("span", { class: "gs-hilfe" },
      !lebt ? t("g_kein_link_steht") : profil && !profil.fernsteuerung ? t("g_kein_link_aus") : t("g_kein_link")));
    teile.push(rechts);
    if (d.titel) teile.push(el("div", { class: "gs-titel" }, d.titel));
    if (API) teile.push(el("div", { class: "gs-titel" }, t("g_online_h") + (d.stand_utc ? " · " + t("k_stand", { x: seit(d.stand_utc) }) : "")));
    kopf.replaceChildren(...teile);
  }
  function aeltereKnopf(d) {
    if (d.anfang) return el("div", { class: "gs-hinweis" }, t("g_anfang"));
    if (API) return el("div", { class: "gs-hinweis" }, t("g_aelter_pc"));
    const k = el("button", { class: "klein-knopf gs-mehr", type: "button", onclick: () => laden("aelter", k) }, t("g_aeltere"));
    return k;
  }
  async function laden(modus, knopf) {
    let q = "/api/gespraech?kennung=" + encodeURIComponent(kennung);
    if (!API) {
      if (sitzung) q += "&sitzung=" + encodeURIComponent(sitzung);
      if (modus === "neu") q += "&ab=" + ab;
      if (modus === "aelter") q += "&vor=" + vor;
    }
    let d;
    try { d = await abrufen(q); }
    catch (e) { if (modus === "voll") liste.replaceChildren(el("div", { class: "leer-gs" }, t("fehler", { x: e.message }))); return; }
    if (!wurzel.isConnected) return;
    if (d.warten) { kopf.replaceChildren(); liste.replaceChildren(el("div", { class: "leer-gs" }, t("g_warten"))); uhrwerkStellen(5000); return; }
    if (modus === "neu") {
      if (!gewaehlt && d.sitzung !== sitzung) return laden("voll");      /* neue Sitzung (Neustart) – von vorn */
      if (!d.eintraege.length) { ab = d.ab; return; }
      const war = unten(); ab = d.ab; bauen(d.eintraege, liste);
      if (war) liste.scrollTop = liste.scrollHeight; else neuKnopf.hidden = false;
      return;
    }
    if (modus === "aelter") {
      const frag = document.createDocumentFragment(), h0 = liste.scrollHeight, merk = [letzterTag, gruppe];
      letzterTag = null; gruppe = null; vor = d.vor;
      frag.append(aeltereKnopf(d)); bauen(d.eintraege, frag);
      [letzterTag, gruppe] = merk; knopf.replaceWith(frag);
      liste.scrollTop += liste.scrollHeight - h0;
      return;
    }
    /* voll: online nur neu zeichnen, wenn sich etwas geändert hat; Leseposition bleibt, wenn du oben liest */
    const merkmal = (d.sitzung || "") + "|" + d.eintraege.length + "|" + (d.eintraege.at(-1)?.zeit || "") + "|" + (d.stand_utc || "");
    kopfBauen(d);
    if (merkmal === stand) return;
    stand = merkmal; sitzung = d.sitzung; ab = d.ab; vor = d.vor;
    const war = unten(), pos = liste.scrollTop, erstes = !liste.childElementCount || !liste.querySelector(".gs-zeile, .gs-gruppe");
    ergebnisse.clear(); letzterTag = null; gruppe = null;
    if (!d.sitzung) { liste.replaceChildren(el("div", { class: "leer-gs" }, t("g_leer"))); return; }
    if (d.fehlt) { liste.replaceChildren(el("div", { class: "leer-gs" }, t("g_fehlt"))); return; }
    liste.replaceChildren(aeltereKnopf(d));
    bauen(d.eintraege, liste);
    if (erstes || war) liste.scrollTop = liste.scrollHeight; else { liste.scrollTop = pos; neuKnopf.hidden = false; }
  }
  function uhrwerkStellen(ms) {
    clearTimeout(uhrwerk);
    uhrwerk = setTimeout(async function weiter() {
      if (!wurzel.isConnected) return;
      if (!document.hidden) await (API || !sitzung ? laden("voll") : laden("neu"));
      uhrwerk = setTimeout(weiter, API ? 15000 : 3000);
    }, ms);
  }
  laden("voll").then(() => uhrwerkStellen(API ? 15000 : 3000));
  return wurzel;
}
async function agentDialog(kennung, reiter) {
  let d; try { d = await abrufen("/api/agent?kennung=" + encodeURIComponent(kennung)); } catch (e) { toast(t("fehler", { x: e.message }), true); return; }
  /* Ein Eintrag = eigener Block: Kopfzeile (Nummer, Kennzeichen, Zeit), darunter der Text; farbiger Rand nach Art/Status */
  const eintrag = (art, ref, etikett, meta, text, zusatz, post) => el("div", { class: "eintrag " + art },
    el("div", { class: "eintrag-kopf" }, el("span", { class: "ref" }, ref), etikett ? el("span", { class: "etikett" }, etikett) : null,
      meta ? el("span", { class: "sehrleise eintrag-meta" }, meta) : null, post ? postKnopf(ref, `${ref} ${String(text).slice(0, 50)}`, d.kennung) : null),
    el("div", { class: "eintrag-text" }, text), zusatz ? el("div", { class: "sehrleise eintrag-zusatz" }, zusatz) : null);
  const abschnitt = (titel, liste, bauen, leer) => el("section", { class: "abschnitt" },
    el("h4", {}, titel, liste && liste.length ? el("span", { class: "anzahl" }, String(liste.length)) : null),
    liste && liste.length ? el("div", { class: "eintraege" }, liste.map(bauen)) : el("div", { class: "sehrleise leer-klein" }, leer || t("k_nichts")));
  const macht = el("section", { class: "abschnitt macht" }, el("h4", {}, t("k_macht")),
    d.gerade ? el("div", { class: "eintrag " + (d.gerade_veraltet ? "vermutet" : (d.gerade_quelle === "lauf" || d.gerade_quelle === "aufgabe") ? "laeuft" : "vermutet") },
      el("div", { class: "eintrag-text gross" }, d.gerade),
      d.gerade_ergaenzung ? el("div", { class: "leise" }, d.gerade_ergaenzung) : null,
      el("div", { class: "sehrleise eintrag-zusatz" }, t("k_quelle_" + d.gerade_quelle), d.gerade_seit ? " · " + seit(d.gerade_seit) : "",
        d.gerade_veraltet ? el("span", { class: "bernstein-text", title: t("k_veraltet_h") }, " · " + t("k_veraltet")) : null))
      : el("div", { class: "sehrleise leer-klein" }, t("k_unbekannt")));
  const links = [
    abschnitt(t("k_kommt"), d.naechste, x => eintrag(x.status, `A${x.id}`, t("sp_" + x.status) || x.status, `Rang ${x.rang}`, x.titel,
      x.wartet_auf ? `${t("k_wartet_auf")} ${x.wartet_auf}` : null)),
    abschnitt(t("k_laeufe"), d.laeufe, x => eintrag("lauf", `L${x.id}`, x.status, seit(x.start_utc), x.beschreibung, x.aufgabe_id ? `A${x.aufgabe_id}` : null, true)),
    abschnitt(t("k_pruefungen"), d.pruefungen, x => eintrag("pruefbitte", `P${x.id}`, x.aufgabe_id ? `A${x.aufgabe_id}` : null, seit(x.angefragt_utc),
      x.pruefer === d.kennung ? t("k_soll_pruefen", { x: x.bauer }) : t("k_wartet_pruefung", { x: x.pruefer }), x.zweig ? `${x.zweig} ${x.sha || ""}` : null, true)),
  ];
  const rechts = [
    abschnitt(t("k_an_ihn", { n: d.an_ihn.length }), d.an_ihn, x => eintrag(x.art, `#${x.id}`, t("art_" + x.art) || x.art, `${wer(x.von)} · ${seit(x.zeit_utc)}`, x.kurz),
      t("k_nichts_neu") + (d.offen_alt ? " " + t("k_alt", { n: d.offen_alt }) : "")),
    abschnitt(t("k_meldungen"), d.meldungen, x => eintrag(x.art, `#${x.id}`, t("art_" + x.art) || x.art, seit(x.zeit_utc), x.kurz)),
  ];
  /* zwei Reiter: Übersicht (was macht er, was kommt) und Gespräch (das Protokoll, erst beim Öffnen geladen) */
  const uebersicht = el("div", { role: "tabpanel" }, macht, zustandAbschnitt(d), aufwandAbschnitt(d),
    el("div", { class: "agent-spalten" }, el("div", {}, ...links), el("div", {}, ...rechts)),
    d.offen_alt && d.an_ihn.length ? el("p", { class: "sehrleise", style: "margin-top:12px" }, t("k_alt", { n: d.offen_alt })) : null);
  const gespraech = el("div", { role: "tabpanel", hidden: true });
  const knopfU = el("button", { type: "button", role: "tab", "aria-selected": "true", onclick: () => wechseln("uebersicht") }, t("g_tab_uebersicht"));
  const knopfG = el("button", { type: "button", role: "tab", "aria-selected": "false", onclick: () => wechseln("gespraech") }, t("g_tab"));
  const tabs = el("div", { class: "gs-tabs", role: "tablist" }, knopfU, knopfG);
  function wechseln(r) {
    const g = r === "gespraech";
    uebersicht.hidden = g; gespraech.hidden = !g;
    knopfU.setAttribute("aria-selected", String(!g)); knopfG.setAttribute("aria-selected", String(g));
    if (g && !gespraech.firstChild) gespraech.append(gespraechAnsicht(d.kennung, d.profil));
  }
  const hg = el("div", { class: "dialog-hg", onclick: e => { if (e.target === hg) hg.remove(); } },
    el("div", { class: "karte dialog agent-dialog" },
      el("div", { class: "agent-kopf" }, el("h3", {}, agentName(d)),
        el("span", { class: "leise" }, `${[d.rolle === "lead" ? t("lead") : null, d.fachgebiet].filter(Boolean).join(" · ") || t("agent")} · ${d.zustand === "aktiv" ? t("laeuft") : (d.zustand || t("nie_gestartet"))}` +
          (d.letzter_puls_utc ? ` · ${t("puls", { t: seit(d.letzter_puls_utc) })}` : "")),
        el("span", { style: "margin-left:auto;display:flex;gap:8px;flex-wrap:wrap" }, ...steuerKnoepfe(d, () => hg.remove()),
          d.claude_link ? el("a", { class: "knopf", href: d.claude_link, target: "_blank", rel: "noopener noreferrer", title: t("g_claude_h") }, t("g_claude")) : null,
          el("button", { class: "knopf", type: "button", onclick: () => { hg.remove(); nachrichtDialog(d.kennung); } }, t("nachricht")))),
      tabs, uebersicht, gespraech));
  document.body.append(hg);
  if (reiter === "gespraech") wechseln("gespraech");
}
/* A1889 (Kleinprobe D1310, F5357 A): Nachrichten über alle Projekte dieses Rechners – je Projekt geladen und hier
   zusammengeführt, jede Zeile trägt ihr Projekt. Ein anderes Projekt, das nicht antwortet, fehlt nur. Fragen bleiben je
   Projekt unter „Fragen“ (B2699). */
const NR_FADEN = 30;                                   /* so viele Nachrichten eines Verlaufs zeigt das Gespräch zuerst */
const nrProjekte = () => { const p = projekte.filter(x => !x.fern).map(x => x.uid); return p.length > 1 ? p : [projekt]; };
async function nrLaden(weg) {
  const r = await Promise.all(nrProjekte().map(p => holen(weg, p).then(d => ({ p, d }), e => { if (p === projekt) throw e; return null; })));
  return r.filter(Boolean);
}
/* Projekt-Filter als Chips (nur bei mehr als einem Projekt): „Alle Projekte“ und je Projekt Farbmarke + Name */
function nrProjektChips(wahl, waehlen) {
  const ps = nrProjekte();
  if (ps.length < 2) return null;
  const chip = (uid, inhalt) => el("button", { type: "button", class: "nr-pchip" + ((wahl || "") === uid ? " an" : ""), "aria-pressed": String((wahl || "") === uid),
    onclick: () => waehlen(uid) }, inhalt);
  return el("div", { class: "nr-pchips" }, chip("", t("nr_alle_projekte")), ...ps.map(uid => chip(uid, projektMarke(uid))));
}
/* Reiter der Nachrichten (A1889): An dich · Mitlesen · Gesendet (+ Lead-Runde); die Zahl an „An dich“ = offen für dich in
   allen Projekten (zuletzt auf der Seite gezählt) */
function nrReiterLeiste(aktiv, eingangOffen, weiter) {
  const z = zustand.start?.zaehler || {};
  if (eingangOffen != null) zustand.nrOffenAlle = eingangOffen;
  const knopf = (k, n) => el("button", { type: "button", class: k === aktiv ? "an" : null, onclick: () => {
    try { localStorage.setItem(ablage("amw-nr"), k); } catch (e) {}
    if (zustand.sicht === "nachrichten" && weiter) weiter(k); else zeige("nachrichten"); } }, t("nr_" + k), n ? el("span", { class: "z" }, n) : null);
  const runde = API && !darfFreigeben() ? null : el("button", { type: "button", class: aktiv === "runde" ? "an" : null, onclick: () => zeige("runde") }, t("nr_runde"));   /* Lead-Runde (A1658): online nur lesen, nur System-Admins (A1680) */
  const chat = el("button", { type: "button", class: aktiv === "teamchat" ? "an" : null, onclick: () => zeige("teamchat") }, t("n_teamchat"));   /* A1657 */
  return el("div", { class: "reiter nr-reiter" }, knopf("eingang", eingangOffen ?? zustand.nrOffenAlle ?? z.nachrichten), chat, knopf("gesendet"), runde);
}
/* Verlauf als Gespräch (A1889, wie im Mail-Programm): alles im selben Projekt mit demselben Bezug – Antworten erben ihn –,
   sonst die Kette über antwort_auf; an dich, von dir und was Agenten untereinander dazu schrieben. Ältestes oben. */
function nrFaeden(eingang, gesendet, mitlesen) {
  const E = "Entwickler", alle = new Map();
  const rein = (p, m) => { const k = `${p}:${m.id}`; if (!alle.has(k)) alle.set(k, { ...m, p }); };
  for (const x of eingang) rein(x.projekt, { id: x.id, zeit_utc: x.zeit_utc, von: x.von, an: [E], kurz: x.kurz, text: x.text, antwort_auf: x.antwort_auf, bezug: x.bezug });
  for (const x of gesendet) rein(x.projekt, { id: x.id, zeit_utc: x.zeit_utc, von: E, an: x.empfaenger.map(e => e.agent), kurz: x.kurz, text: x.text, antwort_auf: x.antwort_auf, bezug: x.bezug });
  for (const x of mitlesen) rein(x.projekt, { id: x.id, zeit_utc: x.zeit_utc, von: x.von, an: x.an, kurz: x.kurz, text: x.text, antwort_auf: x.antwort_auf, bezug: x.bezug });
  const wurzel = m => { const weg = new Set(); while (m.antwort_auf && alle.has(`${m.p}:${m.antwort_auf}`) && !weg.has(m.id)) { weg.add(m.id); m = alle.get(`${m.p}:${m.antwort_auf}`); } return m; };
  const faden = new Map(), schluessel = new Map();
  for (const [k, m] of alle) {
    const w = wurzel(m), s = `${m.p}|` + (m.bezug?.kuerzel || w.bezug?.kuerzel || "r" + w.id);
    schluessel.set(k, s); (faden.get(s) || faden.set(s, []).get(s)).push(m);
  }
  for (const l of faden.values()) l.sort((a, b) => a.id - b.id);
  return x => faden.get(schluessel.get(`${x.projekt}:${x.id}`)) || [];
}
/* Nachrichten an einer Stelle (Stufe N1): Eingang, Gesendet mit Stand je Empfänger, Gespräch rechts, Bezug als Chip */
/* A1837/A1844: Wird die Seite neu gezeichnet (neuer Stand, eigene Aktion), bleibt stehen, was man gerade sieht – Reiter,
   gewählte Nachricht, Scrollstand. Neue Nachrichten erscheinen trotzdem sofort. Nur beim Neuzeichnen derselben Seite. */
let nrMerk = null;
async function sichtNachrichten() {
  let geladen, mit;
  try { [geladen, mit] = await Promise.all([nrLaden("/api/nachrichten"), nrLaden("/api/teamchat").catch(() => [])]); }
  catch (e) { rahmen(t("n_nachrichten")).append(el("div", { class: "leer" }, String(e.message || e))); return; }
  const neuste = (a, b) => (b.zeit_utc || "").localeCompare(a.zeit_utc || "") || b.id - a.id;
  const d = { eingang: [], gesendet: [], zaehler: { eingang_offen: 0, fragen_offen: 0 } };
  for (const { p, d: x } of geladen) {                  /* A1889: alle Projekte in einer Liste, jede Zeile mit ihrem Projekt */
    d.eingang.push(...x.eingang.map(n => ({ ...n, projekt: n.projekt || p })));
    d.gesendet.push(...x.gesendet.map(n => ({ ...n, projekt: n.projekt || p })));
    d.zaehler.eingang_offen += x.zaehler.eingang_offen || 0;
    if (p === projekt) d.zaehler.fragen_offen = x.zaehler.fragen_offen || 0;   /* Fragen: die des Projekts (B2699, eigener Menüpunkt) */
  }
  d.eingang.sort(neuste); d.gesendet.sort(neuste);
  const faden = nrFaeden(d.eingang, d.gesendet, mit.flatMap(({ p, d: x }) => (x.nachrichten || []).map(n => ({ ...n, projekt: p }))));
  const mehrere = nrProjekte().length > 1;
  const m = rahmen(t("n_nachrichten"), el("span", { class: "leise" }, t("nr_unter"), " ", hilfeKnopf("nachrichten")));
  const wahl = gemerkt("amw-nr");                     /* ohne gemerkte Wahl: An dich, wenn dort Ungelesenes liegt (D940 Fund 7) – auch wenn es nicht zählt (A2108) */
  let reiter = wahl === "eingang" || wahl === "gesendet" ? wahl : d.eingang.some(x => x.stand !== "erledigt") ? "eingang" : "gesendet", gewaehlt = null, such = "", agent = "", bezugWahl = "", projektWahl = "";
  const nurOffen = { eingang: true, gesendet: false };  /* A1889: Standard „an dich + offen“ (Marcel, A1629 Punkt 2) */
  const alt = gezeichnet.sicht === "nachrichten" ? nrMerk : null;   /* erst nach dem Laden lesen: ein Klick währenddessen gilt */
  if (alt) { ({ reiter, gewaehlt } = alt); projektWahl = alt.projektWahl || ""; Object.assign(nurOffen, alt.nurOffen || {}); }
  const gesehen = new Set(alt?.gesehen || []);
  const merken = () => { nrMerk = { ...nrMerk, reiter, gewaehlt, projektWahl, nurOffen: { ...nurOffen }, gesehen: [...gesehen], links: liste.scrollTop, rechtsOben: rechts.scrollTop }; };
  const STUFEN = ["gesendet", "benachrichtigt", "gelesen", "erledigt"];
  const schl = x => `${x.projekt || ""}:${x.id}`;
  const chip = (b, x) => b ? el("button", { class: "nr-chip", type: "button", title: t("nr_bezug_h"), onclick: e => { e.stopPropagation();
    if (x?.projekt && x.projekt !== projekt) { try { localStorage.setItem(`amw-sicht:${x.projekt}`, "nachrichten"); } catch (_) {} projektWechseln(x.projekt); return; }
    bezugOeffnen(b); } }, b.text) : null;
  const kette = e => el("div", { class: "nr-kette" }, el("span", { class: "nr-wer" }, e.agent),
    e.stand === "zurueckgezogen" ? el("span", { class: "nr-stufe" }, t("nr_zurueckgezogen")) :
    e.stand === "unterwegs" ? el("span", { class: "nr-stufe jetzt" }, t("nr_unterwegs")) :
    STUFEN.map((x, i) => { const st = STUFEN.indexOf(e.stand);
      const zeitpunkt = { benachrichtigt: e.benachrichtigt_utc, gelesen: e.gelesen_utc, erledigt: e.erledigt_utc }[x];
      return el("span", { class: "nr-stufe" + (i < st || (i === st && x === "erledigt") ? " da" : i === st ? " jetzt" : ""), title: zeitpunkt ? zeit(zeitpunkt) : "" },
        t({ gesendet: "nr_gesendet_s", erledigt: "nr_erledigt_s" }[x] || "nr_" + x)); }));
  const liste = el("div", { class: "nr-liste" }), rechts = el("div", { class: "nr-gespraech" }), raster = el("div", { class: "nr-raster" }, liste, rechts);
  const agenten = [...new Set([...d.gesendet.flatMap(x => x.empfaenger.map(e => e.agent)), ...d.eingang.map(x => x.von)])].sort();
  const bezuege = [...new Map([...d.gesendet, ...d.eingang].filter(x => x.bezug).map(x => [x.bezug.kuerzel, x.bezug.text])).entries()].sort((a, b) => a[0].localeCompare(b[0], undefined, { numeric: true }));
  const filter = el("div", { class: "nr-filter" },
    bezuege.length ? el("select", { "data-filter": "1", onchange: e => { bezugWahl = e.target.value; zeichnen(); } }, el("option", { value: "" }, t("nr_alle_bezuege")),
      bezuege.map(([k, txt]) => el("option", { value: k }, txt.length > 48 ? txt.slice(0, 47) + "…" : txt))) : null,
    el("select", { "data-filter": "1", onchange: e => { agent = e.target.value; zeichnen(); } }, el("option", { value: "" }, t("nr_alle_agenten")), agenten.map(a => el("option", { value: a }, wer(a)))),
    el("label", { class: "leise" }, el("input", { type: "checkbox", "data-filter": "1", class: "nr-nur-offen", onchange: e => { nurOffen[reiter] = e.target.checked; zeichnen(); } }), " " + t("nr_nur_offen")),
    el("input", { "data-filter": "1", placeholder: t("nr_suchen"), oninput: e => { such = e.target.value.toLowerCase(); zeichnen(); } }),
    el("button", { class: "knopf haupt", type: "button", onclick: () => nachrichtDialog(null) }, "+ " + t("nr_schreiben")));
  const kopf = el("div", { class: "nr-leiste" }), chips = el("div", { class: "nr-chipzeile" });
  const nf = d.zaehler.fragen_offen || 0;               /* Fragen stehen nur unter „Fragen“ – hier nur der Hinweis (A1629) */
  const fragenHinweis = nf ? el("div", { class: "nr-hinweis" }, el("button", { type: "button", class: "verweis", onclick: () => zeige("fragen") },
    "? " + (nf === 1 ? t("nr_fragen_offen1") : t("nr_fragen_offen", { n: nf })))) : null;
  const markiert = new Set();                            /* mehrere auf einmal erledigen */
  const sammel = el("div", { class: "nr-sammel" });
  m.append(...[fragenHinweis, kopf, chips, sammel].filter(Boolean), raster);
  const passen = geteilt(raster);
  let gezeigt = null;
  function passt(x) {
    if (such && !`${x.kurz} ${x.text || ""} ${x.bezug?.text || ""}`.toLowerCase().includes(such)) return false;
    if (bezugWahl && x.bezug?.kuerzel !== bezugWahl) return false;
    if (projektWahl && x.projekt !== projektWahl) return false;
    const offen = nurOffen[reiter] && schl(x) !== gewaehlt && !gesehen.has(schl(x));   /* eben Gelesenes bleibt stehen, bis du die Seite verlässt */
    if (reiter === "gesendet") return (!agent || x.empfaenger.some(e => e.agent === agent)) && (!offen || x.empfaenger.some(e => !["erledigt", "zurueckgezogen"].includes(e.stand)));
    return (!agent || x.von === agent) && (!offen || x.stand !== "erledigt");
  }
  function gespraech(x) {
    const neueWahl = (x ? schl(x) : null) !== gezeigt;
    if (neueWahl) { rechts.scrollTop = 0; gezeigt = x ? schl(x) : null; }   /* neue Nachricht: rechts von oben */
    if (!x) { rechts.replaceChildren(el("div", { class: "leer" }, t("nr_waehle"))); return; }
    const ich = reiter === "gesendet";
    const E = "Entwickler", person = k => k === E ? t("nr_dich") : wer(k);
    const ganz = faden(x), alle = nrMerk?.fadenGanz === schl(x);
    const blasen = !ganz.length ? [{ id: x.id, von: ich ? E : x.von, an: ich ? x.empfaenger.map(e => e.agent) : [E], zeit_utc: x.zeit_utc, kurz: x.kurz, text: x.text }]
      : alle ? ganz : ganz.slice(-NR_FADEN);           /* lange Verläufe: die letzten, ältere auf Wunsch */
    const an = ich ? x.empfaenger.map(e => e.agent).join(",") : x.von;
    rechts.replaceChildren(...[                         /* null nicht an replaceChildren geben: es schreibt „null“ */
      el("button", { class: "nr-zurueck", type: "button", onclick: () => { raster.classList.remove("detail"); } }, "‹ " + t(ich ? "nr_gesendet" : "nr_eingang")),
      el("div", { class: "nr-g-kopf" }, el("h3", {}, x.kurz), mehrere ? projektMarke(x.projekt) : null, x.bezug ? chip(x.bezug, x) : null),
      ganz.length > blasen.length ? el("button", { class: "verweis nr-aelter", type: "button", onclick: () => { nrMerk = { ...nrMerk, fadenGanz: schl(x) }; gespraech(x); } },
        t("nr_aelter", { n: ganz.length - blasen.length })) : null,
      ...blasen.map(b => el("div", { class: "nr-blase" + (b.von === E ? " ich" : "") + (b.id === x.id ? " diese" : ""), "data-id": b.id },
        el("div", { class: "wer" }, `${person(b.von)} → ${b.an.map(person).join(", ") || "–"} · ${zeit(b.zeit_utc)}`), el("div", {}, b.kurz),
        b.text ? el("div", { class: "leise", style: "white-space:pre-wrap;margin-top:4px" }, b.text) : null)),
      ich ? el("div", { class: "nr-ketten" }, x.empfaenger.map(kette)) : null,
      el("div", { class: "aktionen" },
        x.zurueckgezogen || x.unterwegs ? null : el("button", { class: "knopf", type: "button", onclick: () => nachrichtDialog(an, { antwort_auf: ich ? null : x.id,
          bezug: x.bezug?.kuerzel, bezugText: x.bezug?.text, art: "info", projekt: x.projekt }) }, t(ich ? "nr_nachfassen" : "nr_antworten")),
        !ich && x.stand !== "erledigt" ? el("button", { class: "knopf", type: "button", onclick: ev => gelesenMarkieren([x], ev.currentTarget) }, t("nr_erledigt")) : null,
        ich && !x.zurueckgezogen && !x.unterwegs && !x.zu_frage ? el("button", { class: "knopf", type: "button", disabled: x.zurueckziehbar ? null : "disabled",
          title: x.zurueckziehbar ? t("nr_zurueckziehen_h") : t("nr_zurueckziehen_nicht"),
          onclick: async () => { if (!confirm(t("nr_zurueckziehen_frage"))) return;
            try { const r = await schicken("/api/nachricht/zurueckziehen", { id: x.id }, x.projekt || projekt); if (!r.unterwegs) toast(t("nr_zurueckgezogen_ok")); sichtNachrichten(); }
            catch (e) { toast(t("fehler", { x: e.message }), true); } } }, t("nr_zurueckziehen")) : null)].filter(Boolean));
    const diese = rechts.querySelector(".nr-blase.diese");   /* im Verlauf: die gewählte Nachricht ins Bild (eigener Scrollbereich am PC) */
    if (neueWahl && diese && blasen.length > 1) rechts.scrollTop += diese.getBoundingClientRect().top - rechts.getBoundingClientRect().top - 80;
  }
  /* A1837 (Marcel 16.11. 22:13: „kommt immer wieder, obwohl ich es schon gelesen habe“): Antippen einer Nachricht = gelesen;
     dazu „Erledigt“ je Nachricht und „Alle erledigt“ (A1889, P308 a: setzt sie auf erledigt wie amw erledigt). Online gilt es sofort in der Anzeige, der PC übernimmt es gleich. */
  async function gelesenMarkieren(xs, knopf) {
    const neu = xs.filter(x => x.stand !== "erledigt");
    if (!neu.length) return;
    if (knopf) knopf.disabled = true;
    const jeProjekt = {};
    for (const x of neu) (jeProjekt[x.projekt || projekt] ||= []).push(x.id);
    try {
      for (const [p, ids] of Object.entries(jeProjekt)) await schicken("/api/gelesen", { ids }, p);
      neu.forEach(x => { x.stand = "erledigt"; gesehen.add(schl(x)); }); markiert.clear();
      d.zaehler.eingang_offen = Math.max(0, (d.zaehler.eingang_offen || 0) - neu.filter(x => x.zaehlt).length);   /* A2108 */
      nachGelesen(neu); gezeichnet.um = Date.now();    /* selbst gezeichnet: nachAktion zeichnet nicht noch einmal */
      kopfAktualisieren().catch(() => {});
    } catch (e) { toast(t("fehler", { x: e.message }), true); if (knopf) knopf.disabled = false; }
  }
  /* Nach „gelesen“ die Liste NICHT neu bauen (L2677: kam das zwischen Drücken und Loslassen eines Tipps, verschwand das
     gedrückte Element und der Klick ging verloren) – nur die betroffenen Zeilen, Reiter-Zähler, Sammelknöpfe, rechts. */
  function kopfZeichnen() {
    const n = d.zaehler.eingang_offen || 0;
    kopf.replaceChildren(nrReiterLeiste(reiter, n, k => { reiter = k; gewaehlt = null; markiert.clear(); zeichnen(); }),
      el("span", { class: "nr-offen" + (n ? "" : " null") }, t("nr_offen_dich", { n })), filter);
    filter.querySelector(".nr-nur-offen").checked = !!nurOffen[reiter];
    const c = mehrere ? nrProjektChips(projektWahl, uid => { projektWahl = uid; gewaehlt = null; markiert.clear(); zeichnen(); }) : null;
    chips.replaceChildren(...(c ? [c] : []));
  }
  function nachGelesen(neu) {
    kopfZeichnen();
    sammelZeichnen();
    for (const x of neu) {
      const z = [...liste.querySelectorAll(".nr-eintrag")].find(e => e.dataset.schl === schl(x));
      if (z) { z.classList.remove("neu"); z.querySelector(".nr-wahl")?.remove(); }
    }
    const g = d[reiter].find(x => schl(x) === gewaehlt);
    if (g && neu.includes(g)) gespraech(g);
    merken();
  }
  function sammelZeichnen() {
    const offene = reiter === "eingang" ? d.eingang.filter(passt).filter(x => x.stand !== "erledigt") : [];
    for (const k of [...markiert]) if (!offene.some(x => schl(x) === k)) markiert.delete(k);
    sammel.replaceChildren(...(offene.length ? [
      offene.length > 1 ? el("label", { class: "leise" }, el("input", { type: "checkbox", "data-filter": "1", checked: markiert.size === offene.length && offene.length ? true : null,
        onchange: e => { markiert.clear(); if (e.target.checked) offene.forEach(x => markiert.add(schl(x))); zeichnen(); } }), " " + t("nr_alle_markieren")) : null,
      markiert.size ? el("button", { class: "knopf", type: "button", onclick: ev => gelesenMarkieren(offene.filter(x => markiert.has(schl(x))), ev.currentTarget) },
        t("nr_erledigt_n", { n: markiert.size }))
        : el("button", { class: "knopf nr-alle-gelesen", type: "button", onclick: ev => gelesenMarkieren(offene, ev.currentTarget) }, t("nr_alle_gelesen", { n: offene.length }))].filter(Boolean) : []));
  }
  function zeichnen() {
    kopfZeichnen();
    sammelZeichnen();
    const l = d[reiter].filter(passt);
    if (!l.some(x => schl(x) === gewaehlt)) gewaehlt = l[0] ? schl(l[0]) : null;
    const system = x => reiter === "eingang" && x.von === "AMW";
    liste.replaceChildren(...(l.length ? l.map(x => el("div", { class: "nr-eintrag" + (system(x) ? " system" : " post") + (schl(x) === gewaehlt ? " an" : "") + (reiter === "eingang" && x.stand === "offen" ? " neu" : "") + (x.zurueckgezogen ? " weg" : ""),
        "data-schl": schl(x), onclick: () => { gewaehlt = schl(x); raster.classList.add("detail"); zeichnen(); if (reiter === "eingang") gelesenMarkieren([x]); } },
      el("div", { class: "nr-kopf" },
        reiter === "eingang" && x.stand !== "erledigt" ? el("input", { type: "checkbox", "data-filter": "1", class: "nr-wahl", title: t("nr_markieren"), "aria-label": t("nr_markieren"),
          checked: markiert.has(schl(x)) ? true : null, onclick: e => { e.stopPropagation(); markiert[markiert.has(schl(x)) ? "delete" : "add"](schl(x)); zeichnen(); } }) : null,
        el("span", { class: "nr-sym", title: t(system(x) ? "nr_art_system" : "nr_art_post") }, system(x) ? "⚙" : "✉"),
        mehrere ? projektMarke(x.projekt) : null,
        el("span", { class: "etikett" }, t("art_" + x.art) || x.art),
        reiter === "gesendet" ? [t("nr_an_k") + " ", el("b", {}, x.empfaenger.map(e => e.agent).join(", ") || "–")] : [t("nr_von_k") + " ", el("b", {}, wer(x.von))],
        el("span", { class: "nr-zeit" }, zeit(x.zeit_utc))),
      el("div", { class: "nr-kurz" }, x.kurz, faden(x).length > 1 ? el("span", { class: "nr-im-verlauf" }, " · " + t("nr_im_verlauf", { n: faden(x).length })) : null),
      x.bezug ? chip(x.bezug, x) : null,
      reiter === "gesendet" && x.empfaenger.length === 1 ? kette(x.empfaenger[0]) : reiter === "gesendet" ? el("div", { class: "sehrleise", style: "font-size:12px" },
        t("nr_mehrere", { n: x.empfaenger.length, e: x.empfaenger.filter(e => e.stand === "erledigt").length })) : null))
      : [el("div", { class: "leer" }, t(reiter === "eingang" && nurOffen.eingang ? "nr_leer_offen" : "nr_leer"))]));
    gespraech(l.find(x => schl(x) === gewaehlt));
    passen();
    if (BREIT.matches && !alt) liste.querySelector(".nr-eintrag.an")?.scrollIntoView({ block: "nearest" });   /* gewählte Zeile bleibt sichtbar */
    merken();
  }
  zeichnen();
  if (alt) { liste.scrollTop = alt.links; rechts.scrollTop = alt.rechtsOben; gezeigt = gewaehlt; if (alt.detail) raster.classList.add("detail"); }
  liste.addEventListener("scroll", merken, { passive: true });
  rechts.addEventListener("scroll", merken, { passive: true });
  new MutationObserver(() => { if (nrMerk) nrMerk.detail = raster.classList.contains("detail"); }).observe(raster, { attributes: true, attributeFilter: ["class"] });   /* Detailansicht (Handy) */
}
/* Team-Chat (A1629, Marcel 13.11.): Agenten und Lead untereinander – nur lesen, zählt nie; neueste oben, Filter Agent/Suche */
/* Lead-Runde (A1658): was die Leads aller Projekte einander schreiben – nur Information, nur lesen, nur am PC */
async function sichtRunde() {
  let d; try { d = await holen("/api/runde"); } catch (e) { rahmen(t("n_nachrichten")).append(el("div", { class: "leer" }, String(e.message || e))); return; }
  const m = rahmen(t("n_nachrichten"), el("span", { class: "leise" }, t("rd_unter"), " ", hilfeKnopf("lead-runde")));
  m.append(nrReiterLeiste("runde"), el("div", { class: "nr-hinweis", id: "runde-richtlinie" }, el("b", {}, t("rd_richtlinie_h") + ": "), d.richtlinie),
    el("div", { class: "tc-liste" }, d.eintraege.length ? d.eintraege.map(x => el("div", { class: "tc-eintrag", id: "runde-" + x.id },
      el("div", { class: "nr-kopf" }, el("span", { class: "ref" }, "R" + x.id), el("span", { class: "etikett" }, t("art_" + x.art) || x.art),
        el("b", {}, `${x.projekt}/${x.von}`), x.an_projekt ? el("span", { class: "leise" }, " " + t("rd_an", { x: x.an_projekt })) : null,
        x.antwort_auf ? el("span", { class: "leise" }, " · " + t("rd_antwort", { n: x.antwort_auf })) : null, el("span", { class: "nr-zeit" }, zeit(x.zeit_utc))),
      el("div", { class: "nr-kurz" }, x.kurz),
      x.text ? el("div", { class: "sehrleise", style: "white-space:pre-wrap;margin-top:4px" }, x.text) : null))
      : [el("div", { class: "leer" }, t("rd_leer"))]));
}
async function sichtTeamchat() {
  let geladen; try { geladen = await nrLaden("/api/teamchat"); } catch (e) { rahmen(t("n_teamchat")).append(el("div", { class: "leer" }, String(e.message || e))); return; }
  const d = { nachrichten: geladen.flatMap(({ p, d: x }) => (x.nachrichten || []).map(n => ({ ...n, projekt: p })))
    .sort((a, b) => (b.zeit_utc || "").localeCompare(a.zeit_utc || "") || b.id - a.id), agenten: [...new Set(geladen.flatMap(({ d: x }) => x.agenten || []))].sort() };
  const mehrere = nrProjekte().length > 1;             /* A1889: Mitlesen über alle Projekte, jede Zeile mit ihrem Projekt */
  const m = rahmen(t("n_nachrichten"), el("span", { class: "leise" }, t("tc_unter")));
  m.append(nrReiterLeiste("teamchat"));
  let agent = "", such = "", projektWahl = "";
  const liste = el("div", { class: "tc-liste" }), chips = el("div", { class: "nr-chipzeile" });
  m.append(el("div", { class: "nr-leiste" }, el("div", { class: "nr-filter" },
    el("select", { onchange: e => { agent = e.target.value; zeichnen(); } }, el("option", { value: "" }, t("nr_alle_agenten")), d.agenten.map(a => el("option", { value: a }, a))),
    el("input", { placeholder: t("nr_suchen"), oninput: e => { such = e.target.value.toLowerCase(); zeichnen(); } }))), chips, liste);
  function zeichnen() {
    const c = mehrere ? nrProjektChips(projektWahl, uid => { projektWahl = uid; zeichnen(); }) : null;
    chips.replaceChildren(...(c ? [c] : []));
    const l = d.nachrichten.filter(x => (!projektWahl || x.projekt === projektWahl) && (!agent || x.von === agent || x.an.includes(agent))
      && (!such || `${x.kurz} ${x.text || ""}`.toLowerCase().includes(such)));
    liste.replaceChildren(...(l.length ? l.map(x => el("div", { class: "tc-eintrag" },
      el("div", { class: "nr-kopf" }, mehrere ? projektMarke(x.projekt) : null, el("span", { class: "etikett" }, t("art_" + x.art) || x.art), el("b", {}, x.von), " → ", el("b", {}, x.an.join(", ") || "–"),
        x.bezug ? el("button", { class: "nr-chip", type: "button", title: t("nr_bezug_h"), onclick: () => {
          if (x.projekt && x.projekt !== projekt) { try { localStorage.setItem(`amw-sicht:${x.projekt}`, "teamchat"); } catch (_) {} projektWechseln(x.projekt); return; }   /* Bezug aus einem anderen Projekt: dorthin */
          bezugOeffnen(x.bezug); } }, x.bezug.text) : null,
        el("span", { class: "nr-zeit" }, zeit(x.zeit_utc))),
      el("div", { class: "nr-kurz" }, x.kurz),
      x.text ? el("details", { class: "tc-text" }, el("summary", {}, t("tc_mehr")), el("div", { style: "white-space:pre-wrap" }, x.text)) : null))
      : [el("div", { class: "leer" }, t("tc_leer"))]));
  }
  zeichnen();
}
/* Von überall schreiben: der Bezug geht mit, der Empfänger ist vorgeschlagen (änderbar); alles landet unter „Nachrichten“ */
const leadKennung = () => (zustand.start?.agenten || []).find(a => a.rolle === "lead")?.kennung || null;
function postKnopf(bezug, text, vorschlag) {
  return el("button", { class: "klein-knopf post-knopf", type: "button", title: t("nr_dazu_h"),
    onclick: e => { e.stopPropagation(); nachrichtDialog(null, { bezug, bezugText: text, vorschlag: vorschlag || leadKennung() }); } }, t("nr_dazu"));
}
/* Kleines Gespräch am Objekt: was du dazu geschrieben hast und was dazu an dich ging */
function gespraechZu(bezug, text, vorschlag) {
  const liste = el("div", { class: "nr-zu-liste" }, el("div", { class: "sehrleise" }, "…"));
  const kopf = el("h4", {}, t("nr_zu_titel", { n: "…" }));
  abrufen("/api/nachrichten").then(d => {
    const alle = [...d.gesendet.map(x => ({ ...x, ich: 1 })), ...d.eingang].filter(x => x.bezug?.kuerzel === bezug).sort((a, b) => a.id - b.id);
    kopf.textContent = t("nr_zu_titel", { n: alle.length });
    liste.replaceChildren(...(alle.length ? alle.map(x => el("div", { class: "nr-blase" + (x.ich ? " ich" : "") },
      el("div", { class: "wer" }, `${x.ich ? t("du") + " → " + x.empfaenger.map(e => e.agent).join(", ") : wer(x.von)} · ${zeit(x.zeit_utc)}`), el("div", {}, x.kurz)))
      : [el("div", { class: "sehrleise" }, t("nr_zu_leer"))]));
  }).catch(() => liste.replaceChildren(el("div", { class: "sehrleise" }, t("nr_zu_leer"))));
  return el("div", { class: "au-block nr-zu" }, kopf, liste,
    el("div", { class: "aktionen", style: "justify-content:flex-start" }, el("button", { class: "knopf", type: "button",
      onclick: () => nachrichtDialog(null, { bezug, bezugText: text, vorschlag: vorschlag || leadKennung() }) }, t("nr_schreiben_dazu"))));
}
/* Projekt einer Zeile: Farbpunkt und Name (Nachrichten über alle Projekte) */
function projektMarke(uid, klein) {
  const p = projekte.find(x => x.uid === uid);
  return el("span", { class: "nr-projekt" + (klein ? " klein" : ""), title: p?.name || uid }, el("span", { class: "pw-farbe", style: `background:${p ? farbe(p) : "var(--linie2)"}` }),
    klein ? null : " " + (p?.name || uid));
}
/* Klick auf einen Bezug: zum Objekt springen (Aufgabe, Dokument, Thema als Dialog; sonst die passende Seite) */
function bezugOeffnen(b) {
  if (b.art === "A") aufgabeDialog(b.id); else if (b.art === "D") dokumentDialog(b.id);
  else zeige({ F: "fragen", M: "planung", P: "betrieb", L: "betrieb", T: "wissen", B: "wissen", agent: "start" }[b.art] || "nachrichten");
}
function nachrichtDialog(an, mit = {}) {
  const wahl = an ? null : el("select", {}, [...(zustand.start?.agenten || []).map(a => a.kennung), "alle"].map(k => el("option", { value: k }, k === "alle" ? t("nr_alle") : k)));
  if (wahl && mit.vorschlag && [...wahl.options].some(o => o.value === mit.vorschlag)) wahl.value = mit.vorschlag;
  const art = el("select", {}, ["auftrag", "frage", "korrektur", "info"].map(k => el("option", { value: k }, t("art_" + k))));
  if (mit.art) art.value = mit.art;
  const kurz = el("input", { placeholder: t("n_kurz_ph"), style: "width:100%;padding:8px;margin:8px 0;background:var(--grund);border:1px solid var(--linie);border-radius:3px" });
  const text = el("textarea", { placeholder: t("n_text_ph") });
  const hg = el("div", { class: "dialog-hg", onclick: e => { if (e.target === hg) hg.remove(); } },
    el("div", { class: "karte dialog" }, el("h3", {}, an ? t("nachricht_an", { x: an }) : t("nr_schreiben")),
      mit.projekt && mit.projekt !== projekt ? el("div", { class: "leise" }, projektMarke(mit.projekt)) : null,
      wahl ? el("div", { class: "feld" }, el("label", {}, t("nr_an")), el("div", {}, wahl)) : null,
      mit.bezug ? el("div", { class: "nr-bezug-zeile" }, el("span", { class: "leise" }, t("nr_bezug") + " "), el("span", { class: "nr-chip" }, mit.bezugText || mit.bezug)) : null, art, kurz, text,
      el("div", { class: "aktionen" }, el("button", { class: "knopf haupt", type: "button", onclick: async () => {
        if (!kurz.value.trim()) { toast(t("text_fehlt"), true); return; }
        try { const r = await schicken("/api/nachricht", { an: an || wahl.value, art: art.value, kurz: kurz.value.trim(), text: text.value.trim(),
                  antwort_auf: mit.antwort_auf || null, bezug: mit.bezug || null }, mit.projekt || projekt);
          hg.remove(); toast(t("gesendet", { x: r.an.join(", ") })); kopfAktualisieren(); if (zustand.sicht === "nachrichten") sichtNachrichten(); }
        catch (e) { toast(t("fehler", { x: e.message }), true); } } }, t("senden")),
        el("button", { class: "knopf", type: "button", onclick: () => hg.remove() }, t("abbrechen")))));
  document.body.append(hg); kurz.focus();
}


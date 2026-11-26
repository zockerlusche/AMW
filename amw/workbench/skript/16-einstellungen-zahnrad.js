/* --- Einstellungen (Zahnrad) ------------------------------------------------------------------
   Projekt, Agenten und Online-Seite: am PC und online änderbar. „Dieser PC“ und „Online-Speicher“: nur am PC
   (online nur sichtbar) – sonst könnte, wer sich online anmeldet, die AMW auf eine andere Datenbank umbiegen. */
async function sichtEinstellungen() {
  let d; try { d = await holen("/api/einstellungen"); } catch (e) { rahmen(t("n_einst")).append(el("div", { class: "leer" }, String(e))); return; }
  const wv = zustand.start?.online?.web_version;
  const m = rahmen(t("n_einst"), el("span", { class: "leise mono" }, `AMW v${d.version}` + (wv && wv !== d.version ? ` · Web v${wv}` : "")));
  const feld = (beschriftung, eingabe, hilfe) => el("div", { class: "feld" }, el("label", {}, beschriftung),
    el("div", {}, eingabe, hilfe ? el("div", { class: "sehrleise", style: "font-size:12px;margin-top:2px" }, hilfe) : null));
  const zahl = (wert, min, max, schritt) => el("input", { type: "number", value: wert ?? "", min, max, step: schritt || 1 });
  const text = (wert, art) => el("input", { type: art || "text", value: wert ?? "", autocomplete: "off" });
  const schalter = an => { const x = el("input", { type: "checkbox" }); x.checked = !!an; return x; };
  const wert = x => x.type === "checkbox" ? x.checked : x.type === "number" ? (x.value === "" ? null : Number(x.value)) : x.value.trim();
  /* felder (A1703): {Schlüssel: Eingabe} – nennt der Fehler ein Feld („heimnetz: …“), steht er rot direkt an diesem Feld */
  async function speichern(teil, daten, knopf, felder) {
    knopf.disabled = true;
    for (const x of Object.values(felder || {})) { x.classList?.remove("feld-fehler"); x.parentElement?.querySelector(":scope > .feld-meldung")?.remove(); }
    try { const r = await schicken(`/api/einstellungen/${teil}`, daten); if (!r.unterwegs) toast(r.hinweis ? `${t("gespeichert")} – ${r.hinweis}` : t("gespeichert")); return true; }
    catch (e) {
      const m = /^(\w+): (.+)$/s.exec(e.message || ""), x = m && felder?.[m[1]];
      if (x) { x.classList.add("feld-fehler"); x.after(el("div", { class: "feld-meldung", role: "alert" }, m[2])); x.focus?.(); x.scrollIntoView?.({ block: "center" }); }
      toast(t("fehler", { x: e.message }), true); return false; }
    finally { knopf.disabled = false; }
  }
  /* teil: Name des Speicher-Wegs oder eine Funktion (Abschnitte, die an zwei Stellen speichern); nach: Zusatz unter den Feldern */
  function block(titel, hinweis, felder, teil, sammeln, gesperrt, nach) {
    const knopf = el("button", { class: "knopf haupt", type: "button" }, t("speichern"));
    knopf.addEventListener("click", () => typeof teil === "function" ? teil(knopf) : speichern(teil, sammeln(), knopf));
    if (gesperrt) { for (const [, x] of felder) x.disabled = true; knopf.disabled = true; }
    return el("div", { class: "karte" + (gesperrt ? " gesperrt" : "") }, el("h3", {}, titel),
      hinweis ? el("p", { class: "leise", style: "margin:0 0 12px" }, hinweis) : null,
      ...felder.map(([b, x, h]) => feld(b, x, h)), nach || null, el("div", { style: "margin-top:12px" }, knopf));
  }
  /* Wirkungsort eines Abschnitts: dieser PC · Online-Seite · dieses Projekt · PC und Online-Seite */
  const wirkt = art => el("span", { class: "wirkt", title: t("wirkt_h_" + art) }, t("wirkt_" + art));
  /* Je Feld: weicht der Wert von der Vorgabe ab, steht die Vorgabe dabei; liest der Wächter ihn nur beim Start, steht ↻ dabei */
  const meta = (gruppe, k, x) => { const v = d.vorgaben?.[gruppe]?.[k], teile = [];
    const ist = x.type === "checkbox" ? x.checked : x.value;
    if (v !== undefined && v !== null && v !== "" && String(ist) !== String(v)) teile.push(t("e_vorgabe", { x: v === true ? t("ja") : v === false ? t("nein") : v }));
    if (gruppe === "pc" && (d.neustart || []).includes(k)) teile.push("\u21bb " + t("e_neustart"));
    return teile.join(" · "); };
  const mitMeta = (gruppe, k, beschriftung, x, hilfe) => [beschriftung, x, [hilfe, meta(gruppe, k, x)].filter(Boolean).join(" – ")];
  const anzeige = (v, mono) => el("div", { class: v ? (mono ? "mono" : "") : "sehrleise", style: "padding-top:7px;font-size:13px;overflow-wrap:anywhere" }, v || "–");
  // Aufräumvorschläge: alte Sicherungen, die nach der Regel nicht mehr gebraucht werden – nur Anzeige, gelöscht wird nichts
  /* Ordner mit Größe – Zuwächse und Ablagerungen aus der täglichen Messung (nur Anzeige) */
  const ordnerListe = (l, zeile, id) => !l.length ? anzeige(t("e_noch_keine")) : el("div", { id, style: "padding-top:7px;font-size:13px" },
    ...l.map(x => el("div", { style: "display:flex;gap:12px;justify-content:space-between;padding:2px 0" },
      el("span", { class: "mono", style: "overflow-wrap:anywhere" }, x.ordner), el("span", { class: "sehrleise", style: "white-space:nowrap" }, zeile(x)))));
  /* A1779: Claude-Ablagen in %TEMP%\claude – je Sitzung Größe, wem sie gehört; alte Arbeitskopien mit fertigem Befehl
     zum Kopieren (die AMW führt ihn nie aus) */
  const clTage = a => a == null ? "–" : a === 0 ? t("e_cl_heute") : a === 1 ? t("e_cl_gestern") : t("e_cl_tage", { a });
  const claudeListe = c => !(c.sitzungen || []).length ? anzeige(t("e_noch_keine")) : el("div", { id: "e-claude", style: "padding-top:7px;font-size:13px" },
    ...c.sitzungen.map(s => el("div", { class: "cl-sitzung" + (s.bytes >= 10 * 2 ** 30 ? " bernstein-text" : "") },
      el("div", { style: "display:flex;flex-wrap:wrap;gap:2px 12px;justify-content:space-between" },
        el("b", {}, s.agent ? `${s.agent} · ${s.projekt}` : t("e_cl_ohne")),
        el("span", { class: "sehrleise" }, t("e_cl_zeile", { g: zahlKurz(s.bytes / 2 ** 30), n: s.dateien, a: clTage(s.tage) }))),
      el("div", { class: "mono sehrleise", style: "overflow-wrap:anywhere;font-size:11.5px" }, s.ordner),
      ...(s.arbeitskopien || []).map(k => el("div", { class: "cl-kopie" },
        el("span", { style: "min-width:0" }, t("e_cl_kopie", { g: zahlKurz(k.bytes / 2 ** 30), a: clTage(k.tage) }), " ", el("span", { class: "mono", style: "overflow-wrap:anywhere" }, k.ordner),
          k.selbst ? el("span", { class: "gruen-text", style: "display:block;font-size:12px" }, t("e_cl_selbst", { x: k.selbst, z: k.zweig })) : null),
        el("button", { class: "klein-knopf", type: "button", title: k.befehl, onclick: async () => {
          try { await navigator.clipboard.writeText(k.befehl); toast(t("e_cl_kopiert")); } catch (e) { prompt(t("e_cl_befehl"), k.befehl); } } }, t("e_cl_befehl_knopf")))))),
    el("div", { class: "sehrleise", style: "margin-top:4px" }, t("e_cl_stand", { x: c.zeit_utc ? zeit(c.zeit_utc) : "–" })));
  /* Ins Archiv verschieben – nur wenn ein Archiv-Ordner eingestellt ist; die AMW löscht nichts */
  const archivieren = async namen => {
    if (!confirm(t(namen.length === 1 ? "e_arch_frage1" : "e_arch_frage", { n: namen.length, x: d.rechner.archiv }))) return;
    try { const r = await schicken("/api/archivieren", { namen }); if (!r.unterwegs) toast(t("e_arch_ok", { n: r.verschoben, x: r.ziel })); sichtEinstellungen(); }
    catch (e) { toast(t("fehler", { x: e.message }), true); } };
  const aufraeumListe = a => !a.sicherungen.length ? anzeige(t("e_aufr_keine")) : el("details", { id: "e-aufraeumen", style: "padding-top:7px;font-size:13px" },
    el("summary", {}, t(a.sicherungen.length === 1 ? "e_aufr_sum1" : "e_aufr_sum", { n: a.sicherungen.length, g: zahlKurz(a.bytes / 2 ** 30) })),
    d.rechner.archiv ? el("div", { style: "margin:6px 0" }, el("button", { class: "klein-knopf", type: "button", id: "e-arch-alle",
      onclick: () => archivieren(a.sicherungen.map(x => x.name)) }, t("e_arch_alle"))) : el("div", { class: "sehrleise", style: "margin:6px 0" }, t("e_arch_ohne")),
    ...a.sicherungen.map(x => el("div", { style: "display:flex;gap:12px;justify-content:space-between;align-items:center;padding:2px 0" },
      el("span", { class: "mono", style: "overflow-wrap:anywhere" }, x.name),
      el("span", { class: "sehrleise", style: "white-space:nowrap" }, t("e_aufr_zeile", { g: Math.round(x.bytes / 2 ** 20).toLocaleString(gebiet()), n: x.tage }),
        d.rechner.archiv ? el("button", { class: "klein-knopf", type: "button", style: "margin-left:8px", onclick: () => archivieren([x.name]) }, t("e_arch")) : null))));
  /* Prüf-Knopf: fragt den PC, zeigt jeden Schritt mit Ergebnis – geprüft wird das Gespeicherte */
  const pruefKnopf = (was, beschriftung) => { const b = el("button", { class: "klein-knopf", type: "button" }, beschriftung);
    const aus = el("div", { class: "mono pruef-aus", role: "status" });
    b.addEventListener("click", async () => { b.disabled = true; aus.className = "sehrleise mono pruef-aus"; aus.textContent = t("pv_laeuft");
      try { const r = await abrufen("/api/pruefen?was=" + was);
        aus.className = "mono pruef-aus";
        aus.replaceChildren(...r.schritte.map(x => el("div", { class: x.ok ? "" : "rot-text" }, (x.ok ? "\u2713 " : "\u2717 ") + t(`pv_${x.name}_${x.ok ? "ok" : "f"}`, { x: x.wert ?? "" }))));
      } catch (f) { aus.className = "rot-text mono pruef-aus"; aus.textContent = f.message; }
      finally { b.disabled = false; } });
    return el("div", { class: "pruef", "data-pruef": was }, el("div", { class: "pruef-kopf" }, b, el("span", { class: "sehrleise" }, t("pv_gespeichert"))), aus); };
  const box = el("div", { class: "einst" + (ruhig ? "" : " zeile-reveal") });

  // Projekt
  const pf = { takt_min: zahl(d.projekt.takt_min, 0, 1440), speicher_grenze_gb: zahl(d.projekt.speicher_grenze_gb, 1, 512, 0.5),
    stillstand_min: zahl(d.projekt.stillstand_min, 5, 1440), lauf_ohne_angabe_min: zahl(d.projekt.lauf_ohne_angabe_min, 5, 1440),
    entwickler_name: text(d.projekt.entwickler_name || ""),
    dateien_online: el("select", {}, ["wunsch", "bilder", "alle"].map(w => el("option", { value: w }, t("e_dateien_" + w)))) };
  pf.dateien_online.value = d.projekt.dateien_online || "wunsch";
  for (const [k, werte] of [["spec_vorlegen", ["lead", "alle"]], ["spec_frei", ["entwickler", "lead"]], ["abnahme_kette", ["aus", "an"]], ["versionen", ["empfohlen", "pflicht", "aus"]], ["pruefstufen", ["aus", "an"]],
                            ["release_takt", ["aus", "sofort", "taeglich", "meilenstein"]], ["plan_automatik", ["an", "aus"]], ["neue_aufgaben", ["meilenstein", "eingang"]], ["meilenstein_fertig", ["vorschlag", "automatisch"]],
                            ["merge_blick", ["server", "alle", "aus"]], ["merge_aussen_pruefung", ["an", "aus"]]]) {
    pf[k] = el("select", {}, werte.map(w => el("option", { value: w }, t(`e_${k}_${w}`)))); pf[k].value = d.projekt[k] || werte[0]; }
  pf.info_ablage_h = zahl(d.projekt.info_ablage_h, 1, 168);
  pf.limit_halt = zahl(d.projekt.limit_halt, 1, 100);                 /* A1888: Halt beim Wochenlimit; A1925: leer = Wert des PCs */
  pf.release_zeit = el("input", { type: "time", value: d.projekt.release_zeit || "18:00" });     /* Release-Takt täglich (A1656) */
  const zeitZeigen = () => { pf.release_zeit.style.display = pf.release_takt.value === "taeglich" ? "" : "none"; };
  pf.release_takt.addEventListener("change", zeitZeigen); zeitZeigen();
  const EMPF_WERTE = ["haiku", "sonnet", "opus", "fable"].flatMap(m => ["low", "medium", "high", "xhigh", "max"].map(s => `${m}/${s}`));
  const empfWahl = {};
  const empfTabelle = el("table", { class: "empf-tabelle" }, el("tr", {}, el("th", {}, t("e_empf_art")), ["S", "M", "L", "XL"].map(g => el("th", {}, g))),
    ["einfach", "mittel", "heikel"].map(gr => el("tr", {}, el("td", { class: "leise" }, t("gg_" + gr)), ["S", "M", "L", "XL"].map(g => {
      const std = d.projekt.empfehlung_standard?.[gr]?.[g];
      const w = el("select", { "aria-label": `${t("gg_" + gr)} ${g}`, title: `${t("e_empf_std")}: ${std}` }, EMPF_WERTE.map(v => el("option", { value: v }, v)));
      w.value = d.projekt.empfehlung?.[gr]?.[g] || d.projekt.empfehlung_standard?.[gr]?.[g] || "opus/high";
      (empfWahl[gr] ||= {})[g] = w; return el("td", {}, w); }))));
  pf.version_frist_tage = zahl(d.projekt.version_frist_tage, 1, 365);
  pf.ende_frist_min = zahl(d.projekt.ende_frist_min, 1, 60);
  pf.merge_dienst = el("select", {}, el("option", { value: "" }, t("e_merge_dienst_keiner")),
    (d.agenten || []).map(a => el("option", { value: a.kennung }, a.kennung)));
  pf.merge_dienst.value = d.projekt.merge_dienst || "";
  pf.schwere_befehle = el("textarea", { rows: 3, placeholder: t("e_schwer_ph") }, (d.projekt.schwere_befehle || []).map(x => `${x.name} = ${x.muster}`).join("\n"));
  const schwereBefehle = () => pf.schwere_befehle.value.split("\n").map(z => z.trim()).filter(Boolean).map(z => { const i = z.indexOf("=");
    return i < 0 ? { name: z, muster: "" } : { name: z.slice(0, i).trim(), muster: z.slice(i + 1).trim() }; });
  pf.entwickler_name.placeholder = t("e_entwickler_ph"); pf.entwickler_name.maxLength = 30;
  const pname = el("select", { onchange: e => projektWechseln(e.target.value), disabled: API || projekte.length < 2 },
    (projekte.length ? projekte : [{ uid: "", name: d.projekt.name }]).map(p => el("option", { value: p.uid, ...(p.uid === projekt ? { selected: true } : {}) }, p.name)));
  pf.farbe = el("select", {}, Object.keys(FARBEN).map(f => el("option", { value: f }, t("farbe_" + f))));
  pf.farbe.value = d.projekt.farbe || "bernstein";
  const pwahl = el("div", { style: "display:flex;gap:8px;align-items:center;flex-wrap:wrap" }, pname,
    API ? null : el("button", { class: "klein-knopf", type: "button", onclick: projektNeuDialog }, "+ " + t("pw_neu")),
    el("button", { class: "klein-knopf", type: "button", onclick: projektAnleitung }, "? " + t("npa_link")));
  const pordner = el("div", { class: d.projekt.ordner ? "mono" : "sehrleise", style: "padding-top:7px;font-size:13px;overflow-wrap:anywhere" },
    d.projekt.ordner || t("e_ordner_leer"));
  /* A1826: Connector (MCP) je Projekt – Zeile für claude_desktop_config.json und Schlüssel (Klartext nur einmal im Dialog) */
  const mcpFeld = m => {
    const kopieren = async (text, ok) => { try { await navigator.clipboard.writeText(text); toast(ok); } catch (e) { prompt(t("e_mcp_zeile"), text); } };
    return el("div", { id: "e-mcp", style: "display:grid;gap:6px;padding-top:6px;font-size:13px" },
      el("div", { class: "mono", style: "overflow-wrap:anywhere;font-variant-ligatures:none" }, m.eintrag),
      el("div", { style: "display:flex;gap:8px;flex-wrap:wrap;align-items:center" },
        el("button", { class: "klein-knopf", type: "button", onclick: () => kopieren(m.eintrag, t("e_mcp_kopiert")) }, t("e_mcp_zeile_knopf")),
        el("button", { class: "klein-knopf", type: "button", onclick: async () => {
          if (m.da && !confirm(t("e_mcp_neu_frage"))) return;
          try { const r = await schicken("/api/mcp/schluessel", {});
            dialog(t("e_mcp_neu_titel", { x: r.projekt }), el("div", { style: "display:grid;gap:10px" },
              el("p", { class: "leise", style: "margin:0" }, t("e_mcp_neu_h")),
              el("div", { class: "mono", style: "font-size:15px;overflow-wrap:anywhere;user-select:all;font-variant-ligatures:none" }, r.schluessel),
              el("button", { class: "knopf haupt", type: "button", onclick: () => kopieren(r.schluessel, t("e_mcp_kopiert")) }, t("e_mcp_kopieren"))));
            sichtEinstellungen(); } catch (e) { toast(t("fehler", { x: e.message }), true); } } }, t(m.da ? "e_mcp_erneuern" : "e_mcp_erzeugen")),
        el("span", { class: m.da ? "sehrleise" : "bernstein-text" }, m.da ? t("e_mcp_da", { x: zeit(m.erzeugt_utc) }) : t("e_mcp_fehlt"))));
  };
  const projektKarte = block([t("e_projekt"), " ", wirkt("projekt")], null,
    [[t("e_projekt_name"), pwahl, t("e_projekt_name_h")], [t("e_ordner"), pordner, t("e_ordner_h")],
     mitMeta("projekt", "takt_min", t("e_takt"), pf.takt_min, t("e_takt_h")), mitMeta("projekt", "speicher_grenze_gb", t("e_speicher"), pf.speicher_grenze_gb, t("e_speicher_h")),
     mitMeta("projekt", "stillstand_min", t("e_stillstand"), pf.stillstand_min, t("e_stillstand_h")), mitMeta("projekt", "lauf_ohne_angabe_min", t("e_lauf_ohne"), pf.lauf_ohne_angabe_min, t("e_lauf_ohne_h")),
     mitMeta("projekt", "ende_frist_min", t("e_ende_frist"), pf.ende_frist_min, t("e_ende_frist_h")),
     [t("e_entwickler"), pf.entwickler_name, t("e_entwickler_h")], [t("e_dateien"), pf.dateien_online, t("e_dateien_h")],
     [t("e_farbe"), pf.farbe, t("e_farbe_h")],
     [t("e_spec_vorlegen"), pf.spec_vorlegen, t("e_spec_vorlegen_h")], [t("e_spec_frei"), pf.spec_frei, t("e_spec_frei_h")],
     mitMeta("projekt", "info_ablage_h", t("e_info_ablage"), pf.info_ablage_h, t("e_info_ablage_h")),
     [t("e_limit_halt"), pf.limit_halt, t("e_limit_halt_h")],
     [t("e_abnahme_kette"), pf.abnahme_kette, t("e_abnahme_kette_h")], [t("e_merge_dienst"), pf.merge_dienst, t("e_merge_dienst_h")],
     [t("e_pruefstufen"), el("div", {}, pf.pruefstufen, " ", hilfeKnopf("release-takt")), t("e_pruefstufen_h")],
     [t("e_release_takt"), el("div", { style: "display:flex;gap:8px;align-items:center;flex-wrap:wrap" }, pf.release_takt, pf.release_zeit), t("e_release_takt_h")],
     [t("e_plan_automatik"), el("div", {}, pf.plan_automatik, " ", hilfeKnopf("planung")), t("e_plan_automatik_h")],
     [t("e_neue_aufgaben"), el("div", {}, pf.neue_aufgaben, " ", hilfeKnopf("planung")), t("e_neue_aufgaben_h")],
     [t("e_meilenstein_fertig"), el("div", {}, pf.meilenstein_fertig, " ", hilfeKnopf("planung")), t("e_meilenstein_fertig_h")],
     [t("e_versionen"), el("div", {}, pf.versionen, " ", hilfeKnopf("versionen")), t("e_versionen_h")],
     [t("e_merge_blick"), el("div", {}, pf.merge_blick, " ", hilfeKnopf("p-pakete")), t("e_merge_blick_h")],
     [t("e_merge_aussen_pruefung"), el("div", {}, pf.merge_aussen_pruefung, " ", hilfeKnopf("p-pakete")), t("e_merge_aussen_pruefung_h")],
     mitMeta("projekt", "version_frist_tage", t("e_version_frist"), pf.version_frist_tage, t("e_version_frist_h")),
     [t("e_schwer"), el("div", {}, pf.schwere_befehle, hilfeKnopf("schwere-laeufe")), t("e_schwer_h")],
     [t("e_empfehlung"), el("div", { style: "overflow-x:auto" }, empfTabelle, hilfeKnopf("agenten")), t("e_empfehlung_h")],
     ...(API || !d.mcp ? [] : [[t("e_mcp"), mcpFeld(d.mcp), t("e_mcp_h")]])],
    "projekt", () => ({ takt_min: wert(pf.takt_min), speicher_grenze_gb: wert(pf.speicher_grenze_gb),
      stillstand_min: wert(pf.stillstand_min), lauf_ohne_angabe_min: wert(pf.lauf_ohne_angabe_min),
      entwickler_name: pf.entwickler_name.value.trim(), dateien_online: pf.dateien_online.value, farbe: pf.farbe.value,
      spec_vorlegen: pf.spec_vorlegen.value, spec_frei: pf.spec_frei.value,
      info_ablage_h: wert(pf.info_ablage_h), limit_halt: wert(pf.limit_halt), abnahme_kette: pf.abnahme_kette.value, merge_dienst: pf.merge_dienst.value,
      pruefstufen: pf.pruefstufen.value, release_takt: pf.release_takt.value, release_zeit: pf.release_zeit.value, plan_automatik: pf.plan_automatik.value, neue_aufgaben: pf.neue_aufgaben.value, meilenstein_fertig: pf.meilenstein_fertig.value,
      versionen: pf.versionen.value, version_frist_tage: wert(pf.version_frist_tage),
      merge_blick: pf.merge_blick.value, merge_aussen_pruefung: pf.merge_aussen_pruefung.value, ende_frist_min: wert(pf.ende_frist_min),
      schwere_befehle: schwereBefehle(),
      empfehlung: Object.fromEntries(Object.entries(empfWahl).map(([gr, z]) => [gr, Object.fromEntries(Object.entries(z).map(([g, w]) => [g, w.value]))])) }));

  const p = d.pc;

  // Speicher und Abgleich – nur am PC; der Schlüssel wird nie angezeigt
  const tu = { url: text(d.turso.url), token: text("", "password"), abgleich: schalter(d.turso.abgleich), ca: text(d.turso.ca || ""),
    art: el("select", { id: "e-speicher-art" }, ["turso", "libsql"].map(a => el("option", { value: a }, t("e_art_" + a)))) };
  tu.art.value = d.turso.art || "turso";
  tu.token.placeholder = d.turso.schluessel_gespeichert ? t("e_token_da") : t("e_token_neu");
  const httpWarnung = el("div", { class: "bernstein-text", style: "font-size:12px;margin-top:4px", hidden: "hidden" }, t("e_http_warnung"));
  const artZeigen = () => { const eigen = tu.art.value === "libsql";               // Zertifikat nur beim eigenen Server
    tu.url.placeholder = eigen ? t("e_url_ph_libsql") : "libsql://\u2026.turso.io";
    tu.ca.closest(".feld")?.toggleAttribute("hidden", !eigen);
    httpWarnung.hidden = !(eigen && /^http:\/\//i.test(tu.url.value.trim())); };
  tu.art.addEventListener("change", artZeigen); tu.url.addEventListener("input", artZeigen);
  const ab = { abgleich_hoch_s: zahl(p.abgleich_hoch_s, 10, 3600), abgleich_puls_s: zahl(p.abgleich_puls_s, 60, 3600), abgleich_eingang_s: zahl(p.abgleich_eingang_s, 5, 600) };
  const speicherKarte = mitHilfe("online-speicher-turso", block([t("e_speicher_titel"), " ", wirkt("speicher")], API ? t("nur_pc") : t("e_turso_h"),
    [[t("e_art"), tu.art, t("e_art_h_neu")], [t("e_url"), el("div", {}, tu.url, httpWarnung)], [t("e_token"), tu.token, API ? null : t("e_token_h", { x: d.turso.datei || "" })],
     [t("e_ca"), tu.ca, t("e_ca_h")], [t("e_abgleich"), tu.abgleich],
     mitMeta("pc", "abgleich_hoch_s", t("e_hoch"), ab.abgleich_hoch_s), mitMeta("pc", "abgleich_puls_s", t("e_puls_pc"), ab.abgleich_puls_s),
     mitMeta("pc", "abgleich_eingang_s", t("e_eingang"), ab.abgleich_eingang_s)],
    async knopf => {                                   /* Zugang nur schicken, wenn er sich geändert hat – er wird beim Speichern geprüft */
      const zugangNeu = wert(tu.url) !== (d.turso.url || "") || tu.token.value.trim() || tu.abgleich.checked !== !!d.turso.abgleich
        || tu.art.value !== (d.turso.art || "turso") || wert(tu.ca) !== (d.turso.ca || "");
      if (zugangNeu && !await speichern("turso", { art: tu.art.value, url: wert(tu.url), token: tu.token.value.trim() || undefined,
        ca: tu.art.value === "libsql" ? wert(tu.ca) : "", abgleich: tu.abgleich.checked }, knopf)) return;
      await speichern("pc", Object.fromEntries(Object.entries(ab).map(([k, x]) => [k, wert(x)])), knopf); },
    null, !!API, API ? null : pruefKnopf("speicher", t("pv_speicher"))));
  artZeigen();

  // Online-Seite: Adresse (nur am PC) und die Grenzen der Anmeldung
  const seiteAdr = text(d.seite?.adresse || ""); seiteAdr.placeholder = "https://\u2026";
  const seiteWarnung = el("div", { class: "bernstein-text", style: "font-size:12px;margin-top:4px", hidden: "hidden" }, t("e_seite_http"));
  const seiteHttp = () => { seiteWarnung.hidden = !/^http:\/\//i.test(seiteAdr.value.trim()); };
  seiteAdr.addEventListener("input", seiteHttp); seiteHttp();
  const g = d.web_grenzen, w = {};
  if (d.web) for (const k of ["leerlauf_min", "hoechstens_h", "fehl_je_ip", "fehl_gesamt"]) w[k] = zahl(d.web[k], g[k][0], g[k][1]);
  const seiteKarte = !d.web && API ? null : block([t("e_web"), " ", wirkt("seite")], d.web ? t("e_web_h") : t("e_web_ohne"),
    [...(API ? [] : [[t("e_seite_adresse"), el("div", {}, seiteAdr, seiteWarnung), t("e_seite_adresse_h")]]),
     ...(d.web ? [mitMeta("web", "leerlauf_min", t("e_leerlauf"), w.leerlauf_min), mitMeta("web", "hoechstens_h", t("e_hoechstens"), w.hoechstens_h),
                  mitMeta("web", "fehl_je_ip", t("e_fehl_ip"), w.fehl_je_ip), mitMeta("web", "fehl_gesamt", t("e_fehl_ges"), w.fehl_gesamt)] : [])],
    async knopf => {
      if (!API && seiteAdr.value.trim() !== (d.seite?.adresse || "")) { if (!await speichern("push", { link: seiteAdr.value.trim() }, knopf)) return; d.seite.adresse = seiteAdr.value.trim(); }
      if (d.web) await speichern("web", Object.fromEntries(Object.entries(w).map(([k, x]) => [k, wert(x)])), knopf); },
    null, false, API ? null : pruefKnopf("seite", t("pv_seite")));
  if (seiteKarte) { mitHilfe("online-seite-webhoster", seiteKarte); seiteKarte.querySelector("h3").append(hilfeKnopf("zweiter-faktor", t("h_zweitfaktor"))); }

  // Benachrichtigungen aufs Handy – nur am PC (Zugangsdaten liegen nur dort)
  const pushKarte = API ? el("div", { class: "karte gesperrt" }, el("h3", {}, t("p_titel")), el("p", { class: "leise" }, t("nur_pc")))
    : await pushBlock(feld, text, zahl, schalter, wert, speichern);
  if (!API) pushKarte.querySelector("h3")?.insertBefore(wirkt("pc"), pushKarte.querySelector("h3 .hilfe-knopf"));

  // Dieser PC – nur am PC
  const wahl = (werte, v) => { const x = el("select", {}, werte.map(([k, l]) => el("option", { value: k }, l))); x.value = v; return x; };
  const pc = { rechner: text(p.rechner || ""), db_pfad: text(p.db_pfad), port: zahl(p.port, 1024, 65535), heimnetz: text(p.heimnetz || ""), cpu_laeufe: zahl(p.cpu_laeufe, 1, 8), leichte_laeufe: zahl(p.leichte_laeufe, 1, 32), vorrang_aufruecken_min: zahl(p.vorrang_aufruecken_min ?? 30, 0, 1440), vorrang_platz_freihalten: schalter(p.vorrang_platz_freihalten ?? true), speicher_reserve_gb: zahl(p.speicher_reserve_gb, 0, 64, 0.5), dauer_ab_gb: zahl(p.dauer_ab_gb ?? 4, 0, 256, 0.5), platte_gelb_prozent: zahl(p.platte_gelb_prozent ?? 15, 0, 100, 1), platte_rot_prozent: zahl(p.platte_rot_prozent ?? 5, 0, 100, 1), sicherungen_behalten: zahl(p.sicherungen_behalten ?? 10, 1, 1000), archiv_ordner: text(p.archiv_ordner || ""), lauf_hook: schalter(p.lauf_hook ?? true),
    produkt_entwickler: text(p.produkt_entwickler || ""), ki_fenster: text(p.ki_fenster || ""), ki_leerlauf_min: zahl(p.ki_leerlauf_min ?? 30, 5, 1440), ki_immer_an: text((p.ki_immer_an || []).join(", ")), aufsicht_s: zahl(p.aufsicht_s, 5, 600),
    bruecke_an: schalter(p.bruecke_an), bruecke_absender: text(p.bruecke_absender), bruecke_kopie_s: zahl(p.bruecke_kopie_s, 15, 3600), bruecke_lesekopie: schalter(p.bruecke_lesekopie ?? false),
    fernsitzung_prozess: text(p.fernsitzung_prozess || ""),
    schirm_zu_eingabe: schalter(p.schirm_zu_eingabe ?? true), schirm_zu_fernsitzung: schalter(p.schirm_zu_fernsitzung ?? true),
    schirm_zu_workbench: schalter(p.schirm_zu_workbench ?? true),
    sprache: wahl([["auto", t("e_sprache_auto")], ["de", "Deutsch"], ["en", "English"]], p.sprache || "auto"), claude_link: schalter(p.claude_link ?? true) };
  pc.fernsitzung_prozess.placeholder = t("e_fern_ph");
  pc.heimnetz.placeholder = t("e_heimnetz_ph");
  /* Vorrang der Projekte (A1623): je Projekt dieses PCs eine Auswahl; gespeichert wird nur, was nicht „normal“ ist */
  pc.vorrang = el("div", { class: "vorrang-liste", id: "e-vorrang" }, ...(p.vorrang_projekte || []).map(n => el("label", {}, el("span", {}, n),
    wahl(["hoch", "normal", "niedrig"].map(s => [s, t("vr_" + s)]), (p.vorrang || {})[n] || "normal"))));
  pc.vorrang._wert = () => Object.fromEntries([...pc.vorrang.querySelectorAll("label")].map(x => [x.firstChild.textContent, x.querySelector("select").value]).filter(([, s]) => s !== "normal"));
  if (API) pc.vorrang.querySelectorAll("select").forEach(x => { x.disabled = true; });
  const pcFeld = (k, beschriftung, hilfe) => mitMeta("pc", k, beschriftung, pc[k], hilfe);
  const pcWerte = () => Object.fromEntries(Object.entries(pc).map(([k, x]) => [k, x._wert ? x._wert() : wert(x)]));
  const pcStart = pcWerte();
  const pcKarte = block([t("e_pc"), " ", wirkt("pc")], API ? t("nur_pc") : t("e_pc_h"), [
    pcFeld("rechner", t("e_rechner"), t("e_rechner_h")), pcFeld("sprache", t("e_sprache"), t("e_sprache_h")), pcFeld("claude_link", t("e_claude_link"), t("e_claude_link_h")),
    pcFeld("db_pfad", t("e_db")), pcFeld("port", t("e_port")), pcFeld("heimnetz", t("e_heimnetz"), t("e_heimnetz_h")), pcFeld("cpu_laeufe", t("e_cpu"), t("e_cpu_h")), pcFeld("leichte_laeufe", t("e_leicht"), t("e_leicht_h")), [t("e_vorrang"), pc.vorrang, t("e_vorrang_h")], pcFeld("vorrang_aufruecken_min", t("e_vr_auf"), t("e_vr_auf_h")), pcFeld("vorrang_platz_freihalten", t("e_vr_platz"), t("e_vr_platz_h")), pcFeld("speicher_reserve_gb", t("e_reserve"), t("e_reserve_h")), pcFeld("dauer_ab_gb", t("e_dauer"), t("e_dauer_h")), pcFeld("platte_gelb_prozent", t("e_platte_gelb"), t("e_platte_h")), pcFeld("platte_rot_prozent", t("e_platte_rot")), pcFeld("sicherungen_behalten", t("e_sich"), t("e_sich_h")), pcFeld("archiv_ordner", t("e_archiv"), t("e_archiv_h")), pcFeld("lauf_hook", t("e_laufhook"), t("e_laufhook_h")), pcFeld("produkt_entwickler", t("e_kanal"), t("e_kanal_h")),
    pcFeld("ki_fenster", t("e_kifenster"), t("e_kifenster_h")), pcFeld("ki_leerlauf_min", t("e_ki_leerlauf"), t("e_ki_leerlauf_h")), pcFeld("ki_immer_an", t("e_ki_immer"), t("e_ki_immer_h")), pcFeld("aufsicht_s", t("e_aufsicht")), pcFeld("bruecke_an", t("e_bruecke")),
    pcFeld("bruecke_absender", t("e_absender")), pcFeld("bruecke_lesekopie", t("e_lesekopie"), t("e_lesekopie_h")), pcFeld("bruecke_kopie_s", t("e_kopie")), pcFeld("fernsitzung_prozess", t("e_fern"), t("e_fern_h")),
    [t("e_bs_titel"), el("div", { class: "sehrleise", style: "padding-top:7px;font-size:13px" }, t("e_bs_h"), " ", hilfeKnopf("bildschirm"))],
    pcFeld("schirm_zu_eingabe", t("e_bs_eingabe"), t("e_bs_eingabe_h")), pcFeld("schirm_zu_fernsitzung", t("e_bs_fern"), t("e_bs_fern_h")),
    pcFeld("schirm_zu_workbench", t("e_bs_wb"), t("e_bs_wb_h")),
    ...(API || !d.rechner ? [] : [[t("e_laufwerke"), el("div", { id: "e-laufwerke", style: "padding-top:7px;font-size:13px" }, ...d.rechner.laufwerke.map(l =>
        el("div", { class: l.stufe === "rot" ? "rot" : l.stufe === "gelb" ? "bernstein" : "" }, t("e_laufwerk", { x: l.laufwerk, n: zahlKurz(l.frei_gb), g: zahlKurz(l.gesamt_gb), p: zahlKurz(l.frei_prozent) }))))],
      [t("e_aufr"), aufraeumListe(d.rechner.aufraeumen), t("e_aufr_h", { x: d.rechner.aufraeumen.ordner })],
      [t("e_zuwachs"), ordnerListe(d.rechner.zuwaechse || [], x => t("e_zuwachs_zeile", { g: zahlKurz(x.bytes / 2 ** 30), p: zahlKurz(x.plus / 2 ** 30) }), "e-zuwaechse"), t("e_zuwachs_h")],
      [t("e_ablage"), ordnerListe(d.rechner.ablagerungen || [], x => t(x.tage != null ? "e_ablage_zeile" : "e_ablage_zeile0", { g: zahlKurz(x.bytes / 2 ** 30), n: x.tage, a: t("e_art_" + x.art) }), "e-ablagerungen"), t("e_ablage_h")],
      [t("e_cl"), claudeListe(d.rechner.claude || {}), t("e_cl_h")]]),
    ...(API ? [] : [[t("e_datei"), anzeige(p.datei, true), t("e_datei_h")]])],
    async knopf => {                    /* A1703: nur, was du hier geändert hast – ein älter geladenes Formular (zweiter Tab,
                                           Handy im Heimnetz) überschreibt so keine Werte, die inzwischen anders gesetzt wurden */
      const jetzt = pcWerte(), neu = Object.fromEntries(Object.entries(jetzt).filter(([k, v]) => JSON.stringify(v) !== JSON.stringify(pcStart[k])));
      if (await speichern("pc", neu, knopf, pc)) Object.assign(pcStart, neu); }, null, !!API);

  // Betriebsart: drei Karten mit ihren Folgen; darunter jede Adresse, zu der diese Installation eine Verbindung aufbaut
  const ba = d.betriebsart || { aktuell: "cloud", gewaehlt: "" };
  let baWahl = ba.aktuell;
  const baKarten = el("div", { class: "ba-karten" });
  const baZeichnen = () => baKarten.replaceChildren(...["pc", "server", "cloud"].map(k => el("button", { type: "button", class: "ba-karte" + (k === baWahl ? " an" : ""),
    disabled: API ? "disabled" : null, "data-art": k, onclick: () => { baWahl = k; baZeichnen(); } },
    el("b", {}, t("ba_" + k)), el("span", {}, t("ba_" + k + "_h")), k === "server" ? el("span", { class: "sehrleise" }, t("ba_server_dazu")) : null)));
  baZeichnen();
  const baListe = el("div", { class: "ba-liste" });
  const baLaden = async was => {
    try { const r = await abrufen("/api/pruefen?was=" + was);
      baListe.replaceChildren(...[el("table", { class: "tab" }, el("tr", {}, ["ba_wer", "ba_ziel", "ba_fuehrt", "ba_zustand"].map(k => el("th", {}, t(k)))),
        ...r.zeilen.map(x => el("tr", { class: x.aktiv && !x.erlaubt ? "ba-fehler" : null },
          el("td", {}, t("ba_wer_" + x.wer) + (x.zusatz ? ` (${x.zusatz})` : "")), el("td", { class: "mono" }, `${x.rechner}:${x.port}`), el("td", {}, t("ba_stufe_" + x.stufe)),
          el("td", { class: x.erlaubt ? "" : "rot-text" }, t(!x.erlaubt ? (x.aktiv ? "ba_gesperrt_an" : "ba_gesperrt") : x.nur_pruefung ? "ba_nur_pruefung" : x.aktiv ? "ba_erlaubt" : "ba_aus")
            + (x.erreichbar === true ? " · \u2713 " + t("ba_erreichbar") : x.erreichbar === false ? " · \u2717 " + t("ba_nicht_erreichbar") : ""))))),
        r.fehler ? el("p", { class: "rot-text", style: "margin:8px 0 0" }, t("ba_fehler", { n: r.fehler })) : null].filter(Boolean));
    } catch (f) { baListe.replaceChildren(el("div", { class: "rot-text" }, f.message)); } };
  const baPruefen = el("button", { class: "klein-knopf", type: "button" }, t("ba_pruefen"));
  baPruefen.addEventListener("click", async () => { baPruefen.disabled = true; await baLaden("erreichbar"); baPruefen.disabled = false; });
  const baKarte = mitHilfe("betriebsart", block([t("ba_titel"), " ", wirkt("pc")], (API ? t("nur_pc") + " " : "") + (ba.gewaehlt ? t("ba_h") : t("ba_h_ungewaehlt", { x: t("ba_" + ba.aktuell) })), [],
    async knopf => { if (await speichern("pc", { betriebsart: baWahl }, knopf)) zeige("einstellungen", true); }, null, !!API,
    el("div", {}, baKarten, API ? null : el("div", { class: "pruef" }, el("div", { class: "pruef-kopf" }, el("b", {}, t("ba_verbindungen")), baPruefen,
      el("span", { class: "sehrleise" }, t("ba_ausserhalb"))), baListe))));
  if (!API) baLaden("verbindungen");

  // Reihenfolge: erst, was die Installation trägt (Betriebsart, Speicher, Seite, Meldungen, PC), dann das Projekt und seine Agenten
  const benutzerKarte = API && !darfBenutzer() ? null : mitHilfe("benutzer", el("div", { class: "karte", id: "e-benutzer" },
    el("h3", {}, t("bn_titel"), " ", wirkt("seite")), el("p", { class: "leise", style: "margin:0 0 12px" }, t("bn_h")),
    el("div", { class: "bn-inhalt" }, el("div", { class: "sehrleise" }, "…"))));
  if (benutzerKarte) benutzerZeichnen(benutzerKarte.querySelector(".bn-inhalt"));
  box.append(...[baKarte, speicherKarte, seiteKarte, benutzerKarte, pushKarte, pcKarte, projektKarte,
    agentenEinstellungen(d, { text, zahl, schalter, wert, feld })].filter(Boolean));
  /* Sprungmarken: die Seite ist lang – jeder Abschnitt mit einem Klick erreichbar */
  m.append(el("div", { class: "sprung" }, [...box.children].map(k => { const h = k.querySelector("h3");
    const text = h && [...h.childNodes].filter(n => n.nodeType === Node.TEXT_NODE).map(n => n.textContent).join("").trim();
    return h ? el("a", { onclick: () => k.scrollIntoView({ behavior: "smooth", block: "start" }) }, text || h.textContent) : null; }).filter(Boolean)));
  m.append(box);
}
/* Einstellungen › Agenten. Links die Agenten, rechts der gewählte in vier Blöcken. „Lead“ ist ein Schalter (führt das
   Projekt), das Fachgebiet frei mit Vorschlägen, die Arbeitsweise bestimmt, was die AMW tut: nur „Terminal“ startet und
   überwacht sie selbst; „Chat“ hat weder Sitzung noch Überwachung. Sitzungs-Felder (Profil) nur am PC. */
const FACHGEBIETE = ["Code", "Grafik", "Daten", "Prüfen", "Merge", "Ausarbeiten", "KI", "3D", "Doku"];
function agentenEinstellungen(d, h) {
  const karte = el("div", { class: "karte ae", id: "agenten-einstellungen" }, el("h3", {}, t("ae_titel")));
  const aktiv = d.agenten.filter(a => !a.entfernt_utc), entfernt = d.agenten.filter(a => a.entfernt_utc);
  let gewaehlt = gemerkt("amw-ae") && aktiv.some(a => a.kennung === gemerkt("amw-ae")) ? gemerkt("amw-ae") : aktiv[0]?.kennung;
  const tunAgent = async (weg, k, frage, ok) => { if (frage && !confirm(frage)) return;
    try { const r = await schicken(weg, { kennung: k }); if (!r.unterwegs) toast(ok(r)); zeige("einstellungen", true); }
    catch (e) { toast(t("fehler", { x: e.message }), true); } };
  const verlaufText = v => Object.entries(v || {}).map(([k, n]) => t("ae_v_" + k, { n })).join(", ");
  const weiseZeichen = a => tmZeichen(a.arbeitsweise === "chat" ? "chat" : a.arbeitsweise === "desktop" ? "desktop" : "sitzung", t("ae_w_" + (a.arbeitsweise || "terminal")));
  const zeichnen = () => {
    const a = aktiv.find(x => x.kennung === gewaehlt);
    const liste = el("div", { class: "ae-wahl" }, aktiv.map(x => el("button", { type: "button", class: x.kennung === gewaehlt ? "an" : null,
        onclick: () => { gewaehlt = x.kennung; try { localStorage.setItem(ablage("amw-ae"), gewaehlt); } catch (e) {} zeichnen(); } },
        weiseZeichen(x), el("span", { class: "tm-name" }, x.kennung), tmFach(x), x.soll !== "an" ? el("span", { class: "sehrleise" }, t("soll_" + x.soll)) : null)),
      neuerAgent(),
      entfernt.length ? el("details", { class: "ae-entfernt", id: "ae-entfernt" }, el("summary", {}, t("ae_entfernt_liste", { n: entfernt.length })),
        ...entfernt.map(x => el("div", { class: "ae-entfernt-zeile" }, el("span", { class: "tm-name" }, x.kennung),
          el("span", { class: "sehrleise" }, t("ae_entfernt_seit", { x: zeit(x.entfernt_utc) })),
          el("button", { class: "klein-knopf", type: "button", onclick: () => tunAgent("/api/agent/wiederaufnehmen", x.kennung, null, () => t("ae_wieder_ok", { x: x.kennung })) },
            t("ae_wieder"))))) : null);
    karte.replaceChildren(el("h3", {}, t("ae_titel"), hilfeKnopf("agenten")), el("p", { class: "leise", style: "margin:0 0 12px" }, t("ae_h")), el("div", { class: "ae-raster klebt" }, liste, a ? formular(a) : el("div", { class: "leer" }, t("ae_keiner"))));
  };
  /* Entfernen: stilllegen und ausblenden, Verlauf bleibt. Endgültig löschen nur ohne Verlauf – sonst ausgegraut mit Grund.
     Online nur für System-Admins (sonst ausgegraut). */
  const entfernenBlock = a => {
    const darf = !API || zustand.start?.online?.ich?.rolle === "system_admin", vt = verlaufText(a.verlauf);
    const sperre = darf ? null : t("schirm_nur_admin_kurz");
    const knopf = (text, tun, klasse, grund) => el("button", { class: "klein-knopf " + (klasse || ""), type: "button", onclick: tun,
      ...(grund ? { disabled: "disabled", title: grund, "aria-label": `${text} – ${grund}` } : {}) }, text);
    return el("div", { class: "ae-weg" }, el("div", { class: "lt" }, t("ae_weg_titel")),
      el("p", { class: "sehrleise", style: "margin:4px 0 8px" }, t("ae_weg_h")),
      el("div", { class: "zeile" },
        knopf(t("ae_entfernen"), () => tunAgent("/api/agent/entfernen", a.kennung,
          t(a.laeuft ? "ae_entfernen_frage_laeuft" : "ae_entfernen_frage", { x: a.kennung }),
          r => t(r.endet ? "ae_entfernt_ok_endet" : "ae_entfernt_ok", { x: a.kennung, b: r.bis_utc ? zeit(r.bis_utc) : "" })), "rot", sperre),
        knopf(t("ae_loeschen"), () => tunAgent("/api/agent/loeschen", a.kennung, t("ae_loeschen_frage", { x: a.kennung }), () => t("ae_geloescht", { x: a.kennung })),
          "", sperre || (vt ? t("ae_loeschen_nicht", { x: vt }) : null))),
      vt ? el("div", { class: "sehrleise", style: "font-size:12px;margin-top:6px" }, t("ae_verlauf", { x: vt })) : null);
  };
  const neuerAgent = () => { const k = h.text(""); k.placeholder = t("e_neu_ph");
    const knopf = el("button", { class: "klein-knopf", type: "button" }, t("e_anlegen"));
    knopf.addEventListener("click", async () => { const name = k.value.trim(); if (!name) { k.focus(); return; }
      await einmalTun("agent/" + name, async () => { await schicken("/api/einstellungen/agent", { kennung: name, neu: true });      /* A2117: wirkt beim ersten Klick */
        try { localStorage.setItem(ablage("amw-ae"), name); } catch (e) {} toast(t("gespeichert")); zeige("einstellungen", true); }); });
    return el("div", { class: "ae-neu" }, k, knopf); };
  const formular = a => {
    const wahl = (werte, v) => { const x = el("select", {}, werte.map(([w, l]) => el("option", { value: w }, l))); x.value = v; return x; };
    const lang = v => el("textarea", { rows: 2 }, v || "");
    const f = { lead: h.schalter(a.rolle === "lead"), fach: h.text(a.fachgebiet), zust: lang(a.zustaendig), nicht: lang(a.fasst_nicht_an), rund: h.schalter(a.empfaengt_rund),
      weise: wahl([["terminal", t("ae_w_terminal")], ["desktop", t("ae_w_desktop")], ["chat", t("ae_w_chat")]], a.arbeitsweise || "terminal"),
      soll: wahl(["an", "ruht", "aus"].map(x => [x, t("ae_soll_" + x)]), a.soll || "an"), puls: h.zahl(Math.round((a.puls_grenze_s || 120) / 60), 1, 1440),
      ordner: h.text(a.ordner), zusatz: h.text((a.zusatzordner || []).join("; ")), modell: h.text(a.modell),
      denkstufe: wahl([["", t("pr_vorgabe")], ...["low", "medium", "high", "xhigh", "max"].map(x => [x, x])], a.denkstufe || ""),
      rechte: wahl([["vorgabe", t("pr_r_vorgabe")], ["auto", t("pr_r_auto")], ["umgehen", t("pr_r_umgehen")]], a.rechte || "vorgabe"),
      fern: h.schalter(a.fernsteuerung ?? 1), neustart: h.schalter(a.neustart_auto), startsatz: el("textarea", { rows: 3 }, a.startsatz || "") };
    f.fach.setAttribute("list", "ae-fachgebiete"); f.fach.placeholder = t("ae_fach_ph"); f.ordner.placeholder = "F:\\projekt"; f.zusatz.placeholder = "F:\\a; F:\\b";
    const fachListe = el("datalist", { id: "ae-fachgebiete" }, [...new Set([...FACHGEBIETE, ...d.agenten.map(x => x.fachgebiet).filter(Boolean)])].map(x => el("option", { value: x })));
    const block = (titel, ...inhalt) => el("div", { class: "ae-block" }, el("h4", {}, titel), ...inhalt.flat());
    const weiseHinweis = el("div", { class: "sehrleise", style: "font-size:12px;margin-top:3px" });
    const sitzung = block(t("ae_sitzung"), API ? el("p", { class: "leise", style: "margin:0" }, t("ae_sitzung_netz")) : [
      h.feld(t("pr_ordner"), f.ordner), h.feld(t("pr_zusatz"), f.zusatz, t("pr_zusatz_h")), h.feld(t("pr_modell") + " · " + t("pr_denkstufe"), el("div", { class: "ae-zwei" }, f.modell, f.denkstufe)),
      h.feld(t("pr_rechte"), f.rechte, t("pr_rechte_h")), h.feld(t("pr_fern"), f.fern, t("pr_fern_h")), h.feld(t("pr_neustart"), f.neustart, t("pr_neustart_h")),
      h.feld(t("pr_startsatz"), f.startsatz, t("pr_startsatz_h"))]);
    const startbefehl = a.start && darfStartbefehl() ? block(t("sb_block"), startbefehlBlock(a.start)) : null;
    const ueberwachung = block(t("ae_ueberwachung"), h.feld(t("ae_soll"), f.soll, t("ae_soll_h")),
      h.feld(t("ae_puls"), el("div", { class: "ae-zwei", style: "align-items:center" }, f.puls, el("span", { class: "leise" }, t("ae_puls_x"))), t("ae_puls_h")));
    const nachWeise = () => { const w = f.weise.value; sitzung.hidden = w !== "terminal"; if (startbefehl) startbefehl.hidden = w !== "terminal";
      ueberwachung.hidden = w === "chat"; weiseHinweis.textContent = t("ae_weise_h_" + w); };
    f.weise.addEventListener("change", nachWeise);
    const vorschlag = el("div", { class: "ae-vorschlag" }, el("span", { class: "leise" }, t("ae_vorschlag_h")), el("button", { class: "klein-knopf", type: "button", onclick: async ev => {
      const knopf = ev.currentTarget; knopf.disabled = true;
      try { const v = await abrufen("/api/agent/vorschlag?kennung=" + encodeURIComponent(a.kennung));
        if (!v.fachgebiet && !v.zustaendig) { vorschlag.replaceChildren(el("span", { class: "leise" }, t("ae_vorschlag_nichts", { x: v.grundlage }))); return; }
        vorschlag.replaceChildren(el("span", {}, el("b", {}, t("ae_vorschlag") + " "), [v.fachgebiet ? t("ae_fach") + ": " + v.fachgebiet : null, v.zustaendig ? t("ae_zust") + ": " + v.zustaendig : null].filter(Boolean).join(" · "),
          el("span", { class: "sehrleise" }, " (" + v.grundlage + ")")), el("button", { class: "klein-knopf", type: "button", onclick: () => {
            if (v.fachgebiet && !f.fach.value.trim()) f.fach.value = v.fachgebiet; if (v.zustaendig && !f.zust.value.trim()) f.zust.value = v.zustaendig; toast(t("ae_uebernommen")); } }, t("ae_uebernehmen")));
      } catch (e) { toast(t("fehler", { x: e.message }), true); knopf.disabled = false; } } }, t("ae_vorschlag_holen")));
    const speichernKnopf = el("button", { class: "knopf haupt", type: "button" }, t("speichern"));
    speichernKnopf.addEventListener("click", async () => {
      speichernKnopf.disabled = true;
      try {
        const w = f.weise.value;
        await schicken("/api/einstellungen/agent", { kennung: a.kennung, rolle: f.lead.checked ? "lead" : "", fachgebiet: f.fach.value.trim(), arbeitsweise: w,
          zustaendig: f.zust.value.trim(), fasst_nicht_an: f.nicht.value.trim(), empfaengt_rund: f.rund.checked,
          ...(w === "chat" ? {} : { soll: f.soll.value, puls_grenze_s: (h.wert(f.puls) || 2) * 60 }) });
        if (!API && w === "terminal") await schicken("/api/einstellungen/profil", { kennung: a.kennung, ordner: f.ordner.value.trim(), zusatzordner: f.zusatz.value,
          denkstufe: f.denkstufe.value, modell: f.modell.value.trim(), rechte: f.rechte.value, fernsteuerung: f.fern.checked, neustart_auto: f.neustart.checked, startsatz: f.startsatz.value.trim() });
        toast(t("gespeichert")); zeige("einstellungen", true);
      } catch (e) { toast(fehlerSatz(e), true); } finally { speichernKnopf.disabled = false; } });
    const form = el("div", { class: "ae-form", "data-k": a.kennung }, fachListe,
      block(t("ae_wer"), h.feld(t("e_kennung"), el("span", { class: "tm-name" }, a.kennung), t("ae_kennung_h")),
        h.feld(t("ae_lead"), el("label", { class: "ae-haken" }, f.lead, " " + t("ae_lead_x")), t("ae_lead_h")), h.feld(t("ae_fach"), f.fach, t("ae_fach_h")),
        h.feld(t("ae_weise"), el("div", {}, f.weise, weiseHinweis))),
      block(t("ae_auftrag"), h.feld(t("ae_zust"), f.zust), h.feld(t("ae_nicht"), f.nicht), h.feld(t("e_rund"), el("label", { class: "ae-haken" }, f.rund, " " + t("ae_rund_x"))), API ? null : vorschlag),
      sitzung, startbefehl, ueberwachung, el("div", { class: "ae-knoepfe" }, speichernKnopf, el("span", { class: "sehrleise" }, t("ae_speichern_h"))),
      entfernenBlock(a));
    nachWeise();
    return form;
  };
  zeichnen();
  return karte;
}
/* Zahnrad „Benachrichtigungen“: Hauptschalter, Anbieter (Geheimnisse nur als „gespeichert“), Ereignisse, Ruhezeit,
   Probe je Anbieter mit Antwort der API, Versandprotokoll. */
async function pushBlock(feld, text, zahl, schalter, wert, speichern) {
  let d; try { d = await holen("/api/push"); } catch (e) { return el("div", { class: "karte" }, el("h3", {}, t("p_titel")), String(e)); }
  const c = d.einstellungen, geheim = (gespeichert) => { const x = text("", "password"); x.placeholder = gespeichert ? t("e_token_da") : ""; return x; };
  const f = {
    an: schalter(c.an), max: zahl(c.max_je_stunde, 1, 60),
    ruhe_an: schalter(c.ruhe.an), ruhe_von: text(c.ruhe.von, "time"), ruhe_bis: text(c.ruhe.bis, "time"),
    ntfy_an: schalter(c.ntfy.an), ntfy_server: text(c.ntfy.server), ntfy_topic: geheim(c.ntfy.topic_gespeichert), ntfy_token: geheim(c.ntfy.token_gespeichert),
    po_an: schalter(c.pushover.an), po_app: geheim(c.pushover.app_token_gespeichert), po_user: geheim(c.pushover.user_key_gespeichert),
    tg_an: schalter(c.telegram.an), tg_token: geheim(c.telegram.bot_token_gespeichert), tg_chat: text(c.telegram.chat_id),
  };
  const ereig = Object.fromEntries(d.ereignisse.map(e => [e, schalter(c.ereignisse[e])]));
  const knopf = el("button", { class: "knopf haupt", type: "button" }, t("speichern"));
  const sammeln = () => ({
    an: f.an.checked, max_je_stunde: wert(f.max),
    ruhe: { an: f.ruhe_an.checked, von: f.ruhe_von.value, bis: f.ruhe_bis.value },
    ntfy: { an: f.ntfy_an.checked, server: wert(f.ntfy_server), topic: f.ntfy_topic.value.trim(), token: f.ntfy_token.value.trim() },
    pushover: { an: f.po_an.checked, app_token: f.po_app.value.trim(), user_key: f.po_user.value.trim() },
    telegram: { an: f.tg_an.checked, bot_token: f.tg_token.value.trim(), chat_id: wert(f.tg_chat) },
    ereignisse: Object.fromEntries(Object.entries(ereig).map(([k, x]) => [k, x.checked])),
  });
  let stand = JSON.stringify(sammeln());
  knopf.addEventListener("click", () => { const x = sammeln(); speichern("push", x, knopf).then(ok => { if (ok) stand = JSON.stringify(x); }); });
  /* Probe: Ergebnis direkt unter dem Knopf; ungespeicherte Änderungen zuerst speichern – die Probe nimmt das Gespeicherte */
  const probe = anbieter => { const b = el("button", { class: "klein-knopf", type: "button" }, t("p_probe", { x: anbieter }));
    const aus = el("div", { class: "mono", role: "status", style: "margin-top:6px;white-space:pre-wrap" });
    b.addEventListener("click", async () => { b.disabled = true; aus.className = "sehrleise mono"; aus.textContent = t("p_probe_laeuft");
      try {
        const x = sammeln(), neu = JSON.stringify(x) !== stand;
        if (neu) { await schicken("/api/einstellungen/push", x); stand = JSON.stringify(x); }
        const r = await schicken("/api/push/probe", { anbieter }), fehler = Object.values(r.probe).find(v => v !== "ok");
        aus.className = "mono";
        aus.replaceChildren(neu ? el("div", { class: "leise" }, t("p_probe_gespeichert")) : "", ...Object.entries(r.probe).map(([a, v]) =>
          el("div", { class: v === "ok" ? "" : "rot-text" }, `${a}: ${v === "ok" ? t("p_probe_ok") : v}`)));
        toast(fehler ? `${anbieter}: ${fehler}` : `${anbieter}: ${t("p_probe_ok")}`, !!fehler);
      } catch (e) { aus.className = "rot-text mono"; aus.textContent = e.message; toast(e.message, true); }
      finally { b.disabled = false; } });
    return el("div", {}, b, aus); };
  const gruppe = (titel, felder, anbieter) => el("div", { class: "push-gruppe" }, el("h4", {}, titel),
    ...felder.map(([b, x, h]) => feld(b, x, h)), anbieter ? probe(anbieter) : null);
  const protokoll = d.protokoll.length ? el("table", { class: "tab" }, el("tr", {}, ["k_zeit", "k_titel", "k_ergebnis"].map(k => el("th", {}, t(k)))),
      ...d.protokoll.slice(0, 12).map(p => el("tr", {}, el("td", {}, zeit(p.geaendert_utc)), el("td", {}, p.titel),
        el("td", { class: p.ergebnis === "gesendet" ? "" : "rot-text" }, p.ergebnis + (p.fehler ? ` – ${p.fehler}` : "")))))
    : el("div", { class: "sehrleise" }, t("p_leer"));
  return el("div", { class: "karte" }, el("h3", {}, t("p_titel"), hilfeKnopf("ntfy")), el("p", { class: "leise", style: "margin:0 0 12px" }, t("p_h", { x: c.datei })),
    feld(t("p_an"), f.an, t("p_an_h")),
    gruppe("ntfy", [[t("p_an_kurz"), f.ntfy_an], [t("p_server"), f.ntfy_server], [t("p_kanal"), f.ntfy_topic, t("p_kanal_h")], [t("p_token"), f.ntfy_token, t("p_optional")]], "ntfy"),
    gruppe("Pushover", [[t("p_an_kurz"), f.po_an], [t("p_app"), f.po_app], [t("p_user"), f.po_user]], "pushover"),
    gruppe("Telegram", [[t("p_an_kurz"), f.tg_an], [t("p_bot"), f.tg_token], [t("p_chat"), f.tg_chat, t("p_chat_h")]], "telegram"),
    gruppe(t("p_ereignisse"), d.ereignisse.map(e => [t("pe_" + e), ereig[e]])),
    gruppe(t("p_ruhe"), [[t("p_an_kurz"), f.ruhe_an, t("p_ruhe_h")], [t("p_von"), f.ruhe_von], [t("p_bis"), f.ruhe_bis], [t("p_max"), f.max]]),
    el("div", { style: "margin-top:12px" }, knopf),
    el("h4", { style: "margin-top:18px" }, t("p_protokoll")), el("div", { style: "overflow-x:auto" }, protokoll));
}

/* Takt (15 s): Start und Betrieb neu laden, sonst Kopf + Stempel der offenen Sicht (siehe standPruefen); Projektliste frisch. */
setInterval(async () => {
  if (document.hidden) return;
  holen("/api/projekte").then(d => { projekte = d.projekte || projekte; }).catch(() => {});
  if (zustand.sicht === "start" || zustand.sicht === "betrieb") { if (stoerfrei()) zeige(zustand.sicht, true); else kopfAktualisieren(); return; }
  await kopfAktualisieren(); standPruefen();
}, 15000);
window.addEventListener("popstate", () => { const s = location.hash.slice(1); if (s && s !== zustand.sicht) zeige(s); });
window.addEventListener("hashchange", () => { const s = location.hash.slice(1); if (s && s !== zustand.sicht) zeige(s); });
projekteLaden().then(() => {
  let startSicht = gemerkt("amw-sicht") || "start";
  if (location.hash.length > 1) startSicht = location.hash.slice(1);
  const s = seitenNr;                                    /* A1907: nur einem echten Wechsel weichen – nicht dem Takt, der still „start“ zeichnet */
  return kopfLaden().then(() => { if (s === seitenNr) return Promise.resolve(zeige(startSicht)).then(kzNachWechsel); });   /* A2014: Treffer aus einem anderen Projekt */
});

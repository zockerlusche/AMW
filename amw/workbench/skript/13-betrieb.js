/* --- Betrieb ------------------------------------------------------------------------------- */
/* Betrieb › „Wofür das Geld geht“ (A1642): Verbrauch nach Anlass, teuerster zuerst, mit Anteil und „vermeidbar“ */
function anlassTeil(m) {
  const ziel = el("div", {}, el("div", { class: "sehrleise" }, "…"));
  let tage = 7;
  const name = r => { const k = "anl_" + r.kennung; const x = t(k); return x && x !== k ? x : r.anlass; };
  const laden = async () => {
    let d; try { d = await holen("/api/verbrauch/anlass?tage=" + tage); } catch (e) { ziel.replaceChildren(el("div", { class: "leer" }, String(e.message || e))); return; }
    const wahl = el("div", { class: "reiter anl-tage" }, [1, 7, 30].map(n => el("button", { type: "button", class: n === tage ? "an" : "",
      onclick: () => { tage = n; laden(); } }, n === 1 ? t("anl_tag") : t("anl_tage", { n }))));
    if (!d.zeilen.length) { ziel.replaceChildren(wahl, el("div", { class: "leer" }, t("anl_leer"))); return; }
    ziel.replaceChildren(wahl,
      el("p", { class: "leise" }, t(d.tage === 1 ? "anl_summe_1" : "anl_summe", { g: d.gesamt.toFixed(2), n: d.tage, v: d.vermeidbar_usd.toFixed(2), w: d.vermeidbar_weckrufe, a: d.weckrufe })),
      tabelle(["k_anlass", "k_kosten_spalte", "k_anteil", "k_weckrufe", "k_je_weckruf"], d.zeilen.map(r => [
        el("span", {}, name(r), r.vermeidbar ? el("span", { class: "etikett anl-vermeidbar", style: "margin-left:6px" }, t("anl_vermeidbar")) : null),
        r.usd.toFixed(2) + " $",
        el("span", { class: "anl-anteil" }, el("i", { style: `width:${Math.max(1, Math.round(r.anteil))}%` }), ` ${r.anteil} %`),
        r.weckrufe || "–", r.je_weckruf == null ? "–" : r.je_weckruf.toFixed(2) + " $"])),
      nlZeile(d.nachlesen),
      el("p", { class: "sehrleise", style: "font-size:12px" }, t("anl_h")));
  };
  /* A1757: lesen Agenten nach einem Weckruf noch nach? Und was kostet ein Weckruf vor/nach der Version mit Inhalt? */
  const nlZeile = n => !n ? null : el("p", { class: "leise", id: "anl-nachlesen" },
    n.weckrufe ? t("anl_nachlesen", { n: n.nachgelesen, w: n.weckrufe, p: zahlKurz(n.anteil) }) : t("anl_nachlesen_leer"),
    n.vorher != null && n.nachher != null ? " · " + t(n.tage === 1 ? "anl_je_weckruf_1" : "anl_je_weckruf", { v: n.version, a: n.vorher.toFixed(2), b: n.nachher.toFixed(2), n: n.tage }) : null);
  m.append(el("h2", {}, t("anl_titel")), ziel);
  laden();
}
function gesundheitTeil(m, g) {
  if (!g || !g.teile) return;
  const farbe = { gruen: "gruen", gelb: "bernstein", rot: "rot", aus: "" };
  const zeilen = g.teile.filter(x => x.zustand !== "aus" || x.runden);
  m.append(...[el("h2", {}, t("gs_titel"), hilfeKnopf("dienst")), g.quelle === "alt" ? el("div", { class: "leer" }, t("gs_alt")) : null,
    zeilen.length ? tabelle(["k_teil", "k_zustand", "k_letzte_runde", "k_dauer", "k_neustarts", "k_fehler"], zeilen.map(x => [
      t("gs_" + x.teil),
      el("span", { class: "gs-zustand" }, el("span", { class: "punkt " + farbe[x.zustand] }), t("gs_" + x.zustand)),
      x.alter_s == null ? "–" : t("gs_vor", { n: x.alter_s }),
      x.dauer_s == null ? "–" : (x.dauer_s < 10 ? x.dauer_s.toFixed(2) : Math.round(x.dauer_s)) + " s",
      x.neustarts || "–",
      x.fehler || x.hing ? el("span", { class: "mono sehrleise", style: "overflow-wrap:anywhere" },
        [x.fehler, x.hing ? t("gs_hing", { x: x.hing }) : null].filter(Boolean).join(" · ")) : "–"]))
      : el("div", { class: "leer" }, t("gs_aus")),
    el("p", { class: "sehrleise", style: "font-size:12px" }, t("gs_h"))].filter(Boolean));   /* m.append schriebe null als Text */
}
async function sichtBetrieb() {
  let d; try { d = await holen("/api/betrieb"); } catch (e) { rahmen(t("betrieb")).append(el("div", { class: "leer" }, String(e))); return; }
  const m = rahmen(t("betrieb"));     /* erst laden, dann ersetzen – sonst steht kurz eine leere Seite da */
  const anteil = d.speicher.frei && d.speicher.gesamt ? d.speicher.frei / d.speicher.gesamt : 0;
  m.append(el("div", { class: "messer zeile-reveal" },
    el("div", { class: "karte" }, el("div", { class: "leise" }, t("speicher_frei"), " ", pcMarke()), el("div", { class: "wert" }, d.speicher.frei == null ? "?" : `${d.speicher.frei} GB`),
      el("div", { class: "sehrleise" }, t("von_gb", { n: d.speicher.gesamt, g: d.speicher.grenze })),
      el("div", { class: "balken" }, el("i", { style: `width:${Math.round(anteil * 100)}%;background:var(${d.speicher.frei < 8 ? "--bernstein" : "--gruen"})` }))),
    el("div", { class: "karte" }, el("div", { class: "leise" }, t("aktive_sitzungen")), el("div", { class: "wert" }, d.sitzungen.filter(s => s.zustand === "aktiv").length),
      el("div", { class: "sehrleise" }, t("ueber_hook"))),
    el("div", { class: "karte" }, el("div", { class: "leise" }, t("sperren")), el("div", { class: "wert" }, d.sperren.length), el("div", { class: "sehrleise" }, t("halt_anweisungen"))),
    d.p_quote ? el("div", { class: "karte", "data-k": "p-quote" }, el("div", { class: "leise" }, t("bt_p")),   /* A2004: Anteil p, Ziel ≥ 50 % */
      el("div", { class: "wert", style: d.p_quote.n && d.p_quote.anteil < d.p_quote.ziel ? "color:var(--bernstein)" : "" },
        d.p_quote.n ? `${Math.round(d.p_quote.anteil * 100)} %` : "–"),
      el("div", { class: "sehrleise" }, d.p_quote.n ? t("bt_p_h", { p: d.p_quote.p, n: d.p_quote.n, z: Math.round(d.p_quote.ziel * 100) })
        : t("bt_p_leer", { z: Math.round(d.p_quote.ziel * 100) }))) : null,
    el("div", { class: "karte" }, el("div", { class: "leise" }, t("datenbank")), el("div", { class: "mono", style: "margin-top:10px;overflow-wrap:anywhere" }, d.db))));
  gesundheitTeil(m, d.gesundheit);                    /* Dienst: Herzschlag je Teil (A1655) */
  const punkt = z => el("span", {}, el("span", { class: "punkt " + (z === "laeuft" ? "gruen" : z === "aus" ? "rot" : "") }), " ", t("sz_" + z));
  m.append(el("h2", {}, t("server"), hilfeKnopf("server")), (d.server || []).length
    ? tabelle(["k_name", "k_port", "k_zustand", "k_seit", "k_zustaendig", "k_neustart", "k_ausfaelle"],
        d.server.map(s => [s.name, s.port, punkt(s.zustand), seit(s.seit_utc), s.zustaendig, s.neustart ? t("ja") : t("nein"), s.ausfaelle]))
    : el("div", { class: "leer" }, t("keine_server")));
  kiTeil(m, d.ki || { kis: [] });
  /* Verbrauch je Agent und Tag (Schätzung zum Listenpreis aus der Statusline) */
  const v = d.verbrauch || { tage: [], agenten: {} }, namen = Object.keys(v.agenten).sort();
  const tagKurz = x => x.slice(8, 10) + "." + x.slice(5, 7) + ".";
  m.append(el("h2", {}, t("verbrauch")), namen.length
    ? el("div", {}, tabelle(["k_agent", ...v.tage.map(tagKurz), "k_summe"].map(k => k.startsWith("k_") ? k : "#" + k),
        [...namen.map(n => [n, ...v.tage.map(x => (v.agenten[n][x] ?? 0).toFixed(2)), Object.values(v.agenten[n]).reduce((a, b) => a + b, 0).toFixed(2)]),
         [t("k_summe"), ...v.tage.map(x => namen.reduce((a, n) => a + (v.agenten[n][x] || 0), 0).toFixed(2)),
          namen.reduce((a, n) => a + Object.values(v.agenten[n]).reduce((s, w) => s + w, 0), 0).toFixed(2)]]),
      el("p", { class: "sehrleise", style: "font-size:12px" }, t("verbrauch_h")))
    : el("div", { class: "leer" }, t("verbrauch_leer")));
  if (!API) anlassTeil(m);                           /* Wofür das Geld geht (A1642) – nur am PC */
  m.append(el("h2", {}, t("sperren")), d.sperren.length ? tabelle(["k_nr", "k_art", "k_fuer", "k_von", "k_text", "k_seit"], d.sperren.map(s => [s.id, s.art, s.gilt_fuer, s.von, s.text, zeit(s.seit_utc)]))
    : el("div", { class: "leer" }, t("keine_sperren")));
  const sitz = [...d.sitzungen.filter(s => s.zustand === "aktiv"), ...d.sitzungen.filter(s => s.zustand !== "aktiv").slice(0, 8)];
  m.append(el("h2", {}, t("sitzungen")), sitz.length ? tabelle(["k_agent", "k_zustand", "k_gestartet", "k_puls", "k_beendet"], sitz.map(s => [s.kennung, s.zustand, zeit(s.gestartet_utc), seit(s.letzter_puls_utc), zeit(s.beendet_utc)]))
    : el("div", { class: "leer" }, t("keine_sitzung")));
  /* Grafikkarte und Schirm gibt es nur einmal: was ein anderes Projekt dieses PCs dort gerade belegt – ohne Inhalt */
  const fremd = (d.fremd || []).map(f => el("tr", { class: "fremd" }, el("td", {}, "–"), el("td", {}, f.projekt ? t("fremd_projekt", { x: f.projekt }) : t("rh_fremd")),
    el("td", { colspan: 5 }, t(f.gpu ? "fremd_gpu" : "fremd_schirm", { x: zeit(f.start_utc) }))));
  const lt = d.laeufe.length || fremd.length ? tabelle(["k_nr", "k_agent", "k_lauf", "k_status", "k_start", "k_ende", "k_rc"], d.laeufe.map(l => [l.id, l.agent,
      l.gpu ? el("span", {}, el("span", { class: "etikett", style: "margin-right:6px" }, "GPU"), l.beschreibung) : l.beschreibung, l.status, zeit(l.start_utc), zeit(l.ende_utc), l.rc ?? ""]))
    : el("div", { class: "leer" }, t("keine_laeufe"));
  lt.querySelector("tbody")?.prepend(...fremd);
  m.append(el("h2", {}, t("laeufe")), lt);
  m.append(el("h2", {}, t("protokoll")), el("pre", { class: "log" }, d.log.join("\n") || t("leer")));
  sprungmarken(m);
}
/* Lokale KI: Kachel je KI, Modelle mit Freigabe, Vorlagen, Aufträge (eine Ansicht der gemeinsamen Lauf-Schlange) */
function kiTeil(m, k) {
  m.append(el("h2", {}, t("ki"), pcMarke(), hilfeKnopf("lokale-ki")), el("p", { class: "sehrleise", style: "font-size:12px;margin:-4px 0 10px" }, t("ki_erkl")));
  if (!k.kis.length) { m.append(el("div", { class: "leer" }, t("ki_keine"))); return; }
  m.append(el("div", { class: "messer" }, k.kis.map(x => el("div", { class: "karte" },
    el("div", { class: "leise" }, `${x.name} · ${x.art}`),
    el("div", { class: "wert", style: "font-size:22px" }, el("span", { class: "punkt " + ({ an: "gruen", belegt: "bernstein", aus: "rot", gestoert: "rot" }[x.zustand] || "") }), " ", t("kiz_" + x.zustand)),
    el("div", { class: "sehrleise" }, [x.schnittstelle + (x.version ? " " + x.version : ""), x.geladen.length ? t("ki_geladen", { x: x.geladen.join(", ") }) : null,
      x.wartend ? t("ki_wartend", { n: x.wartend }) : null].filter(Boolean).join(" · ")),
    x.betrieb ? el("div", { class: "sehrleise", title: x.betrieb === "bedarf" ? t("ki_bedarf_h") : "" },
      [t(x.betrieb === "immer" ? "ki_immer" : "ki_bedarf"), x.von_amw && x.betrieb === "bedarf" ? t("ki_von_amw", { n: x.leerlauf_min }) : null].filter(Boolean).join(" · ")) : null,
    el("div", { class: "sehrleise" }, t("ki_darf", { x: x.darf.length ? ", " + x.darf.join(", ") : "" }))))));
  const frei = x => el("span", {}, el("span", { class: "etikett " + ({ frei: "gruen", gesperrt: "rot", offen: "bernstein" }[x.freigabe] || "") }, t("kif_" + x.freigabe)),
    x.freigabe_grund ? el("span", { class: "sehrleise" }, " " + x.freigabe_grund) : null);
  if (k.modelle.length) m.append(el("h3", { class: "ki-kopf" }, t("ki_modelle")), tabelle(["k_ki", "k_modell", "k_lizenz", "k_kommerziell", "k_freigabe"],
    k.modelle.map(x => [x.ki, el("span", {}, x.name, x.datei && x.datei !== x.name ? el("div", { class: "sehrleise mono" }, x.datei) : null),
      (x.lizenz || "?") + (x.nutzungsregeln ? " · " + t("ki_regeln") : ""), x.kommerziell, frei(x)])));
  if (k.vorlagen.length) m.append(el("h3", { class: "ki-kopf" }, t("ki_vorlagen"),
    el("span", { class: "sehrleise", style: "font-size:12px;font-weight:400;margin-left:8px" }, t("ki_vorlagen_h"))), tabelle(["k_ki", "k_name", "k_text", "k_von"],
    k.vorlagen.map(v => [v.ki, v.name, v.beschreibung || "", v.von])));
  const zustandEt = x => el("span", { class: "etikett " + ({ fertig: "gruen", fehler: "rot", laeuft: "bernstein" }[x.zustand] || ""), title: x.fehler || x.fortschritt || "" }, t("kia_" + x.zustand));
  m.append(el("h3", { class: "ki-kopf" }, t("ki_auftraege")), k.auftraege.length
    ? tabelle(["k_lauf", "k_ki", "k_auftraggeber", "k_auftrag", "k_zustand", "k_ergebnis"], k.auftraege.map(x => [`L${x.lauf_id}`,
        `${x.ki} · ${x.modell || x.vorlage || ""}`, x.auftraggeber, x.titel || x.prompt, zustandEt(x),
        x.dokumente.length ? el("span", {}, x.dokumente.map(n => el("a", { class: "verweis", style: "margin-right:6px", onclick: () => dokumentDialog(n) }, `D${n}`)))
          : el("span", { class: "sehrleise" }, x.fehler || x.fortschritt || "")]))
    : el("div", { class: "leer" }, t("ki_keine_auftraege")));
}
function tabelle(kopf, zeilen) {
  return el("div", { class: "tab-huelle" }, el("table", { class: "tab" }, el("thead", {}, el("tr", {}, kopf.map(k => el("th", {}, k.startsWith("#") ? k.slice(1) : t(k))))),
    el("tbody", {}, zeilen.map(z => el("tr", {}, z.map(w => el("td", {}, w ?? "")))))));
}


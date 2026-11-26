/* A2006 (TH156 F10, Kleinprobe D1534 v4): der Leitstand – die Startseite. Von oben nach unten: Kopf (Zustand · Projektdetails ·
   Steuerung), Bänder nur bei Anlass, Fortschritt, Für dich, Agenten, Ressourcen, Zuletzt · Jetzt · Als Nächstes, Zeitplan,
   Entscheidungen der AMW, darunter die Steuerung. Sofort aus /api/start; was /api/leitstand liefert (Prognose, Zeitplan …), kommt
   in feste Plätze nach (kein Springen der Höhe) und wird nur bei neuem Stempel von arbeit/planung neu geholt (Lead #34060). */
const LS_ALTER_MS = 5 * 60 * 1000;                 /* Zeiten in der Prognose: spätestens alle 5 min neu, auch ohne Änderung */
function lsStempel(d) { return `${d?.stand?.arbeit || ""}|${d?.stand?.planung || ""}|${projekt || ""}`; }
async function lsDaten(d) {
  const c = zustand.leitstand, s = lsStempel(d);
  if (c && c.stempel === s && Date.now() - c.um < LS_ALTER_MS) return c.daten;
  const daten = await holen("/api/leitstand");
  zustand.leitstand = { stempel: s, um: Date.now(), daten };
  return daten;
}
const lsMin = iso => Math.max(0, Math.round((Date.now() - Date.parse(iso)) / 60000));
const lsDauer = m => m == null ? "–" : m < 90 ? t("lst_min", { n: m }) : t("lst_h", { n: zahlKurz(m / 60) });
const lsUhr = iso => new Date(iso).toLocaleTimeString(gebiet(), { hour: "2-digit", minute: "2-digit" });
/* Seitenfenster wie im Projektweg (A2091): am PC fest rechts, am Handy über die ganze Breite; Esc und der Schleier schließen */
function lsFenster(titel, felder, ...teile) {
  document.getElementById("ls-fenster")?.remove();
  const zu = () => document.getElementById("ls-fenster")?.remove();
  $("#inhalt").append(el("div", { id: "ls-fenster" }, el("div", { class: "pjw-schleier", onclick: zu }),
    el("div", { class: "pjw-fenster", role: "dialog" },
      el("div", { class: "pjw-kopf" }, el("h3", {}, titel), el("button", { class: "knopf still pjw-zu", type: "button", onclick: zu, "aria-label": t("pjw_schliessen") }, "✕")),
      felder.length ? el("div", { class: "pjw-felder" }, felder.filter(Boolean).flatMap(([k, v]) => [el("span", {}, k), el("span", {}, v ?? "–")])) : null,
      ...teile)));
}
document.addEventListener("keydown", e => { if (e.key === "Escape") document.getElementById("ls-fenster")?.remove(); });
function lsKopfLeiste(d) {
  const pause = (d.halt || []).length > 0;
  return el("div", { class: "ls-leiste" },
    el("button", { type: "button", class: "ls-zustand", title: t(pause ? "lst_weiter_h" : "lst_pause_h"), onclick: () => pause ? weiterGeben() : haltDialog() },
      el("span", { class: "punkt " + (pause ? "bernstein" : "gruen") }), el("b", {}, t(pause ? "lst_pausiert" : "lst_laeuft")),
      el("span", { class: "leise" }, " · " + t(pause ? "lst_weiter" : "lst_pausieren"))),
    el("button", { type: "button", onclick: () => lsProjektdetails(d) }, t("lst_details")),
    el("button", { type: "button", id: "zur-steuerung", onclick: zurSteuerung }, t("ls_titel")));
}
function lsFortschritt(f) {
  if (!f) return el("div", { class: "ls-fort platz" }, el("div", { class: "ls-zahl" }, "…"), el("div", { class: "ue-spur" }, el("i")));
  const v = f.verzug_tage;
  return el("div", { class: "ls-fort" },
    el("div", { class: "ls-fort-zeile" }, el("span", { class: "ls-zahl" }, `${f.prozent} %`),
      el("span", { class: "leise" }, t("lst_von_paketen", { f: f.fertig, g: f.gesamt })),
      f.p50 ? el("span", { class: "ls-prognose leise" }, t("lst_fertig_vor", { x: datumKurz(f.p50) }),
        v == null ? null : el("span", { class: v > 0 ? "bernstein-text" : "" }, " · " + (v > 0 ? t("lst_spaeter", { n: v }) : v < 0 ? t("lst_frueher", { n: -v }) : t("lst_wie_geplant")))) : null),
    el("div", { class: "ue-spur ls-spur" + (v > 0 ? " ueber" : "") }, el("i", { style: `width:${f.prozent}%` })));
}
function lsAgenten(d) {
  const a = d.agenten || [];
  if (!a.length) return null;
  return el("section", { class: "ls-block" }, el("h2", { class: "ls-lbl" }, t("lst_agenten")),
    el("div", { class: "ls-agenten", id: "team" }, a.map(x => {        /* id/data-k wie die frühere Team-Ansicht: Einstieg der Agenten-Wege */
      const lebt = x.zustand === "aktiv", wartet = (x.wartet_auf || []).length;
      return el("button", { type: "button", class: "ls-agent", "data-k": x.kennung, onclick: () => agentDialog(x.kennung) },
        el("b", {}, el("span", { class: "punkt " + (lebt ? "gruen" : "") }), x.kennung),
        el("span", { class: "leise" }, [x.co ? t("co_entwickler") : x.rolle === "lead" ? t("lead") : x.fachgebiet, x.modell].filter(Boolean).join(" · ") || " "),
        el("span", {}, x.gerade_aufgabe ? `A${x.gerade_aufgabe}` + (x.gerade_seit ? " · " + lsDauer(lsMin(x.gerade_seit)) : "")
          : wartet ? t("lst_wartet_auf", { x: x.wartet_auf.map(w => w === "Entwickler" ? t("lst_dich") : w).join(", ") }) : t(lebt ? "lst_frei" : x.soll === "an" ? "beendet_soll" : "lst_aus")),
        el("span", { class: "ls-auf sehrleise", title: x.gerade || x.zustaendig || "" }, (x.gerade || x.zustaendig || t("tm_keine")) + (x.gerade && x.gerade_veraltet ? " · " + t("k_veraltet") : "")));   /* wie die frühere Kachel */
    })));
}
function lsRessourcen(d, l) {
  const n = art => l ? l.jetzt.filter(j => j.art === art).length : null, s = d.schirm, tk = d.token?.wert, sp = d.speicher?.frei;
  const laufen = x => x == null ? "…" : t(x === 1 ? "lst_laeuft1" : "lst_laufen", { n: x });
  const teil = (k, w) => w == null ? null : el("span", {}, el("span", { class: "leise" }, k + " "), el("b", {}, w));
  return el("div", { class: "ls-ressourcen" },
    teil(t("lst_r_fenster"), laufen(n("fenster"))),
    teil(t("lst_r_headless"), laufen(n("headless"))),
    teil(t("lst_r_lauf"), laufen(n("lauf"))),
    sp == null ? null : teil(t("lst_r_speicher"), t("uk_gb_frei", { n: zahlKurz(sp) })),
    s ? teil(t("lst_r_schirm"), t(s.frei ? "lst_schirm_frei" : "lst_schirm_dir")) : null,
    tk == null ? null : teil(t("lst_r_woche"), `${Math.round(tk)} %`));
}
function lsKarteOeffnen(x) {
  const nr = x.nummer || "";
  if (/^A\d+$/.test(nr)) return aufgabeDialog(+nr.slice(1));
  if (/^L\d+$/.test(nr)) return API ? zeige("betrieb") : laufAusgabeDialog(+nr.slice(1));
  if (x.wer && (zustand.start?.agenten || []).some(a => a.kennung === x.wer)) return agentDialog(x.wer);
}
function lsJetztKarte(j) {
  const min = lsMin(j.seit_utc), erw = j.erwartet_min, ueber = erw != null && min > erw;
  const anteil = erw ? Math.min(1, min / erw) : 0;
  return el("button", { type: "button", class: "ls-karte" + (ueber ? " ueber" : ""), "data-ref": j.nummer || "", onclick: () => lsKarteOeffnen(j) },
    el("div", { class: "ls-karte-kopf" }, el("b", {}, j.wer || "–"), el("span", { class: "chip" }, t("lst_art_" + j.art))),
    el("div", { class: "ls-titel" }, j.nummer ? el("span", { class: "ref" }, j.nummer + " ") : null, j.titel || ""),
    el("div", { class: "ue-spur ls-spur" + (ueber ? " ueber" : "") }, el("i", { style: `width:${Math.round(anteil * 100)}%` })),
    el("div", { class: "ls-karte-fuss mono" }, el("span", {}, erw ? `${min} / ≈ ${erw} min` : lsDauer(min)),
      ueber ? el("span", { class: "bernstein-text" }, `+${min - erw} min`) : null));
}
function lsZeile(x, unten) {
  return el("button", { type: "button", class: "ls-zeile", "data-ref": x.nummer || "", onclick: () => lsKarteOeffnen(x) },
    el("div", {}, x.nummer ? el("span", { class: "ref" }, x.nummer + " ") : null, x.titel || ""), el("div", { class: "leise" }, unten));
}
function lsAblauf(l) {
  if (!l) return el("section", { class: "ls-block ls-platz" }, el("div", { class: "leise" }, t("lst_laedt")));
  const zuletzt = l.zuletzt || [], jetzt = l.jetzt || [], naechst = l.als_naechstes || [];
  return el("section", { class: "ls-ablauf" },
    zuletzt.length ? el("div", {}, el("h2", { class: "ls-lbl" }, t("lst_zuletzt")),
      el("div", { class: "ls-linie" }, zuletzt.map(z => lsZeile(z, [z.wer, seit(z.zeit_utc)].filter(Boolean).join(" · "))))) : null,
    el("h2", { class: "ls-lbl ls-jetzt" }, t("lst_jetzt", { x: lsUhr(new Date().toISOString()), n: jetzt.length })),
    jetzt.length ? el("div", { class: "ls-raster" }, jetzt.map(lsJetztKarte)) : el("p", { class: "leise" }, t("lst_nichts_laeuft")),
    naechst.length ? el("div", {}, el("h2", { class: "ls-lbl" }, t("lst_naechstes")),
      el("div", { class: "ls-linie" }, naechst.map(g => g.pakete.length > 1
        ? el("div", { class: "ls-gleichzeitig" }, el("div", { class: "leise" }, t("lst_gleichzeitig", { x: lsUhr(g.start_utc) })),
            el("div", { class: "ls-raster" }, g.pakete.map(p => lsZeile(p, [p.wer || t("lst_frei_paket"), lsDauer(p.dauer_min)].join(" · ")))))
        : lsZeile(g.pakete[0], [g.pakete[0].wer || t("lst_frei_paket"), lsDauer(g.pakete[0].dauer_min), t("lst_ab", { x: lsUhr(g.start_utc) }),
            g.pakete[0].wartet_auf ? t("lst_nach", { x: g.pakete[0].wartet_auf }) : null].filter(Boolean).join(" · ")))),
      el("a", { class: "verweis", href: "#projektweg", onclick: e => { e.preventDefault(); zeige("projektweg"); } }, t("lst_ganze_reihenfolge"))) : null);
}
function lsZeitplan(l) {
  const z = l?.zeitplan || [];
  if (!z.length) return null;
  const tag = x => Date.parse(x + "T12:00:00Z"), von = Math.min(...z.map(m => tag(m.start || m.p50))),
    bis = Math.max(...z.map(m => Math.max(tag(m.p85 || m.p50), m.ziel ? tag(m.ziel) : 0))), weit = Math.max(1, bis - von);
  const pos = x => `${Math.round(100 * (tag(x) - von) / weit)}%`;
  return el("section", { class: "ls-block" }, el("h2", { class: "ls-lbl" }, t("lst_zeitplan")),
    el("div", { class: "ls-zeitplan" }, z.map(m => el("div", { class: "ls-zp-zeile" },
      el("span", {}, `M${m.nr} ${m.titel}`),
      el("span", { class: "ls-zp-spur" },
        el("i", { class: m.verzug_tage > 0 ? "ueber" : "", style: `left:${pos(m.start || m.p50)};width:calc(${pos(m.p50)} - ${pos(m.start || m.p50)} + 4px)` }),
        m.ziel ? el("b", { title: t("lst_ziel", { x: datumKurz(m.ziel) }), style: `left:${pos(m.ziel)}` }) : null),
      el("span", { class: "leise" }, m.bereit ? t("lst_bereit") : [datumKurz(m.p50), m.verzug_tage == null ? null : m.verzug_tage > 0
        ? t("lst_spaeter", { n: m.verzug_tage }) : m.verzug_tage < 0 ? t("lst_frueher", { n: -m.verzug_tage }) : t("lst_wie_geplant")].filter(Boolean).join(" · "))))));
}
function lsEntscheidungen(l) {
  const e = l?.entscheidungen || [];
  if (!e.length) return null;
  return el("section", { class: "ls-block" }, el("h2", { class: "ls-lbl" }, t("lst_entscheidungen")),
    el("div", { class: "ls-entscheidungen" }, e.map(x => el("button", { type: "button", class: "ls-ent", "data-ref": x.nummer || "",
      onclick: () => x.projekt === (projekte.find(p => p.uid === projekt) || {}).name ? lsKarteOeffnen(x) : lsFenster(x.projekt, [[t("lst_wann"), zeit(x.zeit_utc)]], el("p", {}, x.text)) },
      el("span", { class: "mono leise" }, lsUhr(x.zeit_utc)), el("span", { class: "leise" }, x.projekt), el("span", {}, x.text)))));
}
function lsLeer(l) {                                /* neues Projekt ohne Pakete · alles fertig */
  const f = l?.fortschritt;
  if (!f || f.gesamt) return null;
  const fertig = (l.zeitplan || []).length === 0 && (l.zuletzt || []).length > 0;
  return el("div", { class: "ls-leer" }, el("b", {}, t(fertig ? "lst_leer_fertig" : "lst_leer_neu")),
    fertig ? null : el("a", { class: "verweis", href: "#projektweg", onclick: e => { e.preventDefault(); zeige("projektweg"); } }, t("lst_zum_konzept")));
}
async function lsProjektdetails(d) {
  const l = zustand.leitstand?.daten, f = l?.fortschritt, u = d.uebersicht || {};
  const felder = [[t("lst_erledigt"), f ? t("lst_von_paketen", { f: f.fertig, g: f.gesamt }) : null],
    [t("lst_voraus"), f?.p50 ? `${datumKurz(f.p50)} – ${datumKurz(f.p85)}` : null], [t("lst_ziel_k"), f?.ziel ? datumKurz(f.ziel) : null],
    [t("lst_fragen_offen"), String(d.fragen_anzahl ?? 0)], u.kosten_heute != null ? [t("lst_kosten_heute"), dollar(u.kosten_heute)] : null];
  const termine = (l?.zeitplan || []).map(m => [`M${m.nr} ${m.titel}`, (m.ziel ? t("lst_ziel", { x: datumKurz(m.ziel) }) + " · " : "") + t("lst_fertig_vor", { x: datumKurz(m.p50) })]);
  lsFenster(t("lst_details"), felder, termine.length ? el("div", {}, el("h4", {}, t("lst_termine")),
    el("div", { class: "pjw-felder" }, termine.flatMap(([k, v]) => [el("span", {}, k), el("span", {}, v)]))) : null,
    el("a", { class: "verweis", href: "#projektweg", onclick: e => { e.preventDefault(); document.getElementById("ls-fenster")?.remove(); zeige("projektweg"); } }, t("lst_zum_projektweg")));
}
/* Bänder (Halt, Dienst, Bildschirm, nächster Test, nicht angemeldet, Achtung): nur bei Anlass – wie bisher, aus startBaender */
async function sichtLeitstand(d, m) {
  const fort = el("div", { class: "ls-fort-platz" }, lsFortschritt(null)), leer = el("div"), ress = el("div", {}, lsRessourcen(d, null));
  const ablauf = el("div", {}, lsAblauf(null)), rest = el("div");
  m.append(fort, leer, uebersichtKarten(d), lsAgenten(d) || "", ress, ablauf, rest);
  let l = null;
  try { l = await lsDaten(d); } catch (e) { ablauf.replaceChildren(el("p", { class: "leise" }, t("fehler", { x: e.message || e }))); return; }
  if (zustand.sicht !== "start") return;
  fort.replaceChildren(lsFortschritt(l.fortschritt));
  leer.replaceChildren(...[lsLeer(l)].filter(Boolean));
  ress.replaceChildren(lsRessourcen(d, l));
  ablauf.replaceChildren(lsAblauf(l));
  rest.replaceChildren(...[lsZeitplan(l), lsEntscheidungen(l)].filter(Boolean));
}

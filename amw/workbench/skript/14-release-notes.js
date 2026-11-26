/* --- Release Notes ------------------------------------------------------------------------- */
async function sichtReleases() {
  /* Versionshinweise: je Version der Text für alle (Neu / Verbessert / Behoben); oben der Entwurf der nächsten Version aus
     den fertigen Aufgaben – ohne KI. „Mit Aufgaben“ zeigt die Nummern dazu. */
  let d; try { d = await holen("/api/versionshinweise"); } catch (e) { rahmen(t("releases")).append(el("div", { class: "leer" }, String(e))); return; }
  const mit = !!zustand.vhAufgaben;
  const umschalter = el("div", { class: "reiter", style: "margin:0" }, [false, true].map(w => el("button", { class: w === mit ? "an" : "", type: "button",
    onclick: () => { zustand.vhAufgaben = w; sichtReleases(); } }, t(w ? "vh_mit" : "vh_alle"))));
  const m = rahmen(t("n_releases"), umschalter);                                  /* A2012: beim Projektweg – die Reihe steht im Kopf */
  const gruppen = ["neu", "verbessert", "behoben"], e = d.entwurf || {}, nEntwurf = gruppen.reduce((s, g) => s + (e[g] || []).length, 0);
  const block = (titel, unter, inhalt) => el("div", { class: "karte vh-version" }, el("div", { class: "vh-kopf" }, el("b", { class: "ver" }, titel), unter ? el("span", { class: "sehrleise" }, unter) : null), inhalt);
  if (nEntwurf) m.append(block(t("vh_entwurf"), t("vh_entwurf_h"), gruppen.filter(g => (e[g] || []).length).map(g => el("div", { class: "vh-gruppe vh-" + g },
    el("h4", {}, t("vh_" + g)), el("ul", {}, e[g].map(x => el("li", {}, x.text, x.vorschlag ? el("span", { class: "etikett", style: "margin-left:6px", title: t("vh_vorschlag_h") }, t("vh_vorschlag")) : null,
      mit ? el("span", { class: "ref", style: "margin-left:6px" }, "A" + x.id) : null)))))));
  if (!d.versionen.length && !nEntwurf) { m.append(el("div", { class: "leer" }, t("keine_releases"))); return; }
  for (const v of d.versionen) m.append(block(v.version, [zeit(v.zeit_utc), v.titel].filter(Boolean).join(" · "),
    el("div", { class: "vh-text" }, v.text_oeffentlich ? markdown(v.text_oeffentlich) : el("div", { class: "text" }, v.text_intern || "")),
    mit && v.aufgaben ? el("div", { class: "sehrleise mono", style: "margin-top:6px" }, t("aufgaben_x", { x: v.aufgaben })) : null));
}


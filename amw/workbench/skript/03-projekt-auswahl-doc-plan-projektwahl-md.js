/* --- Projekt-Auswahl (doc/plan-projektwahl.md) ----------------------------------------------- */
const FARBEN = { bernstein: "var(--bernstein)", gruen: "var(--gruen)", blau: "var(--blau)", violett: "#a68bd6", tuerkis: "#5fb5a8",
  rot: "var(--rot)", grau: "var(--leise)" };
const farbe = p => FARBEN[p?.farbe] || FARBEN.bernstein;
const pcHinweis = () => projekte.length > 1 ? t("pc_marke_h") : null;       /* erste Zeile: als Hinweistext statt als Kürzel */
const pcMarke = () => el("span", { class: "pc-marke", title: t("pc_marke_h") }, t("pc_marke"));
async function projekteLaden() {
  let d; try { d = await abrufen("/api/projekte"); } catch (e) { return; }   /* A1907: das gewählte Projekt gilt für jede Seite */
  projekte = d.projekte || [];
  let gewollt = null, ausLink = false;
  try { gewollt = new URLSearchParams(location.search).get("projekt"); ausLink = !!gewollt; } catch (e) {}
  if (!gewollt) try { gewollt = localStorage.getItem("amw-projekt"); } catch (e) {}
  const eigene = projekte.filter(x => !x.fern);
  const p = eigene.find(x => x.uid === gewollt || x.name === gewollt) || eigene.find(x => x.aktiv) || eigene[0];
  if (!p) return;
  projekt = p.uid;
  document.documentElement.style.setProperty("--projekt-farbe", farbe(p));
  if (ausLink && p.uid !== gewollt && p.name !== gewollt) toast(t("pw_unbekannt", { x: p.name }), true);
  try { if (sessionStorage.getItem("amw-gewechselt") === p.uid) { sessionStorage.removeItem("amw-gewechselt"); toast(t("pw_jetzt", { x: p.name })); } } catch (e) {}
  projektwahlZeigen(p);
}
function projektwahlZeigen(p) {
  const knopf = el("button", { class: "pw" + (!projekte.length ? " still" : ""), type: "button", title: t("pw_nur_ansicht"),
    onclick: e => projektListe(e.currentTarget) },
    el("span", { class: "pw-farbe", style: `background:${farbe(p)}` }),
    el("span", {}, el("span", { class: "pw-klein" }, t("pw_projekt")), el("span", { class: "pw-name" }, p.name)),
    el("span", { class: "pw-pfeil" }, "▾"));
  $("#projektwahl").replaceChildren(knopf);
  const chip = $("#projekt-chip"); chip.hidden = false;
  chip.replaceChildren(el("span", { class: "pw-farbe", style: `background:${farbe(p)}` }), el("span", {}, p.name + " ▾"));
  chip.onclick = e => projektListe(e.currentTarget);
  chip.setAttribute("aria-label", `${t("pw_projekt")}: ${p.name}`);
}
function projektListe(anker) {
  const r = anker.getBoundingClientRect();
  const mehrRechner = new Set(projekte.map(x => x.rechner).filter(Boolean)).size > 1;
  /* fremd = Projekt eines anderen Rechners: am PC über die Online-Seite (dort auch dirigierbar), online wie jedes andere */
  const oeffnen = p => { hg.remove(); if (p.uid === projekt) return;
    if (!p.fern) projektWechseln(p.uid);
    else if (p.online) window.open(p.online, "_blank", "noopener");
    else toast(t("pw_fern_ohne_link"), true); };
  const eintrag = p => el("button", { class: "pw-eintrag" + (p.uid === projekt ? " an" : ""), type: "button", onclick: () => oeffnen(p) },
    el("span", { class: "pw-farbe", style: `background:${farbe(p)}` }),
    el("span", {}, el("b", {}, p.name, p.fern ? " ↗" : ""), el("small", {}, [mehrRechner ? p.rechner : null,
      t(p.agenten === 1 ? "pw_agent1" : "pw_agenten", { n: p.agenten }), p.halt ? t("pw_halt") : null,
      p.erreichbar === false ? t("pw_weg") : null].filter(Boolean).join(" · "))),
    p.fragen ? el("span", { class: "pw-zahl", title: t("pw_fragen", { n: p.fragen }) }, `${p.fragen} ?`) : el("span"));
  const liste = el("div", { class: "pw-liste karte", style: `left:${Math.round(r.left)}px;top:${Math.round(r.bottom + 6)}px`, role: "dialog",
      "aria-label": t("pw_waehlen") },
    el("h3", {}, t("pw_waehlen")), ...projekte.map(eintrag),
    el("div", { class: "pw-fuss" }, el("span", { class: "sehrleise", style: "font-size:12px" }, t("pw_nur_ansicht")),
      el("span", { style: "display:flex;gap:6px;align-items:center;flex-wrap:wrap" },
        API ? el("span", { class: "sehrleise", style: "font-size:12px" }, t("pw_neu_pc"))
          : el("button", { class: "klein-knopf", type: "button", onclick: () => { hg.remove(); projektNeuDialog(); } }, "+ " + t("pw_neu")),
        el("button", { class: "klein-knopf", type: "button", onclick: () => { hg.remove(); projektAnleitung(); } }, "? " + t("npa_link")))));
  const hg = el("div", { class: "dialog-hg pw-hg", onclick: e => { if (e.target === hg) hg.remove(); } }, liste);
  document.body.append(hg);
  (liste.querySelector(".pw-eintrag.an") || liste.querySelector(".pw-eintrag"))?.focus();
}
/* Schritt-für-Schritt-Hilfe – ein Baustein für alle Themen. Inhalt: doc/hilfe/<thema>.md (Deutsch) und doc/hilfe/en/
   (Englisch) in festem Aufbau; am PC und online unter derselben Adresse hilfe/<thema>.<sprache>.json (→ amw/hilfen.py,
   amw web bauen). Im Text gelten nur **fett** und `Befehl` – beides wird als Element gesetzt, nie als HTML. */
function mitAuszeichnung(text) {
  const aus = [], roh = String(text || ""), muster = /\*\*(.+?)\*\*|`([^`]+)`/g;
  let m, i = 0;
  while ((m = muster.exec(roh))) {
    if (m.index > i) aus.push(roh.slice(i, m.index));
    aus.push(m[1] != null ? el("b", {}, m[1]) : el("code", {}, m[2])); i = muster.lastIndex;
  }
  if (i < roh.length) aus.push(roh.slice(i));
  return aus;
}
async function hilfe(thema) {
  let d;
  try { const r = await lesenMitWiederholung(`hilfe/${thema}.${sprache}.json`); if (!r.ok) throw new Error(r.status); d = await r.json(); }
  catch (e) { toast(t("h_fehlt", { x: thema }), true); return; }
  const liste = (titel, eintraege, zeile) => eintraege?.length
    ? [el("h4", {}, titel), el("ul", { class: "npa-liste" }, eintraege.map(x => el("li", {}, zeile ? zeile(x) : mitAuszeichnung(x))))] : [];
  dialog(d.titel, el("div", { class: "npa hilfe", "data-thema": thema },
    d.sprache !== sprache ? el("p", { class: "hinweis-zeile" }, t("h_nur_de")) : null,
    d.kurz ? el("p", { class: "leise" }, mitAuszeichnung(d.kurz)) : null,
    ...liste(t("h_brauchst"), d.brauchst),
    el("ol", { class: "npa-schritte" }, d.schritte.map(x => el("li", {}, x.titel ? el("b", {}, x.titel) : null, el("p", {}, mitAuszeichnung(x.text)),
      x.bilder.map(b => el("img", { src: `hilfe/${b.name}.webp`, alt: b.alt, loading: "lazy", class: "npa-bild" }))))),
    ...(d.werte.length ? [el("h4", {}, t("h_werte")), el("table", { class: "hilfe-werte" }, el("tbody", {},
      d.werte.map(([feld, woher]) => el("tr", {}, el("td", {}, el("b", {}, feld)), el("td", {}, mitAuszeichnung(woher))))))] : []),
    ...liste(t("h_fehler"), d.fehler, ([was, hilft]) => [el("b", {}, was), " – ", ...mitAuszeichnung(hilft)]),
    ...liste(t("h_danach"), d.danach),
    ...(d.fragen.length ? [el("h4", {}, t("h_fragen")), ...d.fragen.map(([frage, antwort]) => el("details", { class: "npa-frage" }, el("summary", {}, frage), el("p", {}, mitAuszeichnung(antwort))))] : [])));
}
/* „? Anleitung“ neben einem Feld oder Abschnitt, der etwas außerhalb der AMW verlangt */
const hilfeKnopf = (thema, text) => el("button", { class: "klein-knopf hilfe-knopf", type: "button", title: t("h_knopf_h"),
  onclick: e => { e.stopPropagation(); hilfe(thema); } }, "? " + (text || t("npa_link")));
const projektAnleitung = () => hilfe("neues-projekt");
const mitHilfe = (thema, karte) => { karte?.querySelector("h3")?.append(hilfeKnopf(thema)); return karte; };
/* Neues Projekt (nur am PC): wie `amw einrichten` – Projekt, Lead, Agenten, Projektordner, Startskript, Regel-Kopie */
function projektNeuDialog() {
  const feld = (b, x, h) => el("div", { class: "feld" }, el("label", {}, b), el("div", {}, x, h ? el("div", { class: "sehrleise", style: "font-size:12px;margin-top:2px" }, h) : null));
  const name = el("input", { maxlength: 60, autocomplete: "off" }), ordner = el("input", { placeholder: t("np_ordner_ph"), autocomplete: "off" });
  const lead = el("input", { value: "TL", maxlength: 30 }), agenten = el("input", { value: "CC1,CC2" });
  const leadChat = el("input", { type: "checkbox" });
  const rechte = el("select", {}, ["vorgabe", "auto", "umgehen"].map(r => el("option", { value: r }, t("np_rechte_" + r))));
  /* Regelwerk: das mitgelieferte Grund-Regelwerk (Vorgabe) · Kopie der Arbeitsregeln eines anderen Projekts · ohne */
  const regeln = el("select", { id: "np-regeln" }, el("option", { value: "grund" }, t("np_regeln_grund")),
    projekte.filter(p => !p.fern).map(p => el("option", { value: "kopie:" + p.name }, t("np_regeln_von", { x: p.name }))),
    el("option", { value: "" }, t("np_regeln_keine")));
  const rw = el("div", { class: "np-regelwerk" }), haken = {}, wortlaut = {};
  let vorl = null;
  const regeltext = r => `${r.titel}. ${r.text}`, gewaehlt = () => vorl ? vorl.vorlage.regeln.filter(r => haken[r.nr].checked) : [];
  const rwZahl = el("span", {});
  const rwZaehlen = () => { if (vorl) rwZahl.textContent = t("np_rw_zahl", { a: gewaehlt().length, b: vorl.vorlage.regeln.length }); };
  const rwZeichnen = () => {
    if (regeln.value !== "grund" || !vorl) { rw.replaceChildren(); return; }
    const v = vorl.vorlage;
    rw.replaceChildren(el("details", {}, el("summary", {}, rwZahl),
        Object.entries(v.gruppen).map(([k, name]) => el("div", { class: "np-rw-gruppe" }, el("h4", {}, name),
          v.regeln.filter(r => r.gruppe === k).map(r => el("div", { class: "np-rw-regel", "data-nr": r.nr },
            el("label", {}, haken[r.nr], el("span", { class: "ref" }, r.nr), el("b", {}, r.titel)), wortlaut[r.nr],
            el("div", { class: "gr-warum" }, el("b", {}, t(r.erfahrung ? "gr_erfahrung" : "gr_warum") + " "), r.erfahrung || r.warum)))))),
      el("div", { class: "sehrleise", style: "font-size:12px;margin-top:6px" },
        t("np_rw_dod") + ": " + v.dod.join(" · ") + " — " + t("np_rw_version", { v: v.versionen.erste, s: v.versionen.schema })));
    rwZaehlen();
  };
  regeln.addEventListener("change", rwZeichnen);
  abrufen("/api/regelwerk?sprache=" + sprache).then(d => { vorl = d;
    for (const r of d.vorlage.regeln) {
      haken[r.nr] = el("input", { type: "checkbox" }); haken[r.nr].checked = d.vorgabe.includes(r.nr) || (leadChat.checked && !!r.chat_lead);
      haken[r.nr].addEventListener("change", rwZaehlen);
      wortlaut[r.nr] = el("textarea", { rows: 2 }, regeltext(r)); }
    rwZeichnen(); }).catch(() => { regeln.value = ""; });
  leadChat.addEventListener("change", () => { for (const r of vorl?.vorlage.regeln || []) if (r.chat_lead) haken[r.nr].checked = leadChat.checked; rwZaehlen(); });
  const frb = el("select", {}, Object.keys(FARBEN).map(f => el("option", { value: f }, t("farbe_" + f))));
  frb.value = Object.keys(FARBEN).find(f => !projekte.some(p => p.farbe === f)) || "bernstein";   /* eine noch freie Farbe */
  const knopf = el("button", { class: "knopf haupt", type: "button", onclick: async () => {
    if (!name.value.trim()) { name.focus(); return; }
    if (!ordner.value.trim()) { ordner.focus(); return; }
    const grund = regeln.value === "grund" && vorl;
    if (grund && !gewaehlt().length) { toast(t("np_rw_keine"), true); return; }
    knopf.disabled = true;
    try {
      const r = await schicken("/api/projekt/neu", { name: name.value.trim(), ordner: ordner.value.trim(), lead: lead.value.trim(),
        agenten: agenten.value, lead_chat: leadChat.checked, rechte: rechte.value, farbe: frb.value,
        regeln_von: regeln.value.startsWith("kopie:") ? regeln.value.slice(6) : "",
        ...(grund ? { regelwerk: { sprache, auswahl: gewaehlt().map(x => x.nr),      /* eigener Wortlaut nur, wo er geändert wurde */
          texte: Object.fromEntries(gewaehlt().filter(x => wortlaut[x.nr].value.trim() !== regeltext(x)).map(x => [x.nr, wortlaut[x.nr].value.trim()])) } } : {}) });
      kasten.replaceChildren(el("h3", {}, t("np_fertig", { x: name.value.trim() })),
        el("ul", { class: "np-schritte" }, r.schritte.map(s => el("li", {}, "✓ " + s))), el("p", { class: "leise" }, t("np_danach"), " ", el("button", { class: "klein-knopf", type: "button", onclick: projektAnleitung }, "? " + t("npa_link"))),
        el("div", { class: "aktionen" }, el("button", { class: "knopf haupt", type: "button", onclick: () => projektWechseln(r.uid) }, t("np_weiter"))));
    } catch (e) { toast(t("fehler", { x: e.message }), true); knopf.disabled = false; } } }, t("np_anlegen"));
  const kasten = el("div", { class: "einst" }, el("p", { class: "leise", style: "margin:0" }, t("np_h"), " ",
      el("button", { class: "klein-knopf", type: "button", onclick: projektAnleitung }, "? " + t("npa_link"))),
    feld(t("np_name"), name), feld(t("np_ordner"), ordner), feld(t("np_lead"), lead, t("np_lead_h")),
    feld(t("np_lead_chat"), el("div", { style: "display:flex;gap:8px;align-items:center;flex-wrap:wrap" },
      el("label", { style: "display:flex;gap:8px;align-items:center" }, leadChat, t("np_lead_chat_l")), hilfeKnopf("takt-chat-lead", t("np_takt_hilfe"))), t("np_lead_chat_h")),
    feld(t("np_agenten"), agenten, t("np_agenten_h")), feld(t("np_rechte"), rechte),
    feld(t("np_regeln"), el("div", {}, el("div", { style: "display:flex;gap:8px;align-items:center;flex-wrap:wrap" }, regeln, hilfeKnopf("regelwerk")), rw), t("np_regeln_h")),
    feld(t("e_farbe"), frb),
    el("div", { class: "aktionen" }, knopf, el("button", { class: "knopf", type: "button", onclick: () => hg.remove() }, t("abbrechen"))));
  const hg = dialog(t("np_titel"), kasten);
  name.focus();
}
function projektWechseln(uid) {
  try { localStorage.setItem("amw-projekt", uid); sessionStorage.setItem("amw-gewechselt", uid); } catch (e) {}
  const u = new URL(location.href); u.searchParams.set("projekt", uid);
  let s = "start"; try { s = localStorage.getItem(`amw-sicht:${uid}`) || "start"; } catch (e) {}
  u.hash = s; location.href = u.toString();          /* neue Adresse = neu laden: die ganze Oberfläche zeigt das Projekt */
}


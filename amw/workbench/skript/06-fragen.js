/* --- Fragen -------------------------------------------------------------------------------- */
/* A1657 (Marcel 14.11.): Fragen mit den Reitern Offen · Freigaben · Geparkt · Erledigt – „Freigaben“ sind vorgelegte
   Spezifikationen und Pläne, die nur du freigibst (freigegeben wird in der Planung, dort steht alles dazu). */
function freigabenListe() {
  const pw = zustand.start?.planung_wartet || { spezifikationen: [], plaene: [] };
  const karten = [...pw.spezifikationen.map(s => el("div", { class: "karte klickbar", onclick: () => zuSchritt(null, s.bogen_id) },
      el("div", { class: "meta" }, el("span", { class: "ref" }, bogenRef(s.bogen_id)), el("span", { class: "etikett bernstein" }, t("pl_freigabe_noetig"))),
      el("p", {}, t("pl_spec_frei", { b: bogenNr(s.bogen_id), x: s.titel, teil: t("teil_" + s.teil), v: s.version })),
      el("p", { class: "leise", style: "margin:0;font-size:12.5px" }, specWer({ ...s, status: "vorgelegt" }).slice(3)),
      el("div", { class: "sehrleise", style: "margin-top:6px" }, t("f_freigabe_weg")))),
    ...pw.plaene.map(p => el("div", { class: "karte klickbar", onclick: () => zuSchritt(p.id, null) },
      el("div", { class: "meta" }, el("span", { class: "ref" }, `A${p.id}`), el("span", { class: "etikett bernstein" }, t("pl_freigabe_noetig"))),
      el("p", {}, t("pl_plan_frei", { a: p.id, x: p.titel, ag: p.agent || "–" })),
      el("div", { class: "sehrleise", style: "margin-top:6px" }, t("f_freigabe_weg"))))];
  return karten;
}
function erledigtKarte(f) {
  const antwort = f.status === "verworfen" ? t("f_verworfen") : f.antwort_art === "option"
    ? `${f.antwort}${f.option_text ? " – " + f.option_text : ""}` : (f.antwort || "–");
  return el("div", { class: "karte" }, el("div", { class: "meta", style: "display:flex;gap:8px;flex-wrap:wrap" }, el("span", { class: "ref" }, `F${f.id}`), el("span", {}, t("von", { x: f.von })),
      f.antwort_utc ? el("span", { class: "sehrleise" }, t("f_beantwortet_am", { x: zeit(f.antwort_utc) })) : null),
    el("p", { style: "margin:4px 0" }, el("b", {}, f.kurz)), el("p", { class: "leise", style: "margin:0" }, el("b", {}, t("f_antwort") + " "), antwort));
}
async function sichtFragen() {
  const m = rahmen(t("n_fragen"), el("span", { class: "leise" }, t("f_unter")));
  let alle; try { alle = await holen("/api/fragen?alle=1"); } catch (e) { m.append(el("div", { class: "leer" }, String(e))); return; }
  if (!zustand.start) { try { await kopfAktualisieren(); } catch (e) {} }
  const sicht = ["offen", "freigaben", "geparkt", "erledigt"].includes(zustand.fragenSicht) ? zustand.fragenSicht : "offen";
  const freigaben = freigabenListe();
  const zahl = { offen: alle.filter(f => !f.geparkt_utc).length, freigaben: freigaben.length, geparkt: alle.filter(f => f.geparkt_utc).length, erledigt: null };
  m.append(el("div", { class: "reiter" }, ["offen", "freigaben", "geparkt", "erledigt"].map(s => el("button", { class: s === sicht ? "an" : "", type: "button",
    onclick: () => { zustand.fragenSicht = s; sichtFragen(); } }, t("fr_" + s), zahl[s] == null ? null : el("span", { class: "zahl" }, ` ${zahl[s]}`)))));
  if (sicht === "freigaben") {
    m.append(freigaben.length ? el("div", { class: "zeile-reveal wartet" }, freigaben) : el("div", { class: "leer" }, t("f_keine_freigaben")));
    return;
  }
  if (sicht === "erledigt") {
    let erl; try { erl = await holen("/api/fragen?erledigt=1"); } catch (e) { m.append(el("div", { class: "leer" }, String(e))); return; }
    m.append(erl.length ? el("div", { class: "zeile-reveal wartet" }, erl.map(erledigtKarte)) : el("div", { class: "leer" }, t("f_keine_erledigt")));
    return;
  }
  const geparkt = sicht === "geparkt";
  const liste = alle.filter(f => !!f.geparkt_utc === geparkt);
  const nachtraege = liste.flatMap(f => f.nachtrag_ids || []);      /* A1837: angezeigt = gelesen (das Etikett „neu“ steht noch dieses Mal) */
  if (nachtraege.length) schicken("/api/gelesen", { ids: nachtraege }).then(() => kopfAktualisieren()).catch(() => {});
  if (geparkt && liste.length) m.append(el("p", { class: "leise", style: "margin:0 0 12px" }, t("f_geparkt_hinweis")));
  if (!liste.length) { m.append(el("div", { class: "leer" }, t(geparkt ? "keine_geparkt" : "keine_fragen"))); return; }
  m.append(el("div", { class: "zeile-reveal" }, liste.map(frageKarte)));
}
/* Kennung und Text einer Option zum Anzeigen. Alte Fragen haben teils den ganzen Satz als Kennung („V0: …“, Text leer) –
   dann vorn die kurze Kennung abtrennen; gewählt wird weiter mit der gespeicherten Kennung. */
function optionZeigen(o) {
  if ((o.text || "").trim() || (o.kenn || "").length <= 12) return { kenn: o.kenn, text: o.text };
  const m = o.kenn.match(/^\s*([^\s=:)]{1,12})\s*[:=)]\s*([\s\S]+)$/);
  return m ? { kenn: m[1], text: m[2] } : { kenn: "", text: o.kenn };
}
function frageKarte(f) {
  const echteOptionen = f.optionen.filter(o => o.kenn && o.kenn !== "alt");
  const empfKurz = f.empfehlung ? (optionZeigen({ kenn: f.empfehlung }).kenn || "") : "";
  const notiz = el("textarea", { placeholder: echteOptionen.length ? t("anmerkung_ph") : t("antwort_ph") });
  const meldung = el("span", { class: "rueckmeldung leise" });
  const karte = el("div", { class: "karte frage" });
  const sperren = text => { for (const b of karte.querySelectorAll("button")) b.disabled = true; notiz.disabled = true; meldung.textContent = text; };
  async function antworten(art, wert, anmerkung) {
    try { const r = await schicken(`/api/frage/${f.id}/antwort`, { art, wert, anmerkung });
      const offen = r.status === "offen" || art === "rueckfrage";
      sperren(offen ? t("rueckfrage_gesendet") : t("beantwortet"));
      if (!offen) { toast(t("beantwortet")); karte.classList.add("weg"); setTimeout(() => karte.remove(), 320); }
    } catch (e) { toast(t("fehler", { x: e.message }), true); }
  }
  async function parken(ja) {
    try { await schicken(`/api/frage/${f.id}/${ja ? "parken" : "aufnehmen"}`, { grund: notiz.value.trim() });
      sperren(t(ja ? "f_geparkt_ok" : "f_aufgenommen")); toast(t(ja ? "f_geparkt_ok" : "f_aufgenommen"));
      karte.classList.add("weg"); setTimeout(() => karte.remove(), 320); }
    catch (e) { toast(t("fehler", { x: e.message }), true); }
  }
  karte.append(...[                                                        // DOM-append schriebe null als Text
    el("div", { class: "meta" }, el("span", { class: "ref" }, `F${f.id}`), t("von", { x: f.von }), el("span", { class: "sehrleise" }, `${zeit(f.zeit_utc)} · ${seit(f.zeit_utc)}`),
      f.blockiert ? el("span", { class: "etikett rot" }, t("blockiert_arbeit")) : null,
      f.aufgabe_id ? el("span", { class: "etikett" }, `A${f.aufgabe_id}`) : null,
      f.wartet_auf_fragesteller ? el("span", { class: "etikett bernstein" }, t("wartet_auf_x", { x: f.von })) : null,
      f.geparkt_utc ? el("span", { class: "etikett" }, t("f_geparkt_etikett", { z: zeit(f.geparkt_utc), x: f.geparkt_von === "Entwickler" ? t("du") : f.geparkt_von })) : null),
    el("h3", {}, f.kurz),
    (f.haelt || []).length ? el("div", { class: "haelt" }, f.haelt.map(x => el("span", { class: "etikett rot", title: x.titel },
      t("f_haelt", { a: `A${x.id}`, x: x.agent || "–", z: zeit(x.seit) })))) : null,
    f.worum ? el("p", { class: "worum" }, f.worum) : null,
    (f.dokumente || []).length ? el("div", { class: "dk-anhaenge" }, f.dokumente.map(x => el("button", { class: "dk-anhang", type: "button", onclick: () => dokumentDialog(x.id) },
      [".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg"].includes(x.endung) && (!API || x.online) ? el("img", { src: dokUrl(x.id), alt: "", loading: "lazy", onerror: e => e.target.remove() }) : null,
      `D${x.id} · ${x.titel}`))) : null].filter(Boolean));
  /* Varianten (amw frage neu --anhang A=…): groß ansehen per Klick, gewählt wird unten wie immer */
  const varianten = echteOptionen.filter(o => o.anhang);
  if (varianten.length) {
    const zeigbar = x => !API || x.online;
    const bilder = varianten.filter(o => o.anhang.vorschau === "bild" && zeigbar(o.anhang));
    karte.append(el("div", { class: "varianten" }, varianten.map(o => { const x = o.anhang;
      return el("button", { class: "variante" + (o.kenn === f.empfehlung ? " empfohlen" : ""), type: "button", title: t("dk_variante_tipp"),
        onclick: () => x.vorschau === "bild" && zeigbar(x) ? bildVollbild(bilder.map(b => ({ id: b.anhang.id, titel: `${b.kenn} · ${b.text}` })), bilder.indexOf(o)) : dokumentDialog(x.id) },
        el("div", { class: "variante-bild" }, x.vorschau === "bild" && zeigbar(x) ? el("img", { src: dokUrl(x.id), alt: "", loading: "lazy" })
          : x.vorschau === "mockup" && zeigbar(x) ? el("iframe", { src: dokUrl(x.id), sandbox: "allow-scripts", tabindex: "-1", title: o.text, referrerpolicy: "no-referrer", loading: "lazy" })
          : dokSymbol(x)),
        el("div", { class: "variante-text" }, el("span", { class: "kenn" }, optionZeigen(o).kenn), el("span", {}, optionZeigen(o).text))); })));
  }
  /* Gesprächsverlauf wie im Chat: Fragesteller links, du (Entwickler) rechts */
  if ((f.verlauf || []).length) karte.append(el("div", { class: "verlauf" }, f.verlauf.map(v => {
    const ich = v.von === "Entwickler";
    const vermerk = v.art === "nachtrag" && /^(Geparkt|Wieder aufgenommen)(:|$)/.test(v.text);   // amw frage parken/aufnehmen
    return el("div", { class: "blase" + (ich ? " ich" : "") + (v.unterwegs ? " unterwegs" : "") + (vermerk ? " vermerk" : "") },
      el("div", { class: "wer" }, `${ich ? t("du") : v.von} · ${t(vermerk ? "v_park" : "v_" + v.art)} · ${v.unterwegs ? t("s_briefkasten", { n: 1 }) : seit(v.zeit_utc)}`),
      el("div", { class: "was" }, v.text));
  })));
  if (echteOptionen.length) {
    karte.append(el("div", { class: "optionen" }, echteOptionen.map(o => el("button", {
      type: "button", class: "option" + (o.kenn === f.empfehlung ? " empfohlen" : ""),
      onclick: e => { e.currentTarget.classList.add("gewaehlt"); antworten("option", o.kenn, notiz.value); } },
      el("span", { class: "kenn" }, optionZeigen(o).kenn), el("span", {}, optionZeigen(o).text), o.kenn === f.empfehlung ? el("span", { class: "etikett bernstein" }, t("empfehlung")) : el("span")))));
  } else if (f.optionen.length) {
    karte.append(el("div", { class: "grund" }, el("b", {}, t("optionen")), f.optionen.map(o => o.text).join(" · ")));
  }
  if (f.grund) karte.append(el("div", { class: "grund" }, el("b", {}, f.empfehlung ? t("warum", { k: empfKurz || f.empfehlung }) : ""), f.grund));
  if (f.fundstellen) karte.append(el("div", { class: "sehrleise mono", style: "margin:6px 0;overflow-wrap:anywhere" }, t("fundstellen") + f.fundstellen));
  if (f.geprueft) karte.append(el("div", { class: "sehrleise", style: "margin:6px 0;overflow-wrap:anywhere" }, el("b", {}, t("f_geprueft")), f.geprueft));
  karte.append(notiz, el("div", { class: "aktionen" },
    el("button", { class: "knopf" + (echteOptionen.length ? "" : " haupt"), type: "button", onclick: () => notiz.value.trim() ? antworten("text", notiz.value) : toast(t("text_fehlt"), true) }, t("eigene_antwort")),
    el("button", { class: "knopf", type: "button", onclick: () => notiz.value.trim() ? antworten("rueckfrage", notiz.value) : toast(t("rueckfrage_fehlt"), true) }, t("rueckfrage")),
    el("button", { class: "knopf", type: "button", onclick: () => dokHochladen({ bezug: `frage:${f.id}` }) }, t("dk_anhaengen")),
    f.geparkt_utc ? el("button", { class: "knopf", type: "button", onclick: () => parken(false) }, t("f_aufnehmen"))
      : el("button", { class: "knopf", type: "button", title: t("f_parken_tipp"), onclick: () => parken(true) }, t("f_parken")),
    meldung));
  if (f.vorgeschichte.length) karte.append(el("details", { class: "vor" }, el("summary", {}, t("vorgeschichte", { n: f.vorgeschichte.length })),
    f.vorgeschichte.map(v => el("div", { class: "vor-eintrag" }, el("div", {}, el("span", { class: "ref" }, v.ref), " ", el("span", { class: "sehrleise" }, v.art)),
      el("div", {}, el("div", {}, v.titel, v.zusatz ? el("span", { class: "sehrleise" }, `  · ${v.zusatz}`) : null, v.zeit ? el("span", { class: "sehrleise" }, `  · ${zeit(v.zeit)}`) : null),
        v.text ? el("div", { class: "text" }, v.text) : null)))));
  return karte;
}


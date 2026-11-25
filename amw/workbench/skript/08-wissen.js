/* --- Wissen -------------------------------------------------------------------------------- */
/* Themen: je System eine Seite „gilt jetzt“ – gepflegte Zusammenfassung + geltende Beschlüsse; Stil mit Bildern */
function themenAnsicht(th, q) {
  q = (q || "").toLowerCase();
  const l = th.filter(x => !q || x.name.toLowerCase().includes(q)).sort((a, b) => (b.stil - a.stil) || (b.gilt - a.gilt));
  const stand = x => x.stand === "veraltet" ? el("span", { class: "etikett bernstein" }, t("th_veraltet", { b: x.veraltet_seit }))
    : x.stand === "aktuell" ? el("span", { class: "etikett gruen" }, t("th_aktuell")) : el("span", { class: "etikett" }, t("th_ohne"));
  return el("div", {}, el("p", { class: "leise", style: "margin:0 0 12px" }, t("th_erkl"), " ", hilfeKnopf("themen")),
    el("div", { class: "themen-raster" }, l.map(x => el("div", { class: "karte thema klickbar", onclick: () => themaDialog(x.id) },
      el("div", { class: "kopfzeile" }, el("span", { class: "ref" }, `TH${x.id}`), x.stil ? el("span", { class: "etikett gruen" }, t("th_stil")) : null, stand(x)),
      el("b", {}, x.name),
      el("div", { class: "sehrleise", style: "margin-top:6px" }, t("th_zahlen", { g: x.gilt, p: x.pfleger || "–" })
        + (x.unklar ? " · " + t("th_unklar", { n: x.unklar }) : ""))))));
}
async function themaDialog(id) {
  let s; try { s = await abrufen("/api/thema?id=" + id); } catch (e) { toast(t("fehler", { x: e.message }), true); return; }
  const z = s.zusammenfassung;
  const bilder = s.dokumente.filter(d => d.vorschau === "bild" && (!API || d.online));
  dialog(`TH${s.id} · ${s.name}`, el("div", { class: "thema-seite" },
    el("div", { class: "sehrleise" }, (s.stil ? t("th_stil") + " · " : "") + t("th_pfleger", { p: s.pfleger || "–" })),
    el("h3", {}, t("th_gilt_jetzt"), s.stand === "veraltet" ? el("span", { class: "etikett bernstein", style: "margin-left:8px" }, t("th_veraltet", { b: s.veraltet_seit })) : null),
    z ? el("div", {}, el("div", { class: "sehrleise" }, t("th_fassung", { n: z.nr, v: z.von, x: zeit(z.zeit_utc) })), el("div", { class: "md" }, markdown(z.text)))
      : el("div", { class: "leer" }, t("th_keine_zf")),
    bilder.length ? el("div", { class: "thema-bilder" }, bilder.map((d, i) => el("img", { src: dokUrl(d.id), alt: d.titel, title: d.titel,
      onclick: () => bildVollbild(bilder.map(b => ({ id: b.id, titel: b.titel })), i) }))) : null,
    el("h3", {}, t("th_beschluesse", { n: s.gilt.length })),
    s.gilt.map(b => el("div", { class: "karte wissen-eintrag" }, el("div", { class: "kopfzeile" }, el("span", { class: "ref" }, `B${b.id}`),
      el("b", {}, b.stichwort), el("span", { class: "sehrleise" }, `${zeit(b.zeit_utc)} · ${b.quelle}`), postKnopf(`B${b.id}`, `B${b.id} ${b.stichwort}`)), el("div", { class: "inhalt" }, b.regel))),
    s.unklar.length ? el("p", { class: "bernstein-text" }, t("th_unklar", { n: s.unklar.length }) + ": " + s.unklar.map(b => `B${b.id}`).join(", ")) : null,
    s.ueberholt.length ? el("details", {}, el("summary", {}, t("th_ueberholt", { n: s.ueberholt.length })),
      s.ueberholt.map(b => el("div", { class: "sehrleise" }, `B${b.id} ${b.stichwort}` + (b.ersetzt_durch ? ` → B${b.ersetzt_durch}` : "")))) : null,
    gespraechZu(`T${s.id}`, `T${s.id} ${s.name}`, s.pfleger)));
}
/* A1896 (D1319, W2429–W2431): Themen – ein Status je Thema, der Text als Ganzes, nur die gerade möglichen Handlungen.
   Was intern zwischen AMW und Agenten läuft (Beschlüsse, Gegenlesen, Fassungen), zeigt diese Ansicht nicht. Handy: erst die Liste. */
const TH_VORRANG = ["markiert", "dich", "pruefen", "frei", "arbeit"];          /* D1326 A16: die Sortierung folgt dem Vorrang */
const thRang = z => TH_VORRANG.indexOf(z.markiert ? "markiert" : z.status);
async function sichtThemen() {
  const m = rahmen(t("n_themen"));
  let liste; try { liste = await holen("/api/themen"); } catch (e) { m.append(el("div", { class: "leer" }, String(e.message || e))); return; }
  const zaehlen = liste.filter(x => !x.zustand.markiert);                       /* D1326 A28: Markierte zählen nicht */
  const neuKnopf = !API && (liste[0]?.neu_erlaubt ?? true) ? el("button", { class: "klein-knopf th-neu", type: "button", onclick: () => thNeu() }, t("th2_neu")) : null;
  /* A1972 (Marcel W2464, TH156): oben nur die fünf Tor-Chips (Werte auf Klick), darunter höchstens EINE Zeile – nur wenn du handeln
     musst. Zählungen der Meilensteine stehen in der Planung, Co/Lead-Interna nie hier. */
  const toreFeld = el("div", { class: "th-tore" }), dichFeld = el("div", { class: "th-dich" });
  m.append(el("div", { class: "th-stand" }, toreFeld, neuKnopf), dichFeld);
  const zumThema = () => { const x = zaehlen.find(y => y.zustand.status === "dich"); if (x) { zustand.themaOffen = x.id; zeige("themen", true); } };
  holen("/api/tore").then(d => { const l = toreLeiste(d, true); if (l) toreFeld.replaceChildren(l);
    const z = toreDich(d.fuer_dich, zumThema); dichFeld.replaceChildren(...(z ? [z] : [])); }).catch(() => {});
  const neuKasten = el("div", { class: "th-kasten" }); m.append(neuKasten);
  function thNeu() {                                                            /* F5360 A: Titel und Text, danach in Arbeit */
    const name = el("input", { class: "th-feld th-titel", placeholder: t("th2_neu_titel") }), text = el("textarea", { class: "th-feld", placeholder: t("th2_neu_text") });
    neuKasten.replaceChildren(name, text, el("div", { class: "th-knoepfe" },
      el("button", { class: "klein-knopf haupt", type: "button", onclick: async () => { if (!name.value.trim()) { name.focus(); return; }
        try { const r = await schicken("/api/thema/neu", { name: name.value.trim(), text: text.value }); toast(t("th2_ok_neu")); zustand.themaOffen = r.thema; zeige("themen", true); }
        catch (e) { toast(t("fehler", { x: e.message }), true); } } }, t("th2_anlegen")),
      el("button", { class: "klein-knopf", type: "button", onclick: () => neuKasten.replaceChildren() }, t("abbrechen"))));
    name.focus();
  }
  if (!liste.length) { m.append(el("div", { class: "leer" }, t("th2_leer"))); return; }
  liste.sort((a, b) => (thRang(a.zustand) - thRang(b.zustand)) || a.name.localeCompare(b.name));
  const schmal = matchMedia("(max-width: 760px)").matches;
  let offen = zustand.themaOffen ?? (schmal ? null : liste[0].id);                     /* Auflage (a): am Handy zuerst die Liste */
  const raster = el("div", { class: "th-raster" + (zustand.themaOffen ? " offen" : "") });
  const links = el("div", { class: "th-liste" }), rechts = el("div", { class: "th-thema" });
  const thLiest = g => t("th2_gegenlesen", { z: new Date(g.seit_utc).toLocaleTimeString(gebiet(), { hour: "2-digit", minute: "2-digit" }) });
  const etikett = z => el("span", { class: "th-status " + (z.markiert ? "loeschen" : z.status) }, z.markiert ? t("th2_markiert") : t("th2_" + z.status));
  const zeichneListe = () => links.replaceChildren(...liste.map(x => el("div", {
    class: "th-zeile" + (x.id === offen ? " gewaehlt" : "") + (x.zustand.markiert ? " markiert" : ""), "data-th": x.id,
    onclick: () => { offen = x.id; zustand.themaOffen = x.id; raster.classList.add("offen"); zeichneListe(); zeichneThema(); } },
    el("span", { class: "th-name" }, x.name,
      x.zustand.grund ? el("span", { class: "th-grund-zeile" }, t("th2_grund", { x: x.zustand.grund })) : null,   /* P306 (2): Grund auch in der Liste */
      x.zustand.gegenlesen ? el("span", { class: "th-grund-zeile" }, thLiest(x.zustand.gegenlesen)) : null),          /* A1914: nur der Status als Fakt */
    etikett(x.zustand))));
  async function zeichneThema() {
    if (!offen) { rechts.replaceChildren(el("div", { class: "leer" }, t("th2_waehlen"))); return; }
    let s; try { s = await holen(`/api/thema?id=${offen}`); } catch (e) { rechts.replaceChildren(el("div", { class: "leer" }, String(e.message || e))); return; }
    const z = s.zustand, text = s.zusammenfassung?.text || "", kasten = el("div", { class: "th-kasten" });
    const schliesst = h => (s.tor?.schliesst || []).includes(h);              /* A1913: diese Handlung schlösse das Tor Konzept */
    const tun = async (was, daten, ok) => { if (schliesst(was) && !confirm(t("th2_tor_frage"))) return;   /* W2449: Hinweis vorher, kein eigener Knopf */
      try { const r = await schicken(`/api/thema/${was}`, { thema: s.id, ...daten }) || {}; toast(schliesst(was) ? t("th2_ok_tor") : typeof ok === "function" ? ok(r) : ok); zustand.themaOffen = s.id; zeige("themen", true); }
      catch (e) { toast(t("fehler", { x: e.message }), true); } };
    const eingabe = h => {
      const feld = el("textarea", { class: "th-feld", placeholder: h === "zurueck" ? t("th2_notiz_ph") : "" });
      if (h === "bearbeiten") feld.value = text;
      kasten.replaceChildren(feld, el("div", { class: "th-knoepfe" },
        el("button", { class: "klein-knopf haupt", type: "button", onclick: () => { if (!feld.value.trim()) { feld.focus(); return; }
          if (h === "zurueck") tun("zurueck", { notiz: feld.value }, t("th2_ok_zurueck")); else tun("bearbeiten", { text: feld.value, fassung: z.fassung }, r => t(r.status !== "frei" ? "th2_ok_bearbeiten" : r.planer ? "th2_ok_bearbeiten_planer" : "th2_ok_bearbeiten_frei"));   /* D1326 A40: gegen die erwartete Fassung */ } },
          t(h === "zurueck" ? "th2_zurueckgeben" : "th2_speichern")),
        el("button", { class: "klein-knopf", type: "button", onclick: () => kasten.replaceChildren() }, t("abbrechen"))));
      feld.focus();
    };
    const knoepfe = API ? [el("span", { class: "sehrleise" }, t("th2_nur_pc"))] : s.handlungen.map(h => el("button", {
      class: "klein-knopf" + (h === "freigeben" ? " haupt" : ""), type: "button", "data-h": h,
      onclick: () => h === "freigeben" ? tun("freigeben", {}, t("th2_ok_freigeben")) : (h === "markieren" || h === "entmarkieren")
        ? tun(h, {}, t("th2_ok_" + h)) : eingabe(h) }, t("th2_h_" + h)));
    if (s.freigegeben_text) knoepfe.push(el("button", { class: "klein-knopf", type: "button", "data-h": "unterschied",   /* F5358 (#29401) */
      onclick: () => { if (kasten.firstChild) { kasten.replaceChildren(); return; }
        const absaetze = x => x.split(/\n\s*\n/).map(p => p.trim()).filter(Boolean);
        const alt = absaetze(s.freigegeben_text.text), neu = absaetze(text);
        const weg = alt.filter(p => !neu.includes(p)), dazu = neu.filter(p => !alt.includes(p));
        kasten.replaceChildren(el("div", { class: "sehrleise" }, t("th2_unterschied_kopf", { a: s.freigegeben_text.nr, n: z.fassung })),
          ...weg.map(p => el("p", { class: "th-weg" }, p)), ...dazu.map(p => el("p", { class: "th-dazu" }, p)),
          weg.length || dazu.length ? null : el("p", { class: "leise" }, t("th2_unterschied_keiner"))); } }, t("th2_unterschied")));
    rechts.replaceChildren(...[
      el("div", { class: "th-kopf" }, el("button", { class: "klein-knopf th-zur-liste", type: "button",
        onclick: () => { zustand.themaOffen = null; offen = null; raster.classList.remove("offen"); zeichneListe(); } }, "‹ " + t("n_themen")),
        el("h2", {}, s.name), etikett(z)),
      z.grund ? el("div", { class: "th-grund" }, t("th2_grund", { x: z.grund })) : null,           /* Auflage (c): Grund als Fakt */
      (z.ja_fehlt || []).length ? el("div", { class: "th-grund" }, t("th2_ja_fehlt", { x: z.ja_fehlt.join(", ") })) : null,   /* A1937 */
      z.nur_mensch ? el("div", { class: "th-grund" }, t("th2_nur_mensch")) : null,
      z.gegenlesen ? el("div", { class: "th-grund" }, thLiest(z.gegenlesen)) : null,                /* A1914: wer, seit wann */
      !z.gegenlesen && s.gegengelesen ? el("details", { class: "th-gegengelesen", "data-th-gegen": s.gegengelesen.fassung },   /* A1914: danach das Ergebnis */
        el("summary", { class: "sehrleise" }, t("th2_gegengelesen", { n: s.gegengelesen.fassung, m: s.gegengelesen.modell || "–",
          k: typeof s.gegengelesen.usd === "number" ? s.gegengelesen.usd.toFixed(2) + " $" : t("th2_kosten_unbekannt") })),
        s.gegengelesen.fehler ? el("p", { class: "leise" }, t("th2_gegen_fehler", { x: s.gegengelesen.fehler }))
          : el("div", { class: "md" }, markdown(s.gegengelesen.einwaende || ""))) : null,
      el("div", { class: "th-knoepfe" }, ...knoepfe), kasten,
      el("div", { class: "th-text md" }, text ? markdown(text) : el("p", { class: "leise" }, t("th2_ohne_text")))].filter(Boolean));
  }
  zeichneListe(); zeichneThema();
  raster.append(links, rechts); m.append(raster);
}
/* A2033 (TH164 F2, Kleinprobe D1516 v3, TL #31649/#31722): Projektweg – fünf Schritte als Leiste, darunter die Ansicht des
   gewählten Schritts, rechts der Verlauf (am Handy unter der Leiste). Alles kommt aus /api/projektweg (projektweg_seite.daten);
   der Browser merkt sich nur, welcher Schritt, welcher Meilenstein, welche Fassung und welches Seitenfenster offen ist.
   Läuft ein Planer, öffnet sich die Fortschrittsanzeige (Überlagerung) und schließt sich, sobald sein Ergebnis da ist. */
const PW_SCHRITTE = ["konzept", "grob", "fein", "umsetzung", "abschluss"];
let pwTakt = null, pwHaupt = null, pwStand = null;   /* pwStand: zuletzt gezeichnete Daten + Auswahl (A2060) */                /* pwHaupt: die Handlung des Schritts – steht oben neben der Überschrift (TL #31991) */
const pwDranNr = d => d.dran ? PW_SCHRITTE.indexOf(d.dran) : 4;
const pwM = m => "M" + m.nr;                         /* eine Nummer je Meilenstein: die Projektnummer (TH156, TL #32159 Punkt 7) */
const pwThemaName = (d, id) => (d.konzept.themen.find(x => x.id === id) || {}).name || "";
const pwFeinOffen = d => { const o = d.fein.meilensteine.filter(m => (!m.frei || m.delta_start) && !m.laeuft && (m.pakete.length || m.fehler) && m.status === "geplant");
  return o.find(m => !m.fehler) || o[0]; };                            /* ein Plan, der auf dich wartet, geht vor einem abgelehnten */
/* A2106: Einzahl, wenn es genau eins ist und der Text eine hat (Schlüssel + "1") */
const pwN = (k, n, v = {}) => t(n === 1 && (k + "1") in TEXTE.de ? k + "1" : k, { n, ...v });
const pwPakete = n => n === 1 ? t("pjw_ein_paket") : t("pjw_so_viele_pakete", { n });   /* A2061: laufende sind Umsetzung */
function pwFragenIn(d, i) {                    /* Paket im laufenden Meilenstein → Umsetzung, sonst Feinplan; ohne Paket → wo es gerade steht */
  const aktiv = new Set(d.umsetzung.meilensteine.map(m => m.bogen)), dran = Math.min(pwDranNr(d), 3);
  return d.fragen.filter(f => f.bogen ? (aktiv.has(f.bogen) ? 3 : 2) === i : i === dran);
}
async function pwTun(weg, daten, ok) {
  return einmalTun(weg + JSON.stringify(daten), async () => { const r = await schicken(weg, daten) || {};
    const fehlt = r.ja_fehlt ? (Array.isArray(r.ja_fehlt) ? r.ja_fehlt.join(", ") : r.ja_fehlt) : null;
    toast(fehlt ? t("pjw_ja_fehlt", { x: fehlt }) : ok); zustand.pwFenster = null; zeige("projektweg", true); return r; });
}
function pwWert(d, i) {
  const k = d.konzept, g = d.grob, f = d.fein, u = d.umsetzung, a = d.abschluss;
  if (i === 0) return t("pjw_w_konzept", { n: k.n, g: k.g });
  if (i === 1) { if (g.laeuft) return t("pjw_in_arbeit");
    if (g.angenommen) return pwN("pjw_w_grob_ok", g.angenommen.n);
    if (!g.fassungen.length && (g.bestand || []).length) return pwN("pjw_w_grob_bestand", g.bestand.length);
    const l = g.fassungen.at(-1); return l ? t("pjw_fassung", { n: l.fassung }) : "–"; }
  if (i === 2) { const l = f.meilensteine.find(m => m.laeuft); if (l) return t("pjw_in_arbeit");
    const w = pwFeinOffen(d); if (w) return w.fehler ? t("pjw_w_fein_fehler", { m: pwM(w) }) : t("pjw_w_fein", { m: pwM(w), p: pwPakete(w.pakete.length) });
    const od = pwDeltaOffen(f);                                                                        /* A2118 */
    if (f.delta_fehler.length && !od.length) { const n = f.delta_fehler.length, teil = f.delta_fehler.filter(x => x.teilweise).length;   /* A2076; A2086: teilweise umgesetzt */
      const wort = teil === n ? "pjw_w_delta_teil" : teil ? "pjw_w_delta_klaeren" : "pjw_w_delta_fehler";
      return n === 1 ? t(wort + "1", { t: `TH${f.delta_fehler[0].thema}` }) : t(wort + "_n", { n }); }
    if (od.length) return od.length === 1 ? t("pjw_w_delta1", { t: `TH${od[0].thema}`, p: pwPakete(od[0].karten.length) })   /* A2068 */
      : t("pjw_w_delta_n", { n: od.length });
    const z = f.meilensteine.filter(m => m.frei && m.status !== "fertig").at(-1); if (z) return `${pwM(z)} · ${t("pjw_freigegeben")}`;
    return f.naechster ? t("pjw_w_naechster", { m: pwM(f.naechster) }) : "–"; }                     /* A2086: nach der Abnahme steht da, was als Nächstes geplant wird */
  if (i === 3) { const ms = u.meilensteine; if (!ms.length) return "–";
    const q = pwFragenIn(d, 3).length, fr = q ? " · " + (q === 1 ? t("pjw_frage1") : t("pjw_fragen", { n: q })) : "";
    if (ms.length > 1) return t("pjw_w_ums_n", { n: ms.length, f: ms.reduce((s, m) => s + m.fertig, 0), g: ms.reduce((s, m) => s + m.pakete.length, 0) }) + fr;   /* A2061 */
    return t("pjw_w_ums", { m: pwM(ms[0]), f: ms[0].fertig, n: ms[0].pakete.length }) + fr; }
  const offen = a.filter(x => x.bereit && !x.frei), w = offen.filter(x => x.bei_dir);            /* A2082: „bereit zur Abnahme“ nur, was der Mensch abnehmen kann */
  if (w.length) return `${w.map(x => pwM(x)).join(", ")} · ${t("pjw_bereit")}`;
  if (offen.length) return offen.map(x => `${pwM(x)} · ${pwLage(x)}${x.auslieferung?.length ? ` (${pwPaketListe(x)})` : ""}`).join(", ");
  const z = a.filter(x => x.frei).at(-1); return z ? `${pwM(z)} · ${t("pjw_abgenommen")}` : "–";
}
/* A2116: die Lage vor der Abnahme in Worten; wartet sie auf die Auslieferung, stehen die Pakete im langen Satz und in der Leiste. */
const pwPaketListe = x => (x.auslieferung || []).slice(0, 4).map(a => "A" + a).join(", ") + ((x.auslieferung || []).length > 4 ? ` +${x.auslieferung.length - 4}` : "");
const pwLage = x => t("pjw_l_" + x.lage);
const pwLageLang = x => t("pjw_ll_" + x.lage, { x: pwPaketListe(x) });
const pwStatus = (text, art) => el("span", { class: "pjw-status" + (art ? " " + art : "") }, text);
const pwKnopf = (text, onclick, haupt) => el("button", { class: "knopf" + (haupt ? " haupt" : ""), type: "button", onclick }, text);
const pwHandlungen = (...k) => el("div", { class: "pjw-handlungen" }, ...k.filter(Boolean));
function pwHinweisFeld(platz, id = "pjw-hw") {
  return el("div", { class: "pjw-hw-feld" }, el("label", { class: "pjw-lbl", for: id }, t("pjw_hinweis")), el("textarea", { id, class: "pjw-hinweis", placeholder: platz }));
}
const pwHinweisText = (id = "pjw-hw") => (document.getElementById(id)?.value || "").trim();
function pwFrage(f) {
  const wer = f.vom_lead ? t("pjw_lead_fragt") : t("pjw_fragt", { x: f.von });          /* ohne Paket: nur wer fragt – die Herkunft steht in der Frage */
  return el("div", { class: "pjw-frage" }, el("span", { class: "pjw-lbl" }, f.paket ? `${wer} · ${t("pjw_aus_paket", { x: f.paket })}` : wer), frageKarte(f));
}
function pwStufen(pakete, mitStatus) {
  const stufen = [...new Set(pakete.map(p => p.stufe))].sort((a, b) => a - b);
  return el("div", { class: "pjw-stufen" }, stufen.map(s => el("div", { class: "pjw-stufe" }, el("span", { class: "pjw-snr" }, s),
    el("div", { class: "pjw-pakete" }, pakete.filter(p => p.stufe === s).map(p => el("button", {
      class: "pjw-paket" + (mitStatus && p.status === "blockiert" ? " blockiert" : ""), type: "button", "data-paket": p.id,
      onclick: () => pwOeffne({ art: "paket", id: p.id }) },
      el("span", { class: "pjw-t" }, p.titel),
      el("span", { class: "pjw-u" }, el("span", {}, p.wer), mitStatus
        ? pwStatus(t("pjw_p_" + (["laeuft", "fertig", "blockiert", "wartet"].includes(p.status) ? p.status : "offen")),
                   { laeuft: "laeuft", fertig: "frei", blockiert: "dran" }[p.status] || "")
        : el("span", { class: "pjw-rechts" }, p.groesse || ""))))))));
}
function pwKonzept(d) {
  const k = d.konzept;
  if (!k.themen.length) return [el("div", { class: "leer" }, t("pjw_k_leer"), " ", el("a", { href: "#themen", onclick: e => { e.preventDefault(); zeige("themen"); } }, t("pjw_zu_themen")))];
  const teile = [el("div", { class: "pjw-liste" }, k.themen.map(x => el("div", { class: "pjw-zeile", "data-th": x.id, onclick: () => pwOeffne({ art: "thema", id: x.id }) },
    el("span", { class: "pjw-nr" }, `TH${x.id}`), el("span", {}, x.name),
    pwStatus(x.markiert ? t("th2_markiert") : t("th2_" + (x.status || "arbeit")), x.status === "dich" ? "dran" : x.status === "frei" ? "frei" : ""))))];
  if (!k.zu) teile.push(el("div", { class: "leise" }, t("pjw_k_erst", { n: k.n, g: k.g }), " ",
    el("a", { href: "#themen", onclick: e => { e.preventDefault(); zeige("themen"); } }, t("pjw_zu_themen"))));
  else if (k.bestand) teile.push(el("div", { class: "leise" }, pwN("pjw_k_bestand", k.bestand)));   /* A2061: A2030 kennt keine Übernahme */
  else if (!API && !k.abgeschlossen && !k.grob_angenommen && !k.grob_laeuft)
    pwHaupt = pwKnopf(t("pjw_k_abschliessen"), () => pwTun("/api/projektweg/konzept-abschliessen", {}, t("pjw_ok_abgeschlossen")), true);
  return teile;
}
function pwGrob(d) {
  const g = d.grob, teile = [];
  if (g.laeuft) teile.push(el("div", { class: "leer" }, t("pjw_g_laeuft")));
  if (!g.fassungen.length && (g.bestand || []).length) return [el("div", { class: "leise" }, pwN("pjw_g_bestand", g.bestand.length)),   /* A2061 */
    el("div", { class: "pjw-liste" }, g.bestand.map(b => el("div", { class: "pjw-zeile pjw-zeile-statisch" }, el("span", { class: "pjw-nr" }, pwM(b)), el("span", {}, b.titel),
      el("span", { class: "pjw-rechts" }, b.status === "fertig" ? t("pjw_p_fertig") : t("pjw_f_von_n", { f: b.fertig, n: b.pakete })))))];
  if (!g.fassungen.length) return g.laeuft ? teile : [el("div", { class: "leer" }, t("pjw_g_leer"))];
  const nrs = g.fassungen.map(f => f.fassung);
  const gew = nrs.includes(zustand.pwFassung) ? zustand.pwFassung : (g.angenommen?.fassung ?? nrs.at(-1));
  const f = g.fassungen.find(x => x.fassung === gew), neueste = gew === nrs.at(-1);
  const ae = f.aenderung, nAe = ae ? ae.neu.length + ae.geaendert.length + ae.entfallen.length : 0;
  const markiert = titel => ae && (ae.neu.includes(titel) ? "neu" : ae.geaendert.some(x => x.titel === titel) ? "geaendert" : null);
  teile.push(el("div", { class: "pjw-kopf" }, nrs.length > 1 ? el("span", { class: "pjw-seg" }, [...nrs].reverse().map(n => el("button", { type: "button", class: n === gew ? "an" : "",
    onclick: () => { zustand.pwFassung = n; zeige("projektweg", true); } }, t("pjw_fassung", { n })))) : el("span", { class: "leise" }, t("pjw_fassung", { n: gew })),
    nAe ? el("span", { class: "pjw-marke" }, nAe === 1 ? t("pjw_aenderung1") : t("pjw_aenderungen", { n: nAe })) : null,
    f.angenommen ? pwStatus(t("pjw_freigegeben"), "frei") : null));
  if (f.fehler) teile.push(el("div", { class: "leer" }, t("pjw_fehler_fassung", { n: f.fassung, x: f.fehler })));
  else {
    const msVon = id => f.meilensteine.filter(m => (m.themen || []).includes(id)).map(m => m.schluessel);
    teile.push(el("div", { class: "pjw-zwei" },
      el("div", {}, el("div", { class: "pjw-lbl" }, t("pjw_th_ms")), el("div", { class: "pjw-liste" }, d.konzept.themen.filter(x => x.status === "frei").map(x =>
        el("div", { class: "pjw-zeile", onclick: () => pwOeffne({ art: "thema", id: x.id }) }, el("span", { class: "pjw-nr" }, `TH${x.id}`), el("span", {}, x.name),
          el("span", { class: "pjw-rechts" }, msVon(x.id).join(" · ") || "–"))))),
      el("div", {}, el("div", { class: "pjw-lbl" }, t("pjw_meilensteine")), el("div", { class: "pjw-karten" }, f.meilensteine.map(m => { const mk = markiert(m.titel);
        return el("button", { class: "pjw-karte" + (mk ? " geaendert" : ""), type: "button", "data-ms": m.schluessel, onclick: () => pwOeffne({ art: "ms", id: m.schluessel, fassung: f.fassung }) },
          el("span", { class: "pjw-oben" }, el("b", {}, `${m.schluessel} ${m.titel}`), m.tage ? el("span", { class: "pjw-rechts" }, m.tage === 1 ? t("pjw_tag1") : t("pjw_tage", { n: m.tage })) : null),
          m.fertig_wenn ? el("span", {}, el("span", { class: "leise" }, t("pjw_fertig_wenn")), m.fertig_wenn) : null,
          el("span", { class: "sehrleise" }, [(m.themen || []).map(n => `TH${n}`).join(" · "), (m.nach || []).length ? t("pjw_nach", { x: m.nach.join(", ") }) : null,
            (m.gleichzeitig || []).length ? t("pjw_gleichzeitig", { x: m.gleichzeitig.join(", ") }) : null].filter(Boolean).join(" · ")),
          mk ? el("span", { class: "pjw-marke" }, t(mk === "neu" ? "pjw_neu" : "pjw_geaendert")) : null); }),
        ae && ae.entfallen.length ? el("div", { class: "sehrleise" }, t("pjw_entfallen", { x: ae.entfallen.join(", ") })) : null))));
    if (f.befunde.length) teile.push(el("div", {}, el("div", { class: "pjw-lbl" }, t("pjw_funde")), f.befunde.map(b => el("div", { class: "pjw-fund" },
      el("span", { class: "pjw-art" }, t("pjw_b_" + b.art)), el("span", {}, [(b.themen || []).map(n => `TH${n}`).join(", "), b.text].filter(Boolean).join(": "),
        b.vorschlag ? el("span", { class: "leise" }, " → " + b.vorschlag) : null)))));
    if (f.fragen.length) teile.push(el("div", {}, el("div", { class: "pjw-lbl" }, t("pjw_planer_fragen")), f.fragen.map(q => el("div", { class: "pjw-fund" },
      el("span", { class: "pjw-art" }, (q.themen || []).map(n => `TH${n}`).join(", ") || "–"), el("span", {}, q.frage,
        q.empfehlung && q.optionen?.[q.empfehlung] ? el("span", { class: "leise" }, " · " + t("pjw_empfehlung", { x: q.optionen[q.empfehlung] })) : null)))));
  }
  teile.push(...pwFragenIn(d, 1).map(pwFrage));
  const offen = g.hinweise.filter(h => h.offen);
  if (offen.length) teile.push(el("div", { class: "pjw-hinweise" }, el("div", { class: "pjw-lbl" }, t("pjw_hinweise")),
    offen.map(h => el("div", {}, h.bezug ? el("b", {}, h.bezug + ": ") : null, h.text, el("span", { class: "sehrleise" }, ` · ${h.von === "Entwickler" ? t("du") : h.von}`)))));
  if (!API && !g.angenommen && !g.laeuft && neueste) {
    teile.push(pwHinweisFeld(t("pjw_hinweis_ph")));
    if (!f.fehler) pwHaupt = pwKnopf(t("pjw_g_freigeben"), () => pwTun("/api/projektweg/grob-freigeben", { fassung: f.fassung }, t("pjw_ok_grob")), true);
    teile.push(pwHandlungen(pwKnopf(t("pjw_ueberarbeiten"), () => { const x = pwHinweisText(); if (!x && !offen.length) { toast(t("pjw_text_fehlt"), true); return; }
        pwTun("/api/projektweg/ueberarbeiten", { plan: "grob", text: x }, t("pjw_ok_ueberarbeiten")); })));
  }
  return teile;
}
function pwFein(d) {
  const f = d.fein, teile = [];
  const offenerPlan = pwFeinOffen(d), lead = f.lead_klaert;
  const planWartet = !API && !!offenerPlan && !(offenerPlan.fehler && lead);                         /* eine Hauptaktion je Ansicht (TH156, TL #32217): zuerst der Plan */
  const od = pwDeltaOffen(f);                                                                          /* A2118: zurückgestellte zuletzt */
  [...od, ...f.delta.filter(x => x.wartet)].forEach((x, i) => teile.push(pwDeltaKarte(x, od.length === 1 && x === od[0] && !planWartet, !planWartet && x === od[0])));   /* A2065: Karten statt Textwand */
  f.delta_fehler.forEach((x, i) => teile.push(pwDeltaFehler(x, !lead && !planWartet && !od.length && i === 0, lead)));   /* A2076 */
  if (!f.meilensteine.length) return teile.concat(teile.length ? [] : [el("div", { class: "leer" }, t("pjw_f_leer"))]);
  const offen = f.meilensteine.filter(m => m.status !== "fertig");                  /* A2061: fertige Meilensteine nicht in der Auswahl */
  const gew = f.meilensteine.find(m => m.bogen === zustand.pwMs) || pwFeinOffen(d) || f.meilensteine.find(m => m.laeuft) || offen.at(-1) || f.meilensteine.at(-1);
  const chips = offen.includes(gew) ? offen : [...offen, gew];
  if (chips.length > 1) teile.push(el("div", { class: "pjw-chips" }, chips.map(m => el("button", { type: "button", class: "pjw-chip" + (m === gew ? " an" : ""),
    onclick: () => { zustand.pwMs = m.bogen; zeige("projektweg", true); } }, `${pwM(m)} ${m.titel}`))));
  teile.push(el("div", { class: "pjw-kopf" }, el("h3", {}, `${pwM(gew)} ${gew.titel}`), gew.laeuft ? pwStatus(t("pjw_in_arbeit")) : gew.status === "aktiv" ? pwStatus(t("pjw_laeuft")) : gew.status === "fertig" ? pwStatus(t("pjw_p_fertig"), "frei") : gew.frei ? pwStatus(t("pjw_freigegeben"), "frei")
    : gew.fehler && lead ? pwStatus(t("pjw_lead_klaert", { x: lead })) : pwStatus(t("pjw_wartet_dich"), "dran")));
  if (gew.start_fehlt.length) teile.push(el("div", { class: "pjw-fehler ruhig" }, t("pjw_start_fehlt", { x: gew.start_fehlt.map(x => `„${x}“`).join(", ") })));   /* A2080 */
  if (gew.delta_start?.fehler) teile.push(el("div", { class: "pjw-fehler" }, el("b", {}, t("pjw_delta_nicht_gestartet")), el("div", {}, gew.delta_start.fehler)));   /* A2080 (4) */
  if (gew.laeuft) teile.push(el("div", { class: "leer" }, t("pjw_f_laeuft", { n: gew.nr })));
  if (gew.fehler) teile.push(el("div", { class: "pjw-fehler" + (lead ? " ruhig" : "") }, el("b", {}, t("pjw_f_fehler", { n: gew.nr, f: gew.fassung || 1 })),   /* A2056 */
    el("ul", {}, gew.gruende.slice(0, 8).map(g => el("li", {}, t("pjw_fx_" + g.art, g.x))))));
  if (gew.pakete.length) {
    teile.push(el("div", { class: "pjw-werte" }, el("span", {}, el("b", {}, gew.pakete.length), " ", t(gew.pakete.length === 1 ? "pjw_paket_w" : "pjw_pakete_w")),
      el("span", {}, el("b", {}, gew.pakete.filter(p => p.art === "p").length), " Headless")));
    teile.push(pwStufen(gew.pakete, gew.frei));
  }
  teile.push(...pwFragenIn(d, 2).map(pwFrage));
  if (!API && gew.fehler) {                                             /* A2056: abgelehnter Feinplan → mit Hinweis neu planen lassen */
    teile.push(pwHinweisFeld(t("pjw_f_fehler_ph")));
    teile.push(pwHandlungen(pwKnopf(t("pjw_ueberarbeiten"), () => { const x = pwHinweisText(); if (!x) { toast(t("pjw_text_fehlt"), true); return; }
      pwTun("/api/meilenstein/fein-neu", { bogen: gew.bogen, hinweis: x }, t("pjw_ok_ueberarbeiten")); }, !lead && !od.length)));
  }
  if (!API && (!gew.frei || gew.delta_start) && !gew.laeuft && gew.pakete.length && gew.status === "geplant") {
    if (!gew.delta_start) teile.push(pwHinweisFeld(t("pjw_f_hinweis_ph")));
    pwHaupt = gew.delta_start                                           /* A2080 (5): aus einer freigegebenen Änderung – grob und fein frei, starten */
      ? pwKnopf(t("pjw_delta_nachholen", { n: gew.nr, t: `TH${gew.delta_start.thema}` }), () => pwTun("/api/projektweg/delta-starten", { bogen: gew.bogen }, t("pjw_ok_plan")), true)
      : pwKnopf(t("pjw_plan_starten", { n: gew.nr }), () => pwTun("/api/meilenstein/plan-starten", { bogen: gew.bogen }, t("pjw_ok_plan")), true);
    if (!gew.delta_start) teile.push(pwHandlungen(pwKnopf(t("pjw_ueberarbeiten"), () => { const x = pwHinweisText(); if (!x) { toast(t("pjw_text_fehlt"), true); return; }
        pwTun("/api/meilenstein/fein-neu", { bogen: gew.bogen, hinweis: x }, t("pjw_ok_ueberarbeiten")); })));
  }
  return teile;
}
const pwZielText = z => z.neu ? t("pjw_neuer_ms", { x: z.titel }) : `M${z.nr}`;
function pwDeltaFehler(x, haupt, lead) {
  /* A2076: eine gescheiterte Konzeptänderung – Grund in Menschensprache, Hinweis und „Überarbeiten lassen“ (wie beim Feinplan, A2056). */
  const karte = el("div", { class: "pjw-karte pjw-delta pjw-delta-fehler", "data-thema": x.thema },
    el("div", { class: "pjw-kopf" }, el("h3", {}, t("pjw_delta", { x: `TH${x.thema} ${x.name}` })), lead ? pwStatus(t("pjw_lead_klaert", { x: lead })) : pwStatus(t("pjw_wartet_dich"), "dran")),
    el("div", { class: "pjw-fehler" + (lead ? " ruhig" : "") }, el("b", {}, t(x.teilweise ? "pjw_delta_teilweise" : "pjw_delta_fehler")), el("ul", {}, x.gruende.slice(0, 8).map(g => el("li", {}, t("pjw_fx_" + g.art, g.x))))));
  if (x.hinweise.length) karte.append(el("div", { class: "pjw-hinweise" }, el("div", { class: "pjw-lbl" }, t("pjw_hinweise")), x.hinweise.map(h => el("div", {}, h.text))));
  if (API) return karte;
  const id = "pjw-hwd-" + x.thema;
  karte.append(pwHinweisFeld(t("pjw_delta_fehler_ph"), id),
    pwHandlungen(pwKnopf(t("pjw_ueberarbeiten"), () => { const h = pwHinweisText(id); if (!h && !x.hinweise.length) { toast(t("pjw_text_fehlt"), true); return; }
      pwTun("/api/projektweg/ueberarbeiten", { plan: `TH${x.thema}`, text: h }, t("pjw_ok_ueberarbeiten")); }, haupt)));
  return karte;
}
/* A2112 (Marcel 25.11.): das Ja zu einer Änderung heißt im Projektweg und in Planung › Meilensteine gleich; ja kommt vom Server (planansicht.aenderung_ja). */
function pwDeltaKnopfText(thema, ja) {
  const ziele = ja.ziele.map(pwZielText).join(", ");
  const wohin = ja.neuer_ms ? t("pjw_delta_neu") : ziele ? t("pjw_delta_in", { m: ziele }) : "";     /* A2080: kurz – der Titel steht in der Karte */
  return t(ja.startet ? "pjw_delta_start_n" : "pjw_delta_ja_n", { t: `TH${thema}`, p: pwPakete(ja.pakete), m: wohin })
    + (ja.aendern ? " · " + t("pjw_n_geaendert", { n: ja.aendern }) : "") + (ja.verwerfen ? " · " + t("pjw_n_verworfen", { n: ja.verwerfen }) : "");
}
const pwDeltaOk = ja => t(ja.startet ? "pjw_ok_delta_start" : "pjw_ok_delta");
/* A2118: ein zurückgestellter Entwurf zeigt den Grund statt des Knopfs; der Mensch darf ihn hinter einem Klick, mit Rückfrage, doch freigeben. */
const pwZurueckgestellt = (w, tun) => el("details", { class: "pjw-wartet" }, el("summary", {}, t("pjw_wartet_grund", { x: w.grund })),
  API ? el("div", { class: "leise" }, t("pm_nur_pc")) : el("button", { class: "klein-knopf", type: "button", "data-h": "trotzdem",
    onclick: () => { if (confirm(t("pjw_wartet_frage", { x: w.grund }))) tun(); } }, t("pjw_trotzdem_frei")));
const pwDeltaOffen = f => f.delta.filter(x => !x.wartet);
function pwDeltaKarte(x, einzig, haupt) {
  /* A2065 (Marcel 24.11.): die Änderung als Karten in Stufen wie der Feinplan; was der Knopf freigibt, steht auf dem Knopf. */
  const karte = el("div", { class: "pjw-karte pjw-delta", "data-thema": x.thema },
    el("div", { class: "pjw-kopf" }, el("h3", {}, t("pjw_delta", { x: `TH${x.thema} ${x.name}` })), x.wartet ? pwStatus(t("pjw_wartet")) : pwStatus(t("pjw_wartet_dich"), "dran")),
    el("div", { class: "pjw-werte" }, el("span", {}, el("b", {}, x.karten.length), " ", t(x.karten.length === 1 ? "pjw_paket_w" : "pjw_pakete_w")),
      el("span", {}, el("b", {}, x.karten.filter(k => k.wer.startsWith("Headless")).length), " Headless"), x.ziele.length ? el("span", {}, t("pjw_in_x", { x: x.ziele.map(z => z.neu ? t("pjw_neuem_ms", { x: z.titel }) : `M${z.nr}`).join(", ") })) : null));
  if (x.karten.length) {
    const stufen = [...new Set(x.karten.map(k => k.stufe))].sort((a, b) => a - b);
    karte.append(el("div", { class: "pjw-stufen" }, stufen.map(s => el("div", { class: "pjw-stufe" }, el("span", { class: "pjw-snr" }, s),
      el("div", { class: "pjw-pakete" }, x.karten.filter(k => k.stufe === s).map(k => el("button", { class: "pjw-paket", type: "button",
        onclick: () => pwOeffne({ art: "dpaket", thema: x.thema, id: k.schluessel }) },
        el("span", { class: "pjw-t" }, k.titel), el("span", { class: "pjw-u" }, el("span", {}, k.wer), el("span", { class: "pjw-rechts" }, k.groesse || "")))))))));
  }
  if (x.aendern.length) karte.append(el("div", { class: "pjw-hinweise" }, el("div", { class: "pjw-lbl" }, t("pjw_geaendert_lbl")),
    x.aendern.map(y => el("div", {}, `A${y.aufgabe} ${y.alt || ""}`, y.titel ? el("span", { class: "leise" }, ` → ${y.titel}`) : null))));
  if (x.verwerfen.length) karte.append(el("div", { class: "pjw-hinweise" }, el("div", { class: "pjw-lbl" }, t("pjw_verworfen_lbl")),
    x.verwerfen.map(y => el("div", {}, `A${y.aufgabe} ${y.alt || ""}`, y.grund ? el("span", { class: "leise" }, ` – ${y.grund}`) : null))));
  if ((x.nacharbeit || []).length) karte.append(el("div", { class: "pjw-hinweise" }, el("div", { class: "pjw-lbl" }, t("pjw_nacharbeit_lbl")),   /* A2059 */
    x.nacharbeit.map(y => el("div", {}, `A${y.aufgabe} ${y.alt || ""}`, y.grund ? el("span", { class: "leise" }, ` – ${y.grund}`) : null))));
  if (x.wer && x.wer.length) karte.append(el("div", { class: "leise" }, t("pjw_delta_wer", { x: x.wer.join(", ") })));   /* A2080 (2) */
  const frei = () => pwTun("/api/meilenstein/plan-ja", { thema: x.thema, eid: x.eid }, pwDeltaOk(x.ja));
  if (x.wartet) { karte.append(pwZurueckgestellt(x.wartet, frei)); return karte; }                     /* A2118 */
  if (API) { karte.append(el("div", { class: "leise pjw-nur-pc" }, t("pm_nur_pc"))); return karte; }
  const ja = pwKnopf(pwDeltaKnopfText(x.thema, x.ja), frei, haupt);
  if (einzig) pwHaupt = ja;
  else karte.append(pwHandlungen(ja));
  return karte;
}
function pwUmsetzung(d) {
  /* A2066 (Marcel 24.11.): die laufenden Meilensteine, der jüngste oben – je Meilenstein Fortschritt, was gerade läuft, Fragen;
     fertige Pakete eingeklappt (vorher ~50 fertige Karten in einer Stufe). */
  const u = d.umsetzung;
  if (!u.meilensteine.length) return [el("div", { class: "leer" }, t("pjw_u_leer"))];
  const teile = [], fragen = pwFragenIn(d, 3);
  teile.push(...fragen.filter(f => !f.bogen || !u.meilensteine.some(m => m.bogen === f.bogen)).map(pwFrage));
  for (const m of [...u.meilensteine].sort((a, b) => b.bogen - a.bogen)) {
    const offen = m.pakete.filter(p => p.status !== "fertig"), fertig = m.pakete.filter(p => p.status === "fertig");
    const jetzt = offen.filter(p => p.status === "laeuft").length;
    const block = el("div", { class: "pjw-ums", "data-bogen": m.bogen },
      el("div", { class: "pjw-kopf" }, el("h3", {}, `${pwM(m)} ${m.titel}`, (d.laufende || []).some(x => x.bogen === m.bogen) ? el("span", { class: "pjw-laufend" }, " · " + t("pjw_laufend")) : null),
        pwStatus(t("pjw_f_von_n", { f: m.fertig, n: m.pakete.length }))),
      el("div", { class: "pjw-balken" }, el("span", { style: `width:${m.pakete.length ? Math.round(m.fertig / m.pakete.length * 100) : 0}%` })),
      offen.length ? el("div", { class: "pjw-werte" }, el("span", {}, el("b", {}, jetzt), " ", pwN("pjw_laeuft_jetzt", jetzt)),
        el("span", {}, el("b", {}, offen.length - jetzt), " ", t("pjw_noch_offen"))) : null,
      ...fragen.filter(f => f.bogen === m.bogen).map(pwFrage),
      offen.length ? pwStufen(offen, true) : null,
      fertig.length ? el("details", { class: "pjw-fertig" }, el("summary", {}, pwN("pjw_fertige_pakete", fertig.length)), pwStufen(fertig, true)) : null);
    teile.push(block);
  }
  teile.push(el("div", { class: "pjw-werte" }, el("a", { href: "#start", onclick: e => { e.preventDefault(); zeige("start"); } }, t("pjw_lagebild"))));
  return teile;
}
/* A2088: Vorbehalte und Gründe {art, n} bzw. {art: "pruefer", text} in Worten – auch für Planung › Meilensteine */
const pwVorbehalt = v => v.art === "pruefer" ? v.text : t("pjw_vb_" + v.art + (v.n === 1 ? "1" : ""), { n: v.n, z: v.zweig || "main" });
const pwTrotzdem = (liste, tun) => () => { if (confirm(t("pjw_trotzdem_frage") + "\n\n" + liste.map(x => "– " + x).join("\n"))) tun(); };
/* A2088 (Lead #32824): was beim Abnehmen dagegen spricht – auf Projektweg und Planung gleich. null: gerade geht es nicht. */
const pwDagegen = (lage, zaehlt, vorbehalte, alt) => ["laeuft", "bericht", "auslieferung"].includes(lage) ? null
  : [...(zaehlt ? [t("pjw_l_" + lage)] : []), ...(alt ? [t("pjw_a_alt_" + alt)] : []), ...(vorbehalte || []).map(pwVorbehalt)];
function pwUrteil(x, name, p, text) {
  /* je Thema ein Wort und ein kurzer Satz; Pakete, Commits und Dateien auf Klick */
  const z = x.zustand || (x.erfuellt ? "erfuellt" : "nicht_erfuellt");
  const satz = z === "nicht_pruefbar" ? (x.gruende || []).map(pwVorbehalt).join(" · ") : z === "erfuellt" ? x.beleg : x.fehlt;
  const pakete = (p.pakete || []).filter(k => x.thema ? k.themen.includes(x.thema) : !k.themen.some(th => p.themen.some(y => y.thema === th)));
  const kopf = [el("b", {}, t("pjw_z_" + z, { x: name })), satz ? " – " + satz : null];
  if (!pakete.length && !text) return el("span", {}, kopf);
  return el("details", { class: "pjw-beleg" }, el("summary", {}, kopf), text ? el("div", { class: "pjw-beleg-paket pjw-zielsatz" }, text) : null, z === "nicht_pruefbar" && (x.beleg || x.fehlt) ? el("div", { class: "pjw-beleg-paket leise" }, t("pjw_pruefer_sagt", { x: x.fehlt || x.beleg })) : null,
    ...pakete.map(k => el("div", { class: "pjw-beleg-paket" }, el("div", {}, k.titel), el("div", { class: "leise" },
      [[...new Set([...k.commits.slice(0, 3), ...(k.sha ? [k.sha] : [])])].join(", ") + (k.commits.length > 3 ? " …" : ""), k.grund ? t("pjw_bg_" + k.grund, { z: p.stand?.zweig || "main" }) : k.befund === "urteil" ? t("pjw_bg_urteil") : null, k.dateien.length ? k.dateien.join(", ") + (k.mehr ? " …" : "") : null].filter(Boolean).join(" · ")))));
}
function pwAbschlussKarte(x, einzig, haupt) {
  /* A2082 (B2938): x.lage kommt vom Server (abschlusslage.lage). Dran ist der Mensch nur, wenn x.bei_dir – sonst steht neutral da,
     was fehlt und dass der Lead es klärt; die Knöpfe bleiben, als normale Knöpfe. */
  /* A2064: Abnehmen nur mit Prüfliste – Gesamttest ✓ (oder keiner eingestellt), jedes Thema erfüllt, Prüfer ohne Fehler,
     Abschlussbericht da. Sonst steht da, was noch fehlt; Nacharbeit geht immer. */
  const p = x.pruefung, test = (p && p.test) || {};
  const zeile = (ok, text) => el("div", {}, el("span", { class: ok === null ? "leise" : ok ? "pjw-ok" : x.bei_dir ? "pjw-nein" : "leise" }, ok === null ? "–" : ok ? "✓" : "○"), el("span", {}, text));   /* A2082: Farbe nur, wenn der Mensch dran ist (TH156 Regel 4) */
  const testOk = !!p && (!test.befehl || test.rc === 0), abnehmbar = x.lage === "abnehmbar";
  const karte = el("div", { class: "pjw-karte pjw-ab-karte", "data-bogen": x.bogen, "data-lage": x.lage },
    el("div", { class: "pjw-kopf" }, el("h3", {}, `${pwM(x)} ${x.titel}`), x.bei_dir ? pwStatus(t("pjw_wartet_dich"), "dran") : pwStatus(pwLage(x), "umbruch")));
  const ja = x.bei_dir ? zeile(false, t("pjw_dein_ja")) : null;
  if (!p) karte.append(el("div", { class: "pjw-pruefung" }, zeile(false, x.pruefung_laeuft ? t("pjw_a_laeuft") : t("pjw_a_ohne")), ja));
  else {
    karte.append(el("div", { class: "pjw-pruefung" },
      p.vorbehalte.some(v => v.art === "kein_gesamttest") ? null : zeile(test.befehl ? testOk : null, !test.befehl ? t("pjw_test_kein") : test.rc === 0 ? pwN("pjw_test_gruen", x.pakete, { l: test.lauf }) : t("pjw_test_rot", { l: test.lauf })),
      ...p.themen.map(th => zeile(th.erfuellt, pwUrteil(th, th.thema, p))),
      p.ziel ? zeile(p.ziel.erfuellt, pwUrteil(p.ziel, t(p.zielsatz?.[0] === "ziel" ? "pjw_ziel" : "pjw_ziel_fertig"), p, p.zielsatz?.[1])) : null,   /* A2098: „fertig, wenn“ wie ein Thema, sein Text auf Klick */
      p.fehler ? zeile(false, t("pjw_a_pruefer_fehler_z", { x: p.gruende.map(g => t("pjw_ax_" + g.art, g.x)).join(" · ") })) : null, ja));
    if (p.vorfuehrung.length) karte.append(el("div", { class: "pjw-wie" }, el("span", { class: "pjw-lbl" }, t("pjw_vorfuehrung")), el("ol", {}, p.vorfuehrung.map(s => el("li", {}, s)))));
  }
  if (x.bericht) karte.append(el("div", { class: "pjw-werte" }, el("a", { href: "#", onclick: e => { e.preventDefault(); dokumentDialog(x.bericht); } }, t("pjw_bericht"))));
  /* A2088: Vorbehalte über dem Knopf; gibt es welche, heißt er „Trotz Vorbehalt abnehmen“ und fragt nach. Verboten wird es nicht. */
  const vorbehalte = p ? p.vorbehalte.map(pwVorbehalt) : [], unpruefbar = x.lage === "nicht_pruefbar";
  if (p && p.alt) karte.append(el("div", { class: "leise pjw-a-alt" }, t("pjw_a_alt_" + p.alt)));
  if (vorbehalte.length) karte.append(el("div", { class: "pjw-vorbehalte" + (x.bei_dir ? "" : " ruhig") }, el("div", { class: "pjw-lbl" }, t("pjw_vorbehalte")), el("ul", {}, vorbehalte.map(v => el("li", {}, v)))));
  if (API) return karte;
  const abnehmen = () => pwTun("/api/meilenstein/freigeben", { bogen: x.bogen, art: "abschluss" }, t("pjw_ok_abgenommen"));
  const fragen = pwDagegen(x.lage, x.lage_zaehlt, p?.vorbehalte, p?.alt) || [];
  /* Die Handlung dieser Karte: abnehmen (Prüfliste vollständig) – oder die Prüfung nachholen (A2064, TL #32217: Meilensteine,
     die vor A2029 bereit wurden, bekommen sie nie von selbst). Hauptknopf nur auf der ersten Karte (eine Hauptaktion je Ansicht). */
  const handlung = abnehmbar && !fragen.length ? pwKnopf(t("pjw_abnehmen_m", { m: pwM(x) }), abnehmen, haupt)
    : abnehmbar ? pwKnopf(t("pjw_trotzdem"), pwTrotzdem(fragen, abnehmen), haupt && x.bei_dir)
    : (!p || p.fehler) && !x.pruefung_laeuft && x.lage !== "auslieferung" ? pwKnopf(t(p ? "pjw_a_erneut" : "pjw_a_starten"),       // A2072: nach einem Fehler erneut
        () => pwTun("/api/projektweg/pruefung-starten", { bogen: x.bogen }, t("pjw_ok_pruefung")), haupt && x.bei_dir) : null;
  if (!abnehmbar) karte.append(el("div", { class: "leise pjw-a-lage" }, !x.bei_dir ? pwLageLang(x)
    : !p ? (x.pruefung_laeuft ? t("pjw_a_laeuft_lang") : t("pjw_a_ohne_lang"))
    : p.fehler ? t("pjw_a_pruefer_fehler") : x.lage === "nicht_erfuellt" ? t("pjw_a_nicht_erfuellt") : unpruefbar ? t("pjw_ll_nicht_pruefbar_du") : t("pjw_bericht_kommt")));
  const trotzdem = !abnehmbar && x.lage_zaehlt && fragen.length && x.bericht ? pwKnopf(t("pjw_trotzdem"), pwTrotzdem(fragen, abnehmen)) : null;   /* verboten ist es nicht */
  einzig = einzig && x.bei_dir && !(abnehmbar && (fragen.length || !test.befehl));   /* A2088: Vorbehalt und „kein Gesamttest“ stehen über dem Knopf */                                       /* oben steht nur, was der Mensch tun soll */
  if (handlung && einzig) pwHaupt = handlung;
  const id = "pjw-hw-" + x.bogen;
  karte.append(pwHinweisFeld(t("pjw_nacharbeit_ph"), id),
    pwHandlungen(handlung && !einzig ? handlung : null, pwKnopf(t("pjw_nacharbeit"), () => { const h = pwHinweisText(id); if (!h) { toast(t("pjw_text_fehlt"), true); return; }
      pwTun("/api/meilenstein/nacharbeit", { bogen: x.bogen, hinweis: h }, t("pjw_ok_nacharbeit")); }), trotzdem));
  return karte;
}
function pwAbschluss(d) {
  /* A2064 (Marcel 24.11.): alle Meilensteine, die auf die Abnahme warten, als Liste – nicht nur einer. */
  const a = d.abschluss;
  const warten = a.filter(x => x.bereit && !x.frei).sort((x, y) => (y.bei_dir - x.bei_dir) || (y.bogen - x.bogen));   /* A2082: zuerst, was der Mensch tun kann */
  const laufend = (d.laufende || []).filter(x => x.ruht).map(x => el("div", { class: "leise pjw-a-laufend", "data-bogen": x.bogen }, t("pjw_a_laufend_z", { m: pwM(x), x: x.titel })));
  if (!warten.length) {
    const z = a.filter(x => x.frei).at(-1);
    if (z) return [el("div", { class: "leise pjw-a-zuletzt" }, t("pjw_a_keiner_z", { m: pwM(z), x: z.titel })), ...laufend];   /* Inhalt, nicht „leer“: sonst zeigte der offene Schritt nur „So läuft …“ */
    return laufend.length ? laufend : [el("div", { class: "leer" }, a.length ? t("pjw_a_keiner") : t("pjw_a_leer"))];
  }
  const dran = warten.filter(x => x.bei_dir).length;
  return [dran > 1 ? el("div", { class: "leise" }, t("pjw_a_warten_n", { n: dran })) : !dran ? el("div", { class: "leise" }, t("pjw_a_keiner")) : null,
    ...warten.map((x, i) => pwAbschlussKarte(x, warten.length === 1, i === 0)), ...laufend].filter(Boolean);
}
function pwAuftragMehr(p) {
  /* A2075: der Anfang steht da, „mehr“ holt den ganzen Auftrag (wie der Aufgaben-Dialog, auch online für offene Pakete). */
  const text = el("span", { class: "pjw-auftrag" }, p.auftrag + " … ");
  text.append(el("button", { class: "klein-knopf pjw-mehr", type: "button", onclick: async () => {
    try { const a = await holen(`/api/aufgabe?id=${p.id}`); text.replaceChildren(a.auftrag ?? a.aufgabe?.auftrag ?? p.auftrag); }
    catch (e) { toast(t("fehler", { x: e.message }), true); } } }, t("pjw_mehr")));
  return text;
}
function pwOeffne(was) { zustand.pwFenster = was; pwFensterZeichnen(); }
function pwFensterZeichnen() {
  document.getElementById("pjw-fenster")?.remove();
  const w = zustand.pwFenster, d = zustand.pwDaten; if (!w || !d || zustand.sicht !== "projektweg") return;
  let titel = "", felder = [], hinweis = null;
  const grobOffen = !API && d.grob.fassungen.length && !d.grob.angenommen && !d.grob.laeuft;
  if (w.art === "thema") {
    const x = d.konzept.themen.find(y => y.id === w.id) || { id: w.id, name: "" };
    const f = d.grob.fassungen.find(y => y.fassung === (zustand.pwFassung ?? d.grob.angenommen?.fassung)) || d.grob.fassungen.at(-1);
    titel = `TH${x.id} ${x.name}`;
    felder = [[t("pjw_status"), x.status ? t("th2_" + x.status) : "–"], [t("pjw_meilensteine"), f ? f.meilensteine.filter(m => (m.themen || []).includes(x.id)).map(m => `${m.schluessel} ${m.titel}`).join(" · ") || "–" : "–"]];
    if (grobOffen) hinweis = { plan: "grob", zu: `TH${x.id}` };
  } else if (w.art === "ms") {
    const f = d.grob.fassungen.find(y => y.fassung === w.fassung) || d.grob.fassungen.at(-1), m = f.meilensteine.find(y => y.schluessel === w.id);
    if (!m) return;
    titel = `${m.schluessel} ${m.titel}`;
    felder = [[t("pjw_ziel"), m.ziel || "–"], [t("pjw_fertig_wenn_k"), m.fertig_wenn || "–"], [t("pjw_themen"), (m.themen || []).map(n => `TH${n} ${pwThemaName(d, n)}`).join(" · ") || "–"],
      [t("pjw_reihenfolge"), [(m.nach || []).length ? t("pjw_nach", { x: m.nach.join(", ") }) : t("pjw_ohne_vorgaenger"), (m.gleichzeitig || []).length ? t("pjw_gleichzeitig", { x: m.gleichzeitig.join(", ") }) : null].filter(Boolean).join(" · ")],
      [t("pjw_aufwand"), [m.aufwand, m.tage ? (m.tage === 1 ? t("pjw_tag1") : t("pjw_tage", { n: m.tage })) : null].filter(Boolean).join(" · ") || "–"],
      [t("pjw_kosten"), typeof m.usd === "number" ? `≈ ${m.usd.toFixed(2)} $` : "–"]];
    if (grobOffen && w.fassung === d.grob.fassungen.at(-1).fassung) hinweis = { plan: "grob", zu: m.schluessel };
  } else if (w.art === "paket") {
    const ms = d.fein.meilensteine.find(y => y.pakete.some(p => p.id === w.id)), p = ms?.pakete.find(y => y.id === w.id);
    if (!p) return;
    const titelVon = id => { const q = ms.pakete.find(y => y.id === id); return q ? q.titel : `A${id}`; };
    titel = p.titel;
    felder = [[t("pjw_status"), t("pjw_p_" + (["laeuft", "fertig", "blockiert", "wartet"].includes(p.status) ? p.status : "offen"))], [t("pjw_wer"), p.wer],
      [t("pjw_modell"), [p.modell, p.effort].filter(Boolean).join(" · ") || "–"], [t("pjw_groesse"), p.groesse || "–"], [t("pjw_dateien"), p.dateibereich || "–"],
      [t("pjw_abnahme"), p.pruefbefehl || "–"], [t("pjw_nach_k"), p.nach.length ? p.nach.map(titelVon).join(" · ") : "–"], [t("pjw_auftrag"), p.auftrag_mehr ? pwAuftragMehr(p) : p.auftrag || "–"]];
    if (!API && !ms.frei && !ms.laeuft) hinweis = { bogen: ms.bogen, zu: `A${p.id}` };
  }
  else if (w.art === "lauf") {                                           /* A2078: Modell, Dauer, Kosten nur hier */
    const l = d.laeufe.find(y => y.lauf === w.id); if (!l) return;
    const min = s => `${Math.max(0, Math.round((s || 0) / 60))} min`;
    titel = pwLaufTitel(l);
    felder = [[t("pjw_wer"), pwLaufWer(l) || "–"], [t("pjw_lauf_was"), l.was || "–"], [t("pjw_modell"), l.modell || "–"],
      [t("pjw_lauf_dauer"), l.dauer_s ? `${min(l.seit_s)} / ≈ ${min(l.dauer_s)}` : min(l.seit_s)], [t("pjw_kosten"), typeof l.usd === "number" ? `${l.usd.toFixed(2)} $` : "–"]];
  }
  else if (w.art === "dpaket") {                                         /* A2065: Paket eines Entwurfs – das Technische nur hier */
    const x = d.fein.delta.find(y => y.thema === w.thema), k = x?.karten.find(y => y.schluessel === w.id);
    if (!k) return;
    titel = k.titel;
    felder = [[t("pjw_wer"), k.wer], [t("pjw_groesse"), k.groesse || "–"], [t("pjw_ziel_ms"), pwZielText(k.ziel)],
      [t("pjw_nach_k"), k.nach.length ? k.nach.join(", ") : "–"], [t("pjw_auftrag"), k.auftrag || "–"], [t("pjw_abnahme"), k.abnahme || "–"],
      [t("pjw_dateien"), k.bereiche || "–"], [t("pjw_warum_fenster"), k.grund || "–"]];
  }
  const zu = () => { zustand.pwFenster = null; document.getElementById("pjw-fenster")?.remove(); };
  const teile = [el("div", { class: "pjw-kopf" }, el("h3", {}, titel), el("button", { class: "knopf still pjw-zu", type: "button", onclick: zu, "aria-label": t("pjw_schliessen") }, "✕")),
    el("div", { class: "pjw-felder" }, felder.flatMap(([k, v]) => [el("span", {}, k), el("span", {}, v)]))];
  if (w.art === "thema") teile.push(el("a", { href: "#themen", onclick: e => { e.preventDefault(); zustand.themaOffen = w.id; zu(); zeige("themen"); } }, t("pjw_thema_oeffnen")));
  if (hinweis) {
    teile.push(el("div", {}, el("label", { class: "pjw-lbl", for: "pjw-erg" }, t("pjw_ergaenzen")), el("textarea", { id: "pjw-erg", class: "pjw-hinweis", placeholder: t("pjw_ergaenzen_ph") })));
    teile.push(pwHandlungen(hinweis.bogen
      ? pwKnopf(t("pjw_mit_hinweis"), () => { const x = pwHinweisText("pjw-erg"); if (!x) return; pwTun("/api/meilenstein/fein-neu", { bogen: hinweis.bogen, hinweis: `${hinweis.zu}: ${x}` }, t("pjw_ok_ueberarbeiten")); }, true)
      : pwKnopf(t("pjw_als_hinweis"), () => { const x = pwHinweisText("pjw-erg"); if (!x) return; pwTun("/api/projektweg/hinweis", { plan: hinweis.plan, zu: hinweis.zu, text: x }, t("pjw_ok_hinweis")); }, true)));
  }
  $("#inhalt").append(el("div", { id: "pjw-fenster" }, el("div", { class: "pjw-schleier", onclick: zu }), el("div", { class: "pjw-fenster", role: "dialog" }, ...teile)));
}
/* A2078: was läuft, in Worten; wer es ausgelöst hat, mit Rolle. Modell, Dauer und Kosten nur im Seitenfenster. */
const pwLaufTitel = l => t("pjw_lt_" + (["gegenlesen", "grobplaner", "feinplaner", "planer", "abschluss"].includes(l.art) ? l.art : "sonst"),
  { th: l.thema ? `TH${l.thema}` : "", f: l.fassung ?? "", z: l.ziel || "" }).trim();
const pwLaufWer = l => l.rolle === "mensch" ? t("du") : l.rolle === "amw" ? "AMW" : l.rolle === "lead" || l.rolle === "co" ? `${l.ausloeser} (${t("pjw_rolle_" + l.rolle)})` : l.ausloeser || "";
function pwLaufZeilen(d, schritt) {
  return d.laeufe.filter(l => l.schritt === schritt).map(l => el("button", { class: "pjw-laeuft", type: "button", onclick: () => pwOeffne({ art: "lauf", id: l.lauf }) },
    el("span", { class: "pjw-puls" }), t("pjw_laeuft_gerade", { x: pwLaufTitel(l) }), pwLaufWer(l) ? el("span", { class: "leise" }, " · " + pwLaufWer(l)) : null));
}
function pwUeberZeichnen(d) {
  document.getElementById("pjw-ueber")?.remove();
  const l = d.laeufe.find(x => x.mein && x.lauf !== zustand.pwLaufZu); if (!l) return;
  const anteil = l.gesamt ? Math.min(1, (l.nr || 0) / l.gesamt) : null, min = s => Math.max(0, Math.round((s || 0) / 60));
  $("#inhalt").append(el("div", { id: "pjw-ueber" }, el("div", { class: "pjw-schleier" }), el("div", { class: "pjw-lauf pjw-lauf-ueber", role: "status" },
    el("div", { class: "pjw-was" }, el("span", { class: "pjw-puls" }), pwLaufTitel(l)),
    l.was ? el("div", {}, l.was) : null,
    anteil !== null ? el("div", { class: "pjw-balken" }, el("span", { style: `width:${Math.round(anteil * 100)}%` })) : null,
    el("div", { class: "pjw-werte" }, pwLaufWer(l) ? el("span", {}, el("b", {}, pwLaufWer(l))) : null,
      el("span", {}, el("b", {}, l.dauer_s ? `${min(l.seit_s)} / ≈ ${min(l.dauer_s)} min` : `${min(l.seit_s)} min`)),
      typeof l.usd === "number" ? el("span", {}, el("b", {}, `${l.usd.toFixed(2)} $`)) : null),
    el("div", { class: "pjw-handlungen" }, pwKnopf(t("pjw_l_hintergrund"), () => { zustand.pwLaufZu = l.lauf; document.getElementById("pjw-ueber")?.remove(); })))));
}
function pwNachsehen(d) {
  clearTimeout(pwTakt);                                   /* solange ein Planer läuft: alle 3 s nachsehen (Fortschritt, Ende) */
  if (d.laeufe.length) pwTakt = setTimeout(() => { if (zustand.sicht === "projektweg") frischZeichnen(); }, 3000);
}
async function sichtProjektweg() {
  /* A2060 (Marcel 24.11.: alle ~10 s war rechts alles weg): erst laden, dann vergleichen. Gleiche Daten und gleiche Auswahl –
     nichts neu zeichnen, Scroll und Seitenfenster bleiben. Vorher leerte rahmen() die Seite sofort, und der Abruf (1–3 s) ließ
     sie so lange leer; der Takt zeichnete bei jeder Änderung irgendwo im Projekt (Aufgaben, Ereignisse) neu. */
  let d; try { d = await holen("/api/projektweg"); } catch (e) { rahmen(t("n_projektweg")).append(el("div", { class: "leer" }, String(e.message || e))); return; }
  const stand = JSON.stringify([d, zustand.pwSicht, zustand.pwOffen, zustand.pwMs, zustand.pwFassung, zustand.pwWie, zustand.pwLaufZu, zustand.pwVerlaufAlle, sprache]);
  if (stand === pwStand && document.querySelector("#inhalt .pjw-seite")) { pwNachsehen(d); return; }
  pwStand = stand;
  const m = rahmen(t("n_projektweg"));
  zustand.pwDaten = d;
  const dranNr = pwDranNr(d), v = zustand.pwSicht ?? dranNr;
  const schritte = el("div", { class: "pjw-schritte" }, d.schritte.map((s, i) => {
    const z = s.zustand === "erledigt" ? "ok" : s.zustand === "dran" ? "jetzt" : "offen";
    return el("button", { class: `pjw-schritt ${z}-z${v === i ? " gewaehlt" : ""}`, type: "button", "data-schritt": s.schritt,
      onclick: () => { zustand.pwSicht = i; zustand.pwOffen = true; zeige("projektweg", true); } },
      el("span", { class: "pjw-name" }, el("span", { class: "pjw-zeichen" }, s.zeichen), `${i + 1} · ${t("pjw_s_" + s.schritt)}`),
      el("span", { class: "pjw-wert" + (s.bei_dir ? " dran" : "") }, pwWert(d, i) + (s.bei_dir ? " · " + t("pjw_wartet_dich") : ""))); }));
  pwHaupt = null;
  const inhalt = [pwKonzept, pwGrob, pwFein, pwUmsetzung, pwAbschluss][v](d).filter(Boolean);
  const nochNicht = d.schritte[v].zustand === "offen" && !inhalt.some(x => !x.classList?.contains("leer"));
  const wie = el("div", { class: "pjw-wie" }, el("span", { class: "pjw-lbl" }, t("pjw_wie")), el("ol", {}, t("pjw_wie_" + v).split("|").map(x => el("li", {}, x))));
  const ansicht = el("div", { class: "pjw-ansicht" },
    el("div", { class: "pjw-kopf" }, el("button", { class: "knopf still pjw-zurueck", type: "button", onclick: () => { zustand.pwOffen = false; zeige("projektweg", true); } }, t("pjw_zurueck")),
      el("h2", {}, `${v + 1} · ${t("pjw_s_" + PW_SCHRITTE[v])}`), pwHaupt,
      nochNicht ? pwStatus(t("pjw_noch_nicht")) : el("button", { class: "knopf still", type: "button", onclick: () => { zustand.pwWie = zustand.pwWie === v ? null : v; zeige("projektweg", true); } }, t("pjw_wie"))),
    ...pwLaufZeilen(d, PW_SCHRITTE[v]),
    nochNicht || zustand.pwWie === v ? wie : null,
    ...(nochNicht ? [] : inhalt.length ? inhalt : [el("div", { class: "leer" }, t("pjw_nichts"))]));
  const heute = new Date().toDateString();
  const wann = z => { const x = new Date(z); return x.toLocaleString(gebiet(), x.toDateString() === heute ? { hour: "2-digit", minute: "2-digit" } : { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" }); };
  /* A2063 (Marcel 24.11.): der Verlauf gehört zum gewählten Schritt – oben umschaltbar auf „alle Schritte“; je Eintrag eine Zeile,
     Langes auf Klick. */
  const wer = e => el("span", { class: "pjw-wer" + (e.rolle === "mensch" ? " du" : "") }, e.rolle === "agent" ? e.von : t("pjw_r_" + e.rolle));
  const eintrag = e => el("div", { class: "pjw-eintrag" }, el("span", { class: "pjw-z" }, wann(e.zeit)),
    e.lang ? el("details", { class: "pjw-lang" }, el("summary", {}, wer(e), " ", e.zeile), el("div", { class: "leise" }, e.lang))
      : el("span", {}, wer(e), " ", e.zeile || e.text));
  const alle = !!zustand.pwVerlaufAlle;
  const eintraege = d.verlauf.filter(e => alle || e.schritt === PW_SCHRITTE[v]).slice(-120).reverse();
  const umschalter = el("button", { class: "pjw-chip", type: "button", onclick: () => { zustand.pwVerlaufAlle = !alle; zeige("projektweg", true); } },
    alle ? t("pjw_v_schritt") : t("pjw_v_alle"));
  const verlauf = el("aside", { class: "pjw-verlauf" }, el("div", { class: "pjw-kopf" }, el("span", { class: "pjw-lbl", style: "flex:1" }, t("pjw_verlauf")), umschalter),
    eintraege.length ? eintraege.map(eintrag) : el("div", { class: "sehrleise" }, alle ? "–" : t("pjw_v_leer")));
  const verlaufHandy = el("details", { class: "pjw-verlauf-handy" }, el("summary", {}, t("pjw_verlauf_n", { n: eintraege.length })), el("div", { class: "pjw-liste" }, eintraege.map(eintrag)));
  m.append(el("div", { class: "pjw-seite" + (zustand.pwOffen ? " offen" : "") }, schritte, el("div", { class: "pjw-weg" }, ansicht, verlauf), verlaufHandy));   /* A2091: am Handy auch unter dem geöffneten Schritt */
  pwUeberZeichnen(d);
  pwFensterZeichnen();
  pwNachsehen(d);
}
document.addEventListener("keydown", e => { if (e.key === "Escape" && zustand.pwFenster && zustand.sicht === "projektweg") { zustand.pwFenster = null; document.getElementById("pjw-fenster")?.remove(); } });
async function sichtWissen() {
  const m = rahmen(t("wissen"));
  const such = el("input", { placeholder: t("wissen_ph"), value: zustand.wissenQ, style: "width:300px;max-width:100%",
    onkeydown: e => { if (e.key === "Enter") { zustand.wissenQ = e.target.value; sichtWissen(); } } });
  let d; try { d = await holen("/api/wissen?q=" + encodeURIComponent(zustand.wissenQ)); } catch (e) { m.append(el("div", { class: "leer" }, String(e))); return; }
  const r = zustand.wissenReiter;
  if (r === "themen") {                                      /* Design-Dokument je Thema */
    let th; try { th = await holen("/api/themen"); } catch (e) { th = []; }
    m.append(el("div", { class: "reiter" }, [["themen", th.length], ["beschluesse", d.anzahl?.beschluesse ?? d.beschluesse.length], ["regeln", d.regeln.length],
      ["wortlaut", d.anzahl?.wortlaut ?? d.wortlaut.length], ["notizen", (d.notizen || []).length]]
      .map(([k, n]) => el("button", { class: k === r ? "an" : "", type: "button", onclick: () => { zustand.wissenReiter = k; sichtWissen(); } }, t(k, { n }))),
      ...wissenExtern(),
      el("div", { class: "rechts" }, such)));
    return m.append(themenAnsicht(th, zustand.wissenQ));
  }
  const anzahl = { beschluesse: d.anzahl?.beschluesse ?? d.beschluesse.length, wortlaut: d.anzahl?.wortlaut ?? d.wortlaut.length };
  m.append(el("div", { class: "reiter" }, [["themen", d.anzahl?.themen ?? "…"], ["beschluesse", anzahl.beschluesse], ["regeln", d.regeln.length],
    ["wortlaut", anzahl.wortlaut], ["notizen", (d.notizen || []).length]]
    .map(([k, n]) => el("button", { class: k === r ? "an" : "", type: "button", onclick: () => { zustand.wissenReiter = k; sichtWissen(); } }, t(k, { n }))),
    ...wissenExtern(),
    el("div", { class: "rechts" }, such)));
  const box = el("div", { class: "zeile-reveal" });
  const gezeigt = { beschluesse: d.beschluesse.length, wortlaut: d.wortlaut.length }[r];
  if (gezeigt && anzahl[r] > gezeigt) m.append(el("p", { class: "sehrleise", style: "font-size:13px;margin:-4px 0 10px" }, t("w_neueste", { n: gezeigt, g: anzahl[r] })));
  if (r === "beschluesse") box.append(...d.beschluesse.map(b => el("div", { class: "karte wissen-eintrag" },
    el("div", { class: "kopfzeile" }, el("span", { class: "ref" }, `B${b.id}`), el("b", {}, b.stichwort),
      el("span", { class: "etikett " + (b.status === "gilt" ? "gruen" : b.status === "unklar" ? "bernstein" : "") }, b.status),
      el("span", { class: "sehrleise" }, `${zeit(b.zeit_utc)} · ${b.quelle}`), postKnopf(`B${b.id}`, `B${b.id} ${b.stichwort}`)), el("div", { class: "inhalt" }, b.regel))));
  if (r === "regeln") {
    /* Regeln aus dem Grund-Regelwerk stehen als eigene Gruppe oben: Nummer der Vorlage, „angepasst“, wenn der Wortlaut
       geändert wurde, darunter das Warum bzw. die belegte Erfahrung. Sie bleiben gewöhnliche Arbeitsregeln des Projekts. */
    const karte = x => { const g = x.grund ? (x.grund[sprache] || x.grund.de) : null;
      return el("div", { class: "karte wissen-eintrag" + (g ? " grundregel" : "") },
        el("div", { class: "kopfzeile" }, el("span", { class: "ref" }, (x.ebene === "arbeit" ? "KR" : "PR") + x.nr),
          g ? el("span", { class: "etikett gr-marke", title: t("gr_marke_h", { n: g.fassung }) }, g.nr) : null,
          el("span", { class: "etikett" }, g ? g.gruppe : x.ebene === "arbeit" ? t("arbeitsregel") : t("projektregel") + (x.teil ? " · " + x.teil : "")),
          g?.angepasst ? el("span", { class: "etikett bernstein", title: t("gr_angepasst_h") }, t("gr_angepasst")) : null,
          el("span", { class: "sehrleise" }, t("stand", { t: zeit(x.stand_utc) }))),
        el("div", { class: "inhalt" }, x.text),
        g ? el("div", { class: "gr-warum" }, el("b", {}, t(g.erfahrung ? "gr_erfahrung" : "gr_warum") + " "), g.erfahrung || g.warum) : null); };
    const grund = d.regeln.filter(x => x.grund), eigene = d.regeln.filter(x => !x.grund);
    if (grund.length) box.append(el("h4", { class: "gr-titel" }, t("gr_gruppe", { n: grund.length }), hilfeKnopf("regelwerk")), ...grund.map(karte));
    if (grund.length && eigene.length) box.append(el("h4", { class: "gr-titel" }, t("gr_eigene", { n: eigene.length })));
    box.append(...eigene.map(karte));
    const gw = d.grundregeln;                         /* Abgleich mit dem Grund-Regelwerk (nur Vorschlag; übernehmen einzeln) */
    if (gw && (gw.zahl.fehlt || gw.zahl.aehnlich || gw.zahl.neue_fassung)) {
      const zeile = x => el("div", { class: "gr-abgleich-zeile " + x.status },
        el("span", { class: "gr-zeichen", title: t("gra_" + (x.status === "neue_fassung" ? "neu_uebernehmen" : x.status)), style: `color:var(${{ drin: "--gruen", aehnlich: "--leise", fehlt: "--bernstein", neue_fassung: "--bernstein" }[x.status]})` },
          { drin: "✓", aehnlich: "≈", fehlt: "–", neue_fassung: "↻" }[x.status]),
        el("span", { class: "etikett gr-nr" }, x.nr), el("span", { class: "gr-titel-text", title: x.text[sprache] || x.text.de }, x.titel[sprache] || x.titel.de),
        x.status === "aehnlich" ? el("span", { class: "sehrleise", title: x.gemeinsam.join(", ") }, t("gra_wie", { r: x.ref }))
          : x.status === "neue_fassung" ? el("span", { class: "bernstein-text" }, t("gra_neue_fassung", { r: x.ref, f: x.fassung })) : x.ref ? el("span", { class: "sehrleise" }, x.ref) : null,
        x.status !== "drin" ? el("button", { class: "klein-knopf", type: "button", style: "margin-left:auto", title: x.text[sprache] || x.text.de,
          onclick: async ev => { if (!confirm(t("gra_frage", { x: `${x.nr} ${x.titel[sprache] || x.titel.de}` }))) return;
            try { const r = await schicken("/api/regelwerk/uebernehmen", { nr: x.nr }); if (!r.unterwegs) toast(t("gra_ok", { x: x.nr, r: r.regel })); zeige("wissen", true); }
            catch (e) { toast(t("fehler", { x: e.message }), true); } } }, t(x.status === "neue_fassung" ? "gra_neu_uebernehmen" : "gra_uebernehmen")) : null);
      box.append(el("details", { class: "gr-abgleich" }, el("summary", {}, el("b", {}, t("gra_titel", { v: gw.vorlage })), " ",
          el("span", { class: "sehrleise" }, t("gra_zahl", { f: gw.zahl.fehlt, a: gw.zahl.aehnlich, d: gw.zahl.drin }))),
        el("p", { class: "sehrleise", style: "margin:6px 0" }, t("gra_h")), ...gw.regeln.map(zeile)));
    }
  }
  if (r === "wortlaut") box.append(...d.wortlaut.map(w => el("div", { class: "karte wissen-eintrag" },
    el("div", { class: "kopfzeile" }, el("span", { class: "ref" }, `W${w.id}`), el("span", { class: "sehrleise" }, `${zeit(w.zeit_utc)} · ${w.kanal}`)),
    el("div", { class: "inhalt", style: "color:var(--tinte)" }, w.text))));
  if (r === "notizen") box.append(...(d.notizen || []).map(n => el("div", { class: "karte wissen-eintrag" },
    el("div", { class: "kopfzeile" }, el("b", { class: "mono" }, n.schluessel), el("span", { class: "sehrleise" }, t("stand", { t: zeit(n.geaendert_utc) }))),
    el("div", { class: "inhalt", style: "white-space:pre-wrap" }, n.wert))));
  if (!box.children.length) box.append(el("div", { class: "leer" }, t("nichts_gefunden")));
  m.append(box);
}


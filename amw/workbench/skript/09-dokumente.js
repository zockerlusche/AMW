/* --- Dokumente ----------------------------------------------------------------------------- */
const dokUrl = (id, v) => ziel(`/api/dokument/datei?id=${id}${v ? "&v=" + v : ""}`);
const nurAmPc = d => API && d.vorschau !== "text" && !d.online;      // online: Datei nicht auf dem Webspace
const DK_FORMATE = ["bild", "video", "text", "mockup", "pdf", "download"];
function dokSymbol(d) {
  const symbol = () => el("span", { class: "dk-symbol" }, d.vorschau === "mockup" ? "Mockup" : d.vorschau === "pdf" ? "PDF" : d.format === "markdown" ? "Text" : d.format === "bild" ? t("dk_bild") : d.format,
    el("small", {}, nurAmPc(d) ? `${d.endung} · ${t("dk_online_aus")}` : d.endung));
  if (d.vorschau === "video" && !nurAmPc(d))                 /* erstes Bild als Vorschau, lädt nur die Kopfdaten */
    return el("video", { src: dokUrl(d.id, d.version) + "#t=0.1", muted: true, preload: "metadata", playsinline: true, onerror: e => e.target.replaceWith(symbol()) });
  return d.vorschau === "bild" && !nurAmPc(d) ? el("img", { src: dokUrl(d.id, d.version), alt: "", loading: "lazy", onerror: e => e.target.replaceWith(symbol()) }) : symbol();
}
async function sichtDokumente() {
  const f = zustand.dok ||= { art: "", von: "", bezug: "", q: "", status: "aktuell", liste: false };
  const qs = new URLSearchParams({ status: f.status });
  if (f.art) qs.set("art", f.art); if (f.von) qs.set("von", f.von); if (f.q) qs.set("q", f.q);
  if (f.bezug) { const [ba, bi] = f.bezug.split(":"); qs.set("bezug_art", ba); qs.set("bezug_id", bi); }
  const m = rahmen(t("wissen"), el("button", { class: "knopf haupt kopf-aktion", type: "button", onclick: () => dokHochladen({ bezug: f.bezug }) }, t("dk_hochladen")));
  m.append(wissenReiter("dokumente"));
  let d; try { d = await holen("/api/dokumente?" + qs); } catch (e) { m.append(el("div", { class: "leer" }, String(e))); return; }
  const neu = (k, v) => { f[k] = v; sichtDokumente(); };
  const auswahl = (k, leer, paare) => el("select", { onchange: e => neu(k, e.target.value) }, el("option", { value: "" }, leer),
    paare.map(([v, text]) => el("option", { value: v, ...(String(f[k]) === String(v) ? { selected: true } : {}) }, text)));
  const such = el("input", { type: "search", placeholder: t("dk_such_ph"), value: f.q, onkeydown: e => { if (e.key === "Enter") neu("q", e.target.value.trim()); } });
  const bezugListe = d.boegen.map(b => [`bogen:${b.id}`, `${bogenRef(b.id)} · ${b.titel}`]);
  if (f.bezug && !f.bezug.startsWith("bogen:")) bezugListe.unshift([f.bezug, f.bezug.replace("aufgabe:", "A").replace("frage:", "F").replace("beschluss:", "B")]);
  /* Art als Chips (wie die Arten im Verlauf), Zahl = aktuelle Dokumente; Zeitraum und Reihenfolge wirken hier in der Seite */
  const arten = Object.entries(d.arten).sort((a, b) => b[1] - a[1]);
  if (f.art && !d.arten[f.art]) arten.push([f.art, 0]);
  const chip = (wert, text) => el("button", { class: "vl-chip" + (f.art === wert ? " an" : ""), type: "button", "aria-pressed": String(f.art === wert),
    onclick: () => neu("art", wert) }, text);
  m.append(el("div", { class: "dk-arten", role: "group", "aria-label": t("dk_art") },
    chip("", `${t("dk_alle")} (${arten.reduce((s, [, n]) => s + n, 0)})`), arten.map(([a, n]) => chip(a, `${t("dka_" + a)} (${n})`))));
  const wahl = (k, paare, vorgabe) => el("select", { onchange: e => neu(k, e.target.value) }, paare.map(([v, text]) =>
    el("option", { value: v, ...((f[k] || vorgabe) === v ? { selected: true } : {}) }, text)));
  /* Format (Bild, Video, Text …) – quer zur Art: ein Video ist z. B. Art „Ergebnis“; Zahl = Dokumente in dieser Auswahl */
  const formate = {};
  for (const x of d.dokumente) formate[x.vorschau] = (formate[x.vorschau] || 0) + 1;
  if (f.format && !formate[f.format]) formate[f.format] = 0;
  const formatWahl = el("select", { "aria-label": t("dk_format"), onchange: e => neu("format", e.target.value) },
    el("option", { value: "" }, t("dk_format_alle")),
    DK_FORMATE.filter(v => formate[v] != null).map(v => el("option", { value: v, ...(f.format === v ? { selected: true } : {}) }, `${t("dkf_" + v)} (${formate[v]})`)));
  m.append(el("div", { class: "dk-filter" }, such, formatWahl,
    auswahl("von", t("alle_agenten"), Object.entries(d.von).map(([a, n]) => [a, `${a} (${n})`])),
    auswahl("bezug", t("dk_alle_bezuege"), bezugListe),
    wahl("zeit", [["", t("dk_zeit_alle")], ["heute", t("dk_zeit_heute")], ["7", t("dk_zeit_7")], ["30", t("dk_zeit_30")]], ""),
    wahl("sort", [["neu", t("dk_sort_neu")], ["alt", t("dk_sort_alt")], ["titel", t("dk_sort_titel")], ["art", t("dk_sort_art")]], "neu"),
    el("select", { onchange: e => neu("status", e.target.value) }, ["aktuell", "archiviert", "alle"].map(s =>
      el("option", { value: s, ...(f.status === s ? { selected: true } : {}) }, t("dks_" + s) + (s === "archiviert" ? ` (${d.archiviert})` : "")))),
    el("button", { class: "klein-knopf", type: "button", onclick: () => neu("liste", !f.liste) }, t(f.liste ? "dk_raster" : "dk_liste"))));
  const ab = f.zeit === "heute" ? new Date(new Date().setHours(0, 0, 0, 0)) : f.zeit ? new Date(Date.now() - Number(f.zeit) * 864e5) : null;
  d.dokumente = d.dokumente.filter(x => (!ab || new Date(x.version_utc) >= ab) && (!f.format || x.vorschau === f.format));
  const vergleich = { alt: (a, b) => a.version_utc.localeCompare(b.version_utc) || a.id - b.id,
    titel: (a, b) => a.titel.localeCompare(b.titel, gebiet(), { numeric: true }),
    art: (a, b) => t("dka_" + a.art).localeCompare(t("dka_" + b.art), gebiet()) || b.version_utc.localeCompare(a.version_utc) }[f.sort];
  if (vergleich) d.dokumente.sort(vergleich);
  if (!d.dokumente.length) {
    m.append(el("div", { class: "leer" }, t(f.q || f.art || f.von || f.bezug || f.zeit || f.format || f.status !== "aktuell" ? "nichts_gefunden" : "dk_leer")),
      el("p", { class: "sehrleise mono", style: "font-size:13px" }, "amw dokument ablegen <datei> --titel … --art ergebnis|bericht|entwurf|mockup|bild --aufgabe <nr>"));
    return;
  }
  const bezugText = x => x.bezug_art ? bezugRef(x.bezug_art, x.bezug_id) : null;
  const meta = x => [t("dka_" + x.art), x.angelegt_von, seit(x.version_utc), x.version > 1 ? "v" + x.version : null, bezugText(x), x.ki ? t("kvm_" + x.ki) : null,
    x.status !== "aktuell" ? t("dks_" + x.status) : null].filter(Boolean).join(" · ");
  if (f.liste) m.append(el("div", { class: "liste dk-liste" }, d.dokumente.map(x => el("div", { class: "zeile", onclick: () => dokumentDialog(x.id) },
    el("span", { class: "ref" }, "D" + x.id), el("span", {}, x.titel), el("span", { class: "leise" }, meta(x)),
    el("span", { class: "sehrleise mono" }, `${x.endung} · ${Math.max(1, Math.round(x.groesse / 1024))} KB`)))));
  else m.append(el("div", { class: "dk-raster" }, d.dokumente.map(x => el("button", { class: "dk-karte" + (x.ki === "verworfen" ? " verworfen" : ""), type: "button", title: x.titel, onclick: () => dokumentDialog(x.id) },
    el("div", { class: "dk-bild" }, dokSymbol(x), x.ki ? el("span", { class: "kv-marke " + x.ki }, t("kvm_" + x.ki)) : null), el("div", { class: "dk-text" }, el("b", {}, x.titel), el("span", {}, `D${x.id} · ${meta(x)}`))))));
}
/* KI-Ergebnis: ausgewählt / verworfen / nachbearbeitet (Schema 21) – es gilt der jüngste Entscheid, Nachbearbeitung mit Text */
function kiVermerkBlock(d, knopf, tun) {
  const vs = d.ki_vermerke || [], wahl = vs.slice().reverse().find(v => v.art !== "nachbearbeitet");
  const offen = d.status !== "geloescht";
  const nb = el("textarea", { rows: 3, placeholder: t("kv_nach_ph") });
  return el("div", { class: "dk-vermerk" }, el("h4", {}, t("kv_titel")),
    el("div", { class: "kv-stand " + (wahl ? wahl.art : "") }, wahl ? t("kv_" + wahl.art, { x: wahl.von, z: zeit(wahl.zeit_utc) }) : t("kv_offen")),
    offen ? el("div", { class: "dk-aktionen" },
      knopf(t("kv_auswaehlen"), () => tun("/api/dokument/vermerk", { art: "ausgewaehlt" }, t("kv_ok")), wahl?.art !== "ausgewaehlt"),
      knopf(t("kv_verwerfen"), () => tun("/api/dokument/vermerk", { art: "verworfen" }, t("kv_ok")))) : null,
    offen ? nb : null,
    offen ? el("div", { class: "dk-aktionen" }, knopf(t("kv_nach"), () => { if (nb.value.trim().length < 5) { nb.focus(); return; }
      tun("/api/dokument/vermerk", { art: "nachbearbeitet", text: nb.value.trim() }, t("kv_ok")); })) : null,
    vs.length ? el("div", { class: "kv-verlauf" }, vs.slice().reverse().map(v => el("div", { class: "sehrleise" },
      `${t("kva_" + v.art)} · ${v.von} · ${zeit(v.zeit_utc)} · v${v.version_nr}` + (v.text ? ` – ${v.text}` : "")))) : null,
    el("p", { class: "sehrleise", style: "margin:0;font-size:12.5px" }, t("kv_erkl")));
}
async function dokumentDialog(id, v) {
  let d; try { d = await abrufen(`/api/dokument?id=${id}` + (v ? `&v=${v}` : "")); } catch (e) { toast(t("fehler", { x: e.message }), true); return; }
  const ver = d.versionen.find(x => x.nr === d.gezeigt), nurPc = nurAmPc({ ...ver, online: d.online });
  /* online ist ein Text keine Datei auf dem Webspace – Herunterladen dann aus dem gezeigten Text */
  const url = API && ver.vorschau === "text" ? URL.createObjectURL(new Blob([d.text || ""], { type: "text/plain;charset=utf-8" })) : dokUrl(d.id, ver.nr);
  const vorschau = d.status === "geloescht" ? el("div", { class: "leer" }, t("dks_geloescht"))
    : nurPc ? el("div", { class: "leer dk-nurpc" }, el("p", {}, t("dk_nur_pc_text")),
      el("div", { class: "dk-aktionen", style: "justify-content:center" },
        el("button", { class: "knopf haupt", type: "button", onclick: () => tun("/api/dokument/online", { an: true }) }, t("dk_anfordern")),
        d.bezug_art ? el("button", { class: "klein-knopf", type: "button", onclick: async e => { e.target.disabled = true;
          try { const l = (await abrufen(`/api/dokumente?bezug_art=${d.bezug_art}&bezug_id=${d.bezug_id}`)).dokumente.filter(nurAmPc);
            for (const x of l) await schicken("/api/dokument/online", { id: x.id, an: true }); hg.remove(); }
          catch (x) { toast(t("fehler", { x: x.message }), true); e.target.disabled = false; } } },
          t("dk_alle_anfordern", { x: bezugRef(d.bezug_art, d.bezug_id) })) : null))
    : ver.vorschau === "bild" ? el("img", { src: url, alt: d.titel, title: t("vb_tipp"), onclick: () => dokVollbild(d, ver) })
    : ver.vorschau === "mockup" ? el("iframe", { src: url, sandbox: "allow-scripts", title: d.titel, referrerpolicy: "no-referrer" })
    : ver.vorschau === "pdf" ? el("iframe", { src: url, title: d.titel })
    : ver.vorschau === "video" ? el("video", { src: url, controls: true, preload: "metadata", playsinline: true, title: d.titel })
    : ver.vorschau === "text" ? (ver.format === "markdown" ? markdown(d.text || "") : el("pre", { class: "spec-text", style: "margin:0" }, d.text || ""))
    : el("div", { class: "leer" }, t("dk_nur_download"));
  const knopf = (text, fn, haupt) => el("button", { class: haupt ? "knopf haupt" : "klein-knopf", type: "button", onclick: fn }, text);
  const tun = async (weg, daten, text) => { try { const r = await schicken(weg, { id: d.id, ...daten }); if (text && !r.unterwegs) toast(text); hg.remove(); dokumentDialog(d.id, v); if (zustand.sicht === "dokumente") sichtDokumente(); }
    catch (e) { toast(t("fehler", { x: e.message }), true); } };
  const nachricht = el("textarea", { rows: 3, placeholder: t("dk_kommentar_ph") });
  const melden = async ueberarbeiten => { if (!nachricht.value.trim()) { nachricht.focus(); return; }
    try { const r = await schicken("/api/dokument/kommentar", { id: d.id, text: nachricht.value.trim(), ueberarbeiten }); if (!r.unterwegs) toast(t("gesendet", { x: r.an.join(", ") })); hg.remove(); dokumentDialog(d.id, v); }
    catch (e) { toast(t("fehler", { x: e.message }), true); } };
  const bezug = d.bezug_art ? el("a", { class: "verweis", onclick: () => { hg.remove(); dokBezugOeffnen(d); } },
    bezugRef(d.bezug_art, d.bezug_id) + (d.bezug_titel ? ` · ${d.bezug_titel}` : "")) : el("span", { class: "sehrleise" }, t("dk_ohne_bezug"));
  const hg = dialog(`D${d.id} · ${d.titel}`,
    el("p", { class: "leise", style: "margin-top:0" }, [t("dka_" + d.art), t("von", { x: d.angelegt_von }), zeit(d.angelegt_utc), t("dks_" + d.status),
      ver.vorschau === "text" ? null : d.online ? t("dk_online_an") : t("dk_online_aus")].filter(Boolean).join(" · ")),
    el("div", { class: "dk-detail" },
      el("div", { class: "dk-vorschau" }, vorschau),
      el("aside", { class: "dk-seite" },
        el("div", {}, el("h4", {}, t("dk_gehoert_zu")), bezug),
        (d.ki_herkunft || []).filter(x => x.nr === ver.nr).map(x => el("div", { class: "dk-herkunft" }, el("h4", {}, t("ki_herkunft")),
          el("div", { class: "leise" }, `${x.ki} ${x.ki_version || ""} · ${x.modell || ""}` + (x.modell_lizenz ? ` (${x.modell_lizenz})` : "")),
          el("div", { class: "sehrleise" }, [`L${x.lauf_id}`, x.seed != null ? `Seed ${x.seed}` : null, x.vorlage ? t("ki_vorlage_x", { x: x.vorlage }) : null,
            x.dauer_s ? `${x.dauer_s} s` : null, x.vram_spitze_gb ? `${x.vram_spitze_gb} GB VRAM` : null].filter(Boolean).join(" · ")),
          el("div", { class: "dk-prompt" }, x.prompt),
          x.gegenprobe ? el("div", { class: "sehrleise" }, `${t("ki_gegenprobe")}: ${x.gegenprobe}`) : null)),
        (d.ki_herkunft || []).length ? kiVermerkBlock(d, knopf, tun) : null,
        el("div", {}, el("h4", {}, t("dk_versionen", { n: d.versionen.length }),
          d.versionen.length > 1 ? el("button", { class: "klein-knopf dk-vergleich-knopf", type: "button", onclick: () => {
            const i = d.versionen.findIndex(x => x.nr === ver.nr);                // gezeigte Fassung mit der davor (v1: mit v2)
            dokVergleich(d, ...(i > 0 ? [d.versionen[i - 1].nr, ver.nr] : [ver.nr, d.versionen[1].nr])); } }, t("dk_vergleichen")) : null),
          d.versionen.slice().reverse().map(x => el("button", {
          class: "dk-version" + (x.nr === ver.nr ? " an" : ""), type: "button", onclick: () => { hg.remove(); dokumentDialog(d.id, x.nr); } },
          `v${x.nr} · ${x.von} · ${zeit(x.zeit_utc)} · ${x.endung} · ${Math.max(1, Math.round(x.groesse / 1024))} KB` + (x.notiz ? ` – ${x.notiz}` : "")))),
        el("div", {}, el("h4", {}, t("dk_gespraech", { n: d.gespraech.length })),
          d.gespraech.length ? d.gespraech.map(n => el("div", { class: "dk-nachricht" }, el("div", { class: "sehrleise" }, `#${n.id} · ${wer(n.von)} → ${n.an || "–"} · ${seit(n.zeit_utc)}`),
            el("div", {}, n.kurz), n.text ? el("div", { class: "leise", style: "white-space:pre-wrap" }, n.text.split("\n\n(Dokument D")[0]) : null)) : el("div", { class: "sehrleise" }, t("dk_kein_gespraech")),
          d.status !== "geloescht" ? el("div", { style: "margin-top:8px;display:grid;gap:6px" }, nachricht, el("div", { class: "dk-aktionen" },
            knopf(t("dk_kommentieren"), () => melden(false)), knopf(t("dk_ueberarbeiten"), () => melden(true), true))) : null),
        d.status !== "geloescht" ? el("div", { class: "dk-aktionen" },
          ver.vorschau === "text" ? knopf(t(ver.nr === d.versionen[d.versionen.length - 1].nr ? "dk_bearbeiten" : "dk_als_neue"), () => { hg.remove(); dokBearbeiten(d, ver); }, true) : null,
          ["bild", "mockup", "pdf"].includes(ver.vorschau) && !nurPc ? knopf(t("vb_vollbild"), () => dokVollbild(d, ver, vorschau), true) : null,
          !nurPc && !(API && ver.vorschau === "text") ? el("a", { class: "klein-knopf", href: url, target: "_blank", rel: "noopener" }, t("dk_oeffnen")) : null,
          !nurPc ? el("a", { class: "klein-knopf", href: url, download: `D${d.id}-v${ver.nr}${ver.endung}` }, t("dk_herunterladen")) : null,
          knopf(t("dk_zuordnen"), () => dokZuordnen(d, hg)),
          d.status === "aktuell" ? knopf(t("dk_archivieren"), () => tun("/api/dokument/status", { status: "archiviert" }, t("dk_archiviert")))
            : knopf(t("dk_wiederherstellen"), () => tun("/api/dokument/status", { status: "aktuell" })),
          ver.vorschau !== "text" && !nurPc ? knopf(t(d.online ? "dk_offline" : "dk_online"), () => tun("/api/dokument/online", { an: !d.online })) : null,
          !API ? knopf(t("dk_loeschen"), () => { if (confirm(t("dk_loeschen_frage", { x: d.titel }))) tun("/api/dokument/loeschen", {}, t("dk_geloescht")); }) : null) : null)));
  hg.querySelector(".dialog").style.width = "min(1280px,96vw)";
}
/* Vollbild-Hülle (A1614): ✕ immer oben rechts im sichtbaren Bereich, Esc, die Zurück-Taste bzw. -Geste am Handy und das
   Verlassen des echten Vollbilds schließen. Gibt schliessen() zurück; aufraeumen() räumt die eigenen Tasten usw. ab. */
function vollbildHuelle(hg, aufraeumen) {
  let offen = true;
  const zu = el("button", { class: "vb-zu", type: "button", title: t("vb_schliessen"), "aria-label": t("vb_schliessen"),
    onclick: e => { e.stopPropagation(); schliessen(); } }, "✕");
  const esc = e => { if (e.key !== "Escape") return; e.preventDefault(); e.stopImmediatePropagation(); schliessen(); };   // nur das Vollbild, nicht den Dialog darunter
  const zurueck = () => schliessen(true);
  const raus = () => { if (!document.fullscreenElement) schliessen(); };   // Esc im echten Vollbild verlässt es – dann ganz zu
  function schliessen(vonZurueck) {
    if (!offen) return;
    offen = false;
    window.removeEventListener("keydown", esc, true); window.removeEventListener("popstate", zurueck);
    document.removeEventListener("fullscreenchange", raus);
    if (document.fullscreenElement === hg) document.exitFullscreen().catch(() => {});
    hg.remove();
    if (aufraeumen) aufraeumen();
    if (!vonZurueck && history.state && history.state.amwVollbild) history.back();   // den eigenen Eintrag wieder wegnehmen
  }
  hg.append(zu);
  window.addEventListener("keydown", esc, true);
  history.pushState({ amwVollbild: 1 }, "", location.href);         // Zurück schließt das Vollbild statt die Seite zu wechseln
  window.addEventListener("popstate", zurueck);
  document.body.append(hg);
  if (hg.requestFullscreen) hg.requestFullscreen({ navigationUI: "hide" }).then(() => document.addEventListener("fullscreenchange", raus)).catch(() => {});
  return schliessen;
}
/* Bild im Vollbild: eingepasst, Mausrad oder zwei Finger zoomen an der Stelle, Ziehen verschiebt, Doppelklick 1:1 ↔ eingepasst,
   ←/→ blättert durch die Bilder derselben Aufgabe/desselben Bogens, Esc schließt */
function bildVollbild(bilder, i) {
  let z = 1, x = 0, y = 0, passt = 1;
  const img = el("img", { alt: "", draggable: "false" }), buehne = el("div", { class: "vb-buehne" }, img);
  const titel = el("span", { class: "vb-titel" }), stufe = el("span", { class: "vb-stufe" });
  const knopf = (text, tip, fn, k = "") => el("button", { class: "vb-knopf " + k, type: "button", title: tip, "aria-label": tip, onclick: e => { e.stopPropagation(); fn(); } }, text);
  const zeigen = () => { img.style.transform = `translate(${x}px,${y}px) scale(${z})`; stufe.textContent = `${Math.round(z * 100)} %`; };
  const setzen = (nz, px, py) => { nz = Math.min(8, Math.max(Math.min(passt, 1) / 4, nz)); x = px - (px - x) * nz / z; y = py - (py - y) * nz / z; z = nz; zeigen(); };
  const mitte = () => { const r = buehne.getBoundingClientRect(); return [r.width / 2, r.height / 2]; };
  /* A1675: Auf dem iPad ist die Bühne beim Laden des Bilds oft noch 0 groß (Wechsel ins echte Vollbild läuft noch) – dann
     ergab das scale(0), das Bild blieb schwarz. Jetzt: bei 0 im nächsten Bild noch einmal, und neu bei jeder Größenänderung
     der Bühne und beim Wechsel ins/aus dem Vollbild; passt ist nie 0. */
  let nochmal = 0;
  const einpassen = () => { const r = buehne.getBoundingClientRect(), w = img.naturalWidth || 1, h = img.naturalHeight || 1;
    if (r.width < 2 || r.height < 2) { if (nochmal++ < 120) requestAnimationFrame(einpassen); return; }
    nochmal = 0;
    passt = Math.max(Math.min(r.width / w, r.height / h), 0.01); z = Math.min(passt, 1); x = (r.width - w * z) / 2; y = (r.height - h * z) / 2; zeigen(); };
  const laden = n => { i = (n + bilder.length) % bilder.length; const b = bilder[i];
    titel.textContent = `D${b.id} · ${b.titel}` + (bilder.length > 1 ? `  (${i + 1}/${bilder.length})` : ""); img.onload = einpassen; img.src = dokUrl(b.id, b.nr); };
  const hg = el("div", { class: "vb", role: "dialog", "aria-modal": "true", "aria-label": t("vb_vollbild") }, buehne,
    el("div", { class: "vb-leiste" }, titel, el("span", { class: "vb-hilfe" }, t("vb_hilfe")), stufe,
      knopf("−", t("vb_kleiner"), () => setzen(z / 1.25, ...mitte())), knopf("+", t("vb_groesser"), () => setzen(z * 1.25, ...mitte())),
      knopf(t("vb_einpassen"), t("vb_einpassen") + " (0)", einpassen), knopf("1:1", t("vb_original") + " (1)", () => setzen(1, ...mitte()), "vb-eins"),
      bilder.length > 1 ? knopf("‹", t("vb_zurueck"), () => laden(i - 1)) : null, bilder.length > 1 ? knopf("›", t("vb_weiter"), () => laden(i + 1)) : null));
  const zeiger = new Map();
  let abstand = 0;
  buehne.addEventListener("wheel", e => { e.preventDefault(); const r = buehne.getBoundingClientRect();
    setzen(z * Math.exp(-Math.max(-60, Math.min(60, e.deltaY)) * 0.004), e.clientX - r.left, e.clientY - r.top); }, { passive: false });
  let tipp = null, letzterTipp = 0;
  buehne.addEventListener("pointerdown", e => { buehne.setPointerCapture(e.pointerId); zeiger.set(e.pointerId, [e.clientX, e.clientY]); buehne.classList.add("zieht");
    tipp = zeiger.size === 1 ? { x: e.clientX, y: e.clientY, t: Date.now() } : null; });
  buehne.addEventListener("pointermove", e => {
    if (!zeiger.has(e.pointerId)) return;
    const [ax, ay] = zeiger.get(e.pointerId);
    if (zeiger.size === 1) { x += e.clientX - ax; y += e.clientY - ay; zeigen(); }
    zeiger.set(e.pointerId, [e.clientX, e.clientY]);
    if (zeiger.size === 2) {                                    // zwei Finger: Abstand ändert die Stufe, um die Mitte
      const [[x1, y1], [x2, y2]] = [...zeiger.values()], r = buehne.getBoundingClientRect(), neu = Math.hypot(x2 - x1, y2 - y1);
      if (abstand) setzen(z * neu / abstand, (x1 + x2) / 2 - r.left, (y1 + y2) / 2 - r.top);
      abstand = neu;
    }
  });
  let geschaltet = 0;
  const umschalten = (cx, cy) => { if (Date.now() - geschaltet < 500) return; geschaltet = Date.now(); const r = buehne.getBoundingClientRect();
    if (Math.abs(z - Math.min(passt, 1)) < 0.01) setzen(Math.max(1, passt * 2), cx - r.left, cy - r.top); else einpassen(); };
  const los = e => { zeiger.delete(e.pointerId); abstand = 0; if (!zeiger.size) buehne.classList.remove("zieht");
    /* Doppeltippen am Handy (dort kommt kein dblclick, weil die Bühne die Gesten selbst behandelt) */
    if (e.type === "pointerup" && e.pointerType !== "mouse" && tipp && Date.now() - tipp.t < 300 && Math.hypot(e.clientX - tipp.x, e.clientY - tipp.y) < 12) {
      if (Date.now() - letzterTipp < 350) { umschalten(e.clientX, e.clientY); letzterTipp = 0; } else letzterTipp = Date.now();
    } };
  buehne.addEventListener("pointerup", los); buehne.addEventListener("pointercancel", los);
  buehne.addEventListener("dblclick", e => umschalten(e.clientX, e.clientY));
  const taste = e => {
    const k = { ArrowLeft: () => laden(i - 1), ArrowRight: () => laden(i + 1), "+": () => setzen(z * 1.25, ...mitte()),
      "=": () => setzen(z * 1.25, ...mitte()), "-": () => setzen(z / 1.25, ...mitte()), "0": einpassen, "1": () => setzen(1, ...mitte()) }[e.key];
    if (!k) return;
    e.preventDefault(); e.stopImmediatePropagation(); k();
  };
  const groesse = () => { if (img.naturalWidth) einpassen(); };
  const beobachter = window.ResizeObserver ? new ResizeObserver(groesse) : null;
  if (beobachter) beobachter.observe(buehne);
  window.addEventListener("keydown", taste, true); window.addEventListener("resize", groesse);
  for (const n of ["fullscreenchange", "webkitfullscreenchange"]) document.addEventListener(n, groesse);
  vollbildHuelle(hg, () => { window.removeEventListener("keydown", taste, true); window.removeEventListener("resize", groesse);
    for (const n of ["fullscreenchange", "webkitfullscreenchange"]) document.removeEventListener(n, groesse);
    if (beobachter) beobachter.disconnect(); });
  laden(i);
}
async function dokVollbild(d, ver, rahmen) {
  if (ver.vorschau !== "bild") {             // Mockup, PDF: eigene Hülle mit ✕ (der Rahmen allein im Vollbild hatte am Handy keinen Ausweg)
    const r = rahmen && rahmen.tagName === "IFRAME" ? rahmen.cloneNode(false) : el("iframe", { src: dokUrl(d.id, ver.nr), title: d.titel });
    vollbildHuelle(el("div", { class: "vb vb-rahmen", role: "dialog", "aria-modal": "true", "aria-label": t("vb_vollbild") }, r,
      el("div", { class: "vb-leiste" }, el("span", { class: "vb-titel" }, `D${d.id} · ${d.titel}`),
        el("a", { class: "vb-knopf", href: dokUrl(d.id, ver.nr), target: "_blank", rel: "noopener" }, t("dk_oeffnen")))));
    return;
  }
  let bilder = [{ id: d.id, nr: ver.nr, titel: d.titel }];
  if (d.bezug_art) try {
    const l = (await abrufen(`/api/dokumente?bezug_art=${d.bezug_art}&bezug_id=${d.bezug_id}`)).dokumente.filter(x => x.vorschau === "bild" && !nurAmPc(x)).reverse();
    if (l.some(x => x.id === d.id)) bilder = l.map(x => x.id === d.id ? bilder[0] : { id: x.id, nr: x.version, titel: x.titel });
  } catch (e) { /* dann eben nur dieses Bild */ }
  bildVollbild(bilder, bilder.findIndex(x => x.id === d.id));
}
function dokBezugOeffnen(d) {
  if (d.bezug_art === "bogen") { zeige("planung"); zuSchritt(null, d.bezug_id); }
  else if (d.bezug_art === "aufgabe") { zustand.dok = { ...(zustand.dok || {}), bezug: `aufgabe:${d.bezug_id}`, status: "aktuell" }; zeige("dokumente"); }
  else if (d.bezug_art === "frage") zeige("fragen");
  else zeige("wissen");
}
function dokZuordnen(d, alt) {
  const art = el("select", {}, ["ergebnis", "bericht", "entwurf", "mockup", "bild", "quelle"].map(a => el("option", { value: a, ...(a === d.art ? { selected: true } : {}) }, t("dka_" + a))));
  const typ = el("select", {}, ["", "bogen", "aufgabe", "frage", "beschluss"].map(a => el("option", { value: a, ...(a === (d.bezug_art || "") ? { selected: true } : {}) }, a ? t("dkb_" + a) : t("dk_ohne_bezug"))));
  const nr = el("input", { type: "number", min: 1, value: d.bezug_id || "", placeholder: "Nr." });
  const titel = el("input", { value: d.titel });
  const hg = dialog(t("dk_zuordnen") + ` · D${d.id}`,
    ...[[t("pl_titel"), titel], [t("k_art"), art], [t("dk_gehoert_zu"), el("div", { style: "display:flex;gap:6px" }, typ, nr)]].map(([l, x]) =>
      el("div", { class: "feld" }, el("label", {}, l), el("div", {}, x))),
    el("div", { class: "aktionen" }, el("button", { class: "knopf haupt", type: "button", onclick: async () => {
      const daten = { id: d.id, titel: titel.value.trim(), art: art.value };
      if (!typ.value) daten.loesen = true; else daten[typ.value] = nr.value;
      try { await schicken("/api/dokument/setzen", daten); hg.remove(); alt.remove(); dokumentDialog(d.id); if (zustand.sicht === "dokumente") sichtDokumente(); }
      catch (e) { toast(t("fehler", { x: e.message }), true); } } }, t("speichern"))));
}

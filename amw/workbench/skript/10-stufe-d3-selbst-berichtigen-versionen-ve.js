/* --- Stufe D3: selbst berichtigen, Versionen vergleichen, hochladen -------------------------------- */
/* Unterschiede zweier Folgen (Zeilen oder Wörter) nach Myers: [[0|-1|1, Eintrag], …] – gleich, weg, neu. Gleicher Anfang und
   gleiches Ende zählen nicht mit; sehr viele Änderungen (> 4000 Schritte) werden grob als „alles weg, alles neu“ gezeigt. */
function diffFolge(a, b) {
  let s = 0; while (s < a.length && s < b.length && a[s] === b[s]) s++;
  let ea = a.length, eb = b.length; while (ea > s && eb > s && a[ea - 1] === b[eb - 1]) { ea--; eb--; }
  const A = a.slice(s, ea), B = b.slice(s, eb), N = A.length, M = B.length;
  let mitte = [];
  if (!N || !M) mitte = [...A.map(x => [-1, x]), ...B.map(x => [1, x])];
  else {
    const off = N + M + 1, v = new Int32Array(2 * off + 2), spur = [];
    let fertig = false;
    for (let d = 0; d <= Math.min(N + M, 4000) && !fertig; d++) {
      spur.push(v.slice(off - d - 1, off + d + 2));                 // Stand vor Schritt d, für k = -d-1 … d+1
      for (let k = -d; k <= d; k += 2) {
        let x = k === -d || (k !== d && v[off + k - 1] < v[off + k + 1]) ? v[off + k + 1] : v[off + k - 1] + 1, y = x - k;
        while (x < N && y < M && A[x] === B[y]) { x++; y++; }
        v[off + k] = x;
        if (x >= N && y >= M) { fertig = true; break; }
      }
    }
    if (!fertig) mitte = [...A.map(x => [-1, x]), ...B.map(x => [1, x])];
    else {
      let x = N, y = M;
      for (let d = spur.length - 1; d > 0; d--) {
        const w = spur[d], hol = k => w[k + d + 1], k = x - y;
        const vk = k === -d || (k !== d && hol(k - 1) < hol(k + 1)) ? k + 1 : k - 1, vx = hol(vk), vy = vx - vk;
        while (x > vx && y > vy) { mitte.push([0, A[--x]]); y--; }
        if (vk === k + 1) mitte.push([1, B[--y]]); else mitte.push([-1, A[--x]]);
      }
      while (x > 0 && y > 0) { mitte.push([0, A[--x]]); y--; }
      mitte.reverse();
    }
  }
  /* in jedem Änderungsblock erst alles Weggefallene, dann alles Neue – liest sich wie ein Vorher/Nachher */
  const aus = a.slice(0, s).map(x => [0, x]);
  for (let i = 0; i < mitte.length;) {
    if (!mitte[i][0]) { aus.push(mitte[i++]); continue; }
    const weg = [], neu = [];
    while (i < mitte.length && mitte[i][0]) (mitte[i][0] < 0 ? weg : neu).push(mitte[i++]);
    aus.push(...weg, ...neu);
  }
  return aus.concat(a.slice(ea).map(x => [0, x]));
}
/* Zeilen-Vergleich als DOM: gelöscht/neu mit hervorgehobenen Wörtern, lange unveränderte Strecken eingeklappt */
function diffAnsicht(alt, neu) {
  const z = diffFolge(alt.replace(/\r\n/g, "\n").split("\n"), neu.replace(/\r\n/g, "\n").split("\n"));
  const woerter = s => s.match(/\s+|[\p{L}\p{N}_]+|[^\s\p{L}\p{N}_]/gu) || [];
  const zeilen = [];
  let na = 0, nb = 0, plus = 0, minus = 0;
  for (let i = 0; i < z.length;) {
    if (!z[i][0]) { zeilen.push({ op: 0, text: z[i][1], na: ++na, nb: ++nb }); i++; continue; }
    const weg = [], dazu = [];
    while (i < z.length && z[i][0] < 0) weg.push(z[i++][1]);
    while (i < z.length && z[i][0] > 0) dazu.push(z[i++][1]);
    minus += weg.length; plus += dazu.length;
    const w = weg.map(text => ({ op: -1, text, na: ++na })), n = dazu.map(text => ({ op: 1, text, nb: ++nb }));
    for (let j = 0; j < Math.min(w.length, n.length); j++) {          // Zeile geändert: Wörter hervorheben, wenn genug gleich blieb
      const d = diffFolge(woerter(w[j].text), woerter(n[j].text)), gleich = d.filter(x => !x[0]).reduce((s, x) => s + x[1].length, 0);
      if (gleich >= 0.4 * Math.max(w[j].text.length, n[j].text.length)) {
        w[j].teile = d.filter(x => x[0] <= 0); n[j].teile = d.filter(x => x[0] >= 0);
      }
    }
    zeilen.push(...w, ...n);
  }
  if (!plus && !minus) return el("div", { class: "leer" }, t("dk_df_gleich"));
  const zeile = x => el("div", { class: "df-z" + (x.op < 0 ? " df-weg" : x.op > 0 ? " df-neu" : "") },
    el("span", { class: "df-n" }, x.op > 0 ? "" : x.na), el("span", { class: "df-n" }, x.op < 0 ? "" : x.nb),
    el("span", { class: "df-z-zeichen" }, x.op < 0 ? "−" : x.op > 0 ? "+" : ""),
    el("span", { class: "df-t" }, x.teile ? x.teile.map(([o, s]) => o ? el("mark", {}, s) : s) : x.text || "​"));
  const kasten = el("div", { class: "df" });
  const ROT = 3;                                                       // so viele unveränderte Zeilen um jede Änderung
  const nah = zeilen.map((x, i) => zeilen.slice(Math.max(0, i - ROT), i + ROT + 1).some(y => y.op));
  for (let i = 0; i < zeilen.length;) {
    if (nah[i]) { kasten.append(zeile(zeilen[i++])); continue; }
    const von = i; while (i < zeilen.length && !nah[i]) i++;
    const strecke = zeilen.slice(von, i);
    const luecke = el("button", { class: "df-luecke", type: "button", onclick: () => luecke.replaceWith(...strecke.map(zeile)) },
      t("dk_df_luecke", { n: strecke.length }));
    kasten.append(luecke);
  }
  return el("div", {}, el("p", { class: "leise", style: "margin:0 0 8px" }, el("span", { class: "df-plus" }, `+${plus}`), " ",
    el("span", { class: "df-minus" }, `−${minus}`), " " + t("dk_df_zeilen")), kasten);
}
async function dokVergleich(d, a, b) {
  const nrn = d.versionen.map(x => x.nr);
  b = b || nrn[nrn.length - 1]; a = a || nrn[Math.max(0, nrn.indexOf(b) - 1)];
  const wahl = (wert, fn) => el("select", { onchange: e => fn(+e.target.value) }, d.versionen.map(x =>
    el("option", { value: x.nr, ...(x.nr === wert ? { selected: true } : {}) }, `v${x.nr} · ${x.von} · ${zeit(x.zeit_utc)}`)));
  const inhalt = el("div", {}, ladeLogo(t("dk_laedt")));
  const hg = dialog(`${t("dk_vergleich")} · D${d.id} · ${d.titel}`,
    el("div", { class: "dk-filter" }, wahl(a, n => { hg.remove(); dokVergleich(d, n, b); }), el("span", { class: "leise" }, "→"),
      wahl(b, n => { hg.remove(); dokVergleich(d, a, n); })), inhalt);
  hg.querySelector(".dialog").style.width = "min(1280px,96vw)";
  const va = d.versionen.find(x => x.nr === a), vb = d.versionen.find(x => x.nr === b);
  if (va.vorschau === "text" && vb.vorschau === "text") {
    try {
      const [ta, tb] = await Promise.all([a, b].map(n => abrufen(`/api/dokument?id=${d.id}&v=${n}`).then(x => x.text || "")));
      inhalt.replaceChildren(diffAnsicht(ta, tb));
    } catch (e) { inhalt.replaceChildren(el("div", { class: "leer" }, t("fehler", { x: e.message }))); }
    return;
  }
  const bilder = [va, vb].filter(v => v.vorschau === "bild" && !nurAmPc({ ...v, online: d.online })).map(v => ({ id: d.id, nr: v.nr, titel: `${d.titel} · v${v.nr}` }));
  const seite = v => el("div", { class: "df-seite" },
    el("div", { class: "sehrleise" }, `v${v.nr} · ${v.von} · ${zeit(v.zeit_utc)}` + (v.notiz ? ` – ${v.notiz}` : "")),
    nurAmPc({ ...v, online: d.online }) ? el("div", { class: "leer" }, t("dk_online_aus"))
      : v.vorschau === "bild" ? el("img", { src: dokUrl(d.id, v.nr), alt: "", title: t("vb_tipp"), onclick: () => bildVollbild(bilder, bilder.findIndex(x => x.nr === v.nr)) })
      : v.vorschau === "mockup" ? el("iframe", { src: dokUrl(d.id, v.nr), sandbox: "allow-scripts", title: `v${v.nr}`, referrerpolicy: "no-referrer" })
      : v.vorschau === "pdf" ? el("iframe", { src: dokUrl(d.id, v.nr), title: `v${v.nr}` })
      : el("div", { class: "leer" }, t("dk_nur_download")));
  inhalt.replaceChildren(el("div", { class: "df-paar" }, seite(va), seite(vb)));
}
/* Selbst berichtigen: Text der gezeigten Fassung im Editor, gespeichert als neue Version – aber nur, solange niemand
   inzwischen eine neuere abgelegt hat (sonst Vergleich und bewusste Entscheidung). */
function dokBearbeiten(d, ver) {
  const letzte = d.versionen[d.versionen.length - 1], start = d.text || "";
  let basis = letzte.nr;
  const feld = el("textarea", { class: "dk-editor", spellcheck: "true", "aria-label": t("dk_schreiben") });
  feld.value = start;
  const vorschau = el("div", { class: "dk-vorschau dk-ed-vorschau", hidden: true });
  const notiz = el("input", { placeholder: t("dk_notiz_ph"), maxlength: 500 });
  const an = letzte.von !== "Entwickler" ? letzte.von : d.angelegt_von;
  const melden = el("input", { type: "checkbox", checked: true });
  const meldung = el("div");
  const zaehler = el("span", { class: "sehrleise" });
  const zaehlen = () => { zaehler.textContent = t("dk_zeichen", { n: feld.value.length.toLocaleString(gebiet()) }) + (feld.value !== start ? " · " + t("dk_geaendert") : ""); };
  feld.addEventListener("input", zaehlen); zaehlen();
  const reiterS = el("button", { type: "button", class: "an", onclick: () => umschalten(true) }, t("dk_schreiben"));
  const reiterV = el("button", { type: "button", onclick: () => umschalten(false) }, t("dk_vorschau"));
  function umschalten(schreiben) {
    feld.hidden = !schreiben; vorschau.hidden = schreiben; reiterS.classList.toggle("an", schreiben); reiterV.classList.toggle("an", !schreiben);
    if (!schreiben) vorschau.replaceChildren(ver.format === "markdown" ? markdown(feld.value) : el("pre", { class: "spec-text", style: "margin:0" }, feld.value));
    else feld.focus();
  }
  const speicherKnopf = el("button", { class: "knopf haupt", type: "button", onclick: () => speichern() }, t("dk_speichern_als", { n: letzte.nr + 1 }));
  async function speichern() {
    if (feld.value === start && basis === letzte.nr) { toast(t("dk_nichts_geaendert"), true); return; }
    speicherKnopf.disabled = true; meldung.replaceChildren();
    try {
      const r = await schicken("/api/dokument/text", { id: d.id, basis, text: feld.value, notiz: notiz.value.trim(), melden: an !== "Entwickler" && melden.checked });
      zu(true); if (!r.unterwegs) toast(t("dk_gespeichert", { n: r.version }));
      dokumentDialog(d.id); if (zustand.sicht === "dokumente") sichtDokumente();
    } catch (e) {
      speicherKnopf.disabled = false;
      meldung.replaceChildren(el("div", { class: "band-warn" }, e.message, " ",
        /Inzwischen|meanwhile/i.test(e.message) ? el("button", { class: "klein-knopf", type: "button", onclick: konflikt }, t("dk_unterschiede")) : null));
    }
  }
  async function konflikt() {
    let neu; try { neu = await abrufen(`/api/dokument?id=${d.id}`); } catch (e) { toast(t("fehler", { x: e.message }), true); return; }
    const k = dialog(t("dk_konflikt_titel", { a: neu.gezeigt }), diffAnsicht(neu.text || "", feld.value),
      el("div", { class: "aktionen" }, el("button", { class: "knopf haupt", type: "button", onclick: () => { basis = neu.gezeigt; k.remove(); speichern(); } },
        t("dk_trotzdem", { n: neu.gezeigt + 1 }))));
    k.querySelector(".dialog").style.width = "min(1280px,96vw)";
  }
  const hg = dialog(`${t("dk_bearbeiten")} · D${d.id} · ${d.titel}`,
    el("p", { class: "leise", style: "margin-top:0" }, t("dk_ed_basis", { v: ver.nr, n: letzte.nr + 1 })
      + (matchMedia("(pointer: coarse)").matches ? "" : " · " + t("dk_ed_hilfe"))),
    el("div", { class: "reiter", style: "margin-bottom:8px" }, reiterS, reiterV, el("div", { class: "rechts" }, zaehler)),
    feld, vorschau,
    meldung,
    el("div", { class: "dk-ed-unten" }, notiz,
      an !== "Entwickler" ? el("label", { class: "leise" }, melden, " " + t("dk_melden_an", { x: an })) : null,
      el("div", { class: "aktionen" }, el("button", { class: "klein-knopf", type: "button", onclick: () => zu() }, t("dk_abbrechen")), speicherKnopf)));
  hg.querySelector(".dialog").style.width = "min(1100px,96vw)";
  const warnen = e => { if (feld.value !== start) { e.preventDefault(); e.returnValue = ""; } };
  const tasten = e => {
    if (!hg.isConnected || document.querySelectorAll(".dialog-hg").length > 1 && hg !== [...document.querySelectorAll(".dialog-hg")].pop()) return;
    if (e.key === "Escape") { e.preventDefault(); e.stopImmediatePropagation(); zu(); }
    else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") { e.preventDefault(); speichern(); }
  };
  function zu(ohneFrage) {
    if (!ohneFrage && feld.value !== start && !confirm(t("dk_verwerfen"))) return;
    window.removeEventListener("keydown", tasten, true); window.removeEventListener("beforeunload", warnen); hg.remove();
  }
  hg.addEventListener("click", e => { if (e.target === hg) { e.stopImmediatePropagation(); zu(); } }, true);
  window.addEventListener("keydown", tasten, true); window.addEventListener("beforeunload", warnen);
  feld.focus(); feld.setSelectionRange(0, 0); feld.scrollTop = 0;
}
/* Hochladen: Datei wählen, Foto aufnehmen, hineinziehen oder einfügen. Fotos rechnet der Browser neu (verkleinert, ohne
   Standort/EXIF); dann in Teilen hoch (ein Funkloch kostet nur ein Teil), Prüfsumme aus dem Browser. */
const HOCH_ENDUNGEN = [".md", ".txt", ".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg", ".html", ".htm", ".pdf", ".docx", ".xlsx", ".mp4", ".webm", ".heic", ".heif"];
const HOCH_TEIL = 192 * 1024, BILD_MAX = 2560;
const endungVon = name => (/\.[^.]+$/.exec(name || "") || [""])[0].toLowerCase();
async function bildVorbereiten(datei, verkleinern) {
  const e = endungVon(datei.name);
  if (![".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif"].includes(e)) return { blob: datei, name: datei.name };
  let bild;
  try { bild = await createImageBitmap(datei, { imageOrientation: "from-image" }); }
  catch (x) { if (e === ".heic" || e === ".heif") throw new Error(t("dk_heic")); return { blob: datei, name: datei.name }; }
  const f = verkleinern ? Math.min(1, BILD_MAX / Math.max(bild.width, bild.height)) : 1;
  const c = el("canvas", { width: Math.max(1, Math.round(bild.width * f)), height: Math.max(1, Math.round(bild.height * f)) });
  c.getContext("2d").drawImage(bild, 0, 0, c.width, c.height); bild.close?.();
  const typ = e === ".png" ? "image/png" : e === ".webp" ? "image/webp" : "image/jpeg";
  const blob = await new Promise(r => c.toBlob(r, typ, 0.86));
  if (!blob) return { blob: datei, name: datei.name };
  if (e === ".png" && f === 1 && blob.size > datei.size) return { blob: datei, name: datei.name };   // Bildschirmfoto: Original ist kleiner
  return { blob, name: datei.name.replace(/\.[^.]+$/, "") + { "image/png": ".png", "image/webp": ".webp", "image/jpeg": ".jpg" }[typ] };
}
async function hochladenTeile(blob, name, fortschritt) {
  if (!crypto.subtle) throw new Error(t("dk_kein_https"));
  const roh = new Uint8Array(await blob.arrayBuffer());
  const sha = [...new Uint8Array(await crypto.subtle.digest("SHA-256", roh))].map(b => b.toString(16).padStart(2, "0")).join("");
  const teile = Math.max(1, Math.ceil(roh.length / HOCH_TEIL));
  const { id } = await schicken("/api/hochladen", { schritt: "start", name, groesse: roh.length, sha, teile });
  for (let i = 0; i < teile; i++) {
    const stueck = roh.subarray(i * HOCH_TEIL, (i + 1) * HOCH_TEIL);
    let b = ""; for (let j = 0; j < stueck.length; j += 0x8000) b += String.fromCharCode.apply(null, stueck.subarray(j, j + 0x8000));
    for (let versuch = 1; ; versuch++) {
      try { await schicken("/api/hochladen", { schritt: "teil", id, nr: i, inhalt: btoa(b) }); break; }
      catch (e) { if (versuch >= 3) throw e; await new Promise(r => setTimeout(r, 1500 * versuch)); }
    }
    fortschritt((i + 1) / teile);
  }
  return id;
}
const bogenRef = id => t("ref_bogen", { b: id });
const bezugRef = (art, id) => art === "bogen" ? bogenRef(id) : { aufgabe: "A", frage: "F", beschluss: "B" }[art] + id;
const bezugKurz = b => !b ? "" : bezugRef(b.slice(0, b.indexOf(":")), b.slice(b.indexOf(":") + 1));
function bezugLesen(s) {
  s = (s || "").trim();
  if (!s) return {};
  let m = /^(?:bogen|arc)\s*:?\s*(\d+)$/i.exec(s); if (m) return { bogen: +m[1] };
  m = /^([AFB])\s*(\d+)$/i.exec(s); if (m) return { [{ a: "aufgabe", f: "frage", b: "beschluss" }[m[1].toLowerCase()]]: +m[2] };
  return null;
}
function dokHochladen(vorgabe = {}) {
  const dateien = [];
  const liste = el("div", { class: "hl-liste" });
  const titel = el("input", { placeholder: t("pl_titel"), maxlength: 200 });
  const art = el("select", {}, el("option", { value: "" }, t("dk_art_auto")), ["ergebnis", "bericht", "entwurf", "mockup", "bild", "quelle"].map(a => el("option", { value: a }, t("dka_" + a))));
  const bezug = el("input", { placeholder: t("dk_bezug_ph"), value: bezugKurz(vorgabe.bezug) });
  const online = el("input", { type: "checkbox", ...(API ? { checked: true } : {}) });
  const klein = el("input", { type: "checkbox", checked: true });
  const annehmen = HOCH_ENDUNGEN.join(",") + ",image/*";
  const wahl = el("input", { type: "file", multiple: true, accept: annehmen, hidden: true, onchange: e => { dazu([...e.target.files]); e.target.value = ""; } });
  const kamera = el("input", { type: "file", accept: "image/*", capture: "environment", hidden: true, onchange: e => { dazu([...e.target.files]); e.target.value = ""; } });
  const finger = matchMedia("(pointer: coarse)").matches;              // Handy/Tablet: Kamera statt Ziehen und Strg+V
  const zone = el("div", { class: "hl-zone" }, el("p", { class: "leise", style: "margin:0 0 10px" }, t(finger ? "dk_hl_zone_netz" : "dk_hl_zone")),
    el("div", { class: "dk-aktionen", style: "justify-content:center" },
      el("button", { class: "knopf", type: "button", onclick: () => wahl.click() }, t("dk_hl_waehlen")),
      finger ? el("button", { class: "knopf", type: "button", onclick: () => kamera.click() }, t("dk_hl_foto")) : null), wahl, kamera);
  zone.addEventListener("dragover", e => { e.preventDefault(); zone.classList.add("drueber"); });
  zone.addEventListener("dragleave", () => zone.classList.remove("drueber"));
  zone.addEventListener("drop", e => { e.preventDefault(); zone.classList.remove("drueber"); dazu([...e.dataTransfer.files]); });
  const zustandDatei = new Map();
  function dazu(neu) {
    const ok = neu.filter(f => HOCH_ENDUNGEN.includes(endungVon(f.name)) || /^image\//.test(f.type));
    if (ok.length < neu.length) toast(t("dk_hl_format"), true);
    for (let f of ok) {
      if (!HOCH_ENDUNGEN.includes(endungVon(f.name)) || /^image\.png$/i.test(f.name)) {   // eingefügt: „image.png“ → sprechender Name
        const s = new Date().toLocaleString(gebiet(), { year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" }).replace(/[/:]/g, "-");
        f = new File([f], `${t("dk_hl_bildschirmfoto")} ${s}${{ "image/jpeg": ".jpg", "image/webp": ".webp", "image/gif": ".gif" }[f.type] || ".png"}`, { type: f.type });
      }
      dateien.push(f);
    }
    if (dateien.length === 1 && !titel.value) titel.value = dateien[0].name.replace(/\.[^.]+$/, "");
    zeigen();
  }
  function zeigen() {
    liste.replaceChildren(...dateien.map((f, i) => {
      const z = zustandDatei.get(f) || {};
      return el("div", { class: "hl-datei" },
        /^image\//.test(f.type) && endungVon(f.name) !== ".heic" ? el("img", { src: URL.createObjectURL(f), alt: "" }) : el("span", { class: "dk-symbol" }, el("small", {}, endungVon(f.name))),
        el("div", {}, el("div", { class: "hl-name" }, f.name), el("div", { class: "sehrleise" }, `${Math.max(1, Math.round(f.size / 1024)).toLocaleString(gebiet())} KB` + (z.text ? ` · ${z.text}` : "")),
          z.p != null ? el("progress", { max: 1, value: z.p }) : null),
        z.p == null ? el("button", { class: "klein-knopf", type: "button", "aria-label": t("vb_schliessen"), onclick: () => { dateien.splice(i, 1); zeigen(); } }, "✕") : el("span"));
    }));
    titelFeld.hidden = dateien.length > 1; mehrHinweis.hidden = dateien.length < 2;
  }
  const titelFeld = el("div", { class: "feld" }, el("label", {}, t("pl_titel")), el("div", {}, titel));
  const mehrHinweis = el("p", { class: "sehrleise", hidden: true }, t("dk_hl_titel_mehr"));
  const los = el("button", { class: "knopf haupt", type: "button", onclick: hochladen }, t("dk_hl_los"));
  async function hochladen() {
    if (!dateien.length) { toast(t("dk_hl_leer"), true); return; }
    const b = bezugLesen(bezug.value);
    if (!b) { toast(t("dk_bezug_falsch"), true); bezug.focus(); return; }
    los.disabled = true;
    const neu = []; let fehler = false;
    for (const f of [...dateien]) {
      const setze = (p, text) => { zustandDatei.set(f, { p, text }); zeigen(); };
      try {
        setze(0, t("dk_hl_bereite"));
        const { blob, name } = await bildVorbereiten(f, klein.checked);
        const id = await hochladenTeile(blob, name, p => setze(p, `${Math.round(p * 100)} %`));
        const r = await schicken("/api/dokument/neu", { hoch: id, titel: dateien.length === 1 ? titel.value.trim() : "", art: art.value, online: online.checked, ...b });
        if (r.dokument) neu.push(r.dokument);
        setze(1, "✓");
      } catch (e) { fehler = true; setze(null, "✕ " + e.message); }
    }
    if (fehler) { los.disabled = false; dateien.splice(0, dateien.length, ...dateien.filter(f => zustandDatei.get(f)?.text !== "✓")); zeigen(); return; }
    hg.remove(); window.removeEventListener("paste", einfuegen);
    toast(API ? t("dk_hl_fertig_netz") : t("dk_hl_fertig_pc", { n: neu.length }));
    if (zustand.sicht === "dokumente") sichtDokumente(); else if (zustand.sicht === "fragen") sichtFragen();
    if (neu.length === 1) dokumentDialog(neu[0]);
  }
  const einfuegen = e => { const f = [...(e.clipboardData?.files || [])]; if (f.length && hg.isConnected) { e.preventDefault(); dazu(f); } };
  window.addEventListener("paste", einfuegen);
  const hg = dialog(t("dk_hl_titel"), zone, liste, titelFeld, mehrHinweis,
    ...[[t("k_art"), art], [t("dk_gehoert_zu"), bezug]].map(([l, x]) => el("div", { class: "feld" }, el("label", {}, l), el("div", {}, x))),
    el("label", { class: "leise hl-schalter" }, klein, " " + t("dk_hl_klein")),
    el("label", { class: "leise hl-schalter" }, online, " " + t("dk_hl_online")),
    el("div", { class: "aktionen" }, los));
  new MutationObserver((_, b) => { if (!hg.isConnected) { window.removeEventListener("paste", einfuegen); b.disconnect(); } }).observe(document.body, { childList: true });
  if (vorgabe.dateien?.length) dazu(vorgabe.dateien);
}
/* Bildschirmfoto mit Strg+V im Bereich Dokumente → gleich hochladen */
document.addEventListener("paste", e => {
  if (zustand.sicht !== "dokumente" || document.querySelector(".dialog-hg, .vb")) return;
  const f = [...(e.clipboardData?.files || [])];
  if (f.length) { e.preventDefault(); dokHochladen({ bezug: zustand.dok?.bezug, dateien: f }); }
});
/* Markdown sicher als DOM (nie innerHTML): Überschriften, Absätze, Listen, Code, Zitate, Tabellen, Links (nur http/https/mailto) */
function markdown(text) {
  const inline = s => { const teile = []; const re = /(`[^`]+`)|(\*\*[^*]+\*\*|__[^_]+__)|(\*[^*\s][^*]*\*|_[^_\s][^_]*_)|(!?\[[^\]]*\]\([^)\s]+\))/g;
    let pos = 0, m;
    while ((m = re.exec(s))) {
      if (m.index > pos) teile.push(s.slice(pos, m.index));
      const x = m[0];
      if (m[1]) teile.push(el("code", {}, x.slice(1, -1)));
      else if (m[2]) teile.push(el("strong", {}, ...inline(x.slice(2, -2))));
      else if (m[3]) teile.push(el("em", {}, ...inline(x.slice(1, -1))));
      else { const l = /^(!?)\[([^\]]*)\]\(([^)\s]+)\)$/.exec(x); const ok = /^(https?:|mailto:)/i.test(l[3]);
        teile.push(l[1] ? el("span", { class: "sehrleise" }, `[${t("dk_bild")}: ${l[2] || l[3]}]`)
          : ok ? el("a", { href: l[3], target: "_blank", rel: "noopener noreferrer" }, l[2] || l[3]) : l[2]); }
      pos = m.index + x.length;
    }
    if (pos < s.length) teile.push(s.slice(pos));
    return teile; };
  const zeilen = text.replace(/\r\n?/g, "\n").split("\n"), aus = el("div", { class: "md" });
  let i = 0;
  const istListe = z => /^\s*([-*+]|\d+[.)])\s+/.test(z);
  while (i < zeilen.length) {
    const z = zeilen[i];
    if (!z.trim()) { i++; continue; }
    if (/^```/.test(z)) { const code = []; i++; while (i < zeilen.length && !/^```/.test(zeilen[i])) code.push(zeilen[i++]); i++;
      aus.append(el("pre", {}, el("code", {}, code.join("\n")))); continue; }
    const h = /^(#{1,6})\s+(.*)$/.exec(z);
    if (h) { aus.append(el("h" + Math.min(4, h[1].length), {}, ...inline(h[2].replace(/\s+#+\s*$/, "")))); i++; continue; }
    if (/^\s*([-*_])(\s*\1){2,}\s*$/.test(z)) { aus.append(el("hr")); i++; continue; }
    if (/^\s*>/.test(z)) { const q = []; while (i < zeilen.length && /^\s*>/.test(zeilen[i])) q.push(zeilen[i++].replace(/^\s*>\s?/, ""));
      const b = markdown(q.join("\n")); aus.append(el("blockquote", {}, ...b.childNodes)); continue; }
    if (z.includes("|") && i + 1 < zeilen.length && /^\s*\|?\s*:?-{2,}/.test(zeilen[i + 1])) {
      const zellen = r => r.trim().replace(/^\|/, "").replace(/\|$/, "").split("|").map(c => c.trim());
      const kopf = zellen(z); i += 2; const reihen = [];
      while (i < zeilen.length && zeilen[i].includes("|") && zeilen[i].trim()) reihen.push(zellen(zeilen[i++]));
      aus.append(el("table", {}, el("thead", {}, el("tr", {}, kopf.map(c => el("th", {}, ...inline(c))))),
        el("tbody", {}, reihen.map(r => el("tr", {}, r.map(c => el("td", {}, ...inline(c))))))));
      continue; }
    if (istListe(z)) {
      const wurzel = el(/^\s*\d/.test(z) ? "ol" : "ul"); const stapel = [[wurzel, (/^\s*/.exec(z))[0].length]];
      while (i < zeilen.length && (istListe(zeilen[i]) || (/^\s{2,}\S/.test(zeilen[i]) && stapel.length))) {
        const r = zeilen[i++], tief = (/^\s*/.exec(r))[0].length;
        if (!istListe(r)) { const li = stapel[stapel.length - 1][0].lastElementChild; if (li) li.append(" ", ...inline(r.trim())); continue; }
        while (stapel.length > 1 && tief < stapel[stapel.length - 1][1]) stapel.pop();
        if (tief > stapel[stapel.length - 1][1] + 1 && stapel[stapel.length - 1][0].lastElementChild) {
          const neu = el(/^\s*\d/.test(r) ? "ol" : "ul"); stapel[stapel.length - 1][0].lastElementChild.append(neu); stapel.push([neu, tief]); }
        stapel[stapel.length - 1][0].append(el("li", {}, ...inline(r.replace(/^\s*([-*+]|\d+[.)])\s+/, "").replace(/^\[( |x)\]\s*/i, (_, x) => x.trim() ? "☑ " : "☐ "))));
      }
      aus.append(wurzel); continue; }
    const absatz = [];
    while (i < zeilen.length && zeilen[i].trim() && !/^(#{1,6}\s|```|\s*>)/.test(zeilen[i]) && !istListe(zeilen[i])) absatz.push(zeilen[i++].trim());
    aus.append(el("p", {}, ...inline(absatz.join(" "))));
  }
  return aus;
}


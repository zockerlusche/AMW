/* --- A2014: Kopfzeile nach Kleinprobe A2010 (D1904/D1905, TL #33873) – Projektwechsel mit „für dich“, Gesamtsicht über alle Projekte,
   Suche über alles beim Tippen: erst das eigene Projekt, dann die anderen; eine Nummer findet das Ding selbst, ein Klick öffnet es (A2115).
   Keine Tor-Leiste, keine zweite Statusleiste; Farbe nur am Zähler „für dich“. --------------------------------------------------- */
function kzKnopf() {
  const p = projekte.find(x => x.uid === projekt);
  if (p) projektwahlZeigen(p);
}

/* Gesamtsicht (#projekte): je Projekt eine Karte – für dich, Meilenstein und Pakete, Balken, Prognose mit Verzug, wer arbeitet.
   Online gibt es nur die Projektliste (ohne Fortschritt): dann Name und „für dich“. Klick wechselt ins Projekt (Leitstand). */
async function sichtProjekte() {
  const m = rahmen(t("kz_alle")), nr = wechselNr;                           /* rahmen zählt den Wechsel selbst */
  let d = null;
  try { d = await abrufen("/api/gesamtsicht"); } catch (e) { d = null; }
  if (nr !== wechselNr) return;
  const liste = d?.projekte || projekte.map(p => ({ ...p, fuer_dich: p.fuer_dich ?? p.fragen, fortschritt: null }));
  if (!liste.length) { m.append(el("div", { class: "leer" }, t("kz_keine"))); return; }
  m.append(el("div", { class: "kz-karten" }, liste.map(kzKarte)));
}
function kzKarte(p) {
  const f = p.fortschritt, ms = p.meilensteine || [], vor = projekte.find(x => x.uid === p.uid) || p;
  const zeile1 = !f ? (vor.fern ? t("kz_fern") : null)
    : !ms.length ? t("kz_ms_keiner")
    : f.gesamt && f.fertig === f.gesamt ? t(ms.length === 1 ? "kz_ms1_alle" : "kz_ms_n_alle", { m: ms[0], n: ms.length, b: f.gesamt })
    : t(ms.length === 1 ? "kz_ms1" : "kz_ms_n", { m: ms[0], n: ms.length, a: f.fertig, b: f.gesamt });
  const bereit = f && f.gesamt > 0 && f.fertig === f.gesamt;
  const prog = !f ? null : bereit ? t("kz_bereit") : f.p50 ? t("kz_fertig_etwa", { d: datumKurz(f.p50) }) + (f.verzug_tage > 0 ? t("kz_spaeter", { n: f.verzug_tage }) : "") : null;
  const wer = !f ? null : p.arbeiten ? t(p.arbeiten === 1 ? "kz_arbeitet1" : "kz_arbeiten", { n: p.arbeiten }) : t("kz_nichts_laeuft");
  const oeffnen = () => {
    if (p.uid === projekt) return zeige("start");
    if (vor.fern) { if (vor.online) window.open(vor.online, "_blank", "noopener"); else toast(t("pw_fern_ohne_link"), true); return; }
    try { localStorage.setItem(`amw-sicht:${p.uid}`, "start"); } catch (e) {}     /* aus der Gesamtsicht in den Leitstand des Projekts */
    projektWechseln(p.uid);
  };
  return el("button", { class: "kz-karte", type: "button", "data-uid": p.uid, onclick: oeffnen },
    el("div", { class: "kz-oben" }, el("i", { style: `background:${farbe(vor)}` }), el("b", {}, p.name, vor.fern ? " ↗" : ""),
      p.fuer_dich ? el("span", { class: "kz-zahl" }, t("kz_fuer_dich", { n: p.fuer_dich })) : null),
    zeile1 ? el("div", { class: "kz-zl" }, zeile1) : null,
    f && f.gesamt ? el("div", { class: "kz-balken" }, el("i", { style: `width:${f.prozent}%` })) : null,
    prog || wer ? el("div", { class: "kz-zl" }, [prog, wer].filter(Boolean).join(" · ")) : null);
}

/* Suche beim Tippen: Treffer unter dem Feld, gruppiert „In <Projekt>“ / „Andere Projekte“; leeres Feld: zuletzt gesucht.
   Enter öffnet die ganze Trefferliste wie bisher (suchen). */
const KZ_ZULETZT = 3;
let kzSuchNr = 0, kzAuswahl = -1;
const kzZuletzt = () => { try { return JSON.parse(localStorage.getItem("amw-zuletzt-gesucht") || "[]"); } catch (e) { return []; } };
function kzMerken(q) {
  const l = [q, ...kzZuletzt().filter(x => x.toLowerCase() !== q.toLowerCase())].slice(0, KZ_ZULETZT);
  try { localStorage.setItem("amw-zuletzt-gesucht", JSON.stringify(l)); } catch (e) {}
}
function kzZu() { $("#kz-treffer")?.remove(); kzAuswahl = -1; }
function kzKasten() {
  let k = $("#kz-treffer");
  if (!k) { k = el("div", { id: "kz-treffer", class: "kz-treffer", role: "listbox" }); document.body.append(k); }
  const r = $("#suche").getBoundingClientRect();
  k.style.top = Math.round(r.bottom + 6) + "px";
  if (window.matchMedia("(max-width: 760px)").matches) { k.style.left = "12px"; k.style.right = "12px"; k.style.width = ""; }
  else { k.style.right = Math.max(12, Math.round(window.innerWidth - r.right)) + "px"; k.style.left = ""; }
  return k;
}
const kzMark = (text, q) => {                              /* das Gesuchte fett – als Element, nie als HTML */
  const s = String(text || ""), i = q ? s.toLowerCase().indexOf(q.toLowerCase()) : -1;
  return i < 0 ? [s] : [s.slice(0, i), el("mark", {}, s.slice(i, i + q.length)), s.slice(i + q.length)];
};
const kzWort = z => z && TEXTE.de["kz_s_" + z] ? t("kz_s_" + z) : "";
function kzOeffnen(x, q) {
  kzMerken(q); kzZu();
  if (!x.projekt || x.projekt === projekt) return refOeffnen(x.ref, x.aufgabe);
  try { sessionStorage.setItem("amw-oeffnen", x.ref); } catch (e) {}            /* nach dem Wechsel öffnet die Seite das Ding */
  projektWechseln(x.projekt);
}
async function kzSuchen() {
  const q = $("#suche").value.trim(), k = kzKasten(), nr = ++kzSuchNr;
  if (q.length < 2) {
    const l = kzZuletzt();
    if (!l.length) return kzZu();
    k.replaceChildren(el("div", { class: "kz-gr" }, t("kz_zuletzt")), ...l.map(x => el("button", { class: "kz-tr", type: "button",
      onclick: () => { $("#suche").value = x; kzSuchen(); $("#suche").focus(); } }, el("span", { class: "ref" }, "⌕"), el("span", {}, x))));
    return;
  }
  let l;
  try { l = await abrufen("/api/suche?alle=1&q=" + encodeURIComponent(q)); } catch (e) { if (nr === kzSuchNr) k.replaceChildren(el("div", { class: "kz-leer" }, String(e.message || e))); return; }
  if (nr !== kzSuchNr || !$("#kz-treffer")) return;                             /* inzwischen weitergetippt oder geschlossen */
  if (!l.length) { k.replaceChildren(el("div", { class: "kz-leer" }, t("nichts_gefunden"))); return; }
  const name = projekte.find(x => x.uid === projekt)?.name || "";
  const zeile = (x, fremd) => el("button", { class: "kz-tr", type: "button", role: "option", "data-ref": x.ref, onclick: () => kzOeffnen(x, q) },
    el("span", { class: "ref" }, ...kzMark(x.ref, q)), el("span", { class: "kz-titel" }, ...kzMark(x.titel, q)),
    el("span", { class: "kz-wo" }, [t("sa_" + x.art), kzWort(x.zusatz), fremd ? x.projekt_name : ""].filter(Boolean).join(" · ")));
  const eigen = l.filter(x => !x.projekt), andere = l.filter(x => x.projekt);
  k.replaceChildren(...(eigen.length ? [el("div", { class: "kz-gr" }, t("kz_in", { x: name })), ...eigen.slice(0, 12).map(x => zeile(x, false))] : []),
    ...(andere.length ? [el("div", { class: "kz-gr" }, t("kz_andere")), ...andere.slice(0, 8).map(x => zeile(x, true))] : []));
  kzAuswahl = -1;
}
(() => {
  const s = $("#suche");
  let warte = null;
  s.addEventListener("input", () => { clearTimeout(warte); warte = setTimeout(kzSuchen, 180); });
  s.addEventListener("focus", () => kzSuchen());
  s.addEventListener("keydown", e => {
    const zeilen = [...document.querySelectorAll("#kz-treffer .kz-tr")];
    if (e.key === "Escape") { kzZu(); s.blur(); return; }
    if ((e.key === "ArrowDown" || e.key === "ArrowUp") && zeilen.length) {
      e.preventDefault(); kzAuswahl = (kzAuswahl + (e.key === "ArrowDown" ? 1 : -1) + zeilen.length) % zeilen.length;
      zeilen.forEach((z, i) => z.classList.toggle("an", i === kzAuswahl)); zeilen[kzAuswahl].scrollIntoView({ block: "nearest" }); return;
    }
    if (e.key === "Enter" && kzAuswahl >= 0 && zeilen[kzAuswahl]) { e.preventDefault(); e.stopImmediatePropagation(); zeilen[kzAuswahl].click(); return; }
    if (e.key === "Enter" && s.value.trim().length > 1) { kzMerken(s.value.trim()); kzZu(); }   /* die ganze Liste (suchen) */
  });
  document.addEventListener("click", e => { if (!e.target.closest("#kz-treffer, #suche")) kzZu(); });
  window.addEventListener("resize", () => { if ($("#kz-treffer")) kzKasten(); });
})();
/* nach einem Wechsel aus der Suche: das gefundene Ding im neuen Projekt öffnen */
async function kzNachWechsel() {
  let ref = null; try { ref = sessionStorage.getItem("amw-oeffnen"); sessionStorage.removeItem("amw-oeffnen"); } catch (e) {}
  if (ref) await refOeffnen(ref);
}

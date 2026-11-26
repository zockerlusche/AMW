/* --- Kopf, Navigation ---------------------------------------------------------------------- */
async function kopfAktualisieren() {                    /* A1907: Kopfzeile immer; wer darauf wartet (Startseite, Takt), nur ohne Wechsel */
  const nr = wechselNr;
  await kopfLaden();
  if (nr !== wechselNr) return veraltet();
}
async function kopfLaden() {
  try {
    const d = await abrufen("/api/start"); zustand.start = d; zustand.startFehler = null;
    if (!spracheGewaehlt && ["de", "en"].includes(d.sprache_vorgabe) && d.sprache_vorgabe !== sprache) {   /* Vorgabe der Installation */
      spracheGewaehlt = true; sprache = d.sprache_vorgabe; feste_texte(); if (zustand.sicht) zeige(zustand.sicht, true); }   /* A1907: neu zeichnen, kein Wechsel */
    const wv = d.online?.web_version;
    $("#version").textContent = d.version ? `v${d.version}` + (wv && wv !== d.version ? ` · Web v${wv}` : "") : "";
    const extra = d.agenten.filter(a => a.soll !== "an" && a.zustand === "aktiv").length;     /* laufen, ohne zu sollen */
    const sp = d.speicher.frei;
    $("#signale").replaceChildren(...[
      d.online ? (d.online.pc_frisch && !d.online.briefkasten ? null : el("span", { class: "signal" }, el("span", { class: "punkt " + (d.online.pc_frisch ? "gruen" : "bernstein") }),
        t(d.online.pc_frisch ? "s_pc" : "s_pc_weg", { x: seit(d.online.pc_gesehen_utc) }) + (d.online.briefkasten ? " · " + t("s_briefkasten", { n: d.online.briefkasten }) : "")))
        : (() => { const [f, x] = dienstLage(d); return f === "gruen" ? null : el("span", { class: "signal", title: pcHinweis() },
            el("span", { class: "punkt " + f }), t({ gruen: "s_dienst", bernstein: "s_dienst", rot: "s_dienst_stoerung", "": "s_dienst_aus" }[f])); })(),
      /* A2014 (Kleinprobe A2010, D1429): keine zweite Statusleiste – Agenten und Speicher stehen im Leitstand (Ressourcen); hier nur,
         was vom Normalfall abweicht */
      extra ? el("span", { class: "signal" }, el("span", { class: "punkt bernstein" }), t("s_extra", { n: extra })) : null,
      sp != null && sp < 8 ? el("span", { class: "signal", title: pcHinweis() }, el("span", { class: "punkt bernstein" }), t("s_speicher", { n: Math.round(sp) })) : null,
      /* Steuern geschieht in der Steuerung (Leitstand, unter den Agenten); hier steht nur, was vom Normalfall abweicht – Klick führt hin */
      d.halt.length ? el("span", { class: "signal knopflich", title: t("ls_hin"), onclick: zurSteuerung }, el("span", { class: "punkt rot" }), t("halt_an")) : null,
      d.schirm?.frei ? el("span", { class: "signal knopflich", title: [d.schirm.grund, t("ls_hin")].filter(Boolean).join(" · "), onclick: zurSteuerung },
        el("span", { class: "punkt bernstein" }), t("s_schirm_frei")) : null,
      (d.ende || []).length ? el("span", { class: "signal knopflich", title: t("ls_hin"), onclick: zurSteuerung }, el("span", { class: "punkt bernstein" }),
        t("s_ende", { n: d.ende.length, x: zeit(d.ende[0].bis_utc) })) : null,
    ].filter(Boolean));
    for (const z of document.querySelectorAll("[data-zahl]")) {
      const n = d.zaehler[z.dataset.zahl] ?? ""; z.textContent = n || ""; z.classList.toggle("heiss", ["fragen", "projektweg"].includes(z.dataset.zahl) && n > 0);
    }
  } catch (e) {
    zustand.startFehler = String(e.message || e);      /* A1998: die Startseite zeigt den Grund (z. B. „Noch kein Abgleich …“) */
    if (e.leer) { $("#signale").replaceChildren(); return; }   /* P552: kein Abgleich ist kein Ausfall – ein Status, im Inhalt */
    $("#signale").replaceChildren(el("span", { class: "signal" }, el("span", { class: "punkt rot" }), t("s_dienst_weg")));
  }
}
/* ruhig = Selbst-Aktualisierung: keine Einblend-Animation, Scrollposition bleibt (sonst „springen“ die Kacheln) */
let ruhig = false;
/* Menü nach TH156 (A2018): Leitstand · Projektweg · Fragen (bis „Für dich“) · Wissen · Betrieb · Einstellungen. Was früher ein eigener
   Punkt war, gehört jetzt zu einem dieser Bereiche; jede alte Adresse (#planung, #themen, #nachrichten, #arbeit …) bleibt gültig. */
const BEREICH = { planung: "projektweg", themen: "projektweg", arbeit: "projektweg", verlauf: "projektweg", nachrichten: "wissen", teamchat: "wissen",
  runde: "wissen", dokumente: "wissen", ergebnisse: "wissen", releases: "projektweg", termine: "betrieb" };   /* #ergebnisse: alte Adresse (A2012) */   /* A2012: Versionshinweise beim Projektweg (TH156) */
/* Die Reihe eines Bereichs steht im Seitenkopf jeder seiner Seiten (rahmen): so ist alles erreichbar, was im Menü keinen Punkt mehr hat.
   Wissen hat seine Reiter schon auf der Seite – nur die Nachrichten bekommen sie hier. */
const REIHEN = { projektweg: [["projektweg", "n_projektweg"], ["themen", "n_themen"], ["planung", "n_planung"], ["releases", "n_releases"]],
  betrieb: [["betrieb", "n_betrieb"], ["termine", "pr_termine"]] };
const REIHE_AN = { arbeit: "planung", verlauf: "planung" };
function bereichReihe(sicht) {
  if (["nachrichten", "teamchat", "runde"].includes(sicht)) { const r = wissenReiter(sicht === "teamchat" ? "teamchat" : "nachrichten"); r.className = "bereich-reihe"; return r; }
  const teile = REIHEN[BEREICH[sicht] || sicht];
  return teile ? el("div", { class: "bereich-reihe" }, teile.map(([s, n]) => el("button", { type: "button", class: s === (REIHE_AN[sicht] || sicht) ? "an" : "",
    "data-s": s, onclick: () => zeige(s) }, t(n)))) : null;
}
function bereichReiter(teile, aktiv, ...rechts) {
  return el("div", { class: "reiter bereich-reiter" }, teile.map(([k, text, tun]) => el("button", { type: "button", class: k === aktiv ? "an" : "", onclick: tun }, text)), ...rechts);
}
function planReiter(aktiv, n = {}) {
  const plan = k => () => { zustand.planReiter = k; zeige("planung"); };
  return bereichReiter([...(n.meilensteine ? [["meilensteine", t("pm_meilensteine"), plan("meilensteine")], ["pakete", t("pm_pakete"), plan("pakete")]] : []),   /* A1950 */
    ["zeitleiste", t("pr_zeitleiste"), plan("zeitleiste")], ["arbeit", t("n_aufgaben"), () => zeige("arbeit")],
    ["verlauf", t("n_verlauf"), () => zeige("verlauf")], ["leitbild", t("pr_leitbild"), plan("leitbild")],
    ["risiken", t("pr_risiken") + (n.risiken !== undefined ? ` (${n.risiken})` : ""), plan("risiken")],
    ["check", t("pr_check") + (n.check ? ` (${n.check})` : ""), plan("check")], ["protokoll", t("pr_protokoll"), plan("protokoll")]], aktiv);
}
/* A2012 (Kleinprobe A2008, TL #33784): Wissen hat vier Reiter – Beschlüsse (mit Regeln, Wortlaut, Notizen als Filter), Dokumente,
   Nachrichten, Mitlesen (nur lesen). Themen gehören zum Projektweg, die Versionshinweise auch. */
const WISSEN_FILTER = ["beschluesse", "regeln", "wortlaut", "notizen"];
function wissenReiter(aktiv) {
  const an = WISSEN_FILTER.includes(aktiv) ? "beschluesse" : aktiv;
  return bereichReiter([["beschluesse", t("rb_beschluesse"), () => { if (!WISSEN_FILTER.includes(zustand.wissenReiter)) zustand.wissenReiter = "beschluesse"; zeige("wissen"); }],
    ["dokumente", t("n_dokumente"), () => zeige("dokumente")], ["nachrichten", t("n_nachrichten"), () => zeige("nachrichten")],
    ["teamchat", t("n_teamchat"), () => zeige("teamchat")]], an);
}
function zeige(sicht, still = false) {
  if (sicht === "steuerung") return zurSteuerung();                     /* A2018: Adresse #steuerung */
  if (PW_ADRESSEN[sicht]) return pwAdresse(sicht);                      /* A2011: #reihenfolge, #zeitplan, #gesamtplan → Reiter im Projektweg */
  if (!still) { wechselNr++; seitenNr++; }                              /* A1907: was die vorige Seite noch lädt, zeichnet nicht mehr */
  ruhig = still;
  const pos = [$("#inhalt").scrollTop, window.scrollY];
  const offen = still && zustand.sicht === sicht        /* still neu gezeichnet: aufgeklappte Abschnitte bleiben offen */
    ? new Set([...$("#inhalt").querySelectorAll("details[open] > summary")].map(s => s.textContent)) : null;
  zustand.sicht = sicht;
  gezeichnet.sicht = sicht; gezeichnet.stempel = stempel(sicht); gezeichnet.um = Date.now();
  $("#neuer-stand")?.remove();
  const bereich = BEREICH[sicht] || sicht;               /* A1657: Unterseiten gehören zu einem Menüpunkt */
  for (const a of document.querySelectorAll("nav a[data-sicht]")) a.classList.toggle("an", a.dataset.sicht === bereich);
  $("#mehr")?.classList.toggle("an", !!document.querySelector(`nav a.im-mehr[data-sicht="${bereich}"]`));
  try { localStorage.setItem(ablage("amw-sicht"), sicht); } catch (e) {}
  if (location.hash !== "#" + sicht) history[still ? "replaceState" : "pushState"](null, "", "#" + sicht);   /* Zurück-Knopf */
  kzKnopf();                                                            /* A2014: „Alle Projekte“ im Kopf nur in der Gesamtsicht */
  const fertig = ({ projekte: sichtProjekte, start: sichtStart, nachrichten: sichtNachrichten, fragen: sichtFragen, planung: sichtPlanung, projektweg: sichtProjektweg, verlauf: sichtVerlauf, arbeit: sichtArbeit, teamchat: sichtTeamchat, runde: sichtRunde, wissen: sichtWissen, themen: sichtThemen, termine: sichtTermine, dokumente: sichtDokumente, ergebnisse: sichtDokumente, betrieb: sichtBetrieb, releases: sichtReleases, einstellungen: sichtEinstellungen }[sicht] || sichtStart)();
  if (!still) { $("#inhalt").scrollTop = 0; return fertig; }
  return Promise.resolve(fertig).then(() => {
    if (offen?.size) for (const s of $("#inhalt").querySelectorAll("details > summary")) if (offen.has(s.textContent)) s.parentElement.open = true;
    $("#inhalt").scrollTop = pos[0]; window.scrollTo(0, pos[1]); });
}
/* Seiten aktualisieren sich selbst – am PC, online und am Handy:
   - nach einer eigenen Aktion (jedes schicken) gleich danach,
   - bei Änderungen von außen (Agenten, Brücke, Handy): /api/start bringt je Sicht einen Stempel (jüngste Änderung und Anzahl
     ihrer Tabellen); ändert er sich, wird die offene Sicht still neu gezeichnet. Start und Betrieb laden ohnehin im Takt.
   Nie, wenn dabei etwas verloren ginge (Tippen, ungespeicherte Eingabe, markierter Text, offener Dialog) – dann steht unten
   „Neuer Stand“ mit Knopf. Online kommt die Ansicht der Sicht evtl. erst eine Runde nach dem Stempel: einmal nachladen. */
const gezeichnet = { sicht: null, stempel: null, um: 0, nachlauf: false };
const stempel = s => s === "start" || s === "betrieb" || s === "einstellungen" ? null
  : (zustand.start?.stand?.[s] ?? null) === null ? null : zustand.start.stand[s] + "|" + (zustand.start.online?.briefkasten ?? "");
function ungespeichert() {
  for (const x of $("#inhalt").querySelectorAll("textarea, input, select")) {
    if (x.disabled || x.dataset.filter) continue;     /* gesperrt = schon abgeschickt; Filter sind keine Eingabe (A1844, nur Nachrichten) */
    if (x.tagName === "SELECT") { if ([...x.options].some(o => o.selected !== o.defaultSelected)) return true; }
    else if (x.type === "checkbox" || x.type === "radio") { if (x.checked !== x.defaultChecked) return true; }
    else if (!["button", "submit", "file", "hidden"].includes(x.type) && x.value !== x.defaultValue) return true;
  }
  return false;
}
function stoerfrei(dialogErlaubt = false) {
  const tippt = ["TEXTAREA", "INPUT", "SELECT"].includes(document.activeElement?.tagName);
  const markiert = String(window.getSelection?.() || "").trim() !== "";
  return !document.hidden && !tippt && !markiert && (dialogErlaubt || !document.querySelector(".dialog-hg")) && !ungespeichert();
}
function neuerStandLeiste() {
  if (document.getElementById("neuer-stand")) return;
  const k = el("button", { class: "knopf haupt", type: "button", onclick: () => zeige(zustand.sicht, true) }, t("neuer_stand_knopf"));
  document.body.append(el("div", { class: "karte neuer-stand", id: "neuer-stand", role: "status" }, el("span", { class: "leise", style: "flex:1;min-width:0" }, t("neuer_stand")), k));
}
function frischZeichnen(dialogErlaubt = false) {
  if (haeltGedrueckt()) { setTimeout(() => frischZeichnen(dialogErlaubt), 200); return; }
  if (zustand.sicht === "einstellungen") return;
  if (stoerfrei(dialogErlaubt)) zeige(zustand.sicht, true); else neuerStandLeiste();
}
function nachAktion() {             /* mehrere schicken hintereinander (z. B. Hochladen in Teilen): nur das letzte zählt */
  const z = gezeichnet.aktion = Date.now();
  setTimeout(async () => {
    if (gezeichnet.aktion !== z) return;
    await kopfAktualisieren();
    if (gezeichnet.aktion !== z || gezeichnet.um >= z) return;           /* die Aktion hat schon selbst neu gezeichnet (auch in derselben Millisekunde) */
    frischZeichnen(true);
  }, 900);
}
function standPruefen() {
  const s = zustand.sicht, neu = stempel(s);
  if (neu === null || gezeichnet.sicht !== s) return;
  if (neu === gezeichnet.stempel && !gezeichnet.nachlauf) return;
  gezeichnet.nachlauf = !!API && neu !== gezeichnet.stempel;
  frischZeichnen();
}
/* Klasse „still“ erst hier setzen, im selben Schritt wie das Ersetzen – sonst liefe die Animation am alten Inhalt */
function rahmen(titel, ...rest) {
  wechselNr++;                                           /* A1907: neu gezeichnet (auch ein Reiter derselben Seite) – Altes zeichnet nicht dazu */
  const m = $("#inhalt"); m.classList.toggle("still", ruhig); m.classList.remove("geteilt-seite");
  const gleich = kopfStand.sicht === zustand.sicht;            /* dieselbe Seite neu gezeichnet: Untermenüs bleiben waagrecht, wo sie waren */
  kopfStand.lage = gleich ? Object.fromEntries([...m.querySelectorAll(":scope > .seitenkopf > *")].map(e => [e.classList[0], (e.querySelector(".reiter-zeile") || e).scrollLeft])) : {};
  kopfStand.sicht = zustand.sicht; kopfStand.weg = 0;
  const k = el("div", { class: "seitenkopf" }, el("div", { class: "kopf" }, el("h1", {}, titel), ...rest)), reihe = bereichReihe(zustand.sicht);
  if (reihe) k.append(reihe);                            /* läuft mit dem Titel hinaus – fest bleiben nur die Reiter der Seite */
  m.replaceChildren(k); if (reihe) reihe.querySelector(".an")?.scrollIntoView({ block: "nearest", inline: "nearest" }); kopfStand.groesse.disconnect(); kopfStand.groesse.observe(k); return m;
}
/* Liste links, Inhalt rechts (A1628) – wie im Mail-Programm: am PC füllen beide Spalten das Fenster unter dem Kopf und
   scrollen je für sich; die Seite selbst scrollt dann nicht, die Liste bleibt stehen, wenn man rechts liest. Am Handy
   (eine Spalte: Liste → Inhalt mit Zurück) bleibt alles, wie es war. Rückgabe: passen() – nach dem Neuzeichnen aufrufen. */
const BREIT = matchMedia("(min-width: 761px)");
function geteilt(raster) {
  const m = $("#inhalt");
  raster.classList.add("geteilt");
  const ro = new ResizeObserver(() => passen());
  const passen = () => {
    if (!raster.isConnected) { ro.disconnect(); BREIT.removeEventListener("change", passen); return; }
    m.classList.toggle("geteilt-seite", BREIT.matches);
    if (!BREIT.matches) { raster.style.height = ""; return; }
    const oben = raster.getBoundingClientRect().top - m.getBoundingClientRect().top + m.scrollTop;
    /* Untergrenze 240 px: seit der Bereichs-Reihe (A2018) steht die Liste tiefer – bei 640 px Fensterhöhe passt sie so noch ganz (L3944) */
    raster.style.height = Math.max(240, m.clientHeight - oben - parseFloat(getComputedStyle(m).paddingBottom || 0)) + "px";
  };
  ro.observe(m);
  for (let x = raster.previousElementSibling; x; x = x.previousElementSibling) ro.observe(x);   /* Kopf, Filter: ändern die Höhe darüber */
  BREIT.addEventListener("change", passen);
  requestAnimationFrame(passen);
  return passen;
}
/* Fester Seitenkopf: rahmen() legt ihn an; jedes Untermenü, das eine Seite direkt darunter hängt (Reiter, Filter, Sprungmarken),
   wandert von selbst hinein – keine Seite braucht dafür eigenen Code. Beim Scrollen läuft die Titelzeile hinaus (top negativ),
   die Untermenüs bleiben stehen; Sprungziele landen darunter (scroll-padding). */
const UNTERMENUE = ".reiter, .vl-filter, .dk-arten, .dk-filter, .sprung";
/* Am Handy wischbare Untermenüs: ein Verlauf an der Kante zeigt, dass es dort weitergeht (sonst endet ein Reiter mitten im Wort) */
function kante(w) {
  const rest = w.scrollWidth - w.clientWidth - w.scrollLeft;
  w.classList.toggle("weiter-r", rest > 2);
  w.classList.toggle("weiter-l", w.scrollLeft > 2);
}
const kopfStand = { sicht: null, lage: {}, weg: 0, groesse: new ResizeObserver(() => seitenkopf()) };
function seitenkopf() {
  const m = $("#inhalt"), k = m.firstElementChild;
  if (!k?.classList.contains("seitenkopf")) return;
  for (let n; (n = k.nextElementSibling) && n.matches(UNTERMENUE);) {
    k.append(n);
    let w = n;                                   /* w = was sich am Handy waagrecht wischen lässt */
    if (n.classList.contains("reiter")) { w = el("div", { class: "reiter-zeile" }); w.append(...n.querySelectorAll(":scope > button")); n.prepend(w); }
    const an = w.querySelector("button.an");
    if (kopfStand.lage[n.classList[0]]) w.scrollLeft = kopfStand.lage[n.classList[0]];
    else if (an && w.scrollWidth > w.clientWidth) w.scrollLeft += an.getBoundingClientRect().left - w.getBoundingClientRect().left - (w.clientWidth - an.offsetWidth) / 2;
    w.addEventListener("scroll", () => kante(w), { passive: true });
  }
  for (const w of k.querySelectorAll(":scope > .reiter > .reiter-zeile, :scope > :is(.vl-filter, .dk-arten, .dk-filter, .sprung)")) kante(w);
  const erstes = k.querySelector(`:scope > :is(${UNTERMENUE})`);
  k.classList.toggle("mit-menue", !!erstes);
  kopfStand.weg = erstes ? Math.max(0, erstes.offsetTop - 8) : 0;        /* so viel läuft oben hinaus: Titelzeile samt Abstand */
  k.style.top = erstes ? -(kopfStand.weg + parseFloat(getComputedStyle(m).paddingTop)) + "px" : "";   /* top zählt ab dem Innenabstand von main */
  m.style.scrollPaddingTop = erstes ? k.offsetHeight - kopfStand.weg + 10 + "px" : "";
  m.style.setProperty("--kopf", (erstes ? k.offsetHeight - kopfStand.weg : 0) + "px");      /* was oben stehen bleibt (A1628) */
  k.classList.toggle("fest", !!erstes && m.scrollTop > kopfStand.weg);
}
new MutationObserver(seitenkopf).observe($("#inhalt"), { childList: true });
$("#inhalt").addEventListener("scroll", () => { const k = $("#inhalt").firstElementChild;
  if (k?.classList.contains("mit-menue")) k.classList.toggle("fest", $("#inhalt").scrollTop > kopfStand.weg); }, { passive: true });
/* Sprungmarken aus den Abschnitten (h2) einer langen Seite – sie landen wie jedes Untermenü im festen Seitenkopf */
function sprungmarken(m) {
  const marken = [...m.querySelectorAll(":scope > h2")].map(h => el("a", { onclick: () => h.scrollIntoView({ behavior: "smooth", block: "start" }) },
    [...h.childNodes].filter(n => n.nodeType === Node.TEXT_NODE).map(n => n.textContent).join("").trim() || h.textContent));
  if (marken.length > 2) m.querySelector(":scope > .seitenkopf")?.after(el("div", { class: "sprung" }, marken));
}


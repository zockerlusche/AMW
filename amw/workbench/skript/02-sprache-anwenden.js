/* --- Sprache anwenden ---------------------------------------------------------------------- */
function feste_texte() {
  document.documentElement.lang = sprache;
  for (const e of document.querySelectorAll("[data-t]")) e.textContent = t(e.dataset.t);
  for (const e of document.querySelectorAll("[data-t-ph]")) e.placeholder = t(e.dataset.tPh);
  // Untertitel neben dem Logo: je Wort eine Zeile, der Anfangsbuchstabe hervorgehoben (A·M·W)
  document.getElementById("marke-text").replaceChildren(...t("marke").split(" ").flatMap((w, n) =>
    [...(n ? [document.createElement("br")] : []), Object.assign(document.createElement("i"), { textContent: w[0] }), w.slice(1)]));
}
function sprache_setzen(s) {
  sprache = s; spracheGewaehlt = true; try { localStorage.setItem("amw-sprache", s); } catch (e) {}
  feste_texte(); kopfAktualisieren(); zeige(zustand.sicht);
  const p = projekte.find(x => x.uid === projekt) || projekte.find(x => x.aktiv); if (p) projektwahlZeigen(p);
}


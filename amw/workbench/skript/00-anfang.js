"use strict";
const TOKEN = "__AMW_TOKEN__";
/* Online (doc/online.md): API = "api.php?weg=", sonst leer = lokale Workbench am PC */
const API = "__AMW_API__".startsWith("__") ? "" : "__AMW_API__";
/* Projekt der Ansicht (uid): jede Anfrage trägt es; Umschalten ändert nur die Ansicht, kein Projekt hält an */
let projekt = null, projekte = [];
const ziel = (weg, p = projekt) => API ? API + encodeURIComponent(weg) + (p ? "&projekt=" + encodeURIComponent(p) : "")
  : p ? weg + (weg.includes("?") ? "&" : "?") + "projekt=" + encodeURIComponent(p) : weg;
/* Merken je Projekt (Sicht, letzter Besuch); ohne Eintrag gilt der bisherige Wert ohne Projekt */
const ablage = k => projekt ? `${k}:${projekt}` : k;
/* Absender in der Anzeige: Meldungen der Workbench selbst tragen in der Datenbank die Kennung „AMW“ – verwechselbar mit dem
   Projekt AMW; gezeigt wird „System“ (B2691). Die Kennung selbst bleibt. */
const wer = k => k === "AMW" ? t("absender_system") : k;
const gemerkt = k => { try { return localStorage.getItem(ablage(k)) ?? localStorage.getItem(k); } catch (e) { return null; } };
const $ = (s, w = document) => w.querySelector(s);


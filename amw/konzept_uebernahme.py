"""Konzept-Übernahme (A1994, TH160; verallgemeinert A1886/K11): ein Konzept als Markdown halbautomatisch in Themen-Entwürfe.

Für jedes Projekt: der Lead (oder der Mensch, der Co-Entwickler) nennt eine Markdown-Datei im eigenen Projektordner – am besten
eine Kopie. Die Gliederung wird zu Themen (Überschrift der Gliederungsebene → Name), der Abschnitt darunter (mit allen
Unterüberschriften) zur ersten Fassung. Freigegeben wird nichts: Fassungen eines Agenten warten auf den Menschen wie jede
Vorlage; ein Gegenleser oder Planer wird nicht angestoßen (das Original stammt aus dem Projekt, Kosten entstehen erst mit der
Arbeit daran). Kleinstes Modell (W2431): vorhandene Tabellen thema / thema_fassung / dokument / plan_ereignis, kein Schema.

Halbautomatisch: ohne --anlegen nur die Vorschau (nichts geschrieben). Das Original bleibt unverändert (Prüfsumme vorher und
nachher) und lesbar – es wird zusätzlich als Dokument (Art quelle) abgelegt und an jedes neue Thema gehängt.

Zählprobe (Verfahren wie A1926: vorher/nachher zählen, bestanden = gleich): im Original und in den Themen, wie sie danach in der
Datenbank stehen, plus die nicht zugeordneten Stellen – Zeilen mit Text, Überschriften (mit ihren Nummern), Kennungen (A12, TH3,
§1.5 …) und Links. Jede nicht zuordenbare Stelle steht mit Zeilen und Grund in der Ausgabe.
"""
import collections
import hashlib
import json
import os
import re

from . import db, kern, themen

ART = "konzept_uebernommen"
ENDUNGEN = (".md", ".markdown")
UEBERSCHRIFT = re.compile(r"^(#{1,6})[ \t]+(.*?)(?:[ \t]+#+)?[ \t]*$")
ZAUN = re.compile(r"^[ \t]{0,3}(```|~~~)")
KENNUNG = re.compile(r"(?<![\w§])(?:[A-ZÄÖÜ]{1,4}\d+(?:\.\d+)*|§[ \t]?\d+(?:\.\d+)*)(?!\w)")
LINK = re.compile(r"\[[^\]\n]*\]\([^)\n]*\)|https?://[^\s)>\]]+")
NAME_MAX = 120


def _zeilen_ausser_zaun(text):
    """[(nr ab 1, zeile, ist_ueberschrift_oder_None)] – Überschriften nur außerhalb von Code-Blöcken."""
    aus, zaun = [], None
    for i, z in enumerate(text.splitlines(), 1):
        m = ZAUN.match(z)
        if m:
            zaun = m.group(1) if zaun is None else (None if m.group(1) == zaun else zaun)
            aus.append((i, z, None))
            continue
        u = UEBERSCHRIFT.match(z) if zaun is None else None
        aus.append((i, z, (len(u.group(1)), " ".join(u.group(2).split())) if u else None))
    return aus


def zaehlen(texte):
    """Zählprobe über Texte: {"zeilen": Zeilen mit Text, "ueberschriften": Counter der Überschriften (Text mit Nummer),
    "kennungen": Counter, "links": Counter}."""
    z = {"zeilen": 0, "ueberschriften": collections.Counter(), "kennungen": collections.Counter(), "links": collections.Counter()}
    for t in texte:
        for _, zeile, u in _zeilen_ausser_zaun(t):
            if zeile.strip():
                z["zeilen"] += 1
            if u:
                z["ueberschriften"][u[1]] += 1
            z["kennungen"].update(m.group(0).replace(" ", "").replace("\t", "") for m in KENNUNG.finditer(zeile))
            z["links"].update(LINK.findall(zeile))
    return z


def _summe(*zs):
    aus = zaehlen([])
    for z in zs:
        aus["zeilen"] += z["zeilen"]
        for k in ("ueberschriften", "kennungen", "links"):
            aus[k].update(z[k])
    return aus


def vergleichen(original, nachher):
    """[(was, original, nachher, fehlt, zuviel)] – leer = bestanden."""
    diff = []
    if original["zeilen"] != nachher["zeilen"]:
        diff.append(("Zeilen mit Text", original["zeilen"], nachher["zeilen"], [], []))
    for k, name in (("ueberschriften", "Überschriften"), ("kennungen", "Kennungen"), ("links", "Links")):
        a, b = original[k], nachher[k]
        if a != b:
            diff.append((name, sum(a.values()), sum(b.values()), sorted((a - b).elements()), sorted((b - a).elements())))
    return diff


def ebene_finden(kopf):
    """Gliederungsebene: die oberste Stufe – steht dort genau eine Überschrift (der Titel) und gibt es tiefere, die nächste."""
    stufen = [s for s, _ in kopf]
    if not stufen:
        return None
    oben = min(stufen)
    tiefer = [s for s in stufen if s > oben]
    return min(tiefer) if stufen.count(oben) == 1 and tiefer else oben


def gliedern(text, ebene=None, vorhanden=()):
    """Plan der Übernahme: {"ebene", "themen": [{"name", "text", "von", "bis"}], "rest": [{"von", "bis", "grund", "text"}]}.
    vorhanden: Namen von Themen, die es im Projekt schon gibt (klein geschrieben) – die werden nicht überschrieben."""
    zeilen = _zeilen_ausser_zaun(text)
    kopf = [u for _, _, u in zeilen if u]
    if not kopf:
        raise kern.AmwFehler("Keine Überschriften gefunden – die Gliederung (# …, ## …) wird zu Themen")
    ebene = int(ebene) if ebene else (ebene_finden(kopf) or 1)
    if not 1 <= ebene <= 6:
        raise kern.AmwFehler("--ebene: 1 bis 6")
    if not any(s == ebene for s, _ in kopf):
        raise kern.AmwFehler(f"Keine Überschrift der Ebene {ebene} ({'#' * ebene} …) – andere Ebene wählen")
    titel_da = sum(1 for s, _ in kopf if s < ebene) == 1
    bloecke, akt = [], None
    for nr, zeile, u in zeilen:
        if u and u[0] <= ebene:
            akt = {"von": nr, "bis": nr, "zeilen": [zeile], "kopf": u}
            bloecke.append(akt)
            continue
        if akt is None:
            akt = {"von": nr, "bis": nr, "zeilen": [], "kopf": None}
            bloecke.append(akt)
        akt["zeilen"].append(zeile)
        akt["bis"] = nr
    themen_, rest, namen = [], [], set(x.lower() for x in vorhanden)

    def _rest(b, grund):
        t = "\n".join(b["zeilen"]).strip("\n")
        if t.strip():
            rest.append({"von": b["von"], "bis": b["bis"], "grund": grund, "text": t})

    for b in bloecke:
        u = b["kopf"]
        if not u:
            _rest(b, "Text vor dem ersten Abschnitt")
            continue
        if u[0] < ebene:
            _rest(b, "Titel des Dokuments" if titel_da else "Überschrift über der Gliederungsebene")
            continue
        name = u[1]
        if not name:
            _rest(b, "Überschrift ohne Text")
        elif len(name) > NAME_MAX:
            _rest(b, f"Name länger als {NAME_MAX} Zeichen – Überschrift in der Kopie kürzen")
        elif name.lower() in namen:
            _rest(b, f"Thema „{name}“ gibt es schon" + (" (doppelt im Dokument)" if any(t["name"].lower() == name.lower()
                                                                                         for t in themen_) else " im Projekt"))
        else:
            namen.add(name.lower())
            themen_.append({"name": name, "kopf": b["zeilen"][0], "text": "\n".join(b["zeilen"][1:]).strip("\n"),
                            "von": b["von"], "bis": b["bis"]})
    return {"ebene": ebene, "themen": themen_, "rest": rest}


def _themen_text(name, text, ebene):
    """So steht ein Thema in der Zählprobe: die Überschrift (Name) und der Text der Fassung."""
    return f"{'#' * ebene} {name}\n{text}"


def _datei(con, pid, pfad):
    """Absoluter Pfad – nur eine Markdown-Datei im Projektordner dieses Projekts."""
    ordner = kern.projekt_ordner(con, pid)
    if not ordner:
        raise kern.AmwFehler("Für dieses Projekt ist kein Projektordner eingetragen (amw projekt ordner) – die Datei muss dort liegen")
    p = os.path.realpath(os.path.abspath(pfad or ""))
    o = os.path.realpath(ordner)
    try:
        drinnen = os.path.normcase(os.path.commonpath([p, o])) == os.path.normcase(o)
    except ValueError:                                # anderes Laufwerk
        drinnen = False
    if not drinnen:
        raise kern.AmwFehler(f"{pfad} liegt nicht im Projektordner {ordner} – nur Konzepte des eigenen Projekts")
    if not os.path.isfile(p):
        raise kern.AmwFehler(f"Datei {pfad} gibt es nicht")
    if os.path.splitext(p)[1].lower() not in ENDUNGEN:
        raise kern.AmwFehler("Nur Markdown (.md, .markdown)")
    return p


def _lesen(p):
    with open(p, "rb") as f:
        roh = f.read()
    try:
        return roh, roh.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise kern.AmwFehler(f"{os.path.basename(p)} ist kein UTF-8 – als UTF-8 speichern") from None


def _darf(con, pid, von):
    if not (kern.ist_lead(con, pid, von) or kern.ist_co(con, pid, von)):
        raise kern.AmwFehler("Ein Konzept übernehmen dürfen der Lead, der Mensch und der Co-Entwickler des Projekts")


def uebernehmen(con, pid, von, pfad, ebene=None, anlegen=False):
    """Vorschau (anlegen=False, nichts geschrieben) oder Anlegen. Rückgabe {"datei", "sha256", "ebene", "themen":
    [{"id"?, "name", "von", "bis", "zeichen"}], "rest", "original", "nachher", "unterschiede", "bestanden", "unveraendert",
    "dokument"?, "bericht"?}."""
    _darf(con, pid, von)
    p = _datei(con, pid, pfad)
    roh, text = _lesen(p)
    sha = hashlib.sha256(roh).hexdigest()
    vorhanden = [r[0] for r in con.execute("SELECT name FROM thema WHERE projekt_id = ?", (pid,))]
    plan = gliedern(text, ebene, vorhanden)
    original = zaehlen([text])
    rest_z = zaehlen([r["text"] for r in plan["rest"]])
    aus = {"datei": p, "sha256": sha, "ebene": plan["ebene"], "rest": plan["rest"], "original": original, "angelegt": False,
           "themen": [{"name": t["name"], "von": t["von"], "bis": t["bis"], "zeichen": len(t["text"])} for t in plan["themen"]]}
    if not anlegen:
        nachher = _summe(zaehlen([_themen_text(t["name"], t["text"], plan["ebene"]) for t in plan["themen"]]), rest_z)
    else:
        if not plan["themen"]:
            raise kern.AmwFehler("Nichts anzulegen – keine neuen Themen (siehe nicht zugeordnet)")
        from . import dokumente
        did = dokumente.ablegen_inhalt(con, pid, von, roh, os.path.basename(p), titel=f"Konzept-Original {os.path.basename(p)}"[:200],
                                       art="quelle", notiz=f"A1994 Übernahme in Themen · sha256 {sha[:16]}")
        jetzt = db.jetzt()
        with db.schreiben(con):
            for t, a in zip(plan["themen"], aus["themen"]):
                if con.execute("SELECT 1 FROM thema WHERE projekt_id = ? AND name = ? COLLATE NOCASE", (pid, t["name"])).fetchone():
                    raise kern.AmwFehler(f"Thema „{t['name']}“ gibt es inzwischen – nichts angelegt, noch einmal")
                tid = db.einfuegen(con, "thema", projekt_id=pid, name=t["name"], pfleger=None, stil=0, angelegt_von=von,
                                   angelegt_utc=jetzt)
                a["id"] = tid
                if t["text"].strip():
                    db.einfuegen(con, "thema_fassung", thema_id=tid, nr=1, text=t["text"], von=von, zeit_utc=jetzt)
                    if von != kern.ENTWICKLER:      # wie thema pflegen: Vorlage eines Agenten → wartet auf den Menschen
                        themen._ereignis(con, pid, von, "vorgelegt", tid, fassung=1, quelle=f"D{did}", zeilen=f"{t['von']}-{t['bis']}")
                con.execute("INSERT OR IGNORE INTO thema_dokument (thema_id, dokument_id, von, zeit_utc) VALUES (?, ?, ?, ?)",
                            (tid, did, von, jetzt))
        aus["angelegt"], aus["dokument"] = True, did
        nachher = _summe(_aus_der_datenbank(con, pid, [a["id"] for a in aus["themen"]], plan["ebene"]), rest_z)
    aus["nachher"] = nachher
    aus["unterschiede"] = vergleichen(original, nachher)
    aus["bestanden"] = not aus["unterschiede"]
    aus["unveraendert"] = hashlib.sha256(_lesen(p)[0]).hexdigest() == sha
    if anlegen:
        from . import dokumente
        aus["bericht"] = dokumente.ablegen_inhalt(con, pid, von, bericht(aus).encode("utf-8"), f"konzept-uebernahme-{pid}.md",
                                                  titel=f"Konzept-Übernahme {os.path.basename(p)} – Zählprobe"[:200], art="bericht")
        with db.schreiben(con):
            db.einfuegen(con, "plan_ereignis", projekt_id=pid, zeit_utc=db.jetzt(), von=von, art=ART,
                         text=json.dumps({"datei": p, "sha256": sha, "ebene": plan["ebene"], "themen": [a["id"] for a in aus["themen"]],
                                          "original": did, "bericht": aus["bericht"], "bestanden": aus["bestanden"],
                                          "nicht_zugeordnet": len(plan["rest"]), "unveraendert": aus["unveraendert"]},
                                         ensure_ascii=False))
    return aus


def _aus_der_datenbank(con, pid, tids, ebene):
    texte = []
    for tid in tids:
        t = con.execute("SELECT name FROM thema WHERE id = ? AND projekt_id = ?", (tid, pid)).fetchone()
        f = con.execute("SELECT text FROM thema_fassung WHERE thema_id = ? ORDER BY nr DESC LIMIT 1", (tid,)).fetchone()
        texte.append(_themen_text(t["name"], f["text"] if f else "", ebene))
    return zaehlen(texte)


def zeilen(aus):
    """Ausgabe für die Befehlszeile (und der Kern des Berichts)."""
    o, n = aus["original"], aus["nachher"]
    z = [f"{'Angelegt' if aus['angelegt'] else 'Vorschau – nichts angelegt'}: {len(aus['themen'])} Themen aus "
         f"{os.path.basename(aus['datei'])} (Gliederung: Ebene {aus['ebene']}, {'#' * aus['ebene']} …)"]
    for t in aus["themen"]:
        z.append(f"  {('TH' + str(t['id'])) if t.get('id') else '+':<7} {t['name'][:80]}  · Zeilen {t['von']}–{t['bis']}"
                 + ("" if t["zeichen"] else " · ohne Text"))
    z.append(f"Nicht zugeordnet: {len(aus['rest'])}" + ("" if aus["rest"] else " – alles steht in Themen"))
    for r in aus["rest"]:
        erste = next((x for x in r["text"].splitlines() if x.strip()), "")
        z.append(f"  Zeilen {r['von']}–{r['bis']}: {r['grund']} · „{erste.strip()[:60]}“")
    z.append(f"Zählprobe ({'in der Datenbank' if aus['angelegt'] else 'geplant'} + nicht zugeordnet gegen das Original): "
             + ("bestanden" if aus["bestanden"] else f"NICHT bestanden – {len(aus['unterschiede'])} Unterschied(e)"))
    z.append(f"  Zeilen mit Text {o['zeilen']} → {n['zeilen']} · Überschriften {sum(o['ueberschriften'].values())} →"
             f" {sum(n['ueberschriften'].values())} · Kennungen {sum(o['kennungen'].values())} → {sum(n['kennungen'].values())}"
             f" · Links {sum(o['links'].values())} → {sum(n['links'].values())}")
    for was, a, b, fehlt, zuviel in aus["unterschiede"]:
        z.append(f"  {was}: {a} → {b}" + (f" · fehlt: {', '.join(fehlt[:10])}" if fehlt else "")
                 + (f" · zu viel: {', '.join(zuviel[:10])}" if zuviel else ""))
    z.append("Original " + ("unverändert" if aus["unveraendert"] else "WÄHREND DER ÜBERNAHME GEÄNDERT – Ergebnis prüfen")
             + f" (sha256 {aus['sha256'][:16]})" + (f" · als D{aus['dokument']} abgelegt und an jedes Thema gehängt"
                                                     if aus.get("dokument") else ""))
    return z


def bericht(aus):
    z = [f"# Konzept-Übernahme – {os.path.basename(aus['datei'])}", "", f"Datei: {aus['datei']}", ""]
    z += [x if not x.startswith("  ") else "- " + x.strip() for x in zeilen(aus)]
    if aus["rest"]:
        z += ["", "## Nicht zugeordnete Stellen (Wortlaut)"]
        for r in aus["rest"]:
            zaun = "`" * max(3, 1 + max((len(x) for x in re.findall(r"`+", r["text"])), default=0))
            z += ["", f"### Zeilen {r['von']}–{r['bis']}: {r['grund']}", "", zaun + "text", r["text"], zaun]
    return "\n".join(z) + "\n"

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

Freiwillig (A2109): die Vorschau meldet neue Themen, die ähnlich heißen wie ein vorhandenes (entscheidet nichts); ziel ordnet
Abschnitte vorhandenen Themen zu, ohne schließt Abschnitte aus, ganz nimmt die ganze Datei in ein Thema. Was in ein vorhandenes
Thema geht, wird über themen.pflegen eine neue Fassung hinter dem bisherigen Text (je Thema eine, mit einer Herkunftszeile je
Abschnitt) – also mit den üblichen Folgen einer neuen Fassung (Rechte, Gegenleser, betroffene Aufgaben), nie freigegeben.
"""
import collections
import fnmatch
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
FUELLWOERTER = frozenset("""der die das den dem des ein eine einen einem einer eines und oder sowie mit ohne von vom zu zum zur für
im in ins am an ans auf aus bei beim als über um the a of and or for to""".split())


def _woerter(name):
    return [w for w in re.findall(r"\w+", name.lower()) if w not in FUELLWOERTER]


def aehnlich(a, b):
    """Heißen zwei Themen ähnlich? Gleiche Wörter (klein, ohne Füllwörter) oder der eine Name als ganze Wörter im anderen."""
    x, y = sorted((_woerter(a), _woerter(b)), key=len)
    return bool(x) and (set(x) == set(y) or any(y[i:i + len(x)] == x for i in range(len(y) - len(x) + 1)))


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


def _abziehen(a, b):
    """a ohne b – Fehlendes bleibt als negative Zahl stehen, damit die Zählprobe es findet."""
    aus = _summe(a)
    aus["zeilen"] -= b["zeilen"]
    for k in ("ueberschriften", "kennungen", "links"):
        aus[k].subtract(b[k])
        aus[k] = collections.Counter({x: n for x, n in aus[k].items() if n})
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


def _schluessel(name):
    return " ".join(str(name).split()).lower()


def _ziel_pruefen(ziel):
    """{Abschnittsname (klein): (Name wie angegeben, Thema)}."""
    aus = {}
    for name, tid in (ziel or {}).items():
        if aus.setdefault(_schluessel(name), (name, tid))[1] != tid:
            raise kern.AmwFehler(f"ziel: Abschnitt „{name}“ ist zwei Themen zugeordnet")
    return aus


def gliedern(text, ebene=None, vorhanden=(), ziel=None, ohne=None, ganz=None):
    """Plan der Übernahme: {"ebene", "themen": [{"name", "text", "von", "bis"}], "rest": [{"von", "bis", "grund", "text"}],
    "ziele": [{"abschnitt", "thema", "text", "von", "bis"}]}.
    vorhanden: Namen von Themen, die es im Projekt schon gibt (klein geschrieben) – die werden nicht überschrieben.
    ziel: {Abschnittsname: Thema} – jeder Abschnitt dieses Namens geht in das Thema. ohne: Muster (fnmatch, Groß/klein egal) –
    diese Abschnitte bleiben draußen. ganz: Thema für die ganze Datei, ohne Gliederung (abschnitt None, ebene None)."""
    ohne = [ohne] if isinstance(ohne, str) else list(ohne or ())
    if ganz is not None:
        if ziel or ohne:
            raise kern.AmwFehler("ganz nimmt die ganze Datei – ziel und ohne gehen dann nicht")
        if not text.strip():
            raise kern.AmwFehler("Die Datei ist leer")
        z = text.splitlines()
        return {"ebene": None, "themen": [], "rest": [],
                "ziele": [{"abschnitt": None, "thema": ganz, "text": "\n".join(z).strip("\n"), "von": 1, "bis": len(z)}]}
    ziel = _ziel_pruefen(ziel)
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
    abschnitte = {_schluessel(b["kopf"][1]) for b in bloecke if b["kopf"] and b["kopf"][0] == ebene}
    for k, (name, _) in ziel.items():
        if not k or k not in abschnitte:
            raise kern.AmwFehler(f"ziel: Abschnitt „{name}“ gibt es auf der Gliederungsebene {ebene} nicht")
    themen_, rest, ziele, namen = [], [], [], set(x.lower() for x in vorhanden)

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
        muster = next((m for m in ohne if fnmatch.fnmatchcase(name.lower(), m.lower())), None)
        if _schluessel(name) in ziel:
            if muster is not None:
                raise kern.AmwFehler(f"Abschnitt „{name}“ ist zugeordnet (ziel) und ausgeschlossen (ohne „{muster}“) – nur eines")
            ziele.append({"abschnitt": name, "thema": ziel[_schluessel(name)][1], "text": "\n".join(b["zeilen"]).strip("\n"),
                          "von": b["von"], "bis": b["bis"]})
        elif muster is not None:
            _rest(b, f"Ausgeschlossen (ohne „{muster}“)")
        elif not name:
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
    return {"ebene": ebene, "themen": themen_, "rest": rest, "ziele": ziele}


def _themen_text(name, text, ebene):
    """So steht ein Thema in der Zählprobe: die Überschrift (Name) und der Text der Fassung."""
    return f"{'#' * ebene} {name}\n{text}"


def _thema(con, pid, von, nummer):
    """Thema dieses Projekts nach Nummer (12 oder TH12) – nur, wer dort eine neue Fassung schreiben darf (wie thema pflegen)."""
    m = re.fullmatch(r"(?:TH)?([0-9]{1,12})", str(nummer).strip(), re.IGNORECASE)
    if not m:
        raise kern.AmwFehler(f"„{nummer}“ ist keine Themennummer (z. B. 12 oder TH12)")
    t = con.execute("SELECT * FROM thema WHERE projekt_id = ? AND id = ?", (pid, int(m.group(1)))).fetchone()
    if not t:
        raise kern.AmwFehler(f"Thema TH{int(m.group(1))} gibt es in diesem Projekt nicht")
    themen._lead_oder_pfleger(con, pid, von, t, f"Neue Fassung von TH{t['id']}")
    return t


def _herkunft(z, datei):
    was = f"Abschnitt „{z['abschnitt']}“" if z["abschnitt"] else "ganze Datei"
    return f"Übernommen aus {datei} ({was}, Zeilen {z['von']}–{z['bis']}):"


def _angehaengt(alt, ziele, datei):
    """Text der neuen Fassung: der bisherige Text, dahinter je Abschnitt die Herkunftszeile und der Abschnitt."""
    return "\n\n".join(([alt.strip()] if alt.strip() else []) + [f"{_herkunft(z, datei)}\n\n{z['text']}" for z in ziele]).strip()


def _zuwachs(alt, neu, ziele, datei):
    """Zählprobe einer angehängten Fassung: was zum bisherigen Text dazukam, ohne die Herkunftszeilen. Gezählt wird im ganzen
    Text – fehlt etwas vom bisherigen oder geht der Abschnitt in einem offenen Code-Block unter, fällt es auf."""
    return _abziehen(zaehlen([neu]), zaehlen([alt.strip()] + [_herkunft(z, datei) for z in ziele]))


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


def uebernehmen(con, pid, von, pfad, ebene=None, anlegen=False, ziel=None, ohne=None, ganz=None):
    """Vorschau (anlegen=False, nichts geschrieben) oder Anlegen. ziel, ohne, ganz wie gliedern – Themen als Nummer (12, TH12)
    dieses Projekts. Rückgabe {"datei", "sha256", "ebene", "themen": [{"id"?, "name", "von", "bis", "zeichen", "aehnlich":
    [{"id", "name"}]}], "ziele": [{"abschnitt", "thema", "thema_name", "fassung", "von", "bis"}], "rest", "original", "nachher",
    "unterschiede", "bestanden", "unveraendert", "dokument"?, "bericht"?}."""
    _darf(con, pid, von)
    p = _datei(con, pid, pfad)
    roh, text = _lesen(p)
    sha, datei = hashlib.sha256(roh).hexdigest(), os.path.basename(p)
    vorhanden = [dict(r) for r in con.execute("SELECT id, name FROM thema WHERE projekt_id = ? ORDER BY id", (pid,))]
    ziel = {k: _thema(con, pid, von, v)["id"] for k, v in (ziel or {}).items()}
    ganz = None if ganz is None else _thema(con, pid, von, ganz)["id"]
    plan = gliedern(text, ebene, [v["name"] for v in vorhanden], ziel, ohne, ganz)
    original = zaehlen([text])
    rest_z = zaehlen([r["text"] for r in plan["rest"]])
    je = {}                                           # Thema → seine Abschnitte: je Thema eine neue Fassung
    for z in plan["ziele"]:
        je.setdefault(z["thema"], []).append(z)
    alt = {tid: themen._fassung(con, tid) for tid in je}
    namen = {v["id"]: v["name"] for v in vorhanden}
    aus = {"datei": p, "sha256": sha, "ebene": plan["ebene"], "rest": plan["rest"], "original": original, "angelegt": False,
           "themen": [{"name": t["name"], "von": t["von"], "bis": t["bis"], "zeichen": len(t["text"]),
                       "aehnlich": [v for v in vorhanden if aehnlich(t["name"], v["name"])]} for t in plan["themen"]],
           "ziele": [{"abschnitt": z["abschnitt"], "thema": z["thema"], "thema_name": namen[z["thema"]], "von": z["von"],
                      "bis": z["bis"], "fassung": (alt[z["thema"]]["nr"] if alt[z["thema"]] else 0) + 1} for z in plan["ziele"]]}
    if not anlegen:
        nachher = _summe(zaehlen([_themen_text(t["name"], t["text"], plan["ebene"]) for t in plan["themen"]]), rest_z)
        for tid, zs in je.items():
            t_alt = alt[tid]["text"] if alt[tid] else ""
            nachher = _summe(nachher, _zuwachs(t_alt, _angehaengt(t_alt, zs, datei), zs, datei))
    else:
        if not plan["themen"] and not je:
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
            for tid in je:
                con.execute("INSERT OR IGNORE INTO thema_dokument (thema_id, dokument_id, von, zeit_utc) VALUES (?, ?, ?, ?)",
                            (tid, did, von, jetzt))
        aus["angelegt"], aus["dokument"] = True, did
        nachher = _summe(_aus_der_datenbank(con, pid, [a["id"] for a in aus["themen"]], plan["ebene"]), rest_z)
        neue = []
        for tid, zs in je.items():                    # nach der Transaktion: pflegen hat seine eigene
            f = themen._fassung(con, tid)
            nr = themen.pflegen(con, pid, von, tid, _angehaengt(f["text"] if f else "", zs, datei))
            neue.append({"thema": tid, "fassung": nr})
            for a in aus["ziele"]:
                if a["thema"] == tid:
                    a["fassung"] = nr
            # gegen die Fassung direkt davor: auch was inzwischen jemand anderes dort geschrieben hat, darf nicht fehlen
            texte = dict(con.execute("SELECT nr, text FROM thema_fassung WHERE thema_id = ? AND nr IN (?, ?)",
                                     (tid, nr - 1, nr)).fetchall())
            nachher = _summe(nachher, _zuwachs(texte.get(nr - 1, ""), texte.get(nr, ""), zs, datei))
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
                                          "nicht_zugeordnet": len(plan["rest"]), "unveraendert": aus["unveraendert"],
                                          **({"ziele": neue} if neue else {})},
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
    if aus["ebene"] is None:
        was, wie = "ganze Datei in ein Thema", ""
    else:
        was = f"{len(aus['themen'])} Themen" + (f" und {len(aus['ziele'])} Abschnitt(e) in vorhandene Themen" if aus["ziele"] else "")
        wie = f" (Gliederung: Ebene {aus['ebene']}, {'#' * aus['ebene']} …)"
    z = [f"{'Angelegt' if aus['angelegt'] else 'Vorschau – nichts angelegt'}: {was} aus {os.path.basename(aus['datei'])}{wie}"]
    for t in aus["themen"]:
        z.append(f"  {('TH' + str(t['id'])) if t.get('id') else '+':<7} {t['name'][:80]}  · Zeilen {t['von']}–{t['bis']}"
                 + ("" if t["zeichen"] else " · ohne Text")
                 + (" · ähnlich: " + ", ".join(f"TH{v['id']} „{v['name'][:80]}“" for v in t["aehnlich"]) + " (gibt es schon)"
                    if t["aehnlich"] else ""))
    for a in aus["ziele"]:
        z.append(f"  {'→ TH' + str(a['thema']):<7} {(a['abschnitt'] or 'ganze Datei')[:80]}  · Zeilen {a['von']}–{a['bis']}"
                 f" · angehängt an „{a['thema_name'][:80]}“ als Fassung {a['fassung']} (Entwurf)")
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

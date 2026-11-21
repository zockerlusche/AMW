"""Design-Dokument je Thema (→ doc/automatismen.md): eine Seite „gilt jetzt“ je System (Netz, Rezepte, Maßstab, Stil …).

Die Seite entsteht aus den geltenden Beschlüssen des Themas (beschluss.thema) – sie kann nicht veralten. Dazu kommt eine
kurze, gepflegte Zusammenfassung (jede Fassung bleibt) mit einem Pfleger. Ein neuer Beschluss im Thema macht die
Zusammenfassung „veraltet seit B…“ und weckt den Pfleger, bis er sie anpasst (`thema pflegen`) oder bestätigt
(`thema bestaetigen`). Alte Beschlüsse werden nicht gelöscht, sondern „ueberholt“ (ersetzt durch B…) oder „unklar“.
Ein Thema kann der Projekt-Stil sein (stil): Grafik-Arbeit richtet sich danach, Bilder hängen als Dokumente daran.
"""
from . import db, kern


def _lead_oder_pfleger(con, pid, von, t, was):
    if not (kern.ist_lead(con, pid, von) or (t["pfleger"] and t["pfleger"] == von)):
        raise kern.AmwFehler(f"{was}: nur der Pfleger ({t['pfleger'] or '–'}) oder der Lead")


def finden(con, pid, name):
    """Thema nach Nummer (T… nicht – Themen haben „TH12“ oder 12) oder Name (Groß/klein egal, sonst eindeutiger Anfang)."""
    n = str(name or "").strip()
    if not n:
        raise kern.AmwFehler("welches Thema? amw thema liste")
    nr = n[2:] if n.upper().startswith("TH") and n[2:].isdigit() else n if n.isdigit() else None
    if nr:
        t = con.execute("SELECT * FROM thema WHERE projekt_id = ? AND id = ?", (pid, int(nr))).fetchone()
        if t:
            return t
    t = con.execute("SELECT * FROM thema WHERE projekt_id = ? AND name = ? COLLATE NOCASE", (pid, n)).fetchone()
    if t:
        return t
    l = con.execute("SELECT * FROM thema WHERE projekt_id = ? AND (name LIKE ? OR name LIKE ?) ORDER BY name",
                    (pid, n + "%", f"% {n}%")).fetchall()
    if len(l) == 1:
        return l[0]
    if l:
        raise kern.AmwFehler(f"„{n}“ passt zu mehreren Themen: " + "; ".join(f"TH{x['id']} {x['name']}" for x in l[:8]))
    raise kern.AmwFehler(f"Thema „{n}“ gibt es nicht – amw thema liste (neu: amw thema neu \"…\")")


def _fassung(con, tid):
    return con.execute("SELECT * FROM thema_fassung WHERE thema_id = ? ORDER BY nr DESC LIMIT 1", (tid,)).fetchone()


def stand(con, t):
    """(stand, veraltet_seit): ohne (keine Zusammenfassung) | aktuell | veraltet (B-Nummer des ersten neueren Beschlusses)."""
    f = _fassung(con, t["id"])
    if not f:
        return "ohne", None
    grenze = max(f["zeit_utc"], t["bestaetigt_utc"] or "")
    b = con.execute("SELECT min(id) FROM beschluss WHERE projekt_id = ? AND thema = ? COLLATE NOCASE AND status = 'gilt'"
                    " AND angelegt_utc > ?", (t["projekt_id"], t["name"], grenze)).fetchone()[0]
    return ("veraltet", b) if b else ("aktuell", None)


def liste(con, pid):
    aus = []
    for t in con.execute("SELECT * FROM thema WHERE projekt_id = ? ORDER BY name", (pid,)).fetchall():
        z = con.execute("SELECT sum(status = 'gilt'), sum(status = 'ueberholt'), sum(status = 'unklar'), max(angelegt_utc)"
                        " FROM beschluss WHERE projekt_id = ? AND thema = ? COLLATE NOCASE", (pid, t["name"])).fetchone()
        s, seit = stand(con, t)
        aus.append({"id": t["id"], "name": t["name"], "pfleger": t["pfleger"], "stil": bool(t["stil"]), "gilt": z[0] or 0,
                    "ueberholt": z[1] or 0, "unklar": z[2] or 0, "zuletzt_utc": z[3], "stand": s, "veraltet_seit": seit,
                    "zustand": status(con, t), "neu_erlaubt": MENSCH_LEGT_AN})   # A1896: Status für den Menschen (abgeleitet)
    return aus


def seite(con, pid, name):
    t = finden(con, pid, name)
    s, seit = stand(con, t)
    f = _fassung(con, t["id"])
    b = [dict(r) for r in con.execute(
        "SELECT id, zeit_utc, stichwort, regel, quelle, status, ersetzt_durch FROM beschluss WHERE projekt_id = ?"
        " AND thema = ? COLLATE NOCASE ORDER BY id DESC", (pid, t["name"]))]
    dok = [dict(r) for r in con.execute(
        "SELECT d.id, d.titel, d.art, d.online, v.endung FROM thema_dokument x JOIN dokument d ON d.id = x.dokument_id"
        " JOIN dokument_version v ON v.dokument_id = d.id AND v.nr = (SELECT max(nr) FROM dokument_version WHERE dokument_id = d.id)"
        " WHERE x.thema_id = ? AND d.status != 'geloescht' ORDER BY d.id", (t["id"],))]
    return {"id": t["id"], "name": t["name"], "pfleger": t["pfleger"], "stil": bool(t["stil"]), "stand": s, "veraltet_seit": seit,
            "zusammenfassung": dict(f) if f else None, "bestaetigt_utc": t["bestaetigt_utc"], "bestaetigt_von": t["bestaetigt_von"],
            "gilt": [x for x in b if x["status"] == "gilt"], "unklar": [x for x in b if x["status"] == "unklar"],
            "ueberholt": [x for x in b if x["status"] == "ueberholt"], "dokumente": dok,
            "zustand": (z := status(con, t)), "handlungen": list(handlungen(z)),           # A1896
            "freigegeben_text": _freigegebener_text(con, t["id"], z),                     # F5358: Unterschied zur Freigabe
            "gegengelesen": _gegengelesen(con, pid, t["id"])}                             # A1914: Ergebnis des Gegenlesers


def _gegengelesen(con, pid, tid):
    """A1914: das jüngste Gegenlesen (Fassung, Modell, Einwände oder Fehler, Kosten, Zeit) – oder None."""
    from . import gegenlesen
    e = gegenlesen.letztes(con, pid, tid)
    return {k: e.get(k) for k in ("fassung", "modell", "einwaende", "fehler", "usd", "lauf", "zeit_utc")} if e else None


def neu(con, pid, von, name, pfleger=None, stil=False):
    """Thema anlegen: Lead und Mensch – und der Co-Entwickler (A1908, W2408/B2905: er verantwortet das Konzept, Themen sind
    Konzept, nicht Planung). Wer Co-Entwickler ist, steht in der Projekt-Einstellung co_entwickler, die nur Lead oder Mensch
    setzen (kern.projekt_einstellen) – sich selbst dazu machen geht nicht. Pfleger und Stil bleiben beim Lead (wie einstellen)."""
    co = not kern.ist_lead(con, pid, von) and kern.ist_co(con, pid, von)
    if not (kern.ist_lead(con, pid, von) or co):
        raise kern.AmwFehler("Themen anlegen dürfen Lead, Entwickler und der Co-Entwickler")
    if co and (pfleger or stil):
        raise kern.AmwFehler("Pfleger und Stil setzen dürfen Lead und Entwickler – das Thema ohne --pfleger/--stil anlegen")
    name = " ".join((name or "").split())
    if not name or len(name) > 120:
        raise kern.AmwFehler("Name des Themas: 1–120 Zeichen")
    if con.execute("SELECT 1 FROM thema WHERE projekt_id = ? AND name = ? COLLATE NOCASE", (pid, name)).fetchone():
        raise kern.AmwFehler(f"Thema „{name}“ gibt es schon")
    with db.schreiben(con):
        tid = db.einfuegen(con, "thema", projekt_id=pid, name=name, pfleger=kern.bearbeiter(con, pid, pfleger) if pfleger else None,
                           stil=int(bool(stil)), angelegt_von=von, angelegt_utc=db.jetzt())
        if stil:
            con.execute("UPDATE thema SET stil = 0 WHERE projekt_id = ? AND id != ?", (pid, tid))
    return tid


def einstellen(con, pid, von, name, pfleger=None, stil=None):
    """Pfleger setzen (leer = keiner) bzw. als Projekt-Stil markieren (es gibt höchstens einen). Nur der Lead."""
    if not kern.ist_lead(con, pid, von):
        raise kern.AmwFehler("Pfleger und Stil setzen dürfen Lead und Entwickler")
    t = finden(con, pid, name)
    with db.schreiben(con):
        if pfleger is not None:
            p = kern.bearbeiter(con, pid, pfleger) if pfleger.strip() else None
            con.execute("UPDATE thema SET pfleger = ? WHERE id = ?", (p, t["id"]))
            if p and p != von and p != kern.ENTWICKLER:
                kern._posten(con, pid, von, p, "auftrag", f"Du pflegst jetzt das Thema „{t['name']}“",
                             f"Zusammenfassung „gilt jetzt“ aktuell halten: amw thema zeige TH{t['id']} · amw thema pflegen"
                             f" TH{t['id']} --text-datei … · nach einem neuen Beschluss ohne Änderung: amw thema bestaetigen TH{t['id']}")
        if stil is not None:
            if stil:
                con.execute("UPDATE thema SET stil = 0 WHERE projekt_id = ?", (pid,))
            con.execute("UPDATE thema SET stil = ? WHERE id = ?", (int(bool(stil)), t["id"]))
    return finden(con, pid, t["id"])


def pflegen(con, pid, von, name, text):
    t = finden(con, pid, name)
    _lead_oder_pfleger(con, pid, von, t, "Zusammenfassung pflegen")
    if not (text or "").strip():
        raise kern.AmwFehler("Text fehlt (--text oder --text-datei)")
    with db.schreiben(con):
        f = _fassung(con, t["id"])
        nr = (f["nr"] if f else 0) + 1
        db.einfuegen(con, "thema_fassung", thema_id=t["id"], nr=nr, text=text.strip(), von=von, zeit_utc=db.jetzt())
        if von != kern.ENTWICKLER:                   # A1896: Vorlage eines Agenten → wartet auf den Menschen
            _ereignis(con, pid, von, "vorgelegt", t["id"], fassung=nr)
    if von != kern.ENTWICKLER:                       # A1914: erst gegenlesen, dann wartet sie auf den Menschen
        from . import gegenlesen
        gegenlesen.anstossen(con, pid, t["id"], nr)
    thema_geaendert(con, pid, t["id"], nr)           # A1915: betroffene Aufgaben prüfen lassen
    return nr


def bestaetigen(con, pid, von, name):
    t = finden(con, pid, name)
    _lead_oder_pfleger(con, pid, von, t, "Zusammenfassung bestätigen")
    if not _fassung(con, t["id"]):
        raise kern.AmwFehler("es gibt noch keine Zusammenfassung – amw thema pflegen …")
    with db.schreiben(con):
        con.execute("UPDATE thema SET bestaetigt_utc = ?, bestaetigt_von = ? WHERE id = ?", (db.jetzt(), von, t["id"]))
        if von != kern.ENTWICKLER:                   # A1896: gilt weiter → als Vorlage dem Menschen zeigen
            _ereignis(con, pid, von, "vorgelegt", t["id"], fassung=_fassung(con, t["id"])["nr"], bestaetigt=True)


def dokument(con, pid, von, name, did, loesen=False):
    """Ein Dokument (z. B. Bild für den Stil) an die Seite hängen bzw. lösen. Pfleger oder Lead."""
    t = finden(con, pid, name)
    _lead_oder_pfleger(con, pid, von, t, "Dokumente an das Thema hängen")
    if not con.execute("SELECT 1 FROM dokument WHERE id = ? AND projekt_id = ?", (did, pid)).fetchone():
        raise kern.AmwFehler(f"D{did} gibt es nicht")
    with db.schreiben(con):
        if loesen:
            con.execute("DELETE FROM thema_dokument WHERE thema_id = ? AND dokument_id = ?", (t["id"], did))
        else:
            con.execute("INSERT OR IGNORE INTO thema_dokument (thema_id, dokument_id, von, zeit_utc) VALUES (?, ?, ?, ?)",
                        (t["id"], did, von, db.jetzt()))


def zum_beschluss(con, pid, von, thema, neues_thema=False):
    """Für beschluss neu (Transaktion läuft noch nicht): gibt den Namen des Themas zurück – vorhandenes (Groß/klein egal,
    eindeutiger Anfang) oder mit neues_thema ein neues. Ohne Thema nur, solange das Projekt keine Themen hat."""
    if not (thema or "").strip():
        if con.execute("SELECT 1 FROM thema WHERE projekt_id = ? LIMIT 1", (pid,)).fetchone():
            raise kern.AmwFehler("--thema fehlt: jeder Beschluss gehört zu einem Thema (amw thema liste)")
        return None
    if neues_thema:
        try:
            return finden(con, pid, thema)["name"]
        except kern.AmwFehler:
            neu(con, pid, von, thema)
            return finden(con, pid, thema)["name"]
    return finden(con, pid, thema)["name"]


def nach_beschluss(con, pid, von, bid, thema):
    """Nach beschluss neu (eigene Transaktion): den Pfleger wecken, Hinweise für den Anlegenden zurückgeben."""
    if not thema:
        return []
    t = finden(con, pid, thema)
    andere = con.execute("SELECT id, stichwort FROM beschluss WHERE projekt_id = ? AND thema = ? COLLATE NOCASE AND status = 'gilt'"
                         " AND id != ? ORDER BY id DESC LIMIT 5", (pid, t["name"], bid)).fetchall()
    hinweise = []
    if andere:
        hinweise.append(f"Geltend im Thema TH{t['id']} „{t['name']}“ (neueste): "
                        + "; ".join(f"B{x['id']} {x['stichwort'][:50]}" for x in andere)
                        + f" – ersetzt B{bid} einen davon? amw beschluss ueberholt B… --durch B{bid}")
    if _fassung(con, t["id"]):
        wer = t["pfleger"]
        if wer and wer != von and wer != kern.ENTWICKLER:
            with db.schreiben(con):
                kern._posten(con, pid, "AMW", wer, "meldung", f"Thema „{t['name'][:60]}“: B{bid} neu – Zusammenfassung prüfen",
                             f"amw thema zeige TH{t['id']} · anpassen: amw thema pflegen TH{t['id']} --text-datei … · gilt"
                             f" weiter: amw thema bestaetigen TH{t['id']}")
        else:
            hinweise.append(f"Die Zusammenfassung von TH{t['id']} ist damit veraltet – amw thema pflegen|bestaetigen TH{t['id']}")
    return hinweise


# --- Themen-Bereich für den Menschen (A1896, D1319, W2429–W2431, Einordnung D1326 Teil A): ein Status je Thema (B2907) -------
# Fakten: Fassungen (thema_fassung.nr), Beschlüsse im Thema und feste Ereignisse je Handlung (plan_ereignis, Text JSON mit
# "thema" vorn) – ohne Schemaänderung. Den Status setzt niemand von Hand.
STATUS_TEXT = {"dich": "wartet auf dich", "pruefen": "neu prüfen", "arbeit": "in Arbeit", "frei": "freigegeben"}
VORRANG = ("markiert", "dich", "pruefen", "frei", "arbeit")        # D1326 A16: fester Vorrang, die Sortierung folgt ihm
EREIGNIS = {"vorgelegt": "thema_vorgelegt", "freigegeben": "thema_freigegeben", "zurueck": "thema_zurueck",
            "bearbeitet": "thema_bearbeitet", "markiert": "thema_loeschen_markiert", "entmarkiert": "thema_markierung_aufgehoben"}
NUR_MENSCH = ("freigegeben", "zurueck", "bearbeitet", "markiert", "entmarkiert")
HANDLUNGEN = {"dich": ("freigeben", "zurueck", "bearbeiten", "markieren"), "pruefen": ("freigeben", "zurueck", "bearbeiten", "markieren"),
              "frei": ("zurueck", "bearbeiten", "markieren"), "arbeit": ("bearbeiten", "markieren")}
# Marcels offene Antworten (D1326 B) – je eine Stelle; bis zur Antwort gilt die Empfehlung A des Leads
BEARBEITEN_GIBT_FREI = True      # F5358 A: deine eigene Bearbeitung gilt als von dir freigegeben (B: zurück auf „in Arbeit“)
NEU_PRUEFEN_FUER_DICH = False    # F5359 A: „neu prüfen“ prüft erst die KI, nicht unter „Für dich“ (B: auch unter „Für dich“)
MENSCH_LEGT_AN = True            # F5360 A: „+ Thema“ für den Menschen (B: Themen nur aus dem Gespräch)


def _ereignisse(con, pid, tid):
    import json
    aus = []
    for r in con.execute(f"SELECT id, art, von, zeit_utc, text FROM plan_ereignis WHERE projekt_id = ? AND art IN"
                         f" ({','.join('?' * len(EREIGNIS))}) AND text LIKE ? ORDER BY id", (pid, *EREIGNIS.values(), f'{{"thema": {tid},%')):
        try:
            aus.append({**dict(r), **json.loads(r["text"])})
        except ValueError:
            continue
    return aus


def _ereignis(con, pid, von, art, tid, **extra):
    """In der Transaktion des Aufrufers. Die Handlungen des Menschen schreibt nur der Mensch (D1326 A35)."""
    import json
    if art in NUR_MENSCH and von != kern.ENTWICKLER:
        raise kern.AmwFehler("Das darf nur der Mensch")
    db.einfuegen(con, "plan_ereignis", projekt_id=pid, zeit_utc=db.jetzt(), von=von, art=EREIGNIS[art],
                 text=json.dumps({"thema": tid, **extra}, ensure_ascii=False))


def _neuer_beschluss(con, t, seit):
    return con.execute("SELECT id, stichwort, angelegt_utc FROM beschluss WHERE projekt_id = ? AND thema = ? COLLATE NOCASE"
                       " AND status = 'gilt' AND angelegt_utc > ? ORDER BY id LIMIT 1", (t["projekt_id"], t["name"], seit)).fetchone()


def status(con, t):
    """{"status", "text", "grund", "markiert", "fassung", "freigegeben"} nach festem Vorrang (D1326 A16):
    1 Löschen markiert (Flag, Status darunter bleibt) → 2 wartet auf dich: die neueste Fassung ist eine Vorlage eines Agenten (oder
    seine Bestätigung) ohne Freigabe/Zurück/Bearbeitung danach → 3 neu prüfen: nach der letzten Freigabe kam ein neuer Beschluss →
    4 freigegeben: die letzte Freigabe zeigt auf die neueste Fassung → 5 in Arbeit. Der Grund ist ein abgeleiteter Wert."""
    f = _fassung(con, t["id"])
    nr = f["nr"] if f else None
    ev = _ereignisse(con, t["projekt_id"], t["id"])
    markiert = False
    for e in ev:
        if e["art"] in (EREIGNIS["markiert"], EREIGNIS["entmarkiert"]):
            markiert = e["art"] == EREIGNIS["markiert"]
    # jüngste Handlung des Menschen und jüngste Vorlage (Zeit, Rang: bei gleicher Sekunde gilt das spätere Ereignis)
    mensch = [e for e in ev if e["art"] in (EREIGNIS["freigegeben"], EREIGNIS["zurueck"], EREIGNIS["bearbeitet"])]
    # Reihenfolge: (Zeit, Ereignis-Nummer) – bei gleicher Sekunde gilt das spätere Ereignis; Fassungen ohne Ereignis (vor A1896)
    # zählen mit Nummer 0
    vorlagen = [(f["zeit_utc"], 0)] if f and f["von"] != kern.ENTWICKLER else []
    vorlagen += [(e["zeit_utc"], e["id"]) for e in ev if e["art"] == EREIGNIS["vorgelegt"]]
    if t["bestaetigt_utc"] and t["bestaetigt_von"] != kern.ENTWICKLER:
        vorlagen.append((t["bestaetigt_utc"], 0))
    letzte_vorlage = max(vorlagen) if vorlagen else None
    letzte_mensch = mensch[-1] if mensch else None
    freigaben = [e for e in mensch if e["art"] == EREIGNIS["freigegeben"]
                 or (BEARBEITEN_GIBT_FREI and e["art"] == EREIGNIS["bearbeitet"])]
    letzte_frei = freigaben[-1] if freigaben else None
    frei_nr = letzte_frei.get("fassung") if letzte_frei else None
    st, grund, liest = "arbeit", None, None
    if letzte_vorlage and (not letzte_mensch or letzte_vorlage > (letzte_mensch["zeit_utc"], letzte_mensch["id"])):
        st = "dich"
        b = _neuer_beschluss(con, t, letzte_vorlage[0])
        if b:                                          # die Vorlage ist schon wieder überholt → die KI ist dran
            st = "arbeit"
        elif nr is not None:                           # A1914: liest gerade ein Gegenleser, ist sie noch nicht beim Menschen
            from . import gegenlesen
            g = gegenlesen.laeuft(con, t["projekt_id"], t["id"], nr)
            if g:
                st, liest = "arbeit", {"seit_utc": g["zeit_utc"], "modell": g.get("modell"), "fassung": nr}
    elif letzte_frei and nr is not None and frei_nr == nr and letzte_mensch is letzte_frei:
        b = _neuer_beschluss(con, t, letzte_frei["zeit_utc"])
        if b:
            st, grund = "pruefen", f"B{b['id']} · {b['angelegt_utc'][8:10]}.{b['angelegt_utc'][5:7]}."
        else:
            st = "frei"
    return {"status": st, "text": STATUS_TEXT[st], "grund": grund, "markiert": markiert, "fassung": nr, "freigegeben": frei_nr,
            "gegenlesen": liest}


def _freigegebener_text(con, tid, s):
    """F5358 (Ergänzung #29401): wartet eine neuere Fassung auf den Menschen und gab es vorher eine Freigabe, der freigegebene
    Text – für „Unterschied anzeigen“ (freigegebene Fassung gegen die neueste). Sonst None."""
    if s["status"] != "dich" or not s["freigegeben"] or s["freigegeben"] == s["fassung"]:
        return None
    r = con.execute("SELECT nr, text FROM thema_fassung WHERE thema_id = ? AND nr = ?", (tid, s["freigegeben"])).fetchone()
    return {"nr": r["nr"], "text": r["text"]} if r else None


def rang(s):
    return VORRANG.index("markiert" if s["markiert"] else s["status"])


def handlungen(s):
    return ("entmarkieren",) if s["markiert"] else HANDLUNGEN[s["status"]]


def _nur_mensch(von, was):
    if von != kern.ENTWICKLER:
        raise kern.AmwFehler(f"{was}: nur der Mensch (Workbench am PC oder sein eigenes Terminal)")


def _an_pfleger(con, pid, t):
    k = t["pfleger"] or kern.lead(con, pid)
    return k if k and k != kern.ENTWICKLER else None


def _handlung(con, pid, von, name, was):
    _nur_mensch(von, {"freigeben": "Freigeben", "zurueck": "Zurückgeben", "bearbeiten": "Bearbeiten", "markieren": "Löschen markieren",
                      "entmarkieren": "Markierung aufheben"}[was])
    t = finden(con, pid, name)
    s = status(con, t)
    if was not in handlungen(s):
        raise kern.AmwFehler(f"TH{t['id']} ist „{'zum Löschen markiert' if s['markiert'] else s['text']}“ – das geht gerade nicht"
                             f" (möglich: {', '.join(handlungen(s))})")
    return t, s


def freigeben(con, pid, von, name):
    t, s = _handlung(con, pid, von, name, "freigeben")
    an = _an_pfleger(con, pid, t)
    with db.schreiben(con):
        _ereignis(con, pid, von, "freigegeben", t["id"], fassung=s["fassung"])
        if an:
            kern._posten(con, pid, "AMW", an, "info", f"Thema „{t['name'][:60]}“ freigegeben (Fassung {s['fassung']})",
                         f"TH{t['id']}: {kern.entwickler_name(con, pid)} hat Fassung {s['fassung']} freigegeben.")
    return status(con, finden(con, pid, t["id"]))


def zurueck(con, pid, von, name, notiz):
    if not (notiz or "").strip():
        raise kern.AmwFehler("Zurück nur mit Notiz: was soll anders werden?")
    t, s = _handlung(con, pid, von, name, "zurueck")
    an = _an_pfleger(con, pid, t)
    with db.schreiben(con):
        _ereignis(con, pid, von, "zurueck", t["id"], fassung=s["fassung"], notiz=notiz.strip()[:2000])
        if an:
            kern._posten(con, pid, "AMW", an, "auftrag", f"Thema „{t['name'][:60]}“ zurück: {notiz.strip()[:80]}",
                         f"TH{t['id']} (Fassung {s['fassung']}) – Notiz von {kern.entwickler_name(con, pid)}:\n{notiz.strip()}\n\n"
                         f"Neue Fassung: amw thema pflegen TH{t['id']} --text-datei …")
    return status(con, finden(con, pid, t["id"]))


def bearbeiten(con, pid, von, name, text, erwartet=None):
    """Der Mensch ändert den Text selbst – nur gegen die erwartete Fassung (D1326 A40). F5358 A: gilt als von ihm freigegeben,
    der Pfleger bekommt einen Hinweis; B: in Arbeit, der Pfleger einen Auftrag."""
    t, s = _handlung(con, pid, von, name, "bearbeiten")
    if not (text or "").strip():
        raise kern.AmwFehler("Text fehlt")
    if erwartet not in (None, "") and s["fassung"] != int(erwartet):
        raise kern.AmwFehler(f"TH{t['id']} hat inzwischen Fassung {s['fassung']} (du hast Fassung {erwartet} bearbeitet) –"
                             " nichts gespeichert; neu laden und noch einmal")
    an = _an_pfleger(con, pid, t)
    with db.schreiben(con):
        f = _fassung(con, t["id"])
        nr = (f["nr"] if f else 0) + 1
        db.einfuegen(con, "thema_fassung", thema_id=t["id"], nr=nr, text=text.strip(), von=von, zeit_utc=db.jetzt())
        _ereignis(con, pid, von, "bearbeitet", t["id"], fassung=nr)
        if an:
            kern._posten(con, pid, "AMW", an, "info" if BEARBEITEN_GIBT_FREI else "auftrag",
                         f"Thema „{t['name'][:60]}“: Text von {kern.entwickler_name(con, pid)} geändert (Fassung {nr})",
                         f"TH{t['id']} Fassung {nr} stammt vom Menschen – "
                         + ("sie gilt als freigegeben; prüfe die Folgen für andere Themen und Aufgaben." if BEARBEITEN_GIBT_FREI
                            else f"bitte einarbeiten und als neue Fassung liefern: amw thema pflegen TH{t['id']} --text-datei …"))
    thema_geaendert(con, pid, t["id"], nr)           # A1915: betroffene Aufgaben prüfen lassen
    return status(con, finden(con, pid, t["id"]))


def markieren(con, pid, von, name, an=True):
    """Löschen markieren (B2894: gelöscht wird nichts – löschen tut der Mensch) bzw. die Markierung aufheben."""
    t, _ = _handlung(con, pid, von, name, "markieren" if an else "entmarkieren")
    with db.schreiben(con):
        _ereignis(con, pid, von, "markiert" if an else "entmarkiert", t["id"], fassung=None)
    return status(con, finden(con, pid, t["id"]))


def anlegen_mensch(con, pid, von, name, text):
    """F5360 A: der Mensch legt ein Thema an (Titel und Text) – danach „in Arbeit“ für die KI; der Lead bekommt einen Auftrag."""
    if not MENSCH_LEGT_AN:
        raise kern.AmwFehler("Themen entstehen aus dem Gespräch mit dem Co-Entwickler")
    _nur_mensch(von, "Thema anlegen")
    tid = neu(con, pid, von, name)
    if (text or "").strip():
        with db.schreiben(con):
            db.einfuegen(con, "thema_fassung", thema_id=tid, nr=1, text=text.strip(), von=von, zeit_utc=db.jetzt())
    lead = kern.lead(con, pid)
    if lead and lead != kern.ENTWICKLER:
        with db.schreiben(con):
            kern._posten(con, pid, "AMW", lead, "auftrag", f"Neues Thema von {kern.entwickler_name(con, pid)}: „{name.strip()[:60]}“",
                         f"TH{tid}: Pfleger setzen (amw thema einstellen TH{tid} --pfleger …) und ausarbeiten.")
    return tid


def fuer_dich(con, pid):
    """Themen, die auf den Menschen warten (F5359: „neu prüfen“ nur mit NEU_PRUEFEN_FUER_DICH), nicht zum Löschen markiert."""
    zaehlt = ("dich", "pruefen") if NEU_PRUEFEN_FUER_DICH else ("dich",)
    aus = []
    for t in con.execute("SELECT * FROM thema WHERE projekt_id = ? ORDER BY name", (pid,)).fetchall():
        s = status(con, t)
        if not s["markiert"] and s["status"] in zaehlt:
            aus.append({"id": t["id"], "name": t["name"], **s})
    return aus


def kontext_zeilen(con, pid, kennung):
    z = []
    s = con.execute("SELECT * FROM thema WHERE projekt_id = ? AND stil = 1", (pid,)).fetchone()
    if s:
        z.append(f"Projekt-Stil: amw thema zeige TH{s['id']} („{s['name']}“, Pfleger {s['pfleger'] or '–'}) – Grafik-Arbeit"
                 " danach richten; eine Abweichung ist eine Frage")
    veraltet = [t for t in con.execute("SELECT * FROM thema WHERE projekt_id = ? AND pfleger = ?", (pid, kennung)).fetchall()
                if stand(con, t)[0] == "veraltet"]
    if veraltet:
        z.append("Du pflegst, veraltet: " + "; ".join(f"TH{t['id']} {t['name'][:50]} (seit B{stand(con, t)[1]})" for t in veraltet)
                 + " – amw thema pflegen|bestaetigen")
    return z


# --- Themen → Aufgaben (A1915, D1304 v12 §1.3/§6d): Änderungen wirken von oben nach unten, nur Betroffenes wird gemeldet ---------
# Verweis einer Aufgabe auf Themen ohne Schemaänderung: je Setzen/Lösen ein Ereignis „aufgabe_thema“ (aufgabe_id, Text JSON
# {"aufgabe", "thema", "an"}); der jüngste Eintrag je Thema gilt. Den Status einer Aufgabe ändert das nie.
VERWEIS = "aufgabe_thema"


def verweise(con, pid, aid):
    """Themen (Nummern), auf die die Aufgabe gerade verweist."""
    import json
    an = {}
    for r in con.execute("SELECT text FROM plan_ereignis WHERE projekt_id = ? AND art = ? AND aufgabe_id = ? ORDER BY id", (pid, VERWEIS, aid)):
        try:
            d = json.loads(r[0])
        except ValueError:
            continue
        an[d.get("thema")] = bool(d.get("an"))
    return sorted(k for k, v in an.items() if v and k)


def verweise_setzen(con, pid, von, aid, namen, entfernen=False):
    """`amw aufgabe aendern N --thema TH3,TH5` (dazu) bzw. `--ohne-thema TH3` (lösen). Lead, Mensch, Co-Entwickler oder der
    Agent der Aufgabe. Rückgabe: die Themen danach."""
    import json
    a = con.execute("SELECT * FROM aufgabe WHERE id = ? AND projekt_id = ?", (aid, pid)).fetchone()
    if not a:
        raise kern.AmwFehler(f"A{aid} gibt es nicht")
    if not (kern.ist_lead(con, pid, von) or kern.ist_co(con, pid, von) or (a["agent"] and a["agent"] == von)):
        raise kern.AmwFehler("Themen einer Aufgabe setzen Lead, Entwickler, Co-Entwickler oder ihr Agent")
    tids = list(dict.fromkeys(finden(con, pid, n)["id"] for n in namen if str(n).strip()))
    if not tids:
        raise kern.AmwFehler("welche Themen? z. B. --thema TH3,TH5")
    vorher = set(verweise(con, pid, aid))
    with db.schreiben(con):
        for tid in tids:
            if (tid in vorher) != (not entfernen):           # nur echte Änderungen eintragen
                db.einfuegen(con, "plan_ereignis", projekt_id=pid, zeit_utc=db.jetzt(), von=von, art=VERWEIS, aufgabe_id=aid,
                             text=json.dumps({"aufgabe": aid, "thema": tid, "an": not entfernen}))
    return verweise(con, pid, aid)


def aufgaben_zu(con, pid, tid):
    """Offene Aufgaben (nicht fertig/verworfen), die gerade auf das Thema verweisen."""
    ids = [r[0] for r in con.execute("SELECT DISTINCT aufgabe_id FROM plan_ereignis WHERE projekt_id = ? AND art = ? AND text LIKE ?",
                                     (pid, VERWEIS, f'%"thema": {int(tid)},%'))]
    aus = []
    for aid in sorted(ids):
        a = con.execute("SELECT * FROM aufgabe WHERE id = ? AND projekt_id = ?", (aid, pid)).fetchone()
        if a and a["status"] not in ("fertig", "verworfen") and tid in verweise(con, pid, aid):
            aus.append(a)
    return aus


def _war_freigegeben(con, pid, tid, nr):
    """Gab es vor Fassung `nr` eine Freigabe (bzw. eine eigene Bearbeitung des Menschen, F5358 A)?"""
    arten = (EREIGNIS["freigegeben"], EREIGNIS["bearbeitet"]) if BEARBEITEN_GIBT_FREI else (EREIGNIS["freigegeben"],)
    return any(e["art"] in arten and (e.get("fassung") or 0) < nr for e in _ereignisse(con, pid, tid))


def thema_geaendert(con, pid, tid, nr):
    """A1915: Ein freigegebenes Thema hat eine neue Fassung (vom Pfleger oder vom Menschen) → die offenen Aufgaben mit Verweis
    gehen als „Thema geändert – prüfen“ an ihren Agenten, eine Nachricht je Agent. p-Pakete haben keinen eigenen Agenten:
    ihre Zeile geht an den Lead, ein laufendes wird nicht unterbrochen. Kein Status wird gesetzt. Rückgabe {Empfänger: [A…]}."""
    from . import arbeitspaket
    if not _war_freigegeben(con, pid, tid, nr):
        return {}
    t = finden(con, pid, tid)
    lead = kern.lead(con, pid)
    je = {}
    for a in aufgaben_zu(con, pid, tid):
        f = arbeitspaket.lesen(con, a["id"])
        p = f.get("art") == "p"
        an = lead if p or not a["agent"] or a["agent"] == kern.ENTWICKLER else a["agent"]
        if not an or an == kern.ENTWICKLER:
            continue
        zusatz = (" – p-Paket läuft weiter, nach dem Lauf prüfen" if f.get("zustand") == "laeuft" else " – p-Paket") if p else ""
        je.setdefault(an, []).append((a["id"], f"A{a['id']} [{a['status']}] {a['titel'][:90]}{zusatz}"))
    if not je:
        return {}
    with db.schreiben(con):
        for an, zeilen in je.items():
            kern._posten(con, pid, "AMW", an, "meldung",
                         f"Thema geändert – prüfen: TH{tid} „{t['name'][:60]}“ (Fassung {nr}), {len(zeilen)} Aufgabe(n)",
                         f"TH{tid} „{t['name']}“ hat Fassung {nr} – vorher war es freigegeben. Diese Aufgaben verweisen darauf:\n"
                         + "\n".join(f"- {z}" for _, z in zeilen)
                         + f"\n\nPrüfe, ob sie noch passen: amw thema zeige TH{tid}. Passt etwas nicht mehr, frage den Lead"
                           " oder passe die Aufgabe an. Der Status der Aufgaben bleibt, wie er ist.")
    return {an: [aid for aid, _ in zeilen] for an, zeilen in je.items()}

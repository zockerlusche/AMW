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
            "tor": tor(con, pid, t["id"]),                                                # A1913: Hinweis vor dem Schließen
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
            "bearbeitet": "thema_bearbeitet", "markiert": "thema_loeschen_markiert", "entmarkiert": "thema_markierung_aufgehoben",
            "ja": "thema_ja", "nur_mensch": "thema_nur_mensch"}                    # A1937 (B2913): Ja von Co/Lead, nur der Mensch
ROLLEN_JA = {"co": "Co-Entwickler", "lead": "Lead"}
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


def _ereignis(con, pid, von, art, tid, regel=False, **extra):
    """In der Transaktion des Aufrufers. Die Handlungen des Menschen schreibt nur der Mensch (D1326 A35) – außer der Freigabe
    nach B2913 (regel=True: Co-Entwickler und Lead haben beide Ja gesagt, A1937)."""
    import json
    if art in NUR_MENSCH and von != kern.ENTWICKLER and not regel:
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
    aus = {"status": st, "text": STATUS_TEXT[st], "grund": grund, "markiert": markiert, "fassung": nr, "freigegeben": frei_nr,
           "gegenlesen": liest}
    if freigabe_regel(con, t["projekt_id"]) == "co+lead":          # A1937: wessen Ja fehlt (nur, wo eine Freigabe ansteht)
        aus["nur_mensch"] = nur_mensch(ev)
        if st in ("dich", "pruefen") and nr is not None and not aus["nur_mensch"]:
            j = jas(ev, nr)
            aus["ja"] = j
            aus["ja_fehlt"] = [ROLLEN_JA[r] for r in ROLLEN_JA if not j.get(r)]
    return aus


def freigabe_regel(con, pid):
    """A1937 (B2913): wer ein Thema freigibt – mensch (Vorgabe) | co+lead (Co-Entwickler und Lead je ein Ja; Marcel jederzeit)."""
    return kern.projekt_wahl(con, pid, "thema_freigabe")


def nur_mensch(ev):
    """A1937: Thema bleibt beim Menschen (Löschen, Kosten, Schema, Außenwirkung – G12): letzter Merker gesetzt?"""
    an = False
    for e in ev:
        if e["art"] == EREIGNIS["nur_mensch"]:
            an = bool(e.get("an"))
    return an


def jas(ev, fassung):
    """{"co": Kennung, "lead": Kennung} – die Ja zu genau dieser Fassung."""
    aus = {}
    for e in ev:
        if e["art"] == EREIGNIS["ja"] and e.get("fassung") == fassung:
            aus[e.get("rolle")] = e["von"]
    return aus


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
    vorher = tor(con, pid)
    with db.schreiben(con):
        _ereignis(con, pid, von, "freigegeben", t["id"], fassung=s["fassung"])
        _tor_nachher(con, pid, von, vorher)                                   # A1913: die letzte Freigabe schließt das Tor
        if an:
            kern._posten(con, pid, "AMW", an, "info", f"Thema „{t['name'][:60]}“ freigegeben (Fassung {s['fassung']})",
                         f"TH{t['id']}: {kern.entwickler_name(con, pid)} hat Fassung {s['fassung']} freigegeben.")
    from . import planer                             # A1940 (K4): ein freigegebenes Thema stößt den Planer an
    planer.anstossen(con, pid, t["id"], s["fassung"])
    return status(con, finden(con, pid, t["id"]))


def ja_geben(con, pid, von, name):
    """A1937 (B2913): Co-Entwickler oder Lead gibt sein Ja zur aktuellen Fassung. Mit beiden Ja ist das Thema freigegeben
    (Ereignis thema_freigegeben, von AMW, „durch“ beide). Nur bei thema_freigabe = co+lead und nicht bei Themen „nur der Mensch“."""
    if freigabe_regel(con, pid) != "co+lead":
        raise kern.AmwFehler("Themen gibt in diesem Projekt der Mensch frei (thema_freigabe = mensch)")
    if kern.ist_co(con, pid, von):
        rolle = "co"
    elif von != kern.ENTWICKLER and kern.ist_lead(con, pid, von):
        rolle = "lead"
    else:
        raise kern.AmwFehler("Ein Ja zur Freigabe geben der Co-Entwickler und der Lead (B2913) – sonst gibt der Mensch frei")
    t = finden(con, pid, name)
    s = status(con, t)
    if s.get("nur_mensch"):
        raise kern.AmwFehler(f"TH{t['id']} bleibt beim Menschen (Löschen, Kosten, Schema oder Außenwirkung) – er gibt es frei")
    if "freigeben" not in handlungen(s) or s["fassung"] is None:
        raise kern.AmwFehler(f"TH{t['id']} ist „{s['text']}“ – da steht keine Freigabe an")
    an = _an_pfleger(con, pid, t)
    vorher = tor(con, pid)
    with db.schreiben(con):
        _ereignis(con, pid, von, "ja", t["id"], fassung=s["fassung"], rolle=rolle)
        j = jas(_ereignisse(con, pid, t["id"]), s["fassung"])
        frei = bool(j.get("co") and j.get("lead"))
        if frei:
            _ereignis(con, pid, "AMW", "freigegeben", t["id"], regel=True, fassung=s["fassung"], durch=[j["co"], j["lead"]], regel_von="B2913")
            _tor_nachher(con, pid, "AMW", vorher)
            for k in dict.fromkeys(x for x in (an, kern.ENTWICKLER) if x):
                kern._posten(con, pid, "AMW", k, "info", f"Thema „{t['name'][:60]}“ freigegeben von Co und Lead (Fassung {s['fassung']})",
                             f"TH{t['id']}: {j['co']} (Co-Entwickler) und {j['lead']} (Lead) haben Fassung {s['fassung']} freigegeben (B2913)."
                             " Zurückholen kann der Mensch jederzeit: amw thema zurueck … --notiz …")
    if frei:                                         # A1940 (P462): auch die Freigabe durch Co und Lead stößt den Planer an
        from . import planer
        planer.anstossen(con, pid, t["id"], s["fassung"])
    return status(con, finden(con, pid, t["id"]))


def nur_mensch_setzen(con, pid, von, name, an=True):
    """A1937: Merker „nur der Mensch gibt frei“ – setzen Pfleger, Lead oder Mensch; aufheben nur der Mensch."""
    t = finden(con, pid, name)
    if an and not (von == kern.ENTWICKLER or von == t["pfleger"] or kern.ist_lead(con, pid, von)):
        raise kern.AmwFehler("„nur der Mensch“ setzen Pfleger, Lead oder Mensch")
    if not an and von != kern.ENTWICKLER:
        raise kern.AmwFehler("„nur der Mensch“ aufheben darf nur der Mensch")
    with db.schreiben(con):
        _ereignis(con, pid, von, "nur_mensch", t["id"], an=bool(an))
    return status(con, finden(con, pid, t["id"]))


def zurueck(con, pid, von, name, notiz):
    if not (notiz or "").strip():
        raise kern.AmwFehler("Zurück nur mit Notiz: was soll anders werden?")
    t, s = _handlung(con, pid, von, name, "zurueck")
    an = _an_pfleger(con, pid, t)
    with db.schreiben(con):
        _ereignis(con, pid, von, "zurueck", t["id"], fassung=s["fassung"], notiz=notiz.strip()[:2000])
        zurueck_bei = s["freigegeben"]
        if an:
            kern._posten(con, pid, "AMW", an, "auftrag", f"Thema „{t['name'][:60]}“ zurück: {notiz.strip()[:80]}",
                         f"TH{t['id']} (Fassung {s['fassung']}) – Notiz von {kern.entwickler_name(con, pid)}:\n{notiz.strip()}\n\n"
                         f"Neue Fassung: amw thema pflegen TH{t['id']} --text-datei …")
    if zurueck_bei:                                   # K8 (A1942): ein freigegebenes Thema zurück → Meilensteine prüfen
        from . import planansicht
        planansicht.folgen_melden(con, pid, t["id"], "zurück")
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
    vorher = tor(con, pid)
    with db.schreiben(con):
        f = _fassung(con, t["id"])
        nr = (f["nr"] if f else 0) + 1
        db.einfuegen(con, "thema_fassung", thema_id=t["id"], nr=nr, text=text.strip(), von=von, zeit_utc=db.jetzt())
        _ereignis(con, pid, von, "bearbeitet", t["id"], fassung=nr)
        _tor_nachher(con, pid, von, vorher)                                   # A1913: eigene Bearbeitung gilt als Freigabe
        if an:
            kern._posten(con, pid, "AMW", an, "info" if BEARBEITEN_GIBT_FREI else "auftrag",
                         f"Thema „{t['name'][:60]}“: Text von {kern.entwickler_name(con, pid)} geändert (Fassung {nr})",
                         f"TH{t['id']} Fassung {nr} stammt vom Menschen – "
                         + ("sie gilt als freigegeben; prüfe die Folgen für andere Themen und Aufgaben." if BEARBEITEN_GIBT_FREI
                            else f"bitte einarbeiten und als neue Fassung liefern: amw thema pflegen TH{t['id']} --text-datei …"))
    thema_geaendert(con, pid, t["id"], nr)           # A1915: betroffene Aufgaben prüfen lassen
    if BEARBEITEN_GIBT_FREI:                         # A1940: die eigene Bearbeitung gilt als Freigabe → Planer
        from . import planer
        planer.anstossen(con, pid, t["id"], nr)
    return status(con, finden(con, pid, t["id"]))


def markieren(con, pid, von, name, an=True):
    """Löschen markieren (B2894: gelöscht wird nichts – löschen tut der Mensch) bzw. die Markierung aufheben."""
    t, _ = _handlung(con, pid, von, name, "markieren" if an else "entmarkieren")
    vorher = tor(con, pid)
    with db.schreiben(con):
        _ereignis(con, pid, von, "markiert" if an else "entmarkiert", t["id"], fassung=None)
        _tor_nachher(con, pid, von, vorher)                                   # A1913: markierte zählen nicht
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


# --- Tor Konzept (A1913, D1304 v12 §2, Marcel W2449): kein Knopf „Tor schließen“ – das Tor schließt automatisch mit der letzten
# nötigen Freigabe; vorher sagt die Oberfläche „Damit schließt das Tor Konzept“. Der Zustand wird abgeleitet (kein Statusfeld):
# zu, wenn es zählende Themen gibt und alle freigegeben sind (markierte zählen nicht). Wird danach eines zurückgegeben, neu
# angelegt, neu vorgelegt oder auf „neu prüfen“ gesetzt, ist es wieder offen. Das Ereignis tor_geschlossen (Themen mit
# Fassungsnummern) hält nur fest, wann und womit es schloss – zur Nachvollziehbarkeit.
TORE = ("konzept", "grobplanung", "feinplanung", "umsetzung", "abschluss")
TOR_GESCHLOSSEN = "tor_geschlossen"


def _zustaende(con, pid):
    return {t["id"]: status(con, t) for t in con.execute("SELECT * FROM thema WHERE projekt_id = ?", (pid,)).fetchall()}


def _tor_aus(z):
    zaehlt = {k: s for k, s in z.items() if not s["markiert"]}
    n = sum(s["status"] == "frei" for s in zaehlt.values())
    zu = bool(zaehlt) and n == len(zaehlt)
    return {"tor": TORE[1] if zu else TORE[0], "konzept_zu": zu, "n": n, "g": len(zaehlt)}


def tor(con, pid, tid=None):
    """Wo das Projekt steht: {"tor": konzept|grobplanung, "konzept_zu", "n" (freigegeben), "g" (zählende Themen)}; mit tid dazu
    "schliesst": die Handlungen an diesem Thema, mit denen das Tor Konzept jetzt schlösse (für den Hinweis vorher)."""
    z = _zustaende(con, pid)
    aus = _tor_aus(z)
    if tid is not None and tid in z and not aus["konzept_zu"]:
        s = z[tid]
        nachher = {"freigeben": dict(s, status="frei", markiert=False),
                   "bearbeiten": dict(s, status="frei" if BEARBEITEN_GIBT_FREI else "arbeit", markiert=False),
                   "markieren": dict(s, markiert=True), "entmarkieren": dict(s, markiert=False)}
        aus["schliesst"] = [h for h in handlungen(s) if h in nachher and _tor_aus({**z, tid: nachher[h]})["konzept_zu"]]
    elif tid is not None:
        aus["schliesst"] = []
    return aus


def _tor_nachher(con, pid, von, vorher):
    """In der Transaktion des Aufrufers, nach der Handlung: schloss sie das Tor Konzept, das Ereignis dazu schreiben."""
    import json
    z = _zustaende(con, pid)
    if vorher["konzept_zu"] or not _tor_aus(z)["konzept_zu"]:
        return
    themen_ = [{"thema": k, "fassung": s["fassung"]} for k, s in sorted(z.items()) if not s["markiert"]]
    db.einfuegen(con, "plan_ereignis", projekt_id=pid, zeit_utc=db.jetzt(), von=von, art=TOR_GESCHLOSSEN,
                 text=json.dumps({"tor": TORE[0], "themen": themen_}, ensure_ascii=False))


def tor_ereignisse(con, pid):
    """Wann das Tor Konzept schloss und mit welchen Themen und Fassungen (neueste zuerst)."""
    import json
    aus = []
    for r in con.execute("SELECT id, von, zeit_utc, text FROM plan_ereignis WHERE projekt_id = ? AND art = ? ORDER BY id DESC",
                         (pid, TOR_GESCHLOSSEN)):
        try:
            aus.append({"id": r["id"], "von": r["von"], "zeit_utc": r["zeit_utc"], **json.loads(r["text"])})
        except ValueError:
            continue
    return aus


def konzept_zeile(con, pid, kennung):
    """A1949 (Co #30170, W2458): was ein Agent nach Start oder Kompaktierung liest – das Einstiegs-Thema des Projekts
    (Projekt-Einstellung konzept_einstieg) und nur das Thema seines laufenden Pakets; keine Konzept-Dokumente. Ohne laufendes
    Paket nur der Einstieg; ohne beides None."""
    import json
    from . import arbeitsliste
    r = con.execute("SELECT einstellungen FROM projekt WHERE id = ?", (pid,)).fetchone()
    try:
        einstieg = json.loads((r[0] if r else None) or "{}").get("konzept_einstieg")
    except ValueError:
        einstieg = None
    teile = []
    if einstieg:
        try:
            t = finden(con, pid, einstieg)
            teile.append(f"TH{t['id']} {t['name']} (Einstieg)")
        except kern.AmwFehler:
            pass
    a = arbeitsliste.laufend(con, pid, kennung)
    lesen = [f"TH{t['id']}" for t in ([finden(con, pid, einstieg)] if teile else [])]
    if a:
        ts = [finden(con, pid, x) for x in verweise(con, pid, a["id"])]
        if ts:
            teile.append(f"dein Paket A{a['id']} → " + ", ".join(f"TH{t['id']} {t['name']} (Fassung {status(con, t)['fassung'] or '–'})"
                                                                for t in ts))
            lesen += [f"TH{t['id']}" for t in ts]
        else:
            teile.append(f"dein Paket A{a['id']} hat noch kein Thema")
    if not teile:
        return None
    return ("Konzept: " + " · ".join(teile) + " – lesen: " + " · ".join(f"amw thema zeige {x}" for x in dict.fromkeys(lesen))
            + (" (nur diese; abgelöste Konzept-Dokumente nicht)" if lesen else ""))


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
    try:                                              # K8 (A1942): auch die Ebene Meilenstein – Vorschlag an den Lead
        from . import planansicht
        planansicht.folgen_melden(con, pid, tid, f"Fassung {nr}")
    except Exception:                                 # noqa: BLE001 – die Meldung darf die Fassung nie verhindern
        pass
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


# --- Lücken Thema ↔ Paket (A1947, Marcel W2458, Co #30113): kein Paket ohne Thema, kein freigegebenes Thema ohne Paket ---------
# Die AMW zeigt beide Lücken selbst (Planung, Fakt-Zeile) und weckt den Lead einmal je neuer Lücke (Dienst-Runde). Vermerke ohne
# Schemaänderung als Ereignisse: „nichts zu bauen“ je Thema (Grund; auch der Planer aus A1940 schreibt es) und „ohne Thema“ je
# Aufgabe (Grund: interne Pflege – Aufräumen, Fehlerbehebung).
NICHTS_ZU_BAUEN = "thema_nichts_zu_bauen"      # {"thema", "grund", "an"} – ohne "an" (Planer, A1940) gilt es als gesetzt
OHNE_THEMA = "aufgabe_ohne_thema"              # {"aufgabe", "grund"}
LUECKE_GEMELDET = "luecke_gemeldet"            # {"art": "thema" | "paket", "id"} – je Lücke einmal an den Lead


def nichts_zu_bauen(con, pid, von, name, grund, aufheben=False):
    """`amw thema vermerk TH<n> --nichts-zu-bauen --grund …` (bzw. --aufheben): Lead, Mensch oder Co-Entwickler."""
    if not (kern.ist_lead(con, pid, von) or kern.ist_co(con, pid, von)):
        raise kern.AmwFehler("„nichts zu bauen“ vermerken Lead, Mensch oder Co-Entwickler")
    if not aufheben and not (grund or "").strip():
        raise kern.AmwFehler("Grund fehlt: warum braucht das Thema kein Paket? (--grund …)")
    t = finden(con, pid, name)
    with db.schreiben(con):
        _ereignis_frei(con, pid, von, NICHTS_ZU_BAUEN, {"thema": t["id"], "grund": (grund or "").strip()[:1000], "an": not aufheben})
    return t["id"]


def _ereignis_frei(con, pid, von, art, daten, aufgabe_id=None):
    import json
    db.einfuegen(con, "plan_ereignis", projekt_id=pid, zeit_utc=db.jetzt(), von=von, art=art, aufgabe_id=aufgabe_id,
                 text=json.dumps(daten, ensure_ascii=False))


def ohne_thema_vermerken(con, pid, von, aid, grund):
    """Beim Anlegen (--ohne-thema-grund): die Aufgabe ist bewusst ohne Thema – interne Pflege. Kein Grund, kein Vermerk."""
    if not (grund or "").strip():
        raise kern.AmwFehler("--ohne-thema-grund: bitte einen Grund (z. B. Aufräumen, Fehlerbehebung)")
    with db.schreiben(con):
        _ereignis_frei(con, pid, von, OHNE_THEMA, {"aufgabe": aid, "grund": grund.strip()[:300]}, aufgabe_id=aid)


def _json_zeilen(con, pid, art):
    import json
    for r in con.execute("SELECT text FROM plan_ereignis WHERE projekt_id = ? AND art = ? ORDER BY id", (pid, art)):
        try:
            yield json.loads(r[0])
        except ValueError:
            continue


def nichts_vermerkt(con, pid):
    """{Thema: Grund} – Themen mit gültigem Vermerk „nichts zu bauen“ (der jüngste Eintrag je Thema gilt)."""
    aus = {}
    for d in _json_zeilen(con, pid, NICHTS_ZU_BAUEN):
        if d.get("an", True):
            aus[d.get("thema")] = d.get("grund") or ""
        else:
            aus.pop(d.get("thema"), None)
    return aus


def luecken(con, pid):
    """{"thema_ohne_paket": [{id, name}], "paket_ohne_thema": [{id, titel, agent, status}]} – nur, wenn das Projekt Themen hat.
    Thema ohne Paket: freigegeben (nicht zum Löschen markiert), keine verknüpfte Aufgabe (offen oder fertig; verworfene zählen
    nicht) und kein Vermerk „nichts zu bauen“. Paket ohne Thema: offene Aufgabe (nicht fertig/verworfen) ohne Thema-Verweis und
    ohne Vermerk „ohne Thema“."""
    themen_ = con.execute("SELECT * FROM thema WHERE projekt_id = ? ORDER BY name", (pid,)).fetchall()
    if not themen_:
        return {"thema_ohne_paket": [], "paket_ohne_thema": []}
    import json
    verweis = {}                                     # Aufgabe → Themen (der jüngste Eintrag je Paar gilt)
    for r in con.execute("SELECT aufgabe_id, text FROM plan_ereignis WHERE projekt_id = ? AND art = ? ORDER BY id", (pid, VERWEIS)):
        try:
            d = json.loads(r[1])
        except ValueError:
            continue
        (verweis.setdefault(r[0], set()).add if d.get("an") else verweis.setdefault(r[0], set()).discard)(d.get("thema"))
    status = dict(con.execute("SELECT id, status FROM aufgabe WHERE projekt_id = ?", (pid,)).fetchall())
    verknuepft = {t for aid, ts in verweis.items() if status.get(aid) not in (None, "verworfen") for t in ts}
    nichts = nichts_vermerkt(con, pid)
    ohne = {d.get("aufgabe") for d in _json_zeilen(con, pid, OHNE_THEMA)}
    tl = []
    for t in themen_:
        s = status_(con, t)
        if s["status"] == "frei" and not s["markiert"] and t["id"] not in verknuepft and t["id"] not in nichts:
            tl.append({"id": t["id"], "name": t["name"]})
    pl = [{"id": a["id"], "titel": a["titel"], "agent": a["agent"], "status": a["status"]}
          for a in con.execute("SELECT id, titel, agent, status FROM aufgabe WHERE projekt_id = ? AND status NOT IN ('fertig', 'verworfen')"
                               " ORDER BY id", (pid,)).fetchall()
          if not verweis.get(a["id"]) and a["id"] not in ohne]
    return {"thema_ohne_paket": tl, "paket_ohne_thema": pl}


status_ = status                                 # luecken() hat eine lokale Variable „status“


def luecken_melden(con, pid):
    """Dienst-Runde: neue Lücken (noch nie gemeldet) einmal als Frage an den Lead – nicht täglich wiederholt. Rückgabe: Texte."""
    lead = kern.lead(con, pid)
    if not lead or lead == kern.ENTWICKLER:
        return []
    l = luecken(con, pid)
    schon = {(d.get("art"), d.get("id")) for d in _json_zeilen(con, pid, LUECKE_GEMELDET)}
    neu_t = [x for x in l["thema_ohne_paket"] if ("thema", x["id"]) not in schon]
    neu_p = [x for x in l["paket_ohne_thema"] if ("paket", x["id"]) not in schon]
    if not neu_t and not neu_p:
        return []
    teile = ([f"{len(neu_t)} freigegebene(s) Thema/Themen ohne Paket"] if neu_t else []) + ([f"{len(neu_p)} Paket(e) ohne Thema"] if neu_p else [])
    text = ("Die AMW hat Lücken zwischen Themen und Paketen gefunden (A1947):\n"
            + "".join(f"\n- TH{x['id']} {x['name']} – freigegeben, aber kein Paket" for x in neu_t)
            + "".join(f"\n- A{x['id']} {x['titel'][:80]} ({x['agent'] or '–'}, {x['status']}) – ohne Thema" for x in neu_p[:40])
            + (f"\n- … und {len(neu_p) - 40} weitere" if len(neu_p) > 40 else "")
            + "\n\nSchließen: Paket anlegen bzw. verknüpfen (amw aufgabe aendern <nr> --thema TH…), „nichts zu bauen“ vermerken"
              " (amw thema vermerk TH… --nichts-zu-bauen --grund …) oder die Aufgabe ist interne Pflege (beim Anlegen"
              " --ohne-thema-grund …). Jede Lücke meldet die AMW nur einmal; offen stehen sie in der Planung.")
    with db.schreiben(con):
        kern._posten(con, pid, "AMW", lead, "frage", "Lücken Thema ↔ Paket: " + " · ".join(teile), text)
        for x in neu_t:
            _ereignis_frei(con, pid, "AMW", LUECKE_GEMELDET, {"art": "thema", "id": x["id"]})
        for x in neu_p:
            _ereignis_frei(con, pid, "AMW", LUECKE_GEMELDET, {"art": "paket", "id": x["id"]}, aufgabe_id=x["id"])
    return [f"{pid}: " + " · ".join(teile)]

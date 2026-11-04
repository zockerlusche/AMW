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
                    "ueberholt": z[1] or 0, "unklar": z[2] or 0, "zuletzt_utc": z[3], "stand": s, "veraltet_seit": seit})
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
            "ueberholt": [x for x in b if x["status"] == "ueberholt"], "dokumente": dok}


def neu(con, pid, von, name, pfleger=None, stil=False):
    if not kern.ist_lead(con, pid, von):
        raise kern.AmwFehler("Themen anlegen dürfen Lead und Entwickler")
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
    return nr


def bestaetigen(con, pid, von, name):
    t = finden(con, pid, name)
    _lead_oder_pfleger(con, pid, von, t, "Zusammenfassung bestätigen")
    if not _fassung(con, t["id"]):
        raise kern.AmwFehler("es gibt noch keine Zusammenfassung – amw thema pflegen …")
    with db.schreiben(con):
        con.execute("UPDATE thema SET bestaetigt_utc = ?, bestaetigt_von = ? WHERE id = ?", (db.jetzt(), von, t["id"]))


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

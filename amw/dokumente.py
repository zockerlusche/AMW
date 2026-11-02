"""Dokumente: Ergebnisse der Agenten (Ausarbeitungen, Berichte, Bilder, Mockups) an einem Ort (→ doc/plan-dokumente.md).

Der PC ist die Quelle: Dateien liegen unter <Datenordner>/dokumente/<aa>/<sha256>.<endung> – gleicher Inhalt nur einmal.
Ein Dokument hat Versionen (dokument_version); Kommentare und Überarbeitungs-Aufträge sind Nachrichten mit dokument_id
an den Verfasser. Endgültig löschen nur am PC; sonst archivieren.
"""
import hashlib
import html
import os
import re
import shutil
import zipfile

from . import db, kern

ARTEN = ("ergebnis", "bericht", "entwurf", "mockup", "bild", "quelle")
# Endung → (Format, MIME-Typ, Vorschau). Vorschau: text | bild | mockup | pdf | download
FORMATE = {
    ".md": ("markdown", "text/markdown; charset=utf-8", "text"),
    ".txt": ("text", "text/plain; charset=utf-8", "text"),
    ".png": ("bild", "image/png", "bild"), ".jpg": ("bild", "image/jpeg", "bild"), ".jpeg": ("bild", "image/jpeg", "bild"),
    ".webp": ("bild", "image/webp", "bild"), ".gif": ("bild", "image/gif", "bild"), ".svg": ("bild", "image/svg+xml", "bild"),
    ".html": ("html", "text/html; charset=utf-8", "mockup"), ".htm": ("html", "text/html; charset=utf-8", "mockup"),
    ".pdf": ("pdf", "application/pdf", "pdf"),
    ".docx": ("docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "download"),
    ".xlsx": ("xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "download"),
}
GROESSE_MAX = 25 * 1024 * 1024
SUCHTEXT_MAX = 200_000
# Muster, die nach Schlüsseln/Zugangsdaten aussehen – solche Texte kommen nicht in die Ablage (und nie online)
GEHEIM = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----|\b(?:sk-(?:ant-)?[A-Za-z0-9_-]{20,}|gh[pousr]_[A-Za-z0-9]{30,}"
                    r"|AKIA[0-9A-Z]{16}|xox[baprs]-[A-Za-z0-9-]{10,}|eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.)")
BEZUG = {"bogen": "bogen", "aufgabe": "aufgabe", "frage": "frage", "beschluss": "beschluss"}


def ordner():
    return os.path.join(os.path.dirname(os.path.abspath(db.db_pfad())), "dokumente")


def datei_pfad(sha, endung):
    return os.path.join(ordner(), sha[:2], sha + endung)


def _format(pfad):
    endung = os.path.splitext(pfad)[1].lower()
    if endung not in FORMATE:
        raise kern.AmwFehler(f"Format {endung or '(ohne Endung)'} nicht erlaubt – erlaubt: {', '.join(sorted(FORMATE))}"
                             " (Text bitte als Markdown .md)")
    return endung


def _suchtext(roh, endung):
    """Text für die Suche: Markdown/Text direkt, HTML ohne Tags, DOCX aus dem Word-XML."""
    if endung in (".md", ".txt", ".html", ".htm", ".svg"):
        t = roh.decode("utf-8", errors="replace")
        if endung in (".html", ".htm", ".svg"):
            t = html.unescape(re.sub(r"<script.*?</script>|<style.*?</style>|<[^>]+>", " ", t, flags=re.S | re.I))
        return re.sub(r"[ \t]+", " ", t)[:SUCHTEXT_MAX]
    if endung == ".docx":
        try:
            import io
            with zipfile.ZipFile(io.BytesIO(roh)) as z:
                xml = z.read("word/document.xml").decode("utf-8", errors="replace")
            return html.unescape(re.sub(r"<[^>]+>", " ", xml.replace("</w:p>", "\n")))[:SUCHTEXT_MAX]
        except (KeyError, zipfile.BadZipFile):
            return ""
    return ""


def _lesen(pfad):
    if not os.path.isfile(pfad):
        raise kern.AmwFehler(f"Datei {pfad} gibt es nicht")
    endung = _format(pfad)
    if os.path.getsize(pfad) > GROESSE_MAX:
        raise kern.AmwFehler(f"Datei ist größer als {GROESSE_MAX // 1024 // 1024} MB – bitte verkleinern oder aufteilen")
    with open(pfad, "rb") as f:
        roh = f.read()
    suchtext = _suchtext(roh, endung)
    probe = roh.decode("utf-8", errors="replace") if endung in (".md", ".txt", ".html", ".htm", ".svg") else suchtext
    if probe and GEHEIM.search(probe):                  # Rohtext: auch Skripte im Mockup
        raise kern.AmwFehler("Die Datei enthält etwas, das wie ein Schlüssel oder Zugangsdaten aussieht – nicht abgelegt")
    return roh, endung, suchtext


def _speichern(roh, endung):
    sha = hashlib.sha256(roh).hexdigest()
    ziel = datei_pfad(sha, endung)
    if not os.path.exists(ziel):
        os.makedirs(os.path.dirname(ziel), exist_ok=True)
        with open(ziel + ".neu", "wb") as f:
            f.write(roh)
        os.replace(ziel + ".neu", ziel)
    return sha


def _bezug(con, pid, bogen=None, aufgabe=None, frage=None, beschluss=None):
    gesetzt = [(k, v) for k, v in (("bogen", bogen), ("aufgabe", aufgabe), ("frage", frage), ("beschluss", beschluss)) if v]
    if len(gesetzt) > 1:
        raise kern.AmwFehler("Nur ein Bezug: Bogen, Aufgabe, Frage oder Beschluss")
    if not gesetzt:
        return None, None
    art, nr = gesetzt[0]
    nr = int(str(nr).lstrip("ABFabf"))
    if not con.execute(f"SELECT 1 FROM {BEZUG[art]} WHERE id = ? AND projekt_id = ?", (nr, pid)).fetchone():
        raise kern.AmwFehler(f"{art.capitalize()} {nr} gibt es nicht")
    return art, nr


def ablegen(con, pid, von, pfad, titel=None, art="ergebnis", notiz=None, online=False, **bezug):
    """Neues Dokument mit Version 1. bezug: bogen=, aufgabe=, frage= oder beschluss= (Nummer)."""
    if art not in ARTEN:
        raise kern.AmwFehler(f"Art {art} – erlaubt: {', '.join(ARTEN)}")
    b_art, b_id = _bezug(con, pid, **bezug)
    roh, endung, suchtext = _lesen(pfad)
    titel = (titel or "").strip() or os.path.splitext(os.path.basename(pfad))[0]
    sha = _speichern(roh, endung)
    t = db.jetzt()
    with db.schreiben(con):
        did = db.einfuegen(con, "dokument", projekt_id=pid, titel=titel[:200], art=art, bezug_art=b_art, bezug_id=b_id,
                           status="aktuell", online=int(bool(online)), angelegt_von=von, angelegt_utc=t)
        db.einfuegen(con, "dokument_version", dokument_id=did, nr=1, sha256=sha, endung=endung, groesse=len(roh),
                     notiz=notiz, von=von, zeit_utc=t, suchtext=suchtext)
    return did


def version(con, pid, von, did, pfad, notiz=None):
    """Neue Version (Überarbeitung). Gleicher Inhalt wie die letzte Version → Fehler."""
    d = dokument(con, pid, did)
    if d["status"] == "geloescht":
        raise kern.AmwFehler(f"D{did} ist gelöscht")
    roh, endung, suchtext = _lesen(pfad)
    sha = _speichern(roh, endung)
    letzte = d["versionen"][-1]
    if letzte["sha256"] == sha:
        raise kern.AmwFehler(f"Inhalt gleich wie Version {letzte['nr']} – keine neue Version")
    with db.schreiben(con):
        nr = letzte["nr"] + 1
        db.einfuegen(con, "dokument_version", dokument_id=did, nr=nr, sha256=sha, endung=endung, groesse=len(roh),
                     notiz=notiz, von=von, zeit_utc=db.jetzt(), suchtext=suchtext)
        if d["status"] == "archiviert":
            con.execute("UPDATE dokument SET status = 'aktuell' WHERE id = ?", (did,))
    return nr


def dokument(con, pid, did):
    d = con.execute("SELECT * FROM dokument WHERE id = ? AND projekt_id = ?", (did, pid)).fetchone()
    if not d:
        raise kern.AmwFehler(f"Dokument D{did} gibt es nicht")
    aus = dict(d)
    aus["versionen"] = [dict(v) for v in con.execute(
        "SELECT id, nr, sha256, endung, groesse, notiz, von, zeit_utc FROM dokument_version WHERE dokument_id = ? ORDER BY nr", (did,))]
    for v in aus["versionen"]:
        v["format"], _, v["vorschau"] = FORMATE.get(v["endung"], ("?", "", "download"))
    return aus


def liste(con, pid, art=None, bezug_art=None, bezug_id=None, von=None, q=None, status="aktuell", grenze=500):
    """Neueste zuerst; je Dokument die letzte Version. q sucht in Titel und Text aller Versionen."""
    sql = ("SELECT d.*, v.nr AS version, v.endung, v.groesse, v.zeit_utc AS version_utc, v.von AS version_von, v.sha256"
           " FROM dokument d JOIN dokument_version v ON v.dokument_id = d.id"
           " AND v.nr = (SELECT max(nr) FROM dokument_version WHERE dokument_id = d.id) WHERE d.projekt_id = ?")
    par = [pid]
    if status:
        sql += " AND d.status = ?"
        par.append(status)
    for spalte, wert in (("d.art", art), ("d.bezug_art", bezug_art), ("d.bezug_id", bezug_id), ("d.angelegt_von", von)):
        if wert not in (None, ""):
            sql += f" AND {spalte} = ?"
            par.append(wert)
    if q:
        sql += (" AND (d.titel LIKE ? OR EXISTS (SELECT 1 FROM dokument_version x WHERE x.dokument_id = d.id"
                " AND x.suchtext LIKE ?))")
        par += [f"%{q}%"] * 2
    aus = [dict(r) for r in con.execute(sql + " ORDER BY v.zeit_utc DESC, d.id DESC LIMIT ?", (*par, grenze))]
    for d in aus:
        d["format"], _, d["vorschau"] = FORMATE.get(d["endung"], ("?", "", "download"))
    return aus


def zaehler(con, pid, art, nr):
    """Wie viele aktuelle Dokumente an einem Bogen/einer Aufgabe/Frage hängen (für Karten in der Workbench)."""
    return con.execute("SELECT count(*) FROM dokument WHERE projekt_id = ? AND bezug_art = ? AND bezug_id = ?"
                       " AND status = 'aktuell'", (pid, art, nr)).fetchone()[0]


def setzen(con, pid, von, did, titel=None, art=None, **bezug):
    """Titel, Art oder Bezug ändern (Zuordnen). bezug mit leerem Wert = Bezug lösen."""
    dokument(con, pid, did)
    felder = {}
    if titel and titel.strip():
        felder["titel"] = titel.strip()[:200]
    if art:
        if art not in ARTEN:
            raise kern.AmwFehler(f"Art {art} – erlaubt: {', '.join(ARTEN)}")
        felder["art"] = art
    if bezug:
        b_art, b_id = _bezug(con, pid, **{k: v for k, v in bezug.items() if v not in (None, "", 0, "0")})
        felder["bezug_art"], felder["bezug_id"] = b_art, b_id
    if felder:
        with db.schreiben(con):
            con.execute(f"UPDATE dokument SET {', '.join(k + ' = ?' for k in felder)} WHERE id = ?", (*felder.values(), did))
    return dokument(con, pid, did)


def status_setzen(con, pid, von, did, status):
    """aktuell | archiviert. Endgültig löschen: loeschen()."""
    if status not in ("aktuell", "archiviert"):
        raise kern.AmwFehler("Status aktuell oder archiviert")
    dokument(con, pid, did)
    with db.schreiben(con):
        con.execute("UPDATE dokument SET status = ? WHERE id = ? AND status != 'geloescht'", (status, did))


def online_setzen(con, pid, von, did, an=True):
    """Datei bei Bedarf auch online zeigen (Texte sind immer online) – der Abgleich lädt sie hoch."""
    dokument(con, pid, did)
    with db.schreiben(con):
        con.execute("UPDATE dokument SET online = ? WHERE id = ?", (int(bool(an)), did))


def loeschen(con, pid, von, did):
    """Endgültig (nur Entwickler, nur am PC): Dateien weg, die Zeile bleibt als „geloescht“ für den Verlauf."""
    if von != kern.ENTWICKLER:
        raise kern.AmwFehler("Endgültig löschen darf nur der Entwickler (am PC)")
    d = dokument(con, pid, did)
    with db.schreiben(con):
        con.execute("UPDATE dokument SET status = 'geloescht', online = 0 WHERE id = ?", (did,))
    weg = 0
    for v in d["versionen"]:                          # eine Datei kann zu mehreren Dokumenten gehören (gleicher Inhalt)
        andere = con.execute("SELECT count(*) FROM dokument_version x JOIN dokument y ON y.id = x.dokument_id"
                             " WHERE x.sha256 = ? AND y.status != 'geloescht'", (v["sha256"],)).fetchone()[0]
        p = datei_pfad(v["sha256"], v["endung"])
        if not andere and os.path.exists(p):
            os.remove(p)
            weg += 1
    return weg


def inhalt(con, pid, did, nr=None):
    """(bytes, endung) der Version nr (Vorgabe: letzte)."""
    d = dokument(con, pid, did)
    if d["status"] == "geloescht":
        raise kern.AmwFehler(f"D{did} ist gelöscht")
    v = next((v for v in d["versionen"] if v["nr"] == nr), None) if nr else d["versionen"][-1]
    if not v:
        raise kern.AmwFehler(f"D{did} hat keine Version {nr}")
    p = datei_pfad(v["sha256"], v["endung"])
    if not os.path.exists(p):
        raise kern.AmwFehler(f"Datei von D{did} v{v['nr']} fehlt in der Ablage")
    with open(p, "rb") as f:
        return f.read(), v["endung"]


def melden(con, pid, von, did, text, ueberarbeiten=False):
    """Kommentar (oder Überarbeitungs-Auftrag) an den Verfasser – als Nachricht mit Dokument-Bezug, weckt ihn."""
    d = dokument(con, pid, did)
    text = (text or "").strip()
    if not text:
        raise kern.AmwFehler("Text fehlt")
    an = d["versionen"][-1]["von"] if d["versionen"][-1]["von"] != von else d["angelegt_von"]
    if an == von:
        an = kern.lead(con, pid) or kern.ENTWICKLER
    kurz = (f"Überarbeiten D{did} „{d['titel']}“" if ueberarbeiten else f"Kommentar zu D{did} „{d['titel']}“")[:300]
    with db.schreiben(con):
        nid, namen = kern._posten(con, pid, von, an, "auftrag" if ueberarbeiten else "meldung", kurz,
                                  text + f"\n\n(Dokument D{did}, v{d['versionen'][-1]['nr']}: `amw dokument zeigen {did}`"
                                  + (f"; neue Version: `amw dokument version {did} <datei> --notiz …`)" if ueberarbeiten else ")"),
                                  aufgabe_id=d["bezug_id"] if d["bezug_art"] == "aufgabe" else None)
        con.execute("UPDATE nachricht SET dokument_id = ? WHERE id = ?", (did, nid))
    return nid, namen


def gespraech(con, pid, did):
    return [dict(r) for r in con.execute(
        "SELECT n.id, n.zeit_utc, n.von, n.art, n.kurz, n.text, (SELECT group_concat(agent, ', ') FROM empfang"
        " WHERE nachricht_id = n.id) AS an FROM nachricht n WHERE n.projekt_id = ? AND n.dokument_id = ? ORDER BY n.id",
        (pid, did))]


def sichern(ziel_ordner):
    """Ablage neben eine Datenbank-Sicherung kopieren (nur, was dort fehlt). Rückgabe: Anzahl kopierter Dateien."""
    quelle = ordner()
    if not os.path.isdir(quelle):
        return 0
    n = 0
    for wurzel, _, dateien in os.walk(quelle):
        for name in dateien:
            if name.endswith(".neu"):
                continue
            q = os.path.join(wurzel, name)
            z = os.path.join(ziel_ordner, os.path.relpath(q, quelle))
            if not os.path.exists(z):
                os.makedirs(os.path.dirname(z), exist_ok=True)
                shutil.copy2(q, z)
                n += 1
    return n

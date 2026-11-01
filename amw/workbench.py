"""Workbench-Oberfläche: kleiner HTTP-Server nur auf 127.0.0.1 (→ doc/02 §0, doc/10 §2, doc/05 §6).

Liefert eine Seite (workbench.html) und eine JSON-Schnittstelle. Läuft als Faden im amw-dienst oder allein:
  python -X utf8 -m amw.workbench [--port 8780]
Sicherheit (Stufe 1): nur 127.0.0.1; Schreibwege nur mit dem Sitzungs-Schlüssel der Seite (X-AMW-Token, bei jedem
Serverstart neu) und passendem Host/Origin; nur parametrisierte Abfragen; die Seite setzt Text nur über textContent.
Schreibt ausschließlich über kern (als „Entwickler“).
"""
import argparse
import json
import os
import secrets
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from . import db, kern
from .betrieb import speicher_frei_gb

STANDARD_PORT = 8780
HIER = os.path.dirname(os.path.abspath(__file__))


def zeilen(cur):
    return [dict(r) for r in cur.fetchall()]


# --- Lesen ---------------------------------------------------------------------------------------

def daten_start(con, pid):
    agenten = zeilen(con.execute(
        "SELECT g.kennung, g.rolle, g.soll, g.grenzen, s.zustand, s.letzter_puls_utc, s.gestartet_utc,"
        " (SELECT count(*) FROM empfang e JOIN nachricht n ON n.id = e.nachricht_id"
        "   WHERE e.agent = g.kennung AND n.projekt_id = g.projekt_id AND e.status = 'offen') AS offen,"
        " (SELECT id || ' · ' || titel FROM aufgabe WHERE projekt_id = g.projekt_id AND agent = g.kennung"
        "   AND status = 'laeuft' ORDER BY begonnen_utc DESC LIMIT 1) AS laeuft"
        " FROM agent g LEFT JOIN sitzung s ON s.id = (SELECT max(id) FROM sitzung WHERE agent_id = g.id)"
        " WHERE g.projekt_id = ? ORDER BY g.id", (pid,)))
    fragen = zeilen(con.execute(
        "SELECT id, kurz, von, zeit_utc, blockiert FROM frage WHERE projekt_id = ? AND an = 'entwickler'"
        " AND status = 'offen' AND kurz NOT LIKE 'GEPARKT%' ORDER BY blockiert DESC, id DESC LIMIT 20", (pid,)))
    halte = [dict(s) for s in kern.aktive_sperren(con, pid, art="halt")]
    zaehler = dict(con.execute(
        "SELECT"
        " (SELECT count(*) FROM frage WHERE projekt_id = :p AND an = 'entwickler' AND status = 'offen'"
        "   AND kurz NOT LIKE 'GEPARKT%') AS fragen,"
        " (SELECT count(*) FROM aufgabe WHERE projekt_id = :p AND status IN ('wartet','laeuft','blockiert')"
        "   AND einstufung IN ('aktiv','keine_prio')) AS offen,"
        " (SELECT count(*) FROM aufgabe WHERE projekt_id = :p AND einstufung = 'geparkt'"
        "   AND status NOT IN ('fertig','verworfen')) AS geparkt,"
        " (SELECT count(*) FROM beschluss WHERE projekt_id = :p AND status = 'gilt') AS beschluesse,"
        " (SELECT count(*) FROM regel WHERE ebene = 'arbeit' OR projekt_id = :p) AS regeln,"
        " (SELECT count(*) FROM release WHERE projekt_id = :p) AS releases", {"p": pid}).fetchone())
    frei, gesamt = speicher_frei_gb()
    return {"agenten": agenten, "fragen": fragen, "halt": halte, "zaehler": zaehler,
            "speicher": {"frei": frei, "gesamt": gesamt}, "zeit": db.jetzt()}


def vorgeschichte(con, pid, f):
    v = []
    if f["aufgabe_id"]:
        a = con.execute("SELECT id, titel, status, agent, bemerkung FROM aufgabe WHERE id = ?", (f["aufgabe_id"],)).fetchone()
        if a:
            v.append({"art": "aufgabe", "ref": f"A{a['id']}", "titel": a["titel"],
                      "text": (a["bemerkung"] or "")[-900:], "zusatz": f"{a['status']} · {a['agent'] or '–'}"})
    vor, tiefe = f["folge_von"], 0
    while vor and tiefe < 5:
        p = con.execute("SELECT id, kurz, antwort, folge_von FROM frage WHERE id = ?", (vor,)).fetchone()
        if not p:
            break
        v.append({"art": "frage", "ref": f"F{p['id']}", "titel": p["kurz"], "text": p["antwort"] or "(offen)"})
        vor, tiefe = p["folge_von"], tiefe + 1
    muster = [f"%Frage {f['id']}%", f"%F{f['id']} %", f"%F-{f['id']}%"]
    for b in con.execute("SELECT id, zeit_utc, stichwort, regel FROM beschluss WHERE projekt_id = ? AND"
                         " (regel LIKE ? OR regel LIKE ? OR regel LIKE ? OR quelle LIKE ?) ORDER BY id DESC LIMIT 5",
                         (pid, *muster, muster[0])):
        v.append({"art": "beschluss", "ref": f"B{b['id']}", "titel": b["stichwort"], "text": b["regel"][:600],
                  "zeit": b["zeit_utc"]})
    bedingung = "kurz LIKE ? OR kurz LIKE ? OR kurz LIKE ?"
    par = list(muster)
    if f["aufgabe_id"]:
        bedingung += " OR aufgabe_id = ?"
        par.append(f["aufgabe_id"])
    for n in con.execute(f"SELECT id, zeit_utc, von, kurz FROM nachricht WHERE projekt_id = ? AND ({bedingung})"
                         " ORDER BY id DESC LIMIT 6", (pid, *par)):
        v.append({"art": "nachricht", "ref": f"#{n['id']}", "titel": n["kurz"], "text": n["von"], "zeit": n["zeit_utc"]})
    return v


def daten_fragen(con, pid, alle=False):
    sql = "SELECT * FROM frage WHERE projekt_id = ? AND an = 'entwickler' AND status = 'offen'"
    if not alle:
        sql += " AND kurz NOT LIKE 'GEPARKT%'"
    aus = []
    for f in con.execute(sql + " ORDER BY blockiert DESC, id DESC LIMIT 60", (pid,)).fetchall():
        d = dict(f)
        d["optionen"] = json.loads(f["optionen"] or "[]")
        d["vorgeschichte"] = vorgeschichte(con, pid, f)
        aus.append(d)
    return aus


def daten_aufgaben(con, pid, q):
    sql = ("SELECT id, titel, agent, status, einstufung, rang, wartet_auf, angelegt_utc, fertig_utc FROM aufgabe"
           " WHERE projekt_id = ?")
    par = [pid]
    sicht = q.get("sicht", ["offen"])[0]
    if sicht == "offen":
        sql += " AND status IN ('wartet','laeuft','blockiert') AND einstufung IN ('aktiv','keine_prio')"
    elif sicht == "geparkt":
        sql += " AND einstufung = 'geparkt' AND status NOT IN ('fertig','verworfen')"
    elif sicht == "pool":
        sql += " AND einstufung = 'pool' AND status NOT IN ('fertig','verworfen')"
    elif sicht == "erledigt":
        sql += " AND status IN ('fertig','verworfen')"
    if q.get("agent", [""])[0]:
        sql += " AND agent = ?"
        par.append(q["agent"][0])
    if q.get("q", [""])[0]:
        sql += " AND (titel LIKE ? OR bemerkung LIKE ?)"
        par += [f"%{q['q'][0]}%"] * 2
    ordnung = " ORDER BY fertig_utc DESC" if sicht == "erledigt" else " ORDER BY rang, id DESC"
    return zeilen(con.execute(sql + ordnung + " LIMIT 400", par))


def daten_wissen(con, pid, q):
    such = q.get("q", [""])[0].strip()
    muster = f"%{such}%"
    if such:
        b = con.execute("SELECT id, zeit_utc, thema, stichwort, regel, quelle, status FROM beschluss WHERE projekt_id = ?"
                        " AND (stichwort LIKE ? OR regel LIKE ?) ORDER BY id DESC LIMIT 80", (pid, muster, muster))
        w = con.execute("SELECT id, zeit_utc, text, kanal FROM wortlaut WHERE projekt_id = ? AND text LIKE ?"
                        " ORDER BY id DESC LIMIT 80", (pid, muster))
    else:
        b = con.execute("SELECT id, zeit_utc, thema, stichwort, regel, quelle, status FROM beschluss WHERE projekt_id = ?"
                        " AND status = 'gilt' ORDER BY id DESC LIMIT 60", (pid,))
        w = con.execute("SELECT id, zeit_utc, text, kanal FROM wortlaut WHERE projekt_id = ? ORDER BY id DESC LIMIT 60",
                        (pid,))
    r = con.execute("SELECT ebene, nr, teil, text, stand_utc FROM regel WHERE (ebene = 'arbeit' OR projekt_id = ?)"
                    + (" AND text LIKE ?" if such else "") + " ORDER BY ebene, nr", (pid, muster) if such else (pid,))
    return {"beschluesse": zeilen(b), "wortlaut": zeilen(w), "regeln": zeilen(r)}


def daten_suche(con, pid, q):
    such = q.get("q", [""])[0].strip()
    if len(such) < 2:
        return []
    m = f"%{such}%"
    teile = [
        ("aufgabe", "SELECT 'A' || id AS ref, titel AS titel, status AS zusatz, angelegt_utc AS zeit FROM aufgabe"
                    " WHERE projekt_id = ? AND (titel LIKE ? OR bemerkung LIKE ?)", 3),
        ("beschluss", "SELECT 'B' || id, stichwort, status, zeit_utc FROM beschluss WHERE projekt_id = ?"
                      " AND (stichwort LIKE ? OR regel LIKE ?)", 3),
        ("frage", "SELECT 'F' || id, kurz, status, zeit_utc FROM frage WHERE projekt_id = ? AND (kurz LIKE ? OR antwort LIKE ?)", 3),
        ("wortlaut", "SELECT 'W' || id, substr(text, 1, 200), kanal, zeit_utc FROM wortlaut WHERE projekt_id = ? AND text LIKE ?", 2),
        ("nachricht", "SELECT '#' || id, kurz, von, zeit_utc FROM nachricht WHERE projekt_id = ? AND (kurz LIKE ? OR text LIKE ?)", 3),
    ]
    aus = []
    for art, sql, n in teile:
        for r in con.execute(sql + " ORDER BY 4 DESC LIMIT 25", (pid, *[m] * (n - 1))):
            aus.append({"art": art, "ref": r[0], "titel": r[1], "zusatz": r[2], "zeit": r[3]})
    return aus


def daten_betrieb(con, pid):
    sitz = zeilen(con.execute(
        "SELECT g.kennung, s.zustand, s.gestartet_utc, s.letzter_puls_utc, s.beendet_utc FROM sitzung s"
        " JOIN agent g ON g.id = s.agent_id WHERE g.projekt_id = ? ORDER BY s.id DESC LIMIT 30", (pid,)))
    laeufe = zeilen(con.execute("SELECT id, agent, beschreibung, status, angemeldet_utc, start_utc, ende_utc, rc"
                                " FROM lauf WHERE projekt_id = ? ORDER BY id DESC LIMIT 30", (pid,)))
    sperren = [dict(s) for s in kern.aktive_sperren(con, pid)]
    logdatei = os.path.join(os.path.dirname(db.db_pfad()), "dienst.log")
    log = []
    if os.path.exists(logdatei):
        with open(logdatei, encoding="utf-8", errors="replace") as f:
            log = f.readlines()[-25:]
    frei, gesamt = speicher_frei_gb()
    return {"sitzungen": sitz, "laeufe": laeufe, "sperren": sperren, "log": [z.rstrip() for z in log],
            "speicher": {"frei": frei, "gesamt": gesamt}, "db": db.db_pfad()}


def daten_releases(con, pid):
    return zeilen(con.execute("SELECT id, art, version, zeit_utc, commit_sha, titel, text_intern, aufgaben,"
                              " veroeffentlicht_utc FROM release WHERE projekt_id = ? ORDER BY zeit_utc DESC LIMIT 200",
                              (pid,)))


# --- Server --------------------------------------------------------------------------------------

def baue_handler(port, token):
    with open(os.path.join(HIER, "workbench.html"), encoding="utf-8") as f:
        seite = f.read().replace("__AMW_TOKEN__", token).encode("utf-8")
    erlaubt = {f"127.0.0.1:{port}", f"localhost:{port}"}

    class Handler(BaseHTTPRequestHandler):
        server_version = "amw-workbench"

        def log_message(self, *args):
            pass

        def _senden(self, code, daten, typ="application/json; charset=utf-8"):
            body = daten if isinstance(daten, bytes) else json.dumps(daten, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", typ)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Referrer-Policy", "no-referrer")
            if typ.startswith("text/html"):
                self.send_header("Content-Security-Policy",
                                 "default-src 'none'; script-src 'self' 'unsafe-inline'; style-src 'unsafe-inline';"
                                 " connect-src 'self'; img-src 'self' data:; base-uri 'none'; form-action 'none'")
            self.end_headers()
            self.wfile.write(body)

        def _projekt(self, con, q):
            name = q.get("projekt", [""])[0]
            if name:
                return db.projekt_id(con, name)
            return con.execute("SELECT min(id) FROM projekt").fetchone()[0]

        def do_GET(self):
            if self.headers.get("Host") not in erlaubt:
                return self._senden(403, {"fehler": "Host"})
            u = urlparse(self.path)
            q = parse_qs(u.query)
            if u.path in ("/", "/index.html"):
                return self._senden(200, seite, "text/html; charset=utf-8")
            wege = {"/api/start": lambda c, p: daten_start(c, p),
                    "/api/fragen": lambda c, p: daten_fragen(c, p, q.get("alle", ["0"])[0] == "1"),
                    "/api/aufgaben": lambda c, p: daten_aufgaben(c, p, q),
                    "/api/wissen": lambda c, p: daten_wissen(c, p, q),
                    "/api/suche": lambda c, p: daten_suche(c, p, q),
                    "/api/betrieb": lambda c, p: daten_betrieb(c, p),
                    "/api/releases": lambda c, p: daten_releases(c, p),
                    "/api/projekte": lambda c, p: zeilen(c.execute("SELECT id, name FROM projekt ORDER BY id"))}
            weg = wege.get(u.path)
            if not weg:
                return self._senden(404, {"fehler": "unbekannt"})
            try:
                con = db.verbinde(nur_lesen=True)
                try:
                    return self._senden(200, weg(con, self._projekt(con, q)))
                finally:
                    con.close()
            except Exception as e:
                return self._senden(500, {"fehler": f"{type(e).__name__}: {e}"})

        def do_POST(self):
            herkunft = self.headers.get("Origin")
            if (self.headers.get("Host") not in erlaubt or self.headers.get("X-AMW-Token") != token
                    or (herkunft and herkunft.split("//", 1)[-1] not in erlaubt)):
                return self._senden(403, {"fehler": "nicht erlaubt"})
            try:
                laenge = min(int(self.headers.get("Content-Length") or 0), 100_000)
                daten = json.loads(self.rfile.read(laenge) or b"{}")
            except ValueError:
                return self._senden(400, {"fehler": "JSON"})
            u = urlparse(self.path)
            q = parse_qs(u.query)
            try:
                con = db.verbinde()
                try:
                    pid = self._projekt(con, q)
                    teile = u.path.strip("/").split("/")
                    if teile[:2] == ["api", "frage"] and len(teile) == 4 and teile[3] == "antwort":
                        art = daten.get("art")
                        wert = (daten.get("wert") or "").strip()
                        if art not in ("option", "text", "rueckfrage") or not wert:
                            return self._senden(400, {"fehler": "art/wert fehlt"})
                        st = kern.frage_antworten(con, pid, int(teile[2]), art, wert, "seite")
                        if art == "option" and (daten.get("anmerkung") or "").strip():
                            with db.schreiben(con):
                                t = db.jetzt()
                                db.einfuegen(con, "wortlaut", projekt_id=pid, zeit_utc=t, text=daten["anmerkung"].strip(),
                                             kanal="seite", erfasst_von="amw", erfasst_utc=t,
                                             bemerkung=f"Anmerkung zur Antwort auf F{teile[2]} (Option {wert})")
                        return self._senden(200, {"status": st})
                    if u.path == "/api/nachricht":
                        art = daten.get("art") or "auftrag"
                        if art not in ("auftrag", "frage", "info", "korrektur", "freigabe"):
                            return self._senden(400, {"fehler": "Art nicht erlaubt"})
                        kurz = (daten.get("kurz") or "").strip()
                        if not kurz or not (daten.get("an") or "").strip():
                            return self._senden(400, {"fehler": "an/kurz fehlt"})
                        nid, namen = kern.posten(con, pid, kern.ENTWICKLER, daten["an"], art, kurz[:300],
                                                 (daten.get("text") or "").strip() or None)
                        return self._senden(200, {"nachricht": nid, "an": namen})
                    if u.path == "/api/halt":
                        sid = kern.halt(con, pid, kern.ENTWICKLER, daten.get("fuer") or "alle",
                                        (daten.get("text") or "Halt vom Entwickler").strip())
                        return self._senden(200, {"halt": sid})
                    if u.path == "/api/weiter":
                        return self._senden(200, {"aufgehoben": kern.weiter(con, pid, kern.ENTWICKLER,
                                                                            daten.get("fuer") or "alle")})
                    return self._senden(404, {"fehler": "unbekannt"})
                finally:
                    con.close()
            except kern.AmwFehler as e:
                return self._senden(409, {"fehler": str(e)})
            except Exception as e:
                return self._senden(500, {"fehler": f"{type(e).__name__}: {e}"})

    return Handler


def starten(port=STANDARD_PORT, im_hintergrund=True):
    token = secrets.token_urlsafe(24)
    srv = ThreadingHTTPServer(("127.0.0.1", port), baue_handler(port, token))
    srv.daemon_threads = True
    if im_hintergrund:
        threading.Thread(target=srv.serve_forever, name="workbench", daemon=True).start()
    return srv


def main(argv=None):
    p = argparse.ArgumentParser(prog="amw-workbench")
    p.add_argument("--port", type=int, default=STANDARD_PORT)
    a = p.parse_args(argv)
    srv = starten(a.port, im_hintergrund=False)
    print(f"Workbench: http://127.0.0.1:{a.port}/  ({db.db_pfad()})", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    sys.exit(main())

"""Was der Entwickler über eine Seite tun darf – ein Schreibweg für die lokale Workbench und den Briefkasten aus dem
Netz (→ doc/10 §4 Stufe 2, doc/12). Absender ist immer der Entwickler; erlaubt sind nur diese Aktionen:
Frage beantworten, Nachricht an Agenten, Nachrichten an dich als gelesen markieren, Halt, Weiter.
"""
from . import db, kern

NACHRICHT_ARTEN = ("auftrag", "frage", "info", "korrektur", "freigabe")


class Ungueltig(ValueError):
    """Eingabe unvollständig oder nicht erlaubt (HTTP 400)."""


def ausfuehren(con, pid, weg, daten, kanal="seite"):
    teile = weg.strip("/").split("/")
    if teile[:2] == ["api", "frage"] and len(teile) == 4 and teile[3] == "antwort":
        art = daten.get("art")
        wert = (daten.get("wert") or "").strip()
        if art not in ("option", "text", "rueckfrage") or not wert:
            raise Ungueltig("art/wert fehlt")
        try:
            fid = int(teile[2])
        except ValueError:
            raise Ungueltig("Fragenummer")
        st = kern.frage_antworten(con, pid, fid, art, wert, kanal)
        if art == "option" and (daten.get("anmerkung") or "").strip():
            with db.schreiben(con):
                t = db.jetzt()
                db.einfuegen(con, "wortlaut", projekt_id=pid, zeit_utc=t, text=daten["anmerkung"].strip(),
                             kanal=kanal, erfasst_von="amw", erfasst_utc=t,
                             bemerkung=f"Anmerkung zur Antwort auf F{fid} (Option {wert})")
        return {"status": st}
    if weg == "/api/nachricht":
        art = daten.get("art") or "auftrag"
        if art not in NACHRICHT_ARTEN:
            raise Ungueltig("Art nicht erlaubt")
        kurz = (daten.get("kurz") or "").strip()
        if not kurz or not (daten.get("an") or "").strip():
            raise Ungueltig("an/kurz fehlt")
        nid, namen = kern.posten(con, pid, kern.ENTWICKLER, daten["an"], art, kurz[:300],
                                 (daten.get("text") or "").strip()[:20000] or None)
        return {"nachricht": nid, "an": namen}
    if weg == "/api/gelesen":
        ids = daten.get("ids")
        if not isinstance(ids, list) or not ids or not all(isinstance(i, int) for i in ids):
            raise Ungueltig("ids fehlen")
        return {"erledigt": kern.erledigt(con, pid, kern.ENTWICKLER, ids[:100])}
    if weg == "/api/halt":
        return {"halt": kern.halt(con, pid, kern.ENTWICKLER, daten.get("fuer") or "alle",
                                  (daten.get("text") or "Halt vom Entwickler").strip()[:2000])}
    if weg == "/api/weiter":
        return {"aufgehoben": kern.weiter(con, pid, kern.ENTWICKLER, daten.get("fuer") or "alle")}
    raise LookupError("unbekannt")

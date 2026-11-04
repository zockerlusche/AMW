"""Was der Entwickler über eine Seite tun darf – ein Schreibweg für die lokale Workbench und den Briefkasten aus dem
Netz (→ doc/architektur.md, doc/online.md). Absender ist immer der Entwickler; erlaubt sind nur diese Aktionen:
Frage beantworten oder parken, Nachricht an Agenten, Nachrichten an dich als gelesen markieren, Halt, Weiter, Einstellungen.
Einstellungen „pc“ (Datenbank-Pfad, Port, Takte) und „turso“ (Zugang) nur am PC (kanal „seite“), nie aus dem Netz:
wer sich online anmeldet, soll die AMW nicht auf eine andere Datenbank umbiegen oder den Zugang aussperren können.
"""
from . import db, kern

NACHRICHT_ARTEN = ("auftrag", "frage", "info", "korrektur", "freigabe")


class Ungueltig(ValueError):
    """Eingabe unvollständig oder nicht erlaubt (HTTP 400)."""


def ausfuehren(con, pid, weg, daten, kanal="seite", speicher=None):
    """Führt die Aktion aus. Jede Eingabe des Entwicklers in der Workbench am PC heißt: er sitzt davor – ein freier
    Schirm geht zu. Online (Handy) nicht: er ist unterwegs, der Bildschirm bleibt frei."""
    if weg == "/api/schirm":
        return schirm_setzen(con, pid, daten, kanal)
    aus = _ausfuehren(con, pid, weg, daten, kanal, speicher)
    if kanal == "seite" and (weg != "/api/hochladen" or daten.get("schritt") == "start"):   # Upload in Teilen: einmal
        from . import schirm
        schirm.entwickler_da(con, "Workbench")
    return aus


def schirm_setzen(con, pid, d, kanal):
    """Frei nur am PC (wer online angemeldet ist, soll keine Fenster-Läufe auf diesem PC freigeben); zu überall."""
    from . import schirm
    frei = bool(d.get("frei"))
    if frei and kanal != "seite":
        raise Ungueltig("Schirm frei geben geht nur am PC – zu geht auch von unterwegs")
    try:
        z = schirm.setzen(con, pid, kern.ENTWICKLER, frei, (d.get("grund") or "").strip() or None, d.get("bis") or None,
                          "workbench" if kanal == "seite" else "netz")
    except kern.AmwFehler as e:
        raise Ungueltig(str(e)) from None
    return {"schirm": z, "text": schirm.text(z)}


def _ausfuehren(con, pid, weg, daten, kanal="seite", speicher=None):
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
    if teile[:2] == ["api", "frage"] and len(teile) == 4 and teile[3] in ("parken", "aufnehmen"):
        try:
            fid = int(teile[2])
        except ValueError:
            raise Ungueltig("Fragenummer")
        try:
            return {"status": kern.frage_parken(con, pid, kern.ENTWICKLER, fid, teile[3] == "parken",
                                                (daten.get("grund") or "").strip()[:2000] or None)}
        except kern.AmwFehler as e:                  # schon geparkt/beantwortet (z. B. doppelt aus dem Netz): kein Fehler-Stau
            raise Ungueltig(str(e)) from None
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
    if weg.startswith("/api/einstellungen/"):
        return einstellen(con, pid, weg.rsplit("/", 1)[1], daten, kanal, speicher)
    if weg in ("/api/agent/start", "/api/agent/stop"):     # nur am PC: startet/beendet Programme auf diesem PC
        if kanal != "seite":
            raise Ungueltig("Agenten starten und beenden geht nur am PC")
        from . import steuerung
        try:
            if weg.endswith("start"):
                return {"text": steuerung.starten(con, pid, daten.get("kennung") or "", neu=bool(daten.get("neu")))}
            return {"text": steuerung.beenden(con, pid, daten.get("kennung") or "")}
        except (kern.AmwFehler, LookupError, OSError) as e:
            raise Ungueltig(str(e)) from None
    if weg.startswith("/api/dokument/"):             # Dokumente: kommentieren, zuordnen, archivieren; löschen nur am PC
        return dokument(con, pid, weg.rsplit("/", 1)[1], daten, kanal, speicher)
    if weg == "/api/hochladen":                      # am PC: Teile in den Datenordner (online legt die Seite sie in den Speicher)
        if kanal != "seite":
            raise Ungueltig("Hochladen läuft online über die Seite")
        return hochladen(daten)
    if weg.startswith("/api/plan/"):                 # Planung – auch von unterwegs (Freigaben!)
        return planen(con, pid, weg.rsplit("/", 1)[1], daten)
    if weg == "/api/push/probe":                     # nur am PC: verschickt wirklich
        if kanal != "seite":
            raise Ungueltig("Die Probe geht nur am PC")
        from . import push
        try:
            return {"probe": push.probe(daten.get("anbieter") or None)}
        except kern.AmwFehler as e:
            raise Ungueltig(str(e)) from None
    if weg == "/api/halt":
        return {"halt": kern.halt(con, pid, kern.ENTWICKLER, daten.get("fuer") or "alle",
                                  (daten.get("text") or "Halt vom Entwickler").strip()[:2000])}
    if weg == "/api/weiter":
        return {"aufgehoben": kern.weiter(con, pid, kern.ENTWICKLER, daten.get("fuer") or "alle")}
    raise LookupError("unbekannt")


def hochladen(d):
    from . import dokumente
    try:
        if d.get("schritt") == "start":
            return {"id": dokumente.hoch_start(d.get("name"), d.get("groesse"), d.get("sha"), d.get("teile"))}
        if d.get("schritt") == "teil":
            dokumente.hoch_teil(d.get("id"), d.get("nr"), d.get("inhalt"))
            return {"ok": True}
    except (kern.AmwFehler, ValueError, TypeError) as x:
        raise Ungueltig(str(x)) from None
    raise Ungueltig("schritt start|teil")


def dokument(con, pid, was, d, kanal, speicher=None):
    from . import dokumente
    e = kern.ENTWICKLER
    try:
        if was == "neu":                              # hochgeladene Datei → Dokument (am PC aus hoch/, online aus dem Speicher)
            if kanal == "seite":
                roh, name = dokumente.hoch_fertig(d.get("hoch"))
            else:
                from . import abgleich
                if speicher is None:
                    raise Ungueltig("Kein Online-Speicher")
                roh, name = abgleich.hoch_holen(speicher, d.get("hoch"))
            bezug = {k: d.get(k) for k in ("bogen", "aufgabe", "frage", "beschluss") if d.get(k)}
            did = dokumente.ablegen_inhalt(con, pid, e, roh, name, d.get("titel"), d.get("art") or None,
                                           (d.get("notiz") or "").strip()[:500] or None, bool(d.get("online")), **bezug)
            return {"dokument": did}
        did = int(d.get("id") or 0)
        if was == "text":
            return {"version": dokumente.text_version(con, pid, e, did, d.get("text"), d.get("basis"), d.get("notiz"),
                                                      d.get("melden", True) is not False)}
        if was == "kommentar":
            nid, namen = dokumente.melden(con, pid, e, did, d.get("text"), bool(d.get("ueberarbeiten")))
            return {"nachricht": nid, "an": namen}
        if was == "setzen":
            bezug = {"bogen": None} if d.get("loesen") else {k: d.get(k) for k in ("bogen", "aufgabe", "frage", "beschluss") if d.get(k)}
            dokumente.setzen(con, pid, e, did, d.get("titel"), d.get("art"), **bezug)
            return {"ok": True}
        if was == "status":
            dokumente.status_setzen(con, pid, e, did, d.get("status"))
            return {"ok": True}
        if was == "online":
            dokumente.online_setzen(con, pid, e, did, bool(d.get("an")))
            return {"ok": True}
        if was == "loeschen":
            if kanal != "seite":
                raise Ungueltig("Endgültig löschen geht nur am PC")
            return {"dateien": dokumente.loeschen(con, pid, e, did)}
    except (kern.AmwFehler, ValueError, TypeError) as x:
        raise Ungueltig(str(x)) from None
    raise LookupError("unbekannt")


def planen(con, pid, was, d):
    """Entscheidungen und Pflege der Planung durch den Entwickler (Gate-Rolle: Freigaben gibt nur er)."""
    from . import planung
    e = kern.ENTWICKLER
    zahl = lambda k: int(d[k]) if d.get(k) not in (None, "") else None
    try:
        if was == "spec":
            planung.spec_entscheiden(con, pid, e, zahl("bogen"), d.get("teil"), bool(d.get("frei")), (d.get("kommentar") or "").strip() or None)
            return {"ok": True}
        if was == "planfrei":
            planung.plan_entscheiden(con, pid, e, zahl("aufgabe"), bool(d.get("frei")), (d.get("kommentar") or "").strip() or None)
            return {"ok": True}
        if was == "leitbild":
            zeilen = lambda k: [x for x in (d.get(k) or "").splitlines()] if d.get(k) is not None else None
            return {"leitbild": planung.leitbild_setzen(con, pid, e, d.get("ziel"), zeilen("kennzahlen"), zeilen("nicht_ziele"),
                                                        zeilen("prinzipien"), zeilen("dod"))}
        if was == "bogen":
            if d.get("aktion") == "neu":
                return {"bogen": planung.bogen_neu(con, pid, e, d.get("titel"), d.get("ziel"), d.get("abnahme"), d.get("zieldatum") or None)}
            if d.get("aktion") == "status":
                planung.bogen_status(con, pid, e, zahl("bogen"), d.get("status"), bool(d.get("erzwingen")))
                return {"ok": True}
            planung.bogen_aendern(con, pid, e, zahl("bogen"), d.get("titel"), d.get("ziel"), d.get("abnahme"),
                                  d.get("zieldatum"), zahl("nr"), d.get("grund"))
            return {"ok": True}
        if was == "check":                         # Befund bewusst akzeptieren oder wieder zählen lassen
            if d.get("wieder"):
                planung.check_wieder(con, pid, e, d.get("schluessel") or "")
            else:
                planung.check_akzeptieren(con, pid, e, d.get("schluessel") or "", d.get("grund"))
            return {"ok": True}
        if was == "rueckblick":
            from . import verlauf
            return {"rueckblick": verlauf.rueckblick_neu(con, pid, e, zahl("bogen"), d.get("art"), d.get("text"))}
        if was == "uebernehmen":
            from . import verlauf
            return {"nr": verlauf.massnahme_uebernehmen(con, pid, e, zahl("id"), d.get("als"), d.get("agent") or None)}
        if was == "risiko":
            felder = {k: d.get(k) for k in ("titel", "ursache", "wirkung", "strategie", "massnahme", "verantwortlich", "ausloeser", "status")}
            felder.update(wahrscheinlichkeit=zahl("wahrscheinlichkeit"), auswirkung=zahl("auswirkung"), bogen_id=zahl("bogen"))
            return {"risiko": planung.risiko_setzen(con, pid, e, zahl("id"), **{k: (v or None) if isinstance(v, str) else v
                                                                               for k, v in felder.items()})}
    except kern.AmwFehler as x:
        raise Ungueltig(str(x)) from None
    raise LookupError("unbekannt")


NUR_AM_PC = ("pc", "turso", "push", "profil")   # Profil: Ordner/Startsatz landen in einem Befehl auf diesem PC


def einstellen(con, pid, teil, daten, kanal, speicher=None):
    from . import abgleich, einstellungen
    if teil in NUR_AM_PC and kanal != "seite":
        raise Ungueltig("Diese Einstellung lässt sich nur am PC ändern")
    werte = {k: v for k, v in daten.items() if k not in ("kennung", "neu")}
    try:
        if teil == "projekt":
            return {"projekt": kern.projekt_einstellen(con, pid, kern.ENTWICKLER, **werte)}
        if teil == "agent":
            return {"agent": kern.agent_einstellen(con, pid, kern.ENTWICKLER, daten.get("kennung"),
                                                   neu=bool(daten.get("neu")), **werte)}
        if teil == "web":
            sp = speicher or abgleich.speicher_aus_zugang(nur_wenn_an=False)   # aus dem Briefkasten: derselbe Speicher
            if sp is None:
                raise Ungueltig("Kein Online-Speicher eingerichtet")
            return {"web": abgleich.web_einstellungen_setzen(sp, werte)}
        if teil == "pc":
            return {"pc": einstellungen.speichern(werte), "hinweis": "wirkt beim nächsten Start des Wächters"}
        if teil == "turso":
            return {"turso": turso_einstellen(daten), "hinweis": "wirkt beim nächsten Start des Wächters"}
        if teil == "profil":
            from . import steuerung
            return {"profil": steuerung.profil_setzen(con, pid, kern.ENTWICKLER, daten.get("kennung"),
                                                       **{k: v for k, v in werte.items()})}
        if teil == "push":
            from . import push
            return {"push": push.speichern(daten), "hinweis": "wirkt in der nächsten Runde des Wächters"}
    except ValueError as e:
        raise Ungueltig(str(e)) from None
    raise LookupError("unbekannt")


def turso_einstellen(daten):
    """Adresse/Schlüssel/Abgleich am PC. Neue Adresse oder neuer Schlüssel werden vor dem Speichern geprüft."""
    import json
    import os
    from . import abgleich
    pfad = abgleich.zugang_pfad()
    try:
        with open(pfad, encoding="utf-8") as f:
            z = json.load(f)
    except (OSError, ValueError):
        z = {}
    url = (daten.get("url") or z.get("url") or "").strip()
    token = (daten.get("token") or "").strip() or z.get("token", "")
    if url != z.get("url") or token != z.get("token"):
        if not url.startswith(("libsql://", "https://")) or ".turso.io" not in url or not token:
            raise Ungueltig("Adresse libsql://….turso.io und Schlüssel nötig")
        try:
            abgleich.TursoSpeicher(url, token).ausfuehren([(s, []) for s in abgleich.SCHEMA])
        except OSError as e:
            raise Ungueltig(f"Turso nicht erreichbar oder Schlüssel abgelehnt ({e}) – nichts gespeichert") from None
    z.update({"url": url, "token": token})
    if "abgleich" in daten:
        z["abgleich"] = bool(daten["abgleich"])
    os.makedirs(os.path.dirname(pfad), exist_ok=True)
    with open(pfad + ".neu", "w", encoding="utf-8") as f:
        json.dump(z, f, indent=2)
    os.replace(pfad + ".neu", pfad)
    return {"url": url, "abgleich": bool(z.get("abgleich")), "schluessel_gespeichert": bool(token)}

"""Was der Entwickler über eine Seite tun darf – ein Schreibweg für die lokale Workbench und den Briefkasten aus dem
Netz (→ doc/architektur.md, doc/online.md). Absender ist immer der Entwickler; erlaubt sind nur diese Aktionen:
Frage beantworten oder parken, Nachricht an Agenten, Nachrichten an dich als gelesen markieren, Halt, Weiter, Einstellungen.
Einstellungen „pc“ (Datenbank-Pfad, Port, Takte) und „turso“ (Zugang) nur am PC (kanal „seite“), nie aus dem Netz:
wer sich online anmeldet, soll die AMW nicht auf eine andere Datenbank umbiegen oder den Zugang aussperren können.
"""
import os
import subprocess
import sys
import threading

from . import db, kern

NACHRICHT_ARTEN = ("auftrag", "frage", "info", "korrektur", "freigabe")


class Ungueltig(ValueError):
    """Eingabe unvollständig oder nicht erlaubt (HTTP 400)."""


def ausfuehren(con, pid, weg, daten, kanal="seite", speicher=None):
    """Führt die Aktion aus. Jede Eingabe des Entwicklers in der Workbench am PC heißt: er sitzt davor – ein freier
    Schirm geht zu. Online (Handy) nicht: er ist unterwegs, der Bildschirm bleibt frei."""
    from . import benutzer                           # von der Online-Seite: Rolle und Zuweisung prüft auch der PC
    name = daten.pop("_benutzer", None) if isinstance(daten, dict) else None
    if kanal != "netz":
        name = None                                  # am PC sitzt der Mensch selbst (System-Admin)
    else:                                            # von der Online-Seite: immer prüfen, auch ohne Namen (dann nur Altbetrieb)
        ok, grund = benutzer.darf(con, name, pid, benutzer.klasse(weg, daten))
        if not ok:
            raise Ungueltig(f"Nicht erlaubt: {grund}")
    marke = benutzer.AKTUELL.set(name if name and name != benutzer.ZUGANG else None)
    try:
        if weg == "/api/schirm":
            return schirm_setzen(con, pid, daten, kanal, name)
        aus = _ausfuehren(con, pid, weg, daten, kanal, speicher)
    finally:
        benutzer.AKTUELL.reset(marke)
    if kanal == "seite" and (weg != "/api/hochladen" or daten.get("schritt") == "start"):   # Upload in Teilen: einmal
        from . import schirm
        schirm.entwickler_da(con, "Workbench")
    return aus


def schirm_setzen(con, pid, d, kanal, wer=None):
    """Zu geht überall. Frei am PC – und online nur für einen System-Admin (der Zugang der Seite oder ein Benutzer mit dieser
    Rolle); die Uhrzeit, bis wann, ist freiwillig; der Name steht im Grund."""
    from . import benutzer, schirm
    frei = bool(d.get("frei"))
    grund = (d.get("grund") or "").strip() or None
    if frei and kanal != "seite":
        b = benutzer.finden(con, wer) if wer and wer != benutzer.ZUGANG else None
        if not (wer == benutzer.ZUGANG or (b and b["rolle"] == "system_admin" and not b["gesperrt"])):
            raise Ungueltig("Bildschirm freigeben darf online nur ein System-Admin – belegen geht für alle")
        name = b["anzeige"] or b["name"] if b else kern.entwickler_name(con)
        grund = f"{grund or 'online freigegeben'} – online von {name}"
    try:
        z = schirm.setzen(con, pid, kern.ENTWICKLER, frei, grund, d.get("bis") or None,
                          "workbench" if kanal == "seite" else "netz")
    except kern.AmwFehler as e:
        raise Ungueltig(str(e)) from None
    return {"schirm": z, "text": schirm.text(z)}


def benutzer_verwalten(con, was, d, speicher=None):
    """neu (name, rolle?, projekte?, anzeige?, email?) · aendern (name, rolle?, projekte?, gesperrt?, email?) · freischalten (name, stunden?)."""
    from . import abgleich, benutzer
    name = (d.get("name") or "").strip()
    projekte = d.get("projekte")
    if projekte is not None and not (isinstance(projekte, list) and all(isinstance(p, int) for p in projekte)):
        raise Ungueltig("projekte: Liste von Projekt-Nummern")
    rolle = d.get("rolle") or None
    try:
        if was == "neu":
            benutzer.neu(con, kern.ENTWICKLER, name, rolle, d.get("anzeige"), d.get("email"), projekte or ())
            return {"benutzer": benutzer.finden(con, name)}
        if was == "aendern":
            g = d.get("gesperrt")
            return {"benutzer": benutzer.aendern(con, kern.ENTWICKLER, name, rolle, None if g is None else bool(g), projekte, d.get("email"))}
        if was == "freischalten":
            sp = speicher if speicher is not None else abgleich.speicher_aus_zugang()
            code, bis = benutzer.freischalten(con, kern.ENTWICKLER, name, sp, d.get("stunden") or benutzer.CODE_STUNDEN)
            return {"code": code, "bis": bis}
    except kern.AmwFehler as e:
        raise Ungueltig(str(e)) from None
    raise Ungueltig("unbekannt")


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
        auf = int(daten["antwort_auf"]) if str(daten.get("antwort_auf") or "").isdigit() else None
        try:                                         # Bezug: mitgegeben (von dort, wo geschrieben wurde) oder geerbt
            nid, namen = kern.posten(con, pid, kern.ENTWICKLER, daten["an"], art, kurz[:300],
                                     (daten.get("text") or "").strip()[:20000] or None, antwort_auf=auf,
                                     bezug=(str(daten.get("bezug") or "").strip() or None))
        except kern.AmwFehler as e:
            raise Ungueltig(str(e)) from None
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
    if weg in ("/api/agent/ende", "/api/agent/start-fehlende", "/api/dienst/neustart"):   # Leitstand – nur am PC
        if kanal != "seite":
            raise Ungueltig("Sitzungen und den Dienst steuerst du nur am PC")
        from . import steuerung
        try:
            if weg == "/api/agent/ende":             # sichern & beenden lassen: einer (kennung) oder alle laufenden
                k = (daten.get("kennung") or "").strip()
                return steuerung.ende_anfordern(con, pid, [k] if k else None)
            if weg == "/api/agent/start-fehlende":
                namen = steuerung.fehlende(con, pid)
                if namen:                            # nacheinander mit Abstand, ohne die Seite warten zu lassen
                    threading.Thread(target=steuerung.fehlende_starten, args=(db.verbinde, pid, namen), daemon=True).start()
                return {"agenten": namen, "abstand_s": steuerung.STARTSKRIPT_ABSTAND_S}
            from . import einrichtung                # Wächter neu: als eigener Prozess, sonst beendete er sich mitten in der Antwort
            fremd = einrichtung.fremde_aufgabe()
            if fremd:
                raise Ungueltig(fremd)
            subprocess.Popen([sys.executable, "-X", "utf8", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "amw-cli.py"),
                              "dienst", "neustart"], close_fds=True,
                             creationflags=getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NO_WINDOW", 0))
            return {"text": "Dienst startet neu"}
        except (kern.AmwFehler, LookupError, OSError) as e:
            raise Ungueltig(str(e)) from None
    if weg.startswith("/api/dokument/"):             # Dokumente: kommentieren, zuordnen, archivieren; löschen nur am PC
        return dokument(con, pid, weg.rsplit("/", 1)[1], daten, kanal, speicher)
    if weg == "/api/hochladen":                      # am PC: Teile in den Datenordner (online legt die Seite sie in den Speicher)
        if kanal != "seite":
            raise Ungueltig("Hochladen läuft online über die Seite")
        return hochladen(daten)
    if weg.startswith("/api/aufgabe/"):              # Aufgabe: erledigt / später (eigene), Antwort an den Zuständigen
        return aufgabe(con, pid, weg.rsplit("/", 1)[1], daten)
    if weg.startswith("/api/plan/"):                 # Planung – auch von unterwegs (Freigaben!)
        return planen(con, pid, weg.rsplit("/", 1)[1], daten)
    if weg == "/api/regelwerk/uebernehmen":           # Grundregel ins bestehende Projekt (G-3) – Lead oder Mensch
        from . import regelwerk
        try:
            return regelwerk.nachziehen(con, pid, kern.ENTWICKLER, daten.get("nr"))
        except kern.AmwFehler as e:
            raise Ungueltig(str(e)) from None
    if weg == "/api/nachricht/zurueckziehen":         # eigene Nachricht, solange niemand sie gelesen hat
        from . import benutzer
        try:
            return kern.zurueckziehen(con, pid, kern.ENTWICKLER, int(daten.get("id") or 0), benutzer.AKTUELL.get() if kanal == "netz" else None)
        except (kern.AmwFehler, ValueError) as e:
            raise Ungueltig(str(e)) from None
    if weg == "/api/benutzer/eingerichtet":          # von der Seite selbst: erstes Anmelden fertig → Meldung an den Menschen
        from . import benutzer
        if kanal != "netz" or not benutzer.AKTUELL.get():
            raise Ungueltig("Diese Meldung kommt nur von der Online-Seite")
        return benutzer.eingerichtet_melden(con, pid, benutzer.AKTUELL.get(), daten.get("weg"))
    if weg.startswith("/api/benutzer/"):             # Benutzer verwalten: nur am PC (Stufe R1b)
        if kanal != "seite":
            raise Ungueltig("Benutzer verwaltest du am PC")
        return benutzer_verwalten(con, weg.rsplit("/", 1)[1], daten, speicher)
    if weg in ("/api/agent/entfernen", "/api/agent/wiederaufnehmen", "/api/agent/loeschen"):   # nur der Mensch (online: System-Admin)
        k = (daten.get("kennung") or "").strip()
        tun = {"entfernen": kern.agent_entfernen, "wiederaufnehmen": kern.agent_wiederaufnehmen, "loeschen": kern.agent_loeschen}
        try:
            return tun[weg.rsplit("/", 1)[1]](con, pid, kern.ENTWICKLER, k)
        except kern.AmwFehler as e:
            raise Ungueltig(str(e)) from None
    if weg == "/api/projekt/neu":                    # nur am PC: richtet Ordner und Startskript auf diesem PC ein
        if kanal != "seite":
            raise Ungueltig("Ein neues Projekt legst du am PC an")
        return projekt_neu(con, daten)
    if weg == "/api/archivieren":                    # Aufräumvorschläge ins Archiv verschieben – der Mensch, nie löschen
        from . import platte
        namen = daten.get("namen") or []
        if not isinstance(namen, list) or not namen or not all(isinstance(n, str) for n in namen):
            raise Ungueltig("Welche Sicherungen?")
        try:
            erg = platte.archivieren(con, namen[:500])
        except kern.AmwFehler as e:
            raise Ungueltig(str(e)) from None
        except OSError as e:
            raise Ungueltig(f"Verschieben ging nicht: {e}") from None
        return {"verschoben": len(erg), "ziel": os.path.dirname(erg[0][1]) if erg else ""}
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
        if was == "vermerk":                          # KI-Ergebnis ausgewählt / verworfen / nachbearbeitet (auch am Handy)
            from . import ki
            return {"vermerk": ki.vermerken(con, pid, e, did, d.get("art"), d.get("text"), "workbench" if kanal == "seite" else "netz")}
        if was == "loeschen":
            if kanal != "seite":
                raise Ungueltig("Endgültig löschen geht nur am PC")
            return {"dateien": dokumente.loeschen(con, pid, e, did)}
    except (kern.AmwFehler, ValueError, TypeError) as x:
        raise Ungueltig(str(x)) from None
    raise LookupError("unbekannt")


def aufgabe(con, pid, was, d):
    """Aus der Aufgaben-Ansicht: „erledigt“ (mit Notiz als Beleg) und „später“ nur für Aufgaben des Entwicklers;
    „antwort“ zu jeder Aufgabe. Jede Änderung erfährt der Zuständige (wer sie angelegt hat, sonst Federführung/Lead)."""
    e = kern.ENTWICKLER
    try:
        aid = int(d.get("id") or 0)
    except (TypeError, ValueError):
        raise Ungueltig("Aufgabennummer") from None
    a = con.execute("SELECT * FROM aufgabe WHERE id = ? AND projekt_id = ?", (aid, pid)).fetchone()
    if not a:
        raise Ungueltig(f"A{aid} gibt es nicht")
    text = (d.get("text") or "").strip()[:4000]
    an = a["angelegt_von"] if a["angelegt_von"] not in (None, "", e, "AMW") else kern.zustaendig(con, pid, aid)
    if was in ("erledigt", "spaeter") and a["agent"] != e:
        raise Ungueltig(f"A{aid} ist nicht deine Aufgabe – schreib dem Bearbeiter eine Antwort")
    if a["status"] in ("fertig", "verworfen") and was != "antwort":
        raise Ungueltig(f"A{aid} ist schon {a['status']}")
    try:
        if was == "erledigt":
            if not text:
                raise Ungueltig("Bitte kurz notieren, was erledigt ist (das ist der Beleg)")
            kern.aufgabe_status(con, pid, e, aid, "fertig", beleg=f"{kern.entwickler_name(con, pid)}: {text[:300]}", zusammenfassung=text)
            kurz = f"A{aid} erledigt: {text[:200]}"
        elif was == "dazwischen":                    # nur hier, beim Menschen: vor das laufende Stück des Agenten
            if not text:
                raise Ungueltig("Bitte den Grund eintragen – er geht an den Agenten")
            from . import arbeitsliste
            _, unterbrochen = arbeitsliste.dazwischen(con, pid, e, aid, text)
            kurz = f"A{aid} dazwischengeschoben" + (f" (A{unterbrochen} wartet)" if unterbrochen else "") + f": {text[:150]}"
        elif was == "spaeter":
            from . import arbeitsliste
            arbeitsliste.schieben(con, pid, e, aid, unten=True)
            kurz = f"A{aid} später" + (f": {text[:200]}" if text else " (ans Ende meiner Liste)")
        elif was == "antwort":
            if not text:
                raise Ungueltig("Text fehlt")
            kurz = f"A{aid}: {text[:200]}"
        else:
            raise LookupError("unbekannt")
        nid = None
        if an:                                      # auch zu einer gerade abgeschlossenen Aufgabe (kern.posten lehnt die ab)
            with db.schreiben(con):
                nid, _ = kern._posten(con, pid, e, an, "info", kurz[:300], text if len(text) > 200 else None, aufgabe_id=aid)
        return {"ok": True, "an": an, "nachricht": nid}
    except kern.AmwFehler as x:
        raise Ungueltig(str(x)) from None


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


def projekt_neu(con, d):
    """Workbench „Neues Projekt“ – wie `amw einrichten`: Projekt, Lead, Agenten mit Profil, Projektordner (Hooks,
    AMW_PROJEKT), Startskript je Projekt; auf Wunsch eine Kopie der Arbeitsregeln eines anderen Projekts."""
    import os
    from . import assistent
    name = " ".join(str(d.get("name") or "").split())
    if not name or len(name) > 60:
        raise Ungueltig("Name fehlt (bis 60 Zeichen)")
    if con.execute("SELECT 1 FROM projekt WHERE name = ?", (name,)).fetchone():
        raise Ungueltig(f"Projekt {name} gibt es schon")
    ordner = str(d.get("ordner") or "").strip().strip('"')
    if not ordner or not os.path.isdir(ordner):
        raise Ungueltig("Projektordner fehlt oder gibt es nicht – lege ihn zuerst an (z. B. im Explorer) und trage den Pfad ein")
    agenten = [x.strip() for x in str(d.get("agenten") or "").split(",") if x.strip()]
    try:
        schritte = assistent.schnell(name, str(d.get("lead") or "").strip() or None, agenten, os.path.abspath(ordner),
                                     d.get("rechte") or "vorgabe", None, False, startskript=assistent.STARTSKRIPT, ausgabe=lambda *_: None,
                                     regeln_von=d.get("regeln_von") or None, farbe=d.get("farbe") or None,
                                     lead_chat=bool(d.get("lead_chat")),
                                     regelwerk=d.get("regelwerk") if isinstance(d.get("regelwerk"), dict) else None)
    except (kern.AmwFehler, LookupError, ValueError, OSError) as e:
        raise Ungueltig(str(e)) from None
    return {"uid": con.execute("SELECT uid FROM projekt WHERE name = ?", (name,)).fetchone()[0], "schritte": schritte}


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
        if teil == "sso":                             # Firmen-Anmeldung (R2): nur am PC, ohne Geheimnis (das liegt beim Webhoster)
            if kanal != "seite":
                raise Ungueltig("Die Firmen-Anmeldung stellst du am PC ein")
            sp = speicher or abgleich.speicher_aus_zugang(nur_wenn_an=False)
            if sp is None:
                raise Ungueltig("Kein Online-Speicher eingerichtet")
            return {"sso": abgleich.sso_setzen(sp, werte)}
        if teil == "web":
            sp = speicher or abgleich.speicher_aus_zugang(nur_wenn_an=False)   # aus dem Briefkasten: derselbe Speicher
            if sp is None:
                raise Ungueltig("Kein Online-Speicher eingerichtet")
            return {"web": abgleich.web_einstellungen_setzen(sp, werte)}
        if teil == "pc":
            return {"pc": einstellungen.speichern(werte), "hinweis": "wirkt beim nächsten Start des Dienstes"}
        if teil == "turso":
            return {"turso": turso_einstellen(daten), "hinweis": "wirkt beim nächsten Start des Dienstes"}
        if teil == "profil":
            from . import steuerung
            return {"profil": steuerung.profil_setzen(con, pid, kern.ENTWICKLER, daten.get("kennung"),
                                                       **{k: v for k, v in werte.items()})}
        if teil == "push":
            from . import push
            return {"push": push.speichern(daten), "hinweis": "wirkt in der nächsten Runde des Dienstes"}
    except ValueError as e:
        raise Ungueltig(str(e)) from None
    raise LookupError("unbekannt")


def turso_einstellen(daten):
    """Art/Adresse/Schlüssel/Zertifikat/Abgleich am PC. Neue Werte werden vor dem Speichern geprüft (Verbindung, Tabellen).
    Art „turso“ (Cloud) oder „libsql“ (eigener libSQL-Server im Firmennetz, Stufe R3a)."""
    import json
    import os
    from . import abgleich
    pfad = abgleich.zugang_pfad()
    try:
        with open(pfad, encoding="utf-8") as f:
            z = json.load(f)
    except (OSError, ValueError):
        z = {}
    art = daten.get("art") or z.get("art") or "turso"
    url = (daten.get("url") or z.get("url") or "").strip()
    token = (daten.get("token") or "").strip() or z.get("token", "")
    ca = (daten["ca"] or "").strip() if "ca" in daten else z.get("ca", "")
    if art == "turso":
        ca = ""
    if url != z.get("url") or token != z.get("token") or art != (z.get("art") or "turso") or ca != z.get("ca", ""):
        try:
            url = abgleich.speicher_adresse(art, url)
        except ValueError as e:
            raise Ungueltig(str(e)) from None
        if not token:
            raise Ungueltig("Schlüssel nötig")
        if ca and not os.path.isfile(ca):
            raise Ungueltig(f"Zertifikat-Datei gibt es nicht: {ca}")
        try:
            abgleich.TursoSpeicher(url, token, ca).ausfuehren([(s, []) for s in abgleich.SCHEMA])
            abgleich.nachruesten(abgleich.TursoSpeicher(url, token, ca))
        except OSError as e:
            wer = "Turso" if art == "turso" else "Der eigene Server"
            raise Ungueltig(f"{wer} nicht erreichbar oder Schlüssel abgelehnt ({e}) – nichts gespeichert") from None
    z.update({"art": art, "url": url, "token": token, "ca": ca})
    if "abgleich" in daten:
        z["abgleich"] = bool(daten["abgleich"])
    os.makedirs(os.path.dirname(pfad), exist_ok=True)
    with open(pfad + ".neu", "w", encoding="utf-8") as f:
        json.dump(z, f, indent=2)
    os.replace(pfad + ".neu", pfad)
    return {"art": art, "url": url, "ca": ca, "abgleich": bool(z.get("abgleich")), "schluessel_gespeichert": bool(token)}

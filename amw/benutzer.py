"""Mehrere Benutzer (Stufe R1a): Rolle global, Projekte je Benutzer, Prüfung jeder Eingabe von der Online-Seite am PC.

Rollen, aufsteigend: leser (nur ansehen) < bearbeiter (arbeiten: Fragen, Nachrichten, Aufgaben, Dokumente, Freigaben,
Anhalten) < projekt_admin (dazu Benutzer seiner Projekte und Projekt-Einstellungen) < system_admin (alles, alle Projekte).
Der Mensch am PC (Workbench ohne Anmeldung) und der bisherige Online-Zugang aus der Konfiguration des Webhosters sind
System-Admin. Passwörter und Geheimnisse liegen nie in dieser Datenbank.
"""
import contextvars
import json

from . import db, kern

ROLLEN = ("leser", "bearbeiter", "projekt_admin", "system_admin")
NAMEN = {"leser": "Leser", "bearbeiter": "Bearbeiter", "projekt_admin": "Projekt-Admin", "system_admin": "System-Admin"}
# Klassen von Eingaben und die Rolle, die sie mindestens braucht
KLASSEN = {"lesen": "leser", "arbeiten": "bearbeiter", "projekt": "projekt_admin", "benutzer": "projekt_admin", "system": "system_admin"}

AKTUELL = contextvars.ContextVar("amw_benutzer", default=None)   # wer gerade über die Online-Seite handelt (Name)
ZUGANG = "@zugang"     # so nennt die Online-Seite den bisherigen Zugang aus ihrer Konfiguration (System-Admin)


def klasse(weg, daten=None):
    """Welche Klasse eine Eingabe ist (Weg der Online-Seite)."""
    if weg.startswith("/api/benutzer"):
        return "benutzer"
    if weg in ("/api/einstellungen/projekt", "/api/einstellungen/agent"):
        return "projekt"
    if weg.startswith("/api/einstellungen/") or weg in ("/api/archivieren", "/api/push/probe", "/api/projekt/neu"):
        return "system"
    return "arbeiten"


def _stufe(rolle):
    return ROLLEN.index(rolle)


def neu(con, von, name, rolle=None, anzeige=None, email=None, projekte=()):
    """Legt einen Benutzer an. Nur der Mensch (System-Admin). Ohne Rolle: wartet auf Freigabe, hat keine Rechte."""
    if von != kern.ENTWICKLER:
        raise kern.AmwFehler("Benutzer legt nur der Mensch an")
    name = (name or "").strip()
    if not name or len(name) > 60 or any(c in name for c in " /\\:,@"):
        raise kern.AmwFehler("Name: 1–60 Zeichen, ohne Leerzeichen, / \\ : , @")
    if rolle is not None and rolle not in ROLLEN:
        raise kern.AmwFehler(f"Rolle: {', '.join(ROLLEN)}")
    with db.schreiben(con):
        if con.execute("SELECT 1 FROM benutzer WHERE name = ?", (name,)).fetchone():
            raise kern.AmwFehler(f"Benutzer {name} gibt es schon")
        bid = db.einfuegen(con, "benutzer", name=name, anzeige=(anzeige or "").strip() or None, email=(email or "").strip().lower() or None,
                           rolle=rolle, angelegt_utc=db.jetzt(), angelegt_von=von)
        _zuweisen(con, bid, projekte)
    return bid


def _zuweisen(con, bid, projekte):
    con.execute("DELETE FROM benutzer_projekt WHERE benutzer_id = ?", (bid,))
    for p in projekte:
        pid = p if isinstance(p, int) else db.projekt_id(con, p)
        con.execute("INSERT OR IGNORE INTO benutzer_projekt (benutzer_id, projekt_id) VALUES (?, ?)", (bid, pid))


def aendern(con, von, name, rolle=None, gesperrt=None, projekte=None):
    if von != kern.ENTWICKLER:
        raise kern.AmwFehler("Benutzer ändert nur der Mensch")
    b = finden(con, name)
    if not b:
        raise kern.AmwFehler(f"Benutzer {name} gibt es nicht")
    with db.schreiben(con):
        if rolle is not None:
            if rolle not in ROLLEN:
                raise kern.AmwFehler(f"Rolle: {', '.join(ROLLEN)}")
            con.execute("UPDATE benutzer SET rolle = ? WHERE id = ?", (rolle, b["id"]))
        if gesperrt is not None:
            con.execute("UPDATE benutzer SET gesperrt = ? WHERE id = ?", (1 if gesperrt else 0, b["id"]))
        if projekte is not None:
            _zuweisen(con, b["id"], projekte)
    return finden(con, name)


def finden(con, name):
    r = con.execute("SELECT * FROM benutzer WHERE name = ?", (name,)).fetchone()
    if not r:
        return None
    b = dict(r)
    b["projekte"] = [x[0] for x in con.execute("SELECT projekt_id FROM benutzer_projekt WHERE benutzer_id = ? ORDER BY projekt_id", (b["id"],))]
    return b


def liste(con):
    return [finden(con, r[0]) for r in con.execute("SELECT name FROM benutzer ORDER BY name")]


def darf(con, name, pid, klasse_):
    """(ja, Grund) für eine Eingabe von der Online-Seite. ZUGANG = der bisherige Zugang aus der Konfiguration der Seite
    (System-Admin). Ohne Namen nur, solange niemand angelegt ist (Betrieb wie vor den Benutzern) – sobald es Benutzer
    gibt, wird abgewiesen: fehlt der Name (Fehler, alte Seite, Eingriff), bekommt die Anfrage keine Rechte."""
    if name == ZUGANG:
        return True, None
    if not name:
        if con.execute("SELECT 1 FROM benutzer LIMIT 1").fetchone():
            return False, "Anmeldung fehlt – die Online-Seite hat keinen Benutzer mitgeschickt (bitte neu anmelden)"
        return True, None
    b = finden(con, name)
    if not b:
        return False, f"Benutzer {name} ist hier nicht angelegt"
    if b["gesperrt"]:
        return False, f"{name} ist gesperrt"
    if not b["rolle"]:
        return False, f"{name} wartet auf Freigabe – ein Admin vergibt Rolle und Projekte"
    if b["rolle"] != "system_admin" and pid not in b["projekte"]:
        return False, f"{name} ist diesem Projekt nicht zugewiesen"
    if _stufe(b["rolle"]) < _stufe(KLASSEN[klasse_]):
        return False, f"{name} ist {NAMEN[b['rolle']]} – dafür braucht es {NAMEN[KLASSEN[klasse_]]}"
    return True, None


def fuer_online(con):
    """Die Benutzer für den Online-Speicher – ohne Passwort und Geheimnis (die setzt der Benutzer dort selbst)."""
    aus = []
    for b in liste(con):
        uids = [r[0] for r in con.execute("SELECT uid FROM projekt WHERE id IN (SELECT projekt_id FROM benutzer_projekt WHERE benutzer_id = ?)", (b["id"],))]
        aus.append({"name": b["name"], "anzeige": b["anzeige"], "email": b["email"], "rolle": b["rolle"], "gesperrt": b["gesperrt"],
                    "projekte": json.dumps(sorted(uids))})
    return aus

"""Mehrere Benutzer (Stufe R1a): Rolle global, Projekte je Benutzer, Prüfung jeder Eingabe von der Online-Seite am PC.

Rollen, aufsteigend: leser (nur ansehen) < bearbeiter (arbeiten: Fragen, Nachrichten, Aufgaben, Dokumente, Freigaben,
Anhalten) < projekt_admin (dazu Benutzer seiner Projekte und Projekt-Einstellungen) < system_admin (alles, alle Projekte).
Der Mensch am PC (Workbench ohne Anmeldung) und der bisherige Online-Zugang aus der Konfiguration des Webhosters sind
System-Admin. Passwörter und Geheimnisse liegen nie in dieser Datenbank.
"""
import contextvars
import datetime
import hashlib
import json
import secrets

from . import db, kern

ROLLEN = ("leser", "bearbeiter", "projekt_admin", "system_admin")
NAMEN = {"leser": "Leser", "bearbeiter": "Bearbeiter", "projekt_admin": "Projekt-Admin", "system_admin": "System-Admin"}
# Klassen von Eingaben und die Rolle, die sie mindestens braucht
KLASSEN = {"lesen": "leser", "arbeiten": "bearbeiter", "projekt": "projekt_admin", "benutzer": "projekt_admin", "system": "system_admin",
           "selbst": None}   # selbst: Meldungen der Seite über den Benutzer selbst (z. B. erstes Anmelden fertig) – keine Rolle nötig
CODE_ZEICHEN = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"   # 32 Zeichen ohne I, O, 0, 1 – 16 Stellen = 80 Bit
CODE_STUNDEN = 24

# Benutzer in den Online-Speicher (Abgleich und Freischalten): ohne Passwort und Geheimnis. Ändert der Admin die E-Mail,
# löst das die Bindung an ein Firmenkonto (R2) – sonst käme der Inhaber der alten Adresse weiter hinein.
ONLINE_EINTRAGEN = ("INSERT INTO benutzer (name, anzeige, email, rolle, gesperrt, projekte, stand_utc) VALUES (?, ?, ?, ?, ?, ?, ?)"
                    " ON CONFLICT(name) DO UPDATE SET anzeige = excluded.anzeige, email = excluded.email, rolle = excluded.rolle,"
                    " gesperrt = excluded.gesperrt, projekte = excluded.projekte, stand_utc = excluded.stand_utc,"
                    " sso_kennung = CASE WHEN lower(coalesce(benutzer.email, '')) = lower(coalesce(excluded.email, ''))"
                    " THEN benutzer.sso_kennung ELSE NULL END")

AKTUELL = contextvars.ContextVar("amw_benutzer", default=None)   # wer gerade über die Online-Seite handelt (Name)
ZUGANG = "@zugang"     # so nennt die Online-Seite den bisherigen Zugang aus ihrer Konfiguration (System-Admin)


def klasse(weg, daten=None):
    """Welche Klasse eine Eingabe ist (Weg der Online-Seite)."""
    if weg == "/api/benutzer/eingerichtet":
        return "selbst"
    if weg.startswith("/api/benutzer"):
        return "benutzer"
    if weg in ("/api/einstellungen/projekt", "/api/einstellungen/agent"):
        return "projekt"
    if weg.startswith("/api/einstellungen/") or weg in ("/api/archivieren", "/api/push/probe", "/api/projekt/neu",
                                                        "/api/agent/entfernen", "/api/agent/wiederaufnehmen", "/api/agent/loeschen"):
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
        email = email_pruefen(email)
        if email and con.execute("SELECT 1 FROM benutzer WHERE lower(email) = ?", (email,)).fetchone():
            raise kern.AmwFehler(f"Die E-Mail {email} hat schon ein anderer Benutzer")
        bid = db.einfuegen(con, "benutzer", name=name, anzeige=(anzeige or "").strip() or None, email=email,
                           rolle=rolle, angelegt_utc=db.jetzt(), angelegt_von=von)
        _zuweisen(con, bid, projekte)
    return bid


def _zuweisen(con, bid, projekte):
    con.execute("DELETE FROM benutzer_projekt WHERE benutzer_id = ?", (bid,))
    for p in projekte:
        pid = p if isinstance(p, int) else db.projekt_id(con, p)
        con.execute("INSERT OR IGNORE INTO benutzer_projekt (benutzer_id, projekt_id) VALUES (?, ?)", (bid, pid))


def email_pruefen(email):
    email = (email or "").strip().lower()
    if email and (len(email) > 254 or email.count("@") != 1 or any(c.isspace() for c in email) or "." not in email.split("@")[1]):
        raise kern.AmwFehler("E-Mail: so wie im Firmenkonto, z. B. marie@firma.de")
    return email or None


def aendern(con, von, name, rolle=None, gesperrt=None, projekte=None, email=None):
    """email: None = unverändert, "" = entfernen. Eine neue E-Mail löst online die Bindung an ein Firmenkonto."""
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
        if email is not None:
            neu_ = email_pruefen(email)
            if neu_ and con.execute("SELECT 1 FROM benutzer WHERE lower(email) = ? AND id != ?", (neu_, b["id"])).fetchone():
                raise kern.AmwFehler(f"Die E-Mail {neu_} hat schon ein anderer Benutzer")
            con.execute("UPDATE benutzer SET email = ? WHERE id = ?", (neu_, b["id"]))
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
    if klasse_ == "selbst":
        return True, None
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


# --- Stufe R1b: Freischalt-Code und Stand je Benutzer im Online-Speicher ---------------------------------------------

def code_neu():
    roh = "".join(secrets.choice(CODE_ZEICHEN) for _ in range(16))
    return "-".join(roh[i:i + 4] for i in range(0, 16, 4))


def code_hash(code):
    """Wie die Seite (web/inc/lib.php code_norm): Großbuchstaben, ohne Bindestriche und Leerzeichen."""
    norm = "".join(c for c in code if c.isalnum()).upper()
    return hashlib.sha256(norm.encode("ascii")).hexdigest()


def freischalten(con, von, name, sp, stunden=CODE_STUNDEN):
    """Neuer Freischalt-Code für das erste Anmelden (oder nach verlorenem Passwort/Handy). Setzt Passwort, zweiten
    Faktor und die Bindung an ein Firmenkonto online zurück und beendet alle Sitzungen des Benutzers. Der Code wird nur zurückgegeben – online steht nur
    sein Hash, auf dem PC gar nichts. Rückgabe: (code, bis_utc)."""
    if von != kern.ENTWICKLER:
        raise kern.AmwFehler("Freischalten darf nur der Mensch am PC")
    b = finden(con, name)
    if not b:
        raise kern.AmwFehler(f"Benutzer {name} gibt es nicht")
    if b["gesperrt"]:
        raise kern.AmwFehler(f"{name} ist gesperrt – erst entsperren, dann freischalten")
    if sp is None:
        raise kern.AmwFehler("Kein Online-Speicher eingerichtet – Benutzer melden sich auf der Online-Seite an (amw web einrichten)")
    if not 1 <= int(stunden) <= 168:
        raise kern.AmwFehler("Gültigkeit: 1 bis 168 Stunden")
    from . import abgleich
    sp.ausfuehren([(s, []) for s in abgleich.SCHEMA])                # auch ohne laufenden Dienst: Tabelle und Spalten da
    abgleich.nachruesten(sp)
    code = code_neu()
    bis = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=int(stunden))).strftime("%Y-%m-%dT%H:%M:%SZ")
    z = next(x for x in fuer_online(con) if x["name"] == name)
    sp.ausfuehren([
        (ONLINE_EINTRAGEN, [z["name"], z["anzeige"], z["email"], z["rolle"], z["gesperrt"], z["projekte"], db.jetzt()]),
        ("UPDATE benutzer SET code_hash = ?, code_bis = ?, passwort_hash = NULL, totp_geheim = NULL, totp_letzt = 0,"
         " sso_kennung = NULL, eingerichtet_utc = NULL, sitzung_nr = sitzung_nr + 1 WHERE name = ?", [code_hash(code), bis, name]),
    ])
    return code, bis


def online_stand(sp):
    """{name: {"stand": "wartet_code" | "code_abgelaufen" | "eingerichtet" | "neu", "bis", "eingerichtet_utc", "angemeldet_utc",
    "firmenkonto": bool}} – eingerichtet heißt: Passwort und zweiter Faktor gesetzt ODER mit dem Firmenkonto angemeldet."""
    if sp is None:
        return {}
    try:
        zeilen = sp.ausfuehren([("SELECT name, code_bis, eingerichtet_utc, angemeldet_utc, passwort_hash IS NOT NULL, sso_kennung IS NOT NULL"
                                 " FROM benutzer", [])])[0]
    except Exception:                                  # Speicher nicht erreichbar: die Liste kommt trotzdem
        return {}
    jetzt = db.jetzt()
    aus = {}
    for name, bis, eingerichtet, angemeldet, hat_passwort, hat_sso in zeilen:
        if int(hat_passwort or 0) or int(hat_sso or 0):
            stand = "eingerichtet"
        elif bis:
            stand = "wartet_code" if bis > jetzt else "code_abgelaufen"
        else:
            stand = "neu"
        aus[name] = {"stand": stand, "bis": bis, "eingerichtet_utc": eingerichtet, "angemeldet_utc": angemeldet,
                     "firmenkonto": bool(int(hat_sso or 0))}
    return aus


def eingerichtet_melden(con, pid, name, weg=None):
    """Die Seite meldet: NAME hat Passwort und zweiten Faktor gesetzt (oder – weg „firmenkonto“ – sich zum ersten Mal mit
    dem Firmenkonto angemeldet). Ohne Rolle wartet er auf Freigabe – das geht an den Menschen (Nachricht, damit auch als Push)."""
    b = finden(con, name)
    if not b:
        return {"gemeldet": False}
    if weg == "firmenkonto":
        kurz = f"{name} hat sich zum ersten Mal mit dem Firmenkonto angemeldet" if b["rolle"] else f"Neuer Benutzer {name} wartet auf Freigabe"
        text = (f"{name} hat sich mit dem Firmenkonto ({b['email'] or '–'}) angemeldet"
                + (f" und arbeitet als {NAMEN[b['rolle']]}." if b["rolle"] else
                   " und sieht bis zur Freigabe nur „Dein Zugang wird geprüft“. Rolle und Projekte vergibst du am PC unter"
                   f" Einstellungen › Benutzer (oder: amw benutzer aendern {name} --rolle … --projekte …)."))
    elif b["rolle"]:
        kurz = f"{name} hat sich zum ersten Mal angemeldet"
        text = f"{name} hat Passwort und zweiten Faktor eingerichtet und arbeitet als {NAMEN[b['rolle']]}."
    else:
        kurz = f"Neuer Benutzer {name} wartet auf Freigabe"
        text = (f"{name} hat Passwort und zweiten Faktor eingerichtet und sieht bis zur Freigabe nur „Dein Zugang wird geprüft“."
                " Rolle und Projekte vergibst du am PC unter Einstellungen › Benutzer"
                f" (oder: amw benutzer aendern {name} --rolle … --projekte …).")
    kern.posten(con, pid, "AMW", kern.ENTWICKLER, "meldung", kurz, text)
    return {"gemeldet": True}

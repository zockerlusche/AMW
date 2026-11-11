"""Festplatte: freier Platz auf den Laufwerken, auf denen die Datenbank und die Projektordner liegen – mit Warnstufen und
einer Meldung an Lead und Mensch, wenn ein Laufwerk knapp wird. Dazu Aufräumvorschläge für alte Sicherungen.

Die AMW löscht und verschiebt hier nichts: Sie zeigt, was sich aufräumen ließe (was, wie groß, wie alt). Aufbewahrt
werden nach der Regel die neuesten Sicherungen (Einstellung sicherungen_behalten) und je veröffentlichter Version die
letzte Sicherung davor; alles andere ist ein Vorschlag.
"""
import datetime
import json
import os
import re
import shutil
import time

from . import db, einstellungen, kern

SICHERUNG = re.compile(r"^(?:amw-)?sicherung(?:-.+)?-(\d{4})-(\d\d)-(\d\d)-(\d\d)(\d\d)\.db$")
PRUEFEN_S = 600               # so oft misst der Wächter die Laufwerke
STUFEN = {None: 0, "gelb": 1, "rot": 2}


def laufwerk(pfad):
    """Das Laufwerk eines Pfads („F:“; ohne Laufwerksbuchstaben die Wurzel „/“)."""
    return os.path.splitdrive(os.path.abspath(pfad))[0].upper() or "/"


def stufe(frei_prozent):
    gelb, rot = float(einstellungen.wert("platte_gelb_prozent")), float(einstellungen.wert("platte_rot_prozent"))
    return "rot" if frei_prozent < rot else "gelb" if frei_prozent < gelb else None


def orte(con):
    """{Laufwerk: {"pfad": ein Ordner darauf, "projekte": [projekt_id, …], "daten": liegt die Datenbank dort?}}"""
    aus = {}
    daten = os.path.dirname(db.db_pfad())
    aus[laufwerk(daten)] = {"pfad": daten, "projekte": [], "daten": True}
    for p in con.execute("SELECT id FROM projekt ORDER BY id").fetchall():
        ordner = kern.projekt_ordner(con, p["id"])
        if ordner:
            aus.setdefault(laufwerk(ordner), {"pfad": ordner, "projekte": [], "daten": False})["projekte"].append(p["id"])
    return aus


def laufwerke(con, messen=None):
    """Je Laufwerk: {"laufwerk", "frei_gb", "gesamt_gb", "frei_prozent", "stufe", "projekte", "daten"} – knappstes zuerst.
    Laufwerke, die sich nicht messen lassen, fehlen."""
    messen, aus = messen or shutil.disk_usage, []
    for name, o in orte(con).items():
        try:
            m = messen(o["pfad"])
        except OSError:
            continue
        if not m.total:
            continue
        prozent = round(m.free * 100 / m.total, 1)
        aus.append({"laufwerk": name, "frei_gb": round(m.free / 2 ** 30, 1), "gesamt_gb": round(m.total / 2 ** 30, 1),
                    "frei_prozent": prozent, "stufe": stufe(prozent), "projekte": o["projekte"], "daten": o["daten"]})
    return sorted(aus, key=lambda x: x["frei_prozent"])


# --- Sicherungen: was nach der Aufbewahrungsregel übrig ist ---------------------------------------------------------

def _groesse(pfad):
    if os.path.isfile(pfad):
        return os.path.getsize(pfad)
    summe = 0
    for wurzel, _, dateien in os.walk(pfad):
        for d in dateien:
            try:
                summe += os.path.getsize(os.path.join(wurzel, d))
            except OSError:
                pass
    return summe


def sicherungen(ordner=None):
    """Sicherungen im Ordner der Datenbank, neueste zuerst: [{"name", "zeit" (Ortszeit laut Name), "bytes"}] – die
    Dokumente-Ablage daneben („…-dokumente“) zählt zur Größe."""
    ordner = ordner or os.path.dirname(db.db_pfad())
    aus = []
    try:
        namen = os.listdir(ordner)
    except OSError:
        return aus
    for n in namen:
        m = SICHERUNG.match(n)
        if not m:
            continue
        try:
            zeit = datetime.datetime(*(int(x) for x in m.groups()))
            pfad = os.path.join(ordner, n)
            groesse = os.path.getsize(pfad)
            ablage = os.path.splitext(pfad)[0] + "-dokumente"
            if os.path.isdir(ablage):
                groesse += _groesse(ablage)
            aus.append({"name": n, "zeit": zeit, "bytes": groesse})
        except (OSError, ValueError):
            pass
    return sorted(aus, key=lambda x: x["zeit"], reverse=True)


def versionen(con):
    """Zeitpunkte (Ortszeit) aller veröffentlichten Versionen – je Version bleibt die letzte Sicherung davor."""
    aus = []
    for r in con.execute("SELECT zeit_utc FROM release WHERE art = 'version' AND zeit_utc IS NOT NULL").fetchall():
        try:
            aus.append(datetime.datetime.strptime(r[0][:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=datetime.timezone.utc)
                       .astimezone().replace(tzinfo=None))
        except ValueError:
            pass
    return aus


def aufraeumen(liste, behalten, versionen=(), jetzt=None):
    """Aufräumvorschläge: die Sicherungen, die nach der Regel nicht gebraucht werden – [{"name", "bytes", "tage"}],
    älteste zuerst. Bleiben: die `behalten` neuesten und je Version die letzte Sicherung davor."""
    jetzt = jetzt or datetime.datetime.now()
    bleibt = {x["name"] for x in liste[:max(0, int(behalten))]}
    for v in versionen:
        davor = next((x for x in liste if x["zeit"] <= v), None)       # liste: neueste zuerst
        if davor:
            bleibt.add(davor["name"])
    return [{"name": x["name"], "bytes": x["bytes"], "tage": max(0, (jetzt - x["zeit"]).days)}
            for x in reversed(liste) if x["name"] not in bleibt]


def vorschlaege(con):
    """Aufräumvorschläge für diesen PC: {"sicherungen": […], "bytes": Summe, "ordner": wo sie liegen}."""
    liste = aufraeumen(sicherungen(), einstellungen.wert("sicherungen_behalten"), versionen(con))
    return {"sicherungen": liste, "bytes": sum(x["bytes"] for x in liste), "ordner": os.path.dirname(db.db_pfad())}


# --- Wache: melden, wenn ein Laufwerk knapp wird --------------------------------------------------------------------

def _merk_datei():
    return os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "amw", "platte.json")


def _gemeldet():
    try:
        with open(_merk_datei(), encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _merken(d):
    try:
        os.makedirs(os.path.dirname(_merk_datei()), exist_ok=True)
        with open(_merk_datei(), "w", encoding="utf-8") as f:
            json.dump(d, f)
    except OSError:
        pass


def meldetext(l, vorschlag_bytes=0):
    text = (f"Laufwerk {l['laufwerk']} wird knapp: noch {str(l['frei_gb']).replace('.', ',')} GB frei"
            f" ({str(l['frei_prozent']).replace('.', ',')} % von {str(l['gesamt_gb']).replace('.', ',')} GB).")
    if l["stufe"] == "rot":
        text += " Schwere Läufe und Sicherungen können daran scheitern."
    if vorschlag_bytes >= 2 ** 20:
        text += f" Alte Sicherungen belegen {vorschlag_bytes / 2 ** 30:.1f} GB – Vorschläge zeigt `amw rechner`.".replace(".", ",", 1)
    return text + " Die AMW löscht nichts; aufräumen kann nur der Mensch."


class Wache:
    """Misst alle PRUEFEN_S die Laufwerke. Wird eines knapper als zuletzt gemeldet (frei → gelb → rot), bekommen die
    Leads der Projekte auf diesem Laufwerk eine Meldung und der Mensch eine. Erholt es sich, wird das vermerkt – die
    nächste Verschlechterung meldet wieder. Der Stand je Laufwerk steht in einer Datei dieses PCs (kein Neu-Melden nach
    einem Neustart)."""

    def __init__(self, con, messen=None):
        self.con, self.messen, self.zuletzt = con, messen, 0.0

    def runde(self, jetzt=None):
        jetzt = jetzt or time.time()
        if jetzt - self.zuletzt < PRUEFEN_S:
            return []
        self.zuletzt = jetzt
        gemeldet, aus, neu = _gemeldet(), [], {}
        for l in laufwerke(self.con, self.messen):
            neu[l["laufwerk"]] = l["stufe"]
            if STUFEN[l["stufe"]] <= STUFEN.get(gemeldet.get(l["laufwerk"]), 0):
                continue
            text = meldetext(l, vorschlaege(self.con)["bytes"] if l["daten"] else 0)
            projekte = l["projekte"] or [p["id"] for p in self.con.execute("SELECT id FROM projekt ORDER BY id LIMIT 1").fetchall()]
            mensch = False
            for pid in projekte:
                with db.schreiben(self.con):
                    lead = kern.lead(self.con, pid)
                    if lead:
                        kern._posten(self.con, pid, "AMW", lead, "meldung", text)
                    if not mensch:                           # der Mensch bekommt sie einmal, nicht je Projekt
                        kern._posten(self.con, pid, "AMW", kern.ENTWICKLER, "meldung", text)
                        mensch = True
            aus.append(text)
        if neu != {k: gemeldet.get(k) for k in neu} or set(gemeldet) - set(neu):
            _merken(neu)
        return aus

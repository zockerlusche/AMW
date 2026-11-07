"""Fremde GPU-Last melden (KI Stufe 3, doc/plan-lokale-ki.md §5): Rechnet etwas auf der Grafikkarte, ohne dass ein Lauf mit
Grafikkarte oder Schirm angemeldet ist, bekommen die Leads eine Meldung. Die AMW meldet nur – sie beendet nie etwas.

Damit es keine Fehlalarme gibt: erst ab GRENZE_PROZENT Auslastung über MESSUNGEN Prüfungen hintereinander, nur wenn der
Entwickler seit LEERLAUF_S nicht am PC war (sonst ist es vermutlich seine eigene Arbeit), höchstens einmal je PAUSE_S.
"""
import subprocess
import time

from . import db, kern, schirm

GRENZE_PROZENT = 60          # Desktop allein (Browser, Fenster) liegt bei ~30 % (gemessen 07.11.)
MESSUNGEN = 3
LEERLAUF_S = 300
PAUSE_S = 3600
OHNE_FENSTER = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def messen():
    """(Auslastung %, [(Programm, MB)]) über nvidia-smi; None, wenn es keins gibt oder es nicht antwortet."""
    try:
        aus = subprocess.run(["nvidia-smi", "--query-gpu=utilization.gpu", "--format=csv,noheader,nounits"],
                             capture_output=True, text=True, timeout=10, creationflags=OHNE_FENSTER)
        if aus.returncode:
            return None
        last = max(int(x.strip()) for x in aus.stdout.split("\n") if x.strip())
        apps = subprocess.run(["nvidia-smi", "--query-compute-apps=process_name,used_memory", "--format=csv,noheader,nounits"],
                              capture_output=True, text=True, timeout=10, creationflags=OHNE_FENSTER)
        programme = []
        for z in apps.stdout.split("\n"):
            if "," in z:
                name, mb = z.rsplit(",", 1)
                name = name.strip().replace("\\", "/").rsplit("/", 1)[-1]
                if mb.strip().isdigit() and int(mb) > 0 and not name.startswith("["):   # Windows (WDDM): oft ohne Angabe
                    programme.append((name, int(mb)))
        return last, programme
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def angemeldet(con):
    """Läuft gerade irgendwo (PC-weit) ein Lauf mit Grafikkarte oder Schirm?"""
    return bool(con.execute("SELECT 1 FROM lauf WHERE status = 'laeuft' AND (gpu = 1 OR schirm = 1) LIMIT 1").fetchone())


class Wache:
    def __init__(self, con, messen=messen, leerlauf=schirm.leerlauf_s):
        self.con, self.messen, self.leerlauf = con, messen, leerlauf
        self.hoch = 0                 # Messungen über der Grenze hintereinander
        self.gemeldet = 0.0

    def runde(self, jetzt=None):
        """Eine Messung; gibt die verschickten Meldungen zurück (Text je Lead)."""
        jetzt = jetzt or time.time()
        m = self.messen()
        if m is None or m[0] < GRENZE_PROZENT or angemeldet(self.con):
            self.hoch = 0
            return []
        self.hoch += 1
        weg = self.leerlauf()
        if self.hoch < MESSUNGEN or (weg is not None and weg < LEERLAUF_S) or jetzt - self.gemeldet < PAUSE_S:
            return []
        last, programme = m
        wer = ", ".join(f"{n} ({mb / 1024:.1f} GB)" for n, mb in sorted(programme, key=lambda x: -x[1])[:4]) or "unbekannt"
        text = (f"Fremde GPU-Last: {last} % ohne angemeldeten Lauf – Programme: {wer}. Wer rechnet, bitte über die Schlange"
                " (amw lauf ausfuehren --gpu …). Die AMW meldet nur und beendet nichts.")
        aus = []
        for p in self.con.execute("SELECT id FROM projekt ORDER BY id").fetchall():
            lead = kern.lead(self.con, p["id"])
            if lead:
                with db.schreiben(self.con):
                    kern._posten(self.con, p["id"], "AMW", lead, "meldung", text)
                aus.append(f"{lead}: {text}")
        self.gemeldet = jetzt
        self.hoch = 0
        return aus

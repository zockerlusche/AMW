"""Gesamtlauf und lokales Ausliefern eines Bündels ohne Agent (A2123, TH158 Fassung 5 „Bündeln ohne Agent“, Plan CCamwTL #33741/#33743).

Ein losgelöster Prozess (`python -m amw.buendel_auslieferung <projekt>`, der Dienst startet sich bei der Auslieferung neu) macht:
1. Zusammensetzen (A2120) – ein Paket mit Konflikt bleibt draußen (mit seinen Nachfolgern), der Rest wird ohne es neu
   zusammengesetzt; der Befund steht als Ereignis buendel_befund und geht an genau den Bauer (A2124, befund). Ein Konflikt nur in gebauten Dateien (GEBAUT)
   ist keiner: sie werden nach dem Zusammensetzen einmal neu gebaut (eigener Commit).
2. Version (A2121): Nummer, CHANGELOG, Versionsdatei; Versions-Commit nur mit diesen Dateien (und web/inc/VERSION); Zweig buendel-X.Y.Z.
3. Gesamtlauf über die Lauf-Schlange auf genau diesem Stand (buendel.gesamtlauf_rechnen).
4. Grün → mit buendel_ausliefern = an: je Paket GRÜN und Merge-OK der AMW auf den Bündel-Stand, dazu die Marke (Ereignis
   buendel_auslieferung, schritt „freigabe“) – nur dieser Prozess setzt sie; die Release-Kette nimmt ein Merge-OK der AMW für ein Bündel
   nur mit ihr an. Dann die Kette als AMW: Wartungsmodus mit ihrem Prozess, Warten auf Arbeiter, eine Sicherung, Fast-Forward, Tag, ein
   Neustart. Mit buendel_ausliefern = aus (Vorgabe, Einschalten nur durch Marcel): Ende bei „bereit“ wie A1876 (GRÜN mit dem Lead als
   Prüfer, Meldung mit den Befehlen).
5. Rot → teilen (A2122): jede Teilmenge wird mit Versions-Commit als losgelöster Commit (ohne Zweig) gebaut und gerechnet, höchstens
   TEILUNGEN_MAX Teilungsläufe. Die grün gelaufene Menge geht weiter wie in 4 – genau dieser Stand bekommt den Zweig.
Nach jedem Schritt: gilt eine Pause oder ein Wartungsmodus, den nicht diese Auslieferung gesetzt hat, endet sie. Bricht sie ab, wo auch
immer: der Arbeitsbaum steht wieder auf main, main bewegt nur die Kette, ein Wartungsmodus dieser Auslieferung wird aufgehoben, und
der Lead bekommt eine Meldung mit Stand und Zweig. Ende immer mit buendel_ende.

Angestoßen wird sie vom Dienst (runde: nur mit buendel_ausliefern = an und wenn der Auslöser A2119 es sagt) oder von Hand
(`amw paket ausliefern-buendel`, Lead oder Mensch). Nie, solange ein Bündel offen ist, ein Gesamtlauf läuft oder wartet, ein
Wartungsmodus, eine Pause oder ein Wochenlimit-Halt gilt.

Ereignisse (plan_ereignis, kein Schema): buendel_auslieferung {"schritt", …} – angestossen, zusammengesetzt, gesamtlauf, freigabe
(die Marke: zweig, sha, lauf, aufgaben), ausgeliefert, bereit, geteilt, abgebrochen; buendel_befund {"aufgabe", "art": konflikt|rot, …}.
"""
import json
import os
import subprocess
import sys

from . import db, kern

ART, BEFUND = "buendel_auslieferung", "buendel_befund"
SCHALTER = "buendel_ausliefern"
BUENDEL_GRUND = "stapel:buendel"              # A2124: GRÜN im Bündelbetrieb – die Aufgabe wartet still auf das Bündel
GEBAUT = ("web/inc/seite.html", "web/hilfe/*.json", "web/inc/VERSION")
TEILUNGEN_MAX = 3
ZUSAMMENSETZEN_MAX = 20                       # Konflikte hintereinander, dann Halt (je Runde fällt ein Paket heraus)


class Abbruch(kern.AmwFehler):
    """Die Auslieferung endet – mit Grund; was schon geschah, steht in der Meldung."""


def _ereignis(con, pid, ereignis, **werte):
    with db.schreiben(con):
        return db.einfuegen(con, "plan_ereignis", projekt_id=pid, zeit_utc=db.jetzt(), von="AMW", art=ereignis,
                            aufgabe_id=werte.get("aufgabe"), text=json.dumps(werte, ensure_ascii=False))


def _melden(con, pid, kurz, text):
    lead = kern.lead(con, pid) or kern.ENTWICKLER
    with db.schreiben(con):
        kern._posten(con, pid, "AMW", lead, "meldung", kurz[:200], text)


def gruen_ins_buendel(con, pid, p, ergebnis):
    """A2124: GRÜN auf ein Fenster-Paket bei buendel_ausliefern = an weckt nicht – die Aufgabe wartet still auf das Bündel (Grund
    BUENDEL_GRUND, Sorte wartet_stapel: gibt den Agenten frei, A2053) statt „alle Gründe erledigt – weiter“. Bei aus bleibt alles wie
    heute. p = Zeile der Prüfung; läuft im Schreibvorgang des Aufrufers. Rückgabe: True = Bündelbetrieb (der Aufrufer weckt nicht)."""
    if ergebnis != "gruen" or not p["aufgabe_id"] or str(p["zweig"] or "").startswith("buendel-") \
            or kern.projekt_wahl(con, pid, SCHALTER) != "an":
        return False
    a = con.execute("SELECT status FROM aufgabe WHERE id = ?", (p["aufgabe_id"],)).fetchone()
    if a and a["status"] in ("wartet", "blockiert"):
        from . import wartegrund
        wartegrund.anlegen(con, pid, "AMW", p["aufgabe_id"], BUENDEL_GRUND)
    return True


def befund_offen(con, pid, aid, kopf):
    """A2124: Art des Befunds (konflikt|rot), der für genau diesen Stand des Pakets schon gilt, sonst None. Ein solches Paket bleibt
    draußen, bis sein Bauer einen neuen Stand hat (neue grüne Prüfung bzw. neuer Kopf) – kein zweiter Weckruf zum selben Befund."""
    if not kopf:
        return None
    for (text,) in con.execute("SELECT text FROM plan_ereignis WHERE projekt_id = ? AND aufgabe_id = ? AND art = ? ORDER BY id DESC",
                               (pid, aid, BEFUND)):
        try:
            d = json.loads(text or "{}")
        except ValueError:
            continue
        if d.get("kopf") == kopf:
            return d.get("art")
    return None


def _bauer(con, pid, aid, kopf, agent):
    """Wer genau diesen Stand gebaut hat: Bauer der Prüfung auf genau diesem SHA, sonst der Besitzer der Aufgabe."""
    r = con.execute("SELECT bauer FROM pruefung WHERE projekt_id = ? AND aufgabe_id = ? AND sha = ? AND zweig NOT LIKE 'buendel-%'"
                    " AND bauer != 'AMW' ORDER BY id DESC LIMIT 1", (pid, aid, kopf or "")).fetchone()
    return (r[0] if r else None) or agent


def befund_text(b, art):
    """Der Befund in Worten – genau das, was der Bauer zum Nachbessern braucht."""
    stand = f"Stand {str(b.get('kopf') or '')[:8]}" + (f" (Zweig {b['zweig']})" if b.get("zweig") else "")
    if art == "konflikt":
        zeilen = [f"Konflikt beim Zusammensetzen auf main: {stand}" + (f", Commit {str(b['commit'])[:8]}" if b.get("commit") else ""),
                  f"Dateien: {', '.join(b.get('dateien') or []) or '–'}"]
        if b.get("nach"):
            zeilen.append("Davor im Bündel: " + ", ".join(f"A{x}" for x in b["nach"]))
    else:
        zeilen = [f"Gesamtlauf rot, beim Teilen als schuldig gefunden: {stand}"]
    if b.get("meldung"):
        zeilen.append(f"Meldung: {str(b['meldung'])[:800]}")
    zeilen.append("Das Paket bleibt mit diesem Stand draußen, der Rest geht ohne es weiter. Mit einem neuen Stand (neue Prüfbitte) nimmt"
                  " die AMW es wieder mit.")
    return "\n".join(zeilen)


def befund(con, pid, b, art, felder):
    """A2124 (TH158 F5): ein Befund weckt genau den Bauer des Pakets mit genau diesem Befund – einmal je Paket, Stand und Art; sonst
    niemanden. Fenster-Paket: Auftrag an den Bauer. p-Paket (ein Headless, kein Resume in Stufe 1): E8 an den Paket-Prüfer.
    Rückgabe: an wen (None: derselbe Befund galt schon)."""
    from . import arbeitspaket
    aid = b["aufgabe"]
    if befund_offen(con, pid, aid, b.get("kopf")) == art:
        return None
    text = befund_text(b, art)
    titel = (con.execute("SELECT titel FROM aufgabe WHERE id = ?", (aid,)).fetchone() or [""])[0]
    if arbeitspaket.lesen(con, aid).get("art") == "p":
        from . import entscheidung
        try:
            an = entscheidung.anwenden(con, pid, aid, "E8", f"Bündel/{art}", befund={"grund": text, "kopf": b.get("kopf")})["an"]
        except arbeitspaket.Ungueltig as e:                           # nicht (mehr) in merge_reihe – der Befund steht trotzdem
            an = None
            felder = {**felder, "nicht_gesetzt": str(e)[:200]}
    else:
        an = _bauer(con, pid, aid, b.get("kopf"), b.get("agent"))
        if not an or not con.execute("SELECT 1 FROM agent WHERE projekt_id = ? AND kennung = ? AND entfernt_utc IS NULL",
                                     (pid, an)).fetchone():
            an = kern.lead(con, pid) or kern.ENTWICKLER              # Bauer unbekannt oder entfernt: dann weiß es der Lead
        kurz = (f"A{aid}: Bündel – Konflikt in {', '.join((b.get('dateien') or [])[:3]) or 'deinem Stand'}" if art == "konflikt"
                else f"A{aid}: Bündel – Gesamtlauf rot, dein Stand ist schuldig")
        with db.schreiben(con):
            kern._posten(con, pid, "AMW", an, "auftrag", f"{kurz} – weiter: amw aufgabe start {aid}"[:200],
                         f"„{titel[:120]}“\n{text}", aufgabe_id=aid)
    from . import wartegrund
    g_art, g_bezug = wartegrund.bezug_lesen(con, pid, BUENDEL_GRUND)
    with db.schreiben(con):                                           # das Warten auf das Bündel endet – geweckt ist er oben
        wartegrund.erledige(con, pid, g_art, g_bezug, f"Befund aus dem Bündel ({art})", aufgabe_id=aid, leise=True)
    _ereignis(con, pid, BEFUND, aufgabe=aid, art=art, an=an, **felder)
    return an


def ist_amw(con, pid):
    from . import einrichtung
    ordner = kern.projekt_ordner(con, pid)
    return bool(ordner) and os.path.normcase(os.path.abspath(ordner)) == os.path.normcase(os.path.abspath(einrichtung.WURZEL))


# --- Darf sie jetzt? ------------------------------------------------------------------------------------------------------------

def hindernis(con, pid):
    """Warum jetzt keine Auslieferung beginnt – Text oder None."""
    from . import buendel, limithalt, pause, waechter
    offen = buendel.offenes_buendel(con, pid)
    if offen:
        return f"Bündel {offen['zweig']} ist noch offen"
    z = waechter.zustand()
    if z["wartung"]:
        return "Wartungsmodus ist an"
    if z["pause"]:
        return "Pause für die Headless-Pakete"
    if pause.zustand(con, pid).get("an"):
        return "Pause im Projekt"
    if limithalt.aktive(con, pid):
        return "Wochenlimit-Halt"
    g = con.execute("SELECT id FROM lauf WHERE status IN ('angemeldet', 'laeuft') AND beschreibung LIKE '%Gesamtlauf%' ORDER BY id LIMIT 1").fetchone()
    if g:
        return f"Gesamtlauf L{g[0]} läuft oder wartet"
    return None


def _zwischendurch(con, pid, eigene_wartung=False):
    """Nach jedem Schritt (Vorgabe 3, #33743): Pause oder ein fremder Wartungsmodus beendet die Auslieferung."""
    from . import pause, waechter
    z = waechter.zustand()
    if z["wartung"] and not (eigene_wartung and (z["wartung"] or {}).get("kette") == os.getpid()):
        raise Abbruch("Wartungsmodus von außen gesetzt")
    if z["pause"] or pause.zustand(con, pid).get("an"):
        raise Abbruch("Pause gesetzt")


# --- Anstoßen -------------------------------------------------------------------------------------------------------------------

def starter_starten(pid):
    """Losgelöster Prozess (wie buendel.starter_starten) – Rückgabe: PID."""
    from . import einrichtung
    u = {k: v for k, v in os.environ.items() if k not in ("AMW_AGENT", "AMW_PROJEKT") and not k.startswith("CLAUDE")}
    flags = (0x00000008 | 0x00000200 | getattr(subprocess, "CREATE_NO_WINDOW", 0)) if os.name == "nt" else 0   # DETACHED, NEW_GROUP
    proc = subprocess.Popen([sys.executable, "-X", "utf8", "-m", "amw.buendel_auslieferung", str(pid)], cwd=einrichtung.WURZEL,
                            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True,
                            creationflags=flags, env=u, start_new_session=os.name != "nt")
    return proc.pid


def anstossen(con, pid, von, grund, starten=None):
    """Von Hand (Lead oder Mensch) oder vom Dienst (von „AMW“). Rückgabe {"starter", "ausliefern": bool}."""
    if von != "AMW" and not (von == kern.ENTWICKLER or kern.ist_lead(con, pid, von)):
        raise kern.AmwFehler("Ein Bündel anstoßen dürfen der Lead oder der Mensch")
    h = hindernis(con, pid)
    if h:
        raise kern.AmwFehler(f"Jetzt kein Bündel: {h}")
    an = kern.projekt_wahl(con, pid, SCHALTER) == "an"
    _ereignis(con, pid, ART, schritt="angestossen", von=von, grund=grund, ausliefern=an)
    return {"starter": (starten or starter_starten)(pid), "ausliefern": an}


def _letzte_auslieferung(con, pid):
    r = con.execute("SELECT max(zeit_utc) FROM release WHERE projekt_id = ? AND art = 'version'", (pid,)).fetchone()
    return r[0] if r else None


def runde(con, jetzt=None, starten=None):
    """Dienst: je Projekt mit buendel_ausliefern = an fragt der Auslöser (A2119), ob jetzt gebündelt wird. Rückgabe: Texte."""
    from . import buendel_ausloeser, buendel_zusammensetzen, reihenfolge
    aus = []
    for (pid,) in con.execute("SELECT id FROM projekt ORDER BY id").fetchall():
        if kern.projekt_wahl(con, pid, SCHALTER) != "an" or hindernis(con, pid):
            continue
        bereit = [p["id"] for p in buendel_zusammensetzen.kandidaten(con, pid) if not p.get("befund")]   # A2124: Befund offen zählt nicht
        if not bereit:
            continue
        startklar = {z["agent"] for z in reihenfolge.berechnen(con, pid) if z["zustand"] == "startklar" and z["agent"]}
        blockierend = [r[0] for r in con.execute("SELECT DISTINCT d.vor FROM abhaengigkeit d JOIN aufgabe n ON n.id = d.nach"
                                                 " WHERE n.projekt_id = ? AND n.status NOT IN ('fertig', 'verworfen')", (pid,))]
        e = buendel_ausloeser.entscheiden(bereit, _letzte_auslieferung(con, pid), startklar, jetzt or db.jetzt(), blockierend,
                                          **buendel_ausloeser.einstellung(con, pid))
        if e["buendeln"]:
            anstossen(con, pid, "AMW", e["text"], starten)
            aus.append(f"P{pid}: Bündel angestoßen – {e['text']}")
    return aus


# --- Der Ablauf (eigener Prozess) -----------------------------------------------------------------------------------------------

class Lauf:
    """Ein Durchgang. rechnen(stand) → (rc, lauf, Grund) ist der Gesamtlauf (Tests: eine Attrappe); kette(zweig, lauf) liefert aus."""

    def __init__(self, con, pid, rechnen=None, kette=None, warte=None):
        from . import buendel
        self.con, self.pid = con, pid
        self.e = buendel.einstellungen(con, pid)
        self.repo = kern.projekt_ordner(con, pid)
        self.ziel = buendel.arbeitsbaum(con, pid)
        self.daten = os.path.join(os.path.dirname(self.ziel), "buendel-daten")
        os.makedirs(self.daten, exist_ok=True)
        self.rechnen = rechnen or self._rechnen
        self.kette = kette or self._kette
        self.warte = warte
        self.ausliefern = kern.projekt_wahl(con, pid, SCHALTER) == "an" and ist_amw(con, pid)   # andere Projekte: bis „bereit“
        self.zweig = None
        self.erledigt = []
        self.teilungen = 0

    def git(self, *args, ok=(0,)):
        from . import buendel
        return buendel._git(self.ziel, self.daten, *args, ok=ok)

    def git_repo(self, *args, ok=(0,)):
        from . import buendel
        return buendel._git(self.repo, self.daten, *args, ok=ok)

    def schritt(self, text, **werte):
        self.erledigt.append(text)
        _ereignis(self.con, self.pid, ART, **werte)
        _zwischendurch(self.con, self.pid)

    # Stand bauen: Pakete, gebaute Dateien, Version
    def zusammensetzen(self, nur=None, ohne=()):
        from . import buendel_zusammensetzen as bz
        ohne = set(ohne)
        for _ in range(ZUSAMMENSETZEN_MAX):
            r = bz.zusammensetzen(self.con, self.pid, ohne=ohne, gebaut=GEBAUT, nur=nur)
            if r["ok"]:
                return r, ohne
            b = r["befund"]
            befund(self.con, self.pid, b, "konflikt", {k: b.get(k) for k in ("agent", "zweig", "kopf", "commit", "dateien", "meldung", "nach")})
            ohne.add(b["aufgabe"])
        raise Abbruch(f"nach {ZUSAMMENSETZEN_MAX} Konflikten kein Bündel")

    def bauen(self, r):
        """Gebaute Dateien neu (eigener Commit), dann Version und Versions-Commit. Rückgabe {"version", "sha"}."""
        from . import buendel, buendel_version
        if self.e["schritt_befehl"]:
            self._schritt_befehl()
            self._commit(["*"], "Online-Seite gebaut", nur_gebaut=True)
        v = buendel_version.schreiben(self.con, self.pid, r["drin"], self.ziel)
        if self.e["schritt_befehl"]:
            self._schritt_befehl()
        eigene = list(v["dateien"]) + ["web/inc/VERSION"]
        self._commit(eigene, f"{v['version']}: Bündel ({len(r['drin'])} Paket{'e' if len(r['drin']) != 1 else ''})", genau=True)
        return {"version": v["version"], "sha": self.git("rev-parse", "HEAD")[1]}

    def _schritt_befehl(self):
        u = {k: v for k, v in os.environ.items() if k not in ("AMW_AGENT", "AMW_PROJEKT") and not k.startswith("CLAUDE")}
        u["AMW_DB"] = os.path.join(self.daten, "schritt.db")             # nie die Live-Datenbank
        if not os.path.exists(u["AMW_DB"]):
            db.anlegen(u["AMW_DB"]).close()
        r = subprocess.run(self.e["schritt_befehl"], shell=True, cwd=self.ziel, env=u, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", stdin=subprocess.DEVNULL, timeout=600, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if r.returncode != 0:
            raise Abbruch(f"Nacharbeit „{self.e['schritt_befehl']}“ endete mit {r.returncode}: {(r.stdout + r.stderr).strip()[-300:]}")

    def _commit(self, erlaubt, betreff, nur_gebaut=False, genau=False):
        """Diff-Tor: nur gebaute (bzw. die genannten) Dateien; jede andere Änderung hält an. Ohne Änderung kein Commit."""
        import fnmatch
        pfade = [x.strip() for x in self.git("diff", "--name-only", "HEAD")[1].splitlines() if x.strip()]
        gut = lambda p: any(fnmatch.fnmatchcase(p, m) for m in (GEBAUT if nur_gebaut else erlaubt))
        fremd = [p for p in pfade if not gut(p)]
        if fremd:
            raise Abbruch("Diff-Tor: auch andere Dateien geändert: " + ", ".join(fremd[:8]))
        if not pfade:
            if genau:
                raise Abbruch("Versions-Commit ohne Änderung")
            return
        self.git("add", "--", *pfade)
        self.git("commit", "-q", "-m", betreff)

    def _rechnen(self, stand):
        from . import buendel
        return buendel.gesamtlauf_rechnen(self.con, self.pid, self.ziel, stand["sha"], f"Gesamtlauf Bündel {stand['version']} @{stand['sha'][:8]}",
                                          stand["aufgaben"][0], self.warte)

    # Grün: Freigabe und Kette
    def freigeben(self, stand, lid):
        """GRÜN und Merge-OK der AMW je Paket auf den Bündel-Stand, dazu die Marke. Nur hier – kein Befehl, keine Seite."""
        jetzt = db.jetzt()
        text = (f"Bündel {stand['version']} ohne Agent (A2123): abgenommen ({', '.join(stand['abnahme'])}), Gesamtlauf L{lid} grün auf genau"
                f" {stand['sha'][:8]}")
        with db.schreiben(self.con):
            for aid in stand["aufgaben"]:
                db.einfuegen(self.con, "pruefung", projekt_id=self.pid, aufgabe_id=aid, zweig=self.zweig, sha=stand["sha"], bauer="AMW",
                             pruefer="AMW", punkte=text, ergebnis="gruen", bemerkung="von der AMW (Bündel ohne Agent, A2123)",
                             angefragt_utc=jetzt, ergebnis_utc=jetzt)
                db.einfuegen(self.con, "plan_ereignis", projekt_id=self.pid, zeit_utc=jetzt, von="AMW", art="merge_ok", aufgabe_id=aid,
                             text=self.zweig)
            db.einfuegen(self.con, "plan_ereignis", projekt_id=self.pid, zeit_utc=jetzt, von="AMW", art=ART,
                         text=json.dumps({"schritt": "freigabe", "zweig": self.zweig, "sha": stand["sha"], "lauf": lid,
                                          "aufgaben": stand["aufgaben"], "prozess": os.getpid()}, ensure_ascii=False))

    def _kette(self, zweig, lid):
        from . import auslieferung
        k = auslieferung.Kette(self.con, self.pid, "AMW", self.repo, ausgabe=lambda _: None, amw=ist_amw(self.con, self.pid))
        k.ausliefern(zweig, gesamtlauf=lid)

    def zweig_setzen(self, stand):
        self.zweig = f"buendel-{stand['version']}"
        if self.git_repo("rev-parse", "--verify", "--quiet", f"refs/heads/{self.zweig}", ok=(0, 1))[0] == 0:
            raise Abbruch(f"Zweig {self.zweig} gibt es schon – nichts überschrieben")
        self.git_repo("branch", self.zweig, stand["sha"])
        with db.schreiben(self.con):                                   # wie buendel.buendeln: das Bündel gilt als offen
            db.einfuegen(self.con, "plan_ereignis", projekt_id=self.pid, zeit_utc=db.jetzt(), von="AMW", art="buendel",
                         text=json.dumps({"version": stand["version"], "zweig": self.zweig, "sha": stand["sha"], "drin": stand["aufgaben"],
                                          "raus": stand["raus"], "ohne_agent": True}, ensure_ascii=False))

    def gruen(self, stand, lid):
        from . import buendel
        self.zweig_setzen(stand)
        if not self.ausliefern:
            v = {"version": stand["version"], "sha": stand["sha"], "drin": stand["aufgaben"]}
            buendel.bereit_melden(self.con, self.pid, self.zweig, v, 0, lid, self.e["gesamtlauf_befehl"])
            self.schritt(f"bereit {stand['version']}", schritt="bereit", zweig=self.zweig, version=stand["version"], lauf=lid)
            return "bereit"
        self.freigeben(stand, lid)
        self.kette(self.zweig, lid)
        self.schritt(f"ausgeliefert {stand['version']}", schritt="ausgeliefert", zweig=self.zweig, version=stand["version"], lauf=lid,
                     aufgaben=stand["aufgaben"])
        return "ausgeliefert"

    def stand(self, r):
        s = self.bauen(r)
        return {**s, "aufgaben": [p["id"] for p in r["drin"]], "abnahme": sorted({p.get("abnahme") or "AMW" for p in r["drin"]}),
                "raus": [{"id": p["id"], "grund": p["grund"]} for p in r["raus"]]}

    # Rot: teilen
    def teilen(self, r, lid):
        from . import buendel, buendel_teilen
        gelaufen = {}

        def pruefer(teil):
            self.teilungen += 1
            if self.teilungen > TEILUNGEN_MAX:
                return {"ok": None, "meldung": f"mehr als {TEILUNGEN_MAX} Teilungsläufe"}
            ids = [p["id"] for p in teil]
            rr, _ = self.zusammensetzen(nur=set(ids))
            if [p["id"] for p in rr["drin"]] != ids:
                return {"ok": False, "meldung": "Teilmenge lässt sich nicht genau so zusammensetzen"}
            s = self.stand(rr)
            rc, l, grund = self.rechnen(s)
            if grund:
                return {"ok": None, "meldung": grund}
            gelaufen[tuple(ids)] = (s, l)
            buendel.baum_auf(self.repo, self.ziel, self.daten, "main")
            return {"ok": rc == 0, "meldung": f"Gesamtlauf L{l} rc {rc}"}
        vor = {p["id"]: buendel._vor(self.con, p["id"]) for p in r["drin"]}
        t = buendel_teilen.teilen(r["drin"], pruefer, vor)
        for b in t["befunde"]:
            befund(self.con, self.pid, b, "rot", {k: b.get(k) for k in ("agent", "zweig", "kopf", "meldung", "nach")})
        self.schritt("geteilt", schritt="geteilt", status=t["status"], frei=[p["id"] for p in t["frei"]],
                     befunde=[b["aufgabe"] for b in t["befunde"]], wartet=[p["id"] for p in t["wartet"]], laeufe=t["laeufe"], lauf=lid)
        if t["status"] != buendel_teilen.GETEILT or not t["frei"]:
            raise Abbruch(f"Bündel rot, Teilen ohne grünes Ergebnis ({t['status']}: {t['meldung'] or 'kein Paket grün'})")
        s, l = gelaufen[tuple(p["id"] for p in t["frei"])]
        return self.gruen(s, l)

    # Ablauf
    def los(self):
        from . import buendel
        h = hindernis(self.con, self.pid)
        if h:
            raise Abbruch(f"jetzt nicht: {h}")
        r, _ = self.zusammensetzen()
        if not r["drin"]:
            self.schritt("nichts", schritt="nichts", raus=[{"id": p["id"], "grund": p["grund"]} for p in r["raus"]])
            return "nichts"
        s = self.stand(r)
        self.schritt(f"zusammengesetzt {s['version']}", schritt="zusammengesetzt", version=s["version"], sha=s["sha"], aufgaben=s["aufgaben"],
                     raus=s["raus"])
        rc, lid, grund = self.rechnen(s)
        if grund:
            raise Abbruch(f"Gesamtlauf: {grund}")
        self.schritt(f"Gesamtlauf L{lid} rc {rc}", schritt="gesamtlauf", lauf=lid, rc=rc, sha=s["sha"])
        if rc == 0:
            return self.gruen(s, lid)
        buendel.baum_auf(self.repo, self.ziel, self.daten, "main")
        return self.teilen(r, lid)

    def aufraeumen(self, fehler):
        """Nach einem Abbruch: Arbeitsbaum auf main, eigener Wartungsmodus aus, Meldung an den Lead."""
        from . import buendel, waechter
        try:
            buendel.baum_auf(self.repo, self.ziel, self.daten, "main")
        except Exception:                                              # noqa: BLE001 – die Meldung geht trotzdem
            pass
        w = waechter.zustand()["wartung"] or {}
        if w.get("kette") == os.getpid() or (w.get("kette") and waechter.wartung_von_kette()):
            waechter.wartung_aus()
        _ereignis(self.con, self.pid, ART, schritt="abgebrochen", grund=str(fehler)[:500], zweig=self.zweig, erledigt=self.erledigt)
        _melden(self.con, self.pid, f"Bündel ohne Agent abgebrochen: {str(fehler)[:120]}",
                f"{fehler}\nErledigt: {', '.join(self.erledigt) or 'nichts'}\n"
                + (f"Zweig {self.zweig} liegt noch (nicht ausgeliefert, main unverändert)." if self.zweig else "Kein Zweig angelegt, main unverändert.")
                + "\nWartungsmodus dieser Auslieferung ist aufgehoben.")


def marke(con, pid, zweig, sha):
    """Hat dieser Prozess (und nur er) das Bündel `zweig`@`sha` selbst freigegeben? Für auslieferung.Kette.pruefen."""
    for r in con.execute("SELECT text FROM plan_ereignis WHERE projekt_id = ? AND art = ? AND von = 'AMW' AND text LIKE ? ORDER BY id DESC",
                         (pid, ART, '%"schritt": "freigabe"%')):
        d = json.loads(r[0] or "{}")
        if d.get("zweig") == zweig and d.get("sha") == sha:
            return True
    return False


def ausfuehren(con, pid, rechnen=None, kette=None, warte=None):
    """Ein Durchgang mit Aufräumen. Rückgabe: „ausgeliefert“ | „bereit“ | „nichts“ | „abgebrochen“."""
    from . import buendel
    l = Lauf(con, pid, rechnen, kette, warte)
    try:
        return l.los()
    except Exception as x:                                             # noqa: BLE001 – jeder Abbruch wird gemeldet
        l.aufraeumen(f"{type(x).__name__}: {x}" if not isinstance(x, kern.AmwFehler) else str(x))
        return "abgebrochen"
    finally:
        if l.zweig:
            buendel._ende(con, pid, l.zweig, {"ohne_agent": True})


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    con = db.verbinde()
    try:
        ausfuehren(con, int(argv[0]))
    finally:
        con.close()


if __name__ == "__main__":
    main()

"""Die AMW als MCP-Server (A1781, Marcel 15.11. 16:47): Chat-Leads in der Claude-App rufen amw-Befehle direkt als Werkzeuge
auf – schneller und mit weniger Tokens als über den Dateiaustausch, Pflicht-Parameter stehen im Schema.

Start (eine Instanz je Projekt und Lead; die Identität steht fest und ist nicht per Werkzeug wählbar):
    python -m amw.mcp_server --projekt <Name> --von <Lead>
Transport: stdio, JSON-RPC 2.0 nach der MCP-Spezifikation, eine Nachricht je Zeile – nur Python-Standardbibliothek.
Jedes Werkzeug ruft denselben Code wie die Befehlszeile (cli.main) mit denselben Rechten und Prüfungen; es gibt keine
zweite Logik. Was ein Werkzeug ausgibt, ist genau die Ausgabe des Befehls. Der Dateiaustausch bleibt als Rückfall.

Eintrag für die Claude-Desktop-Konfiguration: siehe doc/hilfe/mcp.md (eintragen tut der Mensch).
"""
import argparse
import contextlib
import io
import json
import logging
import sys
import threading
import time

from . import __version__, cli

log = logging.getLogger("amw.mcp")

VERSIONEN = ("2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05")   # neueste zuerst
FRIST_S = 120

ANWEISUNG = ("Werkzeuge der AMW (Agentenmanagement) für dieses Projekt. Beginne jeden Durchgang mit `takt`: er zeigt Postfach,"
             " Prüfbitten, Fragen, Antworten des Menschen, Läufe, Lead-Runde und Auslieferungen. Ganze Nachrichten mit `lesen`"
             " (ids), schreiben mit `posten`. Du handelst als der Agent, für den dieser Server gestartet wurde.")


# Feld: (name, typ, beschreibung, ziel, pflicht, auswahl). typ: s Text, i Zahl, b ja/nein, ai Liste Zahlen, as Liste Texte.
# ziel: "--option" (Liste: je Eintrag einmal) oder "#" (Position, in der Reihenfolge der Felder). Ein Werkzeug ist damit nur
# (Beschreibung, feste Befehlszeile, Felder) – Schema, Prüfung und Befehlszeile entstehen daraus; jedes ruft cli.main.
def F(name, typ, text, ziel, pflicht=False, auswahl=None):
    return (name, typ, text, ziel, pflicht, auswahl)


def NR(was):
    return F("id", "i", f"Nummer {was} (nur die Zahl)", "#", True)


GROESSE = ("S", "M", "L", "XL")
ZUSTAENDE = ("entwurf", "startklar", "laeuft", "abgegeben", "abnahme", "merge_reihe", "gemergt", "fertig", "blockiert", "unklar",
             "wartet_interaktiv", "abgebrochen", "zurueckgestellt")
# Paketfelder (A1845, Mischbetrieb): wer ausführt und womit – dieselben wie amw aufgabe neu|aendern
PAKET = [F("paket", "s", "wer ausführt: agent (interaktiver Agent), sitzung (neue Sitzung) oder p (frischer claude -p-Arbeiter)",
           "--paket", False, ("agent", "sitzung", "p")),
         F("pruefbefehl", "s", "Abnahme-Befehl, den die AMW ausführt (Pflicht bei p; vor dem Bau rot)", "--pruefbefehl"),
         F("dateien", "s", "Bereiche: Dateien/Muster, die das Paket ändern darf (Pflicht bei p, eng halten)", "--dateien"),
         F("nach", "s", "erst nach diesen Aufgaben, z. B. 1201,1203", "--nach"),
         F("gewicht", "s", "leicht oder schwer", "--gewicht", False, ("leicht", "schwer")),
         F("ressourcen", "s", "gpu,bildschirm (leer: keine)", "--ressourcen"), F("modell", "s", "wie claude --model", "--modell"),
         F("effort", "s", "wie claude --effort", "--effort", False, ("low", "medium", "high")),
         F("pakettyp", "s", "normal, test-schreiben (Test + Änderung) oder test-ergaenzen (nur Tests für bestehenden Code)", "--pakettyp", False, ("normal", "test-schreiben", "test-ergaenzen")),
         F("nie_gleichzeitig", "s", "nie gleichzeitig mit diesen Aufgaben, z. B. A12,A13", "--nie-gleichzeitig"),
         F("gleiche_ressource", "s", "Name einer gemeinsamen Ressource (laufen nacheinander)", "--gleiche-ressource")]

WERKZEUGE = {
    "takt": ("Ein Durchgang in einem Aufruf: Postfach mit gekürztem Text, Prüfbitten an dich, Fragen an dich, Antworten des"
             " Menschen, Läufe mit Wartegrund, Lead-Runde, Auslieferungen. Gezeigte Nachrichten gelten als gelesen.", ["takt"],
             [F("seit", "s", "Antworten/Läufe/Auslieferungen seit (HH:MM oder Datum); sonst seit dem letzten Takt", "--seit"),
              F("abhaken", "b", "gezeigte Infos und Meldungen gleich erledigen", "--abhaken")]),
    "lesen": ("Nachrichten lesen: ohne ids die offene Liste, mit ids die ganzen Nachrichten.", ["lesen"],
              [F("ids", "ai", "Nummern der Nachrichten (ohne #)", "#"), F("neu", "b", "nur Ungelesenes, neueste zuerst", "--neu")]),
    "posten": ("Nachricht schicken (an einen Agenten, alle oder Entwickler).", ["posten"],
               [F("an", "s", "Empfänger: Kennung eines Agenten, alle oder Entwickler", "--an", True),
                F("art", "s", "Art der Nachricht", "--art", True, ("auftrag", "frage", "antwort", "info", "korrektur", "meldung")),
                F("kurz", "s", "worum es geht, ein Satz", "--kurz", True), F("text", "s", "ausführlicher Text", "--text"),
                F("antwort_auf", "i", "Nummer der Nachricht, auf die du antwortest", "--antwort-auf"),
                F("aufgabe", "i", "Nummer der Aufgabe", "--aufgabe"),
                F("bezug", "s", "worum es geht: A<nr>, F<nr>, D<nr>, M<nr>, P<nr>, L<nr>, T<nr>, B<nr> oder @Kennung", "--bezug")]),
    "erledigt": ("Nachrichten als erledigt markieren.", ["erledigt"],
                 [F("ids", "ai", "Nummern der Nachrichten", "#", True), F("bemerkung", "s", "warum/wie erledigt", "--bemerkung")]),
    "kontext": ("Startinformationen: Regeln, Liste, Läufe, Bildschirm – für dich oder einen Agenten.", ["kontext"],
                [F("agent", "s", "Kennung eines Agenten (leer: du)", "#")]),
    "aufgabe_liste": ("Aufgaben des Projekts (offen; mit alle auch fertige).", ["aufgabe", "liste"],
                      [F("agent", "s", "nur dieser Agent", "--agent"), F("bogen", "i", "nur dieser Meilenstein", "--bogen"),
                       F("alle", "b", "auch fertige und verworfene", "--alle")]),
    "aufgabe_zeige": ("Eine Aufgabe ganz: Auftrag, Status, Wartegründe, Kriterien.", ["aufgabe", "zeige"],
                      [NR("der Aufgabe"), F("kurz", "b", "nur Status, Agent, Titel und Wartegründe", "--kurz")]),
    "aufgabe_neu": ("Neue Aufgabe anlegen.", ["aufgabe", "neu"],
                    [F("titel", "s", "kurzer Titel", "--titel", True), F("agent", "s", "Bearbeiter (Kennung oder Entwickler)", "--agent"),
                     F("auftrag", "s", "was genau zu tun ist", "--auftrag"), F("bogen", "i", "Meilenstein", "--bogen"),
                     F("ohne_bogen", "b", "bewusst ohne Meilenstein (Lead)", "--ohne-bogen"),
                     F("kriterien", "as", "Abnahmekriterien", "--kriterium"), F("rang", "i", "Rang (kleiner = früher)", "--rang"),
                     F("groesse", "s", "Größe", "--groesse", False, GROESSE), *PAKET]),
    "aufgabe_aendern": ("Eine Aufgabe ändern (nur die angegebenen Felder).", ["aufgabe", "aendern"],
                        [NR("der Aufgabe"), F("titel", "s", "neuer Titel", "--titel"), F("agent", "s", "neuer Bearbeiter", "--agent"),
                         F("auftrag", "s", "neuer Auftrag", "--auftrag"), F("bogen", "i", "Meilenstein", "--bogen"),
                         F("kriterien", "as", "Abnahmekriterien (ersetzt die Liste)", "--kriterium"), F("rang", "i", "Rang", "--rang"),
                         F("groesse", "s", "Größe", "--groesse", False, GROESSE), *PAKET]),
    "paket_zeigen": ("Paket einer Aufgabe: Art, Zustand, Abnahme-Befehl, Bereiche, Modell, Effort … (mit Vorgaben) und letzte"
                     " Zustandswechsel.", ["paket", "zeigen"], [NR("der Aufgabe")]),
    "paket_zustand": ("Zustand eines p-Pakets von Hand wechseln (nur erlaubte Übergänge; Lead).", ["paket", "zustand"],
                      [NR("der Aufgabe"), F("zustand", "s", "neuer Zustand", "#", True, ZUSTAENDE),
                       F("grund", "s", "warum", "--grund"), F("beleg", "s", "bei fertig: Commit", "--beleg")]),
    "bogen_liste": ("Meilensteine mit Stand (fertig/offen je Meilenstein).", ["bogen", "liste"], []),
    "bogen_zeigen": ("Ein Meilenstein ganz, mit seinen Aufgaben.", ["bogen", "zeigen"], [NR("des Meilensteins")]),
    "pruefung_liste": ("Prüfbitten (offen; mit alle auch erledigte).", ["pruefung", "liste"], [F("alle", "b", "auch erledigte", "--alle")]),
    "pruefung_zeige": ("Eine Prüfbitte ganz (Punkte, Stand, Bemerkung).", ["pruefung", "zeige"], [NR("der Prüfbitte")]),
    "pruefung_urteil": ("Ergebnis einer Prüfbitte eintragen: grün oder rot.", ["pruefung"],
                        [F("ergebnis", "s", "gruen oder rot", "#", True, ("gruen", "rot")), NR("der Prüfbitte"),
                         F("bemerkung", "s", "Begründung bzw. was fehlt", "--bemerkung")]),
    "freigabe_merge": ("Merge-OK für eine Aufgabe (Lead): ihr grün geprüfter Stand darf ausgeliefert werden.", ["freigabe", "merge"],
                       [F("aufgabe", "i", "Nummer der Aufgabe", "#", True), F("zweig", "s", "nur für diesen Zweig", "--zweig"),
                        F("zurueck", "b", "OK zurücknehmen", "--zurueck"),
                        F("ausnahme", "s", "ohne eigenen Gesamtlauf – mit Grund", "--ausnahme")]),
    "frage_liste": ("Offene Fragen (an den Menschen und an dich).", ["frage", "liste"], []),
    "frage_zeige": ("Eine Frage ganz: Optionen, Empfehlung, Grund, Antwort.", ["frage", "zeige"], [NR("der Frage")]),
    "frage_neu": ("Frage stellen – an den Menschen mit Optionen und Empfehlung.", ["frage", "neu"],
                  [F("an", "s", "an wen", "--an", True, ("entwickler", "tl", "zustaendig")),
                   F("kurz", "s", "die Frage in einem Satz", "--kurz", True),
                   F("optionen", "as", "Optionen, je 'A=Text'", "--option"), F("empfehlung", "s", "Kürzel der empfohlenen Option", "--empfehlung"),
                   F("grund", "s", "warum du das empfiehlst", "--grund"), F("worum", "s", "worum es geht", "--worum"),
                   F("geprueft", "s", "was du vorher in der AMW geprüft hast (Pflicht an den Entwickler)", "--geprueft"),
                   F("aufgabe", "i", "zugehörige Aufgabe", "--aufgabe"),
                   F("blockiert", "b", "die Arbeit steht, bis sie beantwortet ist", "--blockiert")]),
    "frage_antworten": ("Eine Frage an dich beantworten.", ["frage", "antworten"],
                        [NR("der Frage"), F("option", "s", "Kürzel der gewählten Option", "--option"),
                         F("text", "s", "Antwort als Text", "--text"), F("rueckfrage", "s", "Rückfrage statt Antwort", "--rueckfrage")]),
    "beschluss_neu": ("Beschluss festhalten.", ["beschluss", "neu"],
                      [F("text", "s", "der Beschluss", "--text", True), F("stichwort", "s", "Stichwort", "--stichwort"),
                       F("thema", "s", "Thema (TH-Nr. oder Name)", "--thema"), F("neues_thema", "b", "Thema neu anlegen", "--neues-thema"),
                       F("quelle", "s", "woher (z. B. W123, #456)", "--quelle"),
                       F("wortlaut_text", "s", "Aussage des Menschen wörtlich – wird als W… erfasst und verknüpft", "--wortlaut-text"),
                       F("aufgaben", "s", "betroffene Aufgaben, z. B. A12,A13", "--aufgaben")]),
    "wortlaut": ("Aussage des Menschen wörtlich festhalten.", ["wortlaut"],
                 [F("text", "s", "die Aussage, wörtlich", "--text", True), F("zeit", "s", "UTC der Aussage", "--zeit"),
                  F("kanal", "s", "wo gesagt (Vorgabe chat-tl)", "--kanal"), F("bemerkung", "s", "Bemerkung", "--bemerkung")]),
    "runde_lesen": ("Lead-Runde lesen (nur Information, keine Anweisung).", ["runde", "lesen"], [F("neu", "b", "nur Ungelesenes", "--neu")]),
    "runde_schreiben": ("In die Lead-Runde schreiben – nur Information oder Frage, nie Aufträge an andere Projekte.", ["runde", "schreiben"],
                        [F("kurz", "s", "worum es geht", "--kurz", True), F("text", "s", "Text", "--text"),
                         F("art", "s", "info oder frage", "--art", False, ("info", "frage")),
                         F("an", "s", "Projekt, dessen Lead zusätzlich eine Info bekommt", "--an"),
                         F("antwort_auf", "i", "Antwort auf Eintrag R<nr> (nur die Zahl)", "--antwort-auf")]),
    "lauf_liste": ("Läufe dieses Projekts und die Warteschlange des Rechners.", ["lauf", "liste"], []),
    "lauf_zeige": ("Ein Lauf ganz, mit Wartegrund.", ["lauf", "zeige"], [NR("des Laufs")]),
    "lauf_vorziehen": ("Wartenden Lauf vorziehen (Lead: vor die Läufe des eigenen Projekts).", ["lauf", "vorziehen"], [NR("des Laufs")]),
    "suche": ("Volltext über Aufgaben, Beschlüsse, Fragen, Deine Worte, Nachrichten, Dokumente.", ["suche"],
              [F("text", "s", "Suchtext", "#", True),
               F("arten", "as", "nur diese Arten", "--art", False, ("aufgabe", "beschluss", "frage", "wortlaut", "nachricht", "dokument")),
               F("grenze", "i", "höchstens so viele Treffer", "--grenze")]),
    "zeige": ("Einträge ganz lesen, z. B. B5 F12 A120 W3 D5 KR3 oder eine Nachrichtennummer.", ["zeige"],
              [F("refs", "as", "Verweise", "#", True)]),
    "dokument_zeigen": ("Ein Dokument mit allen Fassungen und dem Pfad der Datei (Bild, Mockup …); mit inhalt auch der Text.",
                        ["dokument", "zeigen"],
                        [F("nr", "s", "Nummer, z. B. D12 oder 12", "#", True),
                         F("inhalt", "b", "auch den Inhalt zeigen (Text bis 20 000 Zeichen, sonst Hinweis + Pfad)", "--inhalt"),
                         F("fassung", "i", "mit inhalt: diese Fassung statt der neuesten", "--fassung")]),
    "messung": ("Wartezeit und Kosten je Aufgabe: Liegezeit, aktiv, wartet nach Grund, $ (Zähler + erfasst), Lücken.", ["messung"],
                [F("nr", "s", "eine Aufgabe (A12 oder 12); leer: alle begonnenen", "#"),
                 F("seit", "s", "nur Aufgaben, die ab dann noch liefen", "--seit"), F("agent", "s", "nur dieser Agent", "--agent")]),
    "agent_liste": ("Agenten des Projekts kompakt: Zustand, Puls, offene Nachrichten, Tätigkeit, Aufgabe und worauf sie wartet.",
                    ["agent", "liste"], []),
    "wortlaut_liste": ("Erfasste Aussagen des Menschen (neueste zuerst) – zur Kontrolle, ob alles erfasst ist.", ["wortlaut", "--liste"],
                       [F("seit", "s", "nur ab diesem Zeitpunkt (15.11. oder 2026-11-15T18:00:00Z)", "--seit"),
                        F("grenze", "i", "höchstens so viele", "--grenze")]),
    "schirm": ("Bildschirm-Freigabe zeigen – oder als Lead auf das Wort des Menschen frei/zu schalten.", ["schirm"],
               [F("aktion", "s", "zeige (Vorgabe), frei oder zu", "#", False, ("zeige", "frei", "zu")),
                F("grund", "s", "frei/zu: Grund", "--grund"), F("bis", "s", "frei: bis Ortszeit HH:MM", "--bis"),
                F("verlauf", "b", "zeige: die letzten Wechsel", "--verlauf")]),
}
TYP = {"s": "string", "i": "integer", "b": "boolean", "ai": "array", "as": "array"}
TYP_TEXT = {"s": "Text", "i": "eine Zahl", "b": "true/false", "ai": "eine Liste von Zahlen", "as": "eine Liste von Texten"}


def _schema(felder):
    props = {}
    for name, typ, text, _, _, auswahl in felder:
        d = {"type": TYP[typ], "description": text}
        if typ in ("ai", "as"):
            d["items"] = {"type": "integer" if typ == "ai" else "string"}
        if auswahl:
            (d["items"] if typ in ("ai", "as") else d)["enum"] = list(auswahl)
        props[name] = d
    return {"type": "object", "properties": props, "required": [f[0] for f in felder if f[4]], "additionalProperties": False}


SCHLUESSEL_FELD = {"type": "string", "description": "Schlüssel dieses Projekts – steht in den Anweisungen deines Chats (A1826)"}


def werkzeug_liste(projekt=None, von=None):
    """Jedes Werkzeug verlangt den Schlüssel des Projekts (A1826); die Beschreibung nennt Projekt und Identität des Eintrags."""
    aus = []
    for n, (b, _, felder) in WERKZEUGE.items():
        s = _schema(felder)
        s["properties"] = {"schluessel": SCHLUESSEL_FELD, **s["properties"]}
        s["required"] = ["schluessel", *s["required"]]
        vorn = f"[Projekt {projekt} · Zugang von {von}] " if projekt else ""   # A1887: auch der Co-Entwickler (nicht nur der Lead)
        aus.append({"name": n, "description": vorn + b, "inputSchema": s})
    return aus


def _ist_zahl(v):
    return isinstance(v, int) and not isinstance(v, bool)


def _pruefen(name, args):
    """Pflichtfelder und Typen wie im Schema – der Client prüft nicht zuverlässig. Fehlertext für den Aufrufer oder None."""
    felder = {f[0]: f for f in WERKZEUGE[name][2]}
    for f in felder.values():
        if f[4] and args.get(f[0]) in (None, "", []):
            return f"Pflichtfeld fehlt: {f[0]}"
    for k, v in args.items():
        if k not in felder:
            return f"unbekanntes Feld: {k} (erlaubt: {', '.join(felder) or 'keine'})"
        typ, ziel, auswahl = felder[k][1], felder[k][3], felder[k][5]
        gut = {"s": isinstance(v, str), "i": _ist_zahl(v), "b": isinstance(v, bool),
               "ai": isinstance(v, list) and all(_ist_zahl(x) for x in v),
               "as": isinstance(v, list) and all(isinstance(x, str) for x in v)}[typ]
        if not gut:
            return f"{k} muss {TYP_TEXT[typ]} sein"
        if auswahl and any(x not in auswahl for x in (v if isinstance(v, list) else [v])):
            return f"{k}: eines von {', '.join(auswahl)}"
        if ziel == "#" and any(str(x).startswith("-") for x in (v if isinstance(v, list) else [v])):
            return f"{k} darf nicht mit - beginnen"         # keine Optionen durch die Hintertür (z. B. --von)
    return None


def befehlszeile(name, args):
    """Aus den geprüften Argumenten die Befehlszeile – Positionen in Feld-Reihenfolge, dann Optionen."""
    _, fest, felder = WERKZEUGE[name]
    pos, opt = [], []
    for fname, typ, _, ziel, _, _ in felder:
        v = args.get(fname)
        if v is None or v == "" or v == [] or v is False:
            continue
        if v is True:
            opt.append(ziel)
            continue
        werte = [str(x) for x in v] if isinstance(v, list) else [str(v)]
        if ziel == "#":
            pos += werte
        else:
            for w in werte:
                opt += [ziel, w]
    return list(fest) + pos + opt


def befehl_ausfuehren(argv):
    """cli.main mit umgeleiteter Ausgabe, nie auf Eingabe wartend; Kanal „mcp“ (Identität kommt vom Start, nicht vom Werkzeug)."""
    aus, fehler = io.StringIO(), io.StringIO()
    stdin = sys.stdin
    sys.stdin = io.StringIO()
    marke = cli.KANAL.set("mcp")
    try:
        with contextlib.redirect_stdout(aus), contextlib.redirect_stderr(fehler):
            try:
                rc = cli.main(argv)
            except SystemExit as e:
                rc = e.code if isinstance(e.code, int) else 2
            except Exception as e:
                print(f"FEHLER: {type(e).__name__}: {e}", file=sys.stderr)
                rc = 1
    finally:
        cli.KANAL.reset(marke)
        sys.stdin = stdin
    return rc or 0, aus.getvalue(), fehler.getvalue()


class Server:
    def __init__(self, projekt, von):
        self.projekt, self.von = projekt, von
        self.sperre = threading.Lock()                    # cli.main nacheinander (Umleitung von stdout ist prozessweit)
        self.haengt = None                                # (Werkzeug, Start) eines Befehls, der das Zeitlimit überschritten hat

    def protokoll(self, name, ergebnis):
        """A1826: jeder Aufruf in den Verlauf des Projekts (Planung › Verlauf) – Werkzeug und Ergebnis, nie Inhalte."""
        try:
            from . import db
            con = db.verbinde()
            try:
                pid = con.execute("SELECT id FROM projekt WHERE name = ? COLLATE NOCASE", (self.projekt,)).fetchone()
                if pid:
                    with db.schreiben(con):
                        db.einfuegen(con, "plan_ereignis", projekt_id=pid[0], zeit_utc=db.jetzt(), von=self.von, art="mcp_aufruf",
                                     text=f"MCP {name}: {ergebnis}"[:300])
            finally:
                con.close()
        except Exception:                                 # das Protokoll darf nie den Aufruf stören
            log.exception("MCP-Protokoll")

    def werkzeug(self, name, args):
        if name not in WERKZEUGE:
            return {"content": [{"type": "text", "text": f"Unbekanntes Werkzeug: {name}"}], "isError": True}
        args = args or {}
        if not isinstance(args, dict):
            return {"content": [{"type": "text", "text": "arguments muss ein Objekt sein"}], "isError": True}
        args = dict(args)
        schluessel = args.pop("schluessel", None)         # A1826: ohne den Schlüssel des Projekts keinerlei Wirkung
        from . import mcp_schluessel
        if not mcp_schluessel.stand(self.projekt)["da"]:
            self.protokoll(name, "abgelehnt – für das Projekt ist kein Schlüssel erzeugt")
            return {"content": [{"type": "text", "text": f"Für Projekt {self.projekt} ist noch kein Schlüssel erzeugt – der Mensch erzeugt"
                                 " ihn in der Workbench › Einstellungen › Projekt › MCP (oder amw mcp schluessel)."}], "isError": True}
        if not mcp_schluessel.pruefen(self.projekt, schluessel):
            self.protokoll(name, "abgelehnt – falscher oder fehlender Schlüssel")
            log.warning("MCP: %s abgelehnt – falscher oder fehlender Schlüssel", name)
            return {"content": [{"type": "text", "text": f"Abgelehnt: Dieser Connector gehört zu Projekt {self.projekt} ({self.von}) und"
                                 " der Schlüssel fehlt oder stimmt nicht. Nichts wurde gelesen oder geändert. Gehört dieser Chat zu"
                                 " einem anderen Projekt, schalte den Eintrag hier aus und nutze den deines Projekts."}], "isError": True}
        fehler = _pruefen(name, args)
        if fehler:
            return {"content": [{"type": "text", "text": fehler}], "isError": True}
        try:                                              # A1831: jeder angenommene Aufruf ist ein Lebenszeichen des Chat-Leads
            from . import bruecke                         # (wie beim Dateiaustausch) – sonst stand er nach 3 h als „beendet“
            bruecke.puls(self.von, projekt=self.projekt)
        except Exception:
            log.exception("MCP-Puls")
        argv = befehlszeile(name, args) + ["--projekt", self.projekt, "--von", self.von]
        haengt = self.haengt
        if haengt and self.sperre.locked():               # TL P205: nicht still hinter einem hängenden Befehl blockieren
            seit = int(time.monotonic() - haengt[1])
            log.warning("MCP: %s abgelehnt – %s hängt seit %s s", name, haengt[0], seit)
            return {"content": [{"type": "text", "text": f"Noch nicht ausgeführt: der vorige Befehl ({haengt[0]}) hängt seit {seit} s"
                                 " (Datenbank belegt oder Rechner überlastet). Er kann noch fertig werden – in einer Minute erneut"
                                 " versuchen; bleibt es so, die Claude-App neu starten (beendet diesen Server)."}], "isError": True}
        self.haengt = None
        ergebnis = {}

        def los():
            with self.sperre:
                ergebnis["w"] = befehl_ausfuehren(argv)
        f = threading.Thread(target=los, daemon=True)
        f.start()
        f.join(FRIST_S)
        if f.is_alive():
            self.haengt = (name, time.monotonic() - FRIST_S)
            log.warning("MCP: %s nach %s s ohne Ergebnis", name, FRIST_S)
            return {"content": [{"type": "text", "text": f"Zeitlimit {FRIST_S} s – der Befehl hat nicht geantwortet (Datenbank belegt?)."
                                 " Er läuft im Hintergrund weiter; bis er endet, lehnt dieser Server weitere Befehle mit einer"
                                 " Meldung ab. Im Zweifel danach mit takt/lesen nachsehen, bevor du ihn wiederholst."}], "isError": True}
        rc, aus, err = ergebnis["w"]
        text = (aus + (("\n" if aus else "") + err if err else "")).strip() or ("ok" if rc == 0 else f"Fehler (rc {rc})")
        self.protokoll(name, "ok" if rc == 0 else f"Fehler rc {rc}")
        return {"content": [{"type": "text", "text": text}], "isError": rc != 0}

    def bearbeiten(self, n):
        """Eine JSON-RPC-Nachricht → Antwort (dict) oder None (Benachrichtigung)."""
        if not isinstance(n, dict) or n.get("jsonrpc") != "2.0" or not isinstance(n.get("method"), str):
            if isinstance(n, dict) and "id" in n and "method" not in n:
                return None                               # Antwort des Clients auf etwas, das wir nie fragen
            return {"jsonrpc": "2.0", "id": n.get("id") if isinstance(n, dict) else None,
                    "error": {"code": -32600, "message": "ungültige Anfrage"}}
        mid, methode, p = n.get("id"), n["method"], n.get("params") or {}
        if "id" not in n:
            return None                                   # notifications/initialized, notifications/cancelled …
        try:
            if methode == "initialize":
                v = p.get("protocolVersion")
                erg = {"protocolVersion": v if v in VERSIONEN else VERSIONEN[0],
                       "capabilities": {"tools": {"listChanged": False}},
                       "serverInfo": {"name": "amw", "title": "AMW", "version": __version__},
                       "instructions": ANWEISUNG + f" Projekt {self.projekt}, du bist {self.von}. Jedes Werkzeug braucht den Schlüssel"
                                                   f" dieses Projekts (Feld schluessel) – er steht in den Anweisungen deines Chats."
                                                   f" Gehört dein Chat zu einem anderen Projekt, nutze diesen Eintrag nicht."}
            elif methode == "ping":
                erg = {}
            elif methode == "tools/list":
                erg = {"tools": werkzeug_liste(self.projekt, self.von)}
            elif methode == "tools/call":
                erg = self.werkzeug(p.get("name"), p.get("arguments"))
            else:
                return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"unbekannte Methode: {methode}"}}
        except Exception as e:                            # nie den Server beenden
            log.exception("MCP: %s", methode)
            return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32603, "message": f"{type(e).__name__}: {e}"}}
        return {"jsonrpc": "2.0", "id": mid, "result": erg}

    def laufen(self, ein=None, aus=None):
        ein = ein or io.TextIOWrapper(sys.stdin.buffer, encoding="utf-8")
        aus = aus or io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", newline="\n")
        for zeile in ein:
            zeile = zeile.strip()
            if not zeile:
                continue
            try:
                n = json.loads(zeile)
            except ValueError:
                antwort = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "kein gültiges JSON"}}
            else:
                antwort = [a for a in (self.bearbeiten(x) for x in n) if a] if isinstance(n, list) else self.bearbeiten(n)
            if antwort:
                aus.write(json.dumps(antwort, ensure_ascii=False) + "\n")
                aus.flush()


def main(argv=None):
    p = argparse.ArgumentParser(prog="python -m amw.mcp_server", description="Die AMW als MCP-Server (stdio) für einen Lead")
    p.add_argument("--projekt", required=True)
    p.add_argument("--von", required=True, help="als wer die Werkzeuge handeln (fest für diese Instanz)")
    a = p.parse_args(argv)
    logging.basicConfig(level=logging.WARNING, stream=sys.stderr)   # stdout gehört dem Protokoll
    Server(a.projekt, a.von).laufen()


if __name__ == "__main__":
    main()

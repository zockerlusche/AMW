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

from . import __version__, cli

log = logging.getLogger("amw.mcp")

VERSIONEN = ("2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05")   # neueste zuerst
FRIST_S = 120

ANWEISUNG = ("Werkzeuge der AMW (Agentenmanagement) für dieses Projekt. Beginne jeden Durchgang mit `takt`: er zeigt Postfach,"
             " Prüfbitten, Fragen, Antworten des Menschen, Läufe, Lead-Runde und Auslieferungen. Ganze Nachrichten mit `lesen`"
             " (ids), schreiben mit `posten`. Du handelst als der Agent, für den dieser Server gestartet wurde.")


def _zahl(text):
    return {"type": "integer", "description": text}


def _text(text, enum=None):
    d = {"type": "string", "description": text}
    if enum:
        d["enum"] = list(enum)
    return d


# name → (Beschreibung, Eigenschaften, Pflicht, argv-Bauer). Der Bauer macht aus den Argumenten die Befehlszeile.
WERKZEUGE = {
    "takt": ("Ein Durchgang in einem Aufruf: Postfach mit gekürztem Text, Prüfbitten an dich, Fragen an dich, Antworten des"
             " Menschen, Läufe mit Wartegrund, Lead-Runde, Auslieferungen. Gezeigte Nachrichten gelten als gelesen.",
             {"seit": _text("Antworten/Läufe/Auslieferungen seit (HH:MM oder Datum); sonst seit dem letzten Takt"),
              "abhaken": {"type": "boolean", "description": "gezeigte Infos und Meldungen gleich erledigen"}},
             [],
             lambda a: ["takt"] + (["--seit", a["seit"]] if a.get("seit") else []) + (["--abhaken"] if a.get("abhaken") else [])),
    "lesen": ("Nachrichten lesen: ohne ids die offene Liste, mit ids die ganzen Nachrichten.",
              {"ids": {"type": "array", "items": {"type": "integer"}, "description": "Nummern der Nachrichten (ohne #)"},
               "neu": {"type": "boolean", "description": "nur Ungelesenes, neueste zuerst"}},
              [],
              lambda a: ["lesen"] + [str(int(i)) for i in a.get("ids") or []] + (["--neu"] if a.get("neu") else [])),
    "posten": ("Nachricht schicken (an einen Agenten, alle oder Entwickler).",
               {"an": _text("Empfänger: Kennung eines Agenten, alle oder Entwickler"),
                "art": _text("Art der Nachricht", ("auftrag", "frage", "antwort", "info", "korrektur", "meldung")),
                "kurz": _text("worum es geht, ein Satz"),
                "text": _text("ausführlicher Text (optional)"),
                "antwort_auf": _zahl("Nummer der Nachricht, auf die du antwortest"),
                "aufgabe": _zahl("Nummer der Aufgabe (ohne A)"),
                "bezug": _text("worum es geht: A<nr>, F<nr>, D<nr>, M<nr>, P<nr>, L<nr>, T<nr>, B<nr> oder @Kennung")},
               ["an", "art", "kurz"],
               lambda a: ["posten", "--an", a["an"], "--art", a["art"], "--kurz", a["kurz"]]
               + (["--text", a["text"]] if a.get("text") else [])
               + (["--antwort-auf", str(int(a["antwort_auf"]))] if a.get("antwort_auf") else [])
               + (["--aufgabe", str(int(a["aufgabe"]))] if a.get("aufgabe") else [])
               + (["--bezug", a["bezug"]] if a.get("bezug") else [])),
}


def werkzeug_liste():
    return [{"name": n, "description": b, "inputSchema": {"type": "object", "properties": p, "required": r,
                                                           "additionalProperties": False}}
            for n, (b, p, r, _) in WERKZEUGE.items()]


def _pruefen(name, args):
    """Pflichtfelder und Typen wie im Schema – der Client prüft nicht zuverlässig. Fehlertext für den Aufrufer oder None."""
    _, props, pflicht, _ = WERKZEUGE[name]
    for k in pflicht:
        if args.get(k) in (None, ""):
            return f"Pflichtfeld fehlt: {k}"
    for k, v in args.items():
        if k not in props:
            return f"unbekanntes Feld: {k} (erlaubt: {', '.join(props)})"
        typ = props[k].get("type")
        if typ == "integer" and not (isinstance(v, int) and not isinstance(v, bool)):
            return f"{k} muss eine Zahl sein"
        if typ == "string" and not isinstance(v, str):
            return f"{k} muss Text sein"
        if typ == "boolean" and not isinstance(v, bool):
            return f"{k} muss true/false sein"
        if typ == "array" and not (isinstance(v, list) and all(isinstance(x, int) and not isinstance(x, bool) for x in v)):
            return f"{k} muss eine Liste von Zahlen sein"
        if "enum" in props[k] and v not in props[k]["enum"]:
            return f"{k}: eines von {', '.join(props[k]['enum'])}"
    return None


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

    def werkzeug(self, name, args):
        if name not in WERKZEUGE:
            return {"content": [{"type": "text", "text": f"Unbekanntes Werkzeug: {name}"}], "isError": True}
        args = args or {}
        if not isinstance(args, dict):
            return {"content": [{"type": "text", "text": "arguments muss ein Objekt sein"}], "isError": True}
        fehler = _pruefen(name, args)
        if fehler:
            return {"content": [{"type": "text", "text": fehler}], "isError": True}
        argv = WERKZEUGE[name][3](args) + ["--projekt", self.projekt, "--von", self.von]
        ergebnis = {}

        def los():
            with self.sperre:
                ergebnis["w"] = befehl_ausfuehren(argv)
        f = threading.Thread(target=los, daemon=True)
        f.start()
        f.join(FRIST_S)
        if f.is_alive():
            return {"content": [{"type": "text", "text": f"Zeitlimit {FRIST_S} s – der Befehl hat nicht geantwortet (Datenbank belegt?)."
                                 " Im Zweifel mit takt/lesen nachsehen, bevor du ihn wiederholst."}], "isError": True}
        rc, aus, err = ergebnis["w"]
        text = (aus + (("\n" if aus else "") + err if err else "")).strip() or ("ok" if rc == 0 else f"Fehler (rc {rc})")
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
                       "instructions": ANWEISUNG + f" Projekt {self.projekt}, du bist {self.von}."}
            elif methode == "ping":
                erg = {}
            elif methode == "tools/list":
                erg = {"tools": werkzeug_liste()}
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

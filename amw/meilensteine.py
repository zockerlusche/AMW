"""A2079: eine Nummer je Meilenstein. „M19“ ist überall, wo ein Mensch oder ein Agent sie liest oder schreibt, die Projektnummer
(bogen.nr, je Projekt) – nie die interne Nummer (bogen.id, über alle Projekte). Gespeichert und zwischen Seite und AMW ausgetauscht
wird weiter die interne Nummer.

- Befehle und MCP: Optionen, die einen Meilenstein meinen, haben den argparse-Typ `typ`. „M19“ löst cli.main nach dem Öffnen der
  Datenbank im Projekt des Befehls auf (`aufloesen`); eine nackte Zahl bleibt die interne Nummer (Skripte), die Ausgabe nennt beides.
  Gibt es M<n> im Projekt nicht, aber einen Meilenstein mit dieser internen Nummer, steht die richtige Nummer im Fehler – umgedeutet
  wird nie, auch nicht bei Kollision.
- Bezüge von Nachrichten: `bezug` übersetzt die Angabe M<Projektnummer> in das gespeicherte Kürzel M<intern> (wie bisher, damit
  alte Bezüge gelten); kern.bezug_text zeigt die Projektnummer. Die Seite schickt das gespeicherte Kürzel zurück – daher löst der
  Befehl auf, nicht kern.bezug_pruefen.
"""
import re

from . import kern

_M = re.compile(r"\s*[Mm](\d+)\s*")


class Angabe:
    """Was jemand auf der Befehlszeile geschrieben hat, noch nicht aufgelöst."""

    def __init__(self, zahl, projektnummer):
        self.zahl, self.projektnummer = zahl, projektnummer

    def __repr__(self):
        return f"{'M' if self.projektnummer else ''}{self.zahl}"


class Nummer(int):
    """Interne Nummer eines Meilensteins (überall als Zahl verwendbar); nackt: so wurde sie auf der Befehlszeile genannt."""
    nackt = False


def typ(text):
    """argparse-Typ: „M19“ = Projektnummer, sonst wie cli.nummer („57“, „B57“) = interne Nummer."""
    from . import cli
    m = _M.fullmatch(str(text))
    return Angabe(int(m.group(1)), True) if m else Angabe(cli.nummer(text), False)


def typ_projektnummer(text):
    """argparse-Typ für Optionen, bei denen auch die nackte Zahl schon immer die Projektnummer war (thema anhalten --meilenstein)."""
    return Angabe(typ(text).zahl, True)


def zu_id(con, pid, nr):
    """M<nr> → interne Nummer in diesem Projekt; sonst AmwFehler, wenn möglich mit der richtigen Nummer."""
    r = con.execute("SELECT id FROM bogen WHERE projekt_id = ? AND nr = ?", (pid, nr)).fetchone()
    if r:
        return r[0]
    x = con.execute("SELECT nr, titel FROM bogen WHERE projekt_id = ? AND id = ?", (pid, nr)).fetchone()
    raise kern.AmwFehler(f"M{nr} gibt es in diesem Projekt nicht"
                         + (f" – meinst du M{x['nr']} „{x['titel'][:60]}“? ({nr} ist nur die interne Nummer.)" if x else ""))


def aufloesen(con, pid, a):
    """Nach dem Öffnen der Datenbank: jede Angabe im Namespace durch die interne Nummer ersetzen. pid: Funktion (erst bei Bedarf)."""
    projekt = None
    for k, v in list(vars(a).items()):
        if isinstance(v, Angabe):
            if v.projektnummer:
                projekt = projekt or pid()
                setattr(a, k, Nummer(zu_id(con, projekt, v.zahl)))
            else:
                n = Nummer(v.zahl)
                n.nackt = True
                setattr(a, k, n)


def name(con, bid):
    """„M19“ – oder „Meilenstein 57“, wenn es ihn nicht gibt."""
    r = con.execute("SELECT nr FROM bogen WHERE id = ?", (int(bid),)).fetchone()
    return f"M{r[0]}" if r else f"Meilenstein {int(bid)}"


def nennen(con, bid, titel=False):
    """Für Ausgaben: „M19“, nach einer nackten Zahl „M19 (intern 57)“; titel: „M19 „Projektweg““."""
    r = con.execute("SELECT nr, titel FROM bogen WHERE id = ?", (int(bid),)).fetchone()
    if not r:
        return f"Meilenstein {int(bid)}"
    return f"M{r['nr']}" + (f" „{r['titel'][:60]}“" if titel else "") + (f" (intern {int(bid)})" if getattr(bid, "nackt", False) else "")


def bezug(con, pid, text):
    """Bezug von der Befehlszeile: M<Projektnummer> → gespeichertes Kürzel M<intern>; alles andere unverändert."""
    m = _M.fullmatch(str(text or ""))
    return f"M{zu_id(con, pid, int(m.group(1)))}" if m else text

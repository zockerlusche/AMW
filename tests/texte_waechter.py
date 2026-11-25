"""A2089: Textwächter – findet Texte der AMW, die einen Meilenstein mit seiner INTERNEN Nummer nennen („Meilenstein {bid}“, „M{b['id']}“,
„amw bogen freigeben {bid}“). Sichtbar ist nur die Projektnummer (meilensteine.name/nennen). Über den Syntaxbaum, damit auch mehrzeilige
und mit + oder % gebaute Texte auffallen. Kein Test (der Name beginnt nicht mit test_); benutzt von test_a2089_texte."""
import ast
import os
import re

WURZEL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Text direkt vor dem Wert: danach kommt die Nummer eines Meilensteins
VOR = re.compile(r"(?:\bMeilenstein(?:s)? |\bMeilensteine |(?:^|[^A-Za-z0-9_])M|--bogen |--meilenstein |\bamw (?:bogen [a-z-]+|spec [a-z]+|rueckblick) )$")
NAMEN = {"bid", "bogen_id", "bogen", "oid", "bogenid", "bogen_nr_intern"}
SCHLUESSEL = {"id", "bogen_id", "bogen", "bezug_id"}


def intern(n):
    """Steht hier die interne Nummer eines Meilensteins? (Name, a.id/a.bogen, x['id'], x.get('bogen'), str(…)/int(…) davon)"""
    if isinstance(n, ast.Name):
        return n.id in NAMEN
    if isinstance(n, ast.Attribute):
        return n.attr in ("bogen", "bogen_id") or (n.attr == "id" and isinstance(n.value, ast.Name) and n.value.id == "a")
    if isinstance(n, ast.Subscript) and isinstance(n.slice, ast.Constant):
        return n.slice.value in SCHLUESSEL
    if isinstance(n, ast.Call):
        if isinstance(n.func, ast.Attribute) and n.func.attr == "get" and n.args and isinstance(n.args[0], ast.Constant):
            return n.args[0].value in SCHLUESSEL
        if isinstance(n.func, ast.Name) and n.func.id in ("str", "int") and n.args:
            return intern(n.args[0])
    return False


def _text(n):
    return n.value if isinstance(n, ast.Constant) and isinstance(n.value, str) else None


def _letzter_text(n):
    """Das Ende des Textes, den dieser Ausdruck ergibt (für „…“ + str(bid))."""
    if isinstance(n, ast.BinOp) and isinstance(n.op, ast.Add):
        return _letzter_text(n.right)
    if isinstance(n, ast.JoinedStr):
        return _text(n.values[-1]) if n.values else None
    return _text(n)


def funde_in(quelle):
    """[(Zeile, Ausschnitt)] der Stellen mit interner Nummer."""
    aus = []
    for n in ast.walk(ast.parse(quelle)):
        if isinstance(n, ast.JoinedStr):
            for davor, wert in zip(n.values, n.values[1:]):
                t = _text(davor)
                if t is not None and isinstance(wert, ast.FormattedValue) and VOR.search(t) and intern(wert.value):
                    aus.append((wert.lineno, t[-40:] + "{" + ast.unparse(wert.value) + "}"))
            if n.values and isinstance(n.values[0], ast.FormattedValue):
                continue
        elif isinstance(n, ast.BinOp) and isinstance(n.op, ast.Add) and intern(n.right):
            t = _letzter_text(n.left)
            if t is not None and VOR.search(t):
                aus.append((n.lineno, t[-40:] + " + " + ast.unparse(n.right)))
        elif isinstance(n, ast.BinOp) and isinstance(n.op, ast.Mod):
            t, werte = _text(n.left), n.right.elts if isinstance(n.right, ast.Tuple) else [n.right]
            for m, w in zip(re.finditer(r"%[sd]", t or ""), werte):
                if t and VOR.search(t[:m.start()]) and intern(w):
                    aus.append((n.lineno, t[:m.end()][-40:]))
    return sorted(set(aus))


def funde(datei):
    with open(os.path.join(WURZEL, *datei.split("/")), encoding="utf-8") as f:
        return funde_in(f.read())


def zeilen(datei):
    with open(os.path.join(WURZEL, *datei.split("/")), encoding="utf-8") as f:
        return f.read().split("\n")


def dateien():
    return sorted("amw/" + x for x in os.listdir(os.path.join(WURZEL, "amw")) if x.endswith(".py"))

"""Schritt-für-Schritt-Hilfen in der Workbench – ein Baustein, gespeist aus doc/hilfe/ (→ doc/hilfe/README.md).

Je Thema eine Datei doc/hilfe/<thema>.md (Deutsch) und doc/hilfe/en/<thema>.md (Englisch) in festem Aufbau. Dieselbe
Datei ist die Anleitung im Repo – eine Quelle, Doku und Hilfe laufen nicht auseinander. Die Workbench liefert sie als
/hilfe/<thema>.<sprache>.json aus; `amw web bauen` legt dieselben Dateien für die Online-Seite nach web/hilfe/.

Aufbau einer Datei (Überschriften fest, Reihenfolge frei, alles außer Titel und Schritten darf fehlen):

    # Titel
    Ein Satz, wozu das gut ist.

    ## Du brauchst            (en: You need)
    - …
    ## Schritte               (en: Steps)
    1. **Kurztitel** Text des Schritts.
       Fortsetzung eingerückt. ![Bildbeschreibung](bildname)     ← Bild aus amw/hilfe/<bildname>.webp
    ## Diese Werte trägst du ein   (en: Values to enter)
    | Feld | Woher |
    ## Typische Fehler        (en: Common problems)
    - **Was man sieht** – was hilft
    ## Danach                 (en: Next)
    - …
    ## Häufige Fragen         (en: Questions)
    ### Frage?
    Antwort.

Im Text gelten nur **fett** und `Befehl` – die Seite setzt beides selbst als Text, nie als HTML.
"""
import os
import re

WURZEL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ORDNER = os.path.join(WURZEL, "doc", "hilfe")
SPRACHEN = ("de", "en")
ABSCHNITTE = {"du brauchst": "brauchst", "you need": "brauchst", "schritte": "schritte", "steps": "schritte",
              "diese werte trägst du ein": "werte", "values to enter": "werte", "typische fehler": "fehler",
              "common problems": "fehler", "danach": "danach", "next": "danach", "häufige fragen": "fragen", "questions": "fragen"}
NAME = re.compile(r"[a-z0-9-]{1,60}")
_BILD = re.compile(r"!\[([^\]]*)\]\(([a-z0-9-]+)\)")


class Unbekannt(LookupError):
    pass


def pfad(thema, sprache="de"):
    return os.path.join(ORDNER, f"{thema}.md") if sprache == "de" else os.path.join(ORDNER, sprache, f"{thema}.md")


def themen():
    """Namen aller Hilfen (nach den deutschen Dateien)."""
    if not os.path.isdir(ORDNER):
        return []
    return sorted(n[:-3] for n in os.listdir(ORDNER) if n.endswith(".md") and NAME.fullmatch(n[:-3]))


def lesen(thema, sprache="de"):
    """Hilfe als Daten: titel, kurz, brauchst[], schritte[{titel, text, bilder[]}], werte[[feld, woher]],
    fehler[[was, hilft]], danach[], fragen[[frage, antwort]], sprache. Fehlt die Sprache, kommt die deutsche."""
    if not NAME.fullmatch(thema or "") or sprache not in SPRACHEN:
        raise Unbekannt(thema)
    for s in (sprache, "de"):
        p = pfad(thema, s)
        if os.path.isfile(p):
            with open(p, encoding="utf-8") as f:
                d = zerlegen(f.read())
            d["thema"], d["sprache"] = thema, s
            return d
    raise Unbekannt(thema)


def _fett(text):
    """„**Titel** Rest“ → (Titel, Rest); ohne fetten Anfang ("", Text)."""
    m = re.match(r"\*\*(.+?)\*\*\s*(?:[–—:-]\s*)?(.*)$", text, re.S)
    return (m.group(1).strip(), m.group(2).strip()) if m else ("", text.strip())


def zerlegen(text):
    """Text einer Hilfe-Datei → Daten. Wirft ValueError, wenn Titel oder Schritte fehlen."""
    d = {"titel": "", "kurz": "", "brauchst": [], "schritte": [], "werte": [], "fehler": [], "danach": [], "fragen": []}
    teil, absatz = "kopf", []

    def absatz_ende():
        if not absatz:
            return
        ganz = " ".join(x.strip() for x in absatz).strip()
        absatz.clear()
        if teil == "kopf":
            d["kurz"] = (d["kurz"] + " " + ganz).strip()
        elif teil == "fragen" and d["fragen"]:
            d["fragen"][-1][1] = (d["fragen"][-1][1] + " " + ganz).strip()

    for zeile in text.replace("\r\n", "\n").split("\n"):
        roh = zeile.rstrip()
        if roh.startswith("# ") and not d["titel"]:
            d["titel"] = roh[2:].strip()
            continue
        if roh.startswith("## "):
            absatz_ende()
            teil = ABSCHNITTE.get(roh[3:].strip().lower(), "unbekannt")
            continue
        if teil == "fragen" and roh.startswith("### "):
            absatz_ende()
            d["fragen"].append([roh[4:].strip(), ""])
            continue
        if not roh.strip():
            absatz_ende()
            continue
        if teil in ("kopf", "fragen"):
            absatz.append(roh)
        elif teil in ("brauchst", "danach"):
            if roh.lstrip().startswith("- "):
                d[teil].append(roh.lstrip()[2:].strip())
            elif d[teil]:
                d[teil][-1] += " " + roh.strip()
        elif teil == "fehler":
            if roh.lstrip().startswith("- "):
                d["fehler"].append(list(_fett(roh.lstrip()[2:])))
            elif d["fehler"]:
                d["fehler"][-1][1] += " " + roh.strip()
        elif teil == "werte":
            zellen = [z.strip() for z in roh.strip().strip("|").split("|")]
            if len(zellen) >= 2 and not set("".join(zellen)) <= set("-: ") and d.get("_kopf"):
                d["werte"].append(zellen[:2])
            d["_kopf"] = True                         # erste Zeile der Tabelle ist die Kopfzeile
        elif teil == "schritte":
            m = re.match(r"\s*\d+[.)]\s+(.*)$", roh)
            if m and not roh.startswith("   "):
                titel, rest = _fett(m.group(1))
                d["schritte"].append({"titel": titel, "text": rest, "bilder": []})
            elif d["schritte"]:
                d["schritte"][-1]["text"] = (d["schritte"][-1]["text"] + " " + roh.strip()).strip()
    absatz_ende()
    d.pop("_kopf", None)
    for s in d["schritte"]:                            # Bilder aus dem Text herausnehmen
        s["bilder"] = [{"name": n, "alt": a} for a, n in _BILD.findall(s["text"])]
        s["text"] = " ".join(_BILD.sub("", s["text"]).split())
    if not d["titel"] or not d["schritte"]:
        raise ValueError("Hilfe braucht einen Titel (# …) und Schritte (## Schritte, nummeriert)")
    return d


def pruefen():
    """Für Tests und `amw web bauen`: jede Hilfe in jeder Sprache lesbar; Rückgabe {thema: [sprachen]}; wirft bei Fehlern."""
    aus = {}
    for t in themen():
        aus[t] = []
        for s in SPRACHEN:
            if os.path.isfile(pfad(t, s)):
                with open(pfad(t, s), encoding="utf-8") as f:
                    try:
                        zerlegen(f.read())
                    except ValueError as e:
                        raise ValueError(f"{pfad(t, s)}: {e}") from None
                aus[t].append(s)
    return aus

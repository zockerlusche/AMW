"""A2027 (TH164 „Konzeptänderung“): der Planer je Thema im Delta-Modus.

Ändert sich ein freigegebenes Thema, das schon geplante Pakete hat, bekommt der Planer das Ergebnis aus A2026
(konzeptaenderung.aenderung: betroffene Meilensteine und Pakete, eingeteilt in stoppen / zu_ende / fertig) und den
Unterschied zwischen der alten und der neuen freigegebenen Fassung. Er schlägt NUR die Änderung vor:

- neue Pakete (auch Nacharbeit für fertige) und neue Meilensteine – im gewohnten Schema (pakete, meilensteine),
- "aendern": ein nicht begonnenes Paket bekommt einen neuen Titel oder Auftrag,
- "verwerfen": ein nicht begonnenes Paket wird nicht mehr gebraucht,
- "nacharbeit": ein fertiges Paket muss wegen der Änderung wirklich nachgearbeitet werden (A2059) – dazu ein neues Paket.
  Fertige Pakete, die die Änderung nicht berührt, nennt der Planer nicht; die AMW führt fertige nicht pauschal als Nacharbeit.

Laufende Pakete bauen zu Ende (der Lead entscheidet), fertige ändert niemand – für sie gibt es Nacharbeit als neues Paket.
Bestehendes plant der Planer nicht neu. Das Delta legt die AMW dem Menschen als EINEN Block zur Freigabe vor; wer freigibt,
richtet sich nach feinplan_freigabe (A2032: mensch, oder Co-Entwickler und Lead je ein Ja; der Mensch jederzeit allein).

Ereignisse (plan_ereignis, ohne Schemaänderung):
  thema_delta_stimme     {"thema", "entwurf", "rolle"}            – ein Ja von Co oder Lead
  thema_delta_angewandt  {"thema", "entwurf", "geaendert": [A…], "verworfen": [A…]}
"""
import difflib
import json

from . import db, kern

STIMME, ANGEWANDT = "thema_delta_stimme", "thema_delta_angewandt"
LAENGE = {"titel": 120, "auftrag": 4000, "grund": 1000}
MAX_AENDERN = 30

AUFTRAG = (
    "DELTA-MODUS: Das Thema war schon freigegeben und geplant und hat sich geändert. Lies zuerst aenderung.md (was sich am "
    "Thema geändert hat und welche Pakete betroffen sind). Schlage NUR die Änderung vor, plane nichts Bestehendes neu: neue "
    "Pakete (auch Nacharbeit für fertige Pakete) und – nur wenn nötig – neue Meilensteine im gewohnten Schema; dazu "
    "\"aendern\": [{\"paket\": \"A123\", \"titel\": \"…\" | null, \"auftrag\": \"…\" | null, \"grund\": \"…\"}] für nicht "
    "begonnene Pakete, deren Inhalt sich ändert, und \"verwerfen\": [{\"paket\": \"A123\", \"grund\": \"…\"}] für nicht "
    "begonnene Pakete, die nicht mehr gebraucht werden. erlaubt.md sagt je Paket, was erlaubt ist: in \"aendern\" und "
    "\"verwerfen\" nur „nicht begonnen“, in \"nacharbeit\" nur „fertig“. Ein laufendes Paket nennst du in keiner der drei Listen: "
    "es wird zu Ende gebaut, die Anpassung ist ein NEUES Paket danach (nach: [\"A123\"]). Prüfe jedes fertige "
    "Paket: Muss es wegen der Änderung wirklich nachgearbeitet werden, nenne es in \"nacharbeit\": [{\"paket\": \"A123\", "
    "\"grund\": \"…\"}] und plane dafür ein neues Paket; berührt die Änderung es nicht, nennst du es nicht. Ändert die neue "
    "Fassung am Plan nichts, antworte mit nichts_zu_bauen und Grund.")


def kontext(con, pid, tid):
    """Der Delta-Kontext für ein Thema – oder None (kein Delta: nie freigegeben geändert oder nichts geplant). Rückgabe:
    konzeptaenderung.aenderung(...) plus "alt"/"neu" (Fassungsnummer und Text der vorigen und der jetzigen Freigabe)."""
    from . import konzeptaenderung, themen
    a = konzeptaenderung.aenderung(con, pid, tid)
    if a.get("art") != "geaendert" or not a.get("pakete"):
        return None
    t = themen.finden(con, pid, tid)
    s = themen.status(con, t)
    neu_nr = s.get("freigegeben") or s.get("fassung")
    frei = sorted({e.get("fassung") for e in themen._ereignisse(con, pid, tid)
                   if e["art"] in (themen.EREIGNIS["freigegeben"], themen.EREIGNIS["bearbeitet"]) and e.get("fassung")})
    alt_nr = max([n for n in frei if n < (neu_nr or 0)] or [None], key=lambda x: x or 0)

    def text(nr):
        r = con.execute("SELECT text FROM thema_fassung WHERE thema_id = ? AND nr = ?", (tid, nr)).fetchone() if nr else None
        return r["text"] if r else ""
    return {**a, "alt": {"fassung": alt_nr, "text": text(alt_nr)}, "neu": {"fassung": neu_nr, "text": text(neu_nr)}}


def datei(con, pid, delta):
    """Der Inhalt von aenderung.md für den Planer."""
    from . import konzeptaenderung
    diff = "\n".join(difflib.unified_diff(delta["alt"]["text"].splitlines(), delta["neu"]["text"].splitlines(),
                                          f"Fassung {delta['alt']['fassung']}", f"Fassung {delta['neu']['fassung']}", lineterm=""))
    zeilen = [f"# Änderung an TH{delta['thema']} {delta.get('name', '')}", "",
              f"Vorher freigegeben: Fassung {delta['alt']['fassung']} · jetzt freigegeben: Fassung {delta['neu']['fassung']}", "",
              "## Unterschied", "", "```diff", diff or "(kein Unterschied im Text)", "```", "", "## Betroffen", ""]
    zeilen += konzeptaenderung.zeilen(delta)
    zeilen += ["", "## Betroffene Pakete (nur „nicht begonnen“ darfst du ändern oder verwerfen)", ""]
    for aid, g in sorted(delta["pakete"].items()):
        a = con.execute("SELECT titel, auftrag FROM aufgabe WHERE id = ?", (aid,)).fetchone()
        zeilen.append(f"- A{aid} [{konzeptaenderung.TEXT[g]}] {a['titel'] if a else ''}")
        if a and g == "stoppen" and a["auftrag"]:
            zeilen.append(f"  Auftrag: {' '.join(a['auftrag'].split())[:800]}")
    return "\n".join(zeilen) + "\n"


DARF = {"stoppen": ("nicht begonnen", "aendern oder verwerfen"), "zu_ende": ("läuft", "in keine Liste – Anpassung als neues Paket danach"),
        "fertig": ("fertig", "nacharbeit (mit neuem Paket) – oder nicht nennen")}


def erlaubt(con, delta):
    """A2076: der Inhalt von erlaubt.md – die betroffenen Pakete je Gruppe und was der Planer damit darf."""
    z = ["# Was mit welchem Paket erlaubt ist", ""]
    for g, (name, darf) in DARF.items():
        z += [f"## {name} – {darf}", ""]
        ids = sorted(a for a, x in delta["pakete"].items() if x == g)
        for aid in ids:
            a = con.execute("SELECT titel FROM aufgabe WHERE id = ?", (aid,)).fetchone()
            z.append(f"- A{aid} {a['titel'] if a else ''}")
        z += ["(keins)" if not ids else "", ""]
    return "\n".join(z) + "\n"


def _text(x, feld, wo, f, pflicht=True):
    v = x.strip() if isinstance(x, str) else x
    if v is None or v == "":
        if pflicht:
            f.append(f"{wo}: {feld} fehlt")
        return None
    if not isinstance(v, str):
        f.append(f"{wo}: {feld} ist kein Text")
        return None
    if len(v) > LAENGE[feld]:
        f.append(f"{wo}: {feld} länger als {LAENGE[feld]} Zeichen")
    return v


def pruefen_teil(daten, delta, f):
    """Prüft "aendern" und "verwerfen" gegen die betroffenen Pakete: nur „nicht begonnen“ (stoppen); "nacharbeit" (A2059): nur
    fertige betroffene Pakete, mit Grund. Rückgabe (aendern, verwerfen, nacharbeit) bereinigt; Funde kommen in f."""
    from . import konzeptaenderung
    gruppen = {int(k): v for k, v in (delta or {}).get("pakete", {}).items()}
    aus = {"aendern": [], "verwerfen": [], "nacharbeit": []}
    gesehen, nach = set(), set()
    for art in ("aendern", "verwerfen", "nacharbeit"):
        liste = daten.get(art) or []
        if not isinstance(liste, list):
            f.append(f"{art} ist keine Liste")
            continue
        if len(liste) > MAX_AENDERN:
            f.append(f"höchstens {MAX_AENDERN} Einträge in {art}")
        for i, x in enumerate(liste, 1):
            wo = f"{art} {i}"
            if not isinstance(x, dict):
                f.append(f"{wo}: kein Objekt")
                continue
            v = str(x.get("paket") or "").strip().upper()
            if not (v[:1] == "A" and v[1:].isdigit()):
                f.append(f"{wo}: paket „{x.get('paket')}“ – Form A123")
                continue
            aid = int(v[1:])
            g = gruppen.get(aid)
            if g is None:
                f.append(f"{wo}: A{aid} ist kein betroffenes Paket dieses Themas")
            elif art == "nacharbeit":
                if g != "fertig":
                    f.append(f"{wo}: A{aid} ist {konzeptaenderung.TEXT[g]} – Nacharbeit nur für fertige Pakete")
                if aid in nach:
                    f.append(f"{wo}: A{aid} steht doppelt in nacharbeit")
                nach.add(aid)
            elif g != "stoppen":
                f.append(f"{wo}: A{aid} ist {konzeptaenderung.TEXT[g]} – ändern oder verwerfen nur nicht begonnene; für fertige ein "
                         "Nacharbeits-Paket (nacharbeit)")
            if art != "nacharbeit":
                if aid in gesehen:
                    f.append(f"{wo}: A{aid} steht doppelt in aendern/verwerfen")
                gesehen.add(aid)
            e = {"paket": aid, "grund": _text(x.get("grund"), "grund", wo, f)}
            if art == "aendern":
                e["titel"] = _text(x.get("titel"), "titel", wo, f, pflicht=False)
                e["auftrag"] = _text(x.get("auftrag"), "auftrag", wo, f, pflicht=False)
                if not (e["titel"] or e["auftrag"]):
                    f.append(f"{wo}: titel oder auftrag nötig")
            aus[art].append(e)
    return aus["aendern"], aus["verwerfen"], aus["nacharbeit"]


def kurz(delta):
    """Was das Ereignis vom Delta-Kontext behält."""
    return {"art": delta["art"], "alt": delta["alt"]["fassung"], "neu": delta["neu"]["fassung"],
            "meilensteine": [m["bogen"]["nr"] for m in delta["meilensteine"]],
            "pakete": {str(k): v for k, v in delta["pakete"].items()}}


def zeilen(entwurf):
    """Zusatzzeilen der Zusammenfassung für ein Delta."""
    d = entwurf.get("delta") or {}
    z = [f"Delta zu Fassung {d.get('neu')} (vorher {d.get('alt')}) – betrifft Meilenstein(e) "
         + (", ".join(str(n) for n in d.get("meilensteine") or []) or "–") + " · Freigabe als ein Block"]
    for e in entwurf.get("aendern") or []:
        z.append(f"  ändern A{e['paket']}: " + " · ".join(x for x in (e.get("titel") and f"Titel „{e['titel']}“",
                                                                       e.get("auftrag") and "neuer Auftrag") if x) + f" – {e['grund']}")
    for e in entwurf.get("verwerfen") or []:
        z.append(f"  verwerfen A{e['paket']} – {e['grund']}")
    for e in entwurf.get("nacharbeit") or []:                # A2059: nur, was der Planer ausdrücklich nennt
        z.append(f"  Nacharbeit nötig A{e['paket']} – {e['grund']}")
    return z


def stimme(con, pid, von, tid, eid):
    """Wer das Delta freigibt (feinplan_freigabe): der Mensch allein → None; bei co+lead Co und Lead je ein Ja zum selben
    Entwurf → None, sobald beide da sind, sonst die Liste, wessen Ja fehlt. In einer Schreib-Transaktion."""
    from . import themen
    if von == kern.ENTWICKLER:
        return None
    if themen.freigabe_regel(con, pid, "plan") != "co+lead":
        raise kern.AmwFehler("Ein Delta gibt in diesem Projekt der Mensch frei (feinplan_freigabe = mensch) – als ein Block")
    if kern.ist_co(con, pid, von):
        rolle = "co"
    elif kern.ist_lead(con, pid, von):
        rolle = "lead"
    else:
        raise kern.AmwFehler("Ein Ja zum Delta geben der Co-Entwickler und der Lead – sonst der Mensch")
    db.einfuegen(con, "plan_ereignis", projekt_id=pid, zeit_utc=db.jetzt(), von=von, art=STIMME,
                 text=json.dumps({"thema": int(tid), "entwurf": eid, "rolle": rolle}, ensure_ascii=False))
    j = {}
    for (t,) in con.execute("SELECT text FROM plan_ereignis WHERE projekt_id = ? AND art = ?", (pid, STIMME)):
        d = json.loads(t or "{}")
        if d.get("entwurf") == eid:
            j[d.get("rolle")] = True
    fehlt = [themen.ROLLEN_JA[r] for r in themen.ROLLEN_JA if not j.get(r)]
    return fehlt or None


def _noch_nicht_begonnen(con, pid, aid):
    """P593: Zwischen Entwurf und Ja vergehen oft Stunden – ein Paket kann inzwischen laufen oder fertig sein. Beim Anwenden
    wird es deshalb neu eingeteilt; nur „stoppen“ (nicht begonnen) darf geändert oder verworfen werden."""
    from . import konzeptaenderung
    a = con.execute("SELECT * FROM aufgabe WHERE id = ? AND projekt_id = ?", (aid, pid)).fetchone()
    return konzeptaenderung.einteilen(con, a) if a else None


def anwenden(con, pid, von, tid, eid, entwurf, aus=None):
    """„aendern“ und „verwerfen“ ausführen (nach dem Anlegen der neuen Pakete) – je Paket neu eingeteilt: was inzwischen läuft
    oder fertig ist, bleibt unberührt und steht unter „uebersprungen“ („A123 läuft inzwischen“). Rückgabe {"geaendert",
    "verworfen", "uebersprungen"}; der Lead bekommt eine Meldung, wenn etwas übersprungen wurde. aus (A2085): wird laufend gefüllt –
    so weiß der Aufrufer nach einem Abbruch, was schon geschehen ist."""
    from . import konzeptaenderung, planung
    anleger = von if kern.ist_lead(con, pid, von) else (kern.lead(con, pid) or kern.ENTWICKLER)
    aus = {} if aus is None else aus
    aus.update(geaendert=[], verworfen=[], uebersprungen=[])

    def frei(e):
        g = _noch_nicht_begonnen(con, pid, e["paket"])
        if g == "stoppen":
            return True
        aus["uebersprungen"].append(f"A{e['paket']} {konzeptaenderung.TEXT.get(g, 'verworfen') if g else 'gibt es nicht mehr'}"
                                    .replace("laufend – zu Ende bauen", "läuft inzwischen").replace("fertig – Planer prüft, ob betroffen",
                                                                                                    "ist inzwischen fertig"))
        return False
    for e in entwurf.get("aendern") or []:
        if not frei(e):
            continue
        werte = {k: e[k] for k in ("auftrag",) if e.get(k)}
        planung.schritt_setzen(con, pid, anleger, aid=e["paket"], titel=e.get("titel"), **werte)
        aus["geaendert"].append(f"A{e['paket']}")
    for e in entwurf.get("verwerfen") or []:
        if not frei(e):
            continue
        kern.aufgabe_status(con, pid, anleger, e["paket"], "verwerfen", beleg=f"Konzeptänderung TH{tid}: {e['grund']}"[:300],
                            automatik=True)
        aus["verworfen"].append(f"A{e['paket']}")
    if aus["uebersprungen"]:
        lead = kern.lead(con, pid)
        if lead:
            with db.schreiben(con):
                kern._posten(con, pid, "AMW", lead, "meldung", f"Delta TH{tid}: {len(aus['uebersprungen'])} Paket(e) nicht angewandt"[:140],
                             "Seit dem Entwurf haben diese Pakete begonnen oder sind fertig – sie bleiben, wie sie sind:" + chr(10)
                             + chr(10).join(f"- {x}" for x in aus["uebersprungen"]) + chr(10) + "Bei Bedarf neu planen lassen (amw thema planen).")
    with db.schreiben(con):
        db.einfuegen(con, "plan_ereignis", projekt_id=pid, zeit_utc=db.jetzt(), von=von, art=ANGEWANDT,
                     text=json.dumps({"thema": int(tid), "entwurf": eid, **aus}, ensure_ascii=False))
    return aus


def noch_offen(entwurf, stand):
    """Nach einem Abbruch: die Pakete aus „aendern“/„verwerfen“, mit denen noch nichts geschehen ist."""
    fertig = set(stand.get("geaendert") or []) | set(stand.get("verworfen") or [])
    uebersprungen = {str(x).split(" ", 1)[0] for x in stand.get("uebersprungen") or []}
    return [f"A{x['paket']}" for k in ("aendern", "verwerfen") for x in entwurf.get(k) or []
            if f"A{x['paket']}" not in fertig | uebersprungen]


def letzte(con, pid, tid):
    """Die jüngste Anwendung eines Deltas zu diesem Thema ({"geaendert", "verworfen", …}) oder {}."""
    for (t,) in con.execute("SELECT text FROM plan_ereignis WHERE projekt_id = ? AND art = ? ORDER BY id DESC", (pid, ANGEWANDT)):
        d = json.loads(t or "{}")
        if d.get("thema") == int(tid):
            return d
    return {}

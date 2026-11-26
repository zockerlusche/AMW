"""A2148 (TH157): Nachfolger eines Pakets im Bündel sind startklar – sie bauen auf dem Bündelzweig.

Bisher galt ein Vorgänger als offen, bis er fertig (live) war. Stand er gebaut und mit Prüfbitte in einem Bündel, warteten alle
Nachfolger, und freie Agenten bekamen nichts. Jetzt zählt ein Vorgänger als erfüllt, wenn seine jüngste Prüfbitte auf einem
Bündel- oder Stapelzweig liegt und nicht rot ist (im_buendel). Das gilt für Verteilen, „nächster Schritt“ und den Start von Hand.

Bündel- oder Stapelzweig: buendel-X.Y.Z (die AMW bündelt selbst), ein Zweig mit Prüfbitten zu mindestens zwei Aufgaben (ein von
Hand gestapeltes Bündel) oder ein Zweig, auf den jemand mit „stapel:<zweig>“ wartet.

Der Auftrag an den Agenten nennt den Zweig, auf dem er aufbaut, und sagt: nach dem Live-Gang auf main umsetzen. abgleichen() (in
jeder Verteil-Runde) hält die Basis nach:
- neuer Stand (neue Prüfbitte auf einem anderen Zweig/SHA): Nachricht an den Bauer, darauf umsetzen; war er angehalten, ist er frei.
- Prüfbitte rot oder Bündel rot (buendel_befund „rot“) und nach NACHFRIST_MIN kein neuer Stand: angehalten – Wartegrund
  „A<Vorgänger>“ (erledigt sich mit dem Live-Gang von selbst), Status wartet, Nachricht an den Bauer, Kopie an den Lead.
- Vorgänger fertig: Nachricht an den Bauer, jetzt auf main umsetzen.

Ereignisse (plan_ereignis, kein Schema): buendel_basis {"aufgabe", "basis": [{"vor", "pruefung", "zweig", "sha"}]} ·
buendel_basis_halt {"aufgabe", "vor", "grund"} · buendel_basis_frei {"aufgabe", "vor", "zweig", "sha"} · buendel_basis_live {"aufgabe", "vor"}
"""
import json
import time

from . import db, kern

BASIS, HALT, FREI, LIVE = "buendel_basis", "buendel_basis_halt", "buendel_basis_frei", "buendel_basis_live"
NACHFRIST_MIN = 20          # so lange darf nach einer roten Prüfbitte ein neuer Stand kommen, bevor die AMW anhält


def stapelzweig(con, pid, zweig):
    """Ist zweig ein Bündel- oder Stapelzweig?"""
    z = str(zweig or "")
    if not z:
        return False
    if z.startswith("buendel-"):
        return True
    n = con.execute("SELECT count(DISTINCT aufgabe_id) FROM pruefung WHERE projekt_id = ? AND zweig = ? AND aufgabe_id IS NOT NULL",
                    (pid, z)).fetchone()[0]
    if n >= 2:
        return True
    return bool(con.execute("SELECT 1 FROM wartegrund WHERE projekt_id = ? AND art = 'monitor' AND bezug = ?", (pid, f"stapel:{z}")).fetchone())


def _juengste(con, vor):
    """Die jüngste Prüfbitte des Vorgängers auf einem Bündel-/Stapelzweig – oder None."""
    a = con.execute("SELECT projekt_id FROM aufgabe WHERE id = ?", (vor,)).fetchone()
    if not a:
        return None
    for p in con.execute("SELECT * FROM pruefung WHERE aufgabe_id = ? ORDER BY id DESC", (vor,)):
        if stapelzweig(con, a["projekt_id"], p["zweig"]):
            return p
    return None


def _buendel_rot(con, vor, seit):
    """Hat die AMW das Bündel dieses Pakets seit `seit` rot gemeldet (buendel_befund „rot“)? Zeitpunkt oder None."""
    for e in con.execute("SELECT zeit_utc, text FROM plan_ereignis WHERE aufgabe_id = ? AND art = 'buendel_befund' AND zeit_utc >= ?"
                         " ORDER BY id DESC", (vor, seit or "")):
        try:
            if json.loads(e["text"] or "{}").get("art") == "rot":
                return e["zeit_utc"]
        except ValueError:
            continue
    return None


def im_buendel(con, vor):
    """{"vor", "pruefung", "zweig", "sha"}, wenn der Vorgänger gebaut im Bündel steht (jüngste Stapel-Prüfbitte nicht rot,
    Bündel nicht rot) – sonst None."""
    p = _juengste(con, vor)
    if not p or p["ergebnis"] == "rot" or _buendel_rot(con, vor, p["angefragt_utc"]):
        return None
    return {"vor": vor, "pruefung": p["id"], "zweig": p["zweig"], "sha": p["sha"]}


def _rot_seit(con, vor):
    """Seit wann gilt die Basis nicht mehr (rote Prüfbitte oder rotes Bündel)? UTC-Text oder None."""
    p = _juengste(con, vor)
    if not p:
        return None
    if p["ergebnis"] == "rot":
        return p["ergebnis_utc"] or p["geaendert_utc"]
    return _buendel_rot(con, vor, p["angefragt_utc"])


def offen(con, aid):
    """Offene Vorgänger (FS), ohne die, die gebaut im Bündel stehen – an Stelle von planung.offene_vorgaenger, wo es ums Starten geht."""
    from . import planung
    return [v for v in planung.offene_vorgaenger(con, aid) if not im_buendel(con, v)]


def basis(con, aid):
    """Die Vorgänger, die offen sind, aber im Bündel stehen – worauf der Nachfolger aufbaut."""
    from . import planung
    return [b for b in (im_buendel(con, v) for v in planung.offene_vorgaenger(con, aid)) if b]


def text(liste):
    """Zeile für den Auftrag – leer ohne Basis im Bündel."""
    if not liste:
        return ""
    teile = [f"A{b['vor']} (P{b['pruefung']}, {b['zweig']}@{str(b['sha'])[:8]})" for b in liste]
    vor = ", ".join(f"A{b['vor']}" for b in liste)
    return (f"Baut auf: {'; '.join(teile)} – noch nicht live. Auf diesem Zweig aufbauen; nach dem Live-Gang von {vor} auf main umsetzen."
            " Wird die Prüfbitte oder das Bündel rot, hält die AMW das Paket an und sagt es dir.")


def merken(con, pid, aid, liste, immer=False):
    """Basis merken (innerhalb eines offenen Schreibvorgangs); immer=True merkt auch eine leere (alles live)."""
    if liste or immer:
        db.einfuegen(con, "plan_ereignis", projekt_id=pid, zeit_utc=db.jetzt(), von="AMW", art=BASIS, aufgabe_id=aid,
                     text=json.dumps({"aufgabe": aid, "basis": liste}, ensure_ascii=False))


def gemerkt(con, aid):
    """{vor: {"pruefung", "zweig", "sha"}} aus dem jüngsten buendel_basis-Ereignis."""
    r = con.execute("SELECT text FROM plan_ereignis WHERE aufgabe_id = ? AND art = ? ORDER BY id DESC LIMIT 1", (aid, BASIS)).fetchone()
    if not r:
        return {}
    try:
        return {int(b["vor"]): b for b in json.loads(r["text"] or "{}").get("basis") or []}
    except (ValueError, KeyError, TypeError):
        return {}


def _halt_offen(con, aid, vor):
    """Der Wartegrund, mit dem die AMW das Paket angehalten hat – oder None."""
    return con.execute("SELECT * FROM wartegrund WHERE aufgabe_id = ? AND art = 'aufgabe' AND bezug = ? AND erledigt_utc IS NULL"
                       " AND angelegt_von = 'AMW'", (aid, f"A{vor}")).fetchone()


def _schon(con, art, aid, zeichen):
    return con.execute("SELECT 1 FROM plan_ereignis WHERE aufgabe_id = ? AND art = ? AND text LIKE ?", (aid, art, f"%{zeichen}%")).fetchone()


def abgleichen(con, pid, jetzt=None):
    """Basis der Nachfolger nachhalten: neuer Stand, rot → anhalten, live → auf main umsetzen. Rückgabe: Texte fürs Protokoll."""
    from . import planung
    jetzt = jetzt or time.time()
    lead = kern.lead(con, pid)
    aus = []
    gemerkte = {r[0] for r in con.execute("SELECT DISTINCT aufgabe_id FROM plan_ereignis WHERE projekt_id = ? AND art = ?", (pid, BASIS))}
    for a in con.execute("SELECT * FROM aufgabe WHERE projekt_id = ? AND coalesce(agent, '') != '' AND status NOT IN ('fertig', 'verworfen')",
                         (pid,)).fetchall():
        if a["id"] not in gemerkte and a["status"] != "laeuft":
            continue                                                     # nichts gemerkt, nicht gestartet: eine Abfrage weniger je Paket
        alt = gemerkt(con, a["id"]) if a["id"] in gemerkte else {}
        if not alt:
            jetzt_basis = basis(con, a["id"]) if a["status"] == "laeuft" else []
            if jetzt_basis:                                              # von Hand gestartet: merken, ohne Nachricht (er weiß, worauf er baut)
                with db.schreiben(con):
                    merken(con, pid, a["id"], jetzt_basis)
            continue
        offene = set(planung.offene_vorgaenger(con, a["id"]))
        neu_basis, aenderung = dict(alt), False
        for vor, b in alt.items():
            k = a["agent"]
            if vor not in offene:                                        # fertig (live) oder die Kante ist weg
                st = con.execute("SELECT status FROM aufgabe WHERE id = ?", (vor,)).fetchone()
                if st and st["status"] == "fertig" and not _schon(con, LIVE, a["id"], f'"vor": {vor}'):
                    with db.schreiben(con):
                        db.einfuegen(con, "plan_ereignis", projekt_id=pid, zeit_utc=db.jetzt(), von="AMW", art=LIVE, aufgabe_id=a["id"],
                                     text=json.dumps({"aufgabe": a["id"], "vor": vor}))
                        kern._posten(con, pid, "AMW", k, "auftrag", f"A{vor} ist live – A{a['id']} jetzt auf main umsetzen",
                                     f"A{a['id']} baut auf A{vor} ({b.get('zweig')}@{str(b.get('sha'))[:8]}). A{vor} ist ausgeliefert:"
                                     " deinen Zweig jetzt auf main umsetzen (rebase), bevor du die Prüfbitte stellst.", aufgabe_id=a["id"])
                    aus.append(f"A{a['id']}: Basis A{vor} live – auf main umsetzen")
                neu_basis.pop(vor, None)
                aenderung = True
                continue
            cur = im_buendel(con, vor)
            if cur:
                halt = _halt_offen(con, a["id"], vor)
                if cur["zweig"] == b.get("zweig") and cur["sha"] == b.get("sha") and not halt:
                    continue
                with db.schreiben(con):
                    if halt:
                        con.execute("UPDATE wartegrund SET erledigt_utc = ?, erledigt_durch = ? WHERE id = ?",
                                    (db.jetzt(), f"neuer Stand A{vor}: {cur['zweig']}@{str(cur['sha'])[:8]}", halt["id"]))
                        con.execute("UPDATE aufgabe SET geaendert_utc = ? WHERE id = ?", (db.jetzt(), a["id"]))
                    db.einfuegen(con, "plan_ereignis", projekt_id=pid, zeit_utc=db.jetzt(), von="AMW", art=FREI, aufgabe_id=a["id"],
                                 text=json.dumps({"aufgabe": a["id"], "vor": vor, "zweig": cur["zweig"], "sha": cur["sha"]}, ensure_ascii=False))
                    kern._posten(con, pid, "AMW", k, "auftrag",
                                 f"A{a['id']}: neue Basis A{vor} – {cur['zweig']}@{str(cur['sha'])[:8]}" + (" – weiter" if halt else ""),
                                 f"A{vor} steht jetzt auf {cur['zweig']}@{cur['sha']} (P{cur['pruefung']}), vorher {b.get('zweig')}@"
                                 f"{str(b.get('sha'))[:8]}. Deinen Zweig darauf umsetzen (rebase)."
                                 + (f" Die AMW hatte A{a['id']} angehalten – das ist aufgehoben: amw aufgabe start {a['id']}." if halt else ""),
                                 aufgabe_id=a["id"])
                neu_basis[vor] = {k2: cur[k2] for k2 in ("vor", "pruefung", "zweig", "sha")}
                aenderung = True
                aus.append(f"A{a['id']}: neue Basis A{vor} {cur['zweig']}" + (" – Halt aufgehoben" if halt else ""))
                continue
            seit = _rot_seit(con, vor)
            if _halt_offen(con, a["id"], vor) or not seit or (jetzt - db.utc_sek(seit)) / 60 < NACHFRIST_MIN:
                continue                                                 # schon angehalten · oder Zeit für einen neuen Stand
            p = _juengste(con, vor)
            grund = (f"Prüfbitte P{p['id']} rot" if p and p["ergebnis"] == "rot" else "Bündel rot") + f" ({b.get('zweig')}@{str(b.get('sha'))[:8]})"
            with db.schreiben(con):
                db.einfuegen(con, "wartegrund", projekt_id=pid, aufgabe_id=a["id"], art="aufgabe", bezug=f"A{vor}", angelegt_utc=db.jetzt(),
                             angelegt_von="AMW")
                if a["status"] == "laeuft":
                    con.execute("UPDATE aufgabe SET status = 'wartet', geaendert_utc = ? WHERE id = ?", (db.jetzt(), a["id"]))
                db.einfuegen(con, "plan_ereignis", projekt_id=pid, zeit_utc=db.jetzt(), von="AMW", art=HALT, aufgabe_id=a["id"],
                             text=json.dumps({"aufgabe": a["id"], "vor": vor, "grund": grund}, ensure_ascii=False))
                kern._posten(con, pid, "AMW", k, "auftrag", f"A{a['id']} angehalten: Basis A{vor} – {grund}",
                             f"A{a['id']} baut auf A{vor}, und dessen Stand gilt nicht mehr: {grund}. Die AMW hat A{a['id']} angehalten"
                             f" (Wartegrund A{vor}). Kommt ein neuer Stand von A{vor}, sagt die AMW dir den Zweig und hebt den Halt auf;"
                             f" mit dem Live-Gang von A{vor} erledigt er sich von selbst.", aufgabe_id=a["id"])
                if lead and lead != k:
                    kern._posten(con, pid, "AMW", lead, "meldung", f"A{a['id']} angehalten: Basis A{vor} – {grund}",
                                 f"{k} baut A{a['id']} auf A{vor}; {grund}. Wartegrund A{vor} gesetzt. Aufheben: amw aufgabe wartet"
                                 f" {a['id']} --erledigt A{vor}", aufgabe_id=a["id"])
            aus.append(f"A{a['id']} angehalten: Basis A{vor} – {grund}")
        if aenderung:
            with db.schreiben(con):
                merken(con, pid, a["id"], list(neu_basis.values()), immer=True)
    return aus

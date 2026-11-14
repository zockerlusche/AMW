"""MP4 „faststart“ (A1675): den Inhaltsverzeichnis-Block (moov) vor die Daten (mdat) stellen – wie `ffmpeg -movflags +faststart`
bzw. qt-faststart, nur Umpacken, nichts wird neu codiert. Safari/iOS braucht das Verzeichnis vorn, um ein Video ohne
Umwege zu zeigen; liegt es am Ende, muss der Browser erst das Dateiende holen.

Ablauf: oberste Blöcke lesen; liegt moov schon vor dem ersten mdat, bleibt alles, wie es ist. Sonst neue Reihenfolge
ftyp · moov · (alle übrigen Blöcke in alter Reihenfolge) und in moov jede Chunk-Adresse (stco 32 Bit, co64 64 Bit) um die
Verschiebung ihres mdat-Blocks korrigieren. Was nicht sicher geht (komprimiertes moov, Adresse passt nicht mehr in 32 Bit,
kaputte Blöcke), bleibt unverändert – lieber das alte Video als ein kaputtes.
"""
import struct

BEHAELTER = {b"moov", b"trak", b"mdia", b"minf", b"stbl", b"edts", b"dinf", b"udta", b"mvex"}


def _bloecke(roh, start=0, ende=None):
    """[(typ, anfang, kopf, ende)] der Blöcke zwischen start und ende; None, wenn die Struktur nicht stimmt."""
    ende = len(roh) if ende is None else ende
    aus, i = [], start
    while i < ende:
        if ende - i < 8:
            return None
        groesse, typ = struct.unpack(">I4s", roh[i:i + 8])
        kopf = 8
        if groesse == 1:
            if ende - i < 16:
                return None
            groesse = struct.unpack(">Q", roh[i + 8:i + 16])[0]
            kopf = 16
        elif groesse == 0:
            groesse = ende - i
        if groesse < kopf or i + groesse > ende:
            return None
        aus.append((typ, i, kopf, i + groesse))
        i += groesse
    return aus


def _adressen_korrigieren(moov, verschieben):
    """Chunk-Adressen in stco/co64 neu setzen (in einer Kopie von moov). Rückgabe: neue Bytes oder None."""
    neu = bytearray(moov)

    def gehen(start, ende):
        teile = _bloecke(neu, start, ende)
        if teile is None:
            return False
        for typ, a, kopf, e in teile:
            if typ in BEHAELTER:
                if not gehen(a + kopf, e):
                    return False
            elif typ in (b"stco", b"co64"):
                breite = 4 if typ == b"stco" else 8
                anzahl = struct.unpack(">I", neu[a + kopf + 4:a + kopf + 8])[0]
                p = a + kopf + 8
                if p + anzahl * breite > e:
                    return False
                fmt = ">I" if breite == 4 else ">Q"
                for k in range(anzahl):
                    alt = struct.unpack(fmt, neu[p + k * breite:p + (k + 1) * breite])[0]
                    wert = verschieben(alt)
                    if wert is None or (breite == 4 and wert > 0xFFFFFFFF):
                        return False
                    neu[p + k * breite:p + (k + 1) * breite] = struct.pack(fmt, wert)
        return True

    return bytes(neu) if gehen(8 if struct.unpack(">I", moov[:4])[0] != 1 else 16, len(moov)) else None


def schnellstart(roh):
    """MP4 mit moov vorn; unverändert, wenn es schon so ist oder nicht sicher umgestellt werden kann."""
    teile = _bloecke(roh)
    if not teile or teile[0][0] != b"ftyp":
        return roh
    typen = [t for t, *_ in teile]
    if typen.count(b"moov") != 1 or b"mdat" not in typen:
        return roh
    moov = next(x for x in teile if x[0] == b"moov")
    if moov[1] < next(x for x in teile if x[0] == b"mdat")[1]:
        return roh                                     # schon vorn
    moov_roh = roh[moov[1]:moov[3]]
    if b"cmov" in moov_roh[:64]:
        return roh                                     # komprimiertes Verzeichnis: nicht anfassen
    reihe = [teile[0], moov] + [x for x in teile[1:] if x is not moov]
    neue_anfaenge, pos = {}, 0
    for x in reihe:
        neue_anfaenge[x[1]] = pos
        pos += x[3] - x[1]
    alte = [x for x in teile if x is not moov]

    def verschieben(adresse):
        for _, a, _, e in alte:
            if a <= adresse < e:
                return adresse - a + neue_anfaenge[a]
        return None                                    # zeigt nirgendwohin: lieber nichts ändern

    neues_moov = _adressen_korrigieren(moov_roh, verschieben)
    if neues_moov is None:
        return roh
    return b"".join(neues_moov if x is moov else roh[x[1]:x[3]] for x in reihe)


def moov_vorn(roh):
    """Liegt das Inhaltsverzeichnis vor den Daten? (für Tests und Prüfungen)"""
    teile = _bloecke(roh) or []
    lage = {t: a for t, a, *_ in reversed(teile)}
    return b"moov" in lage and b"mdat" in lage and lage[b"moov"] < lage[b"mdat"]

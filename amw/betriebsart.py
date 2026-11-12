"""Betriebsart dieser Installation – die eine Stelle, die jeder Weg nach außen fragt.

    pc      nur dieser PC: die AMW baut keine Verbindung über den eigenen Rechner hinaus auf
    server  eigener Server im Firmennetz: Verbindungen nur zu Adressen im eigenen Netz
    cloud   Online-Speicher und Dienste im Internet sind erlaubt

Entschieden wird nach der Adresse des Ziels (dieser PC · Firmennetz · Internet), nicht nach dem Namen eines Dienstes –
ein eigener ntfy-Server im Firmennetz ist in „server“ erlaubt, ein Dienst im Internet nicht. Wer nichts gewählt hat,
bekommt, was bisher lief: mit eingeschaltetem Abgleich oder Benachrichtigungen „cloud“, sonst „pc“.

Nicht erfasst ist, was außerhalb der AMW läuft: Claude Code selbst spricht mit seinem Anbieter, Git mit seinem Server.
"""
import ipaddress
import json
import socket
import urllib.parse

from . import einstellungen

ARTEN = ("pc", "server", "cloud")
NAMEN = {"pc": "Nur dieser PC", "server": "Eigener Server im Firmennetz", "cloud": "Cloud"}
STUFEN = ("pc", "firma", "internet")               # wohin eine Adresse führt
ERLAUBT = {"pc": ("pc",), "server": ("pc", "firma"), "cloud": STUFEN}
INTERN = (".local", ".lan", ".intern", ".internal", ".corp", ".home.arpa")   # Namen, die es nur im eigenen Netz gibt


class Gesperrt(OSError):
    """Die gewählte Betriebsart lässt diese Verbindung nicht zu."""


def gewaehlt():
    """Die ausdrücklich gewählte Betriebsart oder '' (nichts gewählt)."""
    return einstellungen.wert("betriebsart")


def aktuell():
    art = gewaehlt()
    if art:
        return art
    from . import abgleich, push                   # nichts gewählt: was heute läuft
    try:
        with open(abgleich.zugang_pfad(), encoding="utf-8") as f:
            z = json.load(f)
        if z.get("abgleich") and (z.get("url") or z.get("sqlite")):
            return "cloud"
    except (OSError, ValueError):
        pass
    try:
        if push.laden().get("an"):
            return "cloud"
    except Exception:
        pass
    return "pc"


def host(adresse):
    a = str(adresse or "").strip()
    try:
        return (urllib.parse.urlsplit(a if "://" in a else "//" + a).hostname or "").lower()
    except ValueError:
        return ""


def _stufe_ip(ip):
    if ip.is_loopback:
        return "pc"
    return "firma" if ip.is_private or ip.is_link_local else "internet"


_namen = {}                                        # Namensauflösung merken (je Lauf)


def _aufloesen(name):
    if name not in _namen:
        try:
            _namen[name] = sorted({i[4][0] for i in socket.getaddrinfo(name, None)})
        except OSError:
            _namen[name] = []
    return _namen[name]


def netz(adresse, aufloesen=_aufloesen):
    """Wohin führt die Adresse: 'pc' (dieser Rechner), 'firma' (eigenes Netz) oder 'internet'? Im Zweifel 'internet'.
    aufloesen=None fragt keinen Namensdienst – ein Name mit Punkt gilt dann als Internet."""
    h = host(adresse)
    if not h:
        return "internet"
    if h == "localhost" or h.endswith(".localhost"):
        return "pc"
    try:
        return _stufe_ip(ipaddress.ip_address(h))
    except ValueError:
        pass
    if "." not in h or h.endswith(INTERN):
        return "firma"
    if aufloesen is None:
        return "internet"
    stufen = set()
    for ip in aufloesen(h):
        try:
            stufen.add(_stufe_ip(ipaddress.ip_address(ip.split("%")[0])))
        except ValueError:
            return "internet"
    if not stufen or "internet" in stufen:         # nicht auflösbar oder (auch) öffentlich
        return "internet"
    return "firma" if "firma" in stufen else "pc"


def http_im_netz(adresse):
    """http:// (unverschlüsselt) ist nur erlaubt, wenn das Ziel im Firmennetz oder auf diesem PC liegt – sonst gingen
    Schlüssel und Inhalte lesbar durchs Internet."""
    return str(adresse or "").strip().lower().startswith("http://") and netz(adresse) != "internet"


def erlaubt(adresse, art=None):
    art = art or aktuell()
    if art == "cloud":
        return True
    # in „pc“ wird kein Namensdienst gefragt: was nicht erkennbar dieser Rechner ist, bleibt gesperrt
    return netz(adresse, None if art == "pc" else _aufloesen) in ERLAUBT[art]


def pruefe(adresse, zweck):
    """Wirft Gesperrt, wenn die Betriebsart die Verbindung nicht zulässt. Der Text nennt nur den Rechnernamen des Ziels –
    nie die ganze Adresse (sie kann einen Schlüssel enthalten)."""
    art = aktuell()
    if not erlaubt(adresse, art):
        raise Gesperrt(f"Betriebsart „{NAMEN[art]}“: {zweck} zu {host(adresse) or 'unbekannt'} ist blockiert"
                       f" (ändern unter Einstellungen › Betriebsart)")

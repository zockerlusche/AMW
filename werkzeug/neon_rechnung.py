# Neon-Kosten aus echten Schreibzahlen der bus.db (nur lesend), 14 Tage 18.10.–31.10.2026 UTC
import sqlite3, collections
from datetime import datetime, timedelta, timezone
c = sqlite3.connect('file:F:/agent-bus/projekt-netly/bus.db?mode=ro', uri=True)
VON, BIS = '2026-10-18', '2026-11-01'
quellen = {
 'nachricht': "select zeit_utc from nachricht where zeit_utc>=? and zeit_utc<?",
 'empfang(erledigt)': "select erledigt_utc from empfang where erledigt_utc>=? and erledigt_utc<?",
 'marcel_wort': "select zeit_utc from marcel_wort where zeit_utc>=? and zeit_utc<?",
 'beschluss': "select angelegt_utc from beschluss where angelegt_utc>=? and angelegt_utc<?",
 'aufgabe(neu)': "select angelegt_utc from aufgabe where angelegt_utc>=? and angelegt_utc<?",
 'aufgabe(begonnen)': "select begonnen_utc from aufgabe where begonnen_utc>=? and begonnen_utc<?",
 'aufgabe(fertig)': "select fertig_utc from aufgabe where fertig_utc>=? and fertig_utc<?",
 'frage_marcel': "select zeit_utc from frage_marcel where zeit_utc>=? and zeit_utc<?",
}
def t(s):
    s = s.replace('Z', '').replace('T', ' ')[:19]
    return datetime.strptime(s, '%Y-%m-%d %H:%M:%S')
zeiten, je = [], {}
for n, q in quellen.items():
    try:
        z = [t(r[0]) for r in c.execute(q, (VON, BIS)) if r[0]]
    except Exception as e:
        print('FEHLER', n, e); z = []
    je[n] = len(z); zeiten += z
empf = c.execute("select count(*) from empfang e join nachricht n on n.id=e.nachricht_id where n.zeit_utc>=? and n.zeit_utc<?", (VON, BIS)).fetchone()[0]
tage = 14
print('Schreibvorgänge 14 Tage:', je, '+ empfang(neu)', empf)
gesamt = len(zeiten) + empf
print(f'gesamt {gesamt} = {gesamt/tage:.0f}/Tag; dazu Puls 6 Wachen x 2880/Tag (nur lokal)')
start = t(VON + ' 00:00:00')
def wach_minuten(takt_min, ruhe_min=5, sync_s=10):
    # Abgleich alle takt_min Minuten, aber nur wenn seit dem letzten Abgleich etwas geschrieben wurde.
    slots = sorted({int((z - start).total_seconds() // (takt_min * 60)) for z in zeiten})
    wach, ende_vorher = 0.0, None
    for s in slots:
        a = (s + 1) * takt_min * 60          # Abgleich am Ende des Fensters
        e = a + sync_s + ruhe_min * 60       # wach bis 5 min nach dem Abgleich
        if ende_vorher is not None and a < ende_vorher:
            wach += e - ende_vorher
        else:
            wach += e - a
        ende_vorher = e
    return wach / 60, len(slots)
for takt in (1, 5, 15, 30, 60):
    m, n = wach_minuten(takt)
    cuh_monat = m / 60 / tage * 30 * 0.25
    kosten = max(0, cuh_monat - 0) * 0.106
    print(f'Takt {takt:>2} min: {n:>4} Abgleiche/14 T, wach {m/60/tage:5.1f} h/Tag -> {cuh_monat:6.1f} CU-h/Monat (0,25 CU) '
          f'| Free {"ja" if cuh_monat <= 100 else "nein"} | Launch {kosten:5.2f} $ + Speicher')
# Speicher
print('bus.db MB', round(__import__('os').path.getsize('F:/agent-bus/projekt-netly/bus.db')/1e6,1))

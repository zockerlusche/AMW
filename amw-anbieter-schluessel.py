"""apiKeyHelper der Arbeiter mit freigegebenem Anbieter (A1931): gibt eine Schlüsseldatei nur aus, wenn ihr Pfad freigegeben ist.

    python -I -X utf8 amw-anbieter-schluessel.py <Pfad der Schlüsseldatei>

Der Bindestrich im Namen ist Absicht: die Datei ist nicht importierbar und verdeckt das Paket `amw` nicht.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from amw import anbieter_schluessel  # noqa: E402

sys.exit(anbieter_schluessel.main(sys.argv[1:]))

"""unittest discover -s tests lädt das Paket nicht – deshalb auch hier (wird vor dem ersten Test geladen). → tests/__init__.py"""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import os

os.environ.pop("AMW_PROJEKT", None)
os.environ.pop("AMW_AGENT", None)

"""Tests laufen nie in der Umgebung einer Agenten-Sitzung: AMW_PROJEKT und AMW_AGENT aus dem Startbefehl würden sonst gelten."""
import os

os.environ.pop("AMW_PROJEKT", None)
os.environ.pop("AMW_AGENT", None)

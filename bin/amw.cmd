@echo off
rem AMW in cmd und PowerShell: Ordner bin in den PATH nehmen, dann z. B. amw lesen --von CC1
python -X utf8 "%~dp0..\amw-cli.py" %*

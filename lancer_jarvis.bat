@echo off
title Lowkey
rem Lanceur de l'assistant vocal. Se place dans le dossier du projet puis
rem demarre jarvis14.py via uv. Chemin absolu vers uv pour fonctionner
rem aussi au demarrage de Windows, ou le PATH peut differer.
cd /d "%~dp0"
git pull --ff-only 2>nul
rem Prechauffe Chatterbox en arriere-plan. Le provider attendra sa disponibilite
rem si une reponse vocale arrive avant la fin du chargement du modele.
if exist "..\chatterbox-lowkey\python_embedded\python.exe" (
  powershell -NoProfile -WindowStyle Hidden -Command "if (-not (Get-NetTCPConnection -LocalPort 8004 -State Listen -ErrorAction SilentlyContinue)) { Start-Process -WindowStyle Hidden -FilePath '..\chatterbox-lowkey\python_embedded\python.exe' -ArgumentList 'server.py' -WorkingDirectory '..\chatterbox-lowkey' }"
)
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" jarvis14.py
) else (
  "%USERPROFILE%\.local\bin\uv.exe" run python jarvis14.py
)
echo.
echo Lowkey s'est arrete. Vous pouvez fermer cette fenetre.
pause

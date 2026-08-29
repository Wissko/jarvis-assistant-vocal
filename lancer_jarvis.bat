@echo off
title Lowkey
rem Lanceur de l'assistant vocal. Se place dans le dossier du projet puis
rem demarre jarvis14.py via uv. Chemin absolu vers uv pour fonctionner
rem aussi au demarrage de Windows, ou le PATH peut differer.
cd /d "%~dp0"
rem Si Lowkey tourne deja, ne lance pas une seconde instance : ouvre son interface.
powershell -NoProfile -Command "if (Get-NetTCPConnection -LocalPort 8790 -State Listen -ErrorAction SilentlyContinue) { Start-Process 'http://localhost:8790/cockpit'; exit 42 }"
if %errorlevel% equ 42 exit /b 0
git pull --ff-only 2>nul
rem Precharge XTTS v2 en arriere-plan. Chatterbox reste le repli automatique.
if exist "..\xtts-lowkey\.venv\Scripts\python.exe" (
  powershell -NoProfile -WindowStyle Hidden -Command "$env:COQUI_TOS_AGREED='1'; $py=(Resolve-Path '..\xtts-lowkey\.venv\Scripts\python.exe').Path; $script=(Resolve-Path 'services\xtts_server.py').Path; $cwd=(Get-Location).Path; if (-not (Get-NetTCPConnection -LocalPort 8020 -State Listen -ErrorAction SilentlyContinue)) { Start-Process -WindowStyle Hidden -FilePath $py -ArgumentList $script -WorkingDirectory $cwd }; $fin=(Get-Date).AddSeconds(180); while((Get-Date) -lt $fin){ try { $r=Invoke-RestMethod 'http://127.0.0.1:8020/health' -TimeoutSec 2; if($r.loaded){exit 0} } catch {}; Start-Sleep -Seconds 1 }; exit 1"
)
if exist ".venv\Scripts\python.exe" (
  start "" /b ".venv\Scripts\python.exe" -m core.prechauffer_tts >nul 2>&1
  ".venv\Scripts\python.exe" jarvis14.py
) else (
  "%USERPROFILE%\.local\bin\uv.exe" run python jarvis14.py
)
echo.
echo Lowkey s'est arrete. Vous pouvez fermer cette fenetre.
pause

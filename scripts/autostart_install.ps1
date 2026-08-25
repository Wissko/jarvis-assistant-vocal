# Installe le démarrage automatique de Jarvis à l'ouverture de session Windows.
# Crée une tâche planifiée « JarvisAutostart » qui lance demarrer_jarvis_complet.ps1
# 30 s après le login (le temps que le réseau/Docker montent). RunLevel utilisateur
# (pas admin) pour garder l'accès au micro/haut-parleurs.
#
# Usage :  powershell -ExecutionPolicy Bypass -File scripts\autostart_install.ps1
# Retrait : scripts\autostart_uninstall.ps1

$script = Join-Path $PSScriptRoot "demarrer_jarvis_complet.ps1"
$nom = "JarvisAutostart"

if (-not (Test-Path $script)) { Write-Host "Introuvable : $script" -ForegroundColor Red; exit 1 }

$action = New-ScheduledTaskAction -Execute "powershell.exe" `
  -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$script`""
$trigger = New-ScheduledTaskTrigger -AtLogOn
$trigger.Delay = "PT30S"                       # 30 s de délai réseau
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries `
  -DontStopIfGoingOnBatteries -StartWhenAvailable -ExecutionTimeLimit ([TimeSpan]::Zero)

Register-ScheduledTask -TaskName $nom -Action $action -Trigger $trigger `
  -Settings $settings -Description "Démarre la chaîne Hermes + le Jarvis vocal à l'ouverture de session." `
  -Force -RunLevel Limited | Out-Null

Write-Host "OK : tâche « $nom » installée." -ForegroundColor Green
Write-Host "Jarvis démarrera automatiquement 30 s après chaque ouverture de session."
Write-Host "Pour tester tout de suite sans redémarrer : Start-ScheduledTask -TaskName $nom"
Write-Host "Pour retirer : scripts\autostart_uninstall.ps1"

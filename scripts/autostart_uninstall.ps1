# Désinstalle le démarrage automatique de Jarvis (tâche « JarvisAutostart »).
# Usage : powershell -ExecutionPolicy Bypass -File scripts\autostart_uninstall.ps1
$nom = "JarvisAutostart"
if (Get-ScheduledTask -TaskName $nom -ErrorAction SilentlyContinue) {
  Unregister-ScheduledTask -TaskName $nom -Confirm:$false
  Write-Host "OK : tâche « $nom » supprimée. Jarvis ne démarrera plus automatiquement." -ForegroundColor Green
} else {
  Write-Host "La tâche « $nom » n'existe pas (rien à faire)."
}

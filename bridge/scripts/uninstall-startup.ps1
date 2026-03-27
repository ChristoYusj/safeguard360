$ErrorActionPreference = "Stop"

$taskName = "SafeGuard360 Telegram Codex Bridge"

if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
  Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
  Write-Host "Removed startup task: $taskName"
} else {
  Write-Host "Startup task not found: $taskName"
}

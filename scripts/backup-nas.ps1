#Requires -Version 5.1
<#
.SYNOPSIS
    Backup completo del repo HIRIS verso NAS QNAP.

.DESCRIPTION
    Crea un git bundle (singolo file che contiene tutta la storia + tag)
    e lo salva sul NAS. Mantiene gli ultimi 4 backup settimanali + sempre
    una copia "latest" aggiornata.

.SETUP
    Schedulare con Windows Task Scheduler (eseguire una volta manualmente
    per verificare che funzioni):
      1. Apri Task Scheduler → Create Basic Task
      2. Nome: "HIRIS Git Backup"
      3. Trigger: Weekly, domenica alle 03:00
      4. Action: Start a program
         Program:  powershell.exe
         Arguments: -NonInteractive -ExecutionPolicy Bypass -File "C:\Work\Sviluppo\hiris\scripts\backup-nas.ps1"
      5. Spunta "Run whether user is logged on or not"

.NOTES
    Il NAS deve essere raggiungibile (LAN attiva) al momento dell'esecuzione.
    Se il NAS non è online lo script esce silenziosamente senza errori.
#>

$REPO      = "C:\Work\Sviluppo\hiris"
$NAS_PATH  = "\\192.168.1.131\Backup\hiris-backups"
$KEEP      = 4   # quanti backup datati tenere (oltre a latest)

# ---------------------------------------------------------------------------

$ErrorActionPreference = "Stop"
$date    = Get-Date -Format "yyyy-MM-dd"
$logLine = "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')]"

# Verifica NAS raggiungibile
if (-not (Test-Path $NAS_PATH)) {
    Write-Host "$logLine NAS non raggiungibile ($NAS_PATH) — backup saltato."
    exit 0
}

# Assicura che la cartella di destinazione esista
New-Item -ItemType Directory -Path $NAS_PATH -Force | Out-Null

$bundleDated  = Join-Path $NAS_PATH "hiris-$date.bundle"
$bundleLatest = Join-Path $NAS_PATH "hiris-latest.bundle"

# Crea bundle git (include tutti i branch + tag)
Write-Host "$logLine Creazione bundle git..."
$result = & git -C $REPO bundle create $bundleDated --all 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "$logLine ERRORE bundle: $result"
    exit 1
}

# Verifica integrità bundle
$verify = & git -C $REPO bundle verify $bundleDated 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "$logLine ERRORE verifica bundle: $verify"
    Remove-Item $bundleDated -Force -ErrorAction SilentlyContinue
    exit 1
}

# Aggiorna latest
Copy-Item $bundleDated $bundleLatest -Force
$size = [math]::Round((Get-Item $bundleLatest).Length / 1MB, 2)
Write-Host "$logLine Bundle creato: $bundleDated ($size MB)"

# Rimuovi vecchi backup (tieni solo $KEEP)
Get-ChildItem (Join-Path $NAS_PATH "hiris-20*.bundle") |
    Sort-Object LastWriteTime -Descending |
    Select-Object -Skip $KEEP |
    ForEach-Object {
        Write-Host "$logLine Rimosso vecchio backup: $($_.Name)"
        Remove-Item $_.FullName -Force
    }

Write-Host "$logLine Backup completato."

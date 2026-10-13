# Arranca la demo: backend (API) y frontend en dos ventanas y abre el navegador.
# Solo ASCII a proposito (ver nota en setup-frontend.ps1).
#
# IMPORTANTE: las contrasenas de los usuarios de la demo se generan al azar en cada arranque y
# se muestran UNA sola vez en la ventana del backend. Anotelas ahi.

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
$backend = Join-Path $repo "APP\Backend"
$frontend = Join-Path $repo "APP\Frontend"
$node = Join-Path $env:LOCALAPPDATA "fleetplanner-tools\node"

if (-not (Test-Path (Join-Path $backend ".venv\Scripts\python.exe"))) {
    throw "Falta el entorno de Python. Ver README.md (seccion 'Puesta en marcha')."
}
if (-not (Test-Path (Join-Path $node "node.exe")) -or -not (Test-Path (Join-Path $frontend "node_modules"))) {
    throw "Falta Node o node_modules. Ejecute primero: scripts\setup-frontend.ps1"
}

$backendCmd = "`$host.UI.RawUI.WindowTitle='Backend - API'; Set-Location '$backend'; .\.venv\Scripts\python.exe -m fleetplanner.bootstrap serve"
$frontendCmd = "`$host.UI.RawUI.WindowTitle='Frontend - Vite'; `$env:Path='$node;'+`$env:Path; Set-Location '$frontend'; npm run dev"

Start-Process powershell -ArgumentList "-NoExit", "-Command", $backendCmd
Start-Sleep -Seconds 4
Start-Process powershell -ArgumentList "-NoExit", "-Command", $frontendCmd
Start-Sleep -Seconds 6
Start-Process "http://localhost:5173"
Write-Output "Demo en http://localhost:5173 (API en http://127.0.0.1:8000). Cierre las dos ventanas para detenerla."

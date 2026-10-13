# Prepara las herramientas del frontend (Node local + node_modules fuera de OneDrive).
# Es idempotente. Escrito solo con ASCII a proposito: Windows PowerShell 5.1 lee los .ps1 sin BOM
# como ANSI y estropearia los acentos.
#
# Que hace:
#   1. Descarga Node LTS (zip portable) a %LOCALAPPDATA%\fleetplanner-tools\node si no existe,
#      verificando su SHA-256 contra SHASUMS256.txt de nodejs.org.
#   2. Crea una union (junction) APP\Frontend\node_modules -> %LOCALAPPDATA%\fleetplanner-tools\
#      frontend_node_modules, para que OneDrive no sincronice miles de archivos.
#   3. Ejecuta `npm install` (usa package-lock.json).
#
# No modifica el PATH global ni requiere administrador.

$ErrorActionPreference = "Stop"
$NodeVersion = "v24.21.0"

$repo = Split-Path -Parent $PSScriptRoot
$tools = Join-Path $env:LOCALAPPDATA "fleetplanner-tools"
$nodeDir = Join-Path $tools "node"
$frontend = Join-Path $repo "APP\Frontend"

if (-not (Test-Path (Join-Path $nodeDir "node.exe"))) {
    $dl = Join-Path $tools "download"
    if (Test-Path $dl) { Remove-Item $dl -Recurse -Force }
    New-Item -ItemType Directory -Force $dl | Out-Null
    $zipName = "node-$NodeVersion-win-x64.zip"
    Invoke-WebRequest "https://nodejs.org/dist/$NodeVersion/$zipName" -OutFile (Join-Path $dl $zipName) -UseBasicParsing
    Invoke-WebRequest "https://nodejs.org/dist/$NodeVersion/SHASUMS256.txt" -OutFile (Join-Path $dl "SHASUMS256.txt") -UseBasicParsing
    $line = Get-Content (Join-Path $dl "SHASUMS256.txt") | Where-Object { $_ -match [regex]::Escape($zipName) + '$' }
    $expected = ($line -replace '\s.*', '').ToLower()
    $actual = (Get-FileHash (Join-Path $dl $zipName) -Algorithm SHA256).Hash.ToLower()
    if (-not $expected -or $expected -ne $actual) { throw "El hash de Node no coincide: no se extrae." }
    Expand-Archive (Join-Path $dl $zipName) -DestinationPath $tools -Force
    Rename-Item (Join-Path $tools "node-$NodeVersion-win-x64") $nodeDir
    Write-Output "Node $NodeVersion instalado y verificado en $nodeDir"
} else {
    Write-Output "Node ya instalado: $(& (Join-Path $nodeDir 'node.exe') --version)"
}

$env:Path = "$nodeDir;$env:Path"
$modules = Join-Path $frontend "node_modules"
$target = Join-Path $tools "frontend_node_modules"
New-Item -ItemType Directory -Force $target | Out-Null
if (-not (Test-Path $modules)) {
    New-Item -ItemType Junction -Path $modules -Target $target | Out-Null
}

Set-Location $frontend
npm install
Write-Output "Frontend listo. Siguiente paso: scripts\start-demo.ps1"

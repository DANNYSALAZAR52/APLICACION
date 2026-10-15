# Arranca la demo en UN solo proceso (API + interfaz compilada) lista para compartirla por un tunel.
# Solo ASCII a proposito (ver nota en setup-frontend.ps1).
#
# Uso (en una ventana de PowerShell, desde la raiz del repositorio):
#   powershell -ExecutionPolicy Bypass -File scripts\share-demo.ps1
# Pide dos contrasenas (no se muestran ni se guardan). Luego, en OTRA ventana, abra un tunel
# HTTPS hacia http://127.0.0.1:8000 con la herramienta que prefiera, por ejemplo:
#   cloudflared tunnel --url http://127.0.0.1:8000
# y comparta la direccion https que imprime. El PC debe seguir encendido mientras se muestre.
#
# Las contrasenas viven solo en las variables de entorno de ESTE proceso.

param(
    [int]$Port = 8000
)

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
$backend = Join-Path $repo "APP\Backend"
$frontend = Join-Path $repo "APP\Frontend"
$node = Join-Path $env:LOCALAPPDATA "fleetplanner-tools\node"
$python = Join-Path $backend ".venv\Scripts\python.exe"

if (-not (Test-Path $python)) { throw "Falta el entorno de Python. Ver README.md." }
if (-not (Test-Path (Join-Path $node "node.exe"))) { throw "Falta Node. Ejecute scripts\setup-frontend.ps1" }

function Read-Secret([string]$prompt) {
    $secure = Read-Host -AsSecureString $prompt
    $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    try { return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr) }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr) }
}

$demo = Read-Secret "Contrasena de los usuarios de la demo (min. 12 caracteres)"
$super = Read-Secret "Contrasena del superadministrador (min. 12, distinta)"
if ($demo.Length -lt 12 -or $super.Length -lt 12) { throw "Las contrasenas deben tener al menos 12 caracteres." }
if ($demo -eq $super) { throw "Las dos contrasenas deben ser distintas." }

Write-Output "Compilando la interfaz..."
$env:Path = "$node;$env:Path"
Push-Location $frontend
try { npm run build | Out-Null; if ($LASTEXITCODE -ne 0) { throw "Fallo la compilacion del frontend." } }
finally { Pop-Location }

# Clave de firma efimera de esta sesion (las sesiones caducan al detener el servidor).
$bytes = New-Object byte[] 48
[Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
$env:JWT_SIGNING_KEY = [Convert]::ToBase64String($bytes)
$env:FLEETPLANNER_ENV = "production"   # cookie Secure, documentacion apagada, HSTS (el tunel da HTTPS)
$env:FRONTEND_DIST = Join-Path $frontend "dist"
$env:DEMO_PASSWORD = $demo
$env:DEMO_SUPERADMIN_PASSWORD = $super
$env:HOST = "127.0.0.1"
$env:PORT = "$Port"

Write-Output "Demo en http://127.0.0.1:$Port . Abra el tunel en otra ventana y comparta su direccion https."
Set-Location $backend
& $python -m fleetplanner.bootstrap serve

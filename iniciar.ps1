param(
    [ValidateRange(1024, 65535)] [int] $Port = 8000,
    [switch] $Install
)
$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
    $pythonExe = Join-Path $PSScriptRoot '.venv/Scripts/python.exe'
    if (-not (Test-Path -LiteralPath $pythonExe)) {
        & py -3.12 -m venv .venv
        if ($LASTEXITCODE -ne 0) { throw 'Se requiere Python 3.12 (py -3.12).' }
        $Install = $true
    }
    if ($Install) {
        & $pythonExe -m ensurepip --upgrade
        if ($LASTEXITCODE -ne 0) { throw 'No se pudo preparar pip en el entorno virtual.' }
        & $pythonExe -m pip install -r requirements.txt
        if ($LASTEXITCODE -ne 0) { throw 'No se pudieron instalar las dependencias.' }
    }
    Write-Host "App: http://127.0.0.1:$Port - Ctrl+C para detener."
    & $pythonExe -m shiny run --host 127.0.0.1 --port $Port app.py
    if ($LASTEXITCODE -ne 0) { throw 'La app termino con un error.' }
}
finally { Pop-Location }

$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$projectPython = Join-Path $PSScriptRoot '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $projectPython)) {
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Could not create virtual environment' }
}
& $projectPython -m pip install -r requirements-dev.txt
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed' }
& $projectPython -m flask --app wsgi db upgrade
if ($LASTEXITCODE -ne 0) { throw 'Database migration failed' }
& $projectPython -m flask --app wsgi seed
if ($LASTEXITCODE -ne 0) { throw 'Demo data setup failed' }
& $projectPython -m flask --app wsgi run --host 127.0.0.1 --port 8000

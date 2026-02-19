Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
  Write-Error "python bulunamadı. Python 3 kur ve tekrar dene."
  exit 1
}

if (-not (Test-Path ".venv")) {
  python -m venv .venv
}

try {
  .\.venv\Scripts\Activate.ps1
} catch {
  # Bazı sistemlerde policy engeli çıkabilir
  Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
  .\.venv\Scripts\Activate.ps1
}

python -m pip install --upgrade pip
pip install -r requirements.txt

Write-Host "`nStarting Streamlit... (Ctrl+C ile durdur)"
python -m streamlit run app.py

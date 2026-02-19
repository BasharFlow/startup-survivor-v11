#!/usr/bin/env bash
set -euo pipefail

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 bulunamadı. Python 3 kur ve tekrar dene." >&2
  exit 1
fi

if [ ! -d ".venv" ]; then
  python3 -m venv .venv
fi

source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt

echo "\nStarting Streamlit... (Ctrl+C ile durdur)"
python -m streamlit run app.py

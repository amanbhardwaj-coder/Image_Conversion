#!/bin/bash
set -e
cd "$(dirname "$0")"
if ! python3 -c "import streamlit, PIL" >/dev/null 2>&1; then
  echo "Installing required packages..."
  python3 -m pip install -r requirements.txt
fi
echo ""
echo "Starting Local Image Optimizer..."
echo "Your browser should open automatically."
echo "Press Control+C in this Terminal window to stop the app."
echo ""
python3 -m streamlit run app.py

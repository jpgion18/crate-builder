#!/bin/bash
# Double-click this file in Finder to start Crate Builder without using Terminal manually.
cd "$(dirname "$0")"

if [ ! -d ".venv" ]; then
  echo "First-time setup hasn't been done yet."
  echo "Open this folder in Terminal and follow the Setup steps in README.md, then try again."
  echo
  read -p "Press Enter to close this window..."
  exit 1
fi

source .venv/bin/activate
(sleep 2 && open http://127.0.0.1:5001) &
python3 app.py

echo
echo "Server stopped. Press Enter to close this window."
read

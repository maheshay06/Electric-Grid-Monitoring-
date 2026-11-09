#!/usr/bin/env bash
# First-time setup for macOS / Linux. Run:  bash scripts/setup.sh
# Safe to re-run: it never overwrites an existing backend/.env or database.
set -euo pipefail
cd "$(dirname "$0")/.."

command -v node >/dev/null || { echo "Node.js 20+ is required: https://nodejs.org"; exit 1; }

PY=""
for c in python3.12 python3.11 python3.13 python3.10 python3 python; do
  if command -v "$c" >/dev/null && "$c" -c 'import sys; sys.exit(0 if (3,10)<=sys.version_info[:2]<=(3,13) else 1)'; then PY="$c"; break; fi
done
[ -n "$PY" ] || { echo "Python 3.10 to 3.13 is required."; exit 1; }
echo "Using Python: $PY"

[ -x .venv/bin/python ] || "$PY" -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r backend/requirements.txt

if [ ! -f backend/.env ]; then
  SECRET=$(.venv/bin/python -c "import secrets; print(secrets.token_urlsafe(48))")
  sed "s|^JWT_SECRET=.*|JWT_SECRET=$SECRET|" backend/.env.example > backend/.env
  echo "Created backend/.env with a new random JWT_SECRET."
  read -r -p "Choose an admin operator ID (3+ chars): " ID
  read -r -s -p "Choose an admin password (10+ chars, letter + digit, must not contain the ID): " PW; echo
  sed -i.bak "s|^SEED_ADMIN_OPERATOR_ID=.*|SEED_ADMIN_OPERATOR_ID=$ID|; s|^SEED_ADMIN_PASSWORD=.*|SEED_ADMIN_PASSWORD=$PW|" backend/.env
  rm -f backend/.env.bak
else
  echo "backend/.env already exists - left untouched."
fi

(cd backend && ../.venv/bin/python seed.py)
(cd frontend && npm install)

echo
echo "Setup complete. In VS Code run:  Terminal > Run Task > 'Run everything'"
echo "Then open http://localhost:5173 and sign in with the admin ID you chose."

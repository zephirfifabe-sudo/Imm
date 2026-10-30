#!/usr/bin/env bash
# Lance le bot (scheduler H24) + le dashboard. Si l'un des deux meurt, le conteneur s'arrête
# et Docker le relance (restart: always).
set -euo pipefail
mkdir -p /app/data/logs
python main.py init

python main.py run &
BOT_PID=$!
uvicorn dashboard:app --host 0.0.0.0 --port 8000 --proxy-headers &
WEB_PID=$!

trap 'kill -TERM $BOT_PID $WEB_PID 2>/dev/null; wait' TERM INT
wait -n $BOT_PID $WEB_PID
echo "Un processus s'est arrêté -> redémarrage du conteneur" >&2
kill -TERM $BOT_PID $WEB_PID 2>/dev/null || true
exit 1

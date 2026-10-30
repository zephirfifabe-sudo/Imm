#!/usr/bin/env bash
# Mise à jour sur le VPS (Hetzner Ubuntu) : récupère le code et reconstruit le conteneur.
# Les données (./data) sont conservées.
set -euo pipefail
cd "$(dirname "$0")"

if ! command -v docker >/dev/null 2>&1; then
  echo "Installation de Docker..."
  curl -fsSL https://get.docker.com | sh
fi
# Docker déjà présent sans le plugin compose (cas fréquent sur les images OVH/Ubuntu) -> on l'ajoute
if ! docker compose version >/dev/null 2>&1; then
  echo "Installation du plugin docker compose..."
  apt-get update -qq && (apt-get install -y docker-compose-v2 || apt-get install -y docker-compose-plugin)
fi
[ -f .env ] || { cp .env.example .env; echo "⚠️  .env créé : remplis TELEGRAM_TOKEN / TELEGRAM_CHAT_ID puis relance ./deploy.sh"; exit 1; }
mkdir -p data/logs

git pull --ff-only
docker compose down
docker compose up -d --build
docker image prune -f >/dev/null
sleep 5
docker compose ps
echo "✅ Dashboard : http://$(curl -s -4 ifconfig.me 2>/dev/null || echo IP_DU_VPS):8000"
echo "Logs : tail -f data/logs/bot.log"

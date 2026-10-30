#!/usr/bin/env bash
# Installation guidée (pensée pour le téléphone) : 3 questions, puis tout est automatique.
#   sudo -i
#   cd /root/sniper && ./install.sh
set -euo pipefail
cd "$(dirname "$0")"

if [ "$(id -u)" -ne 0 ]; then
  echo "❌ Tape d'abord : sudo -i   puis relance : cd /root/sniper && ./install.sh"
  exit 1
fi

[ -f .env ] || cp .env.example .env

# Écrit KEY=valeur dans .env (remplace la ligne existante, sans sed : supporte tous les caractères)
set_env() {
  grep -v "^$1=" .env > .env.tmp || true
  printf '%s=%s\n' "$1" "$2" >> .env.tmp
  mv .env.tmp .env
  chmod 600 .env
}

echo "=== FC27 Sniper Analyst : installation ==="
echo
while true; do
  read -r -p "1/3 Colle l'URL du webhook Discord : " WEBHOOK </dev/tty
  WEBHOOK="$(printf '%s' "$WEBHOOK" | tr -d '[:space:]')"
  case "$WEBHOOK" in
    https://discord.com/api/webhooks/*|https://discordapp.com/api/webhooks/*|https://canary.discord.com/api/webhooks/*) break ;;
    *) echo "   ⚠️  L'URL doit commencer par https://discord.com/api/webhooks/ — réessaie." ;;
  esac
done
read -r -p "2/3 Identifiant du dashboard (ex: moi) : " DUSER </dev/tty
DUSER="${DUSER:-moi}"
while true; do
  read -r -s -p "3/3 Mot de passe du dashboard (8 caractères mini, sans espace, sans \$ ni guillemets) : " DPASS </dev/tty
  echo
  if [ "${#DPASS}" -ge 8 ] && [[ ! "$DPASS" =~ [[:space:]\$\"\'] ]]; then break; fi
  echo "   ⚠️  Trop court ou caractère interdit (espace, \$, guillemet) — réessaie."
done

set_env DISCORD_WEBHOOK_URL "$WEBHOOK"
set_env DASHBOARD_USER "$DUSER"
set_env DASHBOARD_PASSWORD "$DPASS"
echo "✅ Configuration enregistrée dans .env"
echo
echo "⏳ Installation de Docker + construction du bot (5 à 10 min, ne ferme pas l'appli)..."
./deploy.sh

echo
echo "⏳ Démarrage..."
for _ in $(seq 1 30); do
  docker compose exec -T sniper true >/dev/null 2>&1 && break
  sleep 2
done
docker compose exec -T sniper python main.py test-alert || true
# Mémoire de départ (historique + 1er apprentissage) en arrière-plan : peut prendre plusieurs minutes
docker compose exec -d sniper sh -c "python main.py backfill && python main.py learn" || true

IP="$(curl -s -4 --max-time 5 ifconfig.me || echo IP_DU_VPS)"
echo
echo "🎉 Terminé !"
echo "   • Un message de test doit être arrivé dans ton salon Discord."
echo "   • Dashboard : http://$IP:8000  (identifiant : $DUSER)"
echo "   • Logs      : tail -f /root/sniper/data/logs/bot.log"
echo "   • Mise à jour plus tard : sudo -i puis cd /root/sniper && ./deploy.sh"

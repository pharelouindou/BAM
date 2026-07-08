#!/usr/bin/env bash
set -euo pipefail

# Bootstrap initial du VPS BAM.
# À lancer une seule fois en root :
#   sudo bash deploy/vps/install_vps.sh

APP_USER="${APP_USER:-bam}"
APP_GROUP="${APP_GROUP:-$APP_USER}"
APP_DIR="${APP_DIR:-/opt/bam}"
ENV_DIR="${ENV_DIR:-/etc/bam}"

echo "==> Installation paquets système"
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y \
  python3 \
  python3-venv \
  python3-pip \
  git \
  curl \
  ca-certificates \
  docker.io \
  docker-compose-plugin

if ! id -u "$APP_USER" >/dev/null 2>&1; then
  echo "==> Création utilisateur système $APP_USER"
  useradd --system --create-home --shell /bin/bash "$APP_USER"
fi

echo "==> Création dossiers"
mkdir -p "$APP_DIR" "$ENV_DIR" /var/log/bam
chown -R "$APP_USER:$APP_GROUP" "$APP_DIR" /var/log/bam
chmod 750 "$ENV_DIR"

echo "==> Activation Docker"
systemctl enable --now docker
usermod -aG docker "$APP_USER"

echo "==> Installation terminée"
echo "Prochaines étapes :"
echo "  1. Cloner le repo dans $APP_DIR"
echo "  2. Créer $ENV_DIR/bam.env"
echo "  3. Installer le service systemd bam-pipeline.service"

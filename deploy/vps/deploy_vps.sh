#!/usr/bin/env bash
set -euo pipefail

# Déploiement idempotent BAM sur VPS.
# Le script suppose :
# - repo cloné dans /opt/bam
# - secrets présents dans /etc/bam/bam.env
# - GEE_CREDENTIALS_JSON disponible dans l'env ou bam.env
#
# Usage :
#   APP_DIR=/opt/bam ENV_FILE=/etc/bam/bam.env bash deploy/vps/deploy_vps.sh

APP_DIR="${APP_DIR:-/opt/bam}"
ENV_FILE="${ENV_FILE:-/etc/bam/bam.env}"
BRANCH="${BRANCH:-$(git -C "$APP_DIR" rev-parse --abbrev-ref HEAD 2>/dev/null || echo main)}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
VENV_DIR="${VENV_DIR:-$APP_DIR/.venv}"
SYSTEMD_UNIT="${SYSTEMD_UNIT:-bam-pipeline.service}"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Fichier d'environnement introuvable : $ENV_FILE"
  exit 1
fi

echo "==> Chargement env"
set -a
source "$ENV_FILE"
set +a

if [[ ! -d "$APP_DIR/.git" ]]; then
  echo "Repo git introuvable dans $APP_DIR"
  exit 1
fi

echo "==> Mise à jour du code ($BRANCH)"
git -C "$APP_DIR" fetch origin
git -C "$APP_DIR" checkout "$BRANCH"
git -C "$APP_DIR" pull --ff-only origin "$BRANCH"

echo "==> Virtualenv"
$PYTHON_BIN -m venv "$VENV_DIR"
"$VENV_DIR/bin/pip" install --upgrade pip
"$VENV_DIR/bin/pip" install -r "$APP_DIR/requirements.txt"

if [[ -n "${GEE_CREDENTIALS_JSON:-}" ]]; then
  echo "==> Écriture credentials GEE"
  export HOME="${HOME:-/root}"
  mkdir -p "$HOME/.config/earthengine"
  printf '%s' "$GEE_CREDENTIALS_JSON" > "$HOME/.config/earthengine/credentials"
  chmod 600 "$HOME/.config/earthengine/credentials"
fi

echo "==> Grafana"
docker compose -f "$APP_DIR/docker-compose.yml" --env-file "$ENV_FILE" up -d grafana

if command -v systemctl >/dev/null 2>&1; then
  echo "==> Redémarrage service $SYSTEMD_UNIT"
  systemctl daemon-reload
  systemctl enable "$SYSTEMD_UNIT"
  systemctl restart "$SYSTEMD_UNIT"
  systemctl --no-pager --full status "$SYSTEMD_UNIT" || true
fi

echo "==> Déploiement BAM terminé"

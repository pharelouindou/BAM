# Déploiement VPS BAM

Cette base permet de déployer BAM sur un VPS Linux avec :
- `bam_pipeline.py` lancé par `systemd`
- Grafana via `docker compose`
- secrets dans `/etc/bam/bam.env`
- déploiement automatique par SSH via `.github/workflows/deploy-vps.yml`

## 1. Bootstrap initial sur le VPS

Depuis le repo cloné une première fois :

```bash
sudo bash deploy/vps/install_vps.sh
sudo mkdir -p /opt/bam /etc/bam
sudo cp -r . /opt/bam
sudo cp deploy/vps/bam.env.example /etc/bam/bam.env
sudo install -m 644 deploy/systemd/bam-pipeline.service /etc/systemd/system/bam-pipeline.service
```

Puis compléter `/etc/bam/bam.env`.

## 2. Secrets attendus

Minimum :

```env
DATABASE_URL=...
GEE_PROJECT=...
GEE_CREDENTIALS_JSON=...
GRAFANA_DB_HOST=...
GRAFANA_DB_NAME=...
GRAFANA_DB_USER=...
GRAFANA_DB_PASSWORD=...
GRAFANA_DB_SSLMODE=require
```

Optionnel :

```env
NASA_USERNAME=...
NASA_PASSWORD=...
```

## 3. Déploiement manuel

```bash
sudo APP_DIR=/opt/bam ENV_FILE=/etc/bam/bam.env bash /opt/bam/deploy/vps/deploy_vps.sh
```

## 4. Déploiement CI/CD

Configurer les secrets suivants dans la plateforme CI :

- `VPS_HOST`
- `VPS_USER`
- `VPS_SSH_PRIVATE_KEY`
- `DATABASE_URL`
- `GEE_PROJECT`
- `GEE_CREDENTIALS_JSON`
- `GRAFANA_DB_HOST`
- `GRAFANA_DB_NAME`
- `GRAFANA_DB_USER`
- `GRAFANA_DB_PASSWORD`
- `GRAFANA_DB_SSLMODE`
- `NASA_USERNAME` / `NASA_PASSWORD` si nécessaire

Le workflow fourni pousse un snapshot du repo vers `/opt/bam`, écrit `/etc/bam/bam.env`, puis relance le service `bam-pipeline`.

## 5. Vérification

```bash
systemctl status bam-pipeline
tail -f /var/log/bam/bam-pipeline.log
docker compose -f /opt/bam/docker-compose.yml --env-file /etc/bam/bam.env ps
```

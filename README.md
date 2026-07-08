# BAM · BeninAquaMap

## Demarrage rapide

```bash
docker-compose up -d        # base + grafana
source .venv/bin/activate   # virtualenv
python test_connexion.py    # tout verifier
python main.py --no-sat     # sans satellite (météo + sol + pluie)
python main.py              # NASA AppEEARS + ORNL (sources stockées séparément)
python main.py --sat-sources=nasa,gee   # + Sentinel-2 via GEE (GEE_PROJECT + earthengine auth)
```

Priorité pour le **score** : Sentinel-2-GEE > AppEEARS > ORNL. Voir `python main.py` (docstring).
Après mise à jour du schéma : `python db/migrate_multisat.py` (colonne `source_satellite` + vue `mesures`).

## Verifier les donnees

```bash
docker compose exec postgres psql -U bam_user -d bam_local \
  -c "SELECT s.nom, m.score_total, m.priorite FROM mesures m
      JOIN sites s ON s.id=m.site_id ORDER BY m.score_total DESC LIMIT 5;"
```

## Grafana (grille Alibori)

Après `docker compose up -d`, la datasource PostgreSQL et le dashboard **BAM · Grille nationale (Alibori)** sont chargés depuis `dockewr/grafana/` (redémarrer Grafana si tu modifies les fichiers).

- URL : http://localhost:3000 — utilisateur `admin`, mot de passe `bam_admin`.
- Collecte département : `python process/enrichir_grille.py --dept "Alibori"` puis satellite : `python process/analyser_grille.py --dept "Alibori"`.

## Note rasterio

rasterio est absent des deps Mac (conflict GDAL).
Il sera installe sur le VPS Linux en phase 2.
En phase 1, CHIRPS passe par Open-Meteo comme proxy.

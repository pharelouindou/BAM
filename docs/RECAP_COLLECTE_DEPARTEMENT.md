# BAM — Récap collecte par département

## Objectif
Traiter la **grille nationale** du Bénin département par département pour :
1. enrichir les points (relief, sol, météo, pluie, score),
2. compléter le satellite (NDWI/NDVI),
3. suivre la progression dans PostgreSQL et Grafana.

---

## Principe de fonctionnement

- Les points GPS (`lat`, `lon`) sont déjà stockés dans `grille_nationale`.
- Le champ `departement` sert de filtre technique.
- L’option `--dept` limite le traitement à un seul département.

---

## Pipeline recommandé (par département)

### 1) Enrichissement non satellite
```bash
python process/enrichir_grille.py --dept "Alibori"
```

Ce script remplit notamment :
- `elevation_m`, `pente_pct`, `twi`
- `ph_sol`, `carbone_g_kg`, `argile_pct`
- `pluie_30j_mm`, `humidite_sol`, `temp_max_c`
- `score_total`, `priorite`, `est_bas_fond`, `est_humide`
- `date_analyse`

---

### 2) Enrichissement satellite (GEE)
```bash
python process/analyser_grille.py --dept "Alibori"
```

Ce script traite les points du département avec `ndwi IS NULL`, puis remplit :
- `ndwi`, `ndvi`
- `score_eau`, `est_humide`
- `source_ndwi` (ex. `Sentinel-2-GEE`, `AppEEARS`, `ORNL`)
- `date_analyse`

> Source satellite : par défaut **`GEE` seul** (rapide). Pour ajouter le fallback **`NASA`** (lent) : `python process/analyser_grille.py --dept "Alibori" --sat-sources=gee,nasa`.

---

## Commandes utiles

### Test sur petit lot
```bash
python process/enrichir_grille.py --dept "Alibori" --limit 100
python process/analyser_grille.py --dept "Alibori" --limit 100
```

### Reprise complète d’un département
```bash
python process/enrichir_grille.py --reset-dept "Alibori"
python process/enrichir_grille.py --dept "Alibori"
python process/analyser_grille.py --dept "Alibori"
```

### Croisement coordonnées -> ville/commune (optionnel)
```bash
python db/migrate_admin_geo.py
python process/enrichir_admin.py --dept "Alibori" --limit 300
```

---

## Contrôle qualité minimal

- Vérifier qu’il reste peu/pas de `ndwi IS NULL` dans le département.
- Vérifier que `date_analyse` est renseigné.
- Vérifier la cohérence des scores/priorités.
- Sur Grafana : suivre la couverture départementale et la table des points.

---

## Problèmes fréquents

- **API lente / timeout** (Open-Elevation, ISRIC, NASA) → relancer en lots (`--limit`).
- **Pas de satellite (`no-sat`)** → activer/configurer GEE (`GEE_PROJECT`, `earthengine authenticate`).
- **Valeurs sol nulles** → fallback par défaut selon le pipeline.

---

## Résultat attendu

À la fin d’un département :
- les points de `grille_nationale` du département sont enrichis,
- le NDWI satellite est renseigné (ou clairement tracé si indisponible),
- la visualisation Grafana reflète la progression.

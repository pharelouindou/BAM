# BAM API Documentation

API BAM pour exposer les sites, mesures et statistiques.

## Lancer l’API

```bash
uvicorn api.app:app --reload --host 0.0.0.0 --port 8001
```

## Swagger / ReDoc

- Swagger UI : `http://localhost:8001/docs`
- ReDoc : `http://localhost:8001/redoc`

## Variables d’environnement

- `DATABASE_URL` : URL PostgreSQL.

## Endpoints

### GET /health

Vérifie que l’API et la base fonctionnent.

Réponse :

```json
{
  "status": "ok",
  "db": "ok",
  "timestamp": "2026-04-..."
}
```

### GET /departements

Liste des départements et nombre de sites.

Réponse : liste de `{ departement, nb_sites }`.

### GET /sites

Liste des sites.

Paramètres optionnels :

- `departement` : filtre par département
- `limit` : 1–1000 (par défaut 100)
- `offset` : décalage (par défaut 0)

Réponse : liste de sites avec `id`, `nom`, `departement`, `commune`, `lat`, `lon`, `superficie_ha`, `cout_activation_m_fcfa`.

### GET /sites/{site_id}

Détail d’un site.

Réponse : site avec `id`, `nom`, `departement`, `commune`, `lat`, `lon`, `superficie_ha`, `cout_activation_m_fcfa`, `created_at`.

### GET /mesures/latest

Dernières mesures pour tous les sites.

Paramètres optionnels :

- `limit` : 1–1000 (par défaut 50)
- `departement` : filtre par département

Réponse : liste de mesures avec `site_id`, `site_nom`, `departement`, `date_collecte`, `ndwi`, `ndvi`, `mndwi`, `ph_sol`, `carbone_g_kg`, `argile_pct`, `pluie_7j_mm`, `pluie_30j_mm`, `humidite_sol`, `temp_max_c`, `score_total`, `priorite`, `source`, `created_at`.

### GET /mesures/by-site/{site_id}

Historique des mesures pour un site.

Paramètre :

- `site_id` : identifiant du site

Optionnel :

- `limit` : 1–2000 (par défaut 200)

Réponse : mesures triées par date descendante.

### GET /mesures/latest-per-site

Dernière mesure disponible par site.

Réponse : pour chaque site, dernière mesure avec les mêmes champs que `/mesures/latest`.

### GET /stats/overview

KPI globaux :

- `total_sites`
- `total_mesures`
- `derniere_date_collecte`
- `score_moyen_jour`
- `mesures_du_jour`

### GET /stats/priorites

Répartition des priorités.

Paramètre optionnel :

- `date_collecte` : `YYYY-MM-DD`

Réponse : liste `{ priorite, nb }`.

## Notes

- L’API repose sur les tables `sites` et `mesures`.
- Les données sont utilisées en front dans `aquamap_benin.html` ou par Grafana.
"""API BAM (FastAPI) pour exposer sites, mesures et stats."""
import os
from typing import Any

import psycopg2
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from psycopg2.extras import RealDictCursor

load_dotenv()

app = FastAPI(
    title="BAM API",
    version="0.2.0",
    description="API de consultation des donnees BAM (sites, mesures, stats).",
)

# Permettre le branchement simple du HTML local.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_conn():
    url = os.getenv("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL manquante dans .env")
    return psycopg2.connect(url)


def fetch_all(sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    conn = get_conn()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute(sql, params)
    rows = [dict(r) for r in cur.fetchall()]
    cur.close()
    conn.close()
    return rows


def fetch_one(sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
    conn = get_conn()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute(sql, params)
    row = cur.fetchone()
    cur.close()
    conn.close()
    return dict(row) if row else None


@app.get("/health")
def health() -> dict[str, Any]:
    """Etat API + DB."""
    try:
        db_time = fetch_one("SELECT NOW() AS now")
        return {"status": "ok", "db": "ok", "timestamp": str(db_time["now"])}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"DB indisponible: {exc}") from exc


@app.get("/departements")
def list_departements() -> list[dict[str, Any]]:
    """Liste des departements avec nb de sites."""
    return fetch_all(
        """
        SELECT departement, COUNT(*) AS nb_sites
        FROM sites
        GROUP BY departement
        ORDER BY departement
        """
    )


@app.get("/sites")
def list_sites(
    departement: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> list[dict[str, Any]]:
    """Liste des sites avec filtre optionnel par departement."""
    if departement:
        return fetch_all(
            """
            SELECT id, nom, departement, commune, lat, lon, superficie_ha
            FROM sites
            WHERE departement = %s
            ORDER BY id
            LIMIT %s OFFSET %s
            """,
            (departement, limit, offset),
        )
    return fetch_all(
        """
        SELECT id, nom, departement, commune, lat, lon, superficie_ha
        FROM sites
        ORDER BY id
        LIMIT %s OFFSET %s
        """,
        (limit, offset),
    )


@app.get("/sites/{site_id}")
def get_site(site_id: int) -> dict[str, Any]:
    """Detail d'un site."""
    row = fetch_one(
        """
        SELECT id, nom, departement, commune, lat, lon, superficie_ha, created_at
        FROM sites
        WHERE id = %s
        """,
        (site_id,),
    )
    if not row:
        raise HTTPException(status_code=404, detail=f"Site {site_id} introuvable")
    return row


@app.get("/mesures/latest")
def latest_mesures(
    limit: int = Query(default=50, ge=1, le=1000),
    departement: str | None = Query(default=None),
) -> list[dict[str, Any]]:
    """Dernieres mesures, avec filtre departement optionnel."""
    if departement:
        return fetch_all(
            """
            SELECT
                m.id, m.site_id, s.nom AS site_nom, s.departement, m.date_collecte,
                m.ndwi, m.ndvi, m.mndwi, m.ph_sol, m.carbone_g_kg, m.argile_pct,
                m.pluie_7j_mm, m.pluie_30j_mm, m.humidite_sol, m.temp_max_c,
                m.score_total, m.priorite, m.source, m.created_at
            FROM mesures m
            JOIN sites s ON s.id = m.site_id
            WHERE s.departement = %s
            ORDER BY m.date_collecte DESC, m.created_at DESC, m.id DESC
            LIMIT %s
            """,
            (departement, limit),
        )
    return fetch_all(
        """
        SELECT
            m.id, m.site_id, s.nom AS site_nom, s.departement, m.date_collecte,
            m.ndwi, m.ndvi, m.mndwi, m.ph_sol, m.carbone_g_kg, m.argile_pct,
            m.pluie_7j_mm, m.pluie_30j_mm, m.humidite_sol, m.temp_max_c,
            m.score_total, m.priorite, m.source, m.created_at
        FROM mesures m
        JOIN sites s ON s.id = m.site_id
        ORDER BY m.date_collecte DESC, m.created_at DESC, m.id DESC
        LIMIT %s
        """,
        (limit,),
    )


@app.get("/mesures/by-site/{site_id}")
def mesures_by_site(
    site_id: int,
    limit: int = Query(default=200, ge=1, le=2000),
) -> list[dict[str, Any]]:
    """Historique des mesures pour un site."""
    site = fetch_one("SELECT id FROM sites WHERE id = %s", (site_id,))
    if not site:
        raise HTTPException(status_code=404, detail=f"Site {site_id} introuvable")
    return fetch_all(
        """
        SELECT
            m.id, m.site_id, m.date_collecte, m.ndwi, m.ndvi, m.mndwi,
            m.ph_sol, m.carbone_g_kg, m.argile_pct, m.pluie_7j_mm, m.pluie_30j_mm,
            m.humidite_sol, m.temp_max_c, m.score_total, m.priorite, m.source, m.created_at
        FROM mesures m
        WHERE m.site_id = %s
        ORDER BY m.date_collecte DESC, m.created_at DESC, m.id DESC
        LIMIT %s
        """,
        (site_id, limit),
    )


@app.get("/mesures/latest-per-site")
def latest_per_site() -> list[dict[str, Any]]:
    """Derniere mesure disponible pour chaque site."""
    return fetch_all(
        """
        SELECT DISTINCT ON (s.id)
            s.id AS site_id, s.nom AS site_nom, s.departement, s.commune, s.lat, s.lon,
            m.date_collecte, m.ndwi, m.ndvi, m.mndwi, m.ph_sol, m.carbone_g_kg, m.argile_pct,
            m.pluie_7j_mm, m.pluie_30j_mm, m.humidite_sol, m.temp_max_c,
            m.score_total, m.priorite, m.source, m.created_at
        FROM sites s
        LEFT JOIN mesures m ON m.site_id = s.id
        ORDER BY s.id, m.date_collecte DESC, m.created_at DESC, m.id DESC
        """
    )


@app.get("/stats/overview")
def stats_overview() -> dict[str, Any]:
    """KPI globaux pour dashboard."""
    row = fetch_one(
        """
        SELECT
            (SELECT COUNT(*) FROM sites) AS total_sites,
            (SELECT COUNT(*) FROM mesures) AS total_mesures,
            (SELECT MAX(date_collecte) FROM mesures) AS derniere_date_collecte,
            (SELECT ROUND(AVG(score_total)::numeric, 1) FROM mesures WHERE date_collecte = CURRENT_DATE) AS score_moyen_jour,
            (SELECT COUNT(*) FROM mesures WHERE date_collecte = CURRENT_DATE) AS mesures_du_jour
        """
    )
    return row or {}


@app.get("/grille/stats")
def grille_stats() -> dict[str, Any]:
    """KPI globaux de la grille nationale."""
    row = fetch_one(
        """
        SELECT
            COUNT(*)                                        AS total_points,
            COUNT(*) FILTER (WHERE date_analyse IS NOT NULL) AS analyses,
            COUNT(*) FILTER (WHERE est_bas_fond = TRUE)     AS bas_fonds,
            COUNT(*) FILTER (WHERE est_humide   = TRUE)     AS humides,
            ROUND(AVG(score_total)::numeric, 1)             AS score_moyen
        FROM grille_nationale
        """
    )
    return row or {}


@app.get("/grille/bas-fonds")
def grille_bas_fonds(
    departement: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=5000),
    priorite: str | None = Query(default=None, description="haute|moyenne|basse"),
) -> list[dict[str, Any]]:
    """Retourne les zones identifiées comme bas-fonds potentiels."""
    conds  = ["est_bas_fond = TRUE", "date_analyse IS NOT NULL"]
    params: list[Any] = []

    if departement:
        conds.append("departement = %s")
        params.append(departement)
    if priorite:
        conds.append("priorite = %s")
        params.append(priorite)

    where = " AND ".join(conds)
    params.append(limit)

    return fetch_all(
        f"""
        SELECT
            id_grille, lat, lon, departement, commune, arrondissement, localite,
            elevation_m, pente_pct, twi,
            ph_sol, carbone_g_kg, argile_pct,
            pluie_30j_mm, humidite_sol, temp_max_c,
            ndwi, ndvi, score_eau, score_total,
            est_humide, est_bas_fond, priorite,
            source_ndwi, date_analyse
        FROM grille_nationale
        WHERE {where}
        ORDER BY score_total DESC NULLS LAST
        LIMIT %s
        """,
        tuple(params),
    )


@app.get("/grille/humides")
def grille_humides(
    departement: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=5000),
) -> list[dict[str, Any]]:
    """Retourne les zones humides détectées (NDWI > 0.2 ou humidité élevée)."""
    if departement:
        return fetch_all(
            """
            SELECT id_grille, lat, lon, departement,
                   commune, arrondissement, localite,
                   twi, ndwi, humidite_sol, pluie_30j_mm,
                   score_eau, score_total, priorite, date_analyse
            FROM grille_nationale
            WHERE est_humide = TRUE AND departement = %s
            ORDER BY score_total DESC NULLS LAST
            LIMIT %s
            """,
            (departement, limit),
        )
    return fetch_all(
        """
        SELECT id_grille, lat, lon, departement,
               commune, arrondissement, localite,
               twi, ndwi, humidite_sol, pluie_30j_mm,
               score_eau, score_total, priorite, date_analyse
        FROM grille_nationale
        WHERE est_humide = TRUE
        ORDER BY score_total DESC NULLS LAST
        LIMIT %s
        """,
        (limit,),
    )


@app.get("/grille/candidats")
def grille_candidats(
    departement: str | None = Query(default=None),
    score_min: float = Query(default=60.0, ge=0.0, le=100.0),
    limit: int = Query(default=100, ge=1, le=1000),
) -> list[dict[str, Any]]:
    """
    Retourne les candidats sites irrigables prioritaires.
    Critères : bas-fond ET score >= score_min.
    """
    if departement:
        return fetch_all(
            """
            SELECT id_grille, lat, lon, departement,
                   commune, arrondissement, localite,
                   elevation_m, twi, ndwi, ndvi,
                   ph_sol, carbone_g_kg, argile_pct,
                   pluie_30j_mm, humidite_sol, temp_max_c,
                   score_eau, score_total, priorite, date_analyse
            FROM grille_nationale
            WHERE est_bas_fond = TRUE
              AND score_total >= %s
              AND departement = %s
            ORDER BY score_total DESC NULLS LAST
            LIMIT %s
            """,
            (score_min, departement, limit),
        )
    return fetch_all(
        """
        SELECT id_grille, lat, lon, departement,
               commune, arrondissement, localite,
               elevation_m, twi, ndwi, ndvi,
               ph_sol, carbone_g_kg, argile_pct,
               pluie_30j_mm, humidite_sol, temp_max_c,
               score_eau, score_total, priorite, date_analyse
        FROM grille_nationale
        WHERE est_bas_fond = TRUE
          AND score_total >= %s
        ORDER BY score_total DESC NULLS LAST
        LIMIT %s
        """,
        (score_min, limit),
    )


@app.get("/grille/par-departement")
def grille_par_departement() -> list[dict[str, Any]]:
    """Résumé de la grille par département."""
    return fetch_all(
        """
        SELECT
            departement,
            COUNT(*)                                         AS total_points,
            COUNT(*) FILTER (WHERE date_analyse IS NOT NULL) AS analyses,
            COUNT(*) FILTER (WHERE est_bas_fond = TRUE)      AS bas_fonds,
            COUNT(*) FILTER (WHERE est_humide   = TRUE)      AS humides,
            ROUND(AVG(score_total)::numeric, 1)              AS score_moyen,
            ROUND(MAX(score_total)::numeric, 1)              AS score_max
        FROM grille_nationale
        GROUP BY departement
        ORDER BY departement
        """
    )


@app.get("/stats/priorites")
def stats_priorites(
    date_collecte: str | None = Query(default=None, description="YYYY-MM-DD"),
) -> list[dict[str, Any]]:
    """Repartition des priorites."""
    if date_collecte:
        return fetch_all(
            """
            SELECT priorite, COUNT(*) AS nb
            FROM mesures
            WHERE date_collecte = %s
            GROUP BY priorite
            ORDER BY nb DESC
            """,
            (date_collecte,),
        )
    return fetch_all(
        """
        SELECT priorite, COUNT(*) AS nb
        FROM mesures
        WHERE date_collecte = CURRENT_DATE
        GROUP BY priorite
        ORDER BY nb DESC
        """
    )

"""
BAM · Historique journalier de la grille.

Chaque collecte met à jour `grille_nationale` (état courant), puis copie l'état
du point dans `grille_historique_journalier` pour permettre le suivi temporel.
"""

from __future__ import annotations

from datetime import date


def ensure_historique_table(cur) -> None:
    """Crée la table historique si elle n'existe pas encore."""
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS grille_historique_journalier (
            id              SERIAL PRIMARY KEY,
            id_grille       TEXT NOT NULL REFERENCES grille_nationale(id_grille) ON DELETE CASCADE,
            date_collecte   DATE NOT NULL,
            departement     TEXT,
            commune         TEXT,
            lat             NUMERIC(9,6),
            lon             NUMERIC(9,6),
            elevation_m     NUMERIC(7,1),
            pente_pct       NUMERIC(6,3),
            twi             NUMERIC(6,3),
            ph_sol          NUMERIC(4,2),
            carbone_g_kg    NUMERIC(6,2),
            argile_pct      NUMERIC(5,2),
            pluie_30j_mm    NUMERIC(7,2),
            humidite_sol    NUMERIC(6,4),
            temp_max_c      NUMERIC(5,2),
            ndwi            NUMERIC(6,4),
            ndvi            NUMERIC(6,4),
            score_eau       NUMERIC(5,1),
            score_total     NUMERIC(5,1),
            est_humide      BOOLEAN,
            est_bas_fond    BOOLEAN,
            priorite        TEXT,
            source_ndwi     TEXT,
            created_at      TIMESTAMP DEFAULT NOW(),
            UNIQUE(id_grille, date_collecte)
        )
        """
    )
    cur.execute("CREATE INDEX IF NOT EXISTS idx_grille_hist_date ON grille_historique_journalier(date_collecte)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_grille_hist_dept ON grille_historique_journalier(departement)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_grille_hist_commune ON grille_historique_journalier(commune)")
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_grille_hist_point ON grille_historique_journalier(id_grille, date_collecte DESC)"
    )


def enregistrer_snapshot_journalier(cur, id_grille: str, date_collecte: date | None = None) -> None:
    """Copie l'état courant d'un point dans l'historique journalier."""
    ensure_historique_table(cur)
    cur.execute(
        """
        INSERT INTO grille_historique_journalier (
            id_grille, date_collecte, departement, commune, lat, lon,
            elevation_m, pente_pct, twi,
            ph_sol, carbone_g_kg, argile_pct,
            pluie_30j_mm, humidite_sol, temp_max_c,
            ndwi, ndvi, score_eau, score_total,
            est_humide, est_bas_fond, priorite, source_ndwi
        )
        SELECT
            id_grille, %s, departement, commune, lat, lon,
            elevation_m, pente_pct, twi,
            ph_sol, carbone_g_kg, argile_pct,
            pluie_30j_mm, humidite_sol, temp_max_c,
            ndwi, ndvi, score_eau, score_total,
            est_humide, est_bas_fond, priorite, source_ndwi
        FROM grille_nationale
        WHERE id_grille = %s
        ON CONFLICT (id_grille, date_collecte) DO UPDATE SET
            departement   = EXCLUDED.departement,
            commune       = EXCLUDED.commune,
            lat           = EXCLUDED.lat,
            lon           = EXCLUDED.lon,
            elevation_m   = EXCLUDED.elevation_m,
            pente_pct     = EXCLUDED.pente_pct,
            twi           = EXCLUDED.twi,
            ph_sol        = EXCLUDED.ph_sol,
            carbone_g_kg  = EXCLUDED.carbone_g_kg,
            argile_pct    = EXCLUDED.argile_pct,
            pluie_30j_mm  = EXCLUDED.pluie_30j_mm,
            humidite_sol  = EXCLUDED.humidite_sol,
            temp_max_c    = EXCLUDED.temp_max_c,
            ndwi          = EXCLUDED.ndwi,
            ndvi          = EXCLUDED.ndvi,
            score_eau     = EXCLUDED.score_eau,
            score_total   = EXCLUDED.score_total,
            est_humide    = EXCLUDED.est_humide,
            est_bas_fond  = EXCLUDED.est_bas_fond,
            priorite      = EXCLUDED.priorite,
            source_ndwi   = EXCLUDED.source_ndwi
        """,
        (date_collecte or date.today(), id_grille),
    )

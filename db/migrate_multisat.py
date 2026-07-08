#!/usr/bin/env python3
"""Ajoute scores.source_satellite et recrée la vue mesures (multi-sources satellite)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psycopg2
from dotenv import load_dotenv

load_dotenv()

VIEW_SQL = """
CREATE OR REPLACE VIEW mesures AS
SELECT
    sc.id,
    sc.site_id,
    sc.date_calcul AS date_collecte,
    COALESCE(
        MAX(CASE WHEN i.nom_indice = 'ndwi'  AND i.categorie = 'satellite'
            AND sc.source_satellite IS NOT NULL AND i.source = sc.source_satellite
            THEN i.valeur END),
        MAX(CASE WHEN i.nom_indice = 'ndwi'  AND i.categorie = 'satellite' THEN i.valeur END)
    ) AS ndwi,
    COALESCE(
        MAX(CASE WHEN i.nom_indice = 'ndvi'  AND i.categorie = 'satellite'
            AND sc.source_satellite IS NOT NULL AND i.source = sc.source_satellite
            THEN i.valeur END),
        MAX(CASE WHEN i.nom_indice = 'ndvi'  AND i.categorie = 'satellite' THEN i.valeur END)
    ) AS ndvi,
    COALESCE(
        MAX(CASE WHEN i.nom_indice = 'mndwi' AND i.categorie = 'satellite'
            AND sc.source_satellite IS NOT NULL AND i.source = sc.source_satellite
            THEN i.valeur END),
        MAX(CASE WHEN i.nom_indice = 'mndwi' AND i.categorie = 'satellite' THEN i.valeur END)
    ) AS mndwi,
    MAX(CASE WHEN i.nom_indice = 'ph_sol'       AND i.categorie = 'sol'   THEN i.valeur END)   AS ph_sol,
    MAX(CASE WHEN i.nom_indice = 'carbone_g_kg' AND i.categorie = 'sol'   THEN i.valeur END)   AS carbone_g_kg,
    MAX(CASE WHEN i.nom_indice = 'argile_pct'   AND i.categorie = 'sol'   THEN i.valeur END)   AS argile_pct,
    MAX(CASE WHEN i.nom_indice = 'pluie_7j_mm'  AND i.categorie = 'meteo' THEN i.valeur END)   AS pluie_7j_mm,
    MAX(CASE WHEN i.nom_indice = 'pluie_30j_mm' AND i.categorie = 'pluie' THEN i.valeur END)   AS pluie_30j_mm,
    MAX(CASE WHEN i.nom_indice = 'humidite_sol' AND i.categorie = 'meteo' THEN i.valeur END)   AS humidite_sol,
    MAX(CASE WHEN i.nom_indice = 'temp_max_c'   AND i.categorie = 'meteo' THEN i.valeur END)   AS temp_max_c,
    sc.s_eau,
    sc.s_sol,
    sc.s_pluie,
    sc.s_temp,
    sc.score_total,
    sc.priorite,
    COALESCE(
        sc.source_satellite,
        CASE WHEN sc.avec_satellite THEN 'AppEEARS' ELSE 'no-sat' END
    ) AS source,
    sc.created_at
FROM scores sc
LEFT JOIN indices i
       ON i.site_id       = sc.site_id
      AND i.date_collecte = sc.date_calcul
GROUP BY
    sc.id, sc.site_id, sc.date_calcul, sc.source_satellite,
    sc.s_eau, sc.s_sol, sc.s_pluie, sc.s_temp,
    sc.score_total, sc.priorite, sc.avec_satellite, sc.created_at
"""


def run() -> None:
    conn = psycopg2.connect(os.getenv("DATABASE_URL"))
    cur  = conn.cursor()
    cur.execute(
        "ALTER TABLE scores ADD COLUMN IF NOT EXISTS source_satellite TEXT"
    )
    # Renseigner les lignes existantes (avant multi-source, la vue supposait AppEEARS si True)
    cur.execute(
        """
        UPDATE scores SET source_satellite = CASE
            WHEN avec_satellite IS TRUE THEN 'AppEEARS'
            ELSE 'no-sat'
        END
        WHERE source_satellite IS NULL
        """
    )
    cur.execute(VIEW_SQL)
    conn.commit()
    cur.close()
    conn.close()
    print("OK : source_satellite + vue mesures (multi-source)")


if __name__ == "__main__":
    run()

#!/usr/bin/env python3
"""
BAM · Migration v2 — restructuration de la base de données.

Ce script effectue la migration depuis l'ancien schéma (table `mesures` plate)
vers le nouveau schéma normalisé (tables `indices` + `scores` + vue `mesures`).

Il gère aussi la suppression de la colonne `cout_activation_m_fcfa` dans `sites`.

Usage :
  python db/migrate.py          # migration complète
  python db/migrate.py --dry-run  # vérification sans modification
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psycopg2
from dotenv import load_dotenv
load_dotenv()

DRY_RUN = "--dry-run" in sys.argv


def get_conn():
    return psycopg2.connect(os.getenv("DATABASE_URL"))


def run():
    conn = get_conn()
    cur  = conn.cursor()

    print("=" * 60)
    print("  BAM · Migration v2")
    print("  Ancien schéma → indices + scores + vue mesures")
    if DRY_RUN:
        print("  MODE DRY-RUN : aucune modification appliquée")
    print("=" * 60)

    # ── 1. Vérifier si la table mesures (ancienne) existe ─────────────────
    cur.execute("""
        SELECT EXISTS (
            SELECT 1 FROM information_schema.tables
            WHERE table_schema = 'public'
              AND table_name   = 'mesures'
              AND table_type   = 'BASE TABLE'
        )
    """)
    old_mesures_exists = cur.fetchone()[0]

    if old_mesures_exists:
        cur.execute("SELECT COUNT(*) FROM mesures")
        nb_old = cur.fetchone()[0]
        print(f"\n[1] Ancienne table mesures trouvée : {nb_old} lignes à migrer")
    else:
        print("\n[1] Pas d'ancienne table mesures (déjà une vue ou absent)")
        nb_old = 0

    # ── 2. Créer les nouvelles tables si inexistantes ─────────────────────
    print("\n[2] Création des tables indices et scores...")

    if not DRY_RUN:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS indices (
                id            BIGSERIAL PRIMARY KEY,
                site_id       INTEGER NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
                date_collecte DATE NOT NULL,
                categorie     TEXT NOT NULL
                    CHECK(categorie IN ('satellite','sol','meteo','pluie')),
                nom_indice    TEXT NOT NULL,
                valeur        NUMERIC(10,4),
                source        TEXT NOT NULL DEFAULT 'inconnu',
                qualite       TEXT NOT NULL DEFAULT 'ok'
                    CHECK(qualite IN ('ok','estime','defaut','erreur')),
                created_at    TIMESTAMP DEFAULT NOW(),
                UNIQUE(site_id, date_collecte, nom_indice, source)
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS scores (
                id             BIGSERIAL PRIMARY KEY,
                site_id        INTEGER NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
                date_calcul    DATE NOT NULL,
                s_eau          NUMERIC(5,1),
                s_sol          NUMERIC(5,1),
                s_pluie        NUMERIC(5,1),
                s_temp         NUMERIC(5,1),
                score_total    NUMERIC(5,1) NOT NULL,
                priorite       TEXT NOT NULL
                    CHECK(priorite IN ('haute','moyenne','basse')),
                avec_satellite BOOLEAN DEFAULT FALSE,
                version_algo   TEXT DEFAULT 'v2',
                created_at     TIMESTAMP DEFAULT NOW(),
                UNIQUE(site_id, date_calcul)
            )
        """)
        for idx_sql in [
            "CREATE INDEX IF NOT EXISTS idx_indices_site      ON indices(site_id, date_collecte DESC)",
            "CREATE INDEX IF NOT EXISTS idx_indices_nom       ON indices(nom_indice)",
            "CREATE INDEX IF NOT EXISTS idx_indices_categorie ON indices(categorie)",
            "CREATE INDEX IF NOT EXISTS idx_scores_score      ON scores(score_total DESC)",
            "CREATE INDEX IF NOT EXISTS idx_scores_priorite   ON scores(priorite)",
            "CREATE INDEX IF NOT EXISTS idx_scores_site       ON scores(site_id, date_calcul DESC)",
        ]:
            cur.execute(idx_sql)
        conn.commit()
        print("  ✓ Tables indices et scores créées")
    else:
        print("  [dry-run] Tables indices et scores seraient créées")

    # ── 3. Migrer les données existantes ──────────────────────────────────
    if old_mesures_exists and nb_old > 0:
        print(f"\n[3] Migration de {nb_old} lignes vers indices + scores...")

        cur.execute("""
            SELECT site_id, date_collecte,
                   ndwi, ndvi, mndwi,
                   ph_sol, carbone_g_kg, argile_pct,
                   pluie_7j_mm, pluie_30j_mm, humidite_sol, temp_max_c,
                   score_total, priorite, source
            FROM mesures
            ORDER BY site_id, date_collecte
        """)
        rows = cur.fetchall()

        migrated_indices = 0
        migrated_scores  = 0

        if not DRY_RUN:
            for row in rows:
                (site_id, date_col,
                 ndwi, ndvi, mndwi,
                 ph_sol, carbone, argile,
                 p7j, p30j, humidite, temp_max,
                 score_total, priorite, source) = row

                source_sat = source or "inconnu"
                avec_sat   = source_sat not in ("inconnu", "collecte", "no-sat", "")

                # Indices bruts
                indices_def = [
                    ("satellite", "ndwi",         ndwi,     source_sat),
                    ("satellite", "ndvi",         ndvi,     source_sat),
                    ("satellite", "mndwi",        mndwi,    source_sat),
                    ("sol",       "ph_sol",       ph_sol,   "ISRIC"),
                    ("sol",       "carbone_g_kg", carbone,  "ISRIC"),
                    ("sol",       "argile_pct",   argile,   "ISRIC"),
                    ("meteo",     "humidite_sol", humidite, "Open-Meteo"),
                    ("meteo",     "temp_max_c",   temp_max, "Open-Meteo"),
                    ("meteo",     "pluie_7j_mm",  p7j,      "Open-Meteo"),
                    ("pluie",     "pluie_30j_mm", p30j,     "Open-Meteo"),
                ]

                for categorie, nom, valeur, src in indices_def:
                    if valeur is None:
                        continue
                    cur.execute("""
                        INSERT INTO indices
                            (site_id, date_collecte, categorie, nom_indice, valeur, source, qualite)
                        VALUES (%s, %s, %s, %s, %s, %s, 'estime')
                        ON CONFLICT DO NOTHING
                    """, (site_id, date_col, categorie, nom, valeur, src))
                    migrated_indices += 1

                if score_total is not None and priorite is not None:
                    cur.execute("""
                        INSERT INTO scores (site_id, date_calcul, score_total, priorite, avec_satellite)
                        VALUES (%s, %s, %s, %s, %s)
                        ON CONFLICT DO NOTHING
                    """, (site_id, date_col, score_total, priorite, avec_sat))
                    migrated_scores += 1

            conn.commit()
            print(f"  ✓ {migrated_indices} indices migrés")
            print(f"  ✓ {migrated_scores} scores migrés")
        else:
            print(f"  [dry-run] {nb_old} lignes seraient migrées")

    # ── 4. Renommer l'ancienne table mesures ──────────────────────────────
    if old_mesures_exists:
        print("\n[4] Archivage de l'ancienne table mesures...")
        if not DRY_RUN:
            cur.execute("ALTER TABLE mesures RENAME TO mesures_old")
            conn.commit()
            print("  ✓ Table renommée en mesures_old (conservée pour rollback)")
        else:
            print("  [dry-run] Table mesures serait renommée en mesures_old")

    # ── 5. Créer la vue mesures ────────────────────────────────────────────
    print("\n[5] Création de la vue mesures...")
    view_sql = """
        CREATE OR REPLACE VIEW mesures AS
        SELECT
            sc.id,
            sc.site_id,
            sc.date_calcul                                                    AS date_collecte,
            MAX(CASE WHEN i.nom_indice = 'ndwi'         THEN i.valeur END)   AS ndwi,
            MAX(CASE WHEN i.nom_indice = 'ndvi'         THEN i.valeur END)   AS ndvi,
            MAX(CASE WHEN i.nom_indice = 'mndwi'        THEN i.valeur END)   AS mndwi,
            MAX(CASE WHEN i.nom_indice = 'ph_sol'       THEN i.valeur END)   AS ph_sol,
            MAX(CASE WHEN i.nom_indice = 'carbone_g_kg' THEN i.valeur END)   AS carbone_g_kg,
            MAX(CASE WHEN i.nom_indice = 'argile_pct'   THEN i.valeur END)   AS argile_pct,
            MAX(CASE WHEN i.nom_indice = 'pluie_7j_mm'  THEN i.valeur END)   AS pluie_7j_mm,
            MAX(CASE WHEN i.nom_indice = 'pluie_30j_mm' THEN i.valeur END)   AS pluie_30j_mm,
            MAX(CASE WHEN i.nom_indice = 'humidite_sol' THEN i.valeur END)   AS humidite_sol,
            MAX(CASE WHEN i.nom_indice = 'temp_max_c'   THEN i.valeur END)   AS temp_max_c,
            sc.s_eau,
            sc.s_sol,
            sc.s_pluie,
            sc.s_temp,
            sc.score_total,
            sc.priorite,
            CASE WHEN sc.avec_satellite THEN 'AppEEARS' ELSE 'no-sat' END    AS source,
            sc.created_at
        FROM scores sc
        LEFT JOIN indices i
               ON i.site_id       = sc.site_id
              AND i.date_collecte = sc.date_calcul
        GROUP BY
            sc.id, sc.site_id, sc.date_calcul,
            sc.s_eau, sc.s_sol, sc.s_pluie, sc.s_temp,
            sc.score_total, sc.priorite, sc.avec_satellite, sc.created_at
    """
    if not DRY_RUN:
        cur.execute(view_sql)
        conn.commit()
        print("  ✓ Vue mesures créée")
    else:
        print("  [dry-run] Vue mesures serait créée")

    # ── 6. Supprimer cout_activation_m_fcfa de sites ──────────────────────
    print("\n[6] Vérification colonne cout_activation_m_fcfa dans sites...")
    cur.execute("""
        SELECT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_name  = 'sites'
              AND column_name = 'cout_activation_m_fcfa'
        )
    """)
    col_exists = cur.fetchone()[0]

    if col_exists:
        if not DRY_RUN:
            cur.execute("ALTER TABLE sites DROP COLUMN IF EXISTS cout_activation_m_fcfa")
            conn.commit()
            print("  ✓ Colonne cout_activation_m_fcfa supprimée de sites")
        else:
            print("  [dry-run] Colonne cout_activation_m_fcfa serait supprimée")
    else:
        print("  ✓ Colonne déjà absente")

    # ── Résumé ─────────────────────────────────────────────────────────────
    if not DRY_RUN:
        cur.execute("SELECT COUNT(*) FROM indices")
        print(f"\n  indices : {cur.fetchone()[0]} lignes")
        cur.execute("SELECT COUNT(*) FROM scores")
        print(f"  scores  : {cur.fetchone()[0]} lignes")

    cur.close()
    conn.close()

    print("\n" + "=" * 60)
    if DRY_RUN:
        print("  Migration simulée — relancer sans --dry-run pour appliquer")
    else:
        print("  ✓ Migration v2 terminée avec succès")
        print("  Pour rollback : ALTER TABLE mesures_old RENAME TO mesures_backup2")
    print("=" * 60)


if __name__ == "__main__":
    run()

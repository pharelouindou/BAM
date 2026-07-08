"""
BAM · Génération de la grille nationale du Bénin.

Crée une grille de points GPS couvrant tout le territoire et les attribue
à leur département. Chaque point devient un candidat "bas-fond" à analyser.

Usage :
  python process/quadrillage.py            # résolution par défaut 0.02° (~2 km)
  python process/quadrillage.py --res 0.1  # résolution 0.1° (plus rapide)
  python process/quadrillage.py --reset    # recrée la grille depuis zéro
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import psycopg2
from dotenv import load_dotenv
load_dotenv()

from process.benin_frontiere import departement_pour_point, est_dans_benin

# ── Bounding box Bénin (WGS84) — enveloppe pour générer la grille, filtre fin via GeoJSON
LAT_MIN, LAT_MAX = 6.2,  12.4
LON_MIN, LON_MAX = 0.8,   3.8

# ── Résolutions disponibles ───────────────────────────────────────────────
# 0.1°  ≈ 11 km  →  ~546  points  (test rapide)
# 0.05° ≈  5 km  → ~2 184 points  (léger)
# 0.02° ≈  2 km  → ~13 640 points (recommandé précision)
# 0.01° ≈  1 km  → ~54 560 points (très lourd)
DEFAULT_RESOLUTION = 0.02


def affecter_departement(lat: float, lon: float) -> str:
    """Attribue un département via les polygones communaux officiels (GeoJSON)."""
    return departement_pour_point(lat, lon)


def generer_grille(resolution: float = DEFAULT_RESOLUTION) -> list[dict]:
    """
    Génère tous les points GPS couvrant le Bénin.
    Retourne une liste de dicts {id_grille, lat, lon, departement}.
    """
    points = []
    lats = np.arange(LAT_MIN, LAT_MAX, resolution)
    lons = np.arange(LON_MIN, LON_MAX, resolution)

    for i, lat in enumerate(lats):
        for j, lon in enumerate(lons):
            lat_r = round(float(lat), 4)
            lon_r = round(float(lon), 4)
            if not est_dans_benin(lat_r, lon_r):
                continue
            dept = affecter_departement(lat_r, lon_r)
            if dept in ("HorsBenin", "Inconnu"):
                continue
            points.append({
                "id_grille":   f"{i:04d}_{j:04d}",
                "lat":         lat_r,
                "lon":         lon_r,
                "departement": dept,
            })

    nb_dept = len({p["departement"] for p in points if p["departement"] != "Inconnu"})
    print(f"Grille générée : {len(points)} points "
          f"({len(lats)} lat × {len(lons)} lon) "
          f"à {resolution}° · {nb_dept} départements couverts")
    return points


def purger_points_hors_benin(cur) -> int:
    """Supprime les points hors polygones communaux (frontière officielle ADM2)."""
    cur.execute("SELECT id_grille, lat::float8, lon::float8 FROM grille_nationale")
    rows = cur.fetchall()
    to_delete = [
        r[0] for r in rows
        if not est_dans_benin(float(r[1]), float(r[2]))
    ]
    if to_delete:
        cur.execute(
            "DELETE FROM grille_nationale WHERE id_grille = ANY(%s)",
            (to_delete,),
        )
    return len(to_delete)


def sauvegarder_grille(points: list[dict], reset: bool = False):
    """Insère la grille dans grille_nationale."""
    conn = psycopg2.connect(os.getenv("DATABASE_URL"))
    cur  = conn.cursor()

    # Créer la table si elle n'existe pas (migration compatible schema.sql)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS grille_nationale (
            id_grille    TEXT PRIMARY KEY,
            lat          NUMERIC(9,6) NOT NULL,
            lon          NUMERIC(9,6) NOT NULL,
            departement  TEXT,
            commune      TEXT,
            arrondissement TEXT,
            localite     TEXT,
            elevation_m  NUMERIC(7,1),
            pente_pct    NUMERIC(6,3),
            twi          NUMERIC(6,3),
            ph_sol       NUMERIC(4,2),
            carbone_g_kg NUMERIC(6,2),
            argile_pct   NUMERIC(5,2),
            pluie_30j_mm NUMERIC(7,2),
            humidite_sol NUMERIC(6,4),
            temp_max_c   NUMERIC(5,2),
            ndwi         NUMERIC(6,4),
            ndvi         NUMERIC(6,4),
            score_eau    NUMERIC(5,1),
            score_total  NUMERIC(5,1),
            est_humide   BOOLEAN DEFAULT FALSE,
            est_bas_fond BOOLEAN DEFAULT FALSE,
            priorite     TEXT,
            source_ndwi  TEXT DEFAULT 'non_collecte',
            date_analyse DATE,
            created_at   TIMESTAMP DEFAULT NOW()
        );
    """)

    # Ajouter les colonnes manquantes si la table existait déjà (migration)
    for col, typ in [
        ("departement",  "TEXT"),
        ("commune",      "TEXT"),
        ("arrondissement","TEXT"),
        ("localite",     "TEXT"),
        ("elevation_m",  "NUMERIC(7,1)"),
        ("pente_pct",    "NUMERIC(6,3)"),
        ("twi",          "NUMERIC(6,3)"),
        ("ph_sol",       "NUMERIC(4,2)"),
        ("carbone_g_kg", "NUMERIC(6,2)"),
        ("argile_pct",   "NUMERIC(5,2)"),
        ("pluie_30j_mm", "NUMERIC(7,2)"),
        ("humidite_sol", "NUMERIC(6,4)"),
        ("temp_max_c",   "NUMERIC(5,2)"),
        ("score_total",  "NUMERIC(5,1)"),
        ("est_bas_fond", "BOOLEAN DEFAULT FALSE"),
        ("priorite",     "TEXT"),
        ("source_ndwi",  "TEXT DEFAULT 'non_collecte'"),
    ]:
        cur.execute(
            f"ALTER TABLE grille_nationale ADD COLUMN IF NOT EXISTS {col} {typ}"
        )

    if reset:
        cur.execute("TRUNCATE grille_nationale")
        print("  Table grille_nationale vidée (reset)")

    inserted = 0
    for p in points:
        cur.execute("""
            INSERT INTO grille_nationale (id_grille, lat, lon, departement)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (id_grille) DO UPDATE SET departement = EXCLUDED.departement
        """, (p["id_grille"], p["lat"], p["lon"], p["departement"]))
        inserted += 1

    # Purge sécurité : supprime d'anciennes lignes hors Bénin
    nb_deleted = purger_points_hors_benin(cur)

    conn.commit()

    # Corriger les anciennes lignes dont le département est NULL (migration)
    cur.execute("SELECT COUNT(*) FROM grille_nationale WHERE departement IS NULL")
    nb_null = cur.fetchone()[0]
    if nb_null:
        cur.execute("""
            SELECT id_grille, lat, lon FROM grille_nationale
            WHERE departement IS NULL
        """)
        null_rows = cur.fetchall()
        for row_id, row_lat, row_lon in null_rows:
            dept = affecter_departement(float(row_lat), float(row_lon))
            cur.execute(
                "UPDATE grille_nationale SET departement = %s WHERE id_grille = %s",
                (dept, row_id),
            )
        conn.commit()
        print(f"  ↳ {nb_null} lignes NULL corrigées (migration)")

    cur.close()
    conn.close()
    print(f"✓ {inserted} points insérés/mis à jour dans grille_nationale")
    if nb_deleted:
        print(f"  ↳ {nb_deleted} points hors Bénin supprimés")


def stats_grille():
    """Affiche les statistiques de la grille par département."""
    conn = psycopg2.connect(os.getenv("DATABASE_URL"))
    cur  = conn.cursor()
    cur.execute("""
        SELECT
            departement,
            COUNT(*) AS nb_points,
            COUNT(*) FILTER (WHERE est_bas_fond = TRUE)  AS bas_fonds,
            COUNT(*) FILTER (WHERE est_humide   = TRUE)  AS humides,
            COUNT(*) FILTER (WHERE date_analyse IS NOT NULL) AS analyses
        FROM grille_nationale
        GROUP BY departement
        ORDER BY departement
    """)
    rows = cur.fetchall()
    cur.close()
    conn.close()

    print(f"\n{'Département':<15} {'Points':>7} {'Bas-fonds':>10} {'Humides':>8} {'Analysés':>9}")
    print("─" * 54)
    for r in rows:
        print(f"  {str(r[0]):<13} {r[1]:>7} {r[2]:>10} {r[3]:>8} {r[4]:>9}")


if __name__ == "__main__":
    res   = DEFAULT_RESOLUTION
    reset = "--reset" in sys.argv

    for i, arg in enumerate(sys.argv):
        if arg == "--res" and i + 1 < len(sys.argv):
            try:
                res = float(sys.argv[i + 1])
            except ValueError:
                pass

    print("=" * 52)
    print(f"  BAM · Grille nationale Bénin · {res}°")
    print("=" * 52)
    grille = generer_grille(res)
    sauvegarder_grille(grille, reset=reset)
    stats_grille()
    print("\n→ Étape suivante : python process/enrichir_grille.py")

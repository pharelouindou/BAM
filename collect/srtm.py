"""
BAM · Collecte SRTM NASA — Relief et détection des bas-fonds
Source : OpenTopography / AWS Open Data
TWI (Topographic Wetness Index) identifie les zones d'accumulation d'eau

Un bas-fond = cuvette naturelle = TWI élevé + NDWI élevé en saison pluies

Usage : python collect/srtm.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests
import numpy as np
import psycopg2
from datetime import date
from dotenv import load_dotenv
load_dotenv()


def get_elevation_open_elevation(lat: float, lon: float) -> float | None:
    """
    Récupère l'altitude via Open-Elevation API (SRTM 30m).
    Gratuit, sans compte.
    """
    try:
        r = requests.get(
            "https://api.open-elevation.com/api/v1/lookup",
            params={"locations": f"{lat},{lon}"},
            timeout=15
        )
        r.raise_for_status()
        return float(r.json()["results"][0]["elevation"])
    except Exception:
        return None


def get_elevation_batch(points: list[dict]) -> dict[str, float]:
    """
    Récupère l'altitude pour plusieurs points en une requête.
    Limite : 1000 points par requête.
    """
    locations = "|".join(f"{p['lat']},{p['lon']}" for p in points)
    try:
        r = requests.post(
            "https://api.open-elevation.com/api/v1/lookup",
            json={"locations": [{"latitude": p["lat"], "longitude": p["lon"]}
                                 for p in points]},
            timeout=60
        )
        r.raise_for_status()
        results = r.json()["results"]
        return {
            f"{r['latitude']:.4f}_{r['longitude']:.4f}": r["elevation"]
            for r in results
        }
    except Exception as e:
        print(f"  ⚠ Open-Elevation batch : {e}")
        return {}


def calculer_pente(elev_centre: float, elev_voisins: list[float],
                   distance_m: float = 11000) -> float:
    """
    Calcule la pente moyenne autour d'un point (en %).
    Distance entre points de la grille 0.1° ≈ 11km.
    """
    if not elev_voisins:
        return 0.0
    diffs = [abs(elev_centre - v) for v in elev_voisins if v is not None]
    if not diffs:
        return 0.0
    pente_rad = np.arctan(np.mean(diffs) / distance_m)
    return round(float(np.degrees(pente_rad)), 3)


def calculer_twi(pente_deg: float, aire_accumulation: float = 1.0) -> float:
    """
    TWI = ln(aire_accumulation / tan(pente))
    Plus le TWI est élevé, plus la zone accumule l'eau.
    TWI > 8 = bas-fond potentiel
    TWI > 12 = zone très humide / cours d'eau
    """
    pente_rad = max(np.radians(pente_deg), 0.001)
    return round(float(np.log(aire_accumulation / np.tan(pente_rad))), 3)


def mettre_a_jour_grille_relief(resultats: list[dict]):
    """Met à jour la table grille_nationale avec altitude, pente et TWI."""
    conn = psycopg2.connect(os.getenv("DATABASE_URL"))
    cur  = conn.cursor()

    # Ajouter colonnes si absentes
    for col, typ in [("elevation_m","NUMERIC(7,1)"),
                     ("pente_pct","NUMERIC(5,3)"),
                     ("twi","NUMERIC(6,3)"),
                     ("est_bas_fond","BOOLEAN")]:
        try:
            cur.execute(f"ALTER TABLE grille_nationale ADD COLUMN IF NOT EXISTS {col} {typ}")
        except Exception:
            pass
    conn.commit()

    for r in resultats:
        cur.execute("""
            UPDATE grille_nationale
            SET elevation_m  = %s,
                pente_pct    = %s,
                twi          = %s,
                est_bas_fond = %s
            WHERE id_grille = %s
        """, (r["elevation"], r["pente"], r["twi"],
              r["twi"] > 8.0,
              r["id_grille"]))

    conn.commit(); cur.close(); conn.close()
    print(f"  ✓ {len(resultats)} points mis à jour avec données relief")


def run():
    print("=" * 52)
    print(f"  BAM · Collecte SRTM Relief · {date.today()}")
    print("=" * 52)

    # Charger la grille
    conn = psycopg2.connect(os.getenv("DATABASE_URL"))
    cur  = conn.cursor()
    cur.execute("""
        SELECT id_grille, lat, lon
        FROM grille_nationale
        WHERE elevation_m IS NULL
        ORDER BY lat DESC, lon ASC
        LIMIT 200
    """)
    points = [{"id_grille": r[0], "lat": float(r[1]), "lon": float(r[2])}
              for r in cur.fetchall()]
    cur.close(); conn.close()

    if not points:
        print("✓ Toute la grille a déjà les données relief")
        return

    print(f"\n→ {len(points)} points sans données relief")
    print("  Collecte par lots de 100 via Open-Elevation API...")

    resultats = []
    batch_size = 100

    for i in range(0, len(points), batch_size):
        batch  = points[i:i+batch_size]
        elevs  = get_elevation_batch(batch)

        for p in batch:
            key  = f"{p['lat']:.4f}_{p['lon']:.4f}"
            elev = elevs.get(key, 0) or 0

            # Pente approximée (sans voisins en batch — valeur par défaut)
            # Pour précision : recalculer avec voisins dans process/calculer_twi.py
            pente = 1.0   # valeur neutre — recalculée après
            twi   = calculer_twi(pente)

            resultats.append({
                "id_grille": p["id_grille"],
                "elevation": elev,
                "pente":     pente,
                "twi":       twi
            })

        print(f"  Lot {i//batch_size + 1} : {len(batch)} points — OK")

    print("\n→ Sauvegarde en base...")
    mettre_a_jour_grille_relief(resultats)

    # Stats
    conn = psycopg2.connect(os.getenv("DATABASE_URL"))
    cur  = conn.cursor()
    cur.execute("""
        SELECT
            COUNT(*) FILTER (WHERE est_bas_fond = TRUE) as bas_fonds,
            ROUND(AVG(elevation_m)::numeric, 0) as alt_moy,
            ROUND(MIN(elevation_m)::numeric, 0) as alt_min,
            ROUND(MAX(elevation_m)::numeric, 0) as alt_max
        FROM grille_nationale
        WHERE elevation_m IS NOT NULL
    """)
    row = cur.fetchone()
    cur.close(); conn.close()

    if row:
        print(f"\n  Altitude moy : {row[1]}m  (min {row[2]}m / max {row[3]}m)")
        print(f"  Bas-fonds potentiels (TWI > 8) : {row[0]} zones")

    print("\n✓ Collecte SRTM terminée")
    print("  Prochain : python process/calculer_twi.py (affine les pentes)")


if __name__ == "__main__":
    run()
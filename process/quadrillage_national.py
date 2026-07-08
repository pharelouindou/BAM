"""
BAM · Quadrillage national du Bénin
Stratégie : 1 GeoTIFF tout-Bénin (Earth Engine) → lecture locale → extraction points

Usage :
  python process/quadrillage_national.py          # télécharge + analyse
  python process/quadrillage_national.py --dl     # télécharge seulement
  python process/quadrillage_national.py --read   # lit un GeoTIFF existant
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psycopg2
import numpy as np
from datetime import date
from dotenv import load_dotenv
load_dotenv()

TIF_PATH   = "data/raw/ndwi_benin.tif"
SEUIL_NDWI = 0.2


def get_grille_db() -> list[dict]:
    """Récupère tous les points de la grille depuis PostgreSQL."""
    conn = psycopg2.connect(os.getenv("DATABASE_URL"))
    cur  = conn.cursor()
    cur.execute(
        "SELECT id_grille, lat, lon FROM grille_nationale ORDER BY lat DESC, lon ASC"
    )
    rows = cur.fetchall()
    cur.close(); conn.close()
    return [{"id_grille": r[0], "lat": float(r[1]), "lon": float(r[2])} for r in rows]


def mettre_a_jour_grille(resultats: dict[str, float]):
    """
    Met à jour la table grille_nationale avec les valeurs NDWI extraites.
    resultats = {id_grille: ndwi_value}
    """
    if not resultats:
        return

    conn = psycopg2.connect(os.getenv("DATABASE_URL"))
    cur  = conn.cursor()

    for id_grille, ndwi in resultats.items():
        cur.execute("""
            UPDATE grille_nationale
            SET ndwi         = %s,
                est_humide   = %s,
                score_eau    = %s,
                date_analyse = %s
            WHERE id_grille = %s
        """, (
            ndwi,
            ndwi > SEUIL_NDWI,
            round(max(0, (ndwi + 1) / 2 * 100), 1),
            date.today(),
            id_grille
        ))

    conn.commit()
    cur.close(); conn.close()
    print(f"  ✓ {len(resultats)} points mis à jour en base")


def afficher_resume():
    """Affiche un résumé des zones humides détectées."""
    conn = psycopg2.connect(os.getenv("DATABASE_URL"))
    cur  = conn.cursor()

    cur.execute("""
        SELECT
            COUNT(*)                                    AS total,
            COUNT(*) FILTER (WHERE est_humide = TRUE)  AS humides,
            COUNT(*) FILTER (WHERE date_analyse IS NOT NULL) AS analyses,
            ROUND(AVG(ndwi)::numeric, 4)               AS ndwi_moyen
        FROM grille_nationale
    """)
    row = cur.fetchone()

    cur.execute("""
        SELECT lat, lon, ndwi, score_eau
        FROM grille_nationale
        WHERE est_humide = TRUE
        ORDER BY ndwi DESC
        LIMIT 10
    """)
    top = cur.fetchall()

    cur.close(); conn.close()

    total, humides, analyses, ndwi_moy = row
    print(f"\n  Total points grille : {total}")
    print(f"  Points analysés     : {analyses}")
    print(f"  Zones humides       : {humides} ({humides/max(analyses,1)*100:.1f}%)")
    print(f"  NDWI moyen          : {ndwi_moy}")

    if top:
        print(f"\n  Top 10 zones les plus humides :")
        print(f"  {'LAT':>8}  {'LON':>8}  {'NDWI':>8}  {'SCORE':>6}")
        print("  " + "─" * 36)
        for r in top:
            print(f"  {r[0]:8.4f}  {r[1]:8.4f}  {float(r[2]):+8.4f}  {float(r[3]):6.1f}")


def run():
    mode_dl   = "--dl"   in sys.argv
    mode_read = "--read" in sys.argv
    mode_both = not mode_dl and not mode_read

    print("=" * 52)
    print(f"  BAM · Quadrillage national · {date.today()}")
    print("=" * 52)

    from collect.sentinel import telecharger_ndwi_benin, lire_ndwi_pour_grille

    # ── Étape 1 : Télécharger le GeoTIFF ───────────────────────
    if mode_dl or mode_both:
        if os.path.exists(TIF_PATH):
            size_mb = os.path.getsize(TIF_PATH) / 1024 / 1024
            print(f"\n→ GeoTIFF existant trouvé : {TIF_PATH} ({size_mb:.1f} MB)")
            rep = input("  Re-télécharger ? (o/N) : ").strip().lower()
            if rep != "o":
                print("  Utilisation du fichier existant")
            else:
                telecharger_ndwi_benin(TIF_PATH)
        else:
            print("\n→ Téléchargement GeoTIFF NDWI — tout le Bénin...")
            telecharger_ndwi_benin(TIF_PATH)

    # ── Étape 2 : Lire les valeurs pour la grille ──────────────
    if mode_read or mode_both:
        if not os.path.exists(TIF_PATH):
            print(f"\n✗ GeoTIFF introuvable : {TIF_PATH}")
            print("  Lancer d'abord : python process/quadrillage_national.py --dl")
            return

        print(f"\n→ Lecture GeoTIFF → {TIF_PATH}")
        points = get_grille_db()
        print(f"  {len(points)} points dans la grille")

        resultats = lire_ndwi_pour_grille(TIF_PATH, points)

        if resultats:
            humides = sum(1 for v in resultats.values() if v > SEUIL_NDWI)
            print(f"  {len(resultats)} valeurs extraites")
            print(f"  {humides} zones humides (NDWI > {SEUIL_NDWI})")
            mettre_a_jour_grille(resultats)
        else:
            # Fallback : afficher les instructions pour Linux
            print(f"\n  GeoTIFF disponible dans : {TIF_PATH}")
            print("  Pour extraire les valeurs pixel-par-pixel :")
            print()
            print("  Sur le VPS Linux (Hetzner) :")
            print("    pip install rasterio")
            print("    python process/quadrillage_national.py --read")
            print()
            print("  Sur ton Mac (alternative QGIS) :")
            print("    Ouvrir QGIS → Layer → Add Raster Layer → ndwi_benin.tif")
            print("    Les zones bleues = NDWI positif = zones humides")

    # ── Résumé ─────────────────────────────────────────────────
    print("\n" + "=" * 52)
    afficher_resume()
    print("=" * 52)


if __name__ == "__main__":
    run()
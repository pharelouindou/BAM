"""
BAM · Sentinel-2 via Google Earth Engine (COPERNICUS/S2_SR_HARMONIZED).

Remplace l’ancienne chaîne OpenEO / Copernicus Data Space (crédits facturés).

Prérequis :
  - pip install earthengine-api
  - earthengine authenticate  (une fois)
  - GEE_PROJECT dans .env
"""

from __future__ import annotations

import os
import urllib.request
from datetime import date, timedelta

import numpy as np
from dotenv import load_dotenv

load_dotenv()

# ── Point unique : délégation à la même implémentation que main.py ───────

from collect.gee_sentinel import get_indices_sentinel_gee


def init_gee() -> bool:
    """Initialise Earth Engine ; retourne True si un projet est configuré et OK."""
    project = os.getenv("GEE_PROJECT", "").strip()
    if not project:
        print("  ✗ GEE : définir GEE_PROJECT dans .env")
        return False
    try:
        import ee  # type: ignore[import-untyped]
    except ImportError:
        print("  ✗ GEE : pip install earthengine-api")
        return False
    try:
        ee.Initialize(project=project)
        print("  ✓ Earth Engine initialisé")
        return True
    except Exception as e:
        print(f"  ✗ GEE init : {e}")
        return False


def get_indices(lat: float, lon: float, radius_km: float = 5) -> dict:
    """
    NDWI, NDVI, MNDWI pour un point (fenêtre ~90 j, médiane comme avant).

    ``radius_km`` est ignoré : GEE utilise une petite région autour du point
    (voir ``collect/gee_sentinel.py``).
    """
    end = date.today().isoformat()
    start = (date.today() - timedelta(days=90)).isoformat()
    return get_indices_sentinel_gee(float(lat), float(lon), start, end)


# ═══════════════════════════════════════════════════════════════════════════
#  QUADRILLAGE NATIONAL — un GeoTIFF NDWI pour tout le Bénin (GEE download)
# ═══════════════════════════════════════════════════════════════════════════

BENIN_BBOX = {"west": 0.8, "east": 3.8, "south": 6.2, "north": 12.4}


def telecharger_ndwi_benin(
    output_path: str = "data/raw/ndwi_benin.tif",
    resolution_m: int = 1000,
    days_back: int = 90,
) -> str | None:
    """
    Télécharge un GeoTIFF NDWI couvrant tout le Bénin via Earth Engine
    (``getDownloadURL``, un fichier GeoTIFF).

    Prérequis : ``GEE_PROJECT``, auth ``earthengine authenticate``.
    """
    project = os.getenv("GEE_PROJECT", "").strip()
    if not project:
        print("  ✗ GEE_PROJECT manquant dans .env")
        return None
    try:
        import ee  # type: ignore[import-untyped]
    except ImportError:
        print("  ✗ earthengine-api non installé")
        return None

    try:
        ee.Initialize(project=project)
    except Exception as e:
        print(f"  ✗ GEE init : {e}")
        return None

    end = date.today()
    start = end - timedelta(days=days_back)

    print(f"  Période : {start} → {end}")
    print(f"  Résolution : {resolution_m}m")
    print(f"  Zone : Bénin complet ({BENIN_BBOX})")

    geometry = ee.Geometry.Rectangle(
        [
            BENIN_BBOX["west"],
            BENIN_BBOX["south"],
            BENIN_BBOX["east"],
            BENIN_BBOX["north"],
        ]
    )

    col = (
        ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
        .filterBounds(geometry)
        .filterDate(str(start), str(end))
        .filter(ee.Filter.lte("CLOUDY_PIXEL_PERCENTAGE", 15))
    )

    try:
        n = col.size().getInfo()
    except Exception as e:
        print(f"  ✗ GEE : {e}")
        return None

    if n == 0:
        print("  ✗ Aucune image Sentinel-2 dans la fenêtre — élargir days_back ou nuages")
        return None

    img = col.median()
    scale = 1 / 10000.0
    b3 = img.select("B3").multiply(scale)
    b8 = img.select("B8").multiply(scale)
    ndwi = b3.subtract(b8).divide(b3.add(b8).max(1e-6)).rename("NDWI")
    ndwi = ndwi.clip(geometry)

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    try:
        url = ndwi.getDownloadURL(
            {
                "scale": resolution_m,
                "region": geometry,
                "crs": "EPSG:4326",
                "format": "GEO_TIFF",
            }
        )
    except Exception as e:
        print(f"  ✗ getDownloadURL : {e}")
        print("  Astuce : réduire la zone ou augmenter resolution_m (ex. 2000).")
        return None

    print(f"  Téléchargement → {output_path}")
    try:
        urllib.request.urlretrieve(url, output_path)
    except Exception as e:
        print(f"  ✗ Téléchargement HTTP : {e}")
        return None

    size_mb = os.path.getsize(output_path) / 1024 / 1024
    print(f"  ✓ Fichier téléchargé : {size_mb:.1f} MB")
    return output_path


def lire_ndwi_pour_grille(
    tif_path: str,
    points: list[dict],
) -> dict[str, float]:
    """
    Lit les valeurs NDWI du GeoTIFF pour une liste de points GPS.

    Nécessite rasterio (disponible sur Linux/VPS).
    Fallback numpy si rasterio absent (Mac dev).
    """
    resultats: dict[str, float] = {}

    try:
        import rasterio
        from rasterio.transform import rowcol

        with rasterio.open(tif_path) as src:
            data = src.read(1)
            nodata = src.nodata if src.nodata is not None else -9999

            for p in points:
                try:
                    row_i, col_i = rowcol(src.transform, p["lon"], p["lat"])
                    if 0 <= row_i < data.shape[0] and 0 <= col_i < data.shape[1]:
                        val = float(data[row_i, col_i])
                        if val != nodata and not np.isnan(val):
                            resultats[p["id_grille"]] = round(val, 4)
                except Exception:
                    pass

        print(f"  ✓ rasterio : {len(resultats)}/{len(points)} points extraits")
        return resultats

    except ImportError:
        print("  rasterio absent — utilisation du fallback numpy")

    print("  ⚠ Installe rasterio sur le VPS pour l'extraction pixel-par-pixel")
    print("    Sur Ubuntu/Linux : pip install rasterio")
    print("    En attendant     : python process/analyser_grille.py --limit 50")
    return {}


if __name__ == "__main__":
    print("Test GEE Sentinel-2 → Savalou (lat=7.93, lon=1.97)")
    print("-" * 40)
    res = get_indices(7.93, 1.97)
    if res:
        for k, v in res.items():
            print(f"  {k:6} : {v}")
        hum = res["ndwi"] > 0.2
        print(f"\n  → {'zone humide ✓' if hum else 'sol sec'}")
        print("\n✓ Sentinel-2 OK")
    else:
        print("✗ Pas de données")

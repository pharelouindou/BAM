"""
BAM · Sentinel-2 (COPERNICUS/S2_SR_HARMONIZED) via Google Earth Engine.

Retourne NDWI, NDVI, MNDWI pour un point, avec médiane temporelle sur la fenêtre.
Clé de source attendue : "Sentinel-2-GEE".

Prérequis :
  - pip install earthengine-api
  - Local : earthengine authenticate (une fois)
  - Render / VPS : variable GEE_SERVICE_ACCOUNT_JSON (contenu JSON du compte de service)
  - GEE_PROJECT dans .env
"""

from __future__ import annotations

import os
from datetime import date, timedelta

from dotenv import load_dotenv

load_dotenv()

SOURCE_KEY = "Sentinel-2-GEE"


def _init_gee(ee, project: str) -> bool:
    """
    Initialise Earth Engine.

    Priorité :
      1. GEE_SERVICE_ACCOUNT_JSON (variable d'env) → compte de service
         Utilisé sur Render / VPS (pas d'auth interactive possible).
         Voir docs/gee_service_account.md pour la procédure de création.
      2. Authentification locale standard (earthengine authenticate).
    Retourne True si succès, False sinon.
    """
    import json
    import tempfile

    sa_json_str = os.getenv("GEE_SERVICE_ACCOUNT_JSON", "").strip()
    if sa_json_str:
        try:
            sa_data = json.loads(sa_json_str)
            sa_email = sa_data.get("client_email", "")
            # Écrire le JSON dans un fichier temporaire (requis par l'API ee)
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".json", delete=False
            ) as f:
                json.dump(sa_data, f)
                key_file = f.name
            credentials = ee.ServiceAccountCredentials(sa_email, key_file)
            ee.Initialize(credentials, project=project)
            return True
        except Exception as e:
            print(f"  GEE service account : {e}")
            return False

    # Auth locale (développement)
    try:
        ee.Initialize(project=project)
        return True
    except Exception as e:
        print(f"  GEE init : {e}")
        return False


def get_indices_sentinel_gee(
    lat: float,
    lon: float,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict:
    """
    Retourne {"ndwi", "ndvi", "mndwi"} ou {} si échec (pas de projet, pas d'auth, pas d'image).
    """
    project = os.getenv("GEE_PROJECT", "").strip()
    if not project:
        return {}

    try:
        import ee  # type: ignore[import-untyped]
    except ImportError:
        print("  GEE : package earthengine-api non installé")
        return {}

    if not _init_gee(ee, project):
        return {}

    end = end_date or date.today().isoformat()
    start = start_date or (date.today() - timedelta(days=60)).isoformat()

    lat, lon = float(lat), float(lon)
    point = ee.Geometry.Point([lon, lat])
    region = point.buffer(100)  # ~100 m pour moyenne stable

    col = (
        ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
        .filterBounds(point)
        .filterDate(start, end)
        .filter(ee.Filter.lte("CLOUDY_PIXEL_PERCENTAGE", 40))
    )
    try:
        n_img = col.size().getInfo()
    except Exception as e:
        print(f"  GEE : {e}")
        return {}

    if n_img == 0:
        print("  GEE : aucune image Sentinel-2 dans la fenêtre")
        return {}

    img = col.median()
    scale = 1 / 10000.0
    b3 = img.select("B3").multiply(scale)
    b4 = img.select("B4").multiply(scale)
    b8 = img.select("B8").multiply(scale)
    b11 = img.select("B11").multiply(scale)

    ndwi = b3.subtract(b8).divide(b3.add(b8).max(1e-6))
    ndvi = b8.subtract(b4).divide(b8.add(b4).max(1e-6))
    mndwi = b3.subtract(b11).divide(b3.add(b11).max(1e-6))

    stack = ee.Image.cat([ndwi, ndvi, mndwi]).rename(["ndwi", "ndvi", "mndwi"])

    try:
        stat = stack.reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=region,
            scale=20,
            maxPixels=1e9,
        ).getInfo()
    except Exception as e:
        print(f"  GEE reduceRegion : {e}")
        return {}

    if not stat:
        return {}
    try:
        out = {
            "ndwi":  round(float(stat["ndwi"]), 4),
            "ndvi":  round(float(stat["ndvi"]), 4),
            "mndwi": round(float(stat["mndwi"]), 4),
        }
        print(f"  ✓ GEE Sentinel-2 : NDWI={out['ndwi']}")
        return out
    except (KeyError, TypeError, ValueError):
        return {}


if __name__ == "__main__":
    r = get_indices_sentinel_gee(7.93, 1.97)
    print(r)

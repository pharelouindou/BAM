"""
BAM · Précipitations GPM via NASA Earthdata (sans GEE).

Stratégie :
  1. NASA GPM OPeNDAP — données IMERG journalières directes.
     Nécessite NASA_USERNAME + NASA_PASSWORD dans .env.
  2. Fallback : Open-Meteo archive ERA5 (sans compte, toujours disponible).

Références :
  - GPM IMERG : https://gpm.nasa.gov/data/imerg
  - OPeNDAP   : https://disc.gsfc.nasa.gov/information/tools?title=OPeNDAP
  - Open-Meteo: https://open-meteo.com/en/docs/historical-weather-api
"""

import os
import requests
from datetime import date, timedelta, datetime
from dotenv import load_dotenv

load_dotenv()

TIMEOUT        = 30
GPM_OPENDAP   = "https://gpm1.gesdisc.eosdis.nasa.gov/opendap"
OPENMETEO_URL = "https://archive-api.open-meteo.com/v1/archive"


# ── Source 1 : NASA GPM OPeNDAP ──────────────────────────────────────────

def _gpm_opendap(lat: float, lon: float, start: str, end: str) -> dict:
    """
    Récupère le cumul de pluie sur la période via l'API GPM OPeNDAP.
    Utilise l'endpoint JSON (NcML/DAP4) pour un point GPS.
    """
    username = os.getenv("NASA_USERNAME")
    password = os.getenv("NASA_PASSWORD")
    if not username or not password:
        return {}

    try:
        start_d = datetime.strptime(start, "%Y-%m-%d").date()
        end_d   = datetime.strptime(end,   "%Y-%m-%d").date()
        total   = 0.0
        found   = 0

        current = start_d
        while current <= end_d:
            yyyy  = current.strftime("%Y")
            doy   = current.strftime("%j")
            ymd   = current.strftime("%Y%m%d")

            # URL fichier journalier IMERG Late Run (V07)
            url = (
                f"{GPM_OPENDAP}/GPM_L3/GPM_3IMERGDL.07/{yyyy}/{doy}/"
                f"3B-DAY-L.MS.MRG.3IMERG.{ymd}-S000000-E235959.V07.nc4.nc4"
                f"?precipitationCal[0:0][{_lon_idx(lon)}:{_lon_idx(lon)}][{_lat_idx(lat)}:{_lat_idx(lat)}]"
            )

            r = requests.get(url, auth=(username, password), timeout=TIMEOUT)
            if r.status_code == 200:
                try:
                    data = r.json()
                    val  = _extract_opendap_val(data, "precipitationCal")
                    if val is not None and val >= 0:
                        total += val
                        found += 1
                except Exception:
                    pass

            current += timedelta(days=1)

        if found == 0:
            return {}

        return {"pluie_30j_mm": round(total, 2)}

    except Exception as e:
        print(f"  GPM OPeNDAP : {e}")
        return {}


def _lon_idx(lon: float) -> int:
    """Convertit longitude en index IMERG (résolution 0.1°, -180 à +180)."""
    return int((lon + 180.0) / 0.1)


def _lat_idx(lat: float) -> int:
    """Convertit latitude en index IMERG (résolution 0.1°, -90 à +90)."""
    return int((lat + 90.0) / 0.1)


def _extract_opendap_val(data: dict, key: str) -> float | None:
    """Extrait la valeur depuis la réponse JSON OPeNDAP."""
    try:
        arr = data.get(key, {}).get("data", [[[[]]]])
        val = arr[0][0][0][0] if isinstance(arr, list) else None
        return float(val) if val is not None else None
    except (IndexError, TypeError, ValueError):
        return None


# ── Source 2 : Open-Meteo archive ERA5 (sans compte) ─────────────────────

def _openmeteo_archive(lat: float, lon: float, start: str, end: str) -> dict:
    """
    Récupère les précipitations historiques ERA5 via Open-Meteo archive.
    Sans compte, gratuit, toujours disponible (données jusqu'à J-5).
    """
    try:
        r = requests.get(
            OPENMETEO_URL,
            params={
                "latitude":   lat,
                "longitude":  lon,
                "start_date": start,
                "end_date":   end,
                "daily":      "precipitation_sum",
                "timezone":   "Africa/Porto-Novo",
            },
            timeout=TIMEOUT,
        )
        r.raise_for_status()
        data = r.json()
        vals = data.get("daily", {}).get("precipitation_sum", [])
        total = sum(float(v) for v in vals if v is not None)
        return {"pluie_30j_mm": round(total, 2)}
    except Exception as e:
        print(f"  Open-Meteo archive : {e}")
        return {}


# ── Point d'entrée public ────────────────────────────────────────────────

def get_precip_gpm(
    lat: float,
    lon: float,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict:
    """
    Retourne {"pluie_30j_mm": ...} depuis NASA GPM ou fallback ERA5.

    Essaie GPM OPeNDAP en premier (si NASA_USERNAME/PASSWORD dispo),
    puis Open-Meteo ERA5 (sans compte).
    Retourne {} si toutes les sources échouent.

    Args :
        lat, lon       : coordonnées GPS
        start_date     : YYYY-MM-DD (défaut : J-30)
        end_date       : YYYY-MM-DD (défaut : aujourd'hui)
    """
    lat = float(lat)
    lon = float(lon)
    end_date   = end_date   or date.today().isoformat()
    start_date = start_date or (date.today() - timedelta(days=30)).isoformat()

    result = _gpm_opendap(lat, lon, start_date, end_date)
    if result:
        print(f"  ✓ GPM OPeNDAP : {result.get('pluie_30j_mm')} mm/30j")
        return result

    result = _openmeteo_archive(lat, lon, start_date, end_date)
    if result:
        print(f"  ✓ ERA5 archive : {result.get('pluie_30j_mm')} mm/30j")
        return result

    print("  ✗ GPM : toutes les sources indisponibles")
    return {}


if __name__ == "__main__":
    print("Test GPM → Savalou (lat=7.93, lon=1.97)")
    print("-" * 40)
    r = get_precip_gpm(7.93, 1.97)
    if r:
        print(f"  Pluie 30j : {r.get('pluie_30j_mm')} mm")
        print("\n✓ GPM OK")
    else:
        print("✗ Pas de données")

"""
BAM · Précipitations historiques CHIRPS / ERA5.

Stratégie :
  1. Open-Meteo forecast (pluie 7j + 30j récents) — rapide, fiable.
  2. Open-Meteo archive ERA5 (historique exact) — fallback.

Note : ClimateSERV désactivé (erreurs 500 systématiques côté serveur SERVIR).

Références :
  - Open-Meteo forecast : https://open-meteo.com/en/docs
  - Open-Meteo archive  : https://open-meteo.com/en/docs/historical-weather-api
"""

import requests
from datetime import date, timedelta

TIMEOUT_FORECAST = 15
TIMEOUT_ARCHIVE  = 25
OPENMETEO_FORECAST = "https://api.open-meteo.com/v1/forecast"
OPENMETEO_ARCHIVE  = "https://archive-api.open-meteo.com/v1/archive"


# ── Source 1 : Open-Meteo forecast (pluie récente 30j) ───────────────────

def _openmeteo_forecast(lat: float, lon: float) -> dict:
    """Cumul pluie 30 derniers jours via Open-Meteo forecast (past_days)."""
    try:
        r = requests.get(
            OPENMETEO_FORECAST,
            params={
                "latitude":   lat,
                "longitude":  lon,
                "daily":      "precipitation_sum",
                "past_days":  30,
                "forecast_days": 0,
                "timezone":   "Africa/Porto-Novo",
            },
            timeout=TIMEOUT_FORECAST,
        )
        r.raise_for_status()
        vals = r.json().get("daily", {}).get("precipitation_sum", [])
        total = sum(float(v) for v in vals if v is not None)
        return {"pluie_30j_mm": round(total, 2), "source_pluie": "Open-Meteo"}
    except Exception as e:
        print(f"  Open-Meteo forecast : {e}")
        return {}


# ── Source 2 : Open-Meteo archive ERA5 (historique exact) ────────────────

def _openmeteo_archive(lat: float, lon: float) -> dict:
    """Cumul pluie 30j via ERA5 historique — fallback si forecast indisponible."""
    try:
        end_date   = (date.today() - timedelta(days=5)).isoformat()  # ERA5 dispo J-5
        start_date = (date.today() - timedelta(days=35)).isoformat()
        r = requests.get(
            OPENMETEO_ARCHIVE,
            params={
                "latitude":   lat,
                "longitude":  lon,
                "start_date": start_date,
                "end_date":   end_date,
                "daily":      "precipitation_sum",
                "timezone":   "Africa/Porto-Novo",
            },
            timeout=TIMEOUT_ARCHIVE,
        )
        r.raise_for_status()
        vals = r.json().get("daily", {}).get("precipitation_sum", [])
        total = sum(float(v) for v in vals if v is not None)
        return {"pluie_30j_mm": round(total, 2), "source_pluie": "ERA5"}
    except Exception as e:
        print(f"  Open-Meteo ERA5 : {e}")
        return {}


# ── Point d'entrée public ────────────────────────────────────────────────

def get_pluie_30j(lat: float, lon: float) -> dict:
    """
    Retourne {"pluie_30j_mm": ..., "source_pluie": ...}.

    Essaie Open-Meteo forecast en premier (rapide),
    puis ERA5 archive en fallback.
    Retourne {"pluie_30j_mm": None} si tout échoue.
    """
    lat = float(lat)
    lon = float(lon)

    result = _openmeteo_forecast(lat, lon)
    if result and result.get("pluie_30j_mm") is not None:
        return result

    result = _openmeteo_archive(lat, lon)
    if result and result.get("pluie_30j_mm") is not None:
        print(f"  ✓ ERA5 (fallback) : {result.get('pluie_30j_mm')} mm/30j")
        return result

    print("  ✗ Pluie 30j : toutes les sources indisponibles")
    return {"pluie_30j_mm": None}


if __name__ == "__main__":
    print("Test pluie 30j → Savalou (lat=7.93, lon=1.97)")
    print("-" * 40)
    r = get_pluie_30j(7.93, 1.97)
    print(f"  Pluie 30j : {r.get('pluie_30j_mm')} mm")
    print(f"  Source    : {r.get('source_pluie', '—')}")
    print("\n✓ OK" if r.get("pluie_30j_mm") is not None else "✗ Echec")

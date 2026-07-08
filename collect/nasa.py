"""
BAM · Indices satellites (NDWI, NDVI, MNDWI) via NASA Earthdata.

Stratégie :
  1. AppEEARS (NASA) — extraction point MODIS MOD09GA (bandes brutes).
     Nécessite NASA_USERNAME + NASA_PASSWORD dans .env.
  2. Fallback : ORNL MODIS REST API — sans compte, gratuit.
  3. Fallback final : valeurs vides {}.

Références :
  - AppEEARS : https://appeears.earthdatacloud.nasa.gov/api
  - ORNL : https://modis.ornl.gov/rst/api/v1
"""

import os
import time
import requests
from datetime import date, timedelta
from dotenv import load_dotenv

load_dotenv()

APPEEARS_BASE = "https://appeears.earthdatacloud.nasa.gov/api"
ORNL_BASE     = "https://modis.ornl.gov/rst/api/v1"
TIMEOUT       = 30


# ── Helpers ─────────────────────────────────────────────────────────────

def _norm_diff(a: float, b: float) -> float:
    """(a - b) / (a + b), retourne 0 si division impossible."""
    denom = a + b
    if abs(denom) < 1e-9:
        return 0.0
    return round((a - b) / denom, 4)


def _ornl_band(product: str, band: str, lat: float, lon: float,
               start: str, end: str) -> float | None:
    """
    Récupère la valeur moyenne d'une bande MODIS via ORNL REST.
    start / end au format YYYY-MM-DD.
    """
    try:
        url = f"{ORNL_BASE}/{product}/subset"
        params = {
            "latitude":  lat,
            "longitude": lon,
            "band":      band,
            "startDate": start.replace("-", "-"),
            "endDate":   end.replace("-", "-"),
            "kmAboveBelow": 0,
            "kmLeftRight":  0,
        }
        r = requests.get(url, params=params, timeout=TIMEOUT)
        r.raise_for_status()
        data = r.json()
        vals = []
        for subset in data.get("subset", []):
            for v in subset.get("data", []):
                try:
                    fv = float(v)
                    if -3000 < fv < 10000:   # filtre fill-value MODIS
                        vals.append(fv)
                except (TypeError, ValueError):
                    pass
        if not vals:
            return None
        return sum(vals) / len(vals)
    except Exception:
        return None


# ── Source 1 : AppEEARS (avec compte NASA) ───────────────────────────────

def _fmt_appeears_date(iso: str) -> str:
    """Convertit YYYY-MM-DD → MM-DD-YYYY (format attendu par AppEEARS)."""
    y, m, d = iso.split("-")
    return f"{m}-{d}-{y}"


def _appeears_indices(lat: float, lon: float, start: str, end: str) -> dict:
    """Tente d'utiliser AppEEARS si les credentials NASA sont disponibles."""
    username = os.getenv("NASA_USERNAME")
    password = os.getenv("NASA_PASSWORD")
    if not username or not password:
        return {}

    try:
        # Authentification token
        r = requests.post(
            f"{APPEEARS_BASE}/login",
            auth=(username, password),
            timeout=TIMEOUT,
        )
        r.raise_for_status()
        token = r.json().get("token", "")
        if not token:
            return {}

        headers = {"Authorization": f"Bearer {token}"}

        # AppEEARS exige le format MM-DD-YYYY
        start_fmt = _fmt_appeears_date(start)
        end_fmt   = _fmt_appeears_date(end)

        # Nom de tâche : lettres/chiffres/tirets uniquement
        task_name = f"bam-{str(lat).replace('.', 'p')}-{str(lon).replace('.', 'p')}"

        # Soumettre une tâche point
        task = {
            "task_type": "point",
            "task_name": task_name,
            "params": {
                "dates": [{"startDate": start_fmt, "endDate": end_fmt}],
                "layers": [
                    {"product": "MOD09GA.061", "layer": "sur_refl_b01_1"},  # rouge
                    {"product": "MOD09GA.061", "layer": "sur_refl_b02_1"},  # NIR
                    {"product": "MOD09GA.061", "layer": "sur_refl_b04_1"},  # vert
                    {"product": "MOD09GA.061", "layer": "sur_refl_b06_1"},  # SWIR
                ],
                "coordinates": [{"latitude": str(lat), "longitude": str(lon), "id": "p1", "category": ""}],
                # AppEEARS retourne un CSV (pas JSON) pour les tâches point
                "output": {"format": {"type": "csv"}, "projection": "geographic"},
            },
        }
        rt = requests.post(
            f"{APPEEARS_BASE}/task", json=task, headers=headers, timeout=TIMEOUT
        )
        rt.raise_for_status()
        task_id = rt.json().get("task_id", "")
        if not task_id:
            return {}

        # Attendre completion (max 240 s — AppEEARS prend souvent 2-3 min)
        completed = False
        for _ in range(24):
            time.sleep(10)
            rs = requests.get(
                f"{APPEEARS_BASE}/task/{task_id}", headers=headers, timeout=TIMEOUT
            )
            if rs.json().get("status") == "done":
                completed = True
                break

        if not completed:
            requests.delete(
                f"{APPEEARS_BASE}/task/{task_id}", headers=headers, timeout=TIMEOUT
            )
            return {}

        # Récupérer la liste des fichiers du bundle
        rd = requests.get(
            f"{APPEEARS_BASE}/bundle/{task_id}", headers=headers, timeout=TIMEOUT
        )
        rd.raise_for_status()
        files = rd.json().get("files", [])

        # Trouver le fichier CSV de résultats (contient "-results.csv")
        csv_file = next(
            (f for f in files if f.get("file_name", "").endswith("-results.csv")),
            None,
        )
        if not csv_file:
            return {}

        rc = requests.get(
            f"{APPEEARS_BASE}/bundle/{task_id}/{csv_file['file_id']}",
            headers=headers, timeout=60,
        )
        rc.raise_for_status()

        # Parser le CSV — colonnes : MOD09GA_061_sur_refl_b01_1, etc.
        import csv, io
        reader = csv.DictReader(io.StringIO(rc.text))
        col_b01 = "MOD09GA_061_sur_refl_b01_1"
        col_b02 = "MOD09GA_061_sur_refl_b02_1"
        col_b04 = "MOD09GA_061_sur_refl_b04_1"
        col_b06 = "MOD09GA_061_sur_refl_b06_1"

        bands: dict[str, list[float]] = {col_b01: [], col_b02: [], col_b04: [], col_b06: []}
        for row in reader:
            for col in bands:
                val = row.get(col)
                if val is not None:
                    try:
                        fv = float(val)
                        if -3000 < fv < 10000:
                            bands[col].append(fv)
                    except (TypeError, ValueError):
                        pass

        def mean(lst): return sum(lst) / len(lst) if lst else None

        red   = mean(bands[col_b01])
        nir   = mean(bands[col_b02])
        green = mean(bands[col_b04])
        swir  = mean(bands[col_b06])

        if any(v is None for v in [red, nir, green, swir]):
            return {}

        return {
            "ndwi":  _norm_diff(green, nir),
            "ndvi":  _norm_diff(nir, red),
            "mndwi": _norm_diff(green, swir),
        }

    except Exception as e:
        print(f"  AppEEARS : {e}")
        return {}


# ── Source 2 : ORNL MODIS REST (sans compte) ─────────────────────────────

def _ornl_indices(lat: float, lon: float, start: str, end: str) -> dict:
    """Calcule NDWI/NDVI/MNDWI depuis ORNL MODIS MOD09GA (sans compte)."""
    try:
        red   = _ornl_band("MOD09GA", "sur_refl_b01", lat, lon, start, end)
        nir   = _ornl_band("MOD09GA", "sur_refl_b02", lat, lon, start, end)
        green = _ornl_band("MOD09GA", "sur_refl_b04", lat, lon, start, end)
        swir  = _ornl_band("MOD09GA", "sur_refl_b06", lat, lon, start, end)

        if any(v is None for v in [red, nir, green, swir]):
            return {}

        return {
            "ndwi":  _norm_diff(green, nir),
            "ndvi":  _norm_diff(nir, red),
            "mndwi": _norm_diff(green, swir),
        }
    except Exception as e:
        print(f"  ORNL MODIS : {e}")
        return {}


# ── Point d'entrée public ────────────────────────────────────────────────

def collect_nasa_all_sources(
    lat: float,
    lon: float,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict[str, dict]:
    """
    Tente AppEEARS et ORNL indépendamment. Retourne
    {"AppEEARS": {...}, "ORNL": {...}} pour chaque source qui a réussi.

    Permet de stocker plusieurs jeux d'indices le même jour (clés source distinctes).
    """
    lat = float(lat)
    lon = float(lon)
    end_date   = end_date   or date.today().isoformat()
    start_date = start_date or (date.today() - timedelta(days=30)).isoformat()

    out: dict[str, dict] = {}
    a = _appeears_indices(lat, lon, start_date, end_date)
    if a:
        print(f"  ✓ NASA AppEEARS : NDWI={a.get('ndwi')}")
        out["AppEEARS"] = a
    o = _ornl_indices(lat, lon, start_date, end_date)
    if o:
        print(f"  ✓ ORNL MODIS : NDWI={o.get('ndwi')}")
        out["ORNL"] = o
    if not out:
        print("  ✗ NASA : AppEEARS et ORNL indisponibles")
    return out


def collect_nasa(
    lat: float,
    lon: float,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict:
    """
    Retourne un seul jeu d'indices (rétrocompatibilité) : AppEEARS, sinon ORNL.

    Pour le multi-source, utiliser `collect_nasa_all_sources`.
    """
    by_src = collect_nasa_all_sources(lat, lon, start_date, end_date)
    if "AppEEARS" in by_src:
        return by_src["AppEEARS"]
    if "ORNL" in by_src:
        return by_src["ORNL"]
    return {}


if __name__ == "__main__":
    print("Test NASA → Savalou (lat=7.93, lon=1.97)")
    print("-" * 40)
    r = collect_nasa(7.93, 1.97)
    if r:
        for k, v in r.items():
            print(f"  {k} : {v}")
        print("\n✓ NASA OK")
    else:
        print("✗ Pas de données")

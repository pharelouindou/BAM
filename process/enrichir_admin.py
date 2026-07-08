"""
BAM · Enrichissement administratif depuis lat/lon (reverse geocoding).

Remplit les colonnes `commune`, `arrondissement`, `localite` de `grille_nationale`
à partir de Nominatim (OpenStreetMap), avec filtre département optionnel.

Usage :
  python process/enrichir_admin.py --dept "Alibori"
  python process/enrichir_admin.py --dept "Atlantique" --limit 200
"""

from __future__ import annotations

import os
import sys
import time

import psycopg2
import requests
from dotenv import load_dotenv

load_dotenv()

NOMINATIM_URL = "https://nominatim.openstreetmap.org/reverse"
UA = "BeninAquaMap/1.0 (contact: bam-local)"


def _parse_args() -> tuple[str | None, int | None]:
    dept: str | None = None
    limit: int | None = None
    for i, arg in enumerate(sys.argv):
        if arg == "--dept" and i + 1 < len(sys.argv):
            dept = sys.argv[i + 1]
        if arg == "--limit" and i + 1 < len(sys.argv):
            limit = int(sys.argv[i + 1])
    return dept, limit


def get_points(dept: str | None, limit: int | None) -> list[tuple[str, float, float]]:
    conn = psycopg2.connect(os.getenv("DATABASE_URL"))
    cur = conn.cursor()

    sql = """
        SELECT id_grille, lat::float8, lon::float8
        FROM grille_nationale
        WHERE (commune IS NULL OR arrondissement IS NULL OR localite IS NULL)
    """
    params: list = []
    if dept:
        sql += " AND departement = %s"
        params.append(dept)
    sql += " ORDER BY lat DESC, lon ASC"
    if limit:
        sql += " LIMIT %s"
        params.append(limit)

    cur.execute(sql, tuple(params))
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows


def reverse_admin(lat: float, lon: float) -> tuple[str | None, str | None, str | None]:
    try:
        r = requests.get(
            NOMINATIM_URL,
            params={
                "format": "jsonv2",
                "lat": lat,
                "lon": lon,
                "addressdetails": 1,
                "zoom": 16,
                "accept-language": "fr",
            },
            headers={"User-Agent": UA},
            timeout=25,
        )
        r.raise_for_status()
        payload = r.json()
        data = payload.get("address", {})
    except Exception:
        return None, None, None

    # Garde-fou frontière : on n'accepte que les réponses côté Bénin.
    country_code = (data.get("country_code") or payload.get("address", {}).get("country_code") or "").lower()
    country_name = (data.get("country") or "").strip().lower()
    if country_code != "bj" and country_name not in {"benin", "bénin", "republic of benin", "république du bénin"}:
        return None, None, None

    commune = (
        data.get("municipality")
        or data.get("city")
        or data.get("town")
        or data.get("county")
    )
    arrondissement = data.get("suburb") or data.get("city_district") or data.get("district")
    localite = (
        data.get("village")
        or data.get("hamlet")
        or data.get("neighbourhood")
        or data.get("quarter")
        or data.get("city")
        or data.get("town")
    )
    return commune, arrondissement, localite


def update_point(id_grille: str, commune: str | None, arrondissement: str | None, localite: str | None) -> None:
    conn = psycopg2.connect(os.getenv("DATABASE_URL"))
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE grille_nationale
        SET commune = COALESCE(%s, commune),
            arrondissement = COALESCE(%s, arrondissement),
            localite = COALESCE(%s, localite)
        WHERE id_grille = %s
        """,
        (commune, arrondissement, localite, id_grille),
    )
    conn.commit()
    cur.close()
    conn.close()


def run() -> None:
    dept, limit = _parse_args()
    points = get_points(dept, limit)
    print(f"{len(points)} points à enrichir administrativement")
    if not points:
        return

    ok = 0
    for i, (pid, lat, lon) in enumerate(points, 1):
        commune, arr, loc = reverse_admin(lat, lon)
        update_point(pid, commune, arr, loc)
        ok += 1
        if i % 50 == 0:
            print(f"  {i}/{len(points)}")
        # Nominatim demande une cadence limitée
        time.sleep(1.0)

    print(f"✓ {ok}/{len(points)} points mis à jour")


if __name__ == "__main__":
    run()


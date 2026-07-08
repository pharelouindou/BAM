"""
BAM · Enrichissement des communes depuis GeoJSON (point dans polygone).

Usage:
  python process/enrichir_communes_geojson.py --dept Alibori
  python process/enrichir_communes_geojson.py --dept Alibori --geojson data/raw/geoBoundaries-BEN-ADM2.geojson
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

load_dotenv()

DEFAULT_GEOJSON = "data/raw/geoBoundaries-BEN-ADM2.geojson"

# Communes officielles par departement (minimum utile ici: Alibori)
DEPT_COMMUNES: dict[str, set[str]] = {
    "Alibori": {"Banikoara", "Gogounou", "Kandi", "Karimama", "Malanville", "Segbana"},
}


def _parse_args() -> tuple[str | None, str]:
    dept = None
    geojson_path = DEFAULT_GEOJSON
    for i, arg in enumerate(sys.argv):
        if arg == "--dept" and i + 1 < len(sys.argv):
            dept = sys.argv[i + 1]
        if arg == "--geojson" and i + 1 < len(sys.argv):
            geojson_path = sys.argv[i + 1]
    return dept, geojson_path


def point_in_ring(lat: float, lon: float, ring: list[list[float]]) -> bool:
    x, y = lon, lat
    inside = False
    j = len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i][0], ring[i][1]
        xj, yj = ring[j][0], ring[j][1]
        intersects = ((yi > y) != (yj > y)) and (
            x < (xj - xi) * (y - yi) / ((yj - yi) + 1e-12) + xi
        )
        if intersects:
            inside = not inside
        j = i
    return inside


def point_in_polygon_geometry(lat: float, lon: float, geom: dict[str, Any]) -> bool:
    gtype = geom.get("type")
    coords = geom.get("coordinates", [])

    if gtype == "Polygon":
        if not coords:
            return False
        if not point_in_ring(lat, lon, coords[0]):
            return False
        for hole in coords[1:]:
            if point_in_ring(lat, lon, hole):
                return False
        return True

    if gtype == "MultiPolygon":
        for poly in coords:
            if not poly:
                continue
            if not point_in_ring(lat, lon, poly[0]):
                continue
            in_hole = any(point_in_ring(lat, lon, hole) for hole in poly[1:])
            if not in_hole:
                return True
        return False

    return False


def _bbox_from_geometry(geom: dict[str, Any]) -> tuple[float, float, float, float]:
    """BBox (lon_min, lat_min, lon_max, lat_max) pour pré-filtre rapide."""
    lon_min = lat_min = float("inf")
    lon_max = lat_max = float("-inf")

    def walk(coords: Any) -> None:
        nonlocal lon_min, lat_min, lon_max, lat_max
        if not coords:
            return
        if isinstance(coords[0], (int, float)):
            lon, lat = float(coords[0]), float(coords[1])
            lon_min = min(lon_min, lon)
            lon_max = max(lon_max, lon)
            lat_min = min(lat_min, lat)
            lat_max = max(lat_max, lat)
            return
        for part in coords:
            walk(part)

    walk(geom.get("coordinates", []))
    return lon_min, lat_min, lon_max, lat_max


def load_commune_geometries(path: str, dept: str | None) -> list[tuple[str, dict[str, Any], tuple[float, float, float, float]]]:
    with open(path, "r", encoding="utf-8") as f:
        gj = json.load(f)

    allowed = DEPT_COMMUNES.get(dept) if dept else None
    out: list[tuple[str, dict[str, Any], tuple[float, float, float, float]]] = []
    for ft in gj.get("features", []):
        props = ft.get("properties", {})
        name = props.get("shapeName")
        geom = ft.get("geometry")
        if not name or not geom:
            continue
        if allowed is not None and name not in allowed:
            continue
        out.append((name, geom, _bbox_from_geometry(geom)))
    return out


def get_points(dept: str | None) -> list[tuple[str, float, float]]:
    conn = psycopg2.connect(os.getenv("DATABASE_URL"))
    cur = conn.cursor()
    sql = "SELECT id_grille, lat::float8, lon::float8 FROM grille_nationale"
    params: list[Any] = []
    if dept:
        sql += " WHERE departement = %s"
        params.append(dept)
    sql += " ORDER BY lat DESC, lon ASC"
    cur.execute(sql, params)
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows


def update_commune(updates: list[tuple[str, str | None]]) -> None:
    conn = psycopg2.connect(os.getenv("DATABASE_URL"))
    cur = conn.cursor()
    psycopg2.extras.execute_values(
        cur,
        """
        UPDATE grille_nationale AS g
        SET commune = v.commune,
            arrondissement = NULL,
            localite = NULL
        FROM (VALUES %s) AS v(id_grille, commune)
        WHERE g.id_grille = v.id_grille
        """,
        updates,
        page_size=5000,
    )
    conn.commit()
    cur.close()
    conn.close()


def run() -> None:
    dept, geojson_path = _parse_args()
    if not dept:
        print("Usage: python process/enrichir_communes_geojson.py --dept <NomDept> [--geojson path]")
        return

    geoms = load_commune_geometries(geojson_path, dept)
    if not geoms:
        print(f"Aucune geometrie chargee pour departement={dept} depuis {geojson_path}")
        return

    points = get_points(dept)
    print(f"{len(points)} points a traiter pour {dept}")
    print(f"{len(geoms)} communes candidates")

    updates: list[tuple[str, str | None]] = []
    assigned = 0
    for i, (pid, lat, lon) in enumerate(points, 1):
        matched = None
        for commune_name, geom, (lon_min, lat_min, lon_max, lat_max) in geoms:
            if not (lon_min <= lon <= lon_max and lat_min <= lat <= lat_max):
                continue
            if point_in_polygon_geometry(lat, lon, geom):
                matched = commune_name
                break
        updates.append((pid, matched))
        if matched:
            assigned += 1
        if i % 1000 == 0:
            print(f"  {i}/{len(points)}")

    print("Mise à jour Postgres (batch)…")
    update_commune(updates)
    print(f"✓ Assignes: {assigned}/{len(points)}")


if __name__ == "__main__":
    run()

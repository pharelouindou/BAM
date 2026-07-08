"""
BAM · Collecte points d'eau — OpenStreetMap via Overpass API
Collecte TOUS les points d'eau connus du Bénin :
  - Cours d'eau (rivières, marigots, canaux)
  - Plans d'eau (lacs, mares, retenues)
  - Zones humides (wetlands, marais)
  - Puits et forages

Usage : python collect/osm.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests
import json
import psycopg2
from datetime import date
from dotenv import load_dotenv
load_dotenv()

OVERPASS_URL = "https://overpass-api.de/api/interpreter"

# Bounding box Bénin
BENIN = "6.2,0.8,12.4,3.8"  # south,west,north,east format Overpass

QUERY = f"""
[out:json][timeout:120];
(
  node["natural"="water"]({BENIN});
  node["natural"="wetland"]({BENIN});
  node["waterway"~"river|stream|canal|drain|ditch"]({BENIN});
  node["man_made"~"water_well|reservoir_covered"]({BENIN});
  node["water"~"lake|pond|reservoir|wastewater"]({BENIN});
  way["natural"="water"]({BENIN});
  way["natural"="wetland"]({BENIN});
  way["waterway"~"river|stream|canal"]({BENIN});
  relation["natural"="water"]({BENIN});
);
out center tags;
"""


def creer_table():
    conn = psycopg2.connect(os.getenv("DATABASE_URL"))
    cur  = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS points_eau_osm (
            osm_id      BIGINT PRIMARY KEY,
            osm_type    TEXT,
            type_eau    TEXT,
            nom         TEXT,
            lat         NUMERIC(9,6),
            lon         NUMERIC(9,6),
            tags        JSONB,
            date_import DATE DEFAULT CURRENT_DATE
        );
        CREATE INDEX IF NOT EXISTS idx_osm_lat_lon
            ON points_eau_osm(lat, lon);
        CREATE INDEX IF NOT EXISTS idx_osm_type
            ON points_eau_osm(type_eau);
    """)
    conn.commit(); cur.close(); conn.close()
    print("  ✓ Table points_eau_osm prête")


def classifier_type(tags: dict) -> str:
    """Classe le point d'eau selon ses tags OSM."""
    if tags.get("natural") == "wetland":  return "zone_humide"
    if tags.get("natural") == "water":
        water = tags.get("water", "")
        if water == "lake":      return "lac"
        if water == "pond":      return "mare"
        if water == "reservoir": return "retenue"
        return "plan_eau"
    ww = tags.get("waterway", "")
    if ww == "river":  return "riviere"
    if ww == "stream": return "marigot"
    if ww == "canal":  return "canal"
    if ww in ("drain","ditch"): return "drain"
    mm = tags.get("man_made", "")
    if mm == "water_well":           return "puits"
    if mm == "reservoir_covered":    return "reservoir"
    return "autre"


def collecter_osm() -> list[dict]:
    """Interroge l'API Overpass et retourne la liste des points d'eau."""
    print("  Requête Overpass API (peut prendre 30-60s)...")
    try:
        r = requests.post(
            OVERPASS_URL,
            data={"data": QUERY},
            timeout=180
        )
        r.raise_for_status()
        elements = r.json().get("elements", [])
        print(f"  {len(elements)} éléments OSM récupérés")
        return elements
    except Exception as e:
        print(f"  ✗ Overpass : {e}")
        return []


def sauvegarder(elements: list[dict]) -> int:
    """Insère les points d'eau en base PostgreSQL."""
    conn = psycopg2.connect(os.getenv("DATABASE_URL"))
    cur  = conn.cursor()
    count = 0

    for el in elements:
        osm_id   = el.get("id")
        osm_type = el.get("type", "node")
        tags     = el.get("tags", {})

        # Coordonnées : node direct ou center pour way/relation
        if osm_type == "node":
            lat = el.get("lat")
            lon = el.get("lon")
        else:
            center = el.get("center", {})
            lat = center.get("lat")
            lon = center.get("lon")

        if not lat or not lon:
            continue

        type_eau = classifier_type(tags)
        nom      = tags.get("name") or tags.get("name:fr") or None

        try:
            cur.execute("""
                INSERT INTO points_eau_osm
                  (osm_id, osm_type, type_eau, nom, lat, lon, tags)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (osm_id) DO UPDATE SET
                  tags = EXCLUDED.tags,
                  date_import = CURRENT_DATE
            """, (osm_id, osm_type, type_eau, nom, lat, lon,
                  json.dumps(tags)))
            count += 1
        except Exception as e:
            print(f"  ⚠ Insert {osm_id} : {e}")

    conn.commit(); cur.close(); conn.close()
    return count


def afficher_stats():
    conn = psycopg2.connect(os.getenv("DATABASE_URL"))
    cur  = conn.cursor()
    cur.execute("""
        SELECT type_eau, COUNT(*) as nb
        FROM points_eau_osm
        GROUP BY type_eau
        ORDER BY nb DESC
    """)
    rows = cur.fetchall()
    cur.close(); conn.close()
    print("\n  Répartition par type :")
    for r in rows:
        print(f"    {r[0]:<20} {r[1]:>5} points")


if __name__ == "__main__":
    print("=" * 52)
    print(f"  BAM · Collecte OSM points d'eau · {date.today()}")
    print("=" * 52)

    print("\n→ Création/vérification table...")
    creer_table()

    print("\n→ Collecte Overpass API...")
    elements = collecter_osm()

    if elements:
        print("\n→ Sauvegarde PostgreSQL...")
        nb = sauvegarder(elements)
        print(f"  ✓ {nb} points d'eau sauvegardés")
        afficher_stats()
    else:
        print("✗ Aucune donnée récupérée")

    print("\n✓ Collecte OSM terminée")
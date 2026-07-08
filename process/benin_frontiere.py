"""
BAM · Frontières du Bénin via GeoJSON officiel (communes ADM2).

Un point est « au Bénin » s'il tombe dans au moins une commune.
Le département est déduit de la commune (table COMMUNE_DEPARTEMENT).
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from typing import Any

DEFAULT_GEOJSON = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data/raw/geoBoundaries-BEN-ADM2.geojson",
)

# 77 communes → département (noms alignés sur shapeName du GeoJSON)
COMMUNE_DEPARTEMENT: dict[str, str] = {
    "Abomey": "Zou",
    "Abomey-Calavi": "Atlantique",
    "Adja-Ouere": "Plateau",
    "Adjarra": "Oueme",
    "Adjohoun": "Oueme",
    "Agbangnizoun": "Zou",
    "Aguegues": "Oueme",
    "Akpo-Misserete": "Oueme",
    "Allada": "Atlantique",
    "Aplahoue": "Couffo",
    "Athieme": "Mono",
    "Avrankou": "Oueme",
    "Banikoara": "Alibori",
    "Bante": "Collines",
    "Bassila": "Donga",
    "Bembereke": "Borgou",
    "Bohicon": "Zou",
    "Bonou": "Oueme",
    "Bopa": "Mono",
    "Boukombe": "Atacora",
    "Come": "Mono",
    "Copargo": "Donga",
    "Cotonou": "Littoral",
    "Cove": "Zou",
    "Dangbo": "Oueme",
    "Dassa-Zoume": "Collines",
    "Djakotomey": "Couffo",
    "Djidja": "Zou",
    "Djougou": "Donga",
    "Dogbo": "Couffo",
    "Glazoue": "Collines",
    "Gogounou": "Alibori",
    "Grand-Popo": "Mono",
    "Houeyogbe": "Mono",
    "Ifangni": "Plateau",
    "Kalale": "Borgou",
    "Kandi": "Alibori",
    "Karimama": "Alibori",
    "Kerou": "Atacora",
    "Ketou": "Plateau",
    "Klouekanme": "Couffo",
    "Kobli": "Atacora",
    "Kouande": "Atacora",
    "Kpomasse": "Atlantique",
    "Lalo": "Couffo",
    "Lokossa": "Mono",
    "Malanville": "Alibori",
    "Materi": "Atacora",
    "N'dali": "Borgou",
    "Natitingou": "Atacora",
    "Nikki": "Borgou",
    "Ouake": "Donga",
    "Ouesse": "Collines",
    "Ouidah": "Atlantique",
    "Ouinhi": "Zou",
    "Parakou": "Borgou",
    "Pehunco": "Atacora",
    "Perere": "Borgou",
    "Pobe": "Plateau",
    "Porto-Novo": "Oueme",
    "Sakete": "Plateau",
    "Savalou": "Collines",
    "Save": "Collines",
    "Segbana": "Alibori",
    "Seme-Kpodji": "Oueme",
    "Sinende": "Borgou",
    "So-Ava": "Atlantique",
    "Tanguieta": "Atacora",
    "Tchaourou": "Borgou",
    "Toffo": "Atlantique",
    "Tori-Bossito": "Atlantique",
    "Toucountouna": "Atacora",
    "Toviklin": "Couffo",
    "Za-Kpota": "Zou",
    "Zagnanado": "Zou",
    "Ze": "Atlantique",
    "Zogbodomey": "Zou",
}


@lru_cache(maxsize=1)
def _charger_index(
    geojson_path: str = DEFAULT_GEOJSON,
) -> tuple[Any, list[Any], list[str], list[str | None]]:
    from shapely.geometry import Point, shape  # type: ignore
    from shapely.strtree import STRtree  # type: ignore

    with open(geojson_path, "r", encoding="utf-8") as f:
        gj = json.load(f)

    shapes: list[Any] = []
    communes: list[str] = []
    departements: list[str | None] = []

    for ft in gj.get("features", []):
        name = ft.get("properties", {}).get("shapeName")
        geom = ft.get("geometry")
        if not name or not geom:
            continue
        try:
            g = shape(geom)
        except Exception:
            continue
        shapes.append(g)
        communes.append(name)
        departements.append(COMMUNE_DEPARTEMENT.get(name))

    if not shapes:
        raise RuntimeError(f"Aucune commune chargée depuis {geojson_path}")

    return STRtree(shapes), shapes, communes, departements


def commune_pour_point(
    lat: float,
    lon: float,
    geojson_path: str = DEFAULT_GEOJSON,
) -> str | None:
    """Retourne le nom de commune si le point est au Bénin, sinon None."""
    from shapely.geometry import Point  # type: ignore

    tree, shapes, communes, _ = _charger_index(geojson_path)
    p = Point(float(lon), float(lat))
    for idx in tree.query(p):
        g = shapes[int(idx)]
        if g.contains(p):
            return communes[int(idx)]
    return None


def est_dans_benin(
    lat: float,
    lon: float,
    geojson_path: str = DEFAULT_GEOJSON,
) -> bool:
    return commune_pour_point(lat, lon, geojson_path=geojson_path) is not None


def departement_pour_point(
    lat: float,
    lon: float,
    geojson_path: str = DEFAULT_GEOJSON,
) -> str:
    """Département via commune GeoJSON, ou HorsBenin si hors territoire."""
    commune = commune_pour_point(lat, lon, geojson_path=geojson_path)
    if not commune:
        return "HorsBenin"
    dept = COMMUNE_DEPARTEMENT.get(commune)
    return dept or "Inconnu"

"""
BAM · Priorité des sources satellite pour le scoring.

Ordre (du plus prioritaire au secours) :
  1. Sentinel-2-GEE  — haute résolution (Google Earth Engine)
  2. AppEEARS        — MODIS NASA
  3. ORNL            — MODIS REST, sans compte
"""

from __future__ import annotations

# Clés retournées par collect_nasa_all_sources / get_indices_sentinel_gee
PRIORITE_SOURCES: list[str] = [
    "Sentinel-2-GEE",
    "AppEEARS",
    "ORNL",
]


def _indices_valides(indi: dict | None) -> bool:
    if not indi:
        return False
    try:
        nd = indi.get("ndwi")
        if nd is None:
            return False
        float(nd)
        return True
    except (TypeError, ValueError):
        return False


def choisir_indices_pour_score(
    par_source: dict[str, dict],
) -> tuple[dict, str | None]:
    """
    Choisit un seul jeu d'indices (ndwi, ndvi, mndwi) pour le calcul du score,
    selon la liste PRIORITE_SOURCES.

    Returns:
        (dict indices pour calculer_score, clé de la source gagnante ou None)
    """
    for nom in PRIORITE_SOURCES:
        raw = par_source.get(nom)
        if _indices_valides(raw):
            return {
                "ndwi":  float(raw["ndwi"]),
                "ndvi":  float(raw.get("ndvi")  or 0.0),
                "mndwi": float(raw.get("mndwi") or 0.0),
            }, nom
    return {}, None

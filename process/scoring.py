"""BAM · Score composite sur 100 (version plus discriminante)."""


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(value, high))


def calculer_score(indices: dict, sol: dict, meteo: dict) -> dict:
    # Eau de surface + humidite du sol
    ndwi = float(indices.get("ndwi", 0.2) or 0.2)
    humidite = float(meteo.get("humidite_sol", 0.0) or 0.0)
    s_ndwi = _clamp((ndwi + 1.0) / 2.0 * 100.0)
    s_humidite = _clamp(humidite / 0.6 * 100.0)
    s_eau = s_ndwi * 0.65 + s_humidite * 0.35

    # Sol
    ph = float(sol.get("ph_sol", 6.5) or 6.5)
    carbone = float(sol.get("carbone_g_kg", 10.0) or 10.0)
    argile = float(sol.get("argile_pct", 25.0) or 25.0)
    s_ph = _clamp(100.0 - abs(ph - 6.5) * 22.0)
    s_carbone = _clamp(carbone / 20.0 * 100.0)
    s_argile = 100.0 if 20.0 <= argile <= 40.0 else 75.0 if 15.0 <= argile <= 45.0 else 45.0
    s_sol = s_ph * 0.35 + s_carbone * 0.40 + s_argile * 0.25

    # Pluie recente (7j + 30j) : cible zones humides cultivables sans exces
    pluie_7j = float(meteo.get("pluie_7j_mm", 0.0) or 0.0)
    pluie_30j = float(meteo.get("pluie_30j_mm", 0.0) or 0.0)
    s_pluie_7j = _clamp(pluie_7j / 40.0 * 100.0)
    s_pluie_30j = _clamp(pluie_30j / 140.0 * 100.0)
    s_pluie = s_pluie_7j * 0.45 + s_pluie_30j * 0.55

    # Temperature max (zone de confort approx. 24-33C)
    temp_max = float(meteo.get("temp_max_c", 30.0) or 30.0)
    ecart = abs(temp_max - 29.0)
    s_temp = _clamp(100.0 - ecart * 8.0)

    total = s_eau * 0.40 + s_sol * 0.30 + s_pluie * 0.20 + s_temp * 0.10
    priorite = "haute" if total >= 70 else "moyenne" if total >= 50 else "basse"

    return {
        "score_total": round(total,   1),
        "priorite":    priorite,
        "s_eau":       round(s_eau,   1),
        "s_sol":       round(s_sol,   1),
        "s_pluie":     round(s_pluie, 1),
        "s_temp":      round(s_temp,  1),
    }

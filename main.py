#!/usr/bin/env python3
"""
BAM · Pipeline principal — collecte + scoring + stockage pour les sites connus.

Usage :
  python main.py
      # satellite : NASA (AppEEARS + ORNL, chaque source stockée si OK) — lent AppEEARS
  python main.py --sat-sources=nasa,gee
      # en plus : Sentinel-2 via Google Earth Engine (GEE_PROJECT + earthengine authenticate)
  python main.py --no-sat
  python main.py --no-gee   # alias de --no-sat (compatibilité)

Variable d'environnement (alternative au flag) :
  BAM_SAT_SOURCES=nasa,gee    # défaut : nasa

Ordre de priorité pour le score (une seule source retenue) :
  1. Sentinel-2-GEE  2. AppEEARS  3. ORNL
(Si aucune : NDWI neutre 0.2 pour le calcul — voir process/scoring.py)

Coût runtime : chaque source activée = appels API supplémentaires par site
(ex. nasa,gee ≈ AppEEARS + ORNL + GEE par site ; AppEEARS seul ~2–3 min/site).
"""
from dotenv import load_dotenv
load_dotenv()

import os
import sys
from datetime import date, timedelta

from collect.meteo   import get_meteo
from collect.sol     import get_sol
from collect.chirps  import get_pluie_30j
from collect.noaa    import get_precip_gpm
from collect.nasa    import collect_nasa_all_sources
from collect.gee_sentinel import get_indices_sentinel_gee, SOURCE_KEY as GEE_SOURCE
from process.scoring import calculer_score
from process.satellite_sources import choisir_indices_pour_score
from db.connexion    import lister_sites, sauvegarder_mesure

_DEFAULT_METEO = {"temp_max_c": 32.0, "humidite_sol": 0.25, "pluie_7j_mm": 0.0}
_DEFAULT_SOL   = {"ph_sol": 6.5, "carbone_g_kg": 10.0, "argile_pct": 25.0}
_DEFAULT_NDWI  = {"ndwi": 0.2}


def _parse_sat_sources() -> set[str]:
    for arg in sys.argv:
        if arg.startswith("--sat-sources="):
            return {
                x.strip().lower()
                for x in arg.split("=", 1)[1].split(",")
                if x.strip()
            }
    raw = os.getenv("BAM_SAT_SOURCES", "nasa")
    return {x.strip().lower() for x in raw.split(",") if x.strip()}


def run():
    use_sat = "--no-sat" not in sys.argv and "--no-gee" not in sys.argv
    sat_src = _parse_sat_sources() if use_sat else set()

    print("=" * 60)
    print(f"  BAM · {date.today()} · Satellite={sat_src or 'désactivé'}")
    if use_sat and sat_src:
        if "nasa" in sat_src:
            print("  • NASA : AppEEARS + ORNL (sources séparées si disponibles)")
        if "gee" in sat_src:
            print("  • GEE  : Sentinel-2 (COPERNICUS/S2_SR_HARMONIZED)")
        print("  Priorité score : Sentinel-2-GEE > AppEEARS > ORNL")
    if use_sat and "nasa" in sat_src:
        print("  ⚠  AppEEARS : ~2–3 min / site en cas d’appel effectif")
    print("=" * 60)

    sites = lister_sites()
    if not sites:
        print("✗ Aucun site — docker compose up -d ?")
        return

    print(f"\n{len(sites)} sites à traiter\n")
    ok         = 0
    start_date = (date.today() - timedelta(days=30)).isoformat()
    end_date   = date.today().isoformat()

    for i, s in enumerate(sites, 1):
        lat, lon = s["lat"], s["lon"]
        print(f"[{i:02d}/{len(sites)}] {s['nom']} ({s['departement']})")

        meteo = get_meteo(lat, lon)
        if not meteo:
            print("  ⚠ météo indisponible → valeurs par défaut")
            meteo = _DEFAULT_METEO.copy()

        sol = get_sol(lat, lon)
        # ISRIC peut répondre HTTP 200 avec des moyennes manquantes → 0 partout (inutilisable)
        bad_sol = (
            sol
            and float(sol.get("ph_sol") or 0) == 0.0
            and float(sol.get("argile_pct") or 0) == 0.0
            and float(sol.get("carbone_g_kg") or 0) == 0.0
        )
        if not sol or bad_sol:
            if bad_sol:
                print("  ⚠ sol ISRIC incomplet (valeurs nulles) → valeurs par défaut")
            else:
                print("  ⚠ sol ISRIC indisponible → valeurs par défaut")
            sol = _DEFAULT_SOL.copy()

        p30 = get_pluie_30j(lat, lon)
        if not p30 or p30.get("pluie_30j_mm") is None:
            print("  ⚠ pluie_30j Open-Meteo indisponible → essai NOAA GPM...")
            p30 = get_precip_gpm(lat, lon, start_date, end_date) or {}
        if not p30 or p30.get("pluie_30j_mm") is None:
            print("  ⚠ pluie 30j toutes sources indisponibles → 0 mm")
            p30 = {"pluie_30j_mm": 0.0, "source_pluie": "défaut"}

        # ── Satellite : plusieurs sources en parallèle (stockage séparé) ─
        par_sat: dict[str, dict] = {}
        if use_sat:
            if "nasa" in sat_src:
                par_sat.update(collect_nasa_all_sources(lat, lon, start_date, end_date))
            if "gee" in sat_src:
                g = get_indices_sentinel_gee(lat, lon, start_date, end_date)
                if g:
                    par_sat[GEE_SOURCE] = g
            if not par_sat:
                print("  ⚠ aucune source satellite → score sans NDWI mesuré")

        idx_win, src_win = choisir_indices_pour_score(par_sat)
        idx_for_score = idx_win if idx_win else _DEFAULT_NDWI

        score_inputs = {**meteo, **p30}
        score = calculer_score(
            indices=idx_for_score,
            sol=sol,
            meteo=score_inputs,
        )

        win = src_win or "no-sat"
        if par_sat:
            mesure = {
                "indices_satellite": par_sat,
                **sol,
                **meteo,
                **p30,
                **score,
                "source":            win,
                "source_satellite":  win,
                "avec_satellite":   bool(src_win),
            }
        else:
            mesure = {
                **sol,
                **meteo,
                **p30,
                **score,
                "source":           "no-sat",
                "source_satellite": "no-sat",
                "avec_satellite":  False,
            }
        saved = sauvegarder_mesure(s["id"], mesure)

        if saved:
            src_l = f"src={win}"
            if par_sat and len(par_sat) > 1:
                src_l = f"sources={','.join(par_sat.keys())} → {win}"
            elif par_sat and len(par_sat) == 1:
                src_l = f"src={list(par_sat.keys())[0]}"
            ndwi_s = f"NDWI={idx_for_score.get('ndwi', 0):.4f}"
            sol_s  = f"pH={sol.get('ph_sol','?')} Arg={sol.get('argile_pct','?')}%"
            p30_s  = f"P30={p30.get('pluie_30j_mm','?')}mm"
            print(f"  ✓ {ndwi_s} | {sol_s} | {p30_s} | {src_l} | "
                  f"Score={score['score_total']}/100 {score['priorite'].upper()}")
            ok += 1
        else:
            print("  ✗ Erreur sauvegarde")
        print()

    print("=" * 60)
    print(f"  ✓ {ok}/{len(sites)} sites traités · {date.today()}")
    print("=" * 60)


if __name__ == "__main__":
    run()

"""
BAM · Enrichissement de la grille nationale (sans satellite).

Pour chaque point de la grille :
  1. Relief  : altitude + pente + TWI via Open-Elevation (SRTM 30m)
  2. Sol     : pH, carbone, argile via ISRIC SoilGrids
  3. Météo   : humidité sol, pluie 30j via Open-Meteo / CHIRPS
  4. Scoring : score_total + priorité + est_bas_fond

Le NDWI satellite est ajouté ultérieurement (quand quota Sentinel dispo).

Usage :
  python process/enrichir_grille.py                    # tout traiter
  python process/enrichir_grille.py --dept Collines    # un seul département
  python process/enrichir_grille.py --limit 50         # test 50 points
  python process/enrichir_grille.py --batch 30         # 30 points par lot (défaut 20)
  python process/enrichir_grille.py --reset-dept Zou   # ré-analyse un département
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import time
import psycopg2
import numpy as np
from datetime import date
from dotenv import load_dotenv
load_dotenv()

from collect.meteo  import get_meteo
from collect.sol    import get_sol
from collect.chirps import get_pluie_30j
from collect.srtm   import get_elevation_batch, calculer_pente, calculer_twi
from process.historique_grille import enregistrer_snapshot_journalier

# ── Paramètres ─────────────────────────────────────────────────────────────
SEUIL_NDWI     = 0.2    # non utilisé sans satellite
SEUIL_TWI      = 7.0    # TWI > 7 → bas-fond potentiel
SEUIL_HUMIDITE = 0.25   # humidité sol > 25% → indice d'eau
DELAI_ENTRE_POINTS = 1  # secondes entre appels API (politesse ISRIC)


# ── DB ─────────────────────────────────────────────────────────────────────

def get_points_a_enrichir(
    limit: int | None = None,
    dept: str | None = None,
) -> list[dict]:
    """Retourne les points non encore enrichis (date_analyse IS NULL)."""
    conn = psycopg2.connect(os.getenv("DATABASE_URL"))
    cur  = conn.cursor()

    conds = ["date_analyse IS NULL"]
    params: list = []

    if dept:
        conds.append("departement = %s")
        params.append(dept)

    where = " AND ".join(conds)
    sql   = f"""
        SELECT id_grille, lat, lon, departement
        FROM grille_nationale
        WHERE {where}
        ORDER BY lat DESC, lon ASC
    """
    if limit:
        sql += f" LIMIT {limit}"

    cur.execute(sql, params)
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [
        {"id": r[0], "lat": float(r[1]), "lon": float(r[2]), "dept": r[3]}
        for r in rows
    ]


def sauvegarder_enrichissement(data: dict) -> bool:
    """Met à jour un point de la grille avec toutes les données collectées."""
    try:
        conn = psycopg2.connect(os.getenv("DATABASE_URL"))
        cur  = conn.cursor()
        cur.execute("""
            UPDATE grille_nationale
            SET elevation_m  = %s,
                pente_pct    = %s,
                twi          = %s,
                ph_sol       = %s,
                carbone_g_kg = %s,
                argile_pct   = %s,
                pluie_30j_mm = %s,
                humidite_sol = %s,
                temp_max_c   = %s,
                score_eau    = %s,
                score_total  = %s,
                est_bas_fond = %s,
                est_humide   = %s,
                priorite     = %s,
                date_analyse = %s
            WHERE id_grille = %s
        """, (
            data.get("elevation_m"),
            data.get("pente_pct"),
            data.get("twi"),
            data.get("ph_sol"),
            data.get("carbone_g_kg"),
            data.get("argile_pct"),
            data.get("pluie_30j_mm"),
            data.get("humidite_sol"),
            data.get("temp_max_c"),
            data.get("score_eau"),
            data.get("score_total"),
            data.get("est_bas_fond"),
            data.get("est_humide"),
            data.get("priorite"),
            date.today(),
            data["id_grille"],
        ))
        enregistrer_snapshot_journalier(cur, data["id_grille"])
        conn.commit()
        cur.close()
        conn.close()
        return True
    except Exception as e:
        print(f"  ✗ DB : {e}")
        return False


# ── Scoring sans satellite ─────────────────────────────────────────────────

def scorer_sans_satellite(
    twi: float,
    humidite: float,
    pluie_30j: float,
    ph: float,
    carbone: float,
    argile: float,
    temp_max: float,
) -> dict:
    """
    Score sur 100 basé uniquement sur données sol/météo/relief.
    Plus conservateur que le score satellite — à affiner quand NDWI dispo.
    """
    def clamp(v, lo=0.0, hi=100.0):
        return max(lo, min(v, hi))

    # Relief (TWI) : bas-fond si TWI > 7, idéal > 10
    s_relief = clamp((twi / 12.0) * 100.0)

    # Eau sol + pluie
    s_humidite = clamp(humidite / 0.5 * 100.0)
    s_pluie    = clamp(pluie_30j / 120.0 * 100.0)
    s_eau      = s_humidite * 0.5 + s_pluie * 0.5

    # Sol
    s_ph      = clamp(100.0 - abs(ph - 6.5) * 22.0)
    s_carbone = clamp(carbone / 20.0 * 100.0)
    s_argile  = 100.0 if 20.0 <= argile <= 40.0 else 75.0 if 15.0 <= argile <= 45.0 else 45.0
    s_sol     = s_ph * 0.35 + s_carbone * 0.40 + s_argile * 0.25

    # Température (zone de confort 26-34°C pour cultures)
    ecart  = abs(temp_max - 30.0)
    s_temp = clamp(100.0 - ecart * 9.0)

    # Pondération finale (sans satellite → relief compte plus)
    total = (
        s_relief * 0.35 +
        s_eau    * 0.30 +
        s_sol    * 0.25 +
        s_temp   * 0.10
    )

    priorite = "haute" if total >= 70 else "moyenne" if total >= 50 else "basse"

    return {
        "score_eau":   round(s_eau,    1),
        "score_total": round(total,    1),
        "priorite":    priorite,
    }


# ── Collecte relief par lots ───────────────────────────────────────────────

def collecter_relief_batch(points: list[dict]) -> dict[str, float]:
    """
    Collecte altitudes pour un lot de points via Open-Elevation.
    Retourne {id_grille: elevation_m}.
    """
    elev_points = [{"lat": p["lat"], "lon": p["lon"]} for p in points]
    raw = get_elevation_batch(elev_points)

    result = {}
    for p in points:
        key  = f"{p['lat']:.4f}_{p['lon']:.4f}"
        elev = raw.get(key)
        result[p["id"]] = float(elev) if elev is not None else 0.0
    return result


def calculer_twi_depuis_voisins(
    lat: float, lon: float, elev: float, elevations: dict[str, float],
    resolution_deg: float = 0.05,
) -> tuple[float, float]:
    """
    Calcule pente et TWI pour un point en utilisant ses voisins directs.
    elevations = {id_grille: elev_m}
    """
    dist_m  = resolution_deg * 111_000  # ~5km pour 0.05°
    voisins = []

    # Les 4 voisins cardinaux (approximatifs via lat/lon proches)
    for dlat, dlon in [(resolution_deg, 0), (-resolution_deg, 0),
                       (0, resolution_deg), (0, -resolution_deg)]:
        vlat = round(lat + dlat, 4)
        vlon = round(lon + dlon, 4)
        for e_id, e_val in elevations.items():
            if abs(e_val - elev) < 500:  # filtre cohérence
                voisins.append(e_val)
                break

    pente = calculer_pente(elev, voisins, distance_m=dist_m)
    twi   = calculer_twi(max(pente, 0.1))
    return pente, twi


# ── Pipeline principal ─────────────────────────────────────────────────────

def run():
    # ── Args CLI ──────────────────────────────────────────────────────────
    limit       = None
    dept_filtre = None
    batch_size  = 20

    for i, arg in enumerate(sys.argv[1:], 1):
        if arg == "--limit" and i < len(sys.argv) - 1:
            limit = int(sys.argv[i + 1])
        if arg in ("--dept", "--reset-dept") and i < len(sys.argv) - 1:
            dept_filtre = sys.argv[i + 1]
        if arg == "--batch" and i < len(sys.argv) - 1:
            batch_size = int(sys.argv[i + 1])

    # Si reset-dept, remettre date_analyse à NULL pour ce département
    if "--reset-dept" in sys.argv and dept_filtre:
        conn = psycopg2.connect(os.getenv("DATABASE_URL"))
        cur  = conn.cursor()
        cur.execute(
            "UPDATE grille_nationale SET date_analyse = NULL WHERE departement = %s",
            (dept_filtre,)
        )
        conn.commit()
        cur.close()
        conn.close()
        print(f"  Reset département {dept_filtre} — points remis à analyser")

    print("=" * 60)
    print(f"  BAM · Enrichissement grille nationale · {date.today()}")
    if dept_filtre:
        print(f"  Filtre département : {dept_filtre}")
    if limit:
        print(f"  Limite : {limit} points")
    print("=" * 60)

    points = get_points_a_enrichir(limit=limit, dept=dept_filtre)
    total  = len(points)

    if not points:
        print("✓ Tous les points ont déjà été enrichis.")
        print("  Pour ré-analyser : --reset-dept <NomDept>")
        return

    print(f"\n  {total} points à enrichir\n")

    ok = 0
    bas_fonds_detectes = 0

    # Collecte relief en lot
    print("→ Collecte altitudes (Open-Elevation batch)...")
    all_elevations: dict[str, float] = {}
    for i in range(0, total, 200):
        lot = points[i:i + 200]
        all_elevations.update(collecter_relief_batch(lot))
        if i + 200 < total:
            time.sleep(2)
    print(f"  ✓ {len(all_elevations)} altitudes récupérées\n")

    # Traitement point par point
    for i, p in enumerate(points, 1):
        lat, lon = p["lat"], p["lon"]
        dept     = p.get("dept", "?")
        prefix   = f"[{i:04d}/{total}] {lat:.4f},{lon:.4f} ({dept})"

        print(prefix, end="  ")

        # ── Relief ──────────────────────────────────────────────────────
        elev    = all_elevations.get(p["id"], 0.0)
        pente, twi = calculer_twi_depuis_voisins(
            lat, lon, elev, all_elevations
        )

        # ── Sol ─────────────────────────────────────────────────────────
        sol = get_sol(lat, lon) or {"ph_sol": 6.5, "carbone_g_kg": 10.0, "argile_pct": 25.0}
        time.sleep(DELAI_ENTRE_POINTS)

        # ── Météo + Pluie ────────────────────────────────────────────────
        meteo = get_meteo(lat, lon) or {"humidite_sol": 0.2, "pluie_7j_mm": 0.0, "temp_max_c": 32.0}
        p30   = get_pluie_30j(lat, lon) or {"pluie_30j_mm": 0.0}

        humidite  = float(meteo.get("humidite_sol", 0.2) or 0.2)
        pluie_30j = float(p30.get("pluie_30j_mm", 0.0) or 0.0)
        temp_max  = float(meteo.get("temp_max_c", 32.0) or 32.0)

        # ── Score ────────────────────────────────────────────────────────
        scores = scorer_sans_satellite(
            twi       = twi,
            humidite  = humidite,
            pluie_30j = pluie_30j,
            ph        = float(sol.get("ph_sol", 6.5) or 6.5),
            carbone   = float(sol.get("carbone_g_kg", 10.0) or 10.0),
            argile    = float(sol.get("argile_pct", 25.0) or 25.0),
            temp_max  = temp_max,
        )

        est_bas_fond = twi > SEUIL_TWI
        est_humide   = humidite > SEUIL_HUMIDITE or pluie_30j > 50.0

        if est_bas_fond:
            bas_fonds_detectes += 1

        tag = "BAS-FOND ✓" if est_bas_fond else "—"
        print(f"TWI={twi:.1f} Score={scores['score_total']:.0f} {scores['priorite'].upper()} {tag}")

        saved = sauvegarder_enrichissement({
            "id_grille":   p["id"],
            "elevation_m": elev,
            "pente_pct":   pente,
            "twi":         twi,
            "ph_sol":      sol.get("ph_sol"),
            "carbone_g_kg":sol.get("carbone_g_kg"),
            "argile_pct":  sol.get("argile_pct"),
            "pluie_30j_mm":pluie_30j,
            "humidite_sol":humidite,
            "temp_max_c":  temp_max,
            "score_eau":   scores["score_eau"],
            "score_total": scores["score_total"],
            "est_bas_fond":est_bas_fond,
            "est_humide":  est_humide,
            "priorite":    scores["priorite"],
        })

        if saved:
            ok += 1

    # ── Résumé ─────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print(f"  ✓ {ok}/{total} points enrichis")
    print(f"  Bas-fonds détectés (TWI > {SEUIL_TWI}) : {bas_fonds_detectes}")
    print("=" * 60)

    # Top bas-fonds
    try:
        conn = psycopg2.connect(os.getenv("DATABASE_URL"))
        cur  = conn.cursor()
        cur.execute("""
            SELECT departement, lat, lon, twi, score_total, priorite
            FROM grille_nationale
            WHERE est_bas_fond = TRUE
            ORDER BY score_total DESC NULLS LAST
            LIMIT 15
        """)
        rows = cur.fetchall()
        cur.close()
        conn.close()

        if rows:
            print(f"\n  Top bas-fonds détectés :")
            print(f"  {'Dép.':<12} {'LAT':>8} {'LON':>8} {'TWI':>6} {'Score':>6} {'Prior.':<8}")
            print("  " + "─" * 54)
            for r in rows:
                print(f"  {str(r[0]):<12} {float(r[1]):8.4f} {float(r[2]):8.4f} "
                      f"{float(r[3]):6.1f} {float(r[4]):6.1f} {str(r[5]):<8}")
    except Exception:
        pass

    print("\n→ Satellite (GEE), après enrichissement :")
    print("  python process/analyser_grille.py --dept \"Alibori\"")
    print("  python process/analyser_grille.py --dept \"Alibori\" --limit 100   # essai")


if __name__ == "__main__":
    run()

# process/analyser_grille.py
"""
BAM · Analyse satellite de la grille nationale (par département possible).

Pour chaque point de la grille :
  - Par défaut : Sentinel-2 via GEE uniquement (rapide pour la grille par département)
  - Option : ajouter NASA (AppEEARS/ORNL) — lent ; utile en secours si GEE échoue
  - Priorité si plusieurs sources : GEE > AppEEARS > ORNL

Usage :
  python process/analyser_grille.py
  python process/analyser_grille.py --dept Collines
  python process/analyser_grille.py --limit 50
  python process/analyser_grille.py --dept Collines --force  # nouveau snapshot quotidien
  python process/analyser_grille.py --sat-sources=gee,nasa   # + NASA (plus lent)
"""
import sys
import psycopg2
import os
from datetime import date
from dotenv import load_dotenv
load_dotenv()
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from process.historique_grille import enregistrer_snapshot_journalier

SEUIL_NDWI = 0.2   # au-dessus = zone humide potentielle


def _parse_sat_sources(argv: list[str]) -> set[str]:
    for arg in argv:
        if arg.startswith("--sat-sources="):
            return {
                x.strip().lower()
                for x in arg.split("=", 1)[1].split(",")
                if x.strip()
            }
    # Défaut : GEE seul (NASA désactivé — AppEEARS peut prendre plusieurs minutes par point)
    return {"gee"}


def get_points_a_analyser(
    limit: int | None = None,
    dept: str | None = None,
    force: bool = False,
) -> list:
    """
    Points encore sans NDWI satellite (indépendant de date_analyse : enrichir_grille
    remplit date_analyse sans NDWI — l’ancien filtre date_analyse IS NULL bloquait l’étape satellite).
    """
    conn = psycopg2.connect(os.getenv("DATABASE_URL"))
    cur = conn.cursor()

    cond = "TRUE" if force else "ndwi IS NULL"
    query = f"""
        SELECT id_grille, lat, lon
        FROM grille_nationale
        WHERE {cond}
    """
    params: list = []
    if dept:
        query += " AND departement = %s"
        params.append(dept)

    query += " ORDER BY lat DESC, lon ASC"
    if limit:
        query += " LIMIT %s"
        params.append(int(limit))

    cur.execute(query, params)
    rows = cur.fetchall()
    cur.close(); conn.close()
    return [{"id": r[0], "lat": float(r[1]), "lon": float(r[2])} for r in rows]


def marquer_analyse(id_grille: str, ndwi: float, ndvi: float, source_ndwi: str):
    """Met à jour un point avec ses résultats."""
    conn = psycopg2.connect(os.getenv("DATABASE_URL"))
    cur  = conn.cursor()
    cur.execute("""
        UPDATE grille_nationale
        SET ndwi         = %s,
            ndvi         = %s,
            est_humide   = %s,
            score_eau    = %s,
            date_analyse = %s,
            source_ndwi  = %s
        WHERE id_grille = %s
    """, (
        ndwi, ndvi,
        ndwi > SEUIL_NDWI,
        round(max(0, (ndwi + 1) / 2 * 100), 1),
        date.today(),
        source_ndwi,
        id_grille,
    ))
    enregistrer_snapshot_journalier(cur, id_grille)
    conn.commit()
    cur.close(); conn.close()


def run():
    from collect.gee_sentinel import SOURCE_KEY as GEE_SOURCE, get_indices_sentinel_gee
    from process.satellite_sources import choisir_indices_pour_score

    # Parser les args
    limit = None
    dept: str | None = None
    force = "--force" in sys.argv
    sat_src = _parse_sat_sources(sys.argv)
    for i, arg in enumerate(sys.argv):
        if arg == "--limit" and i + 1 < len(sys.argv):
            limit = int(sys.argv[i + 1])
        if arg == "--dept" and i + 1 < len(sys.argv):
            dept = sys.argv[i + 1]

    print("=" * 52)
    print(f"  BAM · Analyse grille nationale · {date.today()}")
    print(f"  Seuil NDWI : {SEUIL_NDWI} (au-dessus = zone humide)")
    if dept:
        print(f"  Département : {dept}")
    print(f"  Sources satellites : {sorted(sat_src)}")
    print("=" * 52)

    points = get_points_a_analyser(limit=limit, dept=dept, force=force)
    cible = "points à ré-analyser" if force else "points sans NDWI satellite à analyser"
    print(f"  {len(points)} {cible}\n")

    if not points:
        print("✓ Aucun point à traiter (NDWI déjà renseigné partout pour ce filtre)")
        return

    if "nasa" in sat_src:
        from collect.nasa import collect_nasa_all_sources

    humides = 0
    for i, p in enumerate(points, 1):
        print(f"[{i:04d}/{len(points)}] lat={p['lat']} lon={p['lon']}", end=" ")
        par_source: dict[str, dict] = {}

        # 1) Sentinel-2 via GEE
        if "gee" in sat_src:
            gee_idx = get_indices_sentinel_gee(p["lat"], p["lon"])
            if gee_idx:
                par_source[GEE_SOURCE] = gee_idx

        # 2) NASA (optionnel — très lent si AppEEARS actif)
        if "nasa" in sat_src:
            nasa = collect_nasa_all_sources(p["lat"], p["lon"])
            if nasa:
                par_source.update(nasa)

        idx, src = choisir_indices_pour_score(par_source)

        if idx and src:
            ndwi = idx["ndwi"]
            ndvi = idx.get("ndvi", 0.0)
            tag  = "HUMIDE ✓" if ndwi > SEUIL_NDWI else "sec"
            print(f"→ NDWI={ndwi:+.3f} {tag} (src={src})")
            marquer_analyse(p["id"], ndwi, ndvi, src)
            if ndwi > SEUIL_NDWI:
                humides += 1
        else:
            print("→ pas de données (GEE" + ("/NASA" if "nasa" in sat_src else "") + ")")

    print("\n" + "=" * 52)
    print(f"  {humides}/{len(points)} zones humides détectées")
    print(f"  NDWI > {SEUIL_NDWI} → candidats sites irrigables")
    print("=" * 52)

    # Résumé des zones humides
    conn = psycopg2.connect(os.getenv("DATABASE_URL"))
    cur  = conn.cursor()
    cur.execute("""
        SELECT lat, lon, ndwi, score_eau
        FROM grille_nationale
        WHERE est_humide = TRUE
          AND ndwi IS NOT NULL
        ORDER BY ndwi DESC
        LIMIT 10
    """)
    rows = cur.fetchall()
    cur.close(); conn.close()

    if rows:
        print("\n  Top zones humides détectées :")
        print(f"  {'LAT':>8} {'LON':>8} {'NDWI':>8} {'SCORE':>6}")
        print("  " + "-" * 36)
        for r in rows:
            lat, lon, ndwi, sc = r[0], r[1], r[2], r[3]
            sc_f = float(sc) if sc is not None else 0.0
            print(
                f"  {float(lat):8.4f} {float(lon):8.4f} "
                f"{float(ndwi):+8.4f} {sc_f:6.1f}"
            )


if __name__ == "__main__":
    run()
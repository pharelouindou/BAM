"""BAM · PostgreSQL — accès base de données."""
import os
import psycopg2
from datetime import date
from dotenv import load_dotenv

load_dotenv()


def get_conn():
    return psycopg2.connect(os.getenv("DATABASE_URL"))


def lister_sites() -> list:
    conn = get_conn()
    cur  = conn.cursor()
    cur.execute(
        "SELECT id, nom, departement, commune, lat, lon, superficie_ha "
        "FROM sites ORDER BY id"
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [
        {
            "id": r[0], "nom": r[1], "departement": r[2],
            "commune": r[3], "lat": r[4], "lon": r[5], "superficie_ha": r[6],
        }
        for r in rows
    ]


def _insert_indices_satellite_multisource(
    cur, site_id: int, d: date, par_source: dict[str, dict],
) -> None:
    """Insère ndwi, ndvi, mndwi pour chaque clé de source (AppEEARS, ORNL, Sentinel-2-GEE, …)."""
    for src_name, triplet in par_source.items():
        if not triplet or not isinstance(triplet, dict):
            continue
        for nom in ("ndwi", "ndvi", "mndwi"):
            val = triplet.get(nom)
            if val is None:
                continue
            cur.execute(
                """
                INSERT INTO indices
                    (site_id, date_collecte, categorie, nom_indice, valeur, source, qualite)
                VALUES (%s, %s, 'satellite', %s, %s, %s, 'ok')
                ON CONFLICT (site_id, date_collecte, nom_indice, source) DO UPDATE SET
                    valeur  = EXCLUDED.valeur,
                    qualite = EXCLUDED.qualite
                """,
                (site_id, d, nom, val, str(src_name)),
            )


def sauvegarder_mesure(site_id: int, data: dict) -> bool:
    """
    Persiste une collecte complète :
      - indices bruts (y compris plusieurs sources satellite si `indices_satellite` fourni)
      - ligne dans `scores` (avec `source_satellite` = source retenue pour le score)

    Modes :
      - Multisource : `indices_satellite` = {"AppEEARS": {ndwi,...}, "Sentinel-2-GEE": {...}, ...}
        + `source` / `source_satellite` = source gagnante (ex. Sentinel-2-GEE)
      - Legacy : champs plats `ndwi`, `ndvi`, `mndwi` + `source` unique
    """
    try:
        conn = get_conn()
        cur  = conn.cursor()
        today = data.get("date_collecte", date.today())

        source_pluie = data.get("source_pluie", "Open-Meteo")
        par_sat      = data.get("indices_satellite")
        if par_sat and isinstance(par_sat, dict) and par_sat:
            _insert_indices_satellite_multisource(cur, site_id, today, par_sat)
        else:
            # ── un seul jeu d'indices satellite (rétrocompat) ─────────────
            source_sat = data.get("source", "inconnu")
            for nom, val, ok in [
                ("ndwi",  data.get("ndwi"),  data.get("ndwi")  is not None),
                ("ndvi",  data.get("ndvi"),  data.get("ndvi")  is not None),
                ("mndwi", data.get("mndwi"), data.get("mndwi") is not None),
            ]:
                if not ok or val is None:
                    continue
                cur.execute(
                    """
                    INSERT INTO indices
                        (site_id, date_collecte, categorie, nom_indice, valeur, source, qualite)
                    VALUES (%s, %s, 'satellite', %s, %s, %s, %s)
                    ON CONFLICT (site_id, date_collecte, nom_indice, source) DO UPDATE SET
                        valeur  = EXCLUDED.valeur,
                        qualite = EXCLUDED.qualite
                    """,
                    (site_id, today, nom, val, source_sat, "ok"),
                )

        # Sol / météo / pluie (une source chacun)
        autres = [
            ("sol",   "ph_sol",       data.get("ph_sol"),       "ISRIC"),
            ("sol",   "carbone_g_kg", data.get("carbone_g_kg"), "ISRIC"),
            ("sol",   "argile_pct",   data.get("argile_pct"),   "ISRIC"),
            ("meteo", "humidite_sol", data.get("humidite_sol"), "Open-Meteo"),
            ("meteo", "temp_max_c",   data.get("temp_max_c"),   "Open-Meteo"),
            ("meteo", "pluie_7j_mm",  data.get("pluie_7j_mm"),  "Open-Meteo"),
            ("pluie", "pluie_30j_mm", data.get("pluie_30j_mm"), source_pluie),
        ]
        for cat, nom, val, src in autres:
            if val is None:
                continue
            qu = "ok" if str(val) not in ("0", "0.0", "") else "estime"
            cur.execute(
                """
                INSERT INTO indices
                    (site_id, date_collecte, categorie, nom_indice, valeur, source, qualite)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (site_id, date_collecte, nom_indice, source) DO UPDATE SET
                    valeur  = EXCLUDED.valeur,
                    qualite = EXCLUDED.qualite
                """,
                (site_id, today, cat, nom, val, src, qu),
            )

        win = data.get("source_satellite") or data.get("source") or "no-sat"
        avec_sa = data.get("avec_satellite")
        if avec_sa is None:
            avec_sa = bool(win and win not in ("no-sat", "inconnu", ""))

        cur.execute(
            """
            INSERT INTO scores
                (site_id, date_calcul, s_eau, s_sol, s_pluie, s_temp,
                 score_total, priorite, avec_satellite, source_satellite)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (site_id, date_calcul) DO UPDATE SET
                s_eau            = EXCLUDED.s_eau,
                s_sol            = EXCLUDED.s_sol,
                s_pluie          = EXCLUDED.s_pluie,
                s_temp           = EXCLUDED.s_temp,
                score_total      = EXCLUDED.score_total,
                priorite         = EXCLUDED.priorite,
                avec_satellite   = EXCLUDED.avec_satellite,
                source_satellite = EXCLUDED.source_satellite
            """,
            (
                site_id, today,
                data.get("s_eau"),   data.get("s_sol"),
                data.get("s_pluie"), data.get("s_temp"),
                data.get("score_total"), data.get("priorite"),
                avec_sa, win,
            ),
        )

        conn.commit()
        cur.close()
        conn.close()
        return True

    except Exception as e:
        print(f"  ✗ DB : {e}")
        return False

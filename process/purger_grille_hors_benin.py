"""
BAM · Purge des points de grille_nationale hors frontières du Bénin (GeoJSON ADM2).

Usage:
  python process/purger_grille_hors_benin.py           # dry-run (affiche seulement)
  python process/purger_grille_hors_benin.py --apply   # supprime en base
  python process/purger_grille_hors_benin.py --apply --fix-dept  # + recalcule departement
"""

from __future__ import annotations

import os
import sys

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from process.benin_frontiere import commune_pour_point, COMMUNE_DEPARTEMENT


def run() -> None:
    apply = "--apply" in sys.argv
    fix_dept = "--fix-dept" in sys.argv

    conn = psycopg2.connect(os.getenv("DATABASE_URL"))
    cur = conn.cursor()
    cur.execute("SELECT id_grille, lat::float8, lon::float8, departement FROM grille_nationale")
    rows = cur.fetchall()

    to_delete: list[str] = []
    to_fix: list[tuple[str, str]] = []

    total = len(rows)
    for i, (pid, lat, lon, dept) in enumerate(rows, 1):
        lat_f, lon_f = float(lat), float(lon)
        commune = commune_pour_point(lat_f, lon_f)
        if commune is None:
            to_delete.append(pid)
        elif fix_dept:
            new_dept = COMMUNE_DEPARTEMENT.get(commune, "Inconnu")
            if new_dept not in ("HorsBenin", "Inconnu") and new_dept != dept:
                to_fix.append((pid, new_dept))
        if i % 5000 == 0:
            print(f"  analysé {i}/{total}", flush=True)

    print(f"Points en base : {total}")
    print(f"Hors Bénin (à supprimer) : {len(to_delete)}")
    if fix_dept:
        print(f"Département à corriger : {len(to_fix)}")

    if to_delete:
        delete_set = set(to_delete)
        by_dept: dict[str, int] = {}
        for pid, lat, lon, dept in rows:
            if pid in delete_set:
                key = str(dept or "?")
                by_dept[key] = by_dept.get(key, 0) + 1
        print("Répartition des suppressions par département actuel :")
        for d, n in sorted(by_dept.items(), key=lambda x: -x[1]):
            print(f"  {d:<12} {n}")

    if not apply:
        print("\nDry-run : rien supprimé. Relancer avec --apply pour exécuter.")
        cur.close()
        conn.close()
        return

    if to_delete:
        print("Suppression en cours…", flush=True)
        batch = 500
        hist_total = 0
        grille_total = 0
        for start in range(0, len(to_delete), batch):
            chunk = to_delete[start : start + batch]
            try:
                cur.execute(
                    "DELETE FROM grille_historique_journalier WHERE id_grille = ANY(%s)",
                    (chunk,),
                )
                hist_total += cur.rowcount
            except psycopg2.Error:
                pass
            cur.execute(
                "DELETE FROM grille_nationale WHERE id_grille = ANY(%s)",
                (chunk,),
            )
            grille_total += cur.rowcount
            conn.commit()
            if (start // batch) % 10 == 0:
                print(f"  … {min(start + batch, len(to_delete))}/{len(to_delete)}", flush=True)
        print(f"  historique : {hist_total} lignes", flush=True)
        print(f"✓ {grille_total} points supprimés", flush=True)

    if fix_dept and to_fix:
        print("Correction des départements…", flush=True)
        psycopg2.extras.execute_values(
            cur,
            """
            UPDATE grille_nationale AS g
            SET departement = v.departement
            FROM (VALUES %s) AS v(id_grille, departement)
            WHERE g.id_grille = v.id_grille
            """,
            to_fix,
            page_size=5000,
        )
        print(f"✓ {len(to_fix)} départements corrigés", flush=True)

    conn.commit()
    cur.close()
    conn.close()
    print("Terminé.", flush=True)


if __name__ == "__main__":
    run()

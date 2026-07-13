#!/usr/bin/env python3
"""
BAM · Vérification base de données (Neon / local).

Usage :
  python db/verify_db.py
  DATABASE_URL=postgresql://... python db/verify_db.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv()


def main() -> int:
    import psycopg2

    url = os.getenv("DATABASE_URL", "").strip()
    if not url:
        print("✗  DATABASE_URL manquante")
        return 1

    print("\n═══ BAM · Vérification base ═══\n")
    print(f"  URL : {url[:50]}...")

    try:
        conn = psycopg2.connect(url, connect_timeout=10)
        cur = conn.cursor()

        tables = ("sites", "indices", "scores", "grille_nationale", "grille_historique_journalier")
        for table in tables:
            cur.execute(
                "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = %s)",
                (table,),
            )
            exists = cur.fetchone()[0]
            if not exists:
                print(f"✗  table `{table}` absente")
                return 1
            cur.execute(f"SELECT COUNT(*) FROM {table}")  # noqa: S608 — noms fixes
            n = cur.fetchone()[0]
            print(f"✓  {table:<30} {n:>8} lignes")

        cur.execute(
            """
            SELECT departement, COUNT(*) AS n,
                   COUNT(*) FILTER (WHERE ndwi IS NOT NULL) AS avec_sat
            FROM grille_nationale
            GROUP BY departement
            ORDER BY departement
            """
        )
        rows = cur.fetchall()
        if rows:
            print("\n  Grille par département :")
            for dept, n, sat in rows:
                print(f"    {dept:<12} {n:>6} pts  ({sat} avec satellite)")
        else:
            print("\n⚠  grille_nationale vide — lancer process/quadrillage.py")

        cur.close()
        conn.close()
        print("\n✓  Base OK\n")
        return 0

    except Exception as exc:
        print(f"\n✗  Erreur : {exc}\n")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

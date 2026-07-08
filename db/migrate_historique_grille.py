"""
BAM · Migration historique journalier grille.

Usage:
  python db/migrate_historique_grille.py
"""

import os
import sys

import psycopg2
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from process.historique_grille import ensure_historique_table

load_dotenv()


def run() -> None:
    conn = psycopg2.connect(os.getenv("DATABASE_URL"))
    cur = conn.cursor()
    ensure_historique_table(cur)
    conn.commit()
    cur.close()
    conn.close()
    print("✓ Table grille_historique_journalier prête")


if __name__ == "__main__":
    run()

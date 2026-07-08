"""Ajoute les colonnes administratives à grille_nationale si absentes."""

import os

import psycopg2
from dotenv import load_dotenv

load_dotenv()


def run() -> None:
    conn = psycopg2.connect(os.getenv("DATABASE_URL"))
    cur = conn.cursor()

    cur.execute("ALTER TABLE grille_nationale ADD COLUMN IF NOT EXISTS commune TEXT")
    cur.execute("ALTER TABLE grille_nationale ADD COLUMN IF NOT EXISTS arrondissement TEXT")
    cur.execute("ALTER TABLE grille_nationale ADD COLUMN IF NOT EXISTS localite TEXT")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_grille_commune ON grille_nationale(commune)")

    conn.commit()
    cur.close()
    conn.close()
    print("✓ Migration admin_geo appliquée")


if __name__ == "__main__":
    run()

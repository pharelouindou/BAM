#!/usr/bin/env python3
"""BAM · Test environnement — python test_connexion.py"""
import sys

print("\n═══ BAM · Vérification environnement ═══\n")

# Python
v = sys.version_info
ok_py = v.major >= 3 and v.minor >= 10
print(f"{'✓' if ok_py else '✗'}  Python {v.major}.{v.minor}.{v.micro}")

# Libs
LIBS = [
    ("requests", "requests"),
    ("psycopg2", "psycopg2-binary"),
    ("dotenv", "python-dotenv"),
    ("numpy", "numpy"),
    ("boto3", "boto3"),
    ("ee", "earthengine-api"),
    ("fastapi", "fastapi"),
    ("uvicorn", "uvicorn"),
    ("prefect", "prefect"),
]
for lib, pkg in LIBS:
    try:
        __import__(lib)
        print(f"✓  {lib}")
    except ImportError:
        print(f"✗  {lib}  →  pip install {pkg}")

# DB
print()
try:
    from dotenv import load_dotenv
    import os
    import psycopg2

    load_dotenv()
    url = os.getenv("DATABASE_URL", "")
    print(f"✓  DATABASE_URL  →  {url[:45]}..." if url else "✗  DATABASE_URL manquante")
    if url:
        conn = psycopg2.connect(url, connect_timeout=5)
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM sites")
        nb_sites = cur.fetchone()[0]
        cur.execute(
            "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'grille_nationale')"
        )
        has_grille = cur.fetchone()[0]
        if has_grille:
            cur.execute("SELECT COUNT(*) FROM grille_nationale")
            nb_grille = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM grille_nationale WHERE ndwi IS NOT NULL")
            nb_sat = cur.fetchone()[0]
            print(f"✓  PostgreSQL  →  {nb_sites} sites, {nb_grille} pts grille ({nb_sat} avec satellite)")
        else:
            print(f"✓  PostgreSQL  →  {nb_sites} sites (grille_nationale absente)")
        conn.close()
except Exception as e:
    print(f"✗  PostgreSQL : {e}")

# GEE (optionnel)
print()
gee_proj = os.getenv("GEE_PROJECT", "")
gee_sa = os.getenv("GEE_SERVICE_ACCOUNT_JSON", "")
if gee_proj:
    print(f"✓  GEE_PROJECT  →  {gee_proj}")
else:
    print("⚠  GEE_PROJECT non définie (satellite désactivé)")
if gee_sa:
    print("✓  GEE_SERVICE_ACCOUNT_JSON  →  présent")
else:
    print("⚠  GEE_SERVICE_ACCOUNT_JSON absent (auth locale ou OAuth requis)")

print("\n═══ Suite ═══")
print("  python db/verify_db.py              # détail base")
print("  uvicorn api.app:app --port 8001     # API locale")
print("  BAM_DEPTS=Alibori python scripts/run_collecte_hebdo.py  # smoke collecte")
print()

#!/usr/bin/env python3
"""BAM · Test environnement — python test_connexion.py"""
import sys
print("\n═══ BAM · Verification environnement ═══\n")

# Python
v = sys.version_info
ok_py = v.major >= 3 and v.minor >= 10
print(f"{'✓' if ok_py else '✗'}  Python {v.major}.{v.minor}.{v.micro}")

# Libs
for lib, pkg in [("requests","requests"),("psycopg2","psycopg2-binary"),
                 ("dotenv","python-dotenv"),("numpy","numpy"),
                 ("boto3","boto3"),("ee","earthengine-api")]:
    try: __import__(lib); print(f"✓  {lib}")
    except ImportError: print(f"✗  {lib}  →  pip install {pkg}")

# .env + PostgreSQL
print()
try:
    from dotenv import load_dotenv; import os, psycopg2
    load_dotenv()
    url = os.getenv("DATABASE_URL","")
    print(f"✓  .env  →  {url[:40]}..." if url else "✗  DATABASE_URL manquante dans .env")
    if url:
        conn = psycopg2.connect(url, connect_timeout=5)
        cur  = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM sites;")
        nb = cur.fetchone()[0]
        conn.close()
        print(f"✓  PostgreSQL  →  {nb} sites en base")
except Exception as e:
    print(f"✗  PostgreSQL : {e}\n   → docker compose up -d")

print("\n═══ Si tout est ✓ → python main.py --no-gee ═══\n")

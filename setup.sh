#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════
#  BAM · BeninAquaMap — Setup Mac
#  Usage : chmod +x setup.sh && ./setup.sh
#  Testé : macOS M1/M2/Intel · Python 3.10+
#  NOTE  : rasterio intentionnellement absent (problème GDAL Mac)
# ═══════════════════════════════════════════════════════════════
set -e

GREEN='\033[0;32m'; AMBER='\033[0;33m'; RED='\033[0;31m'
BLUE='\033[0;34m'; BOLD='\033[1m'; DIM='\033[2m'; NC='\033[0m'

ok()   { echo -e "${GREEN}✓${NC}  $1"; }
info() { echo -e "${BLUE}→${NC}  $1"; }
warn() { echo -e "${AMBER}⚠${NC}  $1"; }
fail() { echo -e "${RED}✗${NC}  $1"; exit 1; }
step() { echo -e "\n${BOLD}$1${NC}"; echo -e "${DIM}$(printf '─%.0s' {1..48})${NC}"; }

clear
echo ""
echo -e "  ${GREEN}${BOLD}BAM · BeninAquaMap — Setup${NC}"
echo -e "  ${DIM}Initialisation environnement de développement${NC}"
echo ""
read -p "  Appuyer sur Entrée pour commencer... " _

step "1 · Python"
if ! command -v python3 &>/dev/null; then
  fail "Python3 non trouvé — installer depuis python.org"
fi
PY_FULL=$(python3 --version 2>&1 | awk '{print $2}')
PY_MAJ=$(echo $PY_FULL | cut -d. -f1)
PY_MIN=$(echo $PY_FULL | cut -d. -f2)
if [[ $PY_MAJ -lt 3 ]] || [[ $PY_MAJ -eq 3 && $PY_MIN -lt 10 ]]; then
  fail "Python $PY_FULL détecté — version 3.10+ requise"
fi
ok "Python $PY_FULL"

step "2 · Virtualenv"
if [ -d ".venv" ]; then
  warn ".venv déjà existant — conservé"
else
  python3 -m venv .venv
  ok "Virtualenv créé"
fi
source .venv/bin/activate
ok "Virtualenv activé"

step "3 · Librairies Python"
info "Mise à jour pip..."
pip install --upgrade pip -q
info "Installation des libs BAM..."
pip install -q requests python-dotenv psycopg2-binary earthengine-api numpy pandas boto3 botocore beautifulsoup4 httpx
ok "Toutes les libs installées (sans rasterio — voir README)"

step "4 · Structure dossiers"
for d in collect process db logs data/raw data/processed tests; do
  mkdir -p "$d"
  done
touch collect/__init__.py process/__init__.py db/__init__.py tests/__init__.py
ok "Dossiers créés"

step "5 · Fichiers config"

cat > .gitignore << 'EOF'
.venv/
__pycache__/
*.pyc
.env
data/raw/
logs/
*.log
.DS_Store
*service_account*.json
EOF
ok ".gitignore"

cat > .env.example << 'EOF'
# Copier en .env — NE JAMAIS commiter .env
DATABASE_URL=postgresql://bam_user:bam_dev_2026@localhost:5432/bam_local
GEE_PROJECT=bam-benin-gee
ANTHROPIC_API_KEY=
ELEVENLABS_API_KEY=
EOF
ok ".env.example"

if [ ! -f ".env" ]; then
  cp .env.example .env
  ok ".env créé"
else
  warn ".env existant — conservé"
fi

step "6 · Docker Compose"
cat > docker-compose.yml << 'EOF'
# BAM · PostgreSQL + Grafana
# Lancer : docker compose up -d
# Grafana : http://localhost:3000  (admin / bam_admin)

services:
  postgres:
    image: postgres:16-alpine
    container_name: bam-postgres
    environment:
      POSTGRES_DB:       bam_local
      POSTGRES_USER:     bam_user
      POSTGRES_PASSWORD: bam_dev_2026
    ports:
      - "5432:5432"
    volumes:
      - pg_data:/var/lib/postgresql/data
      - ./db/schema.sql:/docker-entrypoint-initdb.d/01_schema.sql
      - ./db/seeds.sql:/docker-entrypoint-initdb.d/02_seeds.sql
    restart: unless-stopped
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U bam_user -d bam_local"]
      interval: 5s
      timeout: 5s
      retries: 5

  grafana:
    image: grafana/grafana:10.3.0
    container_name: bam-grafana
    ports:
      - "3000:3000"
    environment:
      GF_SECURITY_ADMIN_PASSWORD: bam_admin
      GF_USERS_ALLOW_SIGN_UP:     "false"
    volumes:
      - grafana_data:/var/lib/grafana
    depends_on:
      postgres:
        condition: service_healthy
    restart: unless-stopped

volumes:
  pg_data:
  grafana_data:
EOF
ok "docker-compose.yml"

step "7 · Schéma SQL"
cat > db/schema.sql << 'EOF'
CREATE TABLE IF NOT EXISTS sites (
    id                     SERIAL PRIMARY KEY,
    nom                    TEXT NOT NULL,
    departement            TEXT NOT NULL,
    commune                TEXT,
    lat                    NUMERIC(9,6) NOT NULL,
    lon                    NUMERIC(9,6) NOT NULL,
    superficie_ha          NUMERIC(10,2),
    cout_activation_m_fcfa NUMERIC(8,1),
    created_at             TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS mesures (
    id            SERIAL PRIMARY KEY,
    site_id       INTEGER NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    date_collecte DATE NOT NULL,
    ndwi          NUMERIC(6,4),
    ndvi          NUMERIC(6,4),
    mndwi         NUMERIC(6,4),
    ph_sol        NUMERIC(4,2),
    carbone_g_kg  NUMERIC(6,2),
    argile_pct    NUMERIC(5,2),
    pluie_7j_mm   NUMERIC(7,2),
    pluie_30j_mm  NUMERIC(7,2),
    humidite_sol  NUMERIC(6,4),
    temp_max_c    NUMERIC(5,2),
    score_total   NUMERIC(5,1),
    priorite      TEXT CHECK(priorite IN ('haute','moyenne','basse')),
    source        TEXT DEFAULT 'collecte',
    created_at    TIMESTAMP DEFAULT NOW(),
    UNIQUE(site_id, date_collecte)
);

CREATE INDEX IF NOT EXISTS idx_mesures_site_date ON mesures(site_id, date_collecte DESC);
CREATE INDEX IF NOT EXISTS idx_mesures_score     ON mesures(score_total DESC);
CREATE INDEX IF NOT EXISTS idx_sites_dept        ON sites(departement);
EOF
ok "db/schema.sql"

step "8 · Seeds — 14 sites"
cat > db/seeds.sql << 'EOF'
INSERT INTO sites (nom, departement, commune, lat, lon, superficie_ha, cout_activation_m_fcfa)
VALUES
  ('Bas-fond de Malanville', 'Alibori',  'Malanville', 11.87, 3.39, 380, 48),
  ('Plaine de Karimama',     'Alibori',  'Karimama',   12.06, 3.18, 210, 32),
  ('Mares de Gogounou',      'Alibori',  'Gogounou',   10.83, 2.83, 145, 28),
  ('Vallee Alibori Sud',     'Borgou',   'Nikki',      10.21, 3.01, 520, 65),
  ('Bas-fond Parakou-Est',   'Borgou',   'Parakou',     9.37, 2.68, 290, 41),
  ('Zone humide N-Dali',     'Borgou',   'N-Dali',      9.86, 2.72, 175, 35),
  ('Vallee Pendjari-Ouest',  'Atacora',  'Materi',     10.70, 1.06, 160, 44),
  ('Bas-fond Tanguieta',     'Atacora',  'Tanguieta',  10.62, 1.27,  95, 52),
  ('Bas-fond de Savalou',    'Collines', 'Savalou',     7.93, 1.97, 445, 55),
  ('Bas-fond de Dassa',      'Collines', 'Dassa',       7.75, 2.19, 310, 47),
  ('Mare de Bohicon',        'Zou',      'Bohicon',     7.18, 2.07, 180, 29),
  ('Zone Djidja-Cove',       'Zou',      'Djidja',      7.34, 1.99, 230, 38),
  ('Bas-fond Grand-Popo',    'Mono',     'Grand-Popo',  6.28, 1.83, 125, 36),
  ('Zone humide Porto-Novo', 'Oueme',    'Porto-Novo',  6.49, 2.61,  70, 85)
ON CONFLICT DO NOTHING;
EOF
ok "db/seeds.sql"

step "9 · collect/meteo.py"
cat > collect/meteo.py << 'EOF'
"""BAM · Open-Meteo — gratuit, sans compte, sans clé"""
import requests

def get_meteo(lat: float, lon: float) -> dict:
    """
    Retourne pluie_7j_mm, temp_max_c, humidite_sol pour un point GPS.
    Exemple : get_meteo(7.93, 1.97)
    """
    try:
        r = requests.get("https://api.open-meteo.com/v1/forecast", params={
            "latitude": lat, "longitude": lon,
            "daily": "precipitation_sum,temperature_2m_max",
            "hourly": "soil_moisture_0_to_7cm",
            "forecast_days": 7, "timezone": "Africa/Porto-Novo"
        }, timeout=15)
        r.raise_for_status()
        d = r.json()
        return {
            "pluie_7j_mm":  round(sum(v or 0 for v in d["daily"]["precipitation_sum"]), 2),
            "temp_max_c":   round(d["daily"]["temperature_2m_max"][0] or 0, 1),
            "humidite_sol": round(d["hourly"]["soil_moisture_0_to_7cm"][0] or 0, 4)
        }
    except Exception as e:
        print(f"  ✗ Open-Meteo : {e}"); return {}

if __name__ == "__main__":
    print("Test Open-Meteo → Savalou"); print("-"*40)
    r = get_meteo(7.93, 1.97)
    if r:
        print(f"  Pluie 7j     : {r['pluie_7j_mm']} mm")
        print(f"  Temp max     : {r['temp_max_c']} C")
        print(f"  Humidite sol : {r['humidite_sol']}")
        print("\n✓ Open-Meteo OK")
    else:
        print("✗ Echec")
EOF
ok "collect/meteo.py"

step "10 · collect/sol.py"
cat > collect/sol.py << 'EOF'
"""
BAM · ISRIC SoilGrids — gratuit, sans compte
ATTENTION : API renvoie valeurs x10 — on divise par 10
"""
import requests

def get_sol(lat: float, lon: float) -> dict:
    """
    Retourne ph_sol, carbone_g_kg, argile_pct.
    Peut prendre 5-15s (serveur ISRIC parfois lent).
    """
    try:
        r = requests.get(
            "https://rest.isric.org/soilgrids/v2.0/properties/query",
            params={"lon": lon, "lat": lat,
                    "property": ["phh2o","soc","clay"],
                    "depth": ["0-5cm"], "value": "mean"},
            timeout=30
        )
        r.raise_for_status()
        p = r.json()["properties"]
        def val(name):
            try: return p[name]["layers"][0]["values"]["mean"] or 0
            except: return 0
        return {
            "ph_sol":       round(val("phh2o") / 10, 2),
            "carbone_g_kg": round(val("soc")   / 10, 2),
            "argile_pct":   round(val("clay")  / 10, 1)
        }
    except Exception as e:
        print(f"  ✗ ISRIC : {e}"); return {}

if __name__ == "__main__":
    print("Test ISRIC → Savalou (peut prendre 10-15s)")
    print("-"*40)
    r = get_sol(7.93, 1.97)
    if r:
        print(f"  pH sol    : {r['ph_sol']}")
        print(f"  Carbone   : {r['carbone_g_kg']} g/kg")
        print(f"  Argile    : {r['argile_pct']} %")
        print("\n✓ ISRIC OK")
    else:
        print("✗ Echec — reessayer dans 1 min")
EOF
ok "collect/sol.py"

step "11 · collect/sentinel.py"
cat > collect/sentinel.py << 'EOF'
"""
BAM · Sentinel-2 via Google Earth Engine
Prerequis : earthengine authenticate (une seule fois)
"""
import os, ee
from datetime import date, timedelta
from dotenv import load_dotenv
load_dotenv()

def init_gee():
    project = os.getenv("GEE_PROJECT", "bam-benin-gee")
    ee.Initialize(project=project)
    print(f"  GEE initialise (projet: {project})")

def get_indices(lat: float, lon: float, radius_km: float = 5) -> dict:
    """
    NDWI, NDVI, MNDWI via Sentinel-2.
    Retourne {} si pas d'image valide.
    NDWI > 0.2 = zone humide.
    """
    zone  = ee.Geometry.Point([lon, lat]).buffer(radius_km * 1000)
    end   = str(date.today())
    start = str(date.today() - timedelta(days=90))
    col = (ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
           .filterBounds(zone).filterDate(start, end)
           .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 15)))
    n = col.size().getInfo()
    if n == 0:
        print("  ⚠ 0 image S2 valide sur 90j"); return {}
    print(f"  {n} images S2 → composite median")
    img = col.median()
    r = img.addBands([
        img.normalizedDifference(["B3","B8"]).rename("NDWI"),
        img.normalizedDifference(["B8","B4"]).rename("NDVI"),
        img.normalizedDifference(["B3","B11"]).rename("MNDWI"),
    ]).select(["NDWI","NDVI","MNDWI"]).reduceRegion(
        reducer=ee.Reducer.mean(), geometry=zone, scale=10, maxPixels=1e9
    ).getInfo()
    if not r.get("NDWI"): return {}
    return {k: round(v, 4) for k, v in r.items()}

if __name__ == "__main__":
    print("Test Sentinel-2 → Savalou (10-30s)"); print("-"*40)
    try:
        init_gee()
        r = get_indices(7.93, 1.97)
        if r:
            for k,v in r.items(): print(f"  {k} : {v}")
            print("\n✓ Sentinel-2 OK")
        else:
            print("✗ Pas de donnees")
    except Exception as e:
        print(f"✗ {e}\n→ earthengine authenticate")
EOF
ok "collect/sentinel.py"

step "12 · collect/chirps.py"
cat > collect/chirps.py << 'EOF'
"""
BAM · Precipitations historiques — CHIRPS / Open-Meteo proxy
Phase 1 : Open-Meteo (historique 30j) comme proxy CHIRPS
Phase 2 VPS : rasterio + AWS S3 pour CHIRPS natif
"""
import requests

def get_pluie_30j(lat: float, lon: float) -> dict:
    """Cumul pluie sur 30 jours (Open-Meteo proxy)."""
    try:
        r = requests.get("https://api.open-meteo.com/v1/forecast", params={
            "latitude": lat, "longitude": lon,
            "daily": "precipitation_sum",
            "past_days": 30, "forecast_days": 0,
            "timezone": "Africa/Porto-Novo"
        }, timeout=15)
        r.raise_for_status()
        vals = r.json()["daily"]["precipitation_sum"]
        return {"pluie_30j_mm": round(sum(v or 0 for v in vals), 2)}
    except Exception as e:
        print(f"  ✗ Pluie 30j : {e}"); return {"pluie_30j_mm": None}

if __name__ == "__main__":
    print("Test pluie 30j → Savalou"); print("-"*40)
    r = get_pluie_30j(7.93, 1.97)
    print(f"  Pluie 30j : {r.get('pluie_30j_mm')} mm")
    print("\n✓ OK" if r.get("pluie_30j_mm") else "✗ Echec")
EOF
ok "collect/chirps.py"

step "13 · db/connexion.py"
cat > db/connexion.py << 'EOF'
"""BAM · PostgreSQL"""
import os, psycopg2
from datetime import date
from dotenv import load_dotenv
load_dotenv()

def get_conn():
    return psycopg2.connect(os.getenv("DATABASE_URL"))

def lister_sites() -> list:
    conn = get_conn(); cur = conn.cursor()
    cur.execute("SELECT id,nom,departement,commune,lat,lon,superficie_ha FROM sites ORDER BY id")
    rows = cur.fetchall(); cur.close(); conn.close()
    return [{"id":r[0],"nom":r[1],"departement":r[2],"commune":r[3],"lat":r[4],"lon":r[5],"superficie_ha":r[6]} for r in rows]

def sauvegarder_mesure(site_id: int, data: dict) -> bool:
    try:
        conn = get_conn(); cur = conn.cursor()
        cur.execute("""
            INSERT INTO mesures
              (site_id,date_collecte,ndwi,ndvi,mndwi,ph_sol,carbone_g_kg,argile_pct,
               pluie_7j_mm,pluie_30j_mm,humidite_sol,temp_max_c,score_total,priorite,source)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (site_id,date_collecte) DO UPDATE SET
              ndwi=EXCLUDED.ndwi, ndvi=EXCLUDED.ndvi,
              pluie_7j_mm=EXCLUDED.pluie_7j_mm, pluie_30j_mm=EXCLUDED.pluie_30j_mm,
              humidite_sol=EXCLUDED.humidite_sol, score_total=EXCLUDED.score_total,
              priorite=EXCLUDED.priorite
        """, (site_id, data.get("date_collecte", date.today()),
              data.get("ndwi"), data.get("ndvi"), data.get("mndwi"),
              data.get("ph_sol"), data.get("carbone_g_kg"), data.get("argile_pct"),
              data.get("pluie_7j_mm"), data.get("pluie_30j_mm"),
              data.get("humidite_sol"), data.get("temp_max_c"),
              data.get("score_total"), data.get("priorite"),
              data.get("source","collecte")))
        conn.commit(); cur.close(); conn.close(); return True
    except Exception as e:
        print(f"  ✗ DB : {e}"); return False
EOF
ok "db/connexion.py"

step "14 · process/scoring.py"
cat > process/scoring.py << 'EOF'
"""BAM · Score composite sur 100 (5 criteres ponderes)"""

def calculer_score(indices: dict, sol: dict, meteo: dict) -> dict:
    ndwi   = indices.get("ndwi", 0)
    humide = meteo.get("humidite_sol", 0.2)
    s_eau  = max(0, min((ndwi+1)/2*100, 100)) * 0.7 + min(humide/0.5*100, 100) * 0.3
    ph     = sol.get("ph_sol", 6.5)
    carb   = sol.get("carbone_g_kg", 10)
    argile = sol.get("argile_pct", 25)
    s_sol  = max(0, 100-abs(ph-6.5)*30)*0.3 + min(carb/20*100,100)*0.4 + (80 if 15<=argile<=40 else 40)*0.3
    total  = s_eau*0.30 + s_sol*0.25 + 50*0.20 + 50*0.15 + 50*0.10
    return {
        "score_total": round(total, 1),
        "priorite": "haute" if total>=75 else "moyenne" if total>=50 else "basse"
    }
EOF
ok "process/scoring.py"

step "15 · main.py"
cat > main.py << 'EOF'
#!/usr/bin/env python3
"""
BAM · Pipeline principal
Usage :
  python main.py           # avec Sentinel-2
  python main.py --no-gee  # sans satellite (test rapide)
"""
import sys
from datetime import date
from collect.meteo   import get_meteo
from collect.sol     import get_sol
from collect.chirps  import get_pluie_30j
from process.scoring import calculer_score
from db.connexion    import lister_sites, sauvegarder_mesure

USE_GEE = "--no-gee" not in sys.argv
if USE_GEE:
    from collect.sentinel import init_gee, get_indices

def run():
    print("="*52)
    print(f"  BAM · {date.today()} · GEE={'on' if USE_GEE else 'off'}")
    print("="*52)
    if USE_GEE:
        print("\n→ GEE...")
        try: init_gee()
        except Exception as e:
            print(f"  ⚠ GEE off : {e}")
            global USE_GEE; USE_GEE = False
    sites = lister_sites()
    if not sites:
        print("✗ Aucun site — docker compose up -d ?"); return
    print(f"\n{len(sites)} sites a traiter\n")
    ok = 0
    for i, s in enumerate(sites, 1):
        print(f"[{i:02d}/{len(sites)}] {s['nom']} ({s['departement']})")
        meteo = get_meteo(s["lat"], s["lon"])
        if not meteo: print("  ✗ meteo — ignore\n"); continue
        sol   = get_sol(s["lat"], s["lon"]) or {"ph_sol":6.5,"carbone_g_kg":10,"argile_pct":25}
        p30   = get_pluie_30j(s["lat"], s["lon"])
        idx   = get_indices(s["lat"], s["lon"]) if USE_GEE else {}
        score = calculer_score(idx or {"ndwi":0.2}, sol, meteo)
        saved = sauvegarder_mesure(s["id"], {**idx,**sol,**meteo,**p30,
                "score_total":score["score_total"],"priorite":score["priorite"]})
        if saved:
            ndwi_s = f"NDWI={idx.get('ndwi','—')}" if idx else "NDWI=—"
            print(f"  ✓ {ndwi_s} | Score={score['score_total']}/100 | {score['priorite'].upper()}")
            ok += 1
        print()
    print("="*52)
    print(f"  ✓ {ok}/{len(sites)} sites traites")
    print("="*52)

if __name__ == "__main__": run()
EOF
ok "main.py"

step "16 · test_connexion.py"
cat > test_connexion.py << 'EOF'
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
EOF
ok "test_connexion.py"

step "17 · requirements.txt + README"
cat > requirements.txt << 'EOF'
requests>=2.31
python-dotenv>=1.0
psycopg2-binary>=2.9
earthengine-api>=0.1.390
numpy>=1.26
pandas>=2.1
boto3>=1.34
botocore>=1.34
beautifulsoup4>=4.12
httpx>=0.27
# rasterio : installer sur VPS Linux uniquement (probleme GDAL sur Mac)
EOF

cat > README.md << 'EOF'
# BAM · BeninAquaMap

## Demarrage rapide

```bash
docker compose up -d        # base + grafana
source .venv/bin/activate   # virtualenv
python test_connexion.py    # tout verifier
python main.py --no-gee     # premier run sans satellite
python main.py              # run complet avec Sentinel-2
```


## Verifier les donnees

```bash
docker compose exec postgres psql -U bam_user -d bam_local \
  -c "SELECT s.nom, m.score_total, m.priorite FROM mesures m
      JOIN sites s ON s.id=m.site_id ORDER BY m.score_total DESC LIMIT 5;"
```

## Note rasterio

rasterio est absent des deps Mac (conflict GDAL).
Il sera installe sur le VPS Linux en phase 2.
En phase 1, CHIRPS passe par Open-Meteo comme proxy.
EOF
ok "requirements.txt + README.md"

echo ""
echo -e "${GREEN}${BOLD}═══ Setup termine ══════════════════════════════${NC}"
echo ""
echo -e "  ${AMBER}Etape suivante — dans l'ordre :${NC}"
echo ""
echo -e "  1.  ${DIM}docker compose up -d${NC}"
echo -e "  2.  ${DIM}python test_connexion.py${NC}"
echo -e "  3.  ${DIM}python collect/meteo.py${NC}         # teste Open-Meteo"
echo -e "  4.  ${DIM}python collect/sol.py${NC}           # teste ISRIC"
echo -e "  5.  ${DIM}python main.py --no-gee${NC}         # pipeline sans satellite"
echo -e "  6.  ${DIM}earthengine authenticate${NC}        # puis python main.py"
echo ""
echo -e "${GREEN}${BOLD}════════════════════════════════════════════════${NC}"
echo ""

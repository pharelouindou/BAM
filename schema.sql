-- DEPRECATED — schéma réel : voir db/schema.sql (indices, scores, vue mesures)
-- Sites
CREATE TABLE sites (
    id            SERIAL PRIMARY KEY,
    nom           TEXT NOT NULL,
    departement   TEXT NOT NULL,
    commune       TEXT,
    lat           NUMERIC(9,6) NOT NULL,
    lon           NUMERIC(9,6) NOT NULL,
    superficie_ha NUMERIC(10,2)
);

-- Mesures brutes par site et par date
CREATE TABLE mesures (
    id            BIGSERIAL PRIMARY KEY,
    site_id       INTEGER NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    date_collecte DATE NOT NULL,

    -- Satellite
    ndwi          NUMERIC(6,4),
    ndvi          NUMERIC(6,4),
    mndwi         NUMERIC(6,4),

    -- Sol
    ph_sol        NUMERIC(4,2),
    carbone_g_kg  NUMERIC(6,2),
    argile_pct    NUMERIC(5,2),

    -- Météo
    pluie_7j_mm   NUMERIC(7,2),
    pluie_30j_mm  NUMERIC(7,2),
    humidite_sol  NUMERIC(6,4),
    temp_max_c    NUMERIC(5,2),

    source        TEXT DEFAULT 'inconnu',
    UNIQUE(site_id, date_collecte, source)
);

-- Scores calculés
CREATE TABLE scores (
    id           BIGSERIAL PRIMARY KEY,
    site_id      INTEGER NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    date_calcul  DATE NOT NULL,
    s_eau        NUMERIC(5,1),
    s_sol        NUMERIC(5,1),
    s_pluie      NUMERIC(5,1),
    s_temp       NUMERIC(5,1),
    score_total  NUMERIC(5,1) NOT NULL,
    priorite     TEXT CHECK(priorite IN ('haute', 'moyenne', 'basse')),
    UNIQUE(site_id, date_calcul)
);

-- Grille nationale
CREATE TABLE grille_nationale (
    id_grille    TEXT PRIMARY KEY,
    lat          NUMERIC(9,6) NOT NULL,
    lon          NUMERIC(9,6) NOT NULL,
    departement  TEXT,
    elevation_m  NUMERIC(7,1),
    pente_pct    NUMERIC(6,3),
    ph_sol       NUMERIC(4,2),
    carbone_g_kg NUMERIC(6,2),
    argile_pct   NUMERIC(5,2),
    pluie_30j_mm NUMERIC(7,2),
    humidite_sol NUMERIC(6,4),
    temp_max_c   NUMERIC(5,2),
    ndwi         NUMERIC(6,4),
    score_total  NUMERIC(5,1),
    est_humide   BOOLEAN DEFAULT FALSE,
    priorite     TEXT CHECK(priorite IN ('haute', 'moyenne', 'basse')),
    date_analyse DATE
);
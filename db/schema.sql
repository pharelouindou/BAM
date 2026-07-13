-- ── Sites ─────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS sites (
    id            SERIAL PRIMARY KEY,
    nom           TEXT NOT NULL,
    departement   TEXT NOT NULL,
    commune       TEXT,
    lat           NUMERIC(9,6) NOT NULL,
    lon           NUMERIC(9,6) NOT NULL,
    superficie_ha NUMERIC(10,2),
    created_at    TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_sites_dept ON sites(departement);

-- ── Indices bruts (une ligne = un indice, une source, une date) ────────────
-- Applicable aux 14 sites connus. La grille utilise grille_nationale directement.
CREATE TABLE IF NOT EXISTS indices (
    id            BIGSERIAL PRIMARY KEY,
    site_id       INTEGER NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    date_collecte DATE NOT NULL,

    -- Catégorie : satellite | sol | meteo | pluie
    categorie     TEXT NOT NULL
        CHECK(categorie IN ('satellite', 'sol', 'meteo', 'pluie')),

    nom_indice    TEXT NOT NULL,   -- ndwi, ndvi, ph_sol, pluie_7j_mm, …
    valeur        NUMERIC(10,4),

    -- Traçabilité
    source        TEXT NOT NULL DEFAULT 'inconnu',
    qualite       TEXT NOT NULL DEFAULT 'ok'
        CHECK(qualite IN ('ok', 'estime', 'defaut', 'erreur')),
    created_at    TIMESTAMP DEFAULT NOW(),

    UNIQUE(site_id, date_collecte, nom_indice, source)
);

CREATE INDEX IF NOT EXISTS idx_indices_site     ON indices(site_id, date_collecte DESC);
CREATE INDEX IF NOT EXISTS idx_indices_nom      ON indices(nom_indice);
CREATE INDEX IF NOT EXISTS idx_indices_categorie ON indices(categorie);

-- ── Scores calculés (une ligne = un score daté par site) ──────────────────
CREATE TABLE IF NOT EXISTS scores (
    id             BIGSERIAL PRIMARY KEY,
    site_id        INTEGER NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    date_calcul    DATE NOT NULL,

    -- Sous-scores intermédiaires (audit du calcul)
    s_eau          NUMERIC(5,1),   -- contribution eau/satellite (40 %)
    s_sol          NUMERIC(5,1),   -- contribution sol           (30 %)
    s_pluie        NUMERIC(5,1),   -- contribution pluie         (20 %)
    s_temp         NUMERIC(5,1),   -- contribution température   (10 %)
    score_total    NUMERIC(5,1) NOT NULL,

    priorite       TEXT NOT NULL
        CHECK(priorite IN ('haute', 'moyenne', 'basse')),
    avec_satellite BOOLEAN DEFAULT FALSE,  -- NDWI réel ou valeur neutre ?
    -- Source retenue pour le score (et pour la vue mesures)
    source_satellite TEXT,  -- ex. Sentinel-2-GEE, AppEEARS, ORNL, no-sat
    version_algo   TEXT DEFAULT 'v2',
    created_at     TIMESTAMP DEFAULT NOW(),

    UNIQUE(site_id, date_calcul)
);

CREATE INDEX IF NOT EXISTS idx_scores_score    ON scores(score_total DESC);
CREATE INDEX IF NOT EXISTS idx_scores_priorite ON scores(priorite);
CREATE INDEX IF NOT EXISTS idx_scores_site     ON scores(site_id, date_calcul DESC);

-- ── Vue de compatibilité : reconstitue la structure plate ancienne ─────────
-- Utilisée par l'API sans modification. Éliminée si l'API est refactorisée.
CREATE OR REPLACE VIEW mesures AS
SELECT
    sc.id,
    sc.site_id,
    sc.date_calcul AS date_collecte,
    /* Satellite : priorité à la source retenue pour le score, sinon n'importe quelle mesure */
    COALESCE(
        MAX(CASE WHEN i.nom_indice = 'ndwi'  AND i.categorie = 'satellite'
            AND sc.source_satellite IS NOT NULL AND i.source = sc.source_satellite
            THEN i.valeur END),
        MAX(CASE WHEN i.nom_indice = 'ndwi'  AND i.categorie = 'satellite' THEN i.valeur END)
    ) AS ndwi,
    COALESCE(
        MAX(CASE WHEN i.nom_indice = 'ndvi'  AND i.categorie = 'satellite'
            AND sc.source_satellite IS NOT NULL AND i.source = sc.source_satellite
            THEN i.valeur END),
        MAX(CASE WHEN i.nom_indice = 'ndvi'  AND i.categorie = 'satellite' THEN i.valeur END)
    ) AS ndvi,
    COALESCE(
        MAX(CASE WHEN i.nom_indice = 'mndwi' AND i.categorie = 'satellite'
            AND sc.source_satellite IS NOT NULL AND i.source = sc.source_satellite
            THEN i.valeur END),
        MAX(CASE WHEN i.nom_indice = 'mndwi' AND i.categorie = 'satellite' THEN i.valeur END)
    ) AS mndwi,
    MAX(CASE WHEN i.nom_indice = 'ph_sol'       AND i.categorie = 'sol'   THEN i.valeur END)   AS ph_sol,
    MAX(CASE WHEN i.nom_indice = 'carbone_g_kg' AND i.categorie = 'sol'   THEN i.valeur END)   AS carbone_g_kg,
    MAX(CASE WHEN i.nom_indice = 'argile_pct'   AND i.categorie = 'sol'   THEN i.valeur END)   AS argile_pct,
    MAX(CASE WHEN i.nom_indice = 'pluie_7j_mm'  AND i.categorie = 'meteo' THEN i.valeur END)   AS pluie_7j_mm,
    MAX(CASE WHEN i.nom_indice = 'pluie_30j_mm' AND i.categorie = 'pluie' THEN i.valeur END)   AS pluie_30j_mm,
    MAX(CASE WHEN i.nom_indice = 'humidite_sol' AND i.categorie = 'meteo' THEN i.valeur END)   AS humidite_sol,
    MAX(CASE WHEN i.nom_indice = 'temp_max_c'   AND i.categorie = 'meteo' THEN i.valeur END)   AS temp_max_c,
    sc.s_eau,
    sc.s_sol,
    sc.s_pluie,
    sc.s_temp,
    sc.score_total,
    sc.priorite,
    COALESCE(
        sc.source_satellite,
        CASE WHEN sc.avec_satellite THEN 'AppEEARS' ELSE 'no-sat' END
    ) AS source,
    sc.created_at
FROM scores sc
LEFT JOIN indices i
       ON i.site_id       = sc.site_id
      AND i.date_collecte = sc.date_calcul
GROUP BY
    sc.id, sc.site_id, sc.date_calcul, sc.source_satellite,
    sc.s_eau, sc.s_sol, sc.s_pluie, sc.s_temp,
    sc.score_total, sc.priorite, sc.avec_satellite, sc.created_at;

-- ── Grille nationale ──────────────────────────────────────────────────────
-- Structure géographique plate : efficace pour les 7440+ points de la grille.
CREATE TABLE IF NOT EXISTS grille_nationale (
    id_grille       TEXT PRIMARY KEY,
    lat             NUMERIC(9,6) NOT NULL,
    lon             NUMERIC(9,6) NOT NULL,
    departement     TEXT,
    commune         TEXT,
    arrondissement  TEXT,
    localite        TEXT,

    -- Relief SRTM
    elevation_m     NUMERIC(7,1),
    pente_pct       NUMERIC(6,3),
    twi             NUMERIC(6,3),

    -- Sol ISRIC
    ph_sol          NUMERIC(4,2),
    carbone_g_kg    NUMERIC(6,2),
    argile_pct      NUMERIC(5,2),

    -- Météo / Pluie
    pluie_30j_mm    NUMERIC(7,2),
    humidite_sol    NUMERIC(6,4),
    temp_max_c      NUMERIC(5,2),

    -- Satellite (rempli quand quota dispo)
    ndwi            NUMERIC(6,4),
    ndvi            NUMERIC(6,4),

    -- Scores et classification
    score_eau       NUMERIC(5,1),
    score_total     NUMERIC(5,1),
    est_humide      BOOLEAN DEFAULT FALSE,
    est_bas_fond    BOOLEAN DEFAULT FALSE,
    priorite        TEXT CHECK(priorite IN ('haute', 'moyenne', 'basse', 'non_evalue')),

    -- Traçabilité
    source_ndwi     TEXT DEFAULT 'non_collecte',
    date_analyse    DATE,
    created_at      TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_grille_dept     ON grille_nationale(departement);
CREATE INDEX IF NOT EXISTS idx_grille_commune  ON grille_nationale(commune);
CREATE INDEX IF NOT EXISTS idx_grille_humide   ON grille_nationale(est_humide);
CREATE INDEX IF NOT EXISTS idx_grille_bas_fond ON grille_nationale(est_bas_fond);
CREATE INDEX IF NOT EXISTS idx_grille_score    ON grille_nationale(score_total DESC NULLS LAST);
CREATE INDEX IF NOT EXISTS idx_grille_latlon   ON grille_nationale(lat, lon);

-- ── Historique journalier de la grille ───────────────────────────────────
-- Une ligne par point et par date_collecte pour suivre l'évolution dans Grafana.
CREATE TABLE IF NOT EXISTS grille_historique_journalier (
    id              SERIAL PRIMARY KEY,
    id_grille       TEXT NOT NULL REFERENCES grille_nationale(id_grille) ON DELETE CASCADE,
    date_collecte   DATE NOT NULL,
    departement     TEXT,
    commune         TEXT,
    lat             NUMERIC(9,6),
    lon             NUMERIC(9,6),
    elevation_m     NUMERIC(7,1),
    pente_pct       NUMERIC(6,3),
    twi             NUMERIC(6,3),
    ph_sol          NUMERIC(4,2),
    carbone_g_kg    NUMERIC(6,2),
    argile_pct      NUMERIC(5,2),
    pluie_30j_mm    NUMERIC(7,2),
    humidite_sol    NUMERIC(6,4),
    temp_max_c      NUMERIC(5,2),
    ndwi            NUMERIC(6,4),
    ndvi            NUMERIC(6,4),
    score_eau       NUMERIC(5,1),
    score_total     NUMERIC(5,1),
    est_humide      BOOLEAN,
    est_bas_fond    BOOLEAN,
    priorite        TEXT,
    source_ndwi     TEXT,
    created_at      TIMESTAMP DEFAULT NOW(),
    UNIQUE(id_grille, date_collecte)
);

CREATE INDEX IF NOT EXISTS idx_grille_hist_date    ON grille_historique_journalier(date_collecte);
CREATE INDEX IF NOT EXISTS idx_grille_hist_dept    ON grille_historique_journalier(departement);
CREATE INDEX IF NOT EXISTS idx_grille_hist_commune ON grille_historique_journalier(commune);
CREATE INDEX IF NOT EXISTS idx_grille_hist_point   ON grille_historique_journalier(id_grille, date_collecte DESC);

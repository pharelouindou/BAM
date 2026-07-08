INSERT INTO sites (nom, departement, commune, lat, lon, superficie_ha)
VALUES
  ('Bas-fond de Malanville', 'Alibori',  'Malanville', 11.87, 3.39, 380),
  ('Plaine de Karimama',     'Alibori',  'Karimama',   12.06, 3.18, 210),
  ('Mares de Gogounou',      'Alibori',  'Gogounou',   10.83, 2.83, 145),
  ('Vallee Alibori Sud',     'Borgou',   'Nikki',      10.21, 3.01, 520),
  ('Bas-fond Parakou-Est',   'Borgou',   'Parakou',     9.37, 2.68, 290),
  ('Zone humide N-Dali',     'Borgou',   'N-Dali',      9.86, 2.72, 175),
  ('Vallee Pendjari-Ouest',  'Atacora',  'Materi',     10.70, 1.06, 160),
  ('Bas-fond Tanguieta',     'Atacora',  'Tanguieta',  10.62, 1.27,  95),
  ('Bas-fond de Savalou',    'Collines', 'Savalou',     7.93, 1.97, 445),
  ('Bas-fond de Dassa',      'Collines', 'Dassa',       7.75, 2.19, 310),
  ('Mare de Bohicon',        'Zou',      'Bohicon',     7.18, 2.07, 180),
  ('Zone Djidja-Cove',       'Zou',      'Djidja',      7.34, 1.99, 230),
  ('Bas-fond Grand-Popo',    'Mono',     'Grand-Popo',  6.28, 1.83, 125),
  ('Zone humide Porto-Novo', 'Oueme',    'Porto-Novo',  6.49, 2.61,  70)
ON CONFLICT DO NOTHING;

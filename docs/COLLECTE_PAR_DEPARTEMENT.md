# BAM — Collecte des données **département par département**

Ici, **« département par département »** signifie l’**ordre d’exécution de la collecte** (relief, sol, météo, pluie, scores sur la grille nationale), **pas** seulement un découpage administratif sur le papier.

- **Ordre** : alphabétique (Alibori → Zou), **une vague de collecte par département** avant de passer au suivant.
- **Filtre technique** dans le code : le champ `departement` de la table `grille_nationale` et l’option  
`python process/enrichir_grille.py --dept "NomDuDepartement"`.
- **Échelles** (ville, commune, arrondissement, quartier, village) servent à **cadrer le terrain, le reporting et la priorisation** ; la maille informatique actuelle reste la **grille 0,05°** (points avec `departement` affecté).
docker-compose exec postgres psql -U bam_user -d bam_local -c "
SELECT COUNT(*) AS nb_points
FROM grille_nationale;
"ts de grille de ce département (APIs : Open-Elevation, ISRIC, Open-Meteo, pluie, etc.).

1. Vérifier les **résultats** (scores, bas-fonds, cohérence) — Grafana / SQL / API.
2. (Optionnel) Documenter le **périmètre humain** : communes / arrondissements / quartiers ou villages couverts *par cette vague*, pour le rapport de terrain.

**Commande type (grille nationale) :**

```bash
# Remplacer par le nom exact du département (comme en base : ex. "Collines")
python process/enrichir_grille.py --dept "Alibori"
# Puis itérer limit si besoin : --limit 100
```

**Sites « pilotes » (14 sites connus) :** `python main.py` (ou `main.py --no-sat`) — indépendant de la découpe par département, sauf si vous filtrez ailleurs.

---

## Check-list commune à chaque département

Pour chaque vague (A à L), cocher quand c’est fait :

- **Collecte grille** lancée pour le département (`--dept` + reprise si coupure réseau).
- **Contrôle** : points enrichis, pas d’anomalie massive sur scores / `date_analyse`.
- **Périmètre terrain** (facultatif mais utile pour le rapport) : rappel des **communes / arrondissements** concernés, **quartiers** (villes) ou **villages** (ruraux) où la phase terrain ou la communication s’applique.

---

## Tâche A — Alibori (collecte)

- `enrichir_grille.py --dept "Alibori"` (ou lots avec `--limit`)
- Vérif. données + synthèse
- (Rapport) communes / arr. / quartiers & villages ciblés

**Préfecture :** Kandi

---

## Tâche B — Atacora (collecte)

- Collecte grille
- Vérif.
- Périmètre terrain (optionnel)

**Préfecture :** Natitingou

---

## Tâche C — Atlantique (collecte)

- Collecte grille
- Vérif. (*zones côtières / humides* — attention biais vents / salinité dans l’interprétation)
- Périmètre terrain (optionnel)

**Préfecture :** Allada

---

## Tâche D — Borgou (collecte)

- Collecte grille
- Vérif.
- Périmètre terrain (optionnel)

**Préfecture :** Parakou

---

## Tâche E — Collines (collecte)

- Collecte grille
- Vérif.
- Périmètre terrain (optionnel)

**Préfecture :** Savalou (site témoin *Bas-fond de Savalou* dans BAM)

---

## Tâche F — Couffo (collecte)

- Collecte grille
- Vérif.
- Périmètre terrain (optionnel)

**Préfecture :** Aplahoué

---

## Tâche G — Donga (collecte)

- Collecte grille
- Vérif.
- Périmètre terrain (optionnel)

**Préfecture :** Djougou

---

## Tâche H — Littoral (collecte)

- Collecte grille
- Vérif. (densité urbaine — beaucoup de points en milieu bâti)
- Périmètre : **quartiers** Cotonou / voisins si rapport terrain

**Préfecture :** Cotonou

---

## Tâche I — Mono (collecte)

- Collecte grille
- Vérif.
- Périmètre terrain (optionnel)

**Préfecture :** Lokossa

---

## Tâche J — Ouémé (collecte)

- Collecte grille
- Vérif.
- Périmètre terrain (optionnel)

**Préfecture :** Porto-Novo

---

## Tâche K — Plateau (collecte)

- Collecte grille
- Vérif.
- Périmètre terrain (optionnel)

**Préfecture :** Pobè

---

## Tâche L — Zou (collecte)

- Collecte grille
- Vérif.
- Périmètre terrain (optionnel)

**Préfecture :** Abomey (ex. communes Bohicon, Djidja — sites BAM possibles)

---

## Synthèse (suivi de collecte)


| Département | Vague collecte terminée (oui/non) | Nb points enrichis (approx.) | Commentaire réseau / ISRIC / remarques |
| ----------- | --------------------------------- | ---------------------------- | -------------------------------------- |
| Alibori     | oui                               |                              |                                        |
| Atacora     |                                   |                              |                                        |
| …           |                                   |                              |                                        |


**Référence données :** [INSAE](https://www.insae.bj/) (77 communes au total) pour le cadrage *terrain* ; **BAM** stocke la couverture via `grille_nationale.departement` + enrichissement.

---

*Dernière précision : si une personne disait seulement « département par département », ici c’est bien **enchaîner les collectes de données** dans cet ordre, pas seulement lister des divisions administratives.*
DEPTS=("Alibori" "Atacora" "Atlantique" "Borgou" "Collines" "Couffo" "Donga" "Littoral" "Mono" "Oueme" "Plateau" "Zou")

for dept in "${DEPTS[@]}"; do
  echo "=== Communes: $dept ==="
  python process/enrichir_communes_geojson.py --dept "$dept"

  echo "=== Relief / sol / météo / TWI: $dept ==="
  python process/enrichir_grille.py --dept "$dept"

  echo "=== Satellite GEE + historique journalier: $dept ==="
  python process/analyser_grille.py --dept "$dept" --force
done
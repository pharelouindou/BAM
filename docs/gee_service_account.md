# Authentification GEE via Compte de Service (Render / VPS)

Sur Render, la commande `earthengine authenticate` (OAuth interactif) n'est pas utilisable.
Il faut utiliser un **compte de service GEE** avec un fichier JSON de credentials.

## 1. Créer un compte de service Google

1. Aller sur [console.cloud.google.com](https://console.cloud.google.com)
2. Sélectionner le projet GEE (`bam-benin-gee`)
3. **IAM & Admin → Comptes de service → Créer**
4. Nom : `bam-gee-runner`
5. Télécharger la clé JSON → garder ce fichier en sécurité (ne jamais committer !)

## 2. Enregistrer le compte de service dans GEE

```bash
# Depuis un terminal local avec earthengine installé
earthengine acl set -u bam-gee-runner@bam-benin-gee.iam.gserviceaccount.com -r reader
```

Ou via [code.earthengine.google.com](https://code.earthengine.google.com) → Settings → Assets → Share.

## 3. Injecter la clé JSON dans Render

Dans le **Dashboard Render → bam-api / bam-pipeline → Environment** :

- Clé : `GEE_SERVICE_ACCOUNT_JSON`
- Valeur : **le contenu entier du fichier JSON** (copier-coller)

## 4. Modifier `collect/gee_sentinel.py` pour utiliser le compte de service

Le fichier a déjà été mis à jour pour lire `GEE_SERVICE_ACCOUNT_JSON` automatiquement
(voir la fonction `_init_gee()` dans `collect/gee_sentinel.py`).

## Sécurité

- Ne jamais committer le fichier `.json` dans le dépôt Git
- Ajouter `*.json` dans `.gitignore` si nécessaire (hors `package.json`)
- Sur Render, les variables d'environnement sont chiffrées au repos

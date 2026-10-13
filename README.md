# EduPilot — ERP de gestion scolaire

EduPilot est une application web multi-établissements de gestion scolaire et universitaire, développée avec Flask et déployée sur un VPS OVH avec Docker, Gunicorn et Traefik. Interface en français. Éditeur : LMurbs.

## Accès
- Site : https://edupilot.ci
- Connexion : https://edupilot.ci/login
- Super Admin : compte créé manuellement avec `scripts/bootstrap_superadmin.py`. Aucun compte par défaut, aucun identifiant public.

## Fonctionnalités
- Gestion multi-établissements, abonnements et paramètres.
- Comptes et rôles : Super Admin, administrateur d'établissement, administratif, enseignant, étudiant et parent.
- Classes, années, campus, matières, enseignements et emplois du temps.
- Évaluations, notes, coefficients, bulletins et publications.
- Présences, documents, notifications et historique des opérations.
- Import d'élèves par fichier CSV ou XLSX et prise en charge de fichiers joints.

## Infrastructure VPS
- Code : `/opt/apps/edupilot`
- Compose : `docker-compose.vps.yml`
- Conteneur : `edupilot`
- Base SQLite persistante : `/opt/apps/edupilot/data/edupilot.db`
- Documents persistants : `/opt/apps/edupilot/data/uploads/`
- Réseau Docker partagé : `proxy`
- TLS : certificat Let's Encrypt géré par le Traefik déjà installé sur le VPS.
- Configuration privée : `.env` (non versionné).

Le démarrage de l'application n'ajoute **aucune école, utilisateur ou mot de passe préconfiguré**. Le schéma de base est créé automatiquement si nécessaire.

## Mettre à jour la production

Se connecter au VPS, puis :

```bash
cd /opt/apps/edupilot
git status --short
git pull --ff-only origin main
docker compose -f docker-compose.vps.yml config --quiet
docker compose -f docker-compose.vps.yml up -d --build --no-deps edupilot
docker compose -f docker-compose.vps.yml ps
curl -fsS https://edupilot.ci/health
```

Ne jamais supprimer `data/`, `.env`, ni utiliser `docker compose down -v` pour une mise à jour.

## Initialiser le Super Admin

```bash
cd /opt/apps/edupilot
docker compose -f docker-compose.vps.yml exec edupilot python scripts/bootstrap_superadmin.py
```

Saisir une adresse e-mail valide et un mot de passe temporaire robuste. Un changement de mot de passe est demandé à la première connexion.

## Tests

```bash
python -m unittest discover -s tests -v
```

Les jeux de données synthétiques nécessaires aux tests sont exclusivement créés dans une base temporaire isolée par `tests/test_smoke.py`.

## Précautions avant la mise en exploitation

L'utilisation avec des données personnelles scolaires nécessite notamment une recette fonctionnelle, une revue de sécurité, une stratégie de sauvegarde externe (base et documents), une politique de restauration, la conformité réglementaire applicable et une surveillance opérationnelle. SQLite est persistant sur le VPS mais une migration PostgreSQL devra être envisagée selon la charge.

Documentation détaillée : [Déploiement VPS](docs/DEPLOIEMENT_VPS.md) et [Roadmap](ROADMAP.md).

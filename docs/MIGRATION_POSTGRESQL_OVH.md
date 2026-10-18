# EduPilot — migration SQLite vers PostgreSQL managé OVH

## Architecture cible

Service PostgreSQL managé OVH **déjà utilisé par Coffria** (service partagé, bases distinctes).
- Hôte : `postgresql-d1be9bc3-oe2bccb52.database.cloud.ovh.net`
- Port : `20184`
- Base EduPilot proposée : `edupilot`
- Compte de service EduPilot proposé : `edupilot_app`
- Base `coffria` et son compte : **aucune modification**.
- Tables partagées dans `public`, chaque établissement isolé par `school_id`.

**État : préparation seulement. Aucun changement de moteur en production.**

## 1. Provisionnement (console OVH)

Dans le service PostgreSQL existant :
1. Créer la base `edupilot`, avec encodage UTF-8 si cette option est proposée.
2. Créer l'utilisateur `edupilot_app` et générer un mot de passe robuste unique.
3. N'accorder l'accès de `edupilot_app` qu'à la base `edupilot`. Vérifier les droits SQL de création de tables/schémas séparément.
4. Ajouter **uniquement l'IP publique du VPS EduPilot** à la liste IP autorisées, si ce n'est pas déjà fait.
5. Exiger TLS et récupérer le certificat CA si requis par l'offre.
6. Ne jamais copier les identifiants Coffria pour EduPilot et ne jamais committer de secret.

Si la console OVH ne permet pas plusieurs bases ou une attribution suffisamment isolée, créer un service séparé plutôt que de partager les identifiants Coffria.

## 2. Connexion test, sans écriture sur Coffria

Depuis le VPS, une fois la nouvelle base et l'utilisateur créés :

```bash
export PGHOST=postgresql-d1be9bc3-oe2bccb52.database.cloud.ovh.net
export PGPORT=20184
export PGDATABASE=edupilot
export PGUSER=edupilot_app
export PGSSLMODE=verify-full
# PGSSLROOTCERT=/chemin/vers/ca.pem  # si nécessaire
# Utiliser PGPASSFILE ou une invite interactive, ne pas écrire le mot de passe dans l'historique shell.
psql -W -c "SELECT current_database(), current_user, version();"
psql -W -c "SELECT count(*) FROM pg_catalog.pg_tables WHERE schemaname='public';"
```

Si la chaîne TLS n'est pas correctement vérifiable avec les autorités système, installer le certificat CA OVH puis fournir `PGSSLROOTCERT`. Ne pas désactiver la validation TLS pour la production.

## 3. Contrôles préalables dans EduPilot

EduPilot utilise actuellement directement `sqlite3` : changer seulement `DATABASE_PATH` ou ajouter `DATABASE_URL` **ne fait pas migrer l'application**. Prévoir une adaptation compatible PostgreSQL, notamment :
- DDL SQLite : `INTEGER PRIMARY KEY`, `PRAGMA`, `BLOB`, `AUTOINCREMENT`, `ON CONFLICT`, types temporels ;
- SQL applicatif : placeholders `?`, `INSERT OR IGNORE`, `lastrowid`, `executescript`, `BEGIN IMMEDIATE`, appels `strftime`, etc. ;
- identifiants, contraintes, séquences PostgreSQL, clés étrangères et données binaires ;
- isolation entre établissements avec contrôle applicatif puis RLS correctement initialisé pour chaque transaction et rôle ;
- sessions Flask : conserver strictement `SECRET_KEY`, le domaine et les attributs des cookies ;
- conserver les identifiants des utilisateurs, hash de mots de passe, `mfa_trusted_devices`, `push_subscriptions`, `notifications`, et les fichiers présents dans les volumes.

## 4. Procédure de bascule (à implémenter et à valider)

1. Inventaire et sauvegarde cohérente SQLite à l'aide de l'API `sqlite3.backup()`, plus sauvegarde des documents.
2. Déployer une version PostgreSQL dans un **environnement de recette isolé**, sans accès des utilisateurs réels ni envois d'e-mails/push de test.
3. Migrer une copie des données, conserver les IDs et vérifier comptes, relations, lignes par table, fichiers, dates, comptes MFA et abonnements push.
4. Tester la connexion des cinq profils, les sessions déjà signées, les autorisations inter-écoles, les séances, les notes, les notifications et les workflows administratifs.
5. Préparer un rollback et les procédures de réconciliation des écritures.
6. Planifier une courte maintenance : arrêter les écritures SQLite, refaire copie/synchronisation finale, contrôler les sommes/volumes, changer explicitement le moteur, tester, rouvrir.
7. Conserver SQLite et les fichiers d'origine hors ligne pour restauration d'urgence.

## 5. Notes importantes

- Ne **jamais** copier ici ni dans GitHub les mots de passe OVH, `SECRET_KEY`, certificats privés ou URLs avec mot de passe.
- Tester capacité/quotas du service OVH (connexions simultanées, stockage, disponibilité) avant d'y ajouter EduPilot.
- En cas de panne du service PostgreSQL partagé, Coffria et EduPilot peuvent être tous deux indisponibles. Prévoir une séparation de services lorsque les exigences de disponibilité ou la charge augmentent.

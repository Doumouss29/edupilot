# Audit préalable — compatibilité SQLite / PostgreSQL

L'application reste **100 % SQLite en production** tant que la recette PostgreSQL n'est pas validée.

Audit réalisé sur le code Flask actuel (octobre 2026) :
- connexion directe `sqlite3.connect()`, `sqlite3.Row` ;
- initialisation automatique via `executescript(SCHEMA)` et DDL SQLite ;
- expressions `PRAGMA` et opérations spécifiques à SQLite ;
- instructions `INSERT OR IGNORE` (convertir en `ON CONFLICT DO NOTHING` avec contraintes appropriées) ;
- `lastrowid` (convertir en `INSERT ... RETURNING id`) ;
- transactions `BEGIN IMMEDIATE` (à repenser pour le contrôle de concurrence PostgreSQL) ;
- paramètres positionnels `?` (psycopg utilise `%s`) ;
- fonctions date/heure `strftime` et types SQLite à adapter ;
- stockage `BLOB` vers `bytea`, contraintes, uniques et séquences à préserver.

## Isolation multi-établissements

Schéma `edupilot` partagé entre tous les établissements. L'isolation reste par `school_id`. Ne pas activer RLS aveuglément : le rôle SQL, les transactions et les opérations Super Admin doivent faire l'objet d'un modèle d'autorisation défini et de tests inter-établissements.

## Sauvegarde de travail

Après `git pull` (sans redéploiement), sauvegarder depuis le conteneur en cours :

```bash
docker exec edupilot python /app/scripts/snapshot_sqlite.py
```

**Attention** : la commande ci-dessus nécessite que la version du script ait d'abord été intégrée dans l'image Docker déployée. Pour éviter de reconstruire l'application à ce stade, exécuter directement le script présent sur le VPS :

```bash
cd /opt/apps/edupilot
docker cp scripts/snapshot_sqlite.py edupilot:/tmp/snapshot_sqlite.py
docker exec edupilot python /tmp/snapshot_sqlite.py
```

Copier ensuite le dossier de sauvegardes hors du VPS dans un stockage chiffré. Une sauvegarde uniquement sur le VPS n'assure pas une restauration après perte de machine.

## Stratégie de recette

1. Snapshot SQLite et inventaire des tables, contraintes et relations.
2. Développer un adaptateur PostgreSQL et un schéma initial versionné ; tests automatisés.
3. Copier les données **vers une base de recette isolée**, pas directement dans la base `edupilot` de production cible, en préservant les IDs.
4. Vérifier données, rôles, scolarité, MFA, notifications, inscriptions, tests d'isolation et sessions actives.
5. Préparer la maintenance courte et la bascule contrôlée.
6. Ne changer la configuration de production qu'après validation complète, avec sauvegarde et plan de retour arrière.

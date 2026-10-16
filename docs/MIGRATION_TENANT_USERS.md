# Comptes indépendants par établissement — migration

Cette branche remplace l'unicité globale de l'e-mail par une unicité `(school_id,email)`.
Les comptes conservent leur identifiant numérique, leurs relations et leur mot de passe.
Un même e-mail peut être utilisé dans plusieurs établissements.

## Avant déploiement

**Ne pas exécuter la migration avec le serveur EduPilot actif.**
Tester sur une copie de la base et sauvegarder les données (y compris les pièces jointes).
Ne pas utiliser `docker compose down -v`.

Depuis le VPS, après récupération de la branche validée :

```bash
cd /opt/apps/edupilot
docker compose -f docker-compose.vps.yml stop edupilot
mkdir -p /opt/backups/edupilot
cp -p data/edupilot.db "/opt/backups/edupilot/edupilot-$(date +%Y%m%d-%H%M%S).db"
python3 scripts/migrate_tenant_users.py data/edupilot.db
python3 - <<'PY'
import sqlite3
c=sqlite3.connect("data/edupilot.db")
print("Foreign keys:",c.execute("PRAGMA foreign_key_check").fetchall())
print("Users:",c.execute("SELECT COUNT(*) FROM users").fetchone()[0])
print("Integrity:",c.execute("PRAGMA integrity_check").fetchone()[0])
PY
docker compose -f docker-compose.vps.yml up -d --build --no-deps edupilot
curl -fsS https://edupilot.ci/health
```

## Fonctionnement de connexion

* La connexion dédiée d'une école utilise `https://edupilot.ci/<slug>/login`.
* La connexion générique refuse un e-mail présent dans plusieurs établissements afin de ne
  pas ouvrir silencieusement le mauvais espace. Afficher à l'utilisateur l'adresse de son
  établissement depuis ses invitations.
* La réinitialisation générale de mot de passe adresse un lien distinct à chaque compte actif
  associé à la boîte e-mail.
* Les inscriptions manuelles et les imports CSV ne vérifient les doublons que dans l'école.

## Recette obligatoire avant fusion

1. Créer l'adresse `demo@example.org` comme enseignant dans l'école A.
2. La créer comme parent avec un mot de passe distinct dans l'école B.
3. Vérifier les connexions respectives via les URL des écoles.
4. Vérifier que la connexion générique refuse la sélection ambiguë.
5. Vérifier qu'un administrateur A ne peut consulter ou modifier aucun objet de B.
6. Vérifier les imports, modifications de compte, réinitialisations de mot de passe,
   bulletins, cours, présences et fichiers dans les deux établissements.
7. Répéter la migration sur une copie récente de la production et comparer les
   nombres de lignes et `PRAGMA foreign_key_check`.

## Retour arrière

Arrêter EduPilot. Restaurer la sauvegarde **complète** de SQLite créée avant la
migration et remettre en place la version précédente du code. Toute écriture
effectuée après la sauvegarde serait perdue : sauvegarder et coordonner la bascule.

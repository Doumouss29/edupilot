# EduPilot — Démonstration Render Free

**État : socle de démarrage V0.1, non adapté à la production.**

Application Flask/SQLite autonome destinée aux premiers essais du déploiement Render. Le dépôt contient le démarrage, la connexion par profil, des établissements et utilisateurs fictifs, un calendrier hebdomadaire illustratif, le suivi des cours, une déclaration de séance, des notes publiées et un rapport de progression horaire.

> Les modules complets du cahier des charges (gestion administrative avancée, vraie vue jour/mois, inscription et promotion, pièces jointes, invitation parents, verrouillage/réouverture, publication, notifications en temps réel et Brevo) **ne sont pas encore intégrés dans le dépôt**. Ne pas traiter cette V0.1 comme une application métier achevée.

## Déploiement Render Free

1. Sur https://dashboard.render.com : **New → Web Service**.
2. Connecter GitHub et sélectionner `Doumouss29/edupilot`.
3. Choisir `main`, environnement `Python`, plan `Free`.
4. Build : `pip install -r requirements.txt`.
5. Start : `gunicorn app:app --bind 0.0.0.0:$PORT --workers 1 --threads 4`.
6. Définir `SECRET_KEY` à une chaîne aléatoire (Render peut la générer).
7. Définir `DATABASE_PATH=/tmp/edupilot.db` et `EDUPILOT_DEMO=true`.
8. Déployer puis ouvrir `/health` (réponse attendue : `{"app":"EduPilot","status":"ok"}`).

Le fichier `render.yaml` permet également un déploiement Blueprint sur Render.

## Comptes de démonstration (données totalement fictives)

Mot de passe commun : `Demo2026!`.

- Super Admin : `superadmin@demo.edupilot.test`
- Admin : `admin1@demo.edupilot.test`
- Administratif : `scolarite1@demo.edupilot.test`
- Enseignant : `enseignant1@demo.edupilot.test`
- Étudiant : `eleve1_1@demo.edupilot.test`
- Parent : `parent1@demo.edupilot.test`

## Attention : sécurité et stockage

- Ce dépôt a été constaté **public** au moment de son initialisation. Dans GitHub → Settings → General → Danger Zone, le propriétaire peut passer sa visibilité à **Private**.
- Les identifiants ci-dessus sont des comptes de démonstration : ne jamais y enregistrer de données personnelles réelles.
- Render Free ne garantit pas la persistance de SQLite lors d'un redéploiement ou redémarrage. Les données de démonstration sont recréées sur une base vide.
- Le code n'a pas été validé par des tests HTTP ou E2E automatisés et nécessite une recette avant usage plus large.
- Ne pas ajouter de secrets (API Brevo, mots de passe privés) dans GitHub.

## Suite

Le ZIP `EduPilot_Demo_Render_Free_V0.1.zip` fourni dans la conversation contient une implémentation plus large, mais n'a **pas encore été intégralement synchronisé** dans ce dépôt. Il ne faut pas confondre le socle GitHub et ce ZIP.

La suite consiste à consolider le backend, intégrer progressivement tous les modules fonctionnels puis assurer les tests de bout en bout.

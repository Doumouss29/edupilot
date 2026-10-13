# EduPilot — démonstrateur fonctionnel V0.1

Application SaaS scolaire et universitaire (Flask + SQLite + FullCalendar) conçue pour être déployée sur **Render Free** dans **un seul Web Service**.

> **État du projet** : première version exécutable couvrant plusieurs parcours métier. Ce n'est **pas** encore le cahier des charges intégral ; voir `ROADMAP.md`. Ne pas utiliser pour de vraies données d'élèves ou pour un établissement en production.

## Déploiement Render Free, sans VPS

1. Dans GitHub, créez un dépôt **privé** `edupilot`, puis envoyez tous les fichiers du projet à sa racine. Ne commitez pas `*.db`, `.env` ou fichiers personnels.
2. Sur https://dashboard.render.com, choisissez **New → Web Service** (ou **New → Blueprint** si vous souhaitez importer `render.yaml`).
3. Connectez le compte GitHub, puis sélectionnez le dépôt `edupilot`.
4. **Runtime** : Python ; **Branch** : `main` ; **Plan** : Free.
5. **Build Command** : `pip install -r requirements.txt`
6. **Start Command** : `gunicorn app:app --bind 0.0.0.0:$PORT --workers 1 --threads 4 --timeout 120`
7. Variables d'environnement : `SECRET_KEY` = chaîne aléatoire forte (Render peut la générer), `EDUPILOT_DEMO=true`, `PUBLIC_BASE_URL=https://NOM-DU-SERVICE.onrender.com`. Pour SQLite temporaire, laissez `DATABASE_PATH=/tmp/edupilot.db` (valeur par défaut).
8. Cliquez **Deploy Web Service**. Ouvrez l'URL `https://NOM-DU-SERVICE.onrender.com/login`.
9. La base SQLite et les données de démonstration sont initialisées automatiquement au démarrage si la base est vide.

**Attention** : Render Free ne garantit pas la persistance des fichiers SQLite ; redéploiement ou redémarrage peuvent effacer toutes les modifications. Le système réinstalle les données de démonstration fictives. Les fichiers déposés localement seraient aussi perdus. Ne pas se servir de cette configuration pour stocker de vrais travaux.

## Compte de démonstration

Mot de passe commun : `Demo2026!` (uniquement démo, à ne jamais réutiliser en production).

- Super Admin : `superadmin@demo.edupilot.test`
- Admin école : `admin1@demo.edupilot.test`
- Administratif : `scolarite1@demo.edupilot.test`
- Enseignant : `enseignant1@demo.edupilot.test`
- Élève : `eleve1_1@demo.edupilot.test`
- Parent : `parent1@demo.edupilot.test`
- Admin université : `admin2@demo.edupilot.test`

## E-mails Brevo (optionnel)

Configurer ces variables Render :

- `BREVO_API_KEY` : clé API Brevo transactionnelle
- `BREVO_SENDER_EMAIL` : adresse d'expédition authentifiée sur Brevo
- `BREVO_SENDER_NAME` : `EduPilot`
- `PUBLIC_BASE_URL` : URL publique exacte de l'application, indispensable pour les invitations

Les notifications sont enregistrées en SQLite même sans Brevo. Avec Brevo, elles sont également envoyées par l'API d'envoi transactionnel. Sur les comptes fictifs `.test`, les e-mails ne seront pas délivrés. **Pour un vrai test d'invitation, créez un utilisateur avec une adresse e-mail réelle.**

Important : les invitations créent actuellement un lien de création de mot de passe uniquement envoyé par e-mail. Sans configuration Brevo, l'utilisateur invité ne pourra pas activer son compte automatiquement. Un mécanisme admin de renvoi sécurisé reste prévu.

## Exécution locale

```bash
python -m venv .venv
source .venv/bin/activate       # Windows : .venv\\Scripts\\activate
pip install -r requirements.txt
export SECRET_KEY='a-random-local-development-key'
python app.py
# http://localhost:5000
```

## Protection des données

- Accès par rôles et isolation SQL par `school_id` sur les principales routes.
- Mot de passe haché, session signée et contrôle CSRF sur formulaires.
- Historique des notes, inscriptions distinctes par année et audit métier de base.
- Pas de véritable procédure de sauvegarde sur Render Free.
- Avant production : revue complète des autorisations objet par objet, tests d'intrusion, MFA, politiques de rétention, mécanisme de récupération des comptes, stockage privé S3, sauvegardes, protection des données des mineurs, et PostgreSQL avec isolation renforcée.

## Calendrier

FullCalendar est chargé via CDN dans la vue Planning : vues jour / semaine / mois, navigation, événements colorés selon le statut, déclaration de séance et accès feuille de présence. Le CDN exige une connexion Internet.

## Prochaines extensions

Consulter `ROADMAP.md` pour les fonctionnalités non encore développées.

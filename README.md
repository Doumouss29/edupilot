## V0.7 — Super Admin : gestion des comptes des établissements

Dans **Gérer les établissements → Gérer les accès**, le Super Admin peut désormais :

- Cliquer sur **Modifier** pour un compte Admin ou Administratif : prénom, nom, e-mail, téléphone, profil. Il peut facultativement définir un nouveau mot de passe temporaire, ce qui oblige l'utilisateur à le changer à sa prochaine connexion.
- Sélectionner **un ou plusieurs comptes** grâce aux cases à cocher et appliquer : **Suspendre**, **Réactiver**, **Passer au profil Admin**, **Passer au profil Administratif**, **Supprimer définitivement**.
- La suppression est limitée aux comptes sans dépendances académiques (séances, notes, inscriptions, affectations...). Pour préserver l'historique, utiliser **Suspendre**.
- Toutes ces opérations sont réservées au Super Admin, ciblent exclusivement l'établissement sélectionné et sont enregistrées dans le journal d'audit.
- Les tests de régression ont été complétés pour les actions groupées, les modifications individuelles et la protection entre établissements.

Attention : Render Free utilise toujours SQLite sans garantie de persistance. Ne pas utiliser de comptes ou de données réelles pour cette démo.

## V0.6 — Fiches de classes et tableau de bord étudiant

- La liste des classes propose **Détails** en plus de **Modifier**.
- La fiche `/classes/<id>/details` réunit les étudiants inscrits pour l'année académique associée, les enseignants affectés et les cours (avec volumes et enseignants). Accessible aux Admin/Administratif et aux enseignants affectés à la classe, jamais aux étudiants ; les identifiants d'une autre école sont rejetés.
- L'accueil **Étudiant** est désormais spécifique : suppression des statistiques globales, semaine du calendrier affichée avec les jours du lundi au dimanche, cours/horaire/salle/statut, boutons semaine précédente/suivante et raccourci vers le calendrier intégral.
- Le chargement du planning étudiant vérifie `school_id` et ses inscriptions ; aucun cours extérieur à ses classes n'est affiché.
- La version Render Free reste une démonstration SQLite sans persistance garantie des données.

## V0.5 — Correction planning, édition et comptes

- **Calendrier / Planification** : séance unique ou répétition hebdomadaire jusqu'à une date définie. Renseigner classe, cours, date, heure de début, durée (0,5 à 12 h, pas de 30 minutes), salle éventuelle. L'heure de fin est calculée automatiquement : une séance ne peut pas franchir minuit.
- **Conflits** : rejet en cas de chevauchement avec une autre séance de la même classe, du même enseignant ou de la même salle. L'ajout d'une série est atomique : si une date est en conflit, aucune séance de cette série n'est créée.
- **Classes → Modifier**, **Cours → Modifier** : changement des attributs et du professeur du cours, avec historisation. Changer la classe d'un cours déjà utilisé dans une séance ou une évaluation est interdit pour préserver les historiques.
- **Utilisateurs** : cases à cocher permettant la suspension, la réactivation et la suppression de plusieurs comptes. Les suppressions sont interdites pour les utilisateurs qui portent des notes, cours, séances, présences ou autres données académiques historisées ; privilégier la suspension. On ne peut pas suspendre ou supprimer son propre compte depuis ce formulaire. Les comptes sont isolés par établissement.
- **Création étudiant/enseignant** : mot de passe provisoire saisi ou généré et copiable, stocké uniquement sous forme de hachage ; changement obligatoire à la première connexion. Pas d'envoi automatique du mot de passe.
- Les tests de régression incluent les nouvelles routes et workflows. Vérifier les résultats dans **GitHub → Actions** et les logs **Render** après déploiement.
- **Render Free + SQLite** : la base reste éphémère ; ne pas utiliser de données réelles et ne pas considérer ce build comme prêt pour la production.

## Mise à jour V0.4 — étudiants, enseignants et planification (13 octobre 2026)

- **Utilisateurs → Étudiant** : sélection d'une classe obligatoire lors de la création ; inscription liée à l'année scolaire associée à la classe. Un établissement ne peut inscrire un étudiant dans une classe d'un autre établissement.
- **Utilisateurs → Enseignant** : sélection multiple des cours existants, y compris dans des classes différentes. Historique de réaffectation conservé. La création ultérieure de cours permet toujours de sélectionner le même enseignant pour autant de cours que nécessaire.
- **Import d'étudiants CSV / XLSX** : colonnes `prenom;nom;email;classe`, fichier CSV encodé UTF-8, séparateur virgule, point-virgule ou tabulation, ou fichier `.xlsx`. La colonne `classe` contient soit un nom de classe unique dans l'établissement, soit son ID. Le fichier modèle est téléchargeable sur la page Utilisateurs. Maximum **2 Mo / 2 000 étudiants** ; validation complète avant l'insertion, rejet global si doublon, classe inconnue, erreur de format ou e-mail utilisé.
- Les comptes importés n'ont **pas encore d'invitation envoyée** ; leur activation collective par e-mail fera l'objet d'une évolution. Ne pas importer de données réelles sur Render Free.
- **Calendrier / Planification** : choix de la classe, puis cours filtrés de cette classe. Le serveur vérifie l'appartenance du cours à la classe et à l'établissement avant de créer la séance.
- **Navigation latérale** : Calendrier / planification → Classes → Cours → Utilisateurs → Inscriptions / parcours, etc.
- Nouvelle dépendance `openpyxl` ; Render doit exécuter un nouveau build `pip install -r requirements.txt`.
- Tests automatisés ajoutés pour les parcours étudiants, CSV, Excel, enseignants mult-cours et validation de classe au planning.

## Mise à jour V0.3 — interface et création des accès (13 octobre 2026)

- Palette **orange, blanc**, touches de bleu marine et de vert, sans habillage national marqué.
- Super Admin : deux actions distinctes « **Créer un établissement** » (`/schools/new`) et « **Gérer les établissements** » (`/schools`).
- Après avoir créé une école, ouverture automatique de l'écran `/schools/<id>/accounts`.
- Comptes de direction créés par le Super Admin : prénom, nom, e-mail unique, contact téléphonique, profil `admin` ou `administratif`, et mot de passe temporaire.
- Générateur local de mot de passe avec `crypto.getRandomValues` et bouton copier. Le mot de passe n'est pas enregistré en clair et n'est plus visible après la création.
- Changement obligatoire du mot de passe à la première connexion : nouveau mot de passe d'au moins 12 caractères, avec lettres et chiffres. Les pages métiers sont bloquées tant que le changement n'est pas terminé.
- Lien d'accès par établissement : `https://edupilot-tfee.onrender.com/<slug>/login`. Ce lien affiche le nom de l'école et **refuse les identifiants appartenant à une autre école**. Le Super Admin conserve `/login`.
- L'Admin ou l'Administratif créé peut ensuite utiliser les modules existants de gestion des élèves, enseignants, classes, cours et scolarité.
- Démo sur **Render Free + SQLite éphémère** : nouveaux comptes, logos et établissements peuvent disparaître lorsque Render réinitialise le service.
- Les e-mails d'envoi du mot de passe temporaire **ne sont pas encore activés** : la communication manuelle est prévue pour cette étape de démo, par un moyen sécurisé.

### Tests

`python -m unittest discover -s tests -v` ; le pipeline GitHub Actions doit confirmer les résultats. Ces changements sont destinés à la **démo**, pas à une commercialisation en production sans revue de sécurité et tests de bout en bout.

# EduPilot — Démo SQLite / Render Free

## Nouveautés de l'administration SaaS (13 octobre 2026)

- Identité visuelle bleu marine / turquoise et nouveau formulaire de gestion des établissements.
- Le Super Admin crée un établissement avec sa **date de fin d'abonnement**, sa formule et son logo PNG/JPEG/WEBP (1 Mo maximum).
- La date de fin d'abonnement déclenche la restriction **dès le jour indiqué** (à partir de 00:00, selon la date du serveur). Une désactivation manuelle est immédiate.
- Les utilisateurs d'un établissement expiré ou suspendu sont redirigés vers une **page de restriction** depuis toutes les pages métiers, même via les routes API. Le Super Admin n'est pas bloqué.
- Gestion des établissements : mise à jour de l'échéance, de la formule et du logo, désactivation/réactivation, suppression définitive après confirmation du slug.
- **Attention : la suppression définitive efface également toutes les données scolaires, utilisateurs et documents référencés en base associés à l'établissement. Elle est irréversible.** Le stockage de fichiers externe nécessite une politique de purge distincte.
- **Super Admin → Paramètres éditeur** : personnalisation du nom du support, numéro de téléphone et mention « Propulsé par LMurbs » (valeurs initiales : LMurbs / +2250711124359).
- Les logos sont stockés dans SQLite. Sur Render Free, ils disparaissent donc aussi lorsque la base est réinitialisée.
- Une suite de tests GitHub Actions compile l'application et vérifie la gestion des abonnements, logo, pages et permissions. Consulter l'onglet Actions pour le résultat effectif.

## Déploiement / actualisation

Render Web Service connecté à la branche `main`, commande build `pip install -r requirements.txt`, démarrage `gunicorn 'app:app' --bind 0.0.0.0:$PORT --workers 1 --threads 4 --timeout 120`, health check `/health`.

Variables : `SECRET_KEY` aléatoire fort et fixe, `EDUPILOT_DEMO=true`. SQLite : `DATABASE_PATH=/tmp/edupilot.db` (facultatif : valeur par défaut identique).

En environnement **Render Free**, la base SQLite et les logos ne sont pas persistants. L'initialisation recrée les établissements fictifs si la base est vide. Pour conserver les changements d'abonnement et les logos, il faudra ensuite activer une base persistante.

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

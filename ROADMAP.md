# Couverture fonctionnelle EduPilot — V0.1

## Disponible dans le code

- Authentification avec rôles Super Admin, Admin, Administratif, Enseignant, Étudiant, Parent (comptes fictifs préchargés).
- Plusieurs établissements avec slug, plan, séparation logique des données ; création d'établissement depuis Super Admin.
- Gestion des utilisateurs avec invitation et activation par e-mail (si Brevo configuré).
- Classes, années académiques, régimes semestre/trimestre, campus (création Premium).
- Inscription d'élèves à des classes, conservation des inscriptions successives.
- Cours, volume horaire prévu, affectation initiale d'enseignant ; endpoint de réaffectation avec historique.
- Planning FullCalendar jour/semaine/mois, création de séances par administration.
- Déclaration par enseignant d'une séance réalisée/partielle/non effectuée, temps réel et motif.
- Appel facultatif des étudiants par séance.
- Évaluations, notification de publication aux membres de la classe.
- Notes, historique des corrections ; verrouillage et publication par Admin / Administratif.
- Visibilité des notes publiées aux étudiants et parents autorisés.
- Liaison étudiant/parent limitée à deux responsables actifs.
- Centre de notifications et tentative d'envoi API Brevo si configuré.
- Rapport volume horaire prévu / réalisé et export CSV ouvrable dans Excel.

## À développer avant de parler de « toutes les fonctionnalités »

- Écrans de mise à jour/suppression et imports CSV en masse, transferts de promotion en masse.
- Notifications garanties via file de tâches et retries, suivi des envois, Web Push/SSE et paramètres par événement.
- Réécriture complète des URL utilisateur par établissement avec contrôle du contexte de navigation (les slugs sont enregistrés mais l'application utilise une URL de connexion globale en V0.1).
- Édition glisser-déposer du calendrier, contrôles de conflits salles/enseignants/classes, récurrence, sessions de remplacement et annulation avec notifications.
- Réouverture **limitée** aux enseignants sur un cours/évaluation et expiration, demandes d'autorisation, publication/versionnement des bulletins PDF.
- Workflow évaluations/devoirs avec dépôt sécurisé des fichiers, correction, barème, rattrapage, pondérations, compensation UE/ECTS, jury.
- Historique des parcours dans une interface dédiée, redoublement, diplôme, transferts et cursus parallèles.
- Paramétrage parents par classe en édition et désactivation, invitations multi-enfants, révocation et validation des droits parentaux.
- Paramétrage des permissions personnalisées par rôle/site/campus, accès support éditeur contrôlé.
- Rapports PDF, exports Excel natifs, filtres complets jour/semaine/mois, enseignants, salles, sites, indicateurs avancement attendu et retard.
- Suivi financier, paiement Mobile Money, attestations/QR code, gestion des absences notifiées aux parents.
- UI dédiée aux étudiants et parents (le tableau de bord actuel est une vue minimale).
- Vérifications sécurité et tests E2E avant usage réel ; base PostgreSQL et stockage objet pérenne.

**Avant toute exploitation avec des données scolaires réelles : réaliser les tests de recette, un audit de sécurité et de conformité et mettre en place des sauvegardes externes automatisées.**

# EduPilot pour iOS — prototype technique

Cette première base SwiftUI contient une interface iPhone/iPad, une navigation intégrée, l'ouverture externe des liens non EduPilot et un état de connexion indisponible.

**Ce n'est pas encore une application prête à publier.** Elle charge aujourd'hui le site EduPilot dans une WebView ; Apple peut refuser une telle version au titre de la règle 4.2 (fonctionnalités minimales). Avant la soumission, ajouter de véritables écrans natifs et l'intégration des notifications APNs, ainsi qu'une gestion testée des téléchargements, du MFA et des documents.

## Générer le projet sur Mac

1. Installer Xcode et XcodeGen (https://github.com/yonaskolb/XcodeGen).
2. Depuis le dossier `mobile/ios`, exécuter `xcodegen generate`.
3. Ouvrir `EduPilot.xcodeproj` avec Xcode.
4. Sélectionner l'équipe Apple Developer, vérifier l'identifiant d'application, les icônes et la signature.
5. Ajouter l'icône officielle EduPilot dans `EduPilot/Assets.xcassets/AppIcon.appiconset` (1024×1024, sans transparence) et configurer son fichier Contents.json.
6. Tester sur un vrai iPhone et avec TestFlight avant toute soumission.

## Prochaines fonctionnalités indispensables

- API mobile authentifiée et sécurisée (cookies / MFA ou authentification par jeton conçue spécifiquement).
- Interface native : accueil par profil, notifications, cours et calendrier.
- Notifications APNs : demande d'autorisation, jeton d'appareil et envois côté serveur. Le Web Push PWA ne remplace pas automatiquement APNs dans une WebView.
- Gestion de la confidentialité des élèves et parents, politique de confidentialité, captures App Store, compte de démonstration pour la revue.
- Tests sur iPhone/iPad, suivi des erreurs, gestion des connexions et de la déconnexion.

**Ne créez pas encore de lien App Store dans les e-mails :** ce lien ne sera disponible qu'après publication.

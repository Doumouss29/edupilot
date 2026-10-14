# EduPilot — déploiement sur le VPS Coffria / Gbéléban

Architecture existante (à contrôler) : VPS OVH Ubuntu 24.04 **vps-f4dedfa6**, IPv4 historiquement `51.68.224.154`, Docker Compose avec Traefik v3, réseau externe `proxy`, Traefik sur 80/443, résolution ACME `letsencrypt`. Ne pas recréer Traefik, les réseaux ou les services Coffria/Gbéléban.

## 1. DNS chez le registraire du domaine

Ajouter :
- enregistrement A : `@` vers l'IPv4 publique **actuelle** du VPS ;
- enregistrement CNAME : `www` vers `edupilot.ci` (ou A vers la même IP).
- supprimer les éventuelles entrées A/AAAA contradictoires / anciennes pour ces deux hôtes.

Vérifier via `dig +short edupilot.ci A` et `dig +short www.edupilot.ci A`. Attendre la propagation avant de tester Let's Encrypt.

## 2. Préparer le serveur

Depuis le poste local :
```bash
ssh ubuntu@51.68.224.154
```
Adapter utilisateur/IP si la configuration actuelle diffère. Les commandes suivantes concernent le VPS.

Vérifications **sans perturbation des apps actuelles** :
```bash
hostname
docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'
docker network ls
df -h
free -h
```
Le réseau externe `proxy` et le conteneur `traefik` doivent déjà exister. Si absents, arrêter ici et vérifier l'architecture.

## 3. Cloner depuis GitHub (dépôt privé)

```bash
sudo mkdir -p /opt/apps
sudo chown "$USER":"$USER" /opt/apps
cd /opt/apps
git clone git@github.com:Doumouss29/edupilot.git
cd edupilot
```
La clé SSH du VPS doit disposer d'un accès en lecture au dépôt GitHub privé. Une clé de déploiement dédiée en lecture seule est recommandée. Ne jamais inscrire un jeton GitHub dans une commande visible dans l'historique.

## 4. Préparer le stockage persistant et le secret

```bash
mkdir -p data/uploads
sudo chown -R 10001:10001 data
sudo chmod 750 data
cp .env.vps.example .env
SECRET="$(openssl rand -hex 32)"
sed -i "s/^SECRET_KEY=.*/SECRET_KEY=$SECRET/" .env
unset SECRET
chmod 600 .env
```

Le vrai `.env` n'est pas versionné. Définir les identifiants Brevo dans ce fichier uniquement quand l'intégration e-mail sera prête.

## 5. Démarrer le conteneur

```bash
docker compose -f docker-compose.vps.yml config
docker compose -f docker-compose.vps.yml up -d --build
docker compose -f docker-compose.vps.yml ps
docker compose -f docker-compose.vps.yml logs --tail=80 edupilot
docker compose -f docker-compose.vps.yml exec edupilot python scripts/bootstrap_superadmin.py
```
Créer un **nouveau** compte Super Admin avec e-mail et mot de passe temporaire saisis de manière interactive. La modification du mot de passe à la première connexion est obligatoire.

## 6. Tester DNS / HTTPS / accès

```bash
curl -I https://edupilot.ci/login
curl -s https://edupilot.ci/health
docker logs traefik --tail 80
```
Attendre l'émission du certificat TLS. Si la résolution DNS n'est pas encore effective, Traefik ne peut pas obtenir le certificat.

Si le domaine est correctement résolu et que les certificats fonctionnent, vérifier l'accès depuis `https://edupilot.ci/login`. Un `/health` valide doit renvoyer un statut `ok`.

## 7. Redéploiement sans perte de données

```bash
cd /opt/apps/edupilot
git pull --ff-only
docker compose -f docker-compose.vps.yml up -d --build
docker compose -f docker-compose.vps.yml logs --tail=100 edupilot
```
Le dossier `/opt/apps/edupilot/data` est conservé entre reconstructions des conteneurs. Ne pas exécuter de commandes de nettoyage destructives sur ce dossier.

## 8. Sauvegarde SQLite

Une sauvegarde cohérente peut être générée à chaud via le module standard SQLite :
```bash
mkdir -p /opt/backups/edupilot
docker compose -f docker-compose.vps.yml exec -T edupilot python -c "import sqlite3; src=sqlite3.connect('/data/edupilot.db'); dst=sqlite3.connect('/data/backup.db'); src.backup(dst); dst.close(); src.close()"
sudo cp data/backup.db "/opt/backups/edupilot/edupilot-$(date +%F-%H%M).db"
sudo rm data/backup.db
```
**Important :** sauvegarder également les fichiers du répertoire `data/uploads`, et exporter les backups hors du VPS. Mettre en place une sauvegarde planifiée avec rotation ; ne pas s'en tenir à des copies stockées sur le même disque.

## 9. Limitations

- SQLite sur un VPS devient persistant mais ne remplace pas PostgreSQL pour un SaaS commercial en montée en charge.
- Le VPS a historiquement été dimensionné à environ 4 Go de RAM ; contrôler les ressources de Coffria et Gbéléban. Ici, EduPilot est limité à 900 Mo et 1,5 vCPU.
- Le déploiement n'importe **pas** les données déjà saisies sur Render. Il faut obtenir le fichier SQLite Render avant toute migration de ces données, si leur conservation est nécessaire.
- Ne pas importer de données personnelles réelles avant une revue complète de sécurité, conformité et sauvegarde.
- Aucun changement de configuration n'est nécessaire dans les autres applications tant que le réseau `proxy` et Traefik central sont en place.

## Notifications sur smartphone : activation Web Push

EduPilot est installable en PWA. La cloche en haut à droite fonctionne sans configuration externe, avec stockage dans SQLite. Pour activer les alertes du système Android/iPhone, configurer une paire VAPID permanente, conservée dans le volume persistant.

### 1. Installer le code et générer les clés

Après sauvegarde du dossier `data/`, mise à jour Git et reconstruction du conteneur :

```bash
cd /opt/apps/edupilot
docker compose -f docker-compose.vps.yml exec edupilot python scripts/setup_push.py
```

Le script crée `/data/vapid_private.pem` s'il n'existe pas. Il ne révèle jamais la clé privée. Il affiche trois paramètres à ajouter dans le fichier `.env` du VPS : `VAPID_PRIVATE_KEY`, `VAPID_PUBLIC_KEY`, `VAPID_SUBJECT`. Remplacer la valeur `mailto:` par l'adresse e-mail de contact réelle de l'exploitant. **Ne pas copier la clé privée dans GitHub**. Ne pas la régénérer après l'inscription des téléphones, sinon leurs abonnements peuvent devenir invalides.

```bash
nano .env
# Ajouter les valeurs affichées par le script, puis enregistrer.
docker compose -f docker-compose.vps.yml config --quiet
docker compose -f docker-compose.vps.yml up -d --no-deps --force-recreate edupilot
curl -fsS https://edupilot.ci/api/push/config
```

L'URL `/api/push/config` requiert une session authentifiée ; utiliser le navigateur connecté pour vérifier `enabled: true`. La commande `curl` sans session peut rediriger vers la page de connexion.

### 2. Activer sur les téléphones

- **Android :** ouvrir `https://edupilot.ci` dans un navigateur compatible, se connecter, ouvrir la cloche et toucher « Activer les notifications sur ce téléphone », puis autoriser.
- **iPhone iOS 16.4+ :** ouvrir le site dans Safari, utiliser Partager → Sur l'écran d'accueil, lancer EduPilot depuis l'icône installée, se connecter, puis activer les notifications dans la cloche.
- Les autorisations sont accordées appareil par appareil et peuvent être révoquées dans les réglages système.
- Les notifications push nécessitent Internet. Leur distribution finale dépend du navigateur et du système d'exploitation.
- Les alertes déjà présentes dans le panneau système du téléphone ne peuvent pas être effacées à distance par « Tout effacer » dans EduPilot.

### 3. Maintenance

La base `data/edupilot.db` contient les notifications et les abonnements Web Push. Sauvegarder aussi `data/vapid_private.pem` **hors du VPS, dans un stockage chiffré et à accès restreint**. Les envois e-mail Brevo restent indépendants. Pour des campagnes à grand volume, prévoir une file d'attente asynchrone dédiée : les envois Web Push actuels ont lieu pendant le traitement de l'événement.


## Brevo : e-mails transactionnels et invitations automatiques

### Compte et domaine expéditeur

1. Dans Brevo, activer les **e-mails transactionnels** et créer une clé API de version **v3** disposant des droits d'envoi.
2. Faire authentifier un domaine que l'on contrôle (par exemple `edupilot.ci`) via les enregistrements DNS affichés par Brevo (DKIM et, selon les indications Brevo, SPF/DMARC). Ne pas copier d'enregistrements DNS génériques : utiliser exactement ceux du tableau de bord Brevo.
3. Configurer et vérifier l'adresse expéditrice choisie, par exemple `notifications@edupilot.ci`, avant d'utiliser cette adresse dans EduPilot.
4. Dans le fichier **privé** `/opt/apps/edupilot/.env`, renseigner :
```ini
BREVO_API_KEY=VOTRE_CLE_API_BREVO_V3
BREVO_SENDER_EMAIL=notifications@edupilot.ci
BREVO_SENDER_NAME=EduPilot
```
5. Ne jamais commiter ce fichier dans GitHub, ni envoyer la clé API dans le chat ou les journaux.

### Activer les variables dans Docker Compose

```bash
cd /opt/apps/edupilot
docker compose -f docker-compose.vps.yml config --quiet
docker compose -f docker-compose.vps.yml up -d --force-recreate --no-deps edupilot
docker compose -f docker-compose.vps.yml ps
```

Le fichier `docker-compose.vps.yml` transmet déjà `BREVO_API_KEY`, `BREVO_SENDER_EMAIL`, `BREVO_SENDER_NAME` au conteneur. Un redémarrage **du seul conteneur EduPilot** suffit après modification du fichier `.env`.

### Parcours des utilisateurs

- Un Super Admin crée un administrateur d'établissement : EduPilot crée le compte avec un mot de passe interne aléatoire inconnu de tous puis envoie **un lien d'activation à usage unique, valable 48 h**.
- Un administrateur crée un élève/étudiant, enseignant, parent ou personnel administratif : même fonctionnement.
- À l'ouverture du lien, le destinataire définit son propre mot de passe (12 caractères minimum, lettres et chiffres).
- Depuis la page de connexion, **Mot de passe oublié ?** envoie un lien à usage unique, valable **30 minutes**, vers l'adresse enregistrée.
- Depuis chaque espace connecté, le menu **Modifier mon mot de passe** permet un changement après saisie du mot de passe actuel.
- Depuis les tableaux de comptes, **Renvoyer l'accès** réémet une invitation ; l'ancienne invitation non utilisée devient invalide.
- Après import CSV/XLSX, sélectionner au plus **30 comptes par lot** dans Utilisateurs, action **Envoyer / renvoyer les invitations par e-mail**. Cet envoi est manuel afin d'éviter un déclenchement de 2 000 e-mails pendant l'import.
- Les événements scolaires déjà pris en charge par `notify_event()` créent des alertes internes et, si Brevo est configuré, envoient également un e-mail transactionnel aux personnes ciblées.

Un échec Brevo ne détruit pas le compte créé. La page affiche un avertissement permettant de renvoyer l'invitation une fois l'incident corrigé. Les notifications internes restent enregistrées même si l'envoi e-mail échoue.

**Recette recommandée :** vérifier le statut de la clé API dans Brevo ; créer un compte de test avec une vraie adresse ; ouvrir le message d'invitation ; définir un mot de passe ; valider la connexion ; demander ensuite une réinitialisation. Vérifier les événements d'envoi/livraison dans les journaux transactionnels Brevo. Ne pas utiliser de mots de passe réels dans les tests de recette partagés.

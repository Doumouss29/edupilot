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
chmod 750 data
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

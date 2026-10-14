"""Créer les clés VAPID de Web Push sans afficher la clé privée.

Usage (conteneur EduPilot): python scripts/setup_push.py
Conserver le fichier privé dans /data et renseigner VAPID_PRIVATE_KEY, VAPID_PUBLIC_KEY et VAPID_SUBJECT dans .env.
"""
import base64
import os
from pathlib import Path
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization

path=Path(os.getenv('VAPID_KEY_FILE','/data/vapid_private.pem'))
if path.exists():
    private=serialization.load_pem_private_key(path.read_bytes(),password=None)
    print('Clé privée existante conservée.')
else:
    path.parent.mkdir(parents=True,exist_ok=True)
    private=ec.generate_private_key(ec.SECP256R1())
    content=private.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption())
    descriptor=os.open(str(path),os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    with os.fdopen(descriptor,'wb') as stream:stream.write(content)
    print('Clé privée créée dans '+str(path))
public=private.public_key().public_bytes(serialization.Encoding.X962,serialization.PublicFormat.UncompressedPoint)
encoded=base64.urlsafe_b64encode(public).rstrip(b'=').decode('ascii')
print('VAPID_PRIVATE_KEY='+str(path))
print('VAPID_PUBLIC_KEY='+encoded)
print('VAPID_SUBJECT=mailto:contact@edupilot.ci')
print('Conserver le même fichier privé lors des mises à jour.')

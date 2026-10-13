"""Create/update an initial EduPilot Super Admin, interactively inside the VPS container.

Run: docker compose -f docker-compose.vps.yml exec edupilot python scripts/bootstrap_superadmin.py
"""
import getpass
import os
import re
import sqlite3

if os.getenv("EDUPILOT_DEMO", "false").lower() == "true":
    raise SystemExit("Refus : désactiver EDUPILOT_DEMO pour la production.")

from werkzeug.security import generate_password_hash
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import app as project

def main():
    print("Création / réinitialisation du Super Admin EduPilot")
    email=input("E-mail administrateur : ").strip().lower()
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
        raise SystemExit("E-mail invalide.")
    display_name=input("Nom affiché : ").strip()
    if not display_name or len(display_name)>150:
        raise SystemExit("Nom invalide.")
    password=getpass.getpass("Mot de passe temporaire : ")
    confirmation=getpass.getpass("Confirmer le mot de passe : ")
    if password != confirmation or len(password)<12 or not any(x.isalpha() for x in password) or not any(x.isdigit() for x in password):
        raise SystemExit("Exige 12 caractères minimum, lettres, chiffres et confirmation identique.")
    with project.db() as conn:
        other=conn.execute("SELECT id,role FROM users WHERE email=?", (email,)).fetchone()
        if other and other["role"]!="superadmin":
            raise SystemExit("Cette adresse appartient déjà à un utilisateur non Super Admin.")
        if other:
            conn.execute("UPDATE users SET name=?,password_hash=?,must_change_password=1,active=1 WHERE id=?",
                         (display_name,generate_password_hash(password),other["id"]))
        else:
            conn.execute("INSERT INTO users(school_id,name,email,password_hash,role,active,must_change_password) VALUES (NULL,?,?,?,'superadmin',1,1)",
                         (display_name,email,generate_password_hash(password)))
    print("Compte Super Admin prêt. Le mot de passe devra être modifié à la première connexion.")

if __name__=="__main__":
    main()

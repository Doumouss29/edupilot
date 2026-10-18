#!/usr/bin/env python3
"""Read-only check of an isolated EduPilot PostgreSQL database.

Requires the psycopg driver to be installed separately; the production
application is still using SQLite until a tested database migration is ready.
Uses standard PG* environment variables; never prints secrets.
"""
import os
import sys

HOST = "postgresql-d1be9bc3-oe2bccb52.database.cloud.ovh.net"
PORT = 20184
DBNAME = "edupilot"

def main():
    if os.getenv("PGHOST") != HOST or os.getenv("PGDATABASE") != DBNAME:
        print("Refus : configurer PGHOST et PGDATABASE pour la base EduPilot dédiée.", file=sys.stderr)
        return 2
    if int(os.getenv("PGPORT", "0")) != PORT:
        print("Refus : le port PostgreSQL ne correspond pas au service attendu.", file=sys.stderr)
        return 2
    if os.getenv("PGSSLMODE") not in ("verify-full",):
        print("Refus : exiger PGSSLMODE=verify-full.", file=sys.stderr)
        return 2
    try:
        import psycopg
    except ImportError:
        print("Installer d'abord psycopg[binary] dans un environnement de test.", file=sys.stderr)
        return 2
    with psycopg.connect(connect_timeout=10, options="-c default_transaction_read_only=on") as con:
        with con.cursor() as cur:
            cur.execute("SELECT current_database(), current_user, current_setting('ssl')") 
            dbname, user, ssl_supported = cur.fetchone()
            print(f"Base : {dbname}; utilisateur : {user}; SSL supporté : {ssl_supported}")
            cur.execute("SELECT count(*) FROM pg_catalog.pg_tables WHERE schemaname='public'")
            print("Tables public :", cur.fetchone()[0])
    return 0

if __name__ == "__main__":
    sys.exit(main())

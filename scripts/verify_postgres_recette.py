#!/usr/bin/env python3
"""Compare the 31 SQLite snapshot table counts with PostgreSQL rehearsal."""
import argparse
import getpass
import os
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from postgres_rehearsal import rehearsal_db

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("snapshot", type=Path)
    args = parser.parse_args()
    if not args.snapshot.is_file():
        parser.error("Snapshot not found")
    os.environ["PGSCHEMA"] = "edupilot_recette"
    if not os.getenv("PGPASSWORD"):
        os.environ["PGPASSWORD"] = getpass.getpass("Mot de passe OVH PostgreSQL edupilot : ")
    with sqlite3.connect("file:" + str(args.snapshot.resolve()) + "?mode=ro", uri=True) as src:
        table_names = [r[0] for r in src.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )]
        expected = {}
        for name in table_names:
            safe = '"' + name.replace('"', '""') + '"'
            expected[name] = src.execute("SELECT COUNT(*) FROM " + safe).fetchone()[0]
    from psycopg import sql
    with rehearsal_db() as pg:
        with pg.cursor() as cur:
            cur.execute("SELECT tablename FROM pg_catalog.pg_tables WHERE schemaname='edupilot_recette'")
            available = {row["tablename"] for row in cur.fetchall()}
            if available != set(expected):
                raise RuntimeError("Table list differs between SQLite and PostgreSQL")
            total = 0
            for table, n in sorted(expected.items()):
                cur.execute(sql.SQL("SELECT count(*) AS n FROM {}.{}").format(
                    sql.Identifier("edupilot_recette"), sql.Identifier(table)))
                actual = cur.fetchone()["n"]
                if actual != n:
                    raise RuntimeError(f"Count mismatch for {table}: SQLite={n}, PostgreSQL={actual}")
                total += actual
    print(f"OK : {len(expected)} tables, {total} lignes identiques entre SQLite et PostgreSQL.")
    print("Vérification en lecture seule ; aucun changement en production.")

if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Read-only SQLite migration manifest, without disclosing school or account data.

Run with a SQLite snapshot path (not the live database):
 python scripts/inspect_sqlite_migration.py /path/to/edupilot-snapshot.sqlite3

Outputs schema DDL, row counts and dependency information. No SQL is executed
against PostgreSQL, and the source SQLite file is opened read-only.
"""
import argparse
import json
import sqlite3
from pathlib import Path

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("sqlite_file",type=Path)
    parser.add_argument("--output",type=Path)
    args=parser.parse_args()
    if not args.sqlite_file.is_file():
        parser.error("Sauvegarde SQLite introuvable")
    conn=sqlite3.connect(f"file:{args.sqlite_file.resolve()}?mode=ro",uri=True)
    conn.row_factory=sqlite3.Row
    try:
        integrity=conn.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity!="ok":
            raise SystemExit("Intégrité SQLite non valide")
        items=[]
        for row in conn.execute("SELECT name,sql FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name").fetchall():
            name=row["name"]
            identifier='"'+name.replace('"','""')+'"'
            items.append({
                "table":name,
                "count":conn.execute(f"SELECT COUNT(*) FROM {identifier}").fetchone()[0],
                "ddl_sqlite":row["sql"],
                "columns":[dict(col) for col in conn.execute(f"PRAGMA table_info({identifier})")],
                "foreign_keys":[dict(fk) for fk in conn.execute(f"PRAGMA foreign_key_list({identifier})")],
                "indexes":[dict(idx) for idx in conn.execute(f"PRAGMA index_list({identifier})")],
            })
        result={"integrity_check":integrity,"tables":items,"table_count":len(items)}
        destination=args.output
        if destination:
            destination.parent.mkdir(parents=True,exist_ok=True)
            destination.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
            destination.chmod(0o600)
            print(f"Inventaire technique enregistré : {destination}")
        print(f"Intégrité : {integrity} ; tables : {len(items)} ; lignes totales : {sum(t['count'] for t in items)}")
        for item in items:
            print(f"{item['table']}: {item['count']}")
    finally:
        conn.close()

if __name__=="__main__":
    main()

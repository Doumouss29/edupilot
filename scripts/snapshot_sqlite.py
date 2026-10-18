#!/usr/bin/env python3
"""Take a consistent, read-only SQLite backup and write a non-sensitive inventory.

Example on VPS:
  docker exec edupilot python /app/scripts/snapshot_sqlite.py
This writes a timestamped backup under /data/backup-postgres-prep.
Does not change the source DB or application engine.
"""
import datetime
import json
import os
import pathlib
import sqlite3

def main():
    source=pathlib.Path(os.environ.get("DATABASE_PATH","/tmp/edupilot.db"))
    if not source.is_file():
        raise SystemExit("Base SQLite introuvable : vérifier DATABASE_PATH.")
    destination=source.parent/"backup-postgres-prep"
    destination.mkdir(mode=0o700,parents=True,exist_ok=True)
    destination.chmod(0o700)
    stamp=datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup=destination/f"edupilot-{stamp}.sqlite3"
    inventory=destination/f"edupilot-{stamp}.inventory.json"
    with sqlite3.connect(f"file:{source}?mode=ro",uri=True,timeout=30) as src:
        with sqlite3.connect(str(backup)) as target:
            src.backup(target)
    backup.chmod(0o600)
    with sqlite3.connect(f"file:{backup}?mode=ro",uri=True) as con:
        con.row_factory=sqlite3.Row
        integrity=con.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity!="ok":
            raise RuntimeError("Échec integrity_check sur la sauvegarde.")
        tables=[r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        counts={}
        columns={}
        for name in tables:
            safe='"'+name.replace('"','""')+'"'
            counts[name]=con.execute(f"SELECT COUNT(*) FROM {safe}").fetchone()[0]
            columns[name]=[dict(r) for r in con.execute(f"PRAGMA table_info({safe})")]
    inventory.write_text(json.dumps({
        "generated_utc":stamp,"integrity_check":integrity,
        "table_counts":counts,"table_columns":columns
    },ensure_ascii=False,indent=2),encoding="utf-8")
    inventory.chmod(0o600)
    print("Sauvegarde cohérente :",backup)
    print("Inventaire sans données personnelles :",inventory)
    print("Tables :",len(tables),"| Contrôle d'intégrité :",integrity)
    print("Aucun changement apporté à SQLite ou à PostgreSQL.")

if __name__=="__main__":
    main()

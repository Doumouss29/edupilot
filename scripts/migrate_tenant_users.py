"""One-time offline migration for tenant-scoped user e-mail addresses.

Stop the EduPilot container and back up the database before running.
Usage: python scripts/migrate_tenant_users.py /path/to/edupilot.db
"""
import sqlite3
import sys
from pathlib import Path


def migrate(path):
    path = Path(path).resolve()
    if not path.is_file():
        raise SystemExit(f"Database does not exist: {path}")
    con = sqlite3.connect(str(path), timeout=30, isolation_level=None)
    try:
        con.execute("PRAGMA busy_timeout=30000")
        con.execute("PRAGMA foreign_keys=OFF")
        con.execute("BEGIN EXCLUSIVE")
        ddl = con.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='users'").fetchone()
        if not ddl:
            raise RuntimeError("Missing users table")
        old = ddl[0]
        if "email TEXT NOT NULL UNIQUE" not in old:
            if "email TEXT NOT NULL" in old:
                print("Users table is already migrated")
                con.execute("ROLLBACK")
                return
            raise RuntimeError("Unexpected users schema: review manually")
        old_columns = [r[1] for r in con.execute("PRAGMA table_info(users)")]
        old_indexes = [row[0] for row in con.execute(
            "SELECT sql FROM sqlite_master WHERE type='index' AND tbl_name='users' AND sql IS NOT NULL"
        )]
        # Rename would rewrite foreign-key definitions in dependent tables.
        # Rebuild in-place instead, preserving every integer user ID.
        new_ddl = old.replace("CREATE TABLE users", "CREATE TABLE users_tenant_new", 1).replace(
            "email TEXT NOT NULL UNIQUE", "email TEXT NOT NULL", 1)
        if new_ddl == old or "users_tenant_new" not in new_ddl:
            raise RuntimeError("Unexpected CREATE TABLE format")
        con.execute(new_ddl)
        cols = ",".join('"' + c.replace('"', '""') + '"' for c in old_columns)
        con.execute(f"INSERT INTO users_tenant_new ({cols}) SELECT {cols} FROM users")
        before = con.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        after = con.execute("SELECT COUNT(*) FROM users_tenant_new").fetchone()[0]
        if before != after:
            raise RuntimeError("User row count mismatch")
        con.execute("DROP TABLE users")
        con.execute("ALTER TABLE users_tenant_new RENAME TO users")
        for index in old_indexes:
            con.execute(index)
        con.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_school_email ON users(school_id,email) WHERE school_id IS NOT NULL")
        con.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_platform_email ON users(email) WHERE school_id IS NULL")
        violations = con.execute("PRAGMA foreign_key_check").fetchall()
        if violations:
            raise RuntimeError(f"Foreign-key violations: {violations[:5]}")
        con.execute("COMMIT")
        print(f"Migrated {after} accounts without changing user IDs")
    except BaseException:
        if con.in_transaction:
            con.execute("ROLLBACK")
        raise
    finally:
        con.close()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python scripts/migrate_tenant_users.py /path/to/edupilot.db")
    migrate(sys.argv[1])

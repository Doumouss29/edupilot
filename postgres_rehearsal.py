"""PostgreSQL connection for isolated EduPilot migration rehearsals.

Not wired into app.py: SQLite remains the production engine until all
application SQL statements have passed PostgreSQL compatibility tests.
"""
import os
from contextlib import contextmanager

ALLOWED_SCHEMA = "edupilot_recette"

def pg_connection():
    import psycopg
    from psycopg.rows import dict_row
    required = ("PGHOST", "PGPORT", "PGDATABASE", "PGUSER", "PGPASSWORD")
    missing = [k for k in required if not os.getenv(k)]
    if missing:
        raise RuntimeError("Missing PostgreSQL configuration: " + ", ".join(missing))
    if os.getenv("PGDATABASE") != "edupilot":
        raise RuntimeError("Refusing unexpected PostgreSQL database")
    if os.getenv("PGSCHEMA") != ALLOWED_SCHEMA:
        raise RuntimeError("Only the dedicated rehearsal schema is allowed")
    mode = os.getenv("PGSSLMODE", "verify-full")
    if mode not in ("verify-full", "require"):
        raise RuntimeError("PostgreSQL TLS is required")
    conn = psycopg.connect(
        host=os.environ["PGHOST"],
        port=int(os.environ["PGPORT"]),
        dbname=os.environ["PGDATABASE"],
        user=os.environ["PGUSER"],
        password=os.environ["PGPASSWORD"],
        sslmode=mode,
        connect_timeout=12,
        row_factory=dict_row,
        options="-c search_path=edupilot_recette",
    )
    with conn.cursor() as cur:
        cur.execute("SELECT current_database(), current_schema()")
        row = cur.fetchone()
        if row["current_database"] != "edupilot" or row["current_schema"] != ALLOWED_SCHEMA:
            conn.close()
            raise RuntimeError("Unexpected PostgreSQL database/schema")
    return conn

@contextmanager
def rehearsal_db():
    conn = pg_connection()
    try:
        yield conn
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()

def counts():
    """Read-only reconciliation of the major migrated domain tables."""
    with rehearsal_db() as conn:
        with conn.cursor() as cur:
            result = {}
            for table in ("schools", "users", "lessons", "notifications",
                          "mfa_trusted_devices", "push_subscriptions"):
                from psycopg import sql
                cur.execute(sql.SQL("SELECT COUNT(*) AS n FROM {}").format(sql.Identifier(table)))
                result[table] = cur.fetchone()["n"]
            return result

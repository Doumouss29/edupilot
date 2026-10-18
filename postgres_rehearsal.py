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
    return CompatConnection(conn)

class CompatCursor:
    def __init__(self, cursor, lastrowid=None):
        self.cursor = cursor
        self.lastrowid = lastrowid
        self.rowcount = cursor.rowcount
    def fetchone(self):
        return self.cursor.fetchone()
    def fetchall(self):
        return self.cursor.fetchall()
    def __iter__(self):
        return iter(self.cursor)

class CompatConnection:
    def __init__(self, connection):
        self.raw = connection
    def execute(self, statement, args=()):
        import re
        from postgres_sql import placeholders
        sql = statement.strip()
        if sql.upper() == "BEGIN IMMEDIATE":
            sql = "SELECT pg_advisory_xact_lock(20261018)"
        if re.match(r"INSERT\s+OR\s+IGNORE\s+INTO", sql, re.I):
            sql = re.sub(r"INSERT\s+OR\s+IGNORE\s+INTO", "INSERT INTO", sql, count=1, flags=re.I)
            sql = sql.rstrip(";") + " ON CONFLICT DO NOTHING"
        insert = bool(re.match(r"INSERT\s+INTO", sql, re.I))
        if insert and "RETURNING" not in sql.upper():
            if re.match(r"INSERT\s+INTO\s+(users|schools|years|classes|campuses|courses|lessons|assessments|grades|notifications|audit|invites|enrollments|periods|parent_links|teacher_history|grade_history|push_subscriptions|mfa_trusted_devices|email_delivery_log|assessment_files|attendance|submissions|unlocks)\b", sql, re.I):
                sql = sql.rstrip(";") + " RETURNING id"
        cursor = self.raw.execute(placeholders(sql), args)
        lastrowid = None
        if insert and "RETURNING id" in sql:
            item = cursor.fetchone()
            if item:
                lastrowid = item["id"]
        return CompatCursor(cursor, lastrowid)
    def cursor(self):
        return self.raw.cursor()
    def commit(self):
        self.raw.commit()
    def rollback(self):
        self.raw.rollback()
    def close(self):
        self.raw.close()

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

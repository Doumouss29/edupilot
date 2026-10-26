"""PostgreSQL connection for isolated EduPilot migration rehearsals.

Not wired into app.py: SQLite remains the production engine until all
application SQL statements have passed PostgreSQL compatibility tests.
"""
import os
from contextlib import contextmanager
from threading import Lock

_pool = None
_pool_lock = Lock()

def _get_pool():
    """Bound DB connections instead of opening a new socket for every SQL query."""
    global _pool
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                from psycopg_pool import ConnectionPool
                import psycopg
                from psycopg.rows import dict_row
                _pool = ConnectionPool(
                    conninfo=psycopg.conninfo.make_conninfo(
                        host=os.environ["PGHOST"], port=int(os.environ["PGPORT"]),
                        dbname=os.environ["PGDATABASE"], user=os.environ["PGUSER"],
                        password=os.environ["PGPASSWORD"],
                        sslmode=os.getenv("PGSSLMODE", "require"), connect_timeout=12,
                        options="-c search_path=" + os.environ["PGSCHEMA"]),
                    kwargs={"row_factory": dict_row},
                    min_size=0, max_size=3, timeout=12, open=True)
    return _pool


ALLOWED_SCHEMAS = ("edupilot_recette", "edupilot")

def pg_connection():
    import psycopg
    from psycopg.rows import dict_row
    required = ("PGHOST", "PGPORT", "PGDATABASE", "PGUSER", "PGPASSWORD")
    missing = [k for k in required if not os.getenv(k)]
    if missing:
        raise RuntimeError("Missing PostgreSQL configuration: " + ", ".join(missing))
    if os.getenv("PGDATABASE") != "edupilot":
        raise RuntimeError("Refusing unexpected PostgreSQL database")
    if os.getenv("PGSCHEMA") not in ALLOWED_SCHEMAS:
        raise RuntimeError("Only the dedicated rehearsal schema is allowed")
    mode = os.getenv("PGSSLMODE", "verify-full")
    if mode not in ("verify-full", "require"):
        raise RuntimeError("PostgreSQL TLS is required")
    pool = _get_pool()
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT current_database(), current_schema()")
            row = cur.fetchone()
            if row["current_database"] != "edupilot" or row["current_schema"] != os.environ["PGSCHEMA"]:
                raise RuntimeError("Unexpected PostgreSQL database/schema")
        conn.commit()
        return CompatConnection(conn, pool)
    except BaseException:
        conn.rollback()
        pool.putconn(conn)
        raise

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
    def __init__(self, connection, pool=None):
        self.raw = connection
        self._pool = pool
        self._closed = False
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
        if self._closed:return
        self._closed = True
        if self._pool is not None:
            self._pool.putconn(self.raw)
        else:
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

"""Regressions for tenant boundaries and immutable archived school years.

Run against disposable SQLite databases only; no production secrets or network access.
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from werkzeug.security import generate_password_hash

ROOT=Path(__file__).resolve().parents[1]
TEMP=tempfile.TemporaryDirectory()
os.environ["DB_ENGINE"]="sqlite"
os.environ["DATABASE_PATH"]=str(Path(TEMP.name)/"startup.db")
os.environ["SECRET_KEY"]="test-school-boundaries-only"
sys.path.insert(0,str(ROOT))
import app as project


class TenantAndArchiveSecurityTests(unittest.TestCase):
    def setUp(self):
        project.DB=str(Path(TEMP.name)/(self._testMethodName+".db"))
        with project.db() as conn:
            conn.executescript(project.SCHEMA)
            conn.execute("ALTER TABLE years ADD COLUMN status TEXT NOT NULL DEFAULT 'active'")
            conn.execute("ALTER TABLE years ADD COLUMN start_date TEXT")
            conn.execute("ALTER TABLE years ADD COLUMN end_date TEXT")
            conn.execute("INSERT INTO schools(id,name,slug) VALUES (1,'École A','ecole-a'),(2,'École B','ecole-b')")
            conn.execute("INSERT INTO users(id,school_id,name,email,password_hash,role) VALUES (1,1,'Admin A','a@example.test',?,'admin')",
                         (generate_password_hash("PasswordTest123"),))
            conn.execute("INSERT INTO years(id,school_id,label,is_active,status) VALUES (1,1,'2026-2027',1,'active'),(2,1,'2025-2026',0,'archived'),(3,2,'2025-2026',0,'archived')")
            conn.execute("INSERT INTO classes(id,school_id,year_id,name) VALUES (1,1,1,'Classe en cours'),(2,1,2,'Classe archive'),(3,2,3,'Classe B')")
            conn.execute("INSERT INTO courses(id,school_id,class_id,name,code) VALUES (1,1,1,'SIG','SIG01'),(2,2,3,'Topographie','TOPO')")
        self.client=project.app.test_client()
        with self.client.session_transaction() as sess:
            sess["uid"]=1
            sess["csrf"]="test-csrf-token"

    def test_archive_from_another_school_is_not_accessible(self):
        response=self.client.get("/academic-years/3/archive")
        self.assertEqual(response.status_code,404)

    def test_course_from_another_school_is_not_editable(self):
        response=self.client.post("/courses/2/edit",data={
            "csrf":"test-csrf-token","name":"Topographie modifiée","class_id":"1"
        })
        self.assertEqual(response.status_code,404)

    def test_cannot_move_course_into_archived_year(self):
        response=self.client.post("/courses/1/edit",data={
            "csrf":"test-csrf-token","name":"SIG","class_id":"2",
            "hours":"20","coefficient":"1"
        })
        self.assertEqual(response.status_code,403)
        with project.db() as conn:
            row=conn.execute("SELECT class_id FROM courses WHERE id=1").fetchone()
        self.assertEqual(row["class_id"],1)


if __name__=="__main__":
    unittest.main()

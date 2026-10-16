"""Regression tests for tenant-specific e-mail identities and migration."""
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from werkzeug.security import generate_password_hash

ROOT = Path(__file__).resolve().parents[1]
TEMP = tempfile.TemporaryDirectory()
os.environ["DATABASE_PATH"] = str(Path(TEMP.name) / "test-tenant-app.db")
os.environ["SECRET_KEY"] = "tenant-tests-only"
sys.path.insert(0, str(ROOT))
import app as project


class TenantUsersTest(unittest.TestCase):
    def setUp(self):
        self.dbfile = Path(TEMP.name) / (self.id().replace(".", "_") + ".db")
        project.DB = str(self.dbfile)
        with project.db() as con:
            con.executescript(project.SCHEMA)
            con.execute("INSERT INTO schools(id,name,slug) VALUES (1,'A','ecole-a'),(2,'B','ecole-b')")
            for sid, role, password in [(1, "enseignant", "PasswordA123"), (2, "parent", "PasswordB123")]:
                con.execute("INSERT INTO users(school_id,name,email,password_hash,role) VALUES (?,?,?,?,?)",
                    (sid, "Même personne", "same@example.test", generate_password_hash(password), role))
        self.client = project.app.test_client()

    def login(self, url, password):
        self.client.get(url)
        with self.client.session_transaction() as sess:
            token = sess.get("csrf")
        return self.client.post(url, data={"email":"same@example.test", "password":password, "csrf":token})

    def test_duplicate_mail_across_schools_but_not_within_school(self):
        with project.db() as con:
            self.assertEqual(con.execute("SELECT count(*) FROM users WHERE email='same@example.test'").fetchone()[0], 2)
            with self.assertRaises(sqlite3.IntegrityError):
                con.execute("INSERT INTO users(school_id,name,email,password_hash,role) VALUES (?,?,?,?,?)",
                    (1,"Duplicate","same@example.test","hash","parent"))

    def test_school_login_is_scoped(self):
        self.login("/ecole-a/login", "PasswordA123")
        with self.client.session_transaction() as sess:
            uid_a=sess.get("uid")
        self.assertIsNotNone(uid_a)
        with self.client.session_transaction() as sess:
            sess.clear()
        self.login("/ecole-b/login", "PasswordB123")
        with self.client.session_transaction() as sess:
            uid_b=sess.get("uid")
        self.assertIsNotNone(uid_b)
        self.assertNotEqual(uid_a, uid_b)

    def test_wrong_school_rejected(self):
        self.login("/ecole-a/login", "PasswordB123")
        with self.client.session_transaction() as sess:
            self.assertIsNone(sess.get("uid"))

    def test_modal_only_after_password_verified(self):
        response=self.login("/login","PasswordA123")
        with self.client.session_transaction() as sess:
            self.assertIsNotNone(sess.get("uid"))
        self.assertNotIn(b"school-choice-modal",response.data)

    def test_select_tenant_from_modal(self):
        with project.db() as con:
            con.execute("UPDATE users SET password_hash=? WHERE school_id=2",
                        (generate_password_hash("PasswordA123"),))
        response=self.login("/login","PasswordA123")
        self.assertIn(b"school-choice-modal",response.data)
        with self.client.session_transaction() as sess:
            token=sess["csrf"]
            self.assertIsNone(sess.get("uid"))
        result=self.client.post("/login/choose-school",data={"csrf":token,"school_id":"2"})
        self.assertEqual(result.status_code,302)
        with self.client.session_transaction() as sess:
            uid=sess["uid"]
        self.assertEqual(project.one("SELECT school_id FROM users WHERE id=?",(uid,))["school_id"],2)

    def test_reject_unrelated_tenant(self):
        with project.db() as con:
            con.execute("UPDATE users SET password_hash=? WHERE school_id=2",
                        (generate_password_hash("PasswordA123"),))
            con.execute("INSERT INTO schools(id,name,slug) VALUES (3,'C','ecole-c')")
        self.login("/login","PasswordA123")
        with self.client.session_transaction() as sess:
            token=sess["csrf"]
        result=self.client.post("/login/choose-school",data={"csrf":token,"school_id":"3"})
        self.assertEqual(result.status_code,403)


class MigrationTest(unittest.TestCase):
    def test_migration_preserves_references(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/"old.db"
            con=sqlite3.connect(path)
            con.executescript("""
                PRAGMA foreign_keys=ON;
                CREATE TABLE schools(id INTEGER PRIMARY KEY);
                CREATE TABLE users(id INTEGER PRIMARY KEY, school_id INTEGER REFERENCES schools(id),
                    name TEXT NOT NULL, email TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL,
                    role TEXT NOT NULL);
                CREATE TABLE enrollments(id INTEGER PRIMARY KEY, student_id INTEGER NOT NULL REFERENCES users(id));
                CREATE INDEX idx_users_name ON users(name);
                INSERT INTO schools(id) VALUES (1),(2);
                INSERT INTO users(id,school_id,name,email,password_hash,role)
                VALUES (50,1,'X','same@example.test','hash','etudiant');
                INSERT INTO enrollments(student_id) VALUES (50);
            """)
            con.close()
            subprocess.run([sys.executable,str(ROOT/"scripts/migrate_tenant_users.py"),str(path)],
                           check=True, capture_output=True, text=True)
            con=sqlite3.connect(path)
            con.execute("PRAGMA foreign_keys=ON")
            con.execute("INSERT INTO users(school_id,name,email,password_hash,role) VALUES (2,'Y','same@example.test','hash','parent')")
            self.assertEqual(con.execute("SELECT student_id FROM enrollments").fetchone()[0],50)
            self.assertEqual(con.execute("PRAGMA foreign_key_check").fetchall(),[])
            self.assertEqual(con.execute("PRAGMA integrity_check").fetchone()[0],"ok")
            con.close()


if __name__=="__main__":
    unittest.main()

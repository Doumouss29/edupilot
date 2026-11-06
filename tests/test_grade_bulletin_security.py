"""Security regression tests for grade changes and private school bulletins.

Runs only with disposable SQLite databases (never the VPS PostgreSQL database).
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
os.environ["SECRET_KEY"]="grade-security-test-key"
sys.path.insert(0,str(ROOT))
import app as project


class GradeAndBulletinSecurityTests(unittest.TestCase):
    def setUp(self):
        project.DB=str(Path(TEMP.name)/(self._testMethodName+".db"))
        with project.db() as conn:
            conn.executescript(project.SCHEMA)
            # The baseline SCHEMA predates the academic-year lifecycle migration.
            conn.execute("ALTER TABLE years ADD COLUMN status TEXT NOT NULL DEFAULT 'active'")
            # Error pages also render the academic navigation for administrators.
            conn.execute("ALTER TABLE classes ADD COLUMN filiere_id INTEGER")
            conn.execute("CREATE TABLE IF NOT EXISTS filieres(id INTEGER PRIMARY KEY, school_id INTEGER, name TEXT)")
            conn.execute("INSERT INTO schools(id,name,slug) VALUES (1,'School A','a'),(2,'School B','b')")
            for uid,sid,role in [(1,1,'admin'),(2,1,'enseignant'),(3,1,'etudiant'),
                                  (4,1,'parent'),(5,2,'etudiant'),(6,1,'etudiant'),(7,2,'admin')]:
                conn.execute("INSERT INTO users(id,school_id,name,email,password_hash,role) VALUES (?,?,?,?,?,?)",
                    (uid,sid,role,str(uid)+'@test.invalid',generate_password_hash('Password12345'),role))
            conn.execute("""INSERT INTO years(id,school_id,label,is_active,status)
                VALUES (1,1,'2026-2027',1,'active'),(2,1,'2025-2026',0,'archived'),
                       (3,2,'2026-2027',1,'active')""")
            conn.execute("""INSERT INTO classes(id,school_id,year_id,name,parents_enabled)
                VALUES (1,1,1,'Active A',1),(2,1,2,'Archive A',1),(3,2,3,'Class B',1)""")
            conn.execute("""INSERT INTO enrollments(school_id,student_id,class_id,year_id)
                VALUES (1,3,1,1),(1,3,2,2),(2,5,3,3)""")
            conn.execute("INSERT INTO parent_links(school_id,student_id,parent_id,active) VALUES (1,3,4,1)")
            conn.execute("""INSERT INTO courses(id,school_id,class_id,name,code,teacher_id)
                VALUES (1,1,1,'Course A','A',2),(2,1,2,'Past course','PAST',2),
                       (3,2,3,'Course B','B',NULL)""")
            conn.execute("""INSERT INTO assessments(id,school_id,course_id,title)
                VALUES (1,1,1,'Evaluation A'),(2,1,2,'Evaluation archived'),
                       (3,2,3,'Evaluation B')""")
            conn.execute("INSERT INTO periods(id,school_id,class_id,name,locked,published) VALUES (1,1,1,'Semestre',0,0),(2,1,2,'Semestre',0,0)")
        self.client=project.app.test_client()

    def user(self,uid):
        with self.client.session_transaction() as sess:
            sess.clear()
            sess["uid"]=uid
            sess["csrf"]="csrf-test"

    def post_grade(self,assessment,student,mark="14"):
        return self.client.post('/grades',data={
            "csrf":"csrf-test","assessment_id":str(assessment),
            "student_id":str(student),"value":mark})

    def assert_no_grade(self):
        with project.db() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM grades").fetchone()[0],0)

    def test_teacher_cannot_write_other_school_grade(self):
        self.user(2)
        self.assertEqual(self.post_grade(3,5).status_code,403)
        self.assert_no_grade()

    def test_teacher_cannot_write_unenrolled_student_grade(self):
        self.user(2)
        self.assertEqual(self.post_grade(1,6).status_code,403)
        self.assert_no_grade()

    def test_archived_grade_cannot_be_modified_even_by_admin(self):
        self.user(1)
        self.assertEqual(self.post_grade(2,3).status_code,403)
        self.assert_no_grade()

    def test_parent_cannot_post_grades(self):
        self.user(4)
        self.assertEqual(self.post_grade(1,3).status_code,403)
        self.assert_no_grade()

    def test_student_cannot_read_unpublished_bulletin(self):
        self.user(3)
        self.assertEqual(self.client.get('/grades/my-bulletin/1').status_code,403)

    def test_parent_cannot_access_unrelated_student_bulletin(self):
        self.user(4)
        self.assertEqual(self.client.get('/grades/my-bulletin/1?student_id=6').status_code,403)

    def test_foreign_school_bulletin_cannot_be_read(self):
        self.user(3)
        self.assertEqual(self.client.get('/grades/my-bulletin/3').status_code,403)

    def test_foreign_school_bulletin_cannot_be_published(self):
        self.user(1)
        result=self.client.post('/grades/bulletins/publish',
                                data={"csrf":"csrf-test","class_id":"3"})
        self.assertEqual(result.status_code,403)
        with project.db() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM bulletin_publications").fetchone()[0],0)

    def test_archived_bulletin_cannot_be_republished(self):
        self.user(1)
        result=self.client.post('/grades/bulletins/publish',
                                data={"csrf":"csrf-test","class_id":"2"})
        self.assertEqual(result.status_code,403)
        with project.db() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM bulletin_publications").fetchone()[0],0)


if __name__=="__main__":
    unittest.main()

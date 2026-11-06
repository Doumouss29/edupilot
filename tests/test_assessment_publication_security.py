"""Verify private assessment attachments cannot bypass academic publication status.

Disposable SQLite fixtures. No network calls and no production database access.
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
os.environ["DATABASE_PATH"]=str(Path(TEMP.name)/"start.db")
os.environ["SECRET_KEY"]="assessment-access-tests-only"
sys.path.insert(0,str(ROOT))
import app as project


class AssessmentPublicationSecurityTests(unittest.TestCase):
    def setUp(self):
        project.DB=str(Path(TEMP.name)/(self._testMethodName+".db"))
        with project.db() as conn:
            conn.executescript(project.SCHEMA)
            conn.execute("INSERT INTO schools(id,name,slug) VALUES (1,'School A','school-a'),(2,'School B','school-b')")
            for uid,sid,role in [(1,1,'etudiant'),(2,1,'parent'),(3,1,'enseignant'),(4,2,'etudiant'),(5,1,'admin'),(6,1,'etudiant')]:
                conn.execute("INSERT INTO users(id,school_id,name,email,password_hash,role) VALUES (?,?,?,?,?,?)",
                             (uid,sid,role,str(uid)+'@test.invalid',generate_password_hash('PasswordTest123'),role))
            conn.execute("INSERT INTO years(id,school_id,label,is_active) VALUES (1,1,'2026-2027',1),(2,2,'2026-2027',1)")
            conn.execute("INSERT INTO classes(id,school_id,year_id,name,parents_enabled) VALUES (1,1,1,'A',1),(2,2,2,'B',1)")
            conn.execute("INSERT INTO enrollments(school_id,student_id,class_id,year_id) VALUES (1,1,1,1),(2,4,2,2)")
            conn.execute("INSERT INTO parent_links(school_id,student_id,parent_id,active) VALUES (1,1,2,1)")
            conn.execute("INSERT INTO courses(id,school_id,class_id,name,code,teacher_id) VALUES (1,1,1,'SIG','SIG',3),(2,2,2,'Topographie','TOP',NULL)")
            for aid,sid,cid,published in [(10,1,1,0),(11,1,1,1),(12,2,2,1)]:
                conn.execute("""INSERT INTO assessments(id,school_id,course_id,title,published,attachment_name,attachment_blob,attachment_mime)
                    VALUES (?,?,?,?,?,?,?,?)""",
                    (aid,sid,cid,'Test',published,'sujet.pdf',b'%PDF-1.4 test','application/pdf'))
                conn.execute("INSERT INTO assessment_files(assessment_id,filename,mime,content) VALUES (?,?,?,?)",
                             (aid,'sujet.pdf','application/pdf',b'%PDF-1.4 test'))
            self.files={
                r['assessment_id']:r['id']
                for r in conn.execute("SELECT id,assessment_id FROM assessment_files")
            }
        self.client=project.app.test_client()

    def user(self,uid):
        with self.client.session_transaction() as sess:
            sess.clear()
            sess['uid']=uid
            sess['csrf']='test-csrf'

    def test_unpublished_files_hidden_from_student(self):
        self.user(1)
        self.assertEqual(self.client.get('/assessments/10/attachment').status_code,404)
        self.assertEqual(self.client.get('/assessments/files/'+str(self.files[10])).status_code,404)
        self.assertEqual(self.client.get('/assessments/11/attachment').status_code,200)
        self.assertEqual(self.client.get('/assessments/files/'+str(self.files[11])).status_code,200)

    def test_unpublished_files_hidden_from_parent(self):
        self.user(2)
        self.assertEqual(self.client.get('/assessments/10/attachment').status_code,404)
        self.assertEqual(self.client.get('/assessments/files/'+str(self.files[10])).status_code,404)
        self.assertEqual(self.client.get('/assessments/11/attachment').status_code,200)

    def test_assigned_teacher_can_consult_draft(self):
        self.user(3)
        self.assertEqual(self.client.get('/assessments/10/attachment').status_code,200)
        self.assertEqual(self.client.get('/assessments/files/'+str(self.files[10])).status_code,200)

    def test_cross_school_attachment_is_inaccessible(self):
        self.user(1)
        self.assertEqual(self.client.get('/assessments/12/attachment').status_code,404)
        self.assertEqual(self.client.get('/assessments/files/'+str(self.files[12])).status_code,404)

    def test_unrelated_student_cannot_see_published_file(self):
        self.user(4)
        self.assertEqual(self.client.get('/assessments/11/attachment').status_code,404)
        self.assertEqual(self.client.get('/assessments/files/'+str(self.files[11])).status_code,404)

    def test_same_school_unenrolled_student_cannot_read_published_file(self):
        self.user(6)
        self.assertEqual(self.client.get('/assessments/11/attachment').status_code,403)
        self.assertEqual(self.client.get('/assessments/files/'+str(self.files[11])).status_code,403)


if __name__=='__main__':
    unittest.main()

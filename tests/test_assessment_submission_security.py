"""Student assignment submissions: access control, deadlines and file validation."""
import io
import os
import sys
import tempfile
import unittest
from pathlib import Path
from werkzeug.security import generate_password_hash

ROOT=Path(__file__).resolve().parents[1]
TEMP=tempfile.TemporaryDirectory()
os.environ['DB_ENGINE']='sqlite'
os.environ['DATABASE_PATH']=str(Path(TEMP.name)/'bootstrap.db')
os.environ['SECRET_KEY']='student-submission-security-tests'
sys.path.insert(0,str(ROOT))
import app as project


class AssessmentSubmissionSecurityTests(unittest.TestCase):
    def setUp(self):
        project.DB=str(Path(TEMP.name)/(self._testMethodName+'.db'))
        project.SUBMISSION_ROOT=Path(TEMP.name)/('files-'+self._testMethodName)
        project.SUBMISSION_ROOT.mkdir(parents=True,exist_ok=True)
        with project.db() as c:
            c.executescript(project.SCHEMA)
            c.execute("ALTER TABLE years ADD COLUMN status TEXT NOT NULL DEFAULT 'active'")
            c.execute("ALTER TABLE classes ADD COLUMN filiere_id INTEGER")
            c.execute("""CREATE TABLE IF NOT EXISTS assessment_corrections(
                assessment_id INTEGER PRIMARY KEY,school_id INTEGER,author_id INTEGER,
                body TEXT DEFAULT '',filename TEXT,stored_name TEXT,mime_type TEXT,
                bytes_size INTEGER DEFAULT 0,published INTEGER DEFAULT 0,updated_at TEXT)""")
            c.execute("CREATE TABLE IF NOT EXISTS filieres(id INTEGER PRIMARY KEY,school_id INTEGER,name TEXT)")
            c.execute("INSERT INTO schools(id,name,slug) VALUES (1,'School A','school-a'),(2,'School B','school-b')")
            for uid,sid,role in [(1,1,'etudiant'),(2,1,'etudiant'),(3,1,'enseignant'),(4,1,'admin'),
                                 (5,2,'etudiant'),(6,2,'enseignant'),(7,1,'parent')]:
                c.execute("""INSERT INTO users(id,school_id,name,email,password_hash,role)
                             VALUES (?,?,?,?,?,?)""",
                    (uid,sid,'User '+str(uid),'u'+str(uid)+'@test.invalid',
                     generate_password_hash('PasswordTest123'),role))
            c.execute("""INSERT INTO years(id,school_id,label,is_active,status) VALUES
                (1,1,'2026-2027',1,'active'),(2,2,'2026-2027',1,'active'),
                (3,1,'2025-2026',0,'archived')""")
            c.execute("""INSERT INTO classes(id,school_id,year_id,name) VALUES
                (1,1,1,'Classe A'),(2,2,2,'Classe B'),(3,1,3,'Archive')""")
            c.execute("INSERT INTO enrollments(school_id,student_id,class_id,year_id) VALUES (1,1,1,1),(2,5,2,2)")
            c.execute("""INSERT INTO courses(id,school_id,class_id,name,code,teacher_id) VALUES
                (1,1,1,'Python','PY',3),(2,2,2,'Autre','XX',6),(3,1,3,'Ancien','OLD',3)""")
            c.execute("""INSERT INTO assessments(id,school_id,course_id,title,published,due_date) VALUES
                (1,1,1,'TP Python',1,NULL),(2,2,2,'Évaluation B',1,NULL),
                (3,1,1,'Brouillon',0,NULL),(4,1,3,'Archive',1,NULL),
                (5,1,1,'Expiré',1,'2020-01-01')""")
        self.client=project.app.test_client()

    def actor(self,uid):
        user=project.one('SELECT * FROM users WHERE id=?',(uid,))
        with self.client.session_transaction() as sess:
            sess.clear()
            sess['uid']=uid
            sess['auth_stamp']=project.session_auth_stamp(user)
            sess['csrf']='csrf-submission'

    def submit(self,aid=1,name='solution.py',data=b"print('hello')"):
        return self.client.post('/assessments/'+str(aid)+'/submit',data={
            'csrf':'csrf-submission',
            'submission_file':(io.BytesIO(data),name),
        },content_type='multipart/form-data')

    def test_student_can_submit_python_code(self):
        self.actor(1)
        self.assertEqual(self.submit().status_code,302)
        row=project.one('SELECT filename,filepath FROM submissions WHERE assessment_id=1 AND student_id=1')
        self.assertEqual(row['filename'],'solution.py')
        self.assertRegex(row['filepath'],r'^[0-9a-f]{32}$')
        response=self.client.get('/assessments/1/submissions/1/download')
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.data,b"print('hello')")
        self.assertIn('attachment',response.headers['Content-Disposition'])

    def test_student_can_submit_html_and_css_as_zip(self):
        self.actor(1)
        import zipfile
        buffer=io.BytesIO()
        with zipfile.ZipFile(buffer,'w') as out:
            out.writestr('index.html','<h1>Hi</h1>')
            out.writestr('style.css','h1{color:red}')
        self.assertEqual(self.submit(name='site.zip',data=buffer.getvalue()).status_code,302)

    def test_second_submission_replaces_previous(self):
        self.actor(1)
        self.assertEqual(self.submit().status_code,302)
        old=project.one('SELECT filepath FROM submissions WHERE student_id=1')['filepath']
        self.assertEqual(self.submit(name='solution.css',data=b'body{}').status_code,302)
        rows=project.allrows('SELECT filename,filepath FROM submissions WHERE student_id=1')
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['filename'],'solution.css')
        self.assertNotEqual(rows[0]['filepath'],old)
        self.assertFalse((project.SUBMISSION_ROOT/'1'/old).exists())

    def test_unenrolled_student_cannot_submit(self):
        self.actor(2)
        self.assertEqual(self.submit().status_code,403)

    def test_other_school_student_cannot_submit(self):
        self.actor(5)
        self.assertEqual(self.submit().status_code,404)

    def test_unpublished_evaluation_rejects_submission(self):
        self.actor(1)
        self.assertEqual(self.submit(aid=3).status_code,403)

    def test_archived_evaluation_rejects_submission(self):
        self.actor(1)
        self.assertEqual(self.submit(aid=4).status_code,403)

    def test_expired_evaluation_rejects_submission(self):
        self.actor(1)
        self.assertEqual(self.submit(aid=5).status_code,403)

    def test_executable_file_is_rejected(self):
        self.actor(1)
        self.assertEqual(self.submit(name='run.exe',data=b'MZ'+b'A'*10).status_code,400)
        self.assertIsNone(project.one('SELECT id FROM submissions WHERE student_id=1'))

    def test_teacher_can_download_own_class_submission(self):
        self.actor(1)
        self.assertEqual(self.submit().status_code,302)
        self.actor(3)
        self.assertEqual(self.client.get('/assessments/1/submissions/1/download').status_code,200)

    def test_other_student_cannot_download_submission(self):
        self.actor(1)
        self.assertEqual(self.submit().status_code,302)
        self.actor(2)
        self.assertEqual(self.client.get('/assessments/1/submissions/1/download').status_code,403)

    def test_foreign_school_teacher_cannot_download(self):
        self.actor(1)
        self.assertEqual(self.submit().status_code,302)
        self.actor(6)
        self.assertEqual(self.client.get('/assessments/1/submissions/1/download').status_code,404)

    def test_parent_cannot_download_submission(self):
        self.actor(1)
        self.assertEqual(self.submit().status_code,302)
        self.actor(7)
        self.assertEqual(self.client.get('/assessments/1/submissions/1/download').status_code,403)

    def test_assessment_page_shows_submission_and_download(self):
        self.actor(1)
        self.assertEqual(self.submit().status_code,302)
        page=self.client.get('/assessments')
        self.assertEqual(page.status_code,200)
        self.assertIn(b'solution.py',page.data)


if __name__=='__main__':
    unittest.main()

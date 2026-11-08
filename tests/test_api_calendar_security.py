"""Regression checks for planning APIs, school isolation and archived attendance.

Fixtures use isolated SQLite files; no production PostgreSQL access.
"""
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
os.environ['SECRET_KEY']='api-authorization-tests'
sys.path.insert(0,str(ROOT))
import app as project


class ApiAndCalendarSecurityTests(unittest.TestCase):
    def setUp(self):
        project.DB=str(Path(TEMP.name)/(self._testMethodName+'.db'))
        with project.db() as c:
            c.executescript(project.SCHEMA)
            c.execute("ALTER TABLE years ADD COLUMN status TEXT NOT NULL DEFAULT 'active'")
            c.execute("ALTER TABLE classes ADD COLUMN filiere_id INTEGER")
            c.execute("ALTER TABLE lessons ADD COLUMN hidden_from_planning INTEGER NOT NULL DEFAULT 0")
            c.execute("ALTER TABLE lessons ADD COLUMN series_id TEXT")
            c.execute("CREATE TABLE IF NOT EXISTS filieres(id INTEGER PRIMARY KEY, school_id INTEGER, name TEXT)")
            c.execute("INSERT INTO schools(id,name,slug) VALUES (1,'School A','a'),(2,'School B','b')")
            for uid,sid,role in [(1,1,'etudiant'),(2,1,'parent'),(3,1,'enseignant'),
                                  (4,1,'admin'),(5,2,'etudiant'),(6,2,'admin'),
                                  (7,1,'etudiant'),(8,1,'parent')]:
                c.execute("INSERT INTO users(id,school_id,name,email,password_hash,role) VALUES (?,?,?,?,?,?)",
                    (uid,sid,role,f'api-{uid}@test.invalid',generate_password_hash('PasswordTest123'),role))
            c.execute("""INSERT INTO years(id,school_id,label,is_active,status) VALUES
                (1,1,'2026-2027',1,'active'),(2,1,'2025-2026',0,'archived'),
                (3,2,'2026-2027',1,'active')""")
            c.execute("""INSERT INTO classes(id,school_id,year_id,name,parents_enabled) VALUES
                (1,1,1,'Active A',1),(2,1,2,'Archive A',1),(3,2,3,'Class B',1)""")
            c.execute("""INSERT INTO enrollments(school_id,student_id,class_id,year_id)
                VALUES (1,1,1,1),(1,1,2,2),(2,5,3,3)""")
            c.execute("INSERT INTO parent_links(school_id,student_id,parent_id,active) VALUES (1,1,2,1)")
            c.execute("""INSERT INTO courses(id,school_id,class_id,name,code,teacher_id) VALUES
                (1,1,1,'Course A','A',3),(2,1,2,'Past course','PAST',3),
                (3,2,3,'Course B','B',6)""")
            c.execute("""INSERT INTO lessons(id,school_id,course_id,teacher_id,starts_at,ends_at)
                VALUES (1,1,1,3,'2026-11-09T08:00','2026-11-09T09:00'),
                       (2,1,2,3,'2025-11-10T08:00','2025-11-10T09:00'),
                       (3,2,3,6,'2026-11-09T09:00','2026-11-09T10:00')""")
            c.execute("""INSERT INTO notifications(id,school_id,user_id,message)
                VALUES (1,1,1,'Private A'),(2,2,5,'Private B')""")
            c.execute("""CREATE TABLE IF NOT EXISTS course_documents(
                id INTEGER PRIMARY KEY,school_id INTEGER,course_id INTEGER,uploader_id INTEGER,
                filename TEXT,stored_name TEXT,title TEXT,description TEXT,category TEXT,
                mime_type TEXT,bytes_size INTEGER,published INTEGER,publish_at TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
            c.execute("""INSERT INTO course_documents
                (id,school_id,course_id,uploader_id,filename,stored_name,title,description,category,mime_type,bytes_size,published)
                VALUES (1,1,1,3,'private.pdf','0123456789abcdef0123456789abcdef','Private','', 'Cours','application/pdf',10,0),
                       (2,2,3,6,'foreign.pdf','0123456789abcdef0123456789abcdef','Foreign','', 'Cours','application/pdf',10,1)""")
        self.client=project.app.test_client()

    def actor(self,uid):
        user=project.one('SELECT * FROM users WHERE id=?',(uid,))
        with self.client.session_transaction() as sess:
            sess.clear()
            sess['uid']=uid
            sess['auth_stamp']=project.session_auth_stamp(user)
            sess['csrf']='api-test-csrf'

    def post(self,url,payload):
        return self.client.post(url,json=payload,headers={'X-CSRF-Token':'api-test-csrf'})

    def test_student_only_sees_own_school_active_class_calendar(self):
        self.actor(1)
        result=self.client.get('/api/planning')
        self.assertEqual(result.status_code,200)
        self.assertEqual([item['id'] for item in result.get_json()],[1])

    def test_parent_only_sees_linked_child_calendar(self):
        self.actor(2)
        result=self.client.get('/api/planning')
        self.assertEqual(result.status_code,200)
        self.assertEqual([item['id'] for item in result.get_json()],[1])

    def test_unlinked_parent_cannot_see_student_calendar(self):
        self.actor(8)
        result=self.client.get('/api/planning')
        self.assertEqual(result.status_code,200)
        self.assertEqual(result.get_json(),[])

    def test_teacher_only_sees_assigned_calendar(self):
        self.actor(3)
        result=self.client.get('/api/planning')
        self.assertEqual(result.status_code,200)
        self.assertEqual([item['id'] for item in result.get_json()],[1])

    def test_student_cannot_write_attendance(self):
        self.actor(1)
        result=self.client.post('/attendance/1',data={'csrf':'api-test-csrf','student_1':'absent'})
        self.assertEqual(result.status_code,403)

    def test_archived_attendance_cannot_be_changed(self):
        self.actor(4)
        result=self.client.post('/attendance/2',data={'csrf':'api-test-csrf','student_1':'absent'})
        self.assertEqual(result.status_code,403)
        self.assertEqual(project.one('SELECT COUNT(*) AS n FROM attendance')['n'],0)

    def test_foreign_school_attendance_inaccessible(self):
        self.actor(4)
        self.assertEqual(self.client.get('/attendance/3').status_code,403)
        self.assertEqual(self.client.post('/attendance/3',data={'csrf':'api-test-csrf'}).status_code,403)

    def test_unenrolled_student_cannot_open_course_documents(self):
        self.actor(7)
        self.assertEqual(self.client.get('/courses/1/documents').status_code,403)
        self.assertEqual(self.client.get('/course-documents/1/file').status_code,403)

    def test_teacher_cannot_open_foreign_school_documents(self):
        self.actor(3)
        self.assertEqual(self.client.get('/courses/3/documents').status_code,404)
        self.assertEqual(self.client.get('/course-documents/2/file').status_code,404)

    def test_student_cannot_download_unpublished_document(self):
        self.actor(1)
        self.assertEqual(self.client.get('/course-documents/1/file').status_code,404)

    def test_notifications_are_user_scoped(self):
        self.actor(1)
        result=self.client.get('/api/notifications')
        self.assertEqual(result.status_code,200)
        self.assertEqual([item['message'] for item in result.get_json()['notifications']],['Private A'])

    def test_foreign_notification_cannot_be_marked_read(self):
        self.actor(1)
        result=self.post('/api/notifications/read',{'ids':[2]})
        self.assertEqual(result.status_code,200)
        self.assertEqual(project.one('SELECT read FROM notifications WHERE id=2')['read'],0)

    def test_foreign_notification_cannot_be_deleted(self):
        self.actor(1)
        result=self.post('/api/notifications/delete',{'ids':[2]})
        self.assertEqual(result.status_code,200)
        self.assertIsNotNone(project.one('SELECT id FROM notifications WHERE id=2'))


if __name__=='__main__':
    unittest.main()

"""Deletion of school users must clear auxiliary notification jobs safely."""
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
os.environ['SECRET_KEY']='delete-user-test'
sys.path.insert(0,str(ROOT))
import app as project


class SchoolUserDeletionTests(unittest.TestCase):
    def setUp(self):
        project.DB=str(Path(TEMP.name)/(self._testMethodName+'.db'))
        with project.db() as c:
            c.executescript(project.SCHEMA)
            c.execute("INSERT INTO schools(id,name,slug) VALUES (1,'École Alpha','alpha')")
            for uid,role in ((1,'admin'),(2,'etudiant')):
                c.execute("""INSERT INTO users(id,school_id,name,email,password_hash,role)
                    VALUES (?,?,?,?,?,?)""",
                    (uid,1,'Personne '+str(uid),f'p{uid}@example.test',
                     generate_password_hash('Password1234'),role))
            c.execute("""CREATE TABLE IF NOT EXISTS notification_delivery_queue(
                id INTEGER PRIMARY KEY,school_id INTEGER NOT NULL REFERENCES schools(id),
                user_id INTEGER NOT NULL REFERENCES users(id),channel TEXT NOT NULL,
                address TEXT,subject TEXT,message TEXT NOT NULL,href TEXT DEFAULT '',
                status TEXT DEFAULT 'pending',attempts INTEGER DEFAULT 0,claimed_at INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,html_content TEXT)""")
            c.execute("""INSERT INTO notification_delivery_queue
                 (school_id,user_id,channel,message,href)
                 VALUES (1,2,'email','Planning disponible','/planning')""")
            c.execute("""INSERT INTO notifications(school_id,user_id,message)
                VALUES (1,2,'Planning disponible')""")
        self.client=project.app.test_client()
        u=project.one('SELECT * FROM users WHERE id=1')
        with self.client.session_transaction() as sess:
            sess['uid']=1
            sess['auth_stamp']=project.session_auth_stamp(u)
            sess['csrf']='delete-user-csrf'

    def test_delete_without_academic_history_cleans_queued_email(self):
        response=self.client.post('/people/bulk',data={
            'csrf':'delete-user-csrf','action':'delete','user_ids':['2']})
        self.assertEqual(response.status_code,302)
        self.assertIsNone(project.one('SELECT id FROM users WHERE id=2'))
        self.assertEqual(project.one('SELECT COUNT(*) n FROM notification_delivery_queue WHERE user_id=2')['n'],0)
        self.assertEqual(project.one('SELECT COUNT(*) n FROM notifications WHERE user_id=2')['n'],0)

    def test_user_with_academic_history_cannot_be_deleted(self):
        with project.db() as c:
            c.execute("INSERT INTO years(id,school_id,label) VALUES (1,1,'2026-2027')")
            c.execute("INSERT INTO classes(id,school_id,year_id,name) VALUES (1,1,1,'Classe A')")
            c.execute("INSERT INTO courses(id,school_id,class_id,name,code) VALUES (1,1,1,'SIG','SIG')")
            c.execute("INSERT INTO assessments(id,school_id,course_id,title) VALUES (1,1,1,'Examen')")
            c.execute("INSERT INTO grades(assessment_id,student_id,value) VALUES (1,2,16)")
        response=self.client.post('/people/bulk',data={
            'csrf':'delete-user-csrf','action':'delete','user_ids':['2']})
        self.assertEqual(response.status_code,302)
        self.assertIsNotNone(project.one('SELECT id FROM users WHERE id=2'))
        self.assertEqual(project.one('SELECT COUNT(*) n FROM notification_delivery_queue WHERE user_id=2')['n'],1)


if __name__=='__main__':
    unittest.main()

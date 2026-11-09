"""Planning publication modes, private drafts and manually queued email.

All fixtures are isolated SQLite databases; production PostgreSQL untouched.
"""
import datetime
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
os.environ['SECRET_KEY']='planning-publication-tests'
sys.path.insert(0,str(ROOT))
import app as project


class PlanningPublicationSecurityTests(unittest.TestCase):
    def setUp(self):
        project.DB=str(Path(TEMP.name)/(self._testMethodName+'.db'))
        with project.db() as c:
            c.executescript(project.SCHEMA)
            c.execute("ALTER TABLE lessons ADD COLUMN hidden_from_planning INTEGER NOT NULL DEFAULT 0")
            c.execute("ALTER TABLE lessons ADD COLUMN series_id TEXT")
            c.execute("ALTER TABLE years ADD COLUMN status TEXT NOT NULL DEFAULT 'active'")
            c.execute("ALTER TABLE classes ADD COLUMN filiere_id INTEGER")
            c.execute("ALTER TABLE classes ADD COLUMN video_url TEXT")
            c.execute("CREATE TABLE IF NOT EXISTS filieres(id INTEGER PRIMARY KEY,school_id INTEGER,name TEXT)")
            c.execute("""CREATE TABLE IF NOT EXISTS notification_delivery_queue(
                id INTEGER PRIMARY KEY,school_id INTEGER,user_id INTEGER,
                channel TEXT,address TEXT,subject TEXT,message TEXT,href TEXT,
                status TEXT DEFAULT 'pending',attempts INTEGER DEFAULT 0,
                claimed_at INTEGER DEFAULT 0,created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                html_content TEXT)""")
            c.execute("""INSERT INTO schools(id,name,slug,planning_mode) VALUES
                (1,'École Alpha','alpha','private'),(2,'École Beta','beta','dynamic')""")
            for uid,sid,role in [(1,1,'admin'),(2,1,'enseignant'),(3,1,'etudiant'),
                                  (4,1,'etudiant'),(5,1,'parent'),(6,2,'etudiant'),
                                  (7,2,'enseignant'),(8,None,'superadmin')]:
                c.execute("""INSERT INTO users(id,school_id,name,email,password_hash,role)
                    VALUES (?,?,?,?,?,?)""",
                    (uid,sid,f'Personne {uid}',f'personne{uid}@test.invalid',
                     generate_password_hash('Password1234'),role))
            c.execute("""INSERT INTO years(id,school_id,label,is_active,status) VALUES
                (1,1,'2026-2027',1,'active'),(2,2,'2026-2027',1,'active')""")
            c.execute("""INSERT INTO classes(id,school_id,year_id,name,parents_enabled) VALUES
                (1,1,1,'Classe 1',1),(2,1,1,'Classe 2',1),(3,2,2,'Classe B',1)""")
            c.execute("""INSERT INTO enrollments(school_id,student_id,class_id,year_id) VALUES
                (1,3,1,1),(1,4,2,1),(2,6,3,2)""")
            c.execute("""INSERT INTO courses(id,school_id,class_id,name,code,teacher_id) VALUES
                (1,1,1,'Python & SIG','PY',2),
                (2,1,2,'Autre cours','AU',2),
                (3,2,3,'Cours B','B',7)""")
            c.execute("""INSERT INTO lessons(id,school_id,course_id,teacher_id,starts_at,ends_at,
                    status,planning_shared) VALUES
                (1,1,1,2,'2026-11-10T08:00','2026-11-10T10:00','programmee',0),
                (2,1,2,2,'2026-11-11T08:00','2026-11-11T10:00','programmee',0),
                (3,2,3,7,'2026-11-10T09:00','2026-11-10T11:00','programmee',1)""")
            c.execute("INSERT INTO parent_links(school_id,student_id,parent_id,active) VALUES (1,3,5,1)")
        self.client=project.app.test_client()

    def actor(self,uid):
        u=project.one('SELECT * FROM users WHERE id=?',(uid,))
        with self.client.session_transaction() as session:
            session.clear()
            session['uid']=uid
            session['auth_stamp']=project.session_auth_stamp(u)
            session['csrf']='publication-csrf'

    def share(self):
        return self.client.post('/planning/share',data={
            'csrf':'publication-csrf','week':'2026-11-09'})

    def test_private_unshared_student_calendar_empty(self):
        self.actor(3)
        response=self.client.get('/api/planning')
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.get_json(),[])

    def test_private_unshared_parent_calendar_empty(self):
        self.actor(5)
        self.assertEqual(self.client.get('/api/planning').get_json(),[])

    def test_private_unshared_teacher_calendar_empty(self):
        self.actor(2)
        self.assertEqual(self.client.get('/api/planning').get_json(),[])

    def test_admin_can_see_unshared_drafts(self):
        self.actor(1)
        response=self.client.get('/api/planning')
        self.assertEqual({row['id'] for row in response.get_json()},{1,2})

    def test_admin_can_share_and_publish(self):
        self.actor(1)
        response=self.share()
        self.assertEqual(response.status_code,302)
        self.assertEqual(project.one('SELECT planning_shared FROM lessons WHERE id=1')['planning_shared'],1)
        self.actor(3)
        response=self.client.get('/api/planning')
        self.assertEqual([row['id'] for row in response.get_json()],[1])

    def test_shared_parent_calendar_shows_child_only(self):
        self.actor(1)
        self.share()
        self.actor(5)
        self.assertEqual([row['id'] for row in self.client.get('/api/planning').get_json()],[1])

    def test_ajax_share_keeps_calendar_without_redirect(self):
        self.actor(1)
        response=self.client.post('/planning/share',data={
            'csrf':'publication-csrf','week':'2026-11-09'},
            headers={'Accept':'application/json'})
        self.assertEqual(response.status_code,200)
        self.assertTrue(response.is_json)
        self.assertTrue(response.get_json()['ok'])
        self.assertEqual(response.get_json()['queued'],3)

    def test_share_queues_one_email_per_teacher_and_student(self):
        self.actor(1)
        self.share()
        rows=project.allrows("SELECT user_id,message,html_content FROM notification_delivery_queue ORDER BY user_id")
        self.assertEqual([row['user_id'] for row in rows],[2,3,4])
        mails={row['user_id']:row for row in rows}
        self.assertIn('Python & SIG',mails[3]['message'])
        self.assertNotIn('Autre cours',mails[3]['message'])
        self.assertIn('Autre cours',mails[4]['message'])
        self.assertNotIn('Python & SIG',mails[4]['message'])
        self.assertIn('Python & SIG',mails[2]['message'])
        self.assertIn('Autre cours',mails[2]['message'])
        self.assertIn('<table',mails[3]['html_content'])
        self.assertIn('\n',mails[3]['message'])
        self.assertNotIn('\\n',mails[3]['message'])

    def test_unenrolled_and_foreign_school_not_emailed(self):
        self.actor(1)
        self.share()
        ids={r['user_id'] for r in project.allrows('SELECT user_id FROM notification_delivery_queue')}
        self.assertFalse(ids.intersection({1,5,6,7,8}))

    def test_student_cannot_share(self):
        self.actor(3)
        self.assertEqual(self.share().status_code,403)
        self.assertEqual(project.one('SELECT planning_shared FROM lessons WHERE id=1')['planning_shared'],0)

    def test_dynamic_calendar_shows_sessions_without_share(self):
        self.actor(6)
        events=self.client.get('/api/planning').get_json()
        self.assertEqual([item['id'] for item in events],[3])

    def test_switch_from_dynamic_to_private_retracts_older_sessions(self):
        self.actor(8)
        response=self.client.post('/schools/2/update',data={
            'csrf':'publication-csrf','action':'update','name':'École Beta',
            'slug':'beta','plan':'standard','planning_mode':'private'})
        self.assertEqual(response.status_code,302)
        self.assertEqual(project.one('SELECT planning_mode FROM schools WHERE id=2')['planning_mode'],'private')
        self.assertEqual(project.one('SELECT planning_shared FROM lessons WHERE id=3')['planning_shared'],0)
        self.actor(6)
        self.assertEqual(self.client.get('/api/planning').get_json(),[])

    def test_private_creation_stays_draft_and_sends_no_notifications(self):
        self.actor(1)
        response=self.client.post('/planning',data={
            'csrf':'publication-csrf','course_id':'1','class_id':'1',
            'mode':'unique','planning_timezone':'Africa/Abidjan',
            'lesson_date':'2026-11-24','start_time':'08:00',
            'duration_hours':'2','room':'A2'})
        self.assertEqual(response.status_code,302)
        added=project.one("SELECT id,planning_shared FROM lessons WHERE starts_at='2026-11-24T08:00'")
        self.assertIsNotNone(added)
        self.assertEqual(added['planning_shared'],0)
        self.assertEqual(project.one('SELECT COUNT(*) n FROM notifications')['n'],0)

    def test_planning_notification_only_queues_push_not_email(self):
        self.actor(1)
        # notify() reads the authenticated school from Flask's request session.
        # A direct Python call must explicitly provide that request context.
        from flask import session
        user=project.one('SELECT * FROM users WHERE id=1')
        with project.app.test_request_context('/planning'):
            session['uid']=1
            session['auth_stamp']=project.session_auth_stamp(user)
            project.notify([2,3],'Planning modifié','/planning',
                           email_roles=('etudiant',),defer_external=True)
        rows=project.allrows('SELECT channel FROM notification_delivery_queue')
        self.assertEqual([row['channel'] for row in rows],['push','push'])

    def test_private_draft_edit_does_not_notify_students(self):
        self.actor(1)
        response=self.client.post('/lessons/1/edit',data={
            'csrf':'publication-csrf','course_id':'1',
            'lesson_date':'2026-11-12','start_time':'08:00',
            'duration_hours':'2','room':'A2'})
        self.assertEqual(response.status_code,302)
        self.assertEqual(project.one('SELECT COUNT(*) n FROM notifications')['n'],0)

    def test_plaintext_and_html_escape_user_content(self):
        user={'name':'Étudiant Test'}
        lesson={'starts_at':'2026-11-10T08:00','ends_at':'2026-11-10T09:00',
                'course_name':'<script>alert(1)</script>','class_name':'Master 2','room':'A1'}
        start=datetime.date(2026,11,9)
        plain,markup=project.planning_email_content(user,[lesson],start,start+datetime.timedelta(days=7),'École')
        self.assertIn('Mardi 10/11/2026',plain)
        self.assertIn('&lt;script&gt;',markup)
        self.assertNotIn('<script>',markup)
        self.assertIn('\n',plain)
        self.assertNotIn('\\n',plain)


if __name__=='__main__':
    unittest.main()

"""Planning deletion scope and recurrence security (disposable SQLite only)."""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from werkzeug.security import generate_password_hash

ROOT=Path(__file__).resolve().parents[1]
TEMP=tempfile.TemporaryDirectory()
os.environ['DB_ENGINE']='sqlite'
os.environ['DATABASE_PATH']=str(Path(TEMP.name)/'boot.db')
os.environ['SECRET_KEY']='planning-series-test-only'
sys.path.insert(0,str(ROOT))
import app as project


class PlanningSeriesSecurityTests(unittest.TestCase):
    def setUp(self):
        project.DB=str(Path(TEMP.name)/(self._testMethodName+'.db'))
        with project.db() as c:
            c.executescript(project.SCHEMA)
            c.execute("ALTER TABLE years ADD COLUMN status TEXT NOT NULL DEFAULT 'active'")
            c.execute("ALTER TABLE classes ADD COLUMN filiere_id INTEGER")
            c.execute("ALTER TABLE lessons ADD COLUMN hidden_from_planning INTEGER NOT NULL DEFAULT 0")
            c.execute("ALTER TABLE lessons ADD COLUMN series_id TEXT")
            c.execute("CREATE TABLE IF NOT EXISTS filieres(id INTEGER PRIMARY KEY,school_id INTEGER,name TEXT)")
            c.execute("INSERT INTO schools(id,name,slug) VALUES (1,'A','a'),(2,'B','b')")
            for uid,sid,role in [(1,1,'admin'),(2,1,'administratif'),(3,1,'enseignant'),(4,1,'etudiant'),(5,2,'admin')]:
                c.execute("INSERT INTO users(id,school_id,name,email,password_hash,role) VALUES (?,?,?,?,?,?)",
                    (uid,sid,'Tester',f'test{uid}@invalid.test',generate_password_hash('TestPassword123'),role))
            c.execute("""INSERT INTO years(id,school_id,label,is_active,status) VALUES
                (1,1,'2026-2027',1,'active'),(2,2,'2026-2027',1,'active'),
                (3,1,'2025-2026',0,'archived')""")
            c.execute("""INSERT INTO classes(id,school_id,year_id,name) VALUES
                (1,1,1,'A1'),(2,2,2,'B1'),(3,1,3,'Archive')""")
            c.execute("""INSERT INTO courses(id,school_id,class_id,name,code,teacher_id) VALUES
                (1,1,1,'Cours A','A',3),(2,2,2,'Cours B','B',5),(3,1,3,'Old','OLD',3)""")
            # Dates chosen in distant future so scheduled lessons are not historic.
            c.execute("""INSERT INTO lessons(id,school_id,course_id,teacher_id,starts_at,ends_at,status,series_id) VALUES
                (1,1,1,3,'2098-03-03T08:00','2098-03-03T09:00','programmee','seriesAAA'),
                (2,1,1,3,'2098-03-10T08:00','2098-03-10T09:00','programmee','seriesAAA'),
                (3,1,1,3,'2098-03-17T08:00','2098-03-17T09:00','realisee','seriesAAA'),
                (4,1,1,3,'2098-03-24T08:00','2098-03-24T09:00','programmee',NULL),
                (5,2,2,5,'2098-03-03T08:00','2098-03-03T09:00','programmee','seriesAAA'),
                (6,1,3,3,'2025-03-03T08:00','2025-03-03T09:00','realisee','seriesOLD')""")
        self.client=project.app.test_client()

    def actor(self,uid):
        user=project.one('SELECT * FROM users WHERE id=?',(uid,))
        with self.client.session_transaction() as sess:
            sess.clear()
            sess['uid']=uid
            sess['auth_stamp']=project.session_auth_stamp(user)
            sess['csrf']='series-csrf'

    def delete(self,lid,scope='occurrence'):
        return self.client.post(f'/lessons/{lid}/delete',
            data={'csrf':'series-csrf','scope':scope})

    def test_deleting_one_occurrence_does_not_delete_siblings(self):
        self.actor(1)
        self.assertEqual(self.delete(1).status_code,302)
        self.assertIsNone(project.one('SELECT id FROM lessons WHERE id=1'))
        self.assertIsNotNone(project.one('SELECT id FROM lessons WHERE id=2'))

    def test_deleting_series_removes_pending_and_hides_historical(self):
        self.actor(1)
        self.assertEqual(self.delete(1,'series').status_code,302)
        self.assertIsNone(project.one('SELECT id FROM lessons WHERE id=1'))
        self.assertIsNone(project.one('SELECT id FROM lessons WHERE id=2'))
        self.assertEqual(project.one('SELECT hidden_from_planning FROM lessons WHERE id=3')['hidden_from_planning'],1)
        self.assertIsNotNone(project.one('SELECT id FROM lessons WHERE id=4'))

    def test_foreign_school_series_is_not_touched(self):
        self.actor(1)
        self.assertEqual(self.delete(1,'series').status_code,302)
        self.assertIsNotNone(project.one('SELECT id FROM lessons WHERE id=5'))

    def test_historical_lesson_is_hidden_not_deleted(self):
        self.actor(2)
        self.assertEqual(self.delete(3).status_code,302)
        self.assertEqual(project.one('SELECT hidden_from_planning FROM lessons WHERE id=3')['hidden_from_planning'],1)

    def test_attendance_keeps_the_lesson_record(self):
        with project.db() as c:
            c.execute("INSERT INTO attendance(lesson_id,student_id,status) VALUES (1,4,'present')")
        self.actor(1)
        self.assertEqual(self.delete(1).status_code,302)
        self.assertEqual(project.one('SELECT hidden_from_planning FROM lessons WHERE id=1')['hidden_from_planning'],1)
        self.assertIsNotNone(project.one('SELECT id FROM attendance WHERE lesson_id=1'))

    def test_single_lesson_cannot_request_series_deletion(self):
        self.actor(1)
        self.assertEqual(self.delete(4,'series').status_code,400)
        self.assertIsNotNone(project.one('SELECT id FROM lessons WHERE id=4'))

    def test_invalid_scope_is_rejected(self):
        self.actor(1)
        self.assertEqual(self.delete(1,'all_schools').status_code,400)
        self.assertIsNotNone(project.one('SELECT id FROM lessons WHERE id=1'))

    def test_archived_lesson_is_immutable(self):
        self.actor(1)
        self.assertEqual(self.delete(6).status_code,403)
        self.assertIsNotNone(project.one('SELECT id FROM lessons WHERE id=6'))

    def test_teacher_cannot_delete(self):
        self.actor(3)
        self.assertEqual(self.delete(1).status_code,403)
        self.assertIsNotNone(project.one('SELECT id FROM lessons WHERE id=1'))

    def test_student_cannot_delete(self):
        self.actor(4)
        self.assertEqual(self.delete(1).status_code,403)
        self.assertIsNotNone(project.one('SELECT id FROM lessons WHERE id=1'))

    def test_cross_school_lesson_cannot_delete(self):
        self.actor(1)
        self.assertEqual(self.delete(5).status_code,404)
        self.assertIsNotNone(project.one('SELECT id FROM lessons WHERE id=5'))

    def test_calendar_api_includes_series_identity(self):
        self.actor(1)
        response=self.client.get('/api/planning')
        self.assertEqual(response.status_code,200)
        events=response.get_json()
        self.assertEqual(next(e for e in events if e['id']==1)['extendedProps']['seriesId'],'seriesAAA')
        self.assertIsNone(next(e for e in events if e['id']==4)['extendedProps']['seriesId'])


if __name__=='__main__':
    unittest.main()

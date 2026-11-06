"""Superadministrateur: school-admin availability and cross-school authorisation.

Tests use disposable SQLite only. Never connect to the production database.
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
os.environ['SECRET_KEY']='school-admin-security-tests'
sys.path.insert(0,str(ROOT))
import app as project


class SuperadminSecurityTests(unittest.TestCase):
    def setUp(self):
        project.DB=str(Path(TEMP.name)/(self._testMethodName+'.db'))
        with project.db() as c:
            c.executescript(project.SCHEMA)
            c.execute("ALTER TABLE years ADD COLUMN status TEXT NOT NULL DEFAULT 'active'")
            c.execute("ALTER TABLE classes ADD COLUMN filiere_id INTEGER")
            c.execute("CREATE TABLE IF NOT EXISTS filieres(id INTEGER PRIMARY KEY,school_id INTEGER,name TEXT)")
            c.execute("INSERT INTO schools(id,name,slug) VALUES (1,'School A','school-a'),(2,'School B','school-b')")
            for uid,sid,role in [(1,None,'superadmin'),(2,1,'admin'),(3,1,'administratif'),
                                  (4,2,'admin'),(5,1,'admin')]:
                c.execute("""INSERT INTO users(id,school_id,name,first_name,last_name,phone,
                             email,password_hash,role,active) VALUES (?,?,?,?,?,?,?,?,?,?)""",
                    (uid,sid,f'Person {uid}','Person',str(uid),'0102030405',
                     f'user{uid}@test.invalid',generate_password_hash('PasswordTest123'),role,
                     0 if uid==5 else 1))
        self.client=project.app.test_client()

    def actor(self,uid):
        user=project.one('SELECT * FROM users WHERE id=?',(uid,))
        with self.client.session_transaction() as sess:
            sess.clear()
            sess['uid']=uid
            sess['auth_stamp']=project.session_auth_stamp(user)
            sess['csrf']='csrf'

    def action(self,sid,action,accounts):
        return self.client.post(f'/schools/{sid}/accounts/bulk',data={
            'csrf':'csrf','action':action,'account_ids':[str(x) for x in accounts]})

    def edit(self,sid,uid,role):
        return self.client.post(f'/schools/{sid}/accounts/{uid}/edit',data={
            'csrf':'csrf','first_name':'Person','last_name':str(uid),
            'email':f'user{uid}@test.invalid','phone':'0102030405','role':role})

    def test_superadmin_cannot_suspend_last_active_school_admin(self):
        self.actor(1)
        self.assertEqual(self.action(1,'suspend',[2]).status_code,400)
        self.assertEqual(project.one('SELECT active FROM users WHERE id=2')['active'],1)

    def test_superadmin_cannot_demote_last_active_school_admin(self):
        self.actor(1)
        self.assertEqual(self.action(1,'set_administratif',[2]).status_code,400)
        self.assertEqual(project.one('SELECT role FROM users WHERE id=2')['role'],'admin')

    def test_superadmin_cannot_delete_last_school_admin(self):
        self.actor(1)
        self.assertEqual(self.action(1,'delete',[2]).status_code,400)
        self.assertIsNotNone(project.one('SELECT id FROM users WHERE id=2'))

    def test_superadmin_cannot_demote_last_admin_via_edit(self):
        self.actor(1)
        self.assertEqual(self.edit(1,2,'administratif').status_code,400)
        self.assertEqual(project.one('SELECT role FROM users WHERE id=2')['role'],'admin')

    def test_superadmin_can_promote_administrative_account(self):
        self.actor(1)
        self.assertEqual(self.action(1,'set_admin',[3]).status_code,302)
        self.assertEqual(project.one('SELECT role FROM users WHERE id=3')['role'],'admin')

    def test_superadmin_can_suspend_admin_when_another_remains(self):
        self.actor(1)
        self.assertEqual(self.action(1,'set_admin',[3]).status_code,302)
        self.assertEqual(self.action(1,'suspend',[2]).status_code,302)
        self.assertEqual(project.one('SELECT active FROM users WHERE id=2')['active'],0)
        self.assertEqual(project.one('SELECT active FROM users WHERE id=3')['active'],1)

    def test_populated_school_cannot_be_deleted(self):
        self.actor(1)
        response=self.client.post('/schools/1/update',data={
            'csrf':'csrf','action':'delete','confirm_slug':'school-a'})
        self.assertEqual(response.status_code,403)
        self.assertIsNotNone(project.one('SELECT id FROM schools WHERE id=1'))
        self.assertIsNotNone(project.one('SELECT id FROM users WHERE id=2'))

    def test_school_can_be_deactivated_without_deleting_accounts(self):
        self.actor(1)
        response=self.client.post('/schools/1/update',data={
            'csrf':'csrf','action':'deactivate'})
        self.assertEqual(response.status_code,302)
        self.assertEqual(project.one('SELECT active FROM schools WHERE id=1')['active'],0)
        self.assertIsNotNone(project.one('SELECT id FROM users WHERE id=2'))

    def test_school_admin_cannot_access_superadmin_account_management(self):
        self.actor(2)
        self.assertEqual(self.action(1,'set_admin',[3]).status_code,403)
        self.assertEqual(project.one('SELECT role FROM users WHERE id=3')['role'],'administratif')

    def test_superadmin_cannot_bulk_change_account_in_another_school(self):
        self.actor(1)
        self.assertEqual(self.action(1,'suspend',[4]).status_code,403)
        self.assertEqual(project.one('SELECT active FROM users WHERE id=4')['active'],1)


if __name__=='__main__':
    unittest.main()

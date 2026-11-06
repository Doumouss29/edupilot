"""Regression tests: Web Push ownership and one-time MFA codes, SQLite only."""
import hashlib
import hmac
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from werkzeug.security import generate_password_hash

ROOT=Path(__file__).resolve().parents[1]
TEMP=tempfile.TemporaryDirectory()
os.environ['DB_ENGINE']='sqlite'
os.environ['DATABASE_PATH']=str(Path(TEMP.name)/'bootstrap.db')
os.environ['SECRET_KEY']='push-mfa-security-tests'
sys.path.insert(0,str(ROOT))
import app as project

ENDPOINT='https://fcm.googleapis.com/fcm/send/device-123'
SUB={'endpoint':ENDPOINT,'keys':{'p256dh':'a'*64,'auth':'b'*24}}


class PushAndMfaSecurityTests(unittest.TestCase):
    def setUp(self):
        project.DB=str(Path(TEMP.name)/(self._testMethodName+'.db'))
        with project.db() as c:
            c.executescript(project.SCHEMA)
            c.execute("ALTER TABLE years ADD COLUMN status TEXT NOT NULL DEFAULT 'active'")
            c.execute("ALTER TABLE classes ADD COLUMN filiere_id INTEGER")
            c.execute("CREATE TABLE IF NOT EXISTS filieres(id INTEGER PRIMARY KEY,school_id INTEGER,name TEXT)")
            c.execute("INSERT INTO schools(id,name,slug) VALUES (1,'A','a'),(2,'B','b')")
            for uid,sid,role in [(1,1,'admin'),(2,1,'etudiant'),(3,2,'admin')]:
                c.execute("INSERT INTO users(id,school_id,name,email,password_hash,role) VALUES (?,?,?,?,?,?)",
                    (uid,sid,role,'test'+str(uid)+'@example.invalid',generate_password_hash('PasswordTest123'),role))
        self.client=project.app.test_client()

    def login(self,uid,client=None):
        client=client or self.client
        user=project.one('SELECT * FROM users WHERE id=?',(uid,))
        with client.session_transaction() as sess:
            sess.clear()
            sess['uid']=uid
            sess['auth_stamp']=project.session_auth_stamp(user)
            sess['csrf']='csrf-for-test'
        return client

    def subscribe(self,client=None,sub=None):
        return (client or self.client).post('/api/push/subscribe',json=sub or SUB,
            headers={'X-CSRF-Token':'csrf-for-test'})

    def test_new_push_subscription_is_registered(self):
        self.login(1)
        self.assertEqual(self.subscribe().status_code,200)
        self.assertEqual(project.one('SELECT user_id FROM push_subscriptions WHERE endpoint=?',(ENDPOINT,))['user_id'],1)

    def test_same_user_can_refresh_push_subscription(self):
        self.login(1)
        self.assertEqual(self.subscribe().status_code,200)
        self.assertEqual(self.subscribe().status_code,200)

    def test_other_user_cannot_steal_push_subscription(self):
        self.login(1)
        self.assertEqual(self.subscribe().status_code,200)
        second=project.app.test_client()
        self.login(2,second)
        self.assertEqual(self.subscribe(second).status_code,403)
        self.assertEqual(project.one('SELECT user_id FROM push_subscriptions WHERE endpoint=?',(ENDPOINT,))['user_id'],1)

    def test_other_school_cannot_steal_push_subscription(self):
        self.login(1)
        self.assertEqual(self.subscribe().status_code,200)
        second=project.app.test_client()
        self.login(3,second)
        self.assertEqual(self.subscribe(second).status_code,403)
        self.assertEqual(project.one('SELECT user_id FROM push_subscriptions WHERE endpoint=?',(ENDPOINT,))['user_id'],1)

    def test_wrong_mfa_code_does_not_consume_valid_code(self):
        code='456789'
        digest=hmac.new(project.app.secret_key.encode(),f'1:{code}'.encode(),hashlib.sha256).hexdigest()
        with project.db() as c:
            c.execute("INSERT OR IGNORE INTO mfa_settings(user_id) VALUES (1)")
            c.execute("UPDATE mfa_settings SET email_code_hash=?,email_expires=?,email_attempts=0 WHERE user_id=1",
                (digest,int(time.time())+300))
        with self.client.session_transaction() as sess:
            sess['mfa_pending_uid']=1
            sess['mfa_pending_at']=int(time.time())
            sess['csrf']='csrf-for-test'
        result=self.client.post('/mfa',data={'csrf':'csrf-for-test','code':'000000'})
        self.assertEqual(result.status_code,200)
        self.assertEqual(project.one('SELECT email_attempts FROM mfa_settings WHERE user_id=1')['email_attempts'],1)
        self.assertIsNotNone(project.one('SELECT email_code_hash FROM mfa_settings WHERE user_id=1')['email_code_hash'])

    def test_mfa_code_cannot_be_used_twice(self):
        code='456789'
        digest=hmac.new(project.app.secret_key.encode(),f'1:{code}'.encode(),hashlib.sha256).hexdigest()
        with project.db() as c:
            c.execute("INSERT OR IGNORE INTO mfa_settings(user_id) VALUES (1)")
            c.execute("UPDATE mfa_settings SET email_code_hash=?,email_expires=?,email_attempts=0 WHERE user_id=1",
                (digest,int(time.time())+300))
        clients=[project.app.test_client(),project.app.test_client()]
        for client in clients:
            with client.session_transaction() as sess:
                sess['mfa_pending_uid']=1
                sess['mfa_pending_at']=int(time.time())
                sess['csrf']='csrf-for-test'
        first=clients[0].post('/mfa',data={'csrf':'csrf-for-test','code':code})
        self.assertIn(first.status_code,(302,303))
        second=clients[1].post('/mfa',data={'csrf':'csrf-for-test','code':code})
        self.assertEqual(second.status_code,200)
        with clients[1].session_transaction() as sess:
            self.assertNotIn('uid',sess)
        self.assertIsNone(project.one('SELECT email_code_hash FROM mfa_settings WHERE user_id=1')['email_code_hash'])


if __name__=='__main__':
    unittest.main()

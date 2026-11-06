"""Credential rotation, Flask session revocation, trusted MFA and invitation tests.

All records are isolated in disposable SQLite files. Production DB is never touched.
"""
import datetime
import hashlib
import os
import sys
import tempfile
import unittest
from pathlib import Path
from werkzeug.security import check_password_hash, generate_password_hash

ROOT=Path(__file__).resolve().parents[1]
TEMP=tempfile.TemporaryDirectory()
os.environ["DB_ENGINE"]="sqlite"
os.environ["DATABASE_PATH"]=str(Path(TEMP.name)/"startup.db")
os.environ["SECRET_KEY"]="test-password-session-revocation"
sys.path.insert(0,str(ROOT))
import app as project


class AccountSecurityTests(unittest.TestCase):
    def setUp(self):
        project.DB=str(Path(TEMP.name)/(self._testMethodName+".db"))
        with project.db() as conn:
            conn.executescript(project.SCHEMA)
            conn.execute("ALTER TABLE years ADD COLUMN status TEXT NOT NULL DEFAULT 'active'")
            conn.execute("INSERT INTO schools(id,name,slug) VALUES (1,'School','school')")
            conn.execute("""INSERT INTO users(id,school_id,name,email,password_hash,role)
                VALUES (1,1,'Admin','admin@test.invalid',?,'admin')""",
                (generate_password_hash('OldPassword123'),))
            conn.execute("INSERT INTO mfa_trusted_devices(user_id,token_hash,expires_at) VALUES (1,?,9999999999)",
                         (hashlib.sha256(b'trusted-token').hexdigest(),))
        self.client=project.app.test_client()
        self.client_b=project.app.test_client()

    def auth(self,client,legacy=False):
        with project.app.app_context():
            user=project.one('SELECT * FROM users WHERE id=1')
        with client.session_transaction() as sess:
            sess.clear()
            sess['uid']=1
            sess['csrf']='csrf-test'
            if not legacy:sess['auth_stamp']=project.session_auth_stamp(user)

    def test_valid_session_stays_authenticated(self):
        self.auth(self.client)
        self.assertEqual(self.client.get('/health').status_code,200)
        with self.client.session_transaction() as sess:
            self.assertEqual(sess.get('uid'),1)

    def test_unsigned_legacy_session_expires(self):
        self.auth(self.client,legacy=True)
        self.client.get('/health')
        with self.client.session_transaction() as sess:
            self.assertNotIn('uid',sess)

    def test_password_change_revokes_other_sessions_and_trust(self):
        self.auth(self.client)
        self.auth(self.client_b)
        response=self.client.post('/change-password',data={
            'csrf':'csrf-test','old_password':'OldPassword123',
            'new_password':'UpdatedPassword456','confirm_password':'UpdatedPassword456'})
        self.assertEqual(response.status_code,302)
        with project.db() as conn:
            record=conn.execute('SELECT password_hash FROM users WHERE id=1').fetchone()
            count=conn.execute('SELECT COUNT(*) FROM mfa_trusted_devices WHERE user_id=1').fetchone()[0]
        self.assertTrue(check_password_hash(record['password_hash'],'UpdatedPassword456'))
        self.assertEqual(count,0)
        self.client_b.get('/health')
        with self.client_b.session_transaction() as sess:
            self.assertNotIn('uid',sess)

    def test_activation_reset_revokes_other_sessions_and_trust(self):
        self.auth(self.client_b)
        token='randomized-link-for-test'
        deadline=(datetime.datetime.now(datetime.timezone.utc)+datetime.timedelta(minutes=15)).isoformat()
        with project.db() as conn:
            conn.execute("INSERT INTO invites(user_id,token_hash,expires_at) VALUES (1,?,?)",
                         (hashlib.sha256(token.encode()).hexdigest(),deadline))
        self.client.get('/activate/'+token)
        with self.client.session_transaction() as sess:
            csrf=sess['csrf']
        response=self.client.post('/activate/'+token,data={
            'csrf':csrf,'password':'ResetPassword789','confirm_password':'ResetPassword789'})
        self.assertEqual(response.status_code,302)
        self.client_b.get('/health')
        with self.client_b.session_transaction() as sess:
            self.assertNotIn('uid',sess)
        with project.db() as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM mfa_trusted_devices WHERE user_id=1').fetchone()[0],0)

    def test_used_invitation_cannot_be_replayed(self):
        token='single-use-link'
        deadline=(datetime.datetime.now(datetime.timezone.utc)+datetime.timedelta(minutes=15)).isoformat()
        with project.db() as conn:
            conn.execute("INSERT INTO invites(user_id,token_hash,expires_at) VALUES (1,?,?)",
                         (hashlib.sha256(token.encode()).hexdigest(),deadline))
        self.client.get('/activate/'+token)
        with self.client.session_transaction() as sess:csrf=sess['csrf']
        payload={'csrf':csrf,'password':'ResetPassword789','confirm_password':'ResetPassword789'}
        self.assertEqual(self.client.post('/activate/'+token,data=payload).status_code,302)
        self.assertEqual(self.client.post('/activate/'+token,data=payload).status_code,404)

    def test_invalidated_account_cannot_use_invitation(self):
        token='disabled-user-invite'
        deadline=(datetime.datetime.now(datetime.timezone.utc)+datetime.timedelta(minutes=15)).isoformat()
        with project.db() as conn:
            conn.execute("INSERT INTO invites(user_id,token_hash,expires_at) VALUES (1,?,?)",
                         (hashlib.sha256(token.encode()).hexdigest(),deadline))
            conn.execute("UPDATE users SET active=0 WHERE id=1")
        self.assertEqual(self.client.get('/activate/'+token).status_code,404)

    def test_password_length_limit(self):
        self.assertFalse(project.valid_password('A'*1100+'1'))
        self.assertTrue(project.valid_password('LongPassword123'))


if __name__=='__main__':
    unittest.main()

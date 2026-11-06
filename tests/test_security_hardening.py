"""Security regression tests: login throttling, browser headers and school isolation."""
import os
import sys
import tempfile
import unittest
from pathlib import Path

from werkzeug.security import generate_password_hash

ROOT=Path(__file__).resolve().parents[1]
TEMP=tempfile.TemporaryDirectory()
os.environ.setdefault('DB_ENGINE','sqlite')
os.environ['DATABASE_PATH']=str(Path(TEMP.name)/'initial.db')
os.environ['SECRET_KEY']='test-security-hardening-secret'
sys.path.insert(0,str(ROOT))
import app as project


class SecurityHardeningTests(unittest.TestCase):
    def setUp(self):
        self.database=Path(TEMP.name)/(self._testMethodName+'.db')
        project.DB=str(self.database)
        with project.db() as conn:
            conn.executescript(project.SCHEMA)
            conn.execute("INSERT INTO schools(id,name,slug) VALUES (1,'A','a'),(2,'B','b')")
            conn.execute("INSERT INTO users(school_id,name,email,password_hash,role) VALUES (?,?,?,?,?)",
                         (1,'Étudiant A','student@example.test',
                          generate_password_hash('ValidPassword123'),'etudiant'))
        self.client=project.app.test_client()
        self.client.get('/login')
        with self.client.session_transaction() as sess:
            self.csrf=sess['csrf']

    def login(self,password,email='student@example.test',path='/a/login'):
        return self.client.post(path,data={'csrf':self.csrf,'email':email,'password':password},
                                environ_overrides={'REMOTE_ADDR':'198.51.100.4'})

    def test_failed_login_is_throttled(self):
        for _ in range(project.LOGIN_LIMIT_ACCOUNT):
            self.assertEqual(self.login('wrong-password').status_code,302)
        blocked=self.login('ValidPassword123')
        self.assertEqual(blocked.status_code,429)
        self.assertEqual(blocked.headers['Retry-After'],str(project.LOGIN_LIMIT_WINDOW))

    def test_other_school_not_authorized(self):
        response=self.login('ValidPassword123',path='/b/login')
        self.assertEqual(response.status_code,302)
        with self.client.session_transaction() as sess:
            self.assertNotIn('uid',sess)

    def test_throttle_does_not_store_plain_email_or_ip(self):
        self.login('wrong-password')
        with project.db() as conn:
            keys=[r['key_hash'] for r in conn.execute('SELECT key_hash FROM login_rate_limits')]
        self.assertEqual(len(keys),2)
        self.assertTrue(all(len(key)==64 and 'student@' not in key and '198.51.100' not in key
                            for key in keys))

    def test_security_headers(self):
        response=self.client.get('/login')
        self.assertEqual(response.headers['X-Content-Type-Options'],'nosniff')
        self.assertEqual(response.headers['X-Frame-Options'],'SAMEORIGIN')
        self.assertIn("frame-ancestors 'self'",response.headers['Content-Security-Policy'])
        self.assertEqual(response.headers['Cache-Control'],'private, no-store')


if __name__=='__main__':
    unittest.main()

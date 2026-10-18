"""MFA security regression tests on temporary isolated SQLite databases."""
import os,sys,tempfile,unittest,uuid,time
from pathlib import Path
from werkzeug.security import generate_password_hash

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
TEMP=tempfile.TemporaryDirectory()
os.environ["DATABASE_PATH"]=str(Path(TEMP.name)/"initial.db")
os.environ["SECRET_KEY"]="unit-test-mfa-secret"
import app as project


class MfaTests(unittest.TestCase):
    def setUp(self):
        project.DB=str(Path(TEMP.name)/(uuid.uuid4().hex+".db"))
        with project.db() as c:
            c.executescript(project.SCHEMA)
            c.execute("INSERT INTO schools(id,name,slug) VALUES (1,'School A','school-a')")
            c.execute("INSERT INTO users(id,school_id,name,email,password_hash,role) VALUES (1,1,'Admin A','admin@test.invalid',?,'admin')",(generate_password_hash("PassA1234567"),))
            c.execute("INSERT INTO users(id,school_id,name,email,password_hash,role) VALUES (2,NULL,'Super','super@test.invalid',?,'superadmin')",(generate_password_hash("PassA1234567"),))
        self.client=project.app.test_client()

    def login(self,email):
        self.client.get("/login")
        with self.client.session_transaction() as sess:token=sess["csrf"]
        return self.client.post("/login",data={"csrf":token,"email":email,"password":"PassA1234567"})

    def test_admin_cannot_access_dashboard_without_email_factor(self):
        project.send_mfa_email=lambda u:True
        response=self.login("admin@test.invalid")
        self.assertEqual(response.status_code,302)
        self.assertIn("/mfa",response.headers.get("Location",""))
        with self.client.session_transaction() as sess:
            self.assertNotIn("uid",sess)
            self.assertEqual(sess["mfa_pending_uid"],1)

    def test_superadmin_requires_totp_and_recovery_codes_are_single_use(self):
        self.login("super@test.invalid")
        with self.client.session_transaction() as sess:
            self.assertNotIn("uid",sess)
            self.assertEqual(sess["mfa_pending_uid"],2)
        page=self.client.get("/mfa")
        self.assertEqual(page.status_code,200)
        self.assertIn(b"Authenticator",page.data)
        codes=project.generate_recovery_codes(2)
        self.assertEqual(len(codes),8)
        self.assertTrue(project.use_recovery_code(2,codes[0]))
        self.assertFalse(project.use_recovery_code(2,codes[0]))

    def test_trusted_device_is_bound_to_user_and_expiry(self):
        from hashlib import sha256
        token="sample-test-token"
        with project.db() as c:
            c.execute("INSERT INTO mfa_trusted_devices(user_id,token_hash,expires_at) VALUES (?,?,?)",(1,sha256(token.encode()).hexdigest(),int(time.time())+3600))
        with project.app.test_request_context("/login",headers={"Cookie":"edupilot_trusted="+token}):
            user=project.one("SELECT * FROM users WHERE id=1")
            self.assertTrue(project.mfa_trusted_user(user))
            other=project.one("SELECT * FROM users WHERE id=2")
            self.assertFalse(project.mfa_trusted_user(other))


if __name__=="__main__":unittest.main()

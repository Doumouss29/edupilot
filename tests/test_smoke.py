"""Basic deployment smoke tests; intentionally uses a fresh temporary database."""
import os
import tempfile
import unittest

class EduPilotSmoke(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        os.environ["DATABASE_PATH"] = os.path.join(cls.tmp.name, "edupilot-test.db")
        os.environ["SECRET_KEY"] = "ci-only-test-secret-not-for-production"
        import app
        cls.app = app.app.test_client()

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_health(self):
        response = self.app.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["status"], "ok")

    def test_login_required(self):
        response = self.app.get("/")
        self.assertIn(response.status_code, (301, 302))

    def test_demo_login(self):
        login = self.app.get("/login")
        with self.app.session_transaction() as sess:
            csrf = sess["csrf"]
        response = self.app.post("/login", data={"csrf": csrf, "email": "admin1@demo.edupilot.test", "password": "Demo2026!"}, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Tableau de bord", response.data)

if __name__ == "__main__":
    unittest.main()

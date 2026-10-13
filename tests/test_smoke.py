"""Smoke tests for EduPilot demo; all state is fictitious and isolated."""
import io
import os
import tempfile
import unittest

TEMP = tempfile.TemporaryDirectory()
os.environ["DATABASE_PATH"] = os.path.join(TEMP.name, "edupilot-test.db")
os.environ["SECRET_KEY"] = "ci-only-unique-secret"
import app as project

class EduPilotSmoke(unittest.TestCase):
    def setUp(self):
        self.client = project.app.test_client()

    def csrf(self):
        self.client.get("/login")
        with self.client.session_transaction() as sess:
            return sess["csrf"]

    def login(self, email):
        token = self.csrf()
        return self.client.post("/login", data={"csrf": token, "email": email, "password": "Demo2026!"}, follow_redirects=True)

    def token(self):
        with self.client.session_transaction() as sess:
            return sess["csrf"]

    def test_health(self):
        self.assertEqual(self.client.get("/health").json["status"], "ok")

    def test_login_required(self):
        self.assertEqual(self.client.get("/").status_code, 302)

    def test_admin_login(self):
        result = self.login("admin1@demo.edupilot.test")
        self.assertEqual(result.status_code, 200)
        self.assertIn(b"Tableau de bord", result.data)

    def test_superadmin_settings(self):
        self.login("superadmin@demo.edupilot.test")
        r = self.client.post("/settings", data={
            "csrf": self.token(), "support_name": "LMurbs",
            "support_phone": "+2250711124359",
            "powered_by": "Propulsé par LMurbs",
        }, follow_redirects=True)
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"LMurbs", r.data)

    def test_subscription_blocks_all_protected_pages(self):
        school = project.one("SELECT school_id FROM users WHERE email=?", ("admin1@demo.edupilot.test",))["school_id"]
        project.execute("UPDATE schools SET active=0 WHERE id=?", (school,))
        try:
            response = self.login("admin1@demo.edupilot.test")
            self.assertIn("restreint".encode(), response.data)
            for path in ("/", "/planning", "/grades", "/reports", "/api/planning"):
                self.assertEqual(self.client.get(path).status_code, 302)
        finally:
            project.execute("UPDATE schools SET active=1 WHERE id=?", (school,))

    def test_expiration_date_blocks_access(self):
        school=project.one("SELECT school_id FROM users WHERE email=?",("admin1@demo.edupilot.test",))["school_id"]
        project.execute("UPDATE schools SET subscription_end='2020-01-01' WHERE id=?", (school,))
        try:
            response=self.login("admin1@demo.edupilot.test")
            self.assertIn("restreint".encode(),response.data)
        finally:
            project.execute("UPDATE schools SET subscription_end=NULL WHERE id=?", (school,))

    def test_school_lifecycle_logo_and_deletion(self):
        self.login("superadmin@demo.edupilot.test")
        token = self.token()
        slug = "demo_lifecycle_tests"
        img = b"\\x89PNG\\r\\n\\x1a\\n" + b"fictitiousimage"
        r=self.client.post("/schools",data={
            "csrf":token,"name":"Demo Lifecycle Tests","plan":"premium",
            "subscription_end":"2027-12-31",
            "logo":(io.BytesIO(img),"test.png"),
        },content_type="multipart/form-data")
        self.assertEqual(r.status_code,302)
        school=project.one("SELECT * FROM schools WHERE slug=?",(slug,))
        self.assertIsNotNone(school)
        self.assertEqual(school["subscription_end"],"2027-12-31")
        self.assertEqual(self.client.get("/school-logo/"+str(school["id"])).status_code,200)
        r=self.client.post("/schools/"+str(school["id"])+"/update",data={"csrf":token,"action":"deactivate"})
        self.assertEqual(r.status_code,302)
        self.assertEqual(project.one("SELECT active FROM schools WHERE id=?",(school["id"],))["active"],0)
        r=self.client.post("/schools/"+str(school["id"])+"/update",data={"csrf":token,"action":"delete","confirm_slug":slug})
        self.assertEqual(r.status_code,302)
        self.assertIsNone(project.one("SELECT id FROM schools WHERE id=?",(school["id"],)))

if __name__=="__main__":
    unittest.main()

"""Matricules: isolation par établissement et génération par profil."""
import os
import tempfile
import unittest
import uuid

os.environ.setdefault("SECRET_KEY", "tests-only-secret-value")
os.environ.setdefault("DATABASE_PATH", os.path.join(tempfile.gettempdir(), "edupilot-matricules-init-" + uuid.uuid4().hex + ".db"))
import app as project
from werkzeug.security import generate_password_hash

class MatriculeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        project.DB = os.path.join(self.temp.name, "matricules.db")
        with project.db() as c:
            c.executescript(project.SCHEMA)
            c.execute("INSERT INTO schools(name,slug) VALUES ('École Alpha','alpha')")
            c.execute("INSERT INTO schools(name,slug) VALUES ('École Bêta','beta')")
            c.execute("INSERT INTO users(school_id,name,email,password_hash,role) VALUES (1,'Admin Alpha','admin-alpha@tests.invalid',?,'admin')",(generate_password_hash('Password123456!'),))
            c.execute("INSERT INTO users(school_id,name,email,password_hash,role) VALUES (NULL,'Super Admin','super@tests.invalid',?,'superadmin')",(generate_password_hash('Password123456!'),))
        self.client=project.app.test_client()

    def tearDown(self):
        self.temp.cleanup()

    def login(self,email):
        self.client.get("/login")
        with self.client.session_transaction() as sess:
            token=sess["csrf"]
        result=self.client.post("/login",data={"email":email,"password":"Password123456!","csrf":token})
        self.assertIn(result.status_code,(302,303))
        with self.client.session_transaction() as sess:
            return sess["csrf"]

    def test_rules_independent_and_duplicate_rejected(self):
        with project.db() as c:
            c.execute("BEGIN IMMEDIATE")
            alpha1=project.next_matricule(c,1,"etudiant")
            alpha2=project.next_matricule(c,1,"etudiant")
            beta1=project.next_matricule(c,2,"etudiant")
            teacher=project.next_matricule(c,1,"enseignant")
        self.assertEqual((alpha1,alpha2,beta1,teacher),("ETU0001","ETU0002","ETU0001","ENS0001"))
        with project.db() as c:
            c.execute("INSERT INTO users(school_id,name,email,password_hash,role,matricule) VALUES (1,'Un','one@tests.invalid','test','etudiant',?)",(alpha1,))
            with self.assertRaises(ValueError):
                project.requested_matricule(c,1,"enseignant",alpha1)
        self.assertEqual(project.validate_matricule(" etu-001 "), "ETU-001")

    def test_superadmin_config_and_school_admin_preview(self):
        token=self.login("super@tests.invalid")
        data={"csrf":token}
        for role in project.MATRICULE_PROFILES:
            data["prefix_"+role]="ELV-" if role=="etudiant" else project.MATRICULE_PROFILES[role]
            data["padding_"+role]="5"
            data["next_"+role]="12"
        response=self.client.post("/schools/1/matricules",data=data)
        self.assertEqual(response.status_code,302)
        self.assertEqual(self.client.get("/schools/1/matricules").status_code,200)
        self.assertEqual(self.client.get("/api/schools/1/matricule/next?role=etudiant").json["matricule"],"ELV-00012")
        self.client.get("/logout")
        # CSRF protected logout is POST.
        token=self.login("admin-alpha@tests.invalid")
        self.assertEqual(self.client.get("/api/matricule/next?role=etudiant").json["matricule"],"ELV-00012")
        self.assertEqual(self.client.get("/api/schools/2/matricule/next?role=etudiant").status_code,403)
        self.assertEqual(self.client.get("/people").status_code,200)

if __name__=="__main__":
    unittest.main()

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

    def test_all_templates_compile(self):
        for template in ("base.html","dashboard.html","schools.html","settings.html","restricted.html","login.html","list.html","planning.html","school_new.html","school_accounts.html","change_password.html"):
            project.app.jinja_env.get_template(template)

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


    def test_create_tenant_admin_force_password_change(self):
        self.login("superadmin@demo.edupilot.test")
        token=self.token()
        resp=self.client.post("/schools/new",data={"csrf":token,"name":"Ecole des Tests","plan":"standard","subscription_end":"2027-12-31"})
        self.assertEqual(resp.status_code,302)
        school=project.one("SELECT id,slug FROM schools WHERE slug='ecole_des_tests'")
        self.assertIsNotNone(school)
        password="TemporaryTeacher2026!"
        response=self.client.post(f"/schools/{school['id']}/accounts",data={"csrf":token,"first_name":"Alice","last_name":"Test","email":"alice.edupilot@example.test","phone":"+2250102030405","role":"admin","password":password})
        self.assertEqual(response.status_code,302)
        created=project.one("SELECT * FROM users WHERE email=?",("alice.edupilot@example.test",))
        self.assertEqual(created['school_id'],school['id'])
        self.assertEqual(created['must_change_password'],1)
        self.client.post("/logout",data={"csrf":token})
        # Ensure the scoped login does not accept another institution's admin.
        csrf=self.csrf()
        wrong=self.client.post(f"/{school['slug']}/login",data={"csrf":csrf,"email":"admin1@demo.edupilot.test","password":"Demo2026!"})
        self.assertEqual(wrong.status_code,302)
        with self.client.session_transaction() as sess:self.assertNotIn("uid",sess)
        csrf=self.csrf()
        login=self.client.post(f"/{school['slug']}/login",data={"csrf":csrf,"email":"alice.edupilot@example.test","password":password})
        self.assertIn("/change-password",login.headers["Location"])
        self.assertIn("/change-password",self.client.get("/classes").headers["Location"])
        csrf=self.token()
        result=self.client.post("/change-password",data={"csrf":csrf,"old_password":password,"new_password":"MyNewPass2026Safe!","confirm_password":"MyNewPass2026Safe!"})
        self.assertEqual(result.status_code,302)
        changed=project.one("SELECT must_change_password FROM users WHERE id=?",(created["id"],))
        self.assertEqual(changed["must_change_password"],0)
        self.assertTrue(project.check_password_hash(project.one("SELECT password_hash FROM users WHERE id=?",(created["id"],))["password_hash"],"MyNewPass2026Safe!"))


    def test_student_creation_assigns_class(self):
        self.login("admin1@demo.edupilot.test")
        cl=project.one("SELECT id,year_id FROM classes WHERE school_id=1 ORDER BY id LIMIT 1")
        email="manual.student.demo@example.test"
        response=self.client.post("/people",data={"csrf":self.token(),"role":"etudiant","name":"Etudiant Manuel","email":email,"class_id":cl["id"]})
        self.assertEqual(response.status_code,302)
        student=project.one("SELECT id FROM users WHERE email=?",(email,))
        self.assertIsNotNone(student)
        self.assertIsNotNone(project.one("SELECT id FROM enrollments WHERE school_id=1 AND student_id=? AND class_id=? AND year_id=?",(student["id"],cl["id"],cl["year_id"])))

    def test_bulk_csv_students_enrolled(self):
        self.login("admin1@demo.edupilot.test")
        cl=project.one("SELECT id FROM classes WHERE school_id=1 ORDER BY id LIMIT 1")
        content=("prenom;nom;email;classe\nAicha;Demo;aicha.bulk@example.test;"+str(cl["id"])+"\nBakary;Demo;bakary.bulk@example.test;"+str(cl["id"])+"\n").encode("utf-8")
        response=self.client.post("/people/import",data={"csrf":self.token(),"file":(io.BytesIO(content),"students.csv")},content_type="multipart/form-data")
        self.assertEqual(response.status_code,302)
        for email in ("aicha.bulk@example.test","bakary.bulk@example.test"):
            student=project.one("SELECT id FROM users WHERE email=?",(email,))
            self.assertIsNotNone(student)
            self.assertIsNotNone(project.one("SELECT id FROM enrollments WHERE student_id=? AND class_id=?",(student["id"],cl["id"])))

    def test_bulk_xlsx_students_enrolled(self):
        from openpyxl import Workbook
        self.login("admin1@demo.edupilot.test")
        cl=project.one("SELECT id FROM classes WHERE school_id=1 ORDER BY id LIMIT 1")
        wb=Workbook();ws=wb.active;ws.append(["prenom","nom","email","classe"]);ws.append(["Fatou","Demo","fatou.bulk@example.test",str(cl["id"])])
        bio=io.BytesIO();wb.save(bio);bio.seek(0)
        response=self.client.post("/people/import",data={"csrf":self.token(),"file":(bio,"students.xlsx")},content_type="multipart/form-data")
        self.assertEqual(response.status_code,302)
        self.assertIsNotNone(project.one("SELECT id FROM users WHERE email='fatou.bulk@example.test'"))

    def test_teacher_can_receive_several_courses(self):
        self.login("admin1@demo.edupilot.test")
        cl=project.one("SELECT id FROM classes WHERE school_id=1 ORDER BY id LIMIT 1")
        ids=[]
        for name in ("SVT test","Physique test"):
            ids.append(project.execute("INSERT INTO courses(school_id,class_id,name,code,planned_minutes) VALUES (?,?,?,?,?)",(1,cl["id"],name,"TST",600)))
        response=self.client.post("/people",data={"csrf":self.token(),"role":"enseignant","name":"Enseignant Multi","email":"multi.teacher@example.test","course_ids":[str(x) for x in ids]})
        self.assertEqual(response.status_code,302)
        teacher=project.one("SELECT id FROM users WHERE email='multi.teacher@example.test'")
        self.assertIsNotNone(teacher)
        for cid in ids:
            self.assertEqual(project.one("SELECT teacher_id FROM courses WHERE id=?",(cid,))["teacher_id"],teacher["id"])

    def test_planning_requires_matching_class(self):
        self.login("admin1@demo.edupilot.test")
        own=project.one("SELECT c.id,c.class_id FROM courses c WHERE c.school_id=1 ORDER BY id LIMIT 1")
        other=project.one("SELECT id FROM classes WHERE school_id=2 ORDER BY id LIMIT 1")
        response=self.client.post("/planning",data={"csrf":self.token(),"course_id":own["id"],"class_id":other["id"],"starts_at":"2026-11-02T08:00","ends_at":"2026-11-02T10:00","room":"A101"})
        self.assertEqual(response.status_code,403)
        result=self.client.post("/planning",data={"csrf":self.token(),"course_id":own["id"],"class_id":own["class_id"],"starts_at":"2026-11-02T08:00","ends_at":"2026-11-02T10:00","room":"A101"})
        self.assertEqual(result.status_code,302)
        self.assertIsNotNone(project.one("SELECT id FROM lessons WHERE course_id=? AND starts_at='2026-11-02T08:00'",(own["id"],)))

    def test_school_lifecycle_logo_and_deletion(self):
        self.login("superadmin@demo.edupilot.test")
        token = self.token()
        slug = "demo_lifecycle_tests"
        img = b"\\x89PNG\\r\\n\\x1a\\n" + b"fictitiousimage"
        r=self.client.post("/schools/new",data={
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

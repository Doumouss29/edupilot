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
        for template in ("base.html","dashboard.html","schools.html","settings.html","restricted.html","login.html","list.html","planning.html","edit_academic.html","class_details.html","dashboard_student.html","school_new.html","school_accounts.html","school_account_edit.html","change_password.html","students.html","grade_entry.html","grade_global.html","class_grade_summary.html"):
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
        response=self.client.post("/people",data={"csrf":self.token(),"role":"etudiant","name":"Etudiant Manuel","email":email,"class_id":cl["id"],"password":"Temporary2026Secret!"})
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
        response=self.client.post("/people",data={"csrf":self.token(),"role":"enseignant","name":"Enseignant Multi","email":"multi.teacher@example.test","course_ids":[str(x) for x in ids],"password":"Temporary2026Secret!"})
        self.assertEqual(response.status_code,302)
        teacher=project.one("SELECT id FROM users WHERE email='multi.teacher@example.test'")
        self.assertIsNotNone(teacher)
        for cid in ids:
            self.assertEqual(project.one("SELECT teacher_id FROM courses WHERE id=?",(cid,))["teacher_id"],teacher["id"])


    def test_planning_single_30_minutes_and_recurrence(self):
        self.login("admin1@demo.edupilot.test")
        own=project.one("SELECT id,class_id FROM courses WHERE school_id=1 ORDER BY id LIMIT 1")
        other=project.one("SELECT id FROM classes WHERE school_id=2 ORDER BY id LIMIT 1")
        bad=self.client.post("/planning",data={"csrf":self.token(),"course_id":own["id"],"class_id":other["id"],"lesson_date":"2026-11-02","start_time":"08:00","duration_hours":"0.5","mode":"unique"})
        self.assertEqual(bad.status_code,302)
        self.assertIsNone(project.one("SELECT id FROM lessons WHERE starts_at='2026-11-02T08:00' AND school_id=1"))
        result=self.client.post("/planning",data={"csrf":self.token(),"course_id":own["id"],"class_id":own["class_id"],"lesson_date":"2026-11-02","start_time":"08:00","duration_hours":"0.5","mode":"unique"})
        self.assertEqual(result.status_code,302)
        lesson=project.one("SELECT starts_at,ends_at FROM lessons WHERE course_id=? AND starts_at='2026-11-02T08:00'",(own["id"],))
        self.assertIsNotNone(lesson)
        self.assertEqual(lesson["ends_at"],"2026-11-02T08:30")
        recurring=self.client.post("/planning",data={"csrf":self.token(),"course_id":own["id"],"class_id":own["class_id"],"lesson_date":"2026-11-09","start_time":"10:00","duration_hours":"1.5","mode":"hebdomadaire","repeat_until":"2026-11-23"})
        self.assertEqual(recurring.status_code,302)
        self.assertEqual(project.one("SELECT COUNT(*) n FROM lessons WHERE course_id=? AND starts_at LIKE '2026-11-%T10:00'",(own["id"],))["n"],3)
        clash=self.client.post("/planning",data={"csrf":self.token(),"course_id":own["id"],"class_id":own["class_id"],"lesson_date":"2026-11-09","start_time":"10:00","duration_hours":"1.5","mode":"hebdomadaire","repeat_until":"2026-11-23"},follow_redirects=True)
        self.assertEqual(clash.status_code,200)
        self.assertIn("Conflit".encode(),clash.data)

    def test_class_course_edits_and_user_suspension(self):
        self.login("admin1@demo.edupilot.test")
        cl=project.one("SELECT id FROM classes WHERE school_id=1 ORDER BY id LIMIT 1")
        response=self.client.post(f"/classes/{cl['id']}/edit",data={"csrf":self.token(),"name":"Classe rénovée","cycle":"semestre"})
        self.assertEqual(response.status_code,302)
        self.assertEqual(project.one("SELECT name FROM classes WHERE id=?",(cl["id"],))["name"],"Classe rénovée")
        course=project.one("SELECT id,class_id,code,teacher_id FROM courses WHERE school_id=1 ORDER BY id LIMIT 1")
        r=self.client.post(f"/courses/{course['id']}/edit",data={"csrf":self.token(),"name":"SIG renouvelé","code":"SIG202","class_id":course["class_id"],"hours":"24","teacher_id":str(course["teacher_id"] or "")})
        self.assertEqual(r.status_code,302)
        self.assertEqual(project.one("SELECT name FROM courses WHERE id=?",(course["id"],))["name"],"SIG renouvelé")
        target=project.one("SELECT id FROM users WHERE school_id=1 AND email='parent1@demo.edupilot.test'")
        r=self.client.post("/people/bulk",data={"csrf":self.token(),"action":"suspend","user_ids":[str(target["id"])]})
        self.assertEqual(r.status_code,302)
        self.assertEqual(project.one("SELECT active FROM users WHERE id=?",(target["id"],))["active"],0)
        r=self.client.post("/people/bulk",data={"csrf":self.token(),"action":"activate","user_ids":[str(target["id"])]})
        self.assertEqual(r.status_code,302)
        self.assertEqual(project.one("SELECT active FROM users WHERE id=?",(target["id"],))["active"],1)


    def test_class_details_scoped_and_lists(self):
        self.login("admin1@demo.edupilot.test")
        own=project.one("SELECT id FROM classes WHERE school_id=1 ORDER BY id LIMIT 1")
        foreign=project.one("SELECT id FROM classes WHERE school_id=2 ORDER BY id LIMIT 1")
        r=self.client.get(f"/classes/{own['id']}/details")
        self.assertEqual(r.status_code,200)
        self.assertIn("Étudiants de la classe".encode(),r.data)
        self.assertIn("Enseignants affectés".encode(),r.data)
        self.assertIn("Cours de la classe".encode(),r.data)
        self.assertEqual(self.client.get(f"/classes/{foreign['id']}/details").status_code,404)

    def test_student_dashboard_week_and_privacy(self):
        self.login("eleve1_1@demo.edupilot.test")
        week=self.client.get("/?week=2026-10-12")
        self.assertEqual(week.status_code,200)
        self.assertIn("Mes prochaines séances".encode(),week.data)
        self.assertNotIn(b"Avancement pedagogique",week.data)
        self.assertIn(b"/planning",week.data)
        # No administrative metrics or class management links on the student dashboard.
        self.assertNotIn(b"Sur 0 heures",week.data)
        far=self.client.get("/?week=2028-02-07")
        self.assertEqual(far.status_code,200)
        self.assertIn("Aucune séance programmée".encode(),far.data)
        self.assertEqual(self.client.get("/classes/1/details").status_code,403)


    def test_superadmin_edit_and_bulk_school_accounts(self):
        self.login("superadmin@demo.edupilot.test")
        school=project.one("SELECT id FROM schools WHERE slug='groupe_scolaire_excellence'")
        admin=project.one("SELECT id FROM users WHERE email='admin1@demo.edupilot.test'")
        staff=project.one("SELECT id FROM users WHERE email='scolarite1@demo.edupilot.test'")
        sid=school["id"]
        self.assertEqual(self.client.get(f"/schools/{sid}/accounts/{admin['id']}/edit").status_code,200)
        edit=self.client.post(f"/schools/{sid}/accounts/{admin['id']}/edit",data={
            "csrf":self.token(),"first_name":"Adèle","last_name":"Direction",
            "email":"admin1@demo.edupilot.test","phone":"+2250700001111",
            "role":"administratif","temporary_password":"SafeTemporary2026!"
        })
        self.assertEqual(edit.status_code,302)
        updated=project.one("SELECT name,phone,role,must_change_password,password_hash FROM users WHERE id=?",(admin["id"],))
        self.assertEqual(updated["name"],"Adèle Direction")
        self.assertEqual(updated["role"],"administratif")
        self.assertEqual(updated["must_change_password"],1)
        self.assertTrue(project.check_password_hash(updated["password_hash"],"SafeTemporary2026!"))
        changed=self.client.post(f"/schools/{sid}/accounts/bulk",data={
            "csrf":self.token(),"account_ids":[str(admin["id"]),str(staff["id"])],"action":"set_admin"
        })
        self.assertEqual(changed.status_code,302)
        self.assertEqual(project.one("SELECT role FROM users WHERE id=?",(staff["id"],))["role"],"admin")
        suspended=self.client.post(f"/schools/{sid}/accounts/bulk",data={
            "csrf":self.token(),"account_ids":[str(admin["id"]),str(staff["id"])],"action":"suspend"
        })
        self.assertEqual(suspended.status_code,302)
        self.assertEqual(project.one("SELECT active FROM users WHERE id=?",(admin["id"],))["active"],0)
        restored=self.client.post(f"/schools/{sid}/accounts/bulk",data={
            "csrf":self.token(),"account_ids":[str(admin["id"]),str(staff["id"])],"action":"activate"
        })
        self.assertEqual(restored.status_code,302)
        self.assertEqual(project.one("SELECT active FROM users WHERE id=?",(admin["id"],))["active"],1)

    def test_superadmin_bulk_delete_and_cross_tenant_guard(self):
        self.login("superadmin@demo.edupilot.test")
        school=project.one("SELECT id FROM schools WHERE slug='groupe_scolaire_excellence'")
        other=project.one("SELECT id FROM users WHERE email='admin2@demo.edupilot.test'")
        self.assertEqual(self.client.get(f"/schools/{school['id']}/accounts/{other['id']}/edit").status_code,404)
        bad=self.client.post(f"/schools/{school['id']}/accounts/bulk",data={"csrf":self.token(),"action":"suspend","account_ids":[str(other["id"])]})
        self.assertEqual(bad.status_code,403)
        uid=project.execute("INSERT INTO users(school_id,name,email,phone,role,password_hash) VALUES (?,?,?,?,?,?)",
            (school["id"],"Compte provisoire","deletion.account@example.test","+2250700000000","administratif",project.generate_password_hash("SomeLongPassword2026!")))
        res=self.client.post(f"/schools/{school['id']}/accounts/bulk",data={"csrf":self.token(),"action":"delete","account_ids":[str(uid)]})
        self.assertEqual(res.status_code,302)
        self.assertIsNone(project.one("SELECT id FROM users WHERE id=?",(uid,)))


    def test_transfer_and_grading_workflows(self):
        self.login("admin1@demo.edupilot.test")
        school=project.one("SELECT id FROM schools WHERE slug='groupe_scolaire_excellence'")
        cl=project.one("SELECT id,year_id FROM classes WHERE school_id=? ORDER BY id LIMIT 1",(school["id"],))
        destination=project.execute("INSERT INTO classes(school_id,year_id,name,cycle) VALUES (?,?,?,?)",(school["id"],cl["year_id"],"Destination V08","semestre"))
        student=project.execute("INSERT INTO users(school_id,name,email,password_hash,role) VALUES (?,?,?,?,?)",(school["id"],"Transfert V08","transfer.v08@example.test",project.generate_password_hash("SafePassword2026!"),"etudiant"))
        eid=project.execute("INSERT INTO enrollments(school_id,student_id,class_id,year_id) VALUES (?,?,?,?)",(school["id"],student,cl["id"],cl["year_id"]))
        move=self.client.post("/students/transfer",data={"csrf":self.token(),"class_id":destination,"enrollment_ids":[eid]})
        self.assertEqual(move.status_code,302)
        self.assertIsNotNone(project.one("SELECT id FROM enrollments WHERE student_id=? AND class_id=?",(student,destination)))
        teacher=project.one("SELECT id FROM users WHERE school_id=? AND role='enseignant' LIMIT 1",(school["id"],))
        course=project.execute("INSERT INTO courses(school_id,class_id,name,code,planned_minutes,teacher_id,coefficient) VALUES (?,?,?,?,?,?,?)",(school["id"],destination,"Cours pondéré","COV08",600,teacher["id"],3))
        pdf=io.BytesIO(b"%PDF-1.4\\n%%EOF\\n")
        result=self.client.post("/assessments",data={"csrf":self.token(),"course_id":course,"title":"Évaluation V08","coefficient":"2","description":"Consignes détaillées","documents":(pdf,"sujet.pdf")},content_type="multipart/form-data")
        self.assertEqual(result.status_code,302)
        a=project.one("SELECT id,coefficient FROM assessments WHERE course_id=?",(course,))
        self.assertIsNotNone(a)
        self.assertEqual(a["coefficient"],2)
        file=project.one("SELECT id,filename FROM assessment_files WHERE assessment_id=?",(a["id"],))
        self.assertIsNotNone(file)
        self.assertEqual(file["filename"],"sujet.pdf")
        self.assertEqual(self.client.get(f"/assessments/files/{file['id']}").status_code,200)
        save=self.client.post(f"/grades/entry/{a['id']}",data={"csrf":self.token(),f"note_{student}":"15",f"comment_{student}":"Progrès solide"})
        self.assertEqual(save.status_code,302)
        grade=project.one("SELECT value,comment FROM grades WHERE student_id=? AND assessment_id=?",(student,a["id"]))
        self.assertEqual(grade["value"],15)
        self.assertEqual(grade["comment"],"Progrès solide")
        self.assertEqual(self.client.get(f"/grades/global?course_id={course}").status_code,200)
        self.assertEqual(self.client.get(f"/grades/class-summary?class_id={destination}").status_code,200)


    def test_teacher_validates_only_finished_sessions(self):
        self.login("enseignant1@demo.edupilot.test")
        teacher=project.one("SELECT id,school_id FROM users WHERE email='enseignant1@demo.edupilot.test'")
        course=project.one("SELECT id FROM courses WHERE school_id=? AND teacher_id=? LIMIT 1",(teacher["school_id"],teacher["id"]))
        self.assertIsNotNone(course)
        old=project.execute("INSERT INTO lessons(school_id,course_id,teacher_id,starts_at,ends_at,room) VALUES (?,?,?,?,?,?)",
            (teacher["school_id"],course["id"],teacher["id"],"2020-01-05T08:00","2020-01-05T09:30","A12"))
        confirmed=self.client.post(f"/lessons/{old}/declare",data={"csrf":self.token(),"status":"realisee","actual_minutes":"90","comment":"Cours effectué"})
        self.assertEqual(confirmed.status_code,302)
        row=project.one("SELECT status,actual_minutes FROM lessons WHERE id=?",(old,))
        self.assertEqual(row["status"],"realisee")
        self.assertEqual(row["actual_minutes"],90)
        future=project.execute("INSERT INTO lessons(school_id,course_id,teacher_id,starts_at,ends_at,room) VALUES (?,?,?,?,?,?)",
            (teacher["school_id"],course["id"],teacher["id"],"2030-01-05T08:00","2030-01-05T09:30","A12"))
        early=self.client.post(f"/lessons/{future}/declare",data={"csrf":self.token(),"status":"realisee","actual_minutes":"90"})
        self.assertEqual(early.status_code,400)


    def test_teacher_grade_immediate_visibility_and_bulletin_publication(self):
        self.login("enseignant1@demo.edupilot.test")
        teacher=project.one("SELECT id,school_id FROM users WHERE email='enseignant1@demo.edupilot.test'")
        course=project.one("SELECT id,class_id FROM courses WHERE school_id=? AND teacher_id=? LIMIT 1",(teacher["school_id"],teacher["id"]))
        self.assertIsNotNone(course)
        assessment=project.one("SELECT id FROM assessments WHERE course_id=? LIMIT 1",(course["id"],))
        self.assertIsNotNone(assessment)
        student=project.one("SELECT student_id FROM enrollments WHERE school_id=? AND class_id=? LIMIT 1",(teacher["school_id"],course["class_id"]))
        self.assertIsNotNone(student)
        response=self.client.post(f"/grades/entry/{assessment['id']}",data={"csrf":self.token(),
            f"note_{student['student_id']}":"17.5",f"comment_{student['student_id']}":"Très bon niveau"})
        self.assertEqual(response.status_code,302)
        st=project.one("SELECT email FROM users WHERE id=?",(student["student_id"],))
        self.client.post("/logout",data={"csrf":self.token()})
        # Student seeded account belongs to the same class; use known demo student.
        self.login("eleve1_1@demo.edupilot.test")
        page=self.client.get("/grades")
        self.assertEqual(page.status_code,200)
        self.assertIn("Mes notes".encode(),page.data)
        eva=self.client.get("/assessments")
        self.assertEqual(eva.status_code,200)
        self.assertIn("Note".encode(),eva.data)
        cid=course["class_id"]
        draft=self.client.get(f"/grades/my-bulletin/{cid}")
        self.assertEqual(draft.status_code,403)
        self.client.post("/logout",data={"csrf":self.token()})
        self.login("admin1@demo.edupilot.test")
        overview=self.client.get(f"/grades/bulletins?class_id={cid}")
        self.assertEqual(overview.status_code,200)
        printable=self.client.get(f"/grades/bulletins/print?class_id={cid}")
        self.assertEqual(printable.status_code,200)
        published=self.client.post("/grades/bulletins/publish",data={"csrf":self.token(),"class_id":cid})
        self.assertEqual(published.status_code,302)
        self.client.post("/logout",data={"csrf":self.token()})
        self.login("eleve1_1@demo.edupilot.test")
        report=self.client.get(f"/grades/my-bulletin/{cid}")
        self.assertEqual(report.status_code,200)
        self.assertIn("Bulletin".encode(),report.data)

    def test_school_bulk_course_coefficient_and_deletion(self):
        self.login("admin1@demo.edupilot.test")
        school=project.one("SELECT id FROM schools WHERE slug='groupe_scolaire_excellence'")
        clazz=project.one("SELECT id FROM classes WHERE school_id=? LIMIT 1",(school["id"],))
        ids=[project.execute("INSERT INTO courses(school_id,class_id,name,code,planned_minutes,coefficient) VALUES (?,?,?,?,?,?)",
                 (school["id"],clazz["id"],"Matière groupée "+str(i),"MTEST",300,1)) for i in range(2)]
        response=self.client.post("/courses/bulk",data={"csrf":self.token(),"action":"coefficient","coefficient":"4","course_ids":[str(v) for v in ids]})
        self.assertEqual(response.status_code,302)
        for cid in ids:self.assertEqual(project.one("SELECT coefficient FROM courses WHERE id=?",(cid,))["coefficient"],4)
        response=self.client.post("/courses/bulk",data={"csrf":self.token(),"action":"delete","course_ids":[str(v) for v in ids]})
        self.assertEqual(response.status_code,302)
        for cid in ids:self.assertIsNone(project.one("SELECT id FROM courses WHERE id=?",(cid,)))

    def test_teacher_session_can_be_confirmed_20_minutes_before_end(self):
        self.login("enseignant1@demo.edupilot.test")
        teacher=project.one("SELECT id,school_id FROM users WHERE email='enseignant1@demo.edupilot.test'")
        course=project.one("SELECT id FROM courses WHERE school_id=? AND teacher_id=? LIMIT 1",(teacher["school_id"],teacher["id"]))
        end=project.datetime.datetime.now()+project.datetime.timedelta(minutes=20)
        start=end-project.datetime.timedelta(minutes=90)
        lesson=project.execute("INSERT INTO lessons(school_id,course_id,teacher_id,starts_at,ends_at,room) VALUES (?,?,?,?,?,?)",
            (teacher["school_id"],course["id"],teacher["id"],start.strftime('%Y-%m-%dT%H:%M'),end.strftime('%Y-%m-%dT%H:%M'),"Test A12"))
        result=self.client.post(f"/lessons/{lesson}/declare",data={"csrf":self.token(),"status":"realisee","actual_minutes":"70"})
        self.assertEqual(result.status_code,302)

    def test_school_lifecycle_logo_and_deletion(self):
        self.login("superadmin@demo.edupilot.test")
        token = self.token()
        slug = "demo_lifecycle_tests"
        img = bytes([137,80,78,71,13,10,26,10]) + b"fictitiousimage"
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

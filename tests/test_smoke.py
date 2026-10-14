"""Tests fonctionnels EduPilot sur base SQLite temporaire isolée."""
import io
import os
import tempfile
import unittest
import uuid

TEMP = tempfile.TemporaryDirectory()
os.environ["DATABASE_PATH"] = os.path.join(TEMP.name, "edupilot-test.db")
os.environ["SECRET_KEY"] = "ci-only-unique-secret"
import app as project
from werkzeug.security import generate_password_hash

def seed_test_data():
    if project.one('SELECT id FROM schools LIMIT 1'): return
    with project.db() as c:
        for name,slug,plan in [('Groupe Scolaire Excellence','groupe_scolaire_excellence','premium'),('Université de Bouaké test','universite_de_bouake','standard')]:
            school=c.execute('INSERT INTO schools(name,slug,plan) VALUES (?,?,?)',(name,slug,plan)).lastrowid
            campus=c.execute('INSERT INTO campuses(school_id,name) VALUES (?,?)',(school,'Campus principal')).lastrowid
            year=c.execute('INSERT INTO years(school_id,label) VALUES (?,?)',(school,'2026-2027')).lastrowid
            cls=c.execute('INSERT INTO classes(school_id,year_id,campus_id,name,cycle,parents_enabled) VALUES (?,?,?,?,?,?)',(school,year,campus,'Terminale D' if school==1 else 'Master 1 Géomatique','trimestre' if school==1 else 'semestre',1)).lastrowid
            def u(name,email,role):
                return c.execute('INSERT INTO users(school_id,name,email,password_hash,role) VALUES (?,?,?,?,?)',(school,name,email,generate_password_hash('Test2026!'),role)).lastrowid
            admin=u('Admin établissement',f'admin{school}@tests.edupilot.invalid','admin')
            staff=u('Secrétariat',f'scolarite{school}@tests.edupilot.invalid','administratif')
            teacher=u('Enseignant test',f'enseignant{school}@tests.edupilot.invalid','enseignant')
            students=[u(f'Élève {i}',f'eleve{school}_{i}@tests.edupilot.invalid','etudiant') for i in range(1,9)]
            parent=u('Parent test',f'parent{school}@tests.edupilot.invalid','parent')
            c.execute('INSERT INTO parent_links(school_id,student_id,parent_id) VALUES (?,?,?)',(school,students[0],parent))
            for st in students: c.execute('INSERT INTO enrollments(school_id,student_id,class_id,year_id) VALUES (?,?,?,?)',(school,st,cls,year))
            course=c.execute('INSERT INTO courses(school_id,class_id,name,code,planned_minutes,teacher_id) VALUES (?,?,?,?,?,?)',(school,cls,'Mathématiques' if school==1 else 'SIG avancé','MAT101' if school==1 else 'SIG101',2400,teacher)).lastrowid
            c.execute('INSERT INTO teacher_history(course_id,teacher_id,date_start) VALUES (?,?,?)',(course,teacher,'2026-09-01'))
            for day in range(1,6):
                start=f'2026-10-{12+day-1:02d}T08:00'
                end=f'2026-10-{12+day-1:02d}T10:00'
                c.execute('INSERT INTO lessons(school_id,course_id,teacher_id,starts_at,ends_at,room,status,actual_minutes) VALUES (?,?,?,?,?,?,?,?)',(school,course,teacher,start,end,'A12','realisee' if day<3 else 'programmee',120 if day<3 else 0))
            assessment=c.execute('INSERT INTO assessments(school_id,course_id,title,kind,due_date,description) VALUES (?,?,?,?,?,?)',(school,course,'Devoir n° 1','Devoir','2026-10-23','Déposer votre travail avant la date limite.')).lastrowid
            c.execute('INSERT INTO periods(school_id,class_id,name) VALUES (?,?,?)',(school,cls,'Trimestre 1' if school==1 else 'Semestre 1'))
            for i,st in enumerate(students):c.execute('INSERT INTO grades(assessment_id,student_id,value) VALUES (?,?,?)',(assessment,st,10+i))
        c.execute('INSERT INTO users(school_id,name,email,password_hash,role) VALUES (NULL,?,?,?,?)',('Éditeur EduPilot','superadmin@tests.edupilot.invalid',generate_password_hash('Test2026!'),'superadmin'))

class EduPilotSmoke(unittest.TestCase):
    def setUp(self):
        # Fresh database for each test: prevents role, password, course and period
        # mutations from making unrelated test cases order-dependent.
        project.DB = os.path.join(TEMP.name, "test-" + uuid.uuid4().hex + ".db")
        with project.db() as c:
            c.executescript(project.SCHEMA)
        seed_test_data()
        self.client = project.app.test_client()

    def csrf(self):
        self.client.get("/login")
        with self.client.session_transaction() as sess:
            return sess["csrf"]

    def login(self, email):
        token = self.csrf()
        return self.client.post("/login", data={"csrf": token, "email": email, "password": "Test2026!"}, follow_redirects=True)

    def token(self):
        with self.client.session_transaction() as sess:
            return sess["csrf"]

    def test_all_templates_compile(self):
        for template in ("base.html","dashboard.html","schools.html","settings.html","restricted.html","login.html","list.html","planning.html","edit_academic.html","class_details.html","dashboard_student.html","school_new.html","school_accounts.html","school_account_edit.html","change_password.html","students.html","grade_entry.html","grade_global.html","class_grade_summary.html","courses_manage.html","lesson_edit.html","assessment_edit.html","staff_grades.html","student_grades.html","school_bulletins.html","print_bulletins.html"):
            project.app.jinja_env.get_template(template)

    def test_health(self):
        self.assertEqual(self.client.get("/health").json["status"], "ok")

    def test_login_required(self):
        self.assertEqual(self.client.get("/").status_code, 302)

    def test_admin_login(self):
        result = self.login("admin1@tests.edupilot.invalid")
        self.assertEqual(result.status_code, 200)
        self.assertIn(b"Tableau de bord", result.data)

    def test_superadmin_settings(self):
        self.login("superadmin@tests.edupilot.invalid")
        r = self.client.post("/settings", data={
            "csrf": self.token(), "support_name": "LMurbs",
            "support_phone": "+2250711124359",
            "powered_by": "Propulsé par LMurbs",
        }, follow_redirects=True)
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"LMurbs", r.data)

    def test_subscription_blocks_all_protected_pages(self):
        school = project.one("SELECT school_id FROM users WHERE email=?", ("admin1@tests.edupilot.invalid",))["school_id"]
        project.execute("UPDATE schools SET active=0 WHERE id=?", (school,))
        try:
            response = self.login("admin1@tests.edupilot.invalid")
            self.assertIn("restreint".encode(), response.data)
            for path in ("/", "/planning", "/grades", "/reports", "/api/planning"):
                self.assertEqual(self.client.get(path).status_code, 302)
        finally:
            project.execute("UPDATE schools SET active=1 WHERE id=?", (school,))

    def test_expiration_date_blocks_access(self):
        school=project.one("SELECT school_id FROM users WHERE email=?",("admin1@tests.edupilot.invalid",))["school_id"]
        project.execute("UPDATE schools SET subscription_end='2020-01-01' WHERE id=?", (school,))
        try:
            response=self.login("admin1@tests.edupilot.invalid")
            self.assertIn("restreint".encode(),response.data)
        finally:
            project.execute("UPDATE schools SET subscription_end=NULL WHERE id=?", (school,))


    def test_create_tenant_admin_force_password_change(self):
        self.login("superadmin@tests.edupilot.invalid")
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
        # The supplied legacy password is ignored. The recipient chooses their own
        # password through the single-use activation link sent by Brevo.
        self.assertFalse(project.check_password_hash(created['password_hash'],password))
        self.client.post("/logout",data={"csrf":token})
        # Ensure the scoped login does not accept another institution's admin.
        csrf=self.csrf()
        wrong=self.client.post(f"/{school['slug']}/login",data={"csrf":csrf,"email":"admin1@tests.edupilot.invalid","password":"Test2026!"})
        self.assertEqual(wrong.status_code,302)
        with self.client.session_transaction() as sess:self.assertNotIn("uid",sess)
        import hashlib
        token_value="sample-activation-token-for-test"
        project.execute("INSERT INTO invites(user_id,token_hash,expires_at) VALUES (?,?,?)",
            (created["id"],hashlib.sha256(token_value.encode()).hexdigest(),"2099-01-01T00:00:00+00:00"))
        csrf=self.csrf()
        opened=self.client.get("/activate/"+token_value)
        self.assertEqual(opened.status_code,200)
        result=self.client.post("/activate/"+token_value,data={"csrf":csrf,"password":"MyNewPass2026Safe!","confirm_password":"MyNewPass2026Safe!"})
        self.assertEqual(result.status_code,302)
        self.assertEqual(self.client.get("/activate/"+token_value).status_code,404)
        csrf=self.csrf()
        login=self.client.post(f"/{school['slug']}/login",data={"csrf":csrf,"email":"alice.edupilot@example.test","password":"MyNewPass2026Safe!"})
        self.assertIn("/",login.headers["Location"])
        changed=project.one("SELECT must_change_password FROM users WHERE id=?",(created["id"],))
        self.assertEqual(changed["must_change_password"],0)
        self.assertTrue(project.check_password_hash(project.one("SELECT password_hash FROM users WHERE id=?",(created["id"],))["password_hash"],"MyNewPass2026Safe!"))


    def test_brevo_invitation_activation_and_password_reset(self):
        import re
        from unittest.mock import patch,Mock
        self.login("admin1@tests.edupilot.invalid")
        classroom=project.one("SELECT id FROM classes WHERE school_id=1 LIMIT 1")
        captures=[]
        def brevo_mock(url,**kwargs):
            captures.append(kwargs["json"])
            response=Mock()
            response.raise_for_status.return_value=None
            return response
        with patch.dict(project.os.environ,{"BREVO_API_KEY":"ci-test-key","BREVO_SENDER_EMAIL":"noreply@edupilot.ci"}),patch.object(project.requests,"post",side_effect=brevo_mock):
            resp=self.client.post("/people",data={"csrf":self.token(),"name":"Élève Invité","email":"invite.student@example.test","role":"etudiant","class_id":classroom["id"]})
            self.assertEqual(resp.status_code,302)
            self.assertEqual(len(captures),1)
            self.assertEqual(captures[0]["to"][0]["email"],"invite.student@example.test")
            msg=captures[0]["textContent"]
            found=re.search(r"https://[^\\s]+/activate/([A-Za-z0-9_-]+)",msg)
            self.assertIsNotNone(found)
            self.assertNotIn("Temporary2026Secret!",msg)
            token=found.group(1)
            self.assertEqual(self.client.get("/activate/"+token).status_code,200)
            activated=self.client.post("/activate/"+token,data={"csrf":self.token(),"password":"SecurePassword2026!","confirm_password":"SecurePassword2026!"})
            self.assertEqual(activated.status_code,302)
            self.assertEqual(self.client.get("/activate/"+token).status_code,404)
            student=project.one("SELECT must_change_password,password_hash FROM users WHERE email='invite.student@example.test'")
            self.assertEqual(student["must_change_password"],0)
            self.assertTrue(project.check_password_hash(student["password_hash"],"SecurePassword2026!"))
            self.client.post("/logout",data={"csrf":self.token()})
            csrf=self.csrf()
            reset=self.client.post("/forgot-password",data={"csrf":csrf,"email":"invite.student@example.test"})
            self.assertEqual(reset.status_code,302)
            self.assertEqual(len(captures),2)
            reset_token=re.search(r"/activate/([A-Za-z0-9_-]+)",captures[1]["textContent"]).group(1)
            self.assertNotEqual(reset_token,token)
            again=self.client.post("/forgot-password",data={"csrf":csrf,"email":"invite.student@example.test"})
            self.assertEqual(again.status_code,302)
            self.assertEqual(len(captures),2)  # Rate-limited, but same public response.
            unknown=self.client.post("/forgot-password",data={"csrf":csrf,"email":"unknown@example.test"})
            self.assertEqual(unknown.status_code,302)
            self.assertEqual(len(captures),2)
            changed=self.client.post("/activate/"+reset_token,data={"csrf":csrf,"password":"AnotherPassword2026!","confirm_password":"AnotherPassword2026!"})
            self.assertEqual(changed.status_code,302)
            self.assertEqual(self.client.get("/activate/"+reset_token).status_code,404)

    def test_student_creation_assigns_class(self):
        self.login("admin1@tests.edupilot.invalid")
        cl=project.one("SELECT id,year_id FROM classes WHERE school_id=1 ORDER BY id LIMIT 1")
        email="manual.student.test@example.test"
        response=self.client.post("/people",data={"csrf":self.token(),"role":"etudiant","name":"Etudiant Manuel","email":email,"class_id":cl["id"],"password":"Temporary2026Secret!"})
        self.assertEqual(response.status_code,302)
        student=project.one("SELECT id FROM users WHERE email=?",(email,))
        self.assertIsNotNone(student)
        self.assertIsNotNone(project.one("SELECT id FROM enrollments WHERE school_id=1 AND student_id=? AND class_id=? AND year_id=?",(student["id"],cl["id"],cl["year_id"])))

    def test_bulk_csv_students_enrolled(self):
        self.login("admin1@tests.edupilot.invalid")
        cl=project.one("SELECT id FROM classes WHERE school_id=1 ORDER BY id LIMIT 1")
        content=("prenom;nom;email;classe\nAicha;test;aicha.bulk@example.test;"+str(cl["id"])+"\nBakary;test;bakary.bulk@example.test;"+str(cl["id"])+"\n").encode("utf-8")
        response=self.client.post("/people/import",data={"csrf":self.token(),"file":(io.BytesIO(content),"students.csv")},content_type="multipart/form-data")
        self.assertEqual(response.status_code,302)
        for email in ("aicha.bulk@example.test","bakary.bulk@example.test"):
            student=project.one("SELECT id FROM users WHERE email=?",(email,))
            self.assertIsNotNone(student)
            self.assertIsNotNone(project.one("SELECT id FROM enrollments WHERE student_id=? AND class_id=?",(student["id"],cl["id"])))

    def test_bulk_csv_students_selected_class_overrides_file(self):
        self.login("admin1@tests.edupilot.invalid")
        own=project.one("SELECT id FROM classes WHERE school_id=1 ORDER BY id LIMIT 1")
        foreign=project.one("SELECT id FROM classes WHERE school_id=2 ORDER BY id LIMIT 1")
        content=("prenom;nom;email;classe\nAwa;Kone;awa.override@example.test;"+str(foreign["id"])+"\n").encode("utf-8")
        response=self.client.post("/people/import",data={"csrf":self.token(),"import_class_id":str(own["id"]),"file":(io.BytesIO(content),"students.csv")},content_type="multipart/form-data")
        self.assertEqual(response.status_code,302)
        student=project.one("SELECT id,matricule FROM users WHERE email='awa.override@example.test'")
        self.assertIsNotNone(student)
        self.assertTrue(student["matricule"])
        self.assertIsNotNone(project.one("SELECT id FROM enrollments WHERE student_id=? AND class_id=?",(student["id"],own["id"])))

    def test_bulk_csv_students_without_class_column(self):
        self.login("admin1@tests.edupilot.invalid")
        own=project.one("SELECT id FROM classes WHERE school_id=1 ORDER BY id LIMIT 1")
        content="prenom;nom;email\nMariam;Traore;mariam.import@example.test\n".encode("utf-8")
        response=self.client.post("/people/import",data={"csrf":self.token(),"import_class_id":str(own["id"]),"file":(io.BytesIO(content),"students.csv")},content_type="multipart/form-data")
        self.assertEqual(response.status_code,302)
        student=project.one("SELECT id FROM users WHERE email='mariam.import@example.test'")
        self.assertIsNotNone(student)
        self.assertIsNotNone(project.one("SELECT id FROM enrollments WHERE student_id=? AND class_id=?",(student["id"],own["id"])))

    def test_bulk_csv_rejects_foreign_selected_class(self):
        self.login("admin1@tests.edupilot.invalid")
        foreign=project.one("SELECT id FROM classes WHERE school_id=2 ORDER BY id LIMIT 1")
        content="prenom;nom;email\nAminata;Bamba;aminata.foreign@example.test\n".encode("utf-8")
        response=self.client.post("/people/import",data={"csrf":self.token(),"import_class_id":str(foreign["id"]),"file":(io.BytesIO(content),"students.csv")},content_type="multipart/form-data")
        self.assertEqual(response.status_code,302)
        self.assertIsNone(project.one("SELECT id FROM users WHERE email='aminata.foreign@example.test'"))

    def test_bulk_xlsx_students_enrolled(self):
        from openpyxl import Workbook
        self.login("admin1@tests.edupilot.invalid")
        cl=project.one("SELECT id FROM classes WHERE school_id=1 ORDER BY id LIMIT 1")
        wb=Workbook();ws=wb.active;ws.append(["prenom","nom","email","classe"]);ws.append(["Fatou","test","fatou.bulk@example.test",str(cl["id"])])
        bio=io.BytesIO();wb.save(bio);bio.seek(0)
        response=self.client.post("/people/import",data={"csrf":self.token(),"file":(bio,"students.xlsx")},content_type="multipart/form-data")
        self.assertEqual(response.status_code,302)
        self.assertIsNotNone(project.one("SELECT id FROM users WHERE email='fatou.bulk@example.test'"))

    def test_logout_revokes_only_current_device_push(self):
        self.login("admin1@tests.edupilot.invalid")
        uid=project.one("SELECT id FROM users WHERE email='admin1@tests.edupilot.invalid'")["id"]
        a="https://fcm.googleapis.com/fcm/send/device-a"
        b="https://fcm.googleapis.com/fcm/send/device-b"
        for endpoint in (a,b):
            project.execute("INSERT INTO push_subscriptions(user_id,endpoint,subscription_json) VALUES (?,?,?)",(uid,endpoint,'{}'))
        response=self.client.post("/logout",data={"csrf":self.token(),"push_endpoint":a})
        self.assertEqual(response.status_code,302)
        self.assertIsNone(project.one("SELECT id FROM push_subscriptions WHERE endpoint=?",(a,)))
        self.assertIsNotNone(project.one("SELECT id FROM push_subscriptions WHERE endpoint=?",(b,)))

    def test_web_push_registration_validation_and_user_scope(self):
        self.login("admin1@tests.edupilot.invalid")
        token=self.token()
        self.assertEqual(self.client.get("/api/push/config").status_code,200)
        invalid={"endpoint":"https://127.0.0.1:443/secret","keys":{"p256dh":"abcdefghijklmnop","auth":"abcdefghijklmnop"}}
        result=self.client.post("/api/push/subscribe",json=invalid,headers={"X-CSRF-Token":token})
        self.assertEqual(result.status_code,400)
        valid={"endpoint":"https://fcm.googleapis.com/fcm/send/test-123",
               "keys":{"p256dh":"abcdefghijklmnop","auth":"abcdefghijklmnop"}}
        result=self.client.post("/api/push/subscribe",json=valid,headers={"X-CSRF-Token":token})
        self.assertEqual(result.status_code,200)
        owner=project.one("SELECT user_id FROM push_subscriptions WHERE endpoint=?",(valid["endpoint"],))
        self.assertIsNotNone(owner)
        blocked=self.client.post("/api/push/unsubscribe",json={"endpoint":valid["endpoint"]})
        self.assertEqual(blocked.status_code,400)
        deleted=self.client.post("/api/push/unsubscribe",json={"endpoint":valid["endpoint"]},headers={"X-CSRF-Token":token})
        self.assertEqual(deleted.status_code,200)
        self.assertIsNone(project.one("SELECT id FROM push_subscriptions WHERE endpoint=?",(valid["endpoint"],)))

    def test_notification_bell_api_and_clear(self):
        self.login("admin1@tests.edupilot.invalid")
        user=project.one("SELECT id FROM users WHERE school_id=1 AND role='admin' LIMIT 1")
        foreign=project.one("SELECT id FROM users WHERE school_id=2 LIMIT 1")
        aid=project.execute("INSERT INTO notifications(school_id,user_id,message,href) VALUES (1,?,'Alerte école','/planning')",(user["id"],))
        other=project.execute("INSERT INTO notifications(school_id,user_id,message,href) VALUES (2,?,'Alerte étrangère','/planning')",(foreign["id"],))
        result=self.client.get("/api/notifications")
        self.assertEqual(result.status_code,200)
        self.assertEqual(result.json["unread"],1)
        self.assertEqual(len(result.json["notifications"]),1)
        self.assertEqual(result.json["notifications"][0]["id"],aid)
        self.assertIn(b'notification-bell',self.client.get("/").data)
        self.assertNotIn(b'EduPilot D',self.client.get("/").data)
        self.assertEqual(self.client.post("/api/notifications/read",json={"ids":[aid]},headers={"X-CSRF-Token":self.token()}).status_code,200)
        self.assertEqual(self.client.get("/api/notifications").json["unread"],0)
        self.assertEqual(self.client.post("/api/notifications/delete",json={"all":True},headers={"X-CSRF-Token":self.token()}).status_code,200)
        self.assertIsNone(project.one("SELECT id FROM notifications WHERE id=?",(aid,)))
        self.assertIsNotNone(project.one("SELECT id FROM notifications WHERE id=?",(other,)))
        self.assertEqual(self.client.get("/sw.js").status_code,200)
        self.assertEqual(self.client.get("/manifest.webmanifest").status_code,200)

    def test_event_notifications_roles_and_school_isolation(self):
        with self.client:
            self.login("admin1@tests.edupilot.invalid")
            course=project.one("SELECT id,teacher_id,class_id FROM courses WHERE school_id=1 ORDER BY id LIMIT 1")
            other=project.one("SELECT id FROM users WHERE school_id=2 ORDER BY id LIMIT 1")
            student=project.one("SELECT id FROM users WHERE school_id=1 AND role='etudiant' LIMIT 1")
            admin=project.one("SELECT id FROM users WHERE school_id=1 AND role='admin' LIMIT 1")
            parent=project.one("SELECT id FROM users WHERE school_id=1 AND role='parent' LIMIT 1")
            project.execute("UPDATE classes SET parents_enabled=0 WHERE id=?",(course['class_id'],))
            recipients=project.event_recipients([course['id']],[course['teacher_id']])
            self.assertIn(student['id'],recipients)
            self.assertIn(admin['id'],recipients)
            self.assertIn(course['teacher_id'],recipients)
            self.assertNotIn(other['id'],recipients)
            self.assertNotIn(parent['id'],recipients)
            project.execute("UPDATE classes SET parents_enabled=1 WHERE id=?",(course['class_id'],))
            recipients=project.event_recipients([course['id']],[course['teacher_id']])
            self.assertIn(parent['id'],recipients)
            project.notify_event([course['id']],"Séance annulée : test",'/planning',teacher_ids=[course['teacher_id']])
            sent=project.allrows("SELECT user_id,message FROM notifications WHERE school_id=1 AND message='Séance annulée : test'")
            user_ids={n['user_id'] for n in sent}
            self.assertIn(student['id'],user_ids)
            self.assertIn(parent['id'],user_ids)
            self.assertIn(course['teacher_id'],user_ids)
            self.assertNotIn(admin['id'],user_ids)  # Actor does not receive a duplicate alert.
            self.assertNotIn(other['id'],user_ids)

    def test_teacher_can_receive_several_courses(self):
        self.login("admin1@tests.edupilot.invalid")
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
        self.login("admin1@tests.edupilot.invalid")
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
        self.login("admin1@tests.edupilot.invalid")
        cl=project.one("SELECT id FROM classes WHERE school_id=1 ORDER BY id LIMIT 1")
        response=self.client.post(f"/classes/{cl['id']}/edit",data={"csrf":self.token(),"name":"Classe rénovée","cycle":"semestre"})
        self.assertEqual(response.status_code,302)
        self.assertEqual(project.one("SELECT name FROM classes WHERE id=?",(cl["id"],))["name"],"Classe rénovée")
        course=project.one("SELECT id,class_id,code,teacher_id FROM courses WHERE school_id=1 ORDER BY id LIMIT 1")
        r=self.client.post(f"/courses/{course['id']}/edit",data={"csrf":self.token(),"name":"SIG renouvelé","code":"SIG202","class_id":course["class_id"],"hours":"24","teacher_id":str(course["teacher_id"] or "")})
        self.assertEqual(r.status_code,302)
        self.assertEqual(project.one("SELECT name FROM courses WHERE id=?",(course["id"],))["name"],"SIG renouvelé")
        target=project.one("SELECT id FROM users WHERE school_id=1 AND email='parent1@tests.edupilot.invalid'")
        r=self.client.post("/people/bulk",data={"csrf":self.token(),"action":"suspend","user_ids":[str(target["id"])]})
        self.assertEqual(r.status_code,302)
        self.assertEqual(project.one("SELECT active FROM users WHERE id=?",(target["id"],))["active"],0)
        r=self.client.post("/people/bulk",data={"csrf":self.token(),"action":"activate","user_ids":[str(target["id"])]})
        self.assertEqual(r.status_code,302)
        self.assertEqual(project.one("SELECT active FROM users WHERE id=?",(target["id"],))["active"],1)


    def test_class_details_scoped_and_lists(self):
        self.login("admin1@tests.edupilot.invalid")
        own=project.one("SELECT id FROM classes WHERE school_id=1 ORDER BY id LIMIT 1")
        foreign=project.one("SELECT id FROM classes WHERE school_id=2 ORDER BY id LIMIT 1")
        r=self.client.get(f"/classes/{own['id']}/details")
        self.assertEqual(r.status_code,200)
        self.assertIn("Étudiants de la classe".encode(),r.data)
        self.assertIn("Enseignants affectés".encode(),r.data)
        self.assertIn("Cours de la classe".encode(),r.data)
        self.assertEqual(self.client.get(f"/classes/{foreign['id']}/details").status_code,404)

    def test_student_dashboard_week_and_privacy(self):
        self.login("eleve1_1@tests.edupilot.invalid")
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
        self.login("superadmin@tests.edupilot.invalid")
        school=project.one("SELECT id FROM schools WHERE slug='groupe_scolaire_excellence'")
        admin=project.one("SELECT id FROM users WHERE email='admin1@tests.edupilot.invalid'")
        staff=project.one("SELECT id FROM users WHERE email='scolarite1@tests.edupilot.invalid'")
        sid=school["id"]
        self.assertEqual(self.client.get(f"/schools/{sid}/accounts/{admin['id']}/edit").status_code,200)
        edit=self.client.post(f"/schools/{sid}/accounts/{admin['id']}/edit",data={
            "csrf":self.token(),"first_name":"Adèle","last_name":"Direction",
            "email":"admin1@tests.edupilot.invalid","phone":"+2250700001111",
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
        self.login("superadmin@tests.edupilot.invalid")
        school=project.one("SELECT id FROM schools WHERE slug='groupe_scolaire_excellence'")
        other=project.one("SELECT id FROM users WHERE email='admin2@tests.edupilot.invalid'")
        self.assertEqual(self.client.get(f"/schools/{school['id']}/accounts/{other['id']}/edit").status_code,404)
        bad=self.client.post(f"/schools/{school['id']}/accounts/bulk",data={"csrf":self.token(),"action":"suspend","account_ids":[str(other["id"])]})
        self.assertEqual(bad.status_code,403)
        uid=project.execute("INSERT INTO users(school_id,name,email,phone,role,password_hash) VALUES (?,?,?,?,?,?)",
            (school["id"],"Compte provisoire","deletion.account@example.test","+2250700000000","administratif",project.generate_password_hash("SomeLongPassword2026!")))
        res=self.client.post(f"/schools/{school['id']}/accounts/bulk",data={"csrf":self.token(),"action":"delete","account_ids":[str(uid)]})
        self.assertEqual(res.status_code,302)
        self.assertIsNone(project.one("SELECT id FROM users WHERE id=?",(uid,)))


    def test_transfer_and_grading_workflows(self):
        self.login("admin1@tests.edupilot.invalid")
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
        self.login("enseignant1@tests.edupilot.invalid")
        teacher=project.one("SELECT id,school_id FROM users WHERE email='enseignant1@tests.edupilot.invalid'")
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
        self.login("enseignant1@tests.edupilot.invalid")
        teacher=project.one("SELECT id,school_id FROM users WHERE email='enseignant1@tests.edupilot.invalid'")
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
        # Student seeded account belongs to the same class; use known test student.
        self.login("eleve1_1@tests.edupilot.invalid")
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
        self.login("admin1@tests.edupilot.invalid")
        overview=self.client.get(f"/grades/bulletins?class_id={cid}")
        self.assertEqual(overview.status_code,200)
        printable=self.client.get(f"/grades/bulletins/print?class_id={cid}")
        self.assertEqual(printable.status_code,200)
        published=self.client.post("/grades/bulletins/publish",data={"csrf":self.token(),"class_id":cid})
        self.assertEqual(published.status_code,302)
        self.client.post("/logout",data={"csrf":self.token()})
        self.login("eleve1_1@tests.edupilot.invalid")
        report=self.client.get(f"/grades/my-bulletin/{cid}")
        self.assertEqual(report.status_code,200)
        self.assertIn("Bulletin".encode(),report.data)

    def test_school_bulk_course_coefficient_and_deletion(self):
        self.login("admin1@tests.edupilot.invalid")
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
        self.login("enseignant1@tests.edupilot.invalid")
        teacher=project.one("SELECT id,school_id FROM users WHERE email='enseignant1@tests.edupilot.invalid'")
        course=project.one("SELECT id FROM courses WHERE school_id=? AND teacher_id=? LIMIT 1",(teacher["school_id"],teacher["id"]))
        end=project.datetime.datetime.now()+project.datetime.timedelta(minutes=20)
        start=end-project.datetime.timedelta(minutes=90)
        lesson=project.execute("INSERT INTO lessons(school_id,course_id,teacher_id,starts_at,ends_at,room) VALUES (?,?,?,?,?,?)",
            (teacher["school_id"],course["id"],teacher["id"],start.strftime('%Y-%m-%dT%H:%M'),end.strftime('%Y-%m-%dT%H:%M'),"Test A12"))
        result=self.client.post(f"/lessons/{lesson}/declare",data={"csrf":self.token(),"status":"realisee","actual_minutes":"70"})
        self.assertEqual(result.status_code,302)


    def test_selected_bulletin_publication_is_student_scoped(self):
        self.login("admin1@tests.edupilot.invalid")
        school=project.one("SELECT id FROM schools WHERE slug='groupe_scolaire_excellence'")
        clazz=project.one("SELECT id FROM classes WHERE school_id=? LIMIT 1",(school["id"],))
        pupils=project.allrows("SELECT DISTINCT u.id,u.email FROM users u JOIN enrollments e ON e.student_id=u.id WHERE e.school_id=? AND e.class_id=? ORDER BY u.id LIMIT 2",(school["id"],clazz["id"]))
        self.assertEqual(len(pupils),2)
        publish=self.client.post("/grades/bulletins/publish",data={"csrf":self.token(),"class_id":clazz["id"],"student_ids":[str(pupils[0]["id"])]})
        self.assertEqual(publish.status_code,302)
        self.assertEqual(project.one("SELECT COUNT(*) n FROM bulletin_publications WHERE class_id=?",(clazz["id"],))["n"],1)
        self.assertEqual(project.one("SELECT published FROM periods WHERE class_id=? ORDER BY id DESC LIMIT 1",(clazz["id"],))["published"],0)
        self.client.post("/logout",data={"csrf":self.token()})
        self.login(pupils[0]["email"])
        self.assertEqual(self.client.get(f"/grades/my-bulletin/{clazz['id']}").status_code,200)
        self.client.post("/logout",data={"csrf":self.token()})
        self.login(pupils[1]["email"])
        self.assertEqual(self.client.get(f"/grades/my-bulletin/{clazz['id']}").status_code,403)

    def test_teacher_can_edit_assessment_before_lock(self):
        self.login("enseignant1@tests.edupilot.invalid")
        teacher=project.one("SELECT id,school_id FROM users WHERE email='enseignant1@tests.edupilot.invalid'")
        course=project.one("SELECT id FROM courses WHERE school_id=? AND teacher_id=? LIMIT 1",(teacher["school_id"],teacher["id"]))
        assessment=project.one("SELECT id FROM assessments WHERE school_id=? AND course_id=? LIMIT 1",(teacher["school_id"],course["id"]))
        page=self.client.get(f"/assessments/{assessment['id']}/edit")
        self.assertEqual(page.status_code,200)
        update=self.client.post(f"/assessments/{assessment['id']}/edit",data={"csrf":self.token(),"title":"Devoir corrigé","kind":"Devoir","coefficient":"3","description":"Consigne actualisée"})
        self.assertEqual(update.status_code,302)
        self.assertEqual(project.one("SELECT coefficient FROM assessments WHERE id=?",(assessment["id"],))["coefficient"],3)

    def test_existing_course_with_assessment_cannot_be_deleted(self):
        self.login("admin1@tests.edupilot.invalid")
        school=project.one("SELECT id FROM schools WHERE slug='groupe_scolaire_excellence'")
        course=project.one("SELECT id FROM courses WHERE school_id=? AND id IN (SELECT course_id FROM assessments) LIMIT 1",(school["id"],))
        res=self.client.post("/courses/bulk",data={"csrf":self.token(),"action":"delete","course_ids":[str(course["id"])]})
        self.assertEqual(res.status_code,302)
        self.assertIsNotNone(project.one("SELECT id FROM courses WHERE id=?",(course["id"],)))


    def test_admin_edit_session_and_bulk_changes(self):
        self.login("admin1@tests.edupilot.invalid")
        school=project.one("SELECT id FROM schools WHERE slug='groupe_scolaire_excellence'")
        course=project.one("SELECT id,teacher_id FROM courses WHERE school_id=? AND teacher_id IS NOT NULL LIMIT 1",(school["id"],))
        first=project.execute("INSERT INTO lessons(school_id,course_id,teacher_id,starts_at,ends_at,room) VALUES (?,?,?,?,?,?)",
            (school["id"],course["id"],course["teacher_id"],"2028-03-02T08:00","2028-03-02T09:00","Salle A"))
        second=project.execute("INSERT INTO lessons(school_id,course_id,teacher_id,starts_at,ends_at,room) VALUES (?,?,?,?,?,?)",
            (school["id"],course["id"],course["teacher_id"],"2028-03-09T08:00","2028-03-09T09:00","Salle A"))
        self.assertEqual(self.client.get(f"/lessons/{first}/edit").status_code,200)
        changed=self.client.post(f"/lessons/{first}/edit",data={"csrf":self.token(),"course_id":str(course["id"]),"lesson_date":"2028-03-02","start_time":"10:00","duration_hours":"1.5","room":"Salle B"})
        self.assertEqual(changed.status_code,302)
        self.assertEqual(project.one("SELECT ends_at FROM lessons WHERE id=?",(first,))["ends_at"],"2028-03-02T11:30")
        moved=self.client.post("/lessons/bulk",data={"csrf":self.token(),"action":"modify",
            "lesson_ids":[str(first),str(second)],"day_offset":"0","minute_offset":"30","change_room":"1","room":"Salle C"})
        self.assertEqual(moved.status_code,302)
        self.assertEqual(project.one("SELECT starts_at FROM lessons WHERE id=?",(first,))["starts_at"],"2028-03-02T10:30")
        self.assertEqual(project.one("SELECT room FROM lessons WHERE id=?",(second,))["room"],"Salle C")

    def test_admin_bulk_delete_protects_completed_sessions_and_tenant(self):
        self.login("admin1@tests.edupilot.invalid")
        school=project.one("SELECT id FROM schools WHERE slug='groupe_scolaire_excellence'")
        course=project.one("SELECT id,teacher_id FROM courses WHERE school_id=? AND teacher_id IS NOT NULL LIMIT 1",(school["id"],))
        allowed=project.execute("INSERT INTO lessons(school_id,course_id,teacher_id,starts_at,ends_at) VALUES (?,?,?,?,?)",
            (school["id"],course["id"],course["teacher_id"],"2028-04-02T08:00","2028-04-02T09:00"))
        protected=project.execute("INSERT INTO lessons(school_id,course_id,teacher_id,starts_at,ends_at,status,actual_minutes) VALUES (?,?,?,?,?,?,?)",
            (school["id"],course["id"],course["teacher_id"],"2028-04-09T08:00","2028-04-09T09:00","realisee",60))
        failed=self.client.post("/lessons/bulk",data={"csrf":self.token(),"action":"delete","lesson_ids":[str(allowed),str(protected)]})
        self.assertEqual(failed.status_code,302)
        self.assertIsNotNone(project.one("SELECT id FROM lessons WHERE id=?",(allowed,)))
        other=project.one("SELECT id FROM lessons WHERE school_id<>? LIMIT 1",(school["id"],))
        if other:
            attack=self.client.post("/lessons/bulk",data={"csrf":self.token(),"action":"delete","lesson_ids":[str(other["id"])]})
            self.assertEqual(attack.status_code,403)
        deleted=self.client.post("/lessons/bulk",data={"csrf":self.token(),"action":"delete","lesson_ids":[str(allowed)]})
        self.assertEqual(deleted.status_code,302)
        self.assertIsNone(project.one("SELECT id FROM lessons WHERE id=?",(allowed,)))
        self.assertIsNotNone(project.one("SELECT id FROM lessons WHERE id=?",(protected,)))

    def test_teacher_cannot_use_admin_session_editor(self):
        self.login("enseignant1@tests.edupilot.invalid")
        lesson=project.one("SELECT id FROM lessons WHERE school_id=1 LIMIT 1")
        self.assertEqual(self.client.get(f"/lessons/{lesson['id']}/edit").status_code,403)
        response=self.client.post("/lessons/bulk",data={"csrf":self.token(),"action":"delete","lesson_ids":[str(lesson["id"])]})
        self.assertEqual(response.status_code,403)

    def test_school_lifecycle_logo_and_deletion(self):
        self.login("superadmin@tests.edupilot.invalid")
        token = self.token()
        slug = "test_lifecycle_tests"
        img = bytes([137,80,78,71,13,10,26,10]) + b"fictitiousimage"
        r=self.client.post("/schools/new",data={
            "csrf":token,"name":"test Lifecycle Tests","plan":"premium",
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

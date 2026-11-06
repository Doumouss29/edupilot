"""Security regressions for spreadsheet exports, Office uploads and memo templates.

Only disposable SQLite test data is used; no production database or network access.
"""
import io
import os
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from docx import Document
from openpyxl import Workbook
from werkzeug.security import generate_password_hash

ROOT=Path(__file__).resolve().parents[1]
TMP=tempfile.TemporaryDirectory()
os.environ['DB_ENGINE']='sqlite'
os.environ['DATABASE_PATH']=str(Path(TMP.name)/'startup.db')
os.environ['SECRET_KEY']='office-upload-tests'
sys.path.insert(0,str(ROOT))
import app as project
import memo_documents


def docx_bytes(text):
    doc=Document()
    doc.add_paragraph(text)
    out=io.BytesIO()
    doc.save(out)
    return out.getvalue()


def xlsx_bytes():
    wb=Workbook()
    wb.active.append(['nom','prenom','email'])
    out=io.BytesIO()
    wb.save(out)
    return out.getvalue()


def fake_zip(items):
    buffer=io.BytesIO()
    with zipfile.ZipFile(buffer,'w',zipfile.ZIP_DEFLATED) as z:
        for name,data in items:
            z.writestr(name,data)
    return buffer.getvalue()


class FileAndExportSecurityTests(unittest.TestCase):
    def test_csv_formula_prefixes_are_escaped(self):
        for raw in ('=1+1','+SUM(1,2)','-4+5','@SUM(A1)','  =HYPERLINK("x")','\t=2+2'):
            with self.subTest(raw=raw):
                self.assertTrue(project.csv_safe_cell(raw).startswith("'"))

    def test_normal_csv_values_are_preserved(self):
        self.assertEqual(project.csv_safe_cell('Mathématiques'), 'Mathématiques')
        self.assertEqual(project.csv_safe_cell('L3 Topographie'), 'L3 Topographie')
        self.assertEqual(project.csv_safe_cell(42),42)

    def test_real_docx_is_accepted(self):
        project.validate_office_archive(docx_bytes('{{ enseignant }}'),'docx')

    def test_real_xlsx_is_accepted(self):
        project.validate_office_archive(xlsx_bytes(),'xlsx')

    def test_fake_zip_cannot_masquerade_as_office(self):
        with self.assertRaises(ValueError):
            project.validate_office_archive(fake_zip([('fake','content')]),'docx')

    def test_zip_bomb_is_rejected_before_decompression(self):
        data=fake_zip([
            ('[Content_Types].xml','manifest'),
            ('word/document.xml',b'A'*(17*1024*1024)),
        ])
        self.assertLess(len(data),1024*1024)
        with self.assertRaises(ValueError):
            project.validate_office_archive(data,'docx')

    def test_office_path_traversal_rejected(self):
        data=fake_zip([
            ('[Content_Types].xml','manifest'),
            ('word/document.xml','document'),
            ('../outside.txt','unexpected'),
        ])
        with self.assertRaises(ValueError):
            project.validate_office_archive(data,'docx')

    def test_memo_template_renders_whitelisted_context(self):
        result=memo_documents.build_docx({'enseignant':'Professeur Essai'},
                                          docx_bytes('Enseignant : {{ enseignant }}'))
        rendered=Document(io.BytesIO(result))
        self.assertIn('Professeur Essai',rendered.paragraphs[0].text)

    def test_memo_template_cannot_inspect_python_internals(self):
        exploit=docx_bytes("{{ ''.__class__.__mro__ }}")
        with self.assertRaises(Exception):
            memo_documents.build_docx({},exploit)

    def test_report_csv_escapes_attacker_controlled_course_name(self):
        project.DB=str(Path(TMP.name)/'report-csv.db')
        with project.db() as c:
            c.executescript(project.SCHEMA)
            c.execute("ALTER TABLE years ADD COLUMN status TEXT NOT NULL DEFAULT 'active'")
            c.execute("ALTER TABLE classes ADD COLUMN filiere_id INTEGER")
            c.execute("CREATE TABLE IF NOT EXISTS filieres(id INTEGER PRIMARY KEY,school_id INTEGER,name TEXT)")
            c.execute("INSERT INTO schools(id,name,slug) VALUES (1,'Ecole','ecole')")
            c.execute("""INSERT INTO users(id,school_id,name,email,password_hash,role)
                VALUES (1,1,'Admin','admin@test.invalid',?,'admin')""",
                (generate_password_hash('PasswordTest123'),))
            c.execute("INSERT INTO years(id,school_id,label,is_active,status) VALUES (1,1,'2026-2027',1,'active')")
            c.execute("INSERT INTO classes(id,school_id,year_id,name) VALUES (1,1,1,'=2+2')")
            c.execute("INSERT INTO courses(id,school_id,class_id,name,code,planned_minutes) VALUES (1,1,1,'=1+1','E',120)")
        client=project.app.test_client()
        user=project.one('SELECT * FROM users WHERE id=1')
        with client.session_transaction() as sess:
            sess['uid']=1
            sess['auth_stamp']=project.session_auth_stamp(user)
            sess['csrf']='csrf-test'
        response=client.get('/reports?format=csv')
        self.assertEqual(response.status_code,200)
        self.assertIn("'=1+1",response.get_data(as_text=True))
        self.assertIn("'=2+2",response.get_data(as_text=True))


if __name__=='__main__':
    unittest.main()

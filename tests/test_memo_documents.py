import io
import unittest
from decimal import Decimal
from docx import Document
from memo_documents import context_for_memo, build_docx, build_pdf

class MemoDocumentTests(unittest.TestCase):
    def setUp(self):
        meta={'institution':'Université Démo','currency':'FCFA','tax_rate':2,'signer1':'Responsable','signer2':'Directeur','reference':'MEMO-2026-001'}
        teacher={'name':'Enseignant Test'}
        course={'name':'Fondements des SIG'}
        clazz={'name':'Licence 3','academic_year':'2026-2027'}
        self.ctx=context_for_memo(meta,teacher,course,clazz,Decimal('40'),Decimal('15000'),Decimal('2'))

    def test_financial_calculation(self):
        self.assertEqual(self.ctx['montant_brut'],'600 000')
        self.assertEqual(self.ctx['prelevement'],'12 000')
        self.assertEqual(self.ctx['montant_net'],'588 000')
        self.assertIn('cinq cent quatre-vingt-huit mille',self.ctx['montant_net_lettres'].lower())

    def test_standard_word_generation(self):
        data=build_docx(self.ctx)
        doc=Document(io.BytesIO(data))
        text=' '.join(p.text for p in doc.paragraphs)
        self.assertIn('588 000',text)
        self.assertIn('Enseignant Test',text)

    def test_pdf_generation(self):
        self.assertTrue(build_pdf(self.ctx).startswith(b'%PDF-'))

if __name__=='__main__':unittest.main()

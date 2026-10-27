"""Tenant-isolated teacher honorarium memo document rendering."""
import io
from decimal import Decimal, ROUND_HALF_UP
from num2words import num2words
from docx import Document
from docx.shared import Pt, Inches
from reportlab.lib.utils import ImageReader
from docxtpl import DocxTemplate
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import simpleSplit

def amount(value):
    return format(Decimal(str(value)).quantize(Decimal("1"), rounding=ROUND_HALF_UP), "f").split(".")[0]

def context_for_memo(meta,teacher,course,clazz,hours,rate,tax):
    gross=Decimal(str(hours))*Decimal(str(rate))
    withholding=(gross*Decimal(str(tax))/100).quantize(Decimal("1"),rounding=ROUND_HALF_UP)
    net=gross-withholding
    formatted=lambda x: format(int(x),",").replace(","," ")
    return dict(
        etablissement=meta.get("institution",""),enseignant=teacher["name"],
        cours=course["name"],classe=clazz["name"],annee_academique=clazz["academic_year"],
        volume_horaire=str(hours),tarif_horaire=formatted(rate),
        taux_prelevement=str(tax),montant_brut=formatted(gross),
        prelevement=formatted(withholding),montant_net=formatted(net),
        montant_net_lettres=num2words(int(net),lang="fr").capitalize(),
        devise=meta.get("currency","FCFA"),reference=meta.get("reference",""),
        ville=meta.get("city",""),date=meta.get("date",""),
        objet=meta.get("subject","Paiement des honoraires"),
        destinataire=meta.get("recipient",""),
        signataire_1=meta.get("signer1",""),signataire_2=meta.get("signer2",""),
        imputation=meta.get("budget",""),entete=meta.get("header",""),
        adresse=meta.get("address",""),
    )

def build_docx(ctx,template=None,logo=None):
    if template:
        doc=DocxTemplate(io.BytesIO(template))
        doc.render(ctx,autoescape=True)
        out=io.BytesIO();doc.save(out);return out.getvalue()
    doc=Document()
    sec=doc.sections[0];sec.header.paragraphs[0].text=ctx["entete"] or ctx["etablissement"]
    if logo:
        try:doc.add_picture(io.BytesIO(logo),width=Inches(1.0))
        except Exception:pass
    doc.add_heading(ctx["etablissement"],0)
    doc.add_paragraph(ctx["adresse"])
    doc.add_paragraph("MEMO INTERNE N° "+ctx["reference"])
    doc.add_paragraph(ctx["ville"]+" — "+ctx["date"])
    doc.add_paragraph("À : "+ctx["destinataire"])
    doc.add_heading("Objet : "+ctx["objet"],level=2)
    doc.add_paragraph("Veuillez procéder au paiement des honoraires de :")
    doc.add_heading(ctx["enseignant"],level=2)
    doc.add_paragraph("Pour le cours : "+ctx["cours"])
    doc.add_paragraph("Classe : "+ctx["classe"]+" — Année académique : "+ctx["annee_academique"])
    for key,label in [("volume_horaire","Volume horaire"),("tarif_horaire","Taux horaire"),("montant_brut","Montant brut"),("prelevement","Prélèvement fiscal"),("montant_net","Net à payer")]:
        suffix=" h" if key=="volume_horaire" else (" %" if key=="taux_prelevement" else " "+ctx["devise"])
        doc.add_paragraph(label+" : "+ctx[key]+suffix)
    doc.add_paragraph("Taux de prélèvement : "+ctx["taux_prelevement"]+" %")
    doc.add_paragraph("Imputation budgétaire : "+ctx["imputation"])
    doc.add_paragraph(ctx["signataire_1"]+"                                  "+ctx["signataire_2"])
    out=io.BytesIO();doc.save(out);return out.getvalue()

def build_pdf(ctx,logo=None):
    buf=io.BytesIO();pdf=canvas.Canvas(buf,pagesize=A4)
    width,height=A4;y=height-55
    if logo:
        try:
            img=ImageReader(io.BytesIO(logo));iw,ih=img.getSize()
            w=min(75,iw);h=w*ih/iw
            if h>60:w=w*60/h;h=60
            pdf.drawImage(img,width-55-w,height-35-h,w,h,mask='auto')
        except Exception:pass
    def line(value,bold=False,size=10,space=9):
        nonlocal y
        pdf.setFont("Helvetica-Bold" if bold else "Helvetica",size)
        for chunk in simpleSplit(str(value or ""), "Helvetica-Bold" if bold else "Helvetica",size,width-105):
            if y<85:pdf.showPage();y=height-55;pdf.setFont("Helvetica-Bold" if bold else "Helvetica",size)
            pdf.drawString(52,y,chunk);y-=size+5
        y-=space
    line(ctx["entete"] or ctx["etablissement"],True,13)
    line(ctx["adresse"])
    line("MEMO INTERNE : "+ctx["reference"],True,12)
    line(ctx["ville"]+"  "+ctx["date"])
    line("À : "+ctx["destinataire"])
    line("Objet : "+ctx["objet"],True,12)
    line("Veuillez procéder au paiement des honoraires de :")
    line(ctx["enseignant"],True,13)
    line("Cours : "+ctx["cours"])
    line("Classe : "+ctx["classe"]+" / "+ctx["annee_academique"])
    line("Volume horaire : "+ctx["volume_horaire"]+" h")
    line("Taux horaire : "+ctx["tarif_horaire"]+" "+ctx["devise"])
    line("Montant brut : "+ctx["montant_brut"]+" "+ctx["devise"])
    line("Prélèvement ("+ctx["taux_prelevement"]+" %) : "+ctx["prelevement"]+" "+ctx["devise"])
    line("NET À PAYER : "+ctx["montant_net"]+" "+ctx["devise"],True,12)
    line("Imputation budgétaire : "+ctx["imputation"])
    y-=35;line(ctx["signataire_1"]+"                                     "+ctx["signataire_2"],True,10)
    pdf.save();return buf.getvalue()

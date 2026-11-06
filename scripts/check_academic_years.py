"""Read-only preflight checks for EduPilot academic-year rollover.

Usage inside the running application image:
  python /app/scripts/check_academic_years.py
"""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from app import app,one,allrows

ENDPOINTS=(
    'academic_years','academic_year_select','academic_year_create',
    'academic_year_copy','academic_year_copy_documents',
    'academic_year_promote','academic_year_activate',
)
TEMPLATES=('academic_years.html','base.html','list.html',
           'courses_manage.html','students.html','reports.html',
           'assessments.html','course_documents_index.html')


def check():
    routes={route.endpoint for route in app.url_map.iter_rules()}
    for name in ENDPOINTS:
        assert name in routes, f'Route manquante : {name}'
    print('Routes de rentrée :',len(ENDPOINTS),'OK')
    with app.app_context():
        for filename in TEMPLATES:
            app.jinja_env.get_template(filename)
        print('Modèles Jinja :',len(TEMPLATES),'OK')
        one('SELECT id,school_id,label,is_active,status,start_date,end_date,archived_at FROM years LIMIT 1')
        one('SELECT id,school_id,target_class_id FROM academic_year_class_copies LIMIT 1')
        one('SELECT id,school_id,decision FROM academic_year_promotions LIMIT 1')
        one('SELECT id,source_document_id FROM academic_year_document_copies LIMIT 1')
        print('Tables et colonnes : OK')
        duplicates=allrows("""SELECT school_id,COUNT(*) n FROM years
            WHERE is_active=1 GROUP BY school_id HAVING COUNT(*)>1""")
        assert not duplicates,'Plusieurs années actives pour un établissement'
        mismatches=allrows("""SELECT id FROM years WHERE (is_active=1 AND status<>'active')
                            OR (is_active=0 AND status='active')""")
        assert not mismatches,'Statut incohérent avec is_active'
        print('Unicité et statuts des années : OK')
        invalid_classes=allrows("""SELECT m.id FROM academic_year_class_copies m
            JOIN classes a ON a.id=m.source_class_id
            JOIN classes b ON b.id=m.target_class_id
            WHERE a.school_id<>m.school_id OR b.school_id<>m.school_id
               OR a.year_id<>m.source_year_id OR b.year_id<>m.target_year_id""")
        assert not invalid_classes,'Correspondance de classes incohérente'
        print('Correspondances de classes : OK')
    print('Vérification de rentrée scolaire : OK')


if __name__=='__main__':
    check()

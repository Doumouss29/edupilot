"""Read-only post-deployment checks for EduPilot pedagogical documents."""
from app import app, one, UPLOAD_DIR

ROUTES = (
    'course_documents_index',
    'course_documents',
    'course_documents_upload',
    'course_document_visibility',
    'course_document_delete',
    'course_document_file',
    'course_document_quota',
)
TEMPLATES = (
    'course_documents_index.html',
    'course_documents.html',
    'courses_manage.html',
    'student_maquette.html',
    'base.html',
)


def verify():
    with app.app_context():
        names={rule.endpoint for rule in app.url_map.iter_rules()}
        for endpoint in ROUTES:
            assert endpoint in names, f'Route manquante : {endpoint}'
            print('Route OK :', endpoint)
        for name in TEMPLATES:
            app.jinja_env.get_template(name)
            print('Modèle Jinja OK :', name)
        one('SELECT id,published,publish_at,bytes_size FROM course_documents LIMIT 1')
        one('SELECT school_id,quota_bytes FROM school_document_limits LIMIT 1')
        print('Tables et colonnes PostgreSQL/SQLite OK')
        print('Stockage monté :', UPLOAD_DIR)
    print('Vérification des documents pédagogiques : OK')


if __name__ == '__main__':
    verify()

"""EduPilot - application de demonstration multi-etablissements avec SQLite.
IMPORTANT: demo seulement, stockage Render Free ephemere.
"""
import os, sqlite3, secrets, unicodedata, re, json, datetime, calendar, functools, smtplib, csv, io
from openpyxl import load_workbook
from flask import Response
from contextlib import contextmanager
from pathlib import Path
import requests
from flask import Flask, request, redirect, url_for, render_template, flash, session, abort, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from flask import send_file

ROOT = Path(__file__).parent
app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY') or ('demo-local-only-secret' if os.getenv('EDUPILOT_DEMO', 'true') == 'true' else secrets.token_hex(32))
app.config['MAX_CONTENT_LENGTH'] = 12 * 1024 * 1024
DB = os.getenv('DATABASE_PATH', '/tmp/edupilot.db')
UPLOAD_DIR = Path(os.getenv('UPLOAD_DIR', '/tmp/edupilot_uploads'))
UPLOAD_DIR.mkdir(parents=True,exist_ok=True)

SCHEMA = """
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS schools(id INTEGER PRIMARY KEY, name TEXT NOT NULL, slug TEXT NOT NULL UNIQUE, plan TEXT NOT NULL DEFAULT 'standard', active INTEGER NOT NULL DEFAULT 1, subscription_end TEXT, logo BLOB, logo_mime TEXT);
CREATE TABLE IF NOT EXISTS campuses(id INTEGER PRIMARY KEY, school_id INTEGER NOT NULL REFERENCES schools(id), name TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, school_id INTEGER REFERENCES schools(id), name TEXT NOT NULL, email TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL, role TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1, first_name TEXT, last_name TEXT, phone TEXT, must_change_password INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS years(id INTEGER PRIMARY KEY, school_id INTEGER NOT NULL REFERENCES schools(id), label TEXT NOT NULL, is_active INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS classes(id INTEGER PRIMARY KEY, school_id INTEGER NOT NULL REFERENCES schools(id), year_id INTEGER NOT NULL REFERENCES years(id), campus_id INTEGER REFERENCES campuses(id), name TEXT NOT NULL, cycle TEXT NOT NULL DEFAULT 'semestre', parents_enabled INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS enrollments(id INTEGER PRIMARY KEY, school_id INTEGER NOT NULL REFERENCES schools(id), student_id INTEGER NOT NULL REFERENCES users(id), class_id INTEGER NOT NULL REFERENCES classes(id), year_id INTEGER NOT NULL REFERENCES years(id), status TEXT NOT NULL DEFAULT 'inscrit', UNIQUE(student_id,class_id,year_id));
CREATE TABLE IF NOT EXISTS parent_links(id INTEGER PRIMARY KEY, school_id INTEGER NOT NULL REFERENCES schools(id), student_id INTEGER NOT NULL REFERENCES users(id), parent_id INTEGER NOT NULL REFERENCES users(id), relation TEXT DEFAULT 'parent', active INTEGER NOT NULL DEFAULT 1, UNIQUE(student_id,parent_id));
CREATE TABLE IF NOT EXISTS courses(id INTEGER PRIMARY KEY, school_id INTEGER NOT NULL REFERENCES schools(id), class_id INTEGER NOT NULL REFERENCES classes(id), name TEXT NOT NULL, code TEXT NOT NULL, planned_minutes INTEGER NOT NULL DEFAULT 1200, teacher_id INTEGER REFERENCES users(id), coefficient REAL NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS teacher_history(id INTEGER PRIMARY KEY, course_id INTEGER NOT NULL REFERENCES courses(id), teacher_id INTEGER NOT NULL REFERENCES users(id), date_start TEXT NOT NULL, date_end TEXT);
CREATE TABLE IF NOT EXISTS lessons(id INTEGER PRIMARY KEY, school_id INTEGER NOT NULL REFERENCES schools(id), course_id INTEGER NOT NULL REFERENCES courses(id), teacher_id INTEGER NOT NULL REFERENCES users(id), starts_at TEXT NOT NULL, ends_at TEXT NOT NULL, room TEXT, status TEXT NOT NULL DEFAULT 'programmee', actual_minutes INTEGER NOT NULL DEFAULT 0, comment TEXT, validated INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS attendance(id INTEGER PRIMARY KEY, lesson_id INTEGER NOT NULL REFERENCES lessons(id), student_id INTEGER NOT NULL REFERENCES users(id), status TEXT NOT NULL, UNIQUE(lesson_id,student_id));
CREATE TABLE IF NOT EXISTS assessments(id INTEGER PRIMARY KEY, school_id INTEGER NOT NULL REFERENCES schools(id), course_id INTEGER NOT NULL REFERENCES courses(id), title TEXT NOT NULL, kind TEXT NOT NULL DEFAULT 'Devoir', due_date TEXT, coefficient REAL NOT NULL DEFAULT 1, max_score REAL NOT NULL DEFAULT 20, description TEXT, published INTEGER NOT NULL DEFAULT 1, attachment_name TEXT, attachment_blob BLOB, attachment_mime TEXT);
CREATE TABLE IF NOT EXISTS grades(id INTEGER PRIMARY KEY, assessment_id INTEGER NOT NULL REFERENCES assessments(id), student_id INTEGER NOT NULL REFERENCES users(id), value REAL NOT NULL, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, comment TEXT DEFAULT '', UNIQUE(assessment_id,student_id));
CREATE TABLE IF NOT EXISTS grade_history(id INTEGER PRIMARY KEY, grade_id INTEGER NOT NULL REFERENCES grades(id), old_value REAL, new_value REAL NOT NULL, actor_id INTEGER REFERENCES users(id), changed_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS periods(id INTEGER PRIMARY KEY, school_id INTEGER NOT NULL REFERENCES schools(id), class_id INTEGER NOT NULL REFERENCES classes(id), name TEXT NOT NULL, locked INTEGER NOT NULL DEFAULT 0, published INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS unlocks(id INTEGER PRIMARY KEY, period_id INTEGER NOT NULL REFERENCES periods(id), teacher_id INTEGER NOT NULL REFERENCES users(id), expires_at TEXT NOT NULL, reason TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS notifications(id INTEGER PRIMARY KEY, school_id INTEGER NOT NULL REFERENCES schools(id), user_id INTEGER NOT NULL REFERENCES users(id), message TEXT NOT NULL, href TEXT DEFAULT '', read INTEGER NOT NULL DEFAULT 0, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY, school_id INTEGER, user_id INTEGER, action TEXT NOT NULL, details TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS submissions(id INTEGER PRIMARY KEY, assessment_id INTEGER NOT NULL REFERENCES assessments(id), student_id INTEGER NOT NULL REFERENCES users(id), filename TEXT NOT NULL, filepath TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP, UNIQUE(assessment_id,student_id));
CREATE TABLE IF NOT EXISTS invites(id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id), token_hash TEXT NOT NULL, expires_at TEXT NOT NULL, used INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT NOT NULL);
"""

def connection():
    c=sqlite3.connect(DB,timeout=30)
    c.row_factory=sqlite3.Row
    c.execute('PRAGMA foreign_keys=ON')
    c.execute('PRAGMA busy_timeout=30000')
    return c

@contextmanager
def db():
    c=connection()
    try:
        yield c
        c.commit()
    except:
        c.rollback()
        raise
    finally:
        c.close()

def one(sql, args=()):
    with db() as c: return c.execute(sql,args).fetchone()

def allrows(sql,args=()):
    with db() as c: return c.execute(sql,args).fetchall()

def execute(sql,args=()):
    with db() as c:
        cur=c.execute(sql,args)
        return cur.lastrowid

def seed():
    if one('SELECT id FROM schools LIMIT 1'): return
    with db() as c:
        for name,slug,plan in [('Groupe Scolaire Excellence','groupe_scolaire_excellence','premium'),('Université de Bouaké Démo','universite_de_bouake','standard')]:
            school=c.execute('INSERT INTO schools(name,slug,plan) VALUES (?,?,?)',(name,slug,plan)).lastrowid
            campus=c.execute('INSERT INTO campuses(school_id,name) VALUES (?,?)',(school,'Campus principal')).lastrowid
            year=c.execute('INSERT INTO years(school_id,label) VALUES (?,?)',(school,'2026-2027')).lastrowid
            cls=c.execute('INSERT INTO classes(school_id,year_id,campus_id,name,cycle,parents_enabled) VALUES (?,?,?,?,?,?)',(school,year,campus,'Terminale D' if school==1 else 'Master 1 Géomatique','trimestre' if school==1 else 'semestre',1)).lastrowid
            def u(name,email,role):
                return c.execute('INSERT INTO users(school_id,name,email,password_hash,role) VALUES (?,?,?,?,?)',(school,name,email,generate_password_hash('Demo2026!'),role)).lastrowid
            admin=u('Admin établissement',f'admin{school}@demo.edupilot.test','admin')
            staff=u('Secrétariat',f'scolarite{school}@demo.edupilot.test','administratif')
            teacher=u('Enseignant démo',f'enseignant{school}@demo.edupilot.test','enseignant')
            students=[u(f'Élève {i}',f'eleve{school}_{i}@demo.edupilot.test','etudiant') for i in range(1,9)]
            parent=u('Parent démo',f'parent{school}@demo.edupilot.test','parent')
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
        c.execute('INSERT INTO users(school_id,name,email,password_hash,role) VALUES (NULL,?,?,?,?)',('Éditeur EduPilot','superadmin@demo.edupilot.test',generate_password_hash('Demo2026!'),'superadmin'))

Path(DB).parent.mkdir(parents=True,exist_ok=True)
with db() as c:
    c.executescript(SCHEMA)
    existing={r['name'] for r in c.execute('PRAGMA table_info(schools)').fetchall()}
    for name,definition in [('subscription_end','TEXT'),('logo','BLOB'),('logo_mime','TEXT')]:
        if name not in existing: c.execute(f'ALTER TABLE schools ADD COLUMN {name} {definition}')
    columns={r['name'] for r in c.execute('PRAGMA table_info(users)').fetchall()}
    for name,definition in [('first_name','TEXT'),('last_name','TEXT'),('phone','TEXT'),('must_change_password','INTEGER NOT NULL DEFAULT 0')]:
        if name not in columns:c.execute(f'ALTER TABLE users ADD COLUMN {name} {definition}')
    for table, additions in {'courses':[('coefficient','REAL NOT NULL DEFAULT 1')],
        'assessments':[('attachment_name','TEXT'),('attachment_blob','BLOB'),('attachment_mime','TEXT')],
        'grades':[('comment', "TEXT DEFAULT ''")]}.items():
        existing_columns={x['name'] for x in c.execute(f'PRAGMA table_info({table})')}
        for column,definition in additions:
            if column not in existing_columns:c.execute(f'ALTER TABLE {table} ADD COLUMN {column} {definition}')
    c.execute("INSERT OR IGNORE INTO settings(key,value) VALUES ('support_name','LMurbs')")
    c.execute("INSERT OR IGNORE INTO settings(key,value) VALUES ('support_phone','+2250711124359')")
    c.execute("INSERT OR IGNORE INTO settings(key,value) VALUES ('powered_by','Propulsé par LMurbs')")
seed()

def setting(key,default=''):
    row=one('SELECT value FROM settings WHERE key=?',(key,))
    return row['value'] if row else default

def subscription_blocked(user=None):
    user=user or current_user()
    if not user or user['role']=='superadmin' or not user['school_id']:return False
    school=one('SELECT active,subscription_end FROM schools WHERE id=?',(user['school_id'],))
    if not school:return True
    return not school['active'] or bool(school['subscription_end'] and school['subscription_end']<=datetime.date.today().isoformat())

def read_logo(file):
    if not file or not file.filename:return None,None
    raw=file.read(1024*1024+1)
    if not raw:return None,None
    if len(raw)>1024*1024:abort(400,'Logo supérieur à 1 Mo.')
    if raw.startswith(b'\x89PNG\r\n\x1a\n'):mime='image/png'
    elif raw[:3]==b'\xff\xd8\xff':mime='image/jpeg'
    elif raw[:4]==b'RIFF' and raw[8:12]==b'WEBP':mime='image/webp'
    else:abort(400,'Format de logo non reconnu.')
    return raw,mime

@app.get('/school-logo/<int:sid>')
def school_logo(sid):
    row=one('SELECT logo,logo_mime FROM schools WHERE id=?',(sid,))
    if not row or not row['logo']:abort(404)
    resp=Response(row['logo'],mimetype=row['logo_mime'])
    resp.headers['X-Content-Type-Options']='nosniff'
    resp.headers['Cache-Control']='public, max-age=300'
    return resp


@app.before_request
def safety():
    if request.method=='POST':
        token=request.form.get('csrf','') or request.headers.get('X-CSRF-Token','')
        if token!=session.get('csrf') or not token: abort(400,'Jeton CSRF invalide')
    if 'csrf' not in session: session['csrf']=secrets.token_urlsafe(24)
    u=current_user()
    if u and subscription_blocked(u) and request.endpoint not in ('restricted','logout','login','health','school_logo','static'):
        return redirect(url_for('restricted'))
    if u and u['must_change_password'] and request.endpoint not in ('change_password','logout','restricted','health','school_logo','static'):
        return redirect(url_for('change_password'))

@app.context_processor
def globals_template():
    return dict(me=current_user(),csrf=session.get('csrf',''),appname='EduPilot',support_name=setting('support_name','LMurbs'),support_phone=setting('support_phone','+2250711124359'),powered_by=setting('powered_by','Propulsé par LMurbs'),school_brand=one('SELECT id,name,logo_mime FROM schools WHERE id=?',(school_id(),)) if school_id() else None)

def current_user():
    uid=session.get('uid')
    return one('SELECT * FROM users WHERE id=? AND active=1',(uid,)) if uid else None

def login_required(fn):
    @functools.wraps(fn)
    def wrap(*args,**kwargs):
        if not current_user(): return redirect(url_for('login'))
        return fn(*args,**kwargs)
    return wrap

def roles(*allowed):
    def decorator(fn):
        @functools.wraps(fn)
        @login_required
        def wrap(*args,**kwargs):
            if current_user()['role'] not in allowed: abort(403)
            return fn(*args,**kwargs)
        return wrap
    return decorator

def school_id():
    u=current_user()
    return u['school_id'] if u else None

def scoped(sql,args=()):
    return allrows(sql,(school_id(),)+tuple(args))

def has_school(table,obj_id):
    return one(f'SELECT id FROM {table} WHERE school_id=? AND id=?',(school_id(),obj_id))

def audit(action,details=''):
    u=current_user()
    execute('INSERT INTO audit(school_id,user_id,action,details) VALUES (?,?,?,?)',(u['school_id'],u['id'],action,details))

def notify(ids,message,href=''):
    for uid in set(ids):
        execute('INSERT INTO notifications(school_id,user_id,message,href) VALUES (?,?,?,?)',(school_id(),uid,message,href))
    api_key=os.getenv('BREVO_API_KEY')
    sender=os.getenv('BREVO_SENDER_EMAIL')
    if api_key and sender:
        for uid in set(ids):
            user=one('SELECT email FROM users WHERE id=? AND school_id=?',(uid,school_id()))
            if not user: continue
            try:
                requests.post('https://api.brevo.com/v3/smtp/email',json={'sender':{'email':sender,'name':os.getenv('BREVO_SENDER_NAME','EduPilot')},'to':[{'email':user['email']}],'subject':'Notification EduPilot','textContent':message},headers={'api-key':api_key,'Content-Type':'application/json'},timeout=6).raise_for_status()
            except Exception as e:
                app.logger.warning('Échec envoi courriel: %s',type(e).__name__)

def classmates(course_id):
    return [r['student_id'] for r in scoped('SELECT e.student_id FROM enrollments e JOIN courses c ON c.class_id=e.class_id WHERE e.school_id=? AND c.id=?',(course_id,))]

def slugify(s):
    s=unicodedata.normalize('NFKD',s).encode('ascii','ignore').decode().lower()
    return re.sub(r'^_+|_+$','',re.sub(r'[^a-z0-9]+','_',s))

@app.get('/health')
def health():return {'status':'ok','application':'EduPilot'}

@app.get('/<slug>')
@app.get('/<slug>/login')
def tenant_login(slug):
    school=one('SELECT id,name,slug,logo_mime FROM schools WHERE slug=?',(slug,))
    if not school:abort(404)
    return render_template('login.html',login_school=school,login_action=url_for('tenant_signin',slug=slug))

@app.post('/<slug>/login')
def tenant_signin(slug):
    school=one('SELECT id,name,slug,logo_mime FROM schools WHERE slug=?',(slug,))
    if not school:abort(404)
    return handle_login(school)

def handle_login(school=None):
    email=request.form.get('email','').strip().lower()
    u=one('SELECT * FROM users WHERE email=? AND active=1',(email,))
    if u and check_password_hash(u['password_hash'],request.form.get('password','')) and (school is None or (u['school_id']==school['id'] and u['role']!='superadmin')):
        session.clear()
        session['uid']=u['id']
        session['csrf']=secrets.token_urlsafe(24)
        if u['must_change_password']:return redirect(url_for('change_password'))
        return redirect(url_for('dashboard'))
    flash('Identifiants incorrects.','error')
    if school:return redirect(url_for('tenant_login',slug=school['slug']))
    return redirect(url_for('login'))

@app.route('/login',methods=['GET','POST'])
def login():
    if request.method=='POST':return handle_login()
    return render_template('login.html',login_school=None,login_action=url_for('login'))

@app.route('/change-password',methods=['GET','POST'])
@login_required
def change_password():
    u=current_user()
    if request.method=='POST':
        old=request.form.get('old_password','')
        new=request.form.get('new_password','')
        confirm=request.form.get('confirm_password','')
        if not check_password_hash(u['password_hash'],old):
            flash('Mot de passe temporaire incorrect.','error')
        elif len(new)<12 or not any(x.isalpha() for x in new) or not any(x.isdigit() for x in new):
            flash('Choisissez au moins 12 caractères, avec des lettres et des chiffres.','error')
        elif new!=confirm:
            flash('Les nouveaux mots de passe sont différents.','error')
        elif new==old:
            flash('Le nouveau mot de passe doit être différent.','error')
        else:
            execute('UPDATE users SET password_hash=?, must_change_password=0 WHERE id=?',(generate_password_hash(new),u['id']))
            session.clear()
            flash('Mot de passe modifié. Connectez-vous avec votre nouveau mot de passe.','success')
            return redirect(url_for('login'))
    return render_template('change_password.html')

@app.get('/restricted')
@login_required
def restricted():
    if not subscription_blocked():return redirect(url_for('dashboard'))
    return render_template('restricted.html')

@app.post('/logout')
def logout():session.clear();return redirect(url_for('login'))

@app.get('/')
@login_required
def dashboard():
    u=current_user()
    if u['role']=='superadmin':
        schools=allrows('SELECT s.*, (SELECT COUNT(*) FROM users u WHERE u.school_id=s.id) members FROM schools s')
        return render_template('dashboard.html',schools=schools,stats=None,classes=[],events=[],today=datetime.date.today().isoformat(),base_url=os.getenv('PUBLIC_BASE_URL',request.host_url.rstrip('/')).rstrip('/'))
    if u['role']=='etudiant':
        # Week selection is server-side and restricted to this student's own enrollments.
        ref=request.args.get('week','')
        try:
            today=datetime.date.fromisoformat(ref) if ref else datetime.date.today()
        except ValueError:
            today=datetime.date.today()
        monday=today-datetime.timedelta(days=today.weekday())
        sunday=monday+datetime.timedelta(days=7)
        week_start=monday.isoformat()
        week_end=sunday.isoformat()
        lessons=allrows("""SELECT l.id,l.starts_at,l.ends_at,l.room,l.status,c.name course_name,cl.name class_name
                         FROM lessons l JOIN courses c ON c.id=l.course_id
                         JOIN classes cl ON cl.id=c.class_id
                         WHERE l.school_id=? AND l.starts_at>=? AND l.starts_at<?
                         AND EXISTS (SELECT 1 FROM enrollments e
                           WHERE e.school_id=l.school_id AND e.student_id=? AND e.class_id=c.class_id)
                         ORDER BY l.starts_at,c.name""",(u['school_id'],week_start,week_end,u['id']))
        week_days=[{'date':monday+datetime.timedelta(days=n),'lessons':[]} for n in range(7)]
        for item in lessons:
            index=datetime.date.fromisoformat(item['starts_at'][:10]).weekday()
            week_days[index]['lessons'].append(item)
        return render_template('dashboard_student.html',week_days=week_days,
                               monday=monday,prev_week=(monday-datetime.timedelta(days=7)).isoformat(),
                               next_week=(monday+datetime.timedelta(days=7)).isoformat(),
                               week_end=monday+datetime.timedelta(days=6),lesson_count=len(lessons))
    if u['role']=='parent':
        return render_template('dashboard.html',stats={'classes':0,'courses':0,'lessons':0,'total':0,'actual':0,'percent':0},classes=[],events=[],courses=[],schools=[])
    sid=school_id()
    classes=scoped('SELECT * FROM classes WHERE school_id=?')
    courses=scoped('SELECT c.*,cl.name class_name,u.name teacher_name FROM courses c JOIN classes cl ON cl.id=c.class_id LEFT JOIN users u ON u.id=c.teacher_id WHERE c.school_id=?')
    if u['role']=='enseignant': courses=[x for x in courses if x['teacher_id']==u['id']]
    lessonlist=scoped('SELECT l.*,c.name course_name,cl.name class_name FROM lessons l JOIN courses c ON c.id=l.course_id JOIN classes cl ON cl.id=c.class_id WHERE l.school_id=? ORDER BY l.starts_at DESC LIMIT 80')
    if u['role']=='enseignant': lessonlist=[x for x in lessonlist if any(y['id']==x['course_id'] for y in courses)]
    total=sum(x['planned_minutes'] for x in courses)
    actual=sum(x['actual_minutes'] for x in lessonlist if x['status'] in ('realisee','partielle'))
    stats={'classes':len(classes),'courses':len(courses),'lessons':len(lessonlist),'total':total//60,'actual':round(actual/60,1),'percent':round(actual/total*100,1) if total else 0}
    return render_template('dashboard.html',stats=stats,classes=classes,events=lessonlist,schools=[],courses=courses)

@app.get('/schools')
@roles('superadmin')
def schools():
    records=allrows('SELECT id,name,slug,plan,active,subscription_end,logo_mime FROM schools ORDER BY id DESC')
    counts=allrows("SELECT school_id,COUNT(*) n FROM users WHERE role IN ('admin','administratif') GROUP BY school_id")
    account_counts={r['school_id']:r['n'] for r in counts}
    admins=allrows("SELECT school_id,first_name,last_name,name,email,phone,role,active,must_change_password FROM users WHERE role IN ('admin','administratif') ORDER BY id DESC")
    return render_template('schools.html',schools=records,admin_accounts=admins,account_counts=account_counts,today=datetime.date.today().isoformat(),base_url=os.getenv('PUBLIC_BASE_URL',request.host_url.rstrip('/')).rstrip('/'))

@app.route('/schools/new',methods=['GET','POST'])
@roles('superadmin')
def school_new():
    if request.method=='GET':return render_template('school_new.html')
    name=request.form.get('name','').strip()
    if not name:abort(400)
    end=request.form.get('subscription_end','').strip() or None
    if end:
        try:datetime.date.fromisoformat(end)
        except ValueError:abort(400)
    plan=request.form.get('plan','standard')
    if plan not in ('essentiel','standard','premium'):abort(400)
    slug=slugify(name)
    if not slug:abort(400)
    n=2;unique=slug
    while one('SELECT id FROM schools WHERE slug=?',(unique,)):
        unique=slug+'_'+str(n);n+=1
    logo,mime=read_logo(request.files.get('logo'))
    with db() as c:
        sid=c.execute('INSERT INTO schools(name,slug,plan,subscription_end,logo,logo_mime) VALUES (?,?,?,?,?,?)',(name,unique,plan,end,logo,mime)).lastrowid
        c.execute('INSERT INTO years(school_id,label) VALUES (?,?)',(sid,'2026-2027'))
        c.execute('INSERT INTO campuses(school_id,name) VALUES (?,?)',(sid,'Campus principal'))
    flash('Établissement créé. Créez maintenant ses comptes administrateurs.','success')
    return redirect(url_for('school_accounts',sid=sid))

@app.route('/schools/<int:sid>/accounts',methods=['GET','POST'])
@roles('superadmin')
def school_accounts(sid):
    school=one('SELECT id,name,slug,logo_mime,plan,active,subscription_end FROM schools WHERE id=?',(sid,))
    if not school:abort(404)
    if request.method=='POST':
        first=request.form.get('first_name','').strip()
        last=request.form.get('last_name','').strip()
        email=request.form.get('email','').strip().lower()
        phone=request.form.get('phone','').strip()
        role=request.form.get('role','')
        password=request.form.get('password','')
        if not first or not last or not phone or not email or not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',email):abort(400,'Informations obligatoires manquantes')
        if len(first)>90 or len(last)>90 or len(phone)>40 or len(email)>254:abort(400)
        if role not in ('admin','administratif'):abort(400)
        if len(password)<12 or not any(c.isalpha() for c in password) or not any(c.isdigit() for c in password):
            abort(400,'Mot de passe temporaire non conforme')
        if one('SELECT id FROM users WHERE email=?',(email,)):
            flash('Cette adresse e-mail est déjà utilisée.','error')
        else:
            execute('INSERT INTO users(school_id,name,first_name,last_name,email,phone,password_hash,role,must_change_password) VALUES (?,?,?,?,?,?,?,?,1)',(sid,first+' '+last,first,last,email,phone,generate_password_hash(password),role))
            flash('Compte créé. Transmettez le mot de passe temporaire au destinataire par un canal sécurisé.','success')
            return redirect(url_for('school_accounts',sid=sid))
    accounts=allrows("SELECT id,first_name,last_name,name,email,phone,role,active,must_change_password FROM users WHERE school_id=? AND role IN ('admin','administratif') ORDER BY id DESC",(sid,))
    return render_template('school_accounts.html',school=school,accounts=accounts,base_url=os.getenv('PUBLIC_BASE_URL',request.host_url.rstrip('/')).rstrip('/'))

@app.route('/schools/<int:sid>/accounts/<int:uid>/edit',methods=['GET','POST'])
@roles('superadmin')
def school_account_edit(sid,uid):
    school=one('SELECT id,name,slug FROM schools WHERE id=?',(sid,))
    account=one("SELECT * FROM users WHERE id=? AND school_id=? AND role IN ('admin','administratif')",(uid,sid))
    if not school or not account:abort(404)
    if request.method=='POST':
        first=request.form.get('first_name','').strip()
        last=request.form.get('last_name','').strip()
        email=request.form.get('email','').strip().lower()
        phone=request.form.get('phone','').strip()
        role=request.form.get('role','')
        if not first or not last or not phone or not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',email):abort(400)
        if len(first)>90 or len(last)>90 or len(phone)>40 or len(email)>254 or role not in ('admin','administratif'):abort(400)
        duplicate=one('SELECT id FROM users WHERE email=? AND id<>?',(email,uid))
        if duplicate:
            flash('Adresse e-mail déjà utilisée.','error')
            return redirect(url_for('school_account_edit',sid=sid,uid=uid))
        reset=request.form.get('temporary_password','')
        if reset and (len(reset)<12 or not any(ch.isalpha() for ch in reset) or not any(ch.isdigit() for ch in reset)):
            flash('Le mot de passe temporaire doit avoir au moins 12 caractères, avec lettres et chiffres.','error')
            return redirect(url_for('school_account_edit',sid=sid,uid=uid))
        with db() as c:
            c.execute('UPDATE users SET name=?,first_name=?,last_name=?,email=?,phone=?,role=? WHERE id=? AND school_id=?',
                      (first+' '+last,first,last,email,phone,role,uid,sid))
            if reset:
                c.execute('UPDATE users SET password_hash=?,must_change_password=1 WHERE id=? AND school_id=?',
                          (generate_password_hash(reset),uid,sid))
            c.execute('INSERT INTO audit(school_id,user_id,action,details) VALUES (?,?,?,?)',
                      (sid,current_user()['id'],'account.updated',str(uid)))
        flash('Compte modifié avec succès.','success')
        return redirect(url_for('school_accounts',sid=sid))
    return render_template('school_account_edit.html',school=school,account=account)

@app.post('/schools/<int:sid>/accounts/bulk')
@roles('superadmin')
def school_accounts_bulk(sid):
    school=one('SELECT id,name FROM schools WHERE id=?',(sid,))
    if not school:abort(404)
    values=request.form.getlist('account_ids')
    action=request.form.get('action','')
    if action not in ('suspend','activate','delete','set_admin','set_administratif') or not values or len(values)>100 or any(not v.isdigit() for v in values):
        flash('Sélectionnez des comptes et une action.','error')
        return redirect(url_for('school_accounts',sid=sid))
    ids=list(dict.fromkeys(int(v) for v in values))
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        placeholders=','.join('?' for _ in ids)
        accounts=c.execute(f"SELECT id FROM users WHERE school_id=? AND role IN ('admin','administratif') AND id IN ({placeholders})",(sid,*ids)).fetchall()
        if len(accounts)!=len(ids):abort(403)
        if action=='delete':
            # Historical accounts must be suspended, not deleted: protect academic data and traceability.
            dependencies=(
                ('enrollments','student_id'),('parent_links','student_id'),('parent_links','parent_id'),
                ('courses','teacher_id'),('lessons','teacher_id'),('teacher_history','teacher_id'),
                ('grades','student_id'),('grade_history','actor_id'),
                ('attendance','student_id'),('submissions','student_id'),('unlocks','teacher_id'),
            )
            for uid in ids:
                for table,col in dependencies:
                    if c.execute(f'SELECT 1 FROM {table} WHERE {col}=? LIMIT 1',(uid,)).fetchone():
                        flash('Suppression refusée : certains comptes sont liés à des données scolaires. Vous pouvez les suspendre.','error')
                        return redirect(url_for('school_accounts',sid=sid))
            for uid in ids:
                c.execute('DELETE FROM invites WHERE user_id=?',(uid,))
                c.execute('DELETE FROM notifications WHERE user_id=?',(uid,))
                c.execute('UPDATE audit SET user_id=NULL WHERE user_id=?',(uid,))
            c.execute(f"DELETE FROM users WHERE school_id=? AND id IN ({placeholders})",(sid,*ids))
        elif action in ('activate','suspend'):
            c.execute(f"UPDATE users SET active=? WHERE school_id=? AND id IN ({placeholders})",
                      (1 if action=='activate' else 0,sid,*ids))
        else:
            role='admin' if action=='set_admin' else 'administratif'
            c.execute(f"UPDATE users SET role=? WHERE school_id=? AND id IN ({placeholders})",(role,sid,*ids))
        c.execute('INSERT INTO audit(school_id,user_id,action,details) VALUES (?,?,?,?)',
                  (sid,current_user()['id'],'accounts.'+action,','.join(str(v) for v in ids)))
    flash(f'{len(ids)} compte(s) : modification enregistrée.','success')
    return redirect(url_for('school_accounts',sid=sid))

@app.post('/schools/<int:sid>/update')
@roles('superadmin')
def school_update(sid):
    school=one('SELECT * FROM schools WHERE id=?',(sid,))
    if not school:abort(404)
    action=request.form.get('action','update')
    if action=='delete':
        if request.form.get('confirm_slug')!=school['slug']:abort(400,'Confirmation requise.')
        with db() as c:
            c.execute('BEGIN IMMEDIATE')
            c.execute('DELETE FROM attendance WHERE lesson_id IN (SELECT id FROM lessons WHERE school_id=?)',(sid,))
            c.execute('DELETE FROM submissions WHERE assessment_id IN (SELECT id FROM assessments WHERE school_id=?)',(sid,))
            c.execute('DELETE FROM grade_history WHERE grade_id IN (SELECT g.id FROM grades g JOIN assessments a ON a.id=g.assessment_id WHERE a.school_id=?)',(sid,))
            c.execute('DELETE FROM grades WHERE assessment_id IN (SELECT id FROM assessments WHERE school_id=?)',(sid,))
            c.execute('DELETE FROM assessments WHERE school_id=?',(sid,))
            c.execute('DELETE FROM unlocks WHERE period_id IN (SELECT id FROM periods WHERE school_id=?)',(sid,))
            c.execute('DELETE FROM periods WHERE school_id=?',(sid,))
            c.execute('DELETE FROM lessons WHERE school_id=?',(sid,))
            c.execute('DELETE FROM teacher_history WHERE course_id IN (SELECT id FROM courses WHERE school_id=?)',(sid,))
            c.execute('DELETE FROM courses WHERE school_id=?',(sid,))
            c.execute('DELETE FROM enrollments WHERE school_id=?',(sid,))
            c.execute('DELETE FROM parent_links WHERE school_id=?',(sid,))
            c.execute('DELETE FROM classes WHERE school_id=?',(sid,))
            c.execute('DELETE FROM years WHERE school_id=?',(sid,))
            c.execute('DELETE FROM campuses WHERE school_id=?',(sid,))
            c.execute('DELETE FROM notifications WHERE school_id=?',(sid,))
            c.execute('DELETE FROM audit WHERE school_id=?',(sid,))
            c.execute('DELETE FROM invites WHERE user_id IN (SELECT id FROM users WHERE school_id=?)',(sid,))
            c.execute('DELETE FROM users WHERE school_id=?',(sid,))
            c.execute('DELETE FROM schools WHERE id=?',(sid,))
        flash('Établissement et données associés supprimés définitivement.','success')
    elif action in ('activate','deactivate'):
        execute('UPDATE schools SET active=? WHERE id=?',(1 if action=='activate' else 0,sid))
        flash('Statut de l’établissement mis à jour.','success')
    elif action=='update':
        end=request.form.get('subscription_end','').strip() or None
        if end:
            try:datetime.date.fromisoformat(end)
            except ValueError:abort(400)
        plan=request.form.get('plan',school['plan'])
        if plan not in ('essentiel','standard','premium'):abort(400)
        logo,mime=read_logo(request.files.get('logo'))
        if logo:execute('UPDATE schools SET plan=?,subscription_end=?,logo=?,logo_mime=? WHERE id=?',(plan,end,logo,mime,sid))
        elif request.form.get('remove_logo')=='1':execute('UPDATE schools SET plan=?,subscription_end=?,logo=NULL,logo_mime=NULL WHERE id=?',(plan,end,sid))
        else:execute('UPDATE schools SET plan=?,subscription_end=? WHERE id=?',(plan,end,sid))
        flash('Paramètres de l’établissement enregistrés.','success')
    else:abort(400)
    return redirect(url_for('schools'))

@app.route('/settings',methods=['GET','POST'])
@roles('superadmin')
def settings():
    if request.method=='POST':
        name=request.form.get('support_name','').strip()
        phone=request.form.get('support_phone','').strip()
        powered=request.form.get('powered_by','').strip()
        if not name or not phone or not powered or len(name)>120 or len(phone)>40 or len(powered)>180:abort(400)
        with db() as c:
            for k,v in [('support_name',name),('support_phone',phone),('powered_by',powered)]:
                c.execute('INSERT INTO settings(key,value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',(k,v))
        flash('Coordonnées du support mises à jour.','success')
        return redirect(url_for('settings'))
    return render_template('settings.html')

def assign_courses_to_teacher(teacher_id, course_ids):
    """Assign several existing course offerings, retaining teacher history."""
    wanted=list(dict.fromkeys(int(x) for x in course_ids if str(x).isdigit()))
    if len(wanted)>100:abort(400,'Trop de cours sélectionnés')
    if not wanted:return
    marker=','.join('?' for _ in wanted)
    matches=allrows(f'SELECT id,teacher_id FROM courses WHERE school_id=? AND id IN ({marker})',(school_id(),*wanted))
    if len(matches)!=len(wanted):abort(403,'Cours en dehors de votre établissement')
    now=datetime.datetime.now(datetime.timezone.utc).isoformat()
    with db() as c:
        for course in matches:
            if course['teacher_id']==teacher_id:continue
            if course['teacher_id']:
                c.execute('UPDATE teacher_history SET date_end=? WHERE course_id=? AND date_end IS NULL',(now,course['id']))
            c.execute('UPDATE courses SET teacher_id=? WHERE id=?',(teacher_id,course['id']))
            c.execute('INSERT INTO teacher_history(course_id,teacher_id,date_start) VALUES (?,?,?)',(course['id'],teacher_id,now))

@app.route('/people',methods=['GET','POST'])
@roles('admin','administratif')
def people():
    if request.method=='POST':
        role=request.form.get('role','etudiant')
        if role not in ('etudiant','enseignant','parent','administratif'):abort(400)
        name=request.form.get('name','').strip()
        email=request.form.get('email','').strip().lower()
        if not name or not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',email):abort(400)
        class_id=request.form.get('class_id','').strip()
        if role=='etudiant':
            if not class_id or not has_school('classes',class_id):
                flash('Sélectionnez une classe de votre établissement.','error')
                return redirect(url_for('people'))
        elif class_id:abort(400,'Seuls les étudiants peuvent être inscrits dans une classe depuis ce formulaire')
        course_ids=request.form.getlist('course_ids') if role=='enseignant' else []
        if course_ids:
            if any(not str(v).isdigit() for v in course_ids):abort(400)
            vals=list(dict.fromkeys(int(v) for v in course_ids))
            clause=','.join('?' for _ in vals)
            selected=allrows(f'SELECT id FROM courses WHERE school_id=? AND id IN ({clause})',(school_id(),*vals))
            if len(selected)!=len(vals):abort(403)
        password=request.form.get('password','')
        if len(password)<12 or not any(x.isalpha() for x in password) or not any(x.isdigit() for x in password):
            flash('Mot de passe temporaire : 12 caractères minimum, avec des lettres et des chiffres.','error')
            return redirect(url_for('people'))
        with db() as c:
            if c.execute('SELECT id FROM users WHERE email=?',(email,)).fetchone():
                flash('Adresse e-mail déjà utilisée.','error')
                return redirect(url_for('people'))
            uid=c.execute('INSERT INTO users(school_id,name,email,password_hash,role,must_change_password) VALUES (?,?,?,?,?,1)',(school_id(),name,email,generate_password_hash(password),role)).lastrowid
            if role=='etudiant':
                clazz=c.execute('SELECT year_id FROM classes WHERE school_id=? AND id=?',(school_id(),class_id)).fetchone()
                if not clazz:abort(403)
                c.execute('INSERT INTO enrollments(school_id,student_id,class_id,year_id) VALUES (?,?,?,?)',(school_id(),uid,int(class_id),clazz['year_id']))
        if course_ids:assign_courses_to_teacher(uid,course_ids)
        audit('person.created',email)
        flash('Utilisateur créé. Communiquez son mot de passe temporaire par un canal sécurisé.','success')
        return redirect(url_for('people'))
    users=scoped('SELECT * FROM users WHERE school_id=? ORDER BY role,name')
    classes=scoped('SELECT id,name FROM classes WHERE school_id=? ORDER BY name')
    courses=scoped('SELECT c.id,c.name,cl.name class_name FROM courses c JOIN classes cl ON cl.id=c.class_id WHERE c.school_id=? ORDER BY cl.name,c.name')
    rows=allrows("""SELECT u.id,u.name,u.email,u.role,u.active,u.must_change_password,
                     GROUP_CONCAT(DISTINCT cl.name) class_names,
                     (SELECT GROUP_CONCAT(c.name||' ('||cl2.name||')',', ') FROM courses c JOIN classes cl2 ON cl2.id=c.class_id WHERE c.teacher_id=u.id AND c.school_id=u.school_id) teacher_courses
                  FROM users u LEFT JOIN enrollments e ON e.student_id=u.id AND e.school_id=u.school_id
                  LEFT JOIN classes cl ON cl.id=e.class_id
                  WHERE u.school_id=? GROUP BY u.id ORDER BY u.role,u.name""",(school_id(),))
    return render_template('list.html',title='Utilisateurs',columns=['Nom','E-mail','Profil','Classe / cours attribués'],rows=[(x['name'],x['email'],x['role'],x['class_names'] if x['role']=='etudiant' else x['teacher_courses'] or '—') for x in rows],form='people',classes=classes,courses=courses,user_rows=rows)

@app.post('/people/bulk')
@roles('admin','administratif')
def people_bulk():
    values=request.form.getlist('user_ids')
    action=request.form.get('action','')
    if action not in ('suspend','activate','delete') or not values or len(values)>200 or any(not x.isdigit() for x in values):
        flash('Sélectionnez des utilisateurs et une action valide.','error')
        return redirect(url_for('people'))
    selected=list(dict.fromkeys(int(x) for x in values))
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        users=c.execute('SELECT id,role,name FROM users WHERE school_id=? AND id IN ('+','.join('?' for _ in selected)+')',(school_id(),*selected)).fetchall()
        if len(users)!=len(selected) or current_user()['id'] in selected or any(x['role']=='superadmin' for x in users):
            abort(403)
        if action=='delete':
            # Keep grades, attendance, teacher assignments and audited academic history intact.
            for user in users:
                uid=user['id']
                linked=any(c.execute('SELECT 1 FROM '+sql+' LIMIT 1',(uid,)).fetchone() for sql in [
                    'grades WHERE student_id=?','attendance WHERE student_id=?','submissions WHERE student_id=?',
                    'courses WHERE teacher_id=?','lessons WHERE teacher_id=?','teacher_history WHERE teacher_id=?',
                    'grade_history WHERE actor_id=?','unlocks WHERE teacher_id=?'])
                if linked:
                    flash('Suppression refusée : un compte possède des notes, séances ou affectations historisées. Suspendez-le pour préserver les dossiers.','error')
                    return redirect(url_for('people'))
            for user in users:
                uid=user['id']
                c.execute('DELETE FROM parent_links WHERE student_id=? OR parent_id=?',(uid,uid))
                c.execute('DELETE FROM enrollments WHERE student_id=?',(uid,))
                c.execute('DELETE FROM notifications WHERE user_id=?',(uid,))
                c.execute('DELETE FROM invites WHERE user_id=?',(uid,))
                c.execute('UPDATE audit SET user_id=NULL WHERE user_id=?',(uid,))
                c.execute('DELETE FROM users WHERE id=? AND school_id=?',(uid,school_id()))
        else:
            c.execute('UPDATE users SET active=? WHERE school_id=? AND id IN ('+','.join('?' for _ in selected)+')',(1 if action=='activate' else 0,school_id(),*selected))
    audit('users.'+action,','.join(str(x) for x in selected))
    flash(f'{len(selected)} utilisateur(s) : action « {action} » appliquée.','success')
    return redirect(url_for('people'))

@app.get('/people/import/template')
@roles('admin','administratif')
def students_csv_template():
    csv_data='\ufeffprenom;nom;email;classe\nAmadou;Traore;amadou.exemple@example.test;Licence 1\n'
    return Response(csv_data,mimetype='text/csv; charset=utf-8',headers={'Content-Disposition':'attachment; filename=edupilot-modele-etudiants.csv'})

@app.post('/people/import')
@roles('admin','administratif')
def people_import():
    uploaded=request.files.get('file')
    if not uploaded or not uploaded.filename:abort(400,'Fichier obligatoire')
    filename=uploaded.filename.lower()
    if not filename.endswith(('.csv','.xlsx')):abort(400,'Format CSV ou XLSX uniquement')
    content=uploaded.read(2*1024*1024+1)
    if len(content)>2*1024*1024:abort(400,'Limite de 2 Mo')
    try:
        if filename.endswith('.csv'):
            text=content.decode('utf-8-sig')
            dialect=csv.Sniffer().sniff(text[:2048],delimiters=',;\t') if text.strip() else csv.excel
            rows=list(csv.reader(io.StringIO(text),dialect))
        else:
            workbook=load_workbook(io.BytesIO(content),read_only=True,data_only=True)
            sheet=workbook.active
            rows=list(sheet.iter_rows(values_only=True,max_row=2002))
            workbook.close()
    except Exception as exc:
        app.logger.info('Invalid student import file: %s',type(exc).__name__)
        flash('Impossible de lire le fichier : utilisez un CSV UTF-8 ou un Excel XLSX valide.','error')
        return redirect(url_for('people'))
    if len(rows)<2:
        flash('Le fichier doit contenir un en-tête et au moins un étudiant.','error')
        return redirect(url_for('people'))
    if len(rows)>2001:
        flash('Maximum 2 000 étudiants par import.','error')
        return redirect(url_for('people'))
    def key(s):
        return slugify(str(s or '')).replace('_','')
    headers=[key(x) for x in rows[0]]
    def find_col(*names):
        for name in names:
            if key(name) in headers:return headers.index(key(name))
        return None
    fi=find_col('prenom','first_name')
    la=find_col('nom','last_name')
    em=find_col('email','e_mail','mail')
    cl=find_col('classe','class','class_id')
    if None in (fi,la,em,cl):
        flash('Colonnes requises : prenom, nom, email, classe.','error')
        return redirect(url_for('people'))
    classes=allrows('SELECT id,name,year_id FROM classes WHERE school_id=?',(school_id(),))
    by_id={str(c['id']):c for c in classes}
    by_name={}
    for c in classes:by_name.setdefault(key(c['name']),[]).append(c)
    prepared=[]; errors=[]; encountered=set()
    for lineno,row in enumerate(rows[1:],2):
        if not row or all(v is None or not str(v).strip() for v in row):continue
        def cell(i):return str(row[i] or '').strip() if i<len(row) else ''
        first,last,email,lookup=cell(fi),cell(la),cell(em).lower(),cell(cl)
        target=by_id.get(lookup)
        if not target:
            opts=by_name.get(key(lookup),[])
            target=opts[0] if len(opts)==1 else None
        if not first or not last or not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',email):
            errors.append(f'Ligne {lineno} : identité ou e-mail invalide')
        elif not target:
            errors.append(f'Ligne {lineno} : classe introuvable ou ambiguë ({lookup})')
        elif email in encountered:
            errors.append(f'Ligne {lineno} : e-mail en doublon ({email})')
        else:
            encountered.add(email)
            prepared.append((first+' '+last,email,target['id'],target['year_id']))
        if len(errors)>=8:break
    if not prepared and not errors:errors.append('Aucune ligne exploitable')
    if errors:
        flash('Import annulé. '+ ' ; '.join(errors),'error')
        return redirect(url_for('people'))
    hashes=[]
    try:
        with db() as c:
            c.execute('BEGIN IMMEDIATE')
            registered={r['email'] for r in c.execute('SELECT email FROM users WHERE email IN ('+','.join('?' for _ in prepared)+')',tuple(x[1] for x in prepared)).fetchall()}
            if registered:
                flash('Import annulé : comptes déjà existants : '+', '.join(sorted(registered)[:4]),'error')
                return redirect(url_for('people'))
            for name,email,class_id,year_id in prepared:
                uid=c.execute('INSERT INTO users(school_id,name,email,password_hash,role) VALUES (?,?,?,?,?)',(school_id(),name,email,generate_password_hash(secrets.token_urlsafe(24)),'etudiant')).lastrowid
                c.execute('INSERT INTO enrollments(school_id,student_id,class_id,year_id) VALUES (?,?,?,?)',(school_id(),uid,class_id,year_id))
                hashes.append(uid)
    except sqlite3.IntegrityError:
        flash('Import annulé : conflit sur les données.','error')
        return redirect(url_for('people'))
    # Invitations can be requested later; avoid thousands of synchronous outbound email calls.
    audit('students.imported',str(len(hashes)))
    flash(f'{len(hashes)} étudiants importés et inscrits dans leur classe. Invitations à envoyer ultérieurement.','success')
    return redirect(url_for('people'))

def create_invite(uid):
    import hashlib
    token=secrets.token_urlsafe(32)
    expiry=(datetime.datetime.now(datetime.timezone.utc)+datetime.timedelta(days=2)).isoformat()
    execute('INSERT INTO invites(user_id,token_hash,expires_at) VALUES (?,?,?)',(uid,hashlib.sha256(token.encode()).hexdigest(),expiry))
    url=os.getenv('PUBLIC_BASE_URL',request.host_url.rstrip('/'))+'/activate/'+token
    notify([uid],'Activez votre compte EduPilot : '+url)

@app.route('/activate/<token>',methods=['GET','POST'])
def activate(token):
    import hashlib
    invitation=one('SELECT * FROM invites WHERE token_hash=? AND used=0',(hashlib.sha256(token.encode()).hexdigest(),))
    if not invitation or invitation['expires_at'] < datetime.datetime.now(datetime.timezone.utc).isoformat():abort(404)
    if request.method=='POST':
        password=request.form.get('password','')
        if len(password)<10:flash('Mot de passe : 10 caractères minimum.','error')
        else:
            execute('UPDATE users SET password_hash=? WHERE id=?',(generate_password_hash(password),invitation['user_id']))
            execute('UPDATE invites SET used=1 WHERE id=?',(invitation['id'],))
            flash('Compte activé. Vous pouvez vous connecter.','success')
            return redirect(url_for('login'))
    return render_template('activate.html')

@app.route('/classes',methods=['GET','POST'])
@roles('admin','administratif')
def classes():
    if request.method=='POST':
        year=scoped('SELECT id FROM years WHERE school_id=? AND is_active=1 LIMIT 1')
        if not year:abort(400)
        campus=request.form.get('campus_id')
        if campus and not has_school('campuses',campus):abort(403)
        if campus and one('SELECT plan FROM schools WHERE id=?',(school_id(),))['plan']!='premium':
            first=one('SELECT id FROM campuses WHERE school_id=? ORDER BY id LIMIT 1',(school_id(),))
            if int(campus)!=first['id']: abort(403)
        name=request.form.get('name','').strip()
        if not name:abort(400)
        cid=execute('INSERT INTO classes(school_id,year_id,campus_id,name,cycle,parents_enabled) VALUES (?,?,?,?,?,?)',(school_id(),year[0]['id'],campus or None,name,request.form.get('cycle','semestre'),int('parents_enabled' in request.form)))
        execute('INSERT INTO periods(school_id,class_id,name) VALUES (?,?,?)',(school_id(),cid,'Trimestre 1' if request.form.get('cycle')=='trimestre' else 'Semestre 1'))
        audit('class.created',name)
        return redirect(url_for('classes'))
    return render_template('list.html',title='Classes',columns=['Classe','Régime','Parents','Détails','Modifier'],rows=[(x['name'],x['cycle'],'Actif' if x['parents_enabled'] else 'Inactif',{'link':url_for('class_details',cid=x['id']),'label':'Détails'},{'link':url_for('class_edit',cid=x['id']),'label':'Modifier'}) for x in scoped('SELECT * FROM classes WHERE school_id=?')],form='classes',campuses=scoped('SELECT * FROM campuses WHERE school_id=?'))

@app.route('/classes/<int:cid>/edit',methods=['GET','POST'])
@roles('admin','administratif')
def class_edit(cid):
    item=one('SELECT * FROM classes WHERE id=? AND school_id=?',(cid,school_id()))
    if not item:abort(404)
    if request.method=='POST':
        name=request.form.get('name','').strip()
        cycle=request.form.get('cycle','')
        campus=request.form.get('campus_id') or None
        if not name or len(name)>180 or cycle not in ('semestre','trimestre'):abort(400)
        if campus and not has_school('campuses',campus):abort(403)
        execute('UPDATE classes SET name=?,cycle=?,campus_id=?,parents_enabled=? WHERE id=? AND school_id=?',(name,cycle,campus,int('parents_enabled' in request.form),cid,school_id()))
        audit('class.updated',str(cid));flash('Classe modifiée.','success')
        return redirect(url_for('classes'))
    return render_template('edit_academic.html',kind='class',item=item,campuses=scoped('SELECT * FROM campuses WHERE school_id=?'))

@app.get('/classes/<int:cid>/details')
@roles('admin','administratif','enseignant')
def class_details(cid):
    clazz=one("""SELECT cl.*, y.label academic_year,ca.name campus_name
                FROM classes cl JOIN years y ON y.id=cl.year_id
                LEFT JOIN campuses ca ON ca.id=cl.campus_id
                WHERE cl.id=? AND cl.school_id=?""",(cid,school_id()))
    if not clazz:abort(404)
    if current_user()['role']=='enseignant' and not one(
        'SELECT id FROM courses WHERE school_id=? AND class_id=? AND teacher_id=?',(school_id(),cid,current_user()['id'])):
        abort(403)
    students=allrows("""SELECT DISTINCT u.id,u.name,u.email,u.active
                        FROM enrollments e JOIN users u ON u.id=e.student_id
                        WHERE e.school_id=? AND e.class_id=? AND e.year_id=?
                        ORDER BY u.name""",(school_id(),cid,clazz['year_id']))
    courses=allrows("""SELECT c.id,c.name,c.code,c.planned_minutes,u.id teacher_id,u.name teacher_name
                       FROM courses c LEFT JOIN users u ON u.id=c.teacher_id
                       WHERE c.school_id=? AND c.class_id=? ORDER BY c.name""",(school_id(),cid))
    teachers=allrows("""SELECT DISTINCT u.id,u.name,u.email
                        FROM courses c JOIN users u ON u.id=c.teacher_id
                        WHERE c.school_id=? AND c.class_id=? AND u.role='enseignant'
                        ORDER BY u.name""",(school_id(),cid))
    return render_template('class_details.html',clazz=clazz,students=students,
                           teachers=teachers,courses=courses)

@app.post('/enroll')
@roles('admin','administratif')
def enroll():
    student=request.form.get('student_id');cl=request.form.get('class_id')
    if not has_school('classes',cl) or not one("SELECT id FROM users WHERE id=? AND school_id=? AND role='etudiant'",(student,school_id())):abort(403)
    clazz=one('SELECT * FROM classes WHERE id=? AND school_id=?',(cl,school_id()))
    execute('INSERT OR IGNORE INTO enrollments(school_id,student_id,class_id,year_id) VALUES (?,?,?,?)',(school_id(),student,cl,clazz['year_id']))
    audit('student.enrolled',f'{student}:{cl}');flash('Inscription enregistrée.','success')
    return redirect(url_for('students'))

@app.post('/students/transfer')
@roles('admin','administratif')
def students_transfer():
    ids=request.form.getlist('enrollment_ids')
    class_id=request.form.get('class_id')
    dest=one('SELECT id,year_id FROM classes WHERE id=? AND school_id=?',(class_id,school_id()))
    if not dest or not ids or len(ids)>300 or any(not x.isdigit() for x in ids):abort(400)
    ids=list(dict.fromkeys(map(int,ids)))
    now=datetime.datetime.now(datetime.timezone.utc).isoformat()
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        q=','.join('?'*len(ids))
        rows=c.execute(f'SELECT id,student_id,class_id,year_id FROM enrollments WHERE school_id=? AND id IN ({q})',(school_id(),*ids)).fetchall()
        if len(rows)!=len(ids):abort(403)
        # Keep all historical enrollments for past years. Move only records in same academic year.
        if any(r['year_id']!=dest['year_id'] for r in rows):
            flash('Transfert annulé : choisissez une classe de la même année académique. Pour une nouvelle année, utilisez la promotion.','error')
            return redirect(url_for('students'))
        for row in rows:
            if row['class_id']==dest['id']:continue
            duplicate=c.execute('SELECT id FROM enrollments WHERE school_id=? AND student_id=? AND class_id=? AND year_id=?',(school_id(),row['student_id'],dest['id'],dest['year_id'])).fetchone()
            if duplicate:
                c.execute('DELETE FROM enrollments WHERE id=?',(row['id'],))
            else:
                c.execute('UPDATE enrollments SET class_id=? WHERE id=?',(dest['id'],row['id']))
            c.execute('INSERT INTO audit(school_id,user_id,action,details) VALUES (?,?,?,?)',(school_id(),current_user()['id'],'enrollment.transferred',f"{row['student_id']}:{row['class_id']}->{dest['id']}:{now}"))
    flash(f'{len(ids)} inscription(s) transférée(s).','success')
    return redirect(url_for('students'))

@app.route('/students')
@login_required
def students():
    u=current_user()
    if u['role'] not in ('admin','administratif','enseignant'):abort(403)
    sql="""SELECT e.id enrollment_id,u.name,c.name class_name,c.id class_id,y.id year_id,y.label
           FROM enrollments e JOIN users u ON u.id=e.student_id
           JOIN classes c ON c.id=e.class_id JOIN years y ON y.id=e.year_id
           WHERE e.school_id=?"""
    args=[school_id()]
    if u['role']=='enseignant':
        sql+=" AND EXISTS (SELECT 1 FROM courses co WHERE co.class_id=e.class_id AND co.school_id=e.school_id AND co.teacher_id=?)"
        args.append(u['id'])
    requested_class=request.args.get('class_id','')
    requested_year=request.args.get('year_id','')
    if requested_class and requested_class.isdigit():
        sql+=' AND e.class_id=?';args.append(int(requested_class))
    if requested_year and requested_year.isdigit():
        sql+=' AND e.year_id=?';args.append(int(requested_year))
    sql+=' ORDER BY y.label DESC,c.name,u.name'
    entries=allrows(sql,args)
    class_choices=scoped('SELECT id,name,year_id FROM classes WHERE school_id=? ORDER BY name')
    year_choices=scoped('SELECT id,label FROM years WHERE school_id=? ORDER BY label DESC')
    if u['role']=='enseignant':
        class_choices=[c for c in class_choices if one('SELECT id FROM courses WHERE class_id=? AND school_id=? AND teacher_id=?',(c['id'],school_id(),u['id']))]
    return render_template('students.html',enrollments=entries,classes=class_choices,years=year_choices,can_edit=u['role'] in ('admin','administratif'),chosen_class=requested_class,chosen_year=requested_year)

@app.route('/courses',methods=['GET','POST'])
@roles('admin','administratif')
def courses():
    if request.method=='POST':
        cl=request.form.get('class_id');teacher=request.form.get('teacher_id') or None
        if not has_school('classes',cl):abort(403)
        if teacher and not one("SELECT id FROM users WHERE school_id=? AND id=? AND role='enseignant'",(school_id(),teacher)):abort(403)
        name=request.form.get('name','').strip()
        if not name:abort(400)
        try:
            coefficient=float(request.form.get('coefficient','1'))
            if not (0<coefficient<=100):raise ValueError()
        except ValueError:abort(400,'Coefficient matière invalide')
        cid=execute('INSERT INTO courses(school_id,class_id,name,code,planned_minutes,teacher_id,coefficient) VALUES (?,?,?,?,?,?,?)',(school_id(),cl,name,request.form.get('code',''),int(float(request.form.get('hours',20))*60),teacher,coefficient))
        if teacher:execute('INSERT INTO teacher_history(course_id,teacher_id,date_start) VALUES (?,?,?)',(cid,teacher,datetime.date.today().isoformat()))
        audit('course.created',name);return redirect(url_for('courses'))
    rows=scoped('SELECT c.*,cl.name class_name,u.name teacher_name FROM courses c JOIN classes cl ON cl.id=c.class_id LEFT JOIN users u ON u.id=c.teacher_id WHERE c.school_id=?')
    return render_template('list.html',title='Cours',columns=['Cours','Classe','Enseignant','Volume prévu','Coeff. matière','Modifier'],rows=[(x['name'],x['class_name'],x['teacher_name'] or 'Non affecté',f"{x['planned_minutes']/60:g} h",x["coefficient"],{'link':url_for('course_edit',cid=x['id']),'label':'Modifier'}) for x in rows],form='courses',classes=scoped('SELECT * FROM classes WHERE school_id=?'),teachers=scoped("SELECT * FROM users WHERE school_id=? AND role='enseignant'"))

@app.route('/courses/<int:cid>/edit',methods=['GET','POST'])
@roles('admin','administratif')
def course_edit(cid):
    item=one('SELECT * FROM courses WHERE id=? AND school_id=?',(cid,school_id()))
    if not item:abort(404)
    if request.method=='POST':
        name=request.form.get('name','').strip()
        class_id=request.form.get('class_id')
        teacher=request.form.get('teacher_id') or None
        if not name or len(name)>180 or not has_school('classes',class_id):abort(400)
        if teacher and not one("SELECT id FROM users WHERE id=? AND school_id=? AND role='enseignant' AND active=1",(teacher,school_id())):abort(403)
        try:
            minutes=int(round(float(request.form.get('hours',''))*60))
            coefficient=float(request.form.get('coefficient','1'))
            if not (0<coefficient<=100):raise ValueError()
            if minutes<30 or minutes>300000:raise ValueError()
        except (ValueError,TypeError):abort(400)
        if int(class_id)!=item['class_id'] and (one('SELECT id FROM lessons WHERE course_id=?',(cid,)) or one('SELECT id FROM assessments WHERE course_id=?',(cid,))):
            flash('Ce cours possède des séances ou évaluations : sa classe ne peut plus être modifiée.','error')
            return redirect(url_for('course_edit',cid=cid))
        now=datetime.datetime.now(datetime.timezone.utc).isoformat()
        changed_teacher=item['teacher_id']!=(int(teacher) if teacher else None)
        with db() as c:
            if changed_teacher:
                c.execute('UPDATE teacher_history SET date_end=? WHERE course_id=? AND date_end IS NULL',(now,cid))
                if teacher:c.execute('INSERT INTO teacher_history(course_id,teacher_id,date_start) VALUES (?,?,?)',(cid,teacher,now))
            c.execute('UPDATE courses SET name=?,code=?,class_id=?,teacher_id=?,planned_minutes=?,coefficient=? WHERE id=? AND school_id=?',(name,request.form.get('code','').strip(),class_id,teacher,minutes,coefficient,cid,school_id()))
        audit('course.updated',str(cid));flash('Cours mis à jour ; les séances existantes gardent leur enseignant initial.','success')
        return redirect(url_for('courses'))
    return render_template('edit_academic.html',kind='course',item=item,classes=scoped('SELECT * FROM classes WHERE school_id=?'),teachers=scoped("SELECT * FROM users WHERE school_id=? AND role='enseignant' AND active=1"))

@app.route('/planning',methods=['GET','POST'])
@login_required
def planning():
    u=current_user()
    if u['role']=='superadmin':abort(403)
    if request.method=='POST':
        if u['role'] not in ('admin','administratif'):abort(403)
        course_id=request.form.get('course_id')
        class_id=request.form.get('class_id')
        course=one('SELECT * FROM courses WHERE id=? AND school_id=? AND class_id=?',(course_id,school_id(),class_id))
        if not course:
            flash('Sélectionnez une classe puis un cours appartenant à cette classe.','error')
            return redirect(url_for('planning'))
        if not course['teacher_id']:
            flash('Affectez un enseignant à ce cours avant la planification.','error')
            return redirect(url_for('planning'))
        try:
            day=datetime.date.fromisoformat(request.form.get('lesson_date',''))
            start_time=datetime.time.fromisoformat(request.form.get('start_time',''))
            hours=float(request.form.get('duration_hours',''))
            if hours<0.5 or hours>12 or not (hours*2).is_integer():raise ValueError('durée')
            start_dt=datetime.datetime.combine(day,start_time)
            end_dt=start_dt+datetime.timedelta(minutes=round(hours*60))
            if end_dt.date()!=day:raise ValueError('minuit')
            mode=request.form.get('mode','unique')
            if mode not in ('unique','hebdomadaire'):raise ValueError('mode')
            if mode=='hebdomadaire':
                last=datetime.date.fromisoformat(request.form.get('repeat_until',''))
                if last<day or (last-day).days>365:raise ValueError('récurrence')
                dates=[start_dt+datetime.timedelta(days=7*i) for i in range((last-day).days//7+1)]
            else: dates=[start_dt]
            if len(dates)>53:raise ValueError('limite')
        except (ValueError,TypeError,OverflowError):
            flash('Date, heure, durée ou récurrence invalide. Une séance doit finir le même jour et durer de 0,5 à 12 h.','error')
            return redirect(url_for('planning'))
        room=request.form.get('room','').strip()[:80]
        created=[]
        with db() as c:
            c.execute('BEGIN IMMEDIATE')
            for dt in dates:
                end_at=dt+datetime.timedelta(minutes=round(hours*60))
                start_txt=dt.strftime('%Y-%m-%dT%H:%M')
                end_txt=end_at.strftime('%Y-%m-%dT%H:%M')
                clash=c.execute("""SELECT l.id FROM lessons l JOIN courses c ON c.id=l.course_id
                           WHERE l.school_id=? AND l.status NOT IN ('annulee','reportee')
                           AND l.starts_at < ? AND l.ends_at > ?
                           AND (c.class_id=? OR l.teacher_id=? OR (?<>'' AND l.room=?))
                           LIMIT 1""",(school_id(),end_txt,start_txt,class_id,course['teacher_id'],room,room)).fetchone()
                if clash:
                    c.rollback()
                    flash(f'Conflit le {dt.strftime("%d/%m/%Y")} : classe, enseignant ou salle déjà occupé(e). Aucune séance ajoutée.','error')
                    return redirect(url_for('planning'))
                cur=c.execute('INSERT INTO lessons(school_id,course_id,teacher_id,starts_at,ends_at,room) VALUES (?,?,?,?,?,?)',(school_id(),course_id,course['teacher_id'],start_txt,end_txt,room))
                created.append(cur.lastrowid)
        notify(classmates(course_id)+[course['teacher_id']],f'{len(created)} séance(s) programmée(s) : '+course['name'],'/planning')
        audit('lesson.created',','.join(str(x) for x in created))
        flash(f'{len(created)} séance(s) ajoutée(s) au planning.','success')
        return redirect(url_for('planning'))
    query='''SELECT l.*,c.name course_name,cl.name class_name FROM lessons l JOIN courses c ON c.id=l.course_id JOIN classes cl ON cl.id=c.class_id WHERE l.school_id=?'''
    args=[school_id()]
    if u['role']=='enseignant':query+=' AND l.teacher_id=?';args.append(u['id'])
    elif u['role']=='etudiant':query+=' AND EXISTS (SELECT 1 FROM enrollments e WHERE e.student_id=? AND e.class_id=c.class_id)';args.append(u['id'])
    elif u['role']=='parent':query+=' AND EXISTS (SELECT 1 FROM parent_links p JOIN enrollments e ON e.student_id=p.student_id WHERE p.parent_id=? AND p.active=1 AND e.class_id=c.class_id AND cl.parents_enabled=1)';args.append(u['id'])
    events=allrows(query,args)
    return render_template('planning.html',events=events,courses=scoped('SELECT * FROM courses WHERE school_id=? ORDER BY name') if u['role'] in ('admin','administratif') else [],classes=scoped('SELECT id,name FROM classes WHERE school_id=? ORDER BY name') if u['role'] in ('admin','administratif') else [])

@app.post('/lessons/<int:lid>/declare')
@roles('enseignant','admin','administratif')
def declare(lid):
    u=current_user();les=one('SELECT * FROM lessons WHERE id=? AND school_id=?',(lid,school_id()))
    if not les or (u['role']=='enseignant' and les['teacher_id']!=u['id']):abort(403)
    if les['ends_at']>datetime.datetime.now().strftime('%Y-%m-%dT%H:%M'):abort(400,'Séance future')
    status=request.form.get('status')
    if status not in ('realisee','partielle','non_effectuee'):abort(400)
    mins=int(request.form.get('actual_minutes','0')) if status!='non_effectuee' else 0
    if (status!='non_effectuee' and mins<=0) or mins>24*60:abort(400)
    if status=='non_effectuee' and not request.form.get('comment','').strip():abort(400,'Motif obligatoire')
    execute('UPDATE lessons SET status=?,actual_minutes=?,comment=? WHERE id=?',(status,mins,request.form.get('comment',''),lid))
    audit('lesson.declared',str(lid)+':'+status)
    flash('Séance déclarée.','success');return redirect(url_for('planning'))

@app.get('/assessments/<int:aid>/attachment')
@login_required
def assessment_attachment(aid):
    a=one("""SELECT a.attachment_name,a.attachment_blob,a.attachment_mime,c.class_id,c.teacher_id,cl.parents_enabled
           FROM assessments a JOIN courses c ON c.id=a.course_id JOIN classes cl ON cl.id=c.class_id
           WHERE a.id=? AND a.school_id=?""",(aid,school_id()))
    if not a or not a['attachment_blob']:abort(404)
    u=current_user()
    if u['role']=='superadmin':abort(403)
    if u['role']=='enseignant' and a['teacher_id']!=u['id']:abort(403)
    if u['role']=='etudiant' and not one('SELECT id FROM enrollments WHERE school_id=? AND class_id=? AND student_id=?',(school_id(),a['class_id'],u['id'])):abort(403)
    if u['role']=='parent' and (not a['parents_enabled'] or not one("""SELECT p.id FROM parent_links p JOIN enrollments e ON e.student_id=p.student_id WHERE p.school_id=? AND p.parent_id=? AND p.active=1 AND e.class_id=?""",(school_id(),u['id'],a['class_id']))):abort(403)
    response=send_file(io.BytesIO(a['attachment_blob']),download_name=a['attachment_name'],mimetype=a['attachment_mime'],as_attachment=True)
    response.headers['X-Content-Type-Options']='nosniff'
    return response

@app.route('/assessments',methods=['GET','POST'])
@login_required
def assessments():
    u=current_user()
    if u['role']=='superadmin':abort(403)
    if request.method=='POST':
        if u['role'] not in ('enseignant','admin','administratif'):abort(403)
        course_id=request.form.get('course_id')
        course=one('SELECT * FROM courses WHERE id=? AND school_id=?',(course_id,school_id()))
        if not course or (u['role']=='enseignant' and course['teacher_id']!=u['id']):abort(403)
        title=request.form.get('title','').strip()
        description=request.form.get('description','').strip()
        try:
            coeff=float(request.form.get('coefficient','1'))
            if not (0<coeff<=100):raise ValueError()
        except (ValueError,TypeError):abort(400,'Coefficient invalide')
        if not title or len(title)>200 or len(description)>10000:abort(400)
        file=request.files.get('document')
        data=None;mime=None;filename=None
        if file and file.filename:
            from werkzeug.utils import secure_filename
            filename=secure_filename(file.filename)
            data=file.read(3*1024*1024+1)
            if not filename or len(data)>3*1024*1024:abort(400,'Fichier supérieur à 3 Mo')
            if data.startswith(b'%PDF-'):mime='application/pdf'
            elif data.startswith(bytes([137,80,78,71,13,10,26,10])):mime='image/png'
            elif data.startswith(bytes([255,216,255])):mime='image/jpeg'
            elif data.startswith(b'PK') and filename.lower().endswith('.docx'):mime='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
            else:abort(400,'Format autorisé : PDF, DOCX, PNG et JPEG')
        execute('''INSERT INTO assessments(school_id,course_id,title,kind,due_date,description,coefficient,attachment_name,attachment_blob,attachment_mime)
                   VALUES (?,?,?,?,?,?,?,?,?,?)''',(school_id(),course_id,title,request.form.get('kind','Devoir'),request.form.get('due_date') or None,description,coeff,filename,data,mime))
        notify(classmates(course_id),'Nouvelle évaluation : '+title,'/assessments')
        audit('assessment.created',title);flash('Évaluation créée.','success')
        return redirect(url_for('assessments'))
    sql='''SELECT a.id,a.school_id,a.course_id,a.title,a.kind,a.due_date,a.coefficient,a.description,a.attachment_name,c.name course_name,cl.name class_name,c.teacher_id
           FROM assessments a JOIN courses c ON c.id=a.course_id JOIN classes cl ON cl.id=c.class_id WHERE a.school_id=?''';args=[school_id()]
    if u['role']=='enseignant':sql+=' AND c.teacher_id=?';args.append(u['id'])
    elif u['role']=='etudiant':sql+=' AND EXISTS (SELECT 1 FROM enrollments e WHERE e.class_id=c.class_id AND e.student_id=? AND e.school_id=a.school_id)';args.append(u['id'])
    elif u['role']=='parent':sql+=' AND EXISTS (SELECT 1 FROM parent_links p JOIN enrollments e ON e.student_id=p.student_id WHERE p.parent_id=? AND p.active=1 AND e.class_id=c.class_id AND cl.parents_enabled=1)';args.append(u['id'])
    rows=allrows(sql,args)
    choices=scoped('SELECT * FROM courses WHERE school_id=?')
    if u['role']=='enseignant':choices=[x for x in choices if x['teacher_id']==u['id']]
    return render_template('assessments.html',assessments=rows,courses=choices)

@app.route('/grades',methods=['GET','POST'])
@login_required
def grades():
    u=current_user()
    if u['role']=='superadmin':abort(403)
    if request.method=='POST':
        if u['role'] not in ('enseignant','admin','administratif'):abort(403)
        aid=request.form.get('assessment_id');student=request.form.get('student_id');value=float(request.form.get('value','-1'))
        a=one('''SELECT a.*,c.class_id,c.teacher_id,cl.school_id FROM assessments a JOIN courses c ON c.id=a.course_id JOIN classes cl ON cl.id=c.class_id WHERE a.id=? AND a.school_id=?''',(aid,school_id()))
        if not a or (u['role']=='enseignant' and a['teacher_id']!=u['id']) or not (0<=value<=a['max_score']):abort(403)
        if not one('SELECT id FROM enrollments WHERE student_id=? AND class_id=? AND school_id=?',(student,a['class_id'],school_id())):abort(403)
        period=one('SELECT * FROM periods WHERE class_id=? AND school_id=? ORDER BY id DESC LIMIT 1',(a['class_id'],school_id()))
        if period and period['locked']:
            unlocked=one('SELECT * FROM unlocks WHERE period_id=? AND teacher_id=? AND expires_at>? ORDER BY id DESC LIMIT 1',(period['id'],u['id'],datetime.datetime.now(datetime.timezone.utc).isoformat()))
            if not unlocked and u['role']=='enseignant':abort(403,'Période verrouillée')
        existing=one('SELECT * FROM grades WHERE assessment_id=? AND student_id=?',(aid,student))
        if existing:
            execute('UPDATE grades SET value=?,updated_at=CURRENT_TIMESTAMP WHERE id=?',(value,existing['id']))
            gid=existing['id']; old=existing['value']
        else:
            gid=execute('INSERT INTO grades(assessment_id,student_id,value) VALUES (?,?,?)',(aid,student,value));old=None
        execute('INSERT INTO grade_history(grade_id,old_value,new_value,actor_id) VALUES (?,?,?,?)',(gid,old,value,u['id']))
        audit('grade.saved',str(gid));flash('Note enregistrée.','success');return redirect(url_for('grades'))
    sql='''SELECT g.*,a.title,c.name course_name,cl.name class_name,cl.parents_enabled,p.published,u.name student_name,u.id student_id FROM grades g JOIN assessments a ON a.id=g.assessment_id JOIN courses c ON c.id=a.course_id JOIN classes cl ON cl.id=c.class_id JOIN users u ON u.id=g.student_id LEFT JOIN periods p ON p.class_id=cl.id WHERE a.school_id=?''';args=[school_id()]
    if u['role']=='enseignant':sql+=' AND c.teacher_id=?';args.append(u['id'])
    if u['role']=='etudiant':sql+=' AND u.id=? AND p.published=1';args.append(u['id'])
    if u['role']=='parent':sql+=' AND cl.parents_enabled=1 AND p.published=1 AND EXISTS (SELECT 1 FROM parent_links l WHERE l.student_id=u.id AND l.parent_id=? AND l.active=1)';args.append(u['id'])
    rows=allrows(sql,args)
    evals=scoped('SELECT a.*,c.name course_name,c.class_id,c.teacher_id FROM assessments a JOIN courses c ON c.id=a.course_id WHERE a.school_id=?')
    if u['role']=='enseignant':evals=[a for a in evals if a['teacher_id']==u['id']]
    return render_template('grades.html',grades=rows,evaluations=evals,students=scoped("SELECT * FROM users WHERE school_id=? AND role='etudiant'") if u['role'] in ('enseignant','admin','administratif') else [])

@app.route('/grades/entry/<int:aid>',methods=['GET','POST'])
@roles('enseignant','admin','administratif')
def grade_entry(aid):
    a=one("""SELECT a.id,a.title,a.max_score,a.coefficient,c.id course_id,c.class_id,c.teacher_id,c.name course_name,cl.name class_name
             FROM assessments a JOIN courses c ON c.id=a.course_id JOIN classes cl ON cl.id=c.class_id
             WHERE a.id=? AND a.school_id=?""",(aid,school_id()))
    if not a:abort(404)
    u=current_user()
    if u['role']=='enseignant' and a['teacher_id']!=u['id']:abort(403)
    period=one('SELECT * FROM periods WHERE class_id=? AND school_id=? ORDER BY id DESC LIMIT 1',(a['class_id'],school_id()))
    if period and period['locked'] and u['role']=='enseignant':
        if not one('SELECT id FROM unlocks WHERE period_id=? AND teacher_id=? AND expires_at>?',(period['id'],u['id'],datetime.datetime.now(datetime.timezone.utc).isoformat())):abort(403,'Période verrouillée')
    students=allrows("""SELECT DISTINCT u.id,u.name,g.value,g.comment FROM enrollments e JOIN users u ON u.id=e.student_id
                        LEFT JOIN grades g ON g.student_id=u.id AND g.assessment_id=?
                        WHERE e.school_id=? AND e.class_id=? ORDER BY u.name""",(aid,school_id(),a['class_id']))
    if request.method=='POST':
        changes=[]
        for student in students:
            raw=request.form.get(f"note_{student['id']}",'').strip()
            comment=request.form.get(f"comment_{student['id']}",'').strip()
            if len(comment)>2000:abort(400,'Commentaire trop long')
            if not raw:
                if student['value'] is not None: # Empty input does not erase an existing grade
                    continue
                continue
            try:
                value=float(raw)
                if not (0<=value<=a['max_score']):raise ValueError()
            except ValueError:abort(400,'Note invalide')
            changes.append((student['id'],value,comment,student['value']))
        with db() as c:
            for student_id,value,comment,old in changes:
                row=c.execute('SELECT id FROM grades WHERE assessment_id=? AND student_id=?',(aid,student_id)).fetchone()
                if row:
                    c.execute('UPDATE grades SET value=?,comment=?,updated_at=CURRENT_TIMESTAMP WHERE id=?',(value,comment,row['id']))
                    gid=row['id']
                else:
                    gid=c.execute('INSERT INTO grades(assessment_id,student_id,value,comment) VALUES (?,?,?,?)',(aid,student_id,value,comment)).lastrowid
                if old!=value:
                    c.execute('INSERT INTO grade_history(grade_id,old_value,new_value,actor_id) VALUES (?,?,?,?)',(gid,old,value,u['id']))
        audit('grades.batch.updated',f'{aid}:{len(changes)}')
        flash(f'{len(changes)} note(s) enregistrée(s).','success')
        return redirect(url_for('grade_entry',aid=aid))
    return render_template('grade_entry.html',assessment=a,students=students)

@app.get('/grades/global')
@roles('enseignant','admin','administratif')
def grade_global():
    u=current_user()
    choices=scoped("""SELECT c.id,c.name,cl.name class_name,c.coefficient FROM courses c JOIN classes cl ON cl.id=c.class_id
                      WHERE c.school_id=? ORDER BY cl.name,c.name""")
    if u['role']=='enseignant':choices=[c for c in choices if one('SELECT id FROM courses WHERE id=? AND teacher_id=?',(c['id'],u['id']))]
    requested=request.args.get('course_id','')
    selected=next((c for c in choices if str(c['id'])==requested),choices[0] if choices else None)
    if not selected:return render_template('grade_global.html',choices=choices,course=None,assessments=[],rows=[])
    course=one('SELECT * FROM courses WHERE id=? AND school_id=?',(selected['id'],school_id()))
    assessments=allrows('SELECT id,title,coefficient,max_score FROM assessments WHERE school_id=? AND course_id=? ORDER BY id',(school_id(),course['id']))
    students=allrows("""SELECT DISTINCT u.id,u.name FROM enrollments e JOIN users u ON u.id=e.student_id
                        WHERE e.school_id=? AND e.class_id=? ORDER BY u.name""",(school_id(),course['class_id']))
    results=allrows("""SELECT g.student_id,g.assessment_id,g.value FROM grades g JOIN assessments a ON a.id=g.assessment_id
                       WHERE a.school_id=? AND a.course_id=?""",(school_id(),course['id']))
    marks={(g['student_id'],g['assessment_id']):g['value'] for g in results}
    rows=[]
    for student in students:
        cells=[marks.get((student['id'],a['id'])) for a in assessments]
        weighted=sum((v/a['max_score']*20)*a['coefficient'] for v,a in zip(cells,assessments) if v is not None and a['max_score'])
        weight=sum(a['coefficient'] for v,a in zip(cells,assessments) if v is not None and a['max_score'])
        rows.append({'student':student,'notes':cells,'average':round(weighted/weight,2) if weight else None})
    return render_template('grade_global.html',choices=choices,course=course,assessments=assessments,rows=rows)

@app.route('/periods',methods=['GET','POST'])
@roles('admin','administratif')
def periods():
    if request.method=='POST':
        pid=request.form.get('period_id');action=request.form.get('action')
        if not one('SELECT id FROM periods WHERE id=? AND school_id=?',(pid,school_id())):abort(403)
        if action=='lock':execute('UPDATE periods SET locked=1 WHERE id=?',(pid,))
        elif action=='publish':execute('UPDATE periods SET locked=1,published=1 WHERE id=?',(pid,))
        elif action=='unpublish':execute('UPDATE periods SET published=0 WHERE id=?',(pid,))
        elif action=='unlock':execute('UPDATE periods SET locked=0 WHERE id=?',(pid,))
        else:abort(400)
        audit('period.'+action,str(pid));flash('Période mise à jour.','success');return redirect(url_for('periods'))
    return render_template('periods.html',periods=scoped('SELECT p.*,c.name class_name FROM periods p JOIN classes c ON c.id=p.class_id WHERE p.school_id=?'))

@app.route('/notifications')
@login_required
def notifications():
    u=current_user()
    rows=allrows('SELECT * FROM notifications WHERE user_id=? ORDER BY created_at DESC LIMIT 100',(u['id'],))
    execute('UPDATE notifications SET read=1 WHERE user_id=?',(u['id'],))
    return render_template('list.html',title='Notifications',columns=['Date','Message'],rows=[(x['created_at'],x['message']) for x in rows])

@app.get('/reports')
@roles('admin','administratif')
def reports():
    rows=scoped('''SELECT c.name,cl.name class_name,c.planned_minutes,COUNT(l.id) lessons,
      COALESCE(SUM(CASE WHEN l.status IN ('realisee','partielle') THEN l.actual_minutes ELSE 0 END),0) actual_minutes
      FROM courses c JOIN classes cl ON cl.id=c.class_id LEFT JOIN lessons l ON l.course_id=c.id WHERE c.school_id=? GROUP BY c.id ORDER BY cl.name,c.name''')
    if request.args.get('format')=='csv':
        import csv,io
        b=io.StringIO();w=csv.writer(b,delimiter=';');w.writerow(['Cours','Classe','Séances planifiées','Heures prévues','Heures réalisées','Taux %'])
        for x in rows:w.writerow([x['name'],x['class_name'],x['lessons'],x['planned_minutes']/60,x['actual_minutes']/60,round(x['actual_minutes']/x['planned_minutes']*100,1) if x['planned_minutes'] else 0])
        from flask import Response
        return Response('\ufeff'+b.getvalue(),headers={'Content-Disposition':'attachment; filename=edupilot-rapport.csv'},mimetype='text/csv')
    return render_template('reports.html',rows=rows)

@app.route('/campuses',methods=['GET','POST'])
@roles('admin','administratif')
def campuses():
    school=one('SELECT * FROM schools WHERE id=?',(school_id(),))
    if request.method=='POST':
        if school['plan']!='premium':abort(403)
        name=request.form.get('name','').strip()
        if not name:abort(400)
        execute('INSERT INTO campuses(school_id,name) VALUES (?,?)',(school_id(),name))
        audit('campus.created',name)
        return redirect(url_for('campuses'))
    return render_template('list.html',title='Campus et sites',columns=['Campus'],rows=[(x['name'],) for x in scoped('SELECT name FROM campuses WHERE school_id=?')],form='campuses' if school['plan']=='premium' else None)

@app.post('/courses/<int:cid>/assign')
@roles('admin','administratif')
def assign_teacher(cid):
    if not has_school('courses',cid):abort(403)
    teacher=request.form.get('teacher_id')
    if not one("SELECT id FROM users WHERE school_id=? AND id=? AND role='enseignant'",(school_id(),teacher)):abort(403)
    old=one('SELECT teacher_id FROM courses WHERE id=?',(cid,))
    now=datetime.datetime.now(datetime.timezone.utc).isoformat()
    if old['teacher_id']:
        execute('UPDATE teacher_history SET date_end=? WHERE course_id=? AND date_end IS NULL',(now,cid))
    execute('UPDATE courses SET teacher_id=? WHERE id=?',(teacher,cid))
    execute('INSERT INTO teacher_history(course_id,teacher_id,date_start) VALUES (?,?,?)',(cid,teacher,now))
    audit('course.teacher.changed',str(cid))
    notify([int(teacher)],'Vous êtes affecté à un nouveau cours.','/planning')
    flash('Enseignant affecté. Les séances déjà planifiées conservent leur affectation initiale.','success')
    return redirect(url_for('courses'))

@app.post('/parents/link')
@roles('admin','administratif')
def parent_link():
    student=request.form.get('student_id');parent=request.form.get('parent_id')
    if not one("SELECT id FROM users WHERE school_id=? AND id=? AND role='etudiant'",(school_id(),student)):abort(403)
    if not one("SELECT id FROM users WHERE school_id=? AND id=? AND role='parent'",(school_id(),parent)):abort(403)
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        existing=c.execute('SELECT id FROM parent_links WHERE school_id=? AND student_id=? AND parent_id=?',(school_id(),student,parent)).fetchone()
        count=c.execute('SELECT count(*) n FROM parent_links WHERE school_id=? AND student_id=? AND active=1',(school_id(),student)).fetchone()['n']
        if count>=2 and not existing:abort(400,'Limite de 2 responsables')
        if existing:c.execute('UPDATE parent_links SET active=1 WHERE id=?',(existing['id'],))
        else:c.execute('INSERT INTO parent_links(school_id,student_id,parent_id) VALUES (?,?,?)',(school_id(),student,parent))
    audit('parent.linked',str(student)+':'+str(parent))
    notify([int(parent)],'Vous êtes rattaché à un apprenant dans EduPilot.','/grades')
    flash('Responsable associé.','success')
    return redirect(url_for('parents'))

@app.route('/parents')
@roles('admin','administratif')
def parents():
    linked=scoped('SELECT s.name student_name,p.name parent_name,pl.relation FROM parent_links pl JOIN users s ON s.id=pl.student_id JOIN users p ON p.id=pl.parent_id WHERE pl.school_id=? AND pl.active=1')
    return render_template('parents.html',linked=linked,students=scoped("SELECT id,name FROM users WHERE school_id=? AND role='etudiant'"),parents=scoped("SELECT id,name FROM users WHERE school_id=? AND role='parent'"))

@app.get('/attendance/<int:lid>')
@roles('enseignant','admin','administratif')
def attendance(lid):
    lesson=one('SELECT l.*,c.class_id,c.name course_name FROM lessons l JOIN courses c ON c.id=l.course_id WHERE l.id=? AND l.school_id=?',(lid,school_id()))
    if not lesson or (current_user()['role']=='enseignant' and lesson['teacher_id']!=current_user()['id']):abort(403)
    students=allrows('SELECT u.id,u.name,a.status FROM enrollments e JOIN users u ON u.id=e.student_id LEFT JOIN attendance a ON a.lesson_id=? AND a.student_id=u.id WHERE e.school_id=? AND e.class_id=?',(lid,school_id(),lesson['class_id']))
    return render_template('attendance.html',lesson=lesson,students=students)

@app.post('/attendance/<int:lid>')
@roles('enseignant','admin','administratif')
def attendance_save(lid):
    lesson=one('SELECT l.*,c.class_id FROM lessons l JOIN courses c ON c.id=l.course_id WHERE l.id=? AND l.school_id=?',(lid,school_id()))
    if not lesson or (current_user()['role']=='enseignant' and lesson['teacher_id']!=current_user()['id']):abort(403)
    students=allrows('SELECT student_id FROM enrollments WHERE school_id=? AND class_id=?',(school_id(),lesson['class_id']))
    with db() as c:
        for x in students:
            v=request.form.get('student_'+str(x['student_id']))
            if v in ('present','absent','retard','excuse'):
                c.execute('INSERT INTO attendance(lesson_id,student_id,status) VALUES (?,?,?) ON CONFLICT(lesson_id,student_id) DO UPDATE SET status=excluded.status',(lid,x['student_id'],v))
    audit('attendance.saved',str(lid));flash('Appel enregistré.','success')
    return redirect(url_for('attendance',lid=lid))

@app.get('/api/planning')
@login_required
def planning_json():
    u=current_user()
    if u['role']=='superadmin':abort(403)
    sql='''SELECT l.id,l.starts_at,l.ends_at,l.status,l.room,c.name course,c.class_id,cl.name class_name,l.teacher_id FROM lessons l JOIN courses c ON c.id=l.course_id JOIN classes cl ON cl.id=c.class_id WHERE l.school_id=?'''; args=[school_id()]
    if u['role']=='enseignant':sql+=' AND l.teacher_id=?';args.append(u['id'])
    elif u['role']=='etudiant':sql+=' AND EXISTS (SELECT 1 FROM enrollments e WHERE e.student_id=? AND e.class_id=c.class_id)';args.append(u['id'])
    elif u['role']=='parent':sql+=' AND EXISTS (SELECT 1 FROM parent_links p JOIN enrollments e ON e.student_id=p.student_id WHERE p.parent_id=? AND e.class_id=c.class_id AND p.active=1 AND cl.parents_enabled=1)';args.append(u['id'])
    return jsonify([{'id':x['id'],'title':x['course']+' — '+x['class_name'],'start':x['starts_at'],'end':x['ends_at'],'extendedProps':{'status':x['status'],'room':x['room']}} for x in allrows(sql,args)])

@app.errorhandler(403)
def denied(e):return render_template('error.html',message='Accès non autorisé.'),403
@app.errorhandler(404)
def missing(e):return render_template('error.html',message='Page introuvable.'),404
@app.errorhandler(400)
def invalid(e):return render_template('error.html',message='Données ou demande invalides.'),400

if __name__=='__main__':app.run(debug=False,port=int(os.getenv('PORT',5000)))

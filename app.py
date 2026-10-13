import os, sqlite3, secrets, datetime, functools, re, unicodedata
from pathlib import Path
from flask import Flask, request, session, redirect, abort, render_template_string, flash
from werkzeug.security import generate_password_hash, check_password_hash
app=Flask(__name__)
app.secret_key=os.environ.get("SECRET_KEY",secrets.token_hex(32))
PATH=os.environ.get("DATABASE_PATH","/tmp/edupilot.db")
Path(PATH).parent.mkdir(parents=True,exist_ok=True)
def conn():
 c=sqlite3.connect(PATH);c.row_factory=sqlite3.Row;c.execute("PRAGMA foreign_keys=ON");return c
def query(sql,args=(),one=False):
 with conn() as c:
  cur=c.execute(sql,args);return cur.fetchone() if one else cur.fetchall()
def write(sql,args=()):
 with conn() as c:
  cur=c.execute(sql,args);c.commit();return cur.lastrowid
SCHEMA="""CREATE TABLE IF NOT EXISTS schools(id INTEGER PRIMARY KEY,name TEXT,slug TEXT UNIQUE,plan TEXT);
CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY,school_id INTEGER,name TEXT,email TEXT UNIQUE,role TEXT,hash TEXT);
CREATE TABLE IF NOT EXISTS classes(id INTEGER PRIMARY KEY,school_id INTEGER,name TEXT,parents_enabled INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS enrollments(id INTEGER PRIMARY KEY,student_id INTEGER,class_id INTEGER,year TEXT,UNIQUE(student_id,class_id,year));
CREATE TABLE IF NOT EXISTS courses(id INTEGER PRIMARY KEY,school_id INTEGER,class_id INTEGER,teacher_id INTEGER,title TEXT,minutes INTEGER);
CREATE TABLE IF NOT EXISTS lessons(id INTEGER PRIMARY KEY,course_id INTEGER,starts TEXT,ends TEXT,status TEXT DEFAULT 'programmee',actual_minutes INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS evaluations(id INTEGER PRIMARY KEY,course_id INTEGER,title TEXT,max_note INTEGER DEFAULT 20,published INTEGER DEFAULT 1);
CREATE TABLE IF NOT EXISTS grades(id INTEGER PRIMARY KEY,evaluation_id INTEGER,student_id INTEGER,note REAL,UNIQUE(evaluation_id,student_id));
CREATE TABLE IF NOT EXISTS parent_links(id INTEGER PRIMARY KEY,student_id INTEGER,parent_id INTEGER,UNIQUE(student_id,parent_id));
CREATE TABLE IF NOT EXISTS notifications(id INTEGER PRIMARY KEY,user_id INTEGER,message TEXT,created TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS periods(id INTEGER PRIMARY KEY,class_id INTEGER,name TEXT,locked INTEGER DEFAULT 0,published INTEGER DEFAULT 0);
"""
with conn() as c:c.executescript(SCHEMA)
if not query("SELECT id FROM schools LIMIT 1",one=True):
 for name,slug,plan in [("Groupe Scolaire Excellence","groupe_scolaire_excellence","premium"),("Université de Bouaké","universite_de_bouake","standard")]:
  sid=write("INSERT INTO schools(name,slug,plan) VALUES (?,?,?)",(name,slug,plan))
  cl=write("INSERT INTO classes(school_id,name,parents_enabled) VALUES (?,?,1)",(sid,"Terminale D" if sid==1 else "Master 1 Géomatique"))
  def newuser(n,e,r):
   return write("INSERT INTO users(school_id,name,email,role,hash) VALUES (?,?,?,?,?)",(sid,n,e,r,generate_password_hash("Demo2026!")))
  ad=newuser("Directeur",f"admin{sid}@demo.edupilot.test","admin")
  sec=newuser("Secrétariat",f"scolarite{sid}@demo.edupilot.test","administratif")
  te=newuser("Enseignant",f"enseignant{sid}@demo.edupilot.test","enseignant")
  st=[newuser("Étudiant "+str(i),f"eleve{sid}_{i}@demo.edupilot.test","etudiant") for i in range(1,9)]
  pa=newuser("Parent",f"parent{sid}@demo.edupilot.test","parent")
  write("INSERT INTO parent_links(student_id,parent_id) VALUES (?,?)",(st[0],pa))
  for s in st:write("INSERT INTO enrollments(student_id,class_id,year) VALUES (?,?,?)",(s,cl,"2026-2027"))
  co=write("INSERT INTO courses(school_id,class_id,teacher_id,title,minutes) VALUES (?,?,?,?,?)",(sid,cl,te,"Mathématiques" if sid==1 else "SIG avancé",2400))
  for day in range(12,17):
   write("INSERT INTO lessons(course_id,starts,ends) VALUES (?,?,?)",(co,f"2026-10-{day:02d}T08:00",f"2026-10-{day:02d}T10:00"))
  ev=write("INSERT INTO evaluations(course_id,title) VALUES (?,?)",(co,"Devoir n°1"))
  for i,s in enumerate(st):write("INSERT INTO grades(evaluation_id,student_id,note) VALUES (?,?,?)",(ev,s,10+i))
  write("INSERT INTO periods(class_id,name) VALUES (?,?)",(cl,"Trimestre 1" if sid==1 else "Semestre 1"))
 write("INSERT INTO users(school_id,name,email,role,hash) VALUES (NULL,?,?,?,?)",("Éditeur EduPilot","superadmin@demo.edupilot.test","superadmin",generate_password_hash("Demo2026!")))
def me():
 return query("SELECT * FROM users WHERE id=?",(session.get("uid",-1),),True)
@app.before_request
def csrf():
 if "csrf" not in session:session["csrf"]=secrets.token_urlsafe(24)
 if request.method=="POST" and request.form.get("csrf")!=session["csrf"]:abort(400)
def require(*roles):
 u=me()
 if not u:abort(401)
 if roles and u["role"] not in roles:abort(403)
 return u
CSS="""<style>body{font:15px system-ui;background:#f3f6fa;color:#14213d;margin:0}header{background:#14213d;color:white;padding:15px 24px}nav a{color:#dbeafe;margin-right:16px}main{max-width:1200px;margin:30px auto;padding:0 22px}.card{background:white;border:1px solid #e1e7f0;border-radius:13px;padding:18px;margin:12px 0}table{border-collapse:collapse;width:100%;background:white}th,td{padding:11px;border-bottom:1px solid #ddd;text-align:left}button{background:#2459bb;color:white;border:0;border-radius:7px;padding:9px 14px;cursor:pointer}input,select{padding:9px;border:1px solid #ccd5e2;border-radius:6px;margin:5px}.bar{height:10px;background:#dde5f3;border-radius:9px;overflow:hidden}.bar div{height:100%;background:#3b9873}h1{font-size:26px}.muted{color:#64748b}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px}.calendar{display:grid;grid-template-columns:55px repeat(5,minmax(110px,1fr));overflow:auto}.cell{border:1px solid #e3e9f1;min-height:58px;padding:5px}.event{background:#dceafd;border-left:4px solid #2459bb;padding:5px;border-radius:4px;font-size:12px}</style>"""
def page(title,body):
 u=me()
 menu=("<nav><a href='/'>Tableau de bord</a> <a href='/planning'>Calendrier</a> <a href='/cours'>Cours</a> <a href='/notes'>Notes</a> <a href='/rapports'>Rapports</a> <a href='/logout'>Déconnexion</a></nav>" if u else "")
 return render_template_string(CSS+"<header><b>🎓 EduPilot</b> "+menu+"</header><main><h1>{{title}}</h1>"+body+"</main>",title=title)
def form(action,fields,button="Enregistrer"):
 return f"<form method='POST' action='{action}'><input type='hidden' name='csrf' value='{session['csrf']}'/>"+fields+f"<button>{button}</button></form>"
@app.get("/health")
def health():return {"status":"ok","app":"EduPilot"}
@app.route("/login",methods=["GET","POST"])
def login():
 if request.method=="POST":
  u=query("SELECT * FROM users WHERE email=?",(request.form.get("email",""),),True)
  if u and check_password_hash(u["hash"],request.form.get("password","")):session["uid"]=u["id"];return redirect("/")
  flash("Identifiants invalides")
 return page("Connexion","<p>Démo fictive : <code>admin1@demo.edupilot.test</code> / <code>Demo2026!</code></p>"+form("/login","<input name='email' placeholder='E-mail' required><input name='password' type='password' placeholder='Mot de passe' required>","Se connecter"))
@app.get("/logout")
def logout():session.clear();return redirect("/login")
@app.get("/")
def home():
 u=me()
 if not u:return redirect("/login")
 sid=u["school_id"]
 school=query("SELECT name FROM schools WHERE id=?",(sid,),True)
 if u["role"]=="superadmin":
  schools=query("SELECT * FROM schools")
  return page("Console Super Admin","<div class='grid'>"+"".join(f"<div class='card'><b>{s['name']}</b><p>/{s['slug']}</p><p>{s['plan']}</p></div>" for s in schools)+"</div>"+form("/school","<input name='name' placeholder='Nouvel établissement' required><select name='plan'><option>standard</option><option>premium</option></select>","Créer un établissement"))
 classes=query("SELECT * FROM classes WHERE school_id=?",(sid,))
 courses=query("SELECT * FROM courses WHERE school_id=?",(sid,))
 return page("Tableau de bord — "+(school["name"] if school else ""),f"<div class='grid'><div class='card'><b>Profil</b><p>{u['role']}</p></div><div class='card'><b>Classes</b><p>{len(classes)}</p></div><div class='card'><b>Cours</b><p>{len(courses)}</p></div></div><div class='card'>Bienvenue {u['name']}. Utilisez les menus pour explorer la démonstration.</div>")
@app.post("/school")
def school():
 require("superadmin")
 name=request.form["name"].strip()
 slug=unicodedata.normalize("NFKD",name).encode("ascii","ignore").decode().lower()
 slug=re.sub(r"[^a-z0-9]+","_",slug).strip("_")
 if not slug:abort(400)
 if query("SELECT id FROM schools WHERE slug=?",(slug,),True):abort(409)
 write("INSERT INTO schools(name,slug,plan) VALUES (?,?,?)",(name,slug,request.form.get("plan","standard")))
 return redirect("/")
@app.get("/planning")
def planning():
 u=require()
 sid=u["school_id"]
 mode=request.args.get("vue","semaine")
 rows=query("""SELECT l.*,c.title,cl.name classe FROM lessons l JOIN courses c ON c.id=l.course_id JOIN classes cl ON cl.id=c.class_id WHERE c.school_id=? ORDER BY starts""",(sid,)) if sid else []
 cell="<div class='calendar'><div class='cell'>Heure</div>"+''.join("<div class='cell'><b>"+d+"</b></div>" for d in ["Lundi","Mardi","Mercredi","Jeudi","Vendredi"])
 for hour in range(8,19):
  cell+=f"<div class='cell'>{hour:02d} h</div>"
  for weekday in range(5):
   subset=[r for r in rows if datetime.datetime.fromisoformat(r["starts"]).weekday()==weekday and datetime.datetime.fromisoformat(r["starts"]).hour==hour]
   cell+="<div class='cell'>"+"".join(f"<div class='event'>{r['title']}<br>{r['classe']}<br>{r['status']}</div>" for r in subset)+"</div>"
 cell+="</div>"
 return page("Emploi du temps — vue "+mode,"<p><a href='?vue=jour'>Jour</a> · <a href='?vue=semaine'>Semaine</a> · <a href='?vue=mois'>Mois</a></p>"+cell+"<p class='muted'>Démo V0.1 : la grille représente la semaine des séances fictives. Les modes Jour/Mois complets restent à intégrer.</p>")
@app.get("/cours")
def courses():
 u=require()
 sid=u["school_id"]
 courses=query("""SELECT c.*,cl.name classe,t.name enseignant FROM courses c JOIN classes cl ON c.class_id=cl.id LEFT JOIN users t ON c.teacher_id=t.id WHERE c.school_id=?""",(sid,)) if sid else []
 html="<table><tr><th>Cours</th><th>Classe</th><th>Enseignant</th><th>Volume prévu</th><th>Réalisé</th></tr>"
 for c in courses:
  r=query("SELECT COALESCE(SUM(actual_minutes),0) done FROM lessons WHERE course_id=? AND status='realisee'",(c["id"],),True)
  html+=f"<tr><td>{c['title']}</td><td>{c['classe']}</td><td>{c['enseignant']}</td><td>{c['minutes']/60:.0f} h</td><td>{r['done']/60:.1f} h</td></tr>"
 return page("Gestion des cours",html+"</table>"+("<h2>Déclarer une séance</h2>"+form("/realiser","<input type='number' name='lesson_id' min='1' placeholder='ID séance' required><input type='number' name='minutes' min='1' max='600' placeholder='Minutes réelles' required>","Confirmer séance") if u["role"] in ("admin","administratif","enseignant") else ""))
@app.post("/realiser")
def realize():
 u=require("admin","administratif","enseignant")
 lesson=query("SELECT l.*,c.school_id,c.teacher_id FROM lessons l JOIN courses c ON c.id=l.course_id WHERE l.id=?",(request.form.get("lesson_id"),),True)
 if not lesson or lesson["school_id"]!=u["school_id"] or (u["role"]=="enseignant" and lesson["teacher_id"]!=u["id"]):abort(403)
 if datetime.datetime.fromisoformat(lesson["ends"])>datetime.datetime.now():abort(400)
 minutes=int(request.form["minutes"])
 if minutes<1 or minutes>600:abort(400)
 write("UPDATE lessons SET status='realisee',actual_minutes=? WHERE id=?",(minutes,lesson["id"]))
 return redirect("/cours")
@app.get("/notes")
def notes():
 u=require()
 sid=u["school_id"]
 rows=query("""SELECT e.title evaluation,g.note,st.name eleve,cl.name classe,p.published FROM grades g JOIN evaluations e ON g.evaluation_id=e.id JOIN courses c ON c.id=e.course_id JOIN classes cl ON c.class_id=cl.id JOIN users st ON g.student_id=st.id LEFT JOIN periods p ON p.class_id=cl.id WHERE c.school_id=?""",(sid,)) if sid else []
 html="<table><tr><th>Élève</th><th>Classe</th><th>Évaluation</th><th>Note</th></tr>"
 for r in rows:
  if u["role"]=="etudiant" and r["eleve"]!=u["name"]:continue
  if u["role"] in ("etudiant","parent") and not r["published"]:continue
  html+=f"<tr><td>{r['eleve']}</td><td>{r['classe']}</td><td>{r['evaluation']}</td><td>{r['note']}/20</td></tr>"
 return page("Notes et évaluations",html+"</table><p class='muted'>Les résultats ne deviennent visibles aux élèves et parents qu'après publication administrative.</p>")
@app.get("/rapports")
def reports():
 u=require("admin","administratif")
 data=query("""SELECT c.title,c.minutes,COALESCE(SUM(CASE WHEN l.status='realisee' THEN l.actual_minutes ELSE 0 END),0) done,COUNT(l.id) sessions FROM courses c LEFT JOIN lessons l ON l.course_id=c.id WHERE c.school_id=? GROUP BY c.id""",(u["school_id"],))
 body="<table><tr><th>Cours</th><th>Prévu</th><th>Réalisé</th><th>Séances</th><th>Avancement</th></tr>"
 for c in data:
  pct=round(c["done"]/c["minutes"]*100) if c["minutes"] else 0
  body+=f"<tr><td>{c['title']}</td><td>{c['minutes']/60:.1f} h</td><td>{c['done']/60:.1f} h</td><td>{c['sessions']}</td><td>{pct}%<div class='bar'><div style='width:{min(100,pct)}%'></div></div></td></tr>"
 return page("Rapports pédagogiques",body+"</table>")
if __name__=="__main__":app.run(host="0.0.0.0",port=int(os.environ.get("PORT",5000)))
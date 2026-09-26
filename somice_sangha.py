import os
import sqlite3
import secrets
from functools import wraps
from pathlib import Path
from datetime import datetime
from flask import (
    Flask, request, redirect, url_for, session, render_template_string,
    flash, send_from_directory, abort
)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

# ============================================================
# พระสงฆ์สมไอซ์ — ระบบกฎหมายคณะสงฆ์และงานบริหาร
# Single-file Flask + SQLite
# ============================================================

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
UPLOAD_DIR = DATA_DIR / "uploads"
DB_PATH = DATA_DIR / "somice_sangha.db"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-this-secret-key-in-production")
app.config["MAX_CONTENT_LENGTH"] = 12 * 1024 * 1024

ADMIN_USER = os.environ.get("ADMIN_USER", "1389")
ADMIN_PASS = os.environ.get("ADMIN_PASS", "184224")

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp", "gif"}

# ------------------------- Database -------------------------

def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def init_db():
    conn = db()
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS laws (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sort_order INTEGER NOT NULL,
        title TEXT NOT NULL,
        section TEXT NOT NULL,
        content TEXT NOT NULL,
        penalty TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS temples (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        ordination_date TEXT NOT NULL DEFAULT '',
        temple TEXT NOT NULL DEFAULT '',
        status TEXT NOT NULL DEFAULT 'บวชแล้ว',
        source TEXT NOT NULL DEFAULT 'manual',
        created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS council (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        royal_name TEXT NOT NULL,
        active_date TEXT NOT NULL DEFAULT '',
        temple TEXT NOT NULL DEFAULT '',
        details TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS ordination_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        real_name TEXT NOT NULL,
        age INTEGER NOT NULL,
        temple TEXT NOT NULL,
        chant TEXT NOT NULL,
        kind TEXT NOT NULL,
        birth_temple TEXT NOT NULL,
        reason TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending',
        assigned_preceptor_id INTEGER,
        monastic_name TEXT NOT NULL DEFAULT '',
        ordination_date TEXT NOT NULL DEFAULT '',
        affiliated_temple TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL,
        FOREIGN KEY (assigned_preceptor_id) REFERENCES preceptors(id) ON DELETE SET NULL
    );

    CREATE TABLE IF NOT EXISTS preceptors (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL,
        display_name TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS employees (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL,
        display_name TEXT NOT NULL DEFAULT '',
        total_works INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS works (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        employee_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        work_count INTEGER NOT NULL,
        image_file TEXT NOT NULL DEFAULT '',
        status TEXT NOT NULL DEFAULT 'pending',
        created_at TEXT NOT NULL,
        FOREIGN KEY (employee_id) REFERENCES employees(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS study_applications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        employee_id INTEGER,
        name TEXT NOT NULL,
        type TEXT NOT NULL,
        vassa TEXT NOT NULL,
        level TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending',
        created_at TEXT NOT NULL,
        FOREIGN KEY (employee_id) REFERENCES employees(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS preceptor_applications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        employee_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        vassa TEXT NOT NULL,
        temple TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending',
        created_at TEXT NOT NULL,
        FOREIGN KEY (employee_id) REFERENCES employees(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS prayers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        link TEXT NOT NULL DEFAULT '',
        image_file TEXT NOT NULL DEFAULT '',
        body TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS salary_settings (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        is_open INTEGER NOT NULL DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS salary_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        employee_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        temple TEXT NOT NULL,
        total_works INTEGER NOT NULL DEFAULT 0,
        payment_channel TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending',
        created_at TEXT NOT NULL,
        FOREIGN KEY (employee_id) REFERENCES employees(id) ON DELETE CASCADE
    );
    """)
    # Small compatibility migrations for older SQLite databases.
    def add_column_if_missing(table, column, definition):
        cols = {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        if column not in cols:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    add_column_if_missing("temples", "source", "TEXT NOT NULL DEFAULT 'manual'")
    add_column_if_missing("temples", "source_ref", "TEXT NOT NULL DEFAULT ''")

    # Older builds sometimes made study_applications.employee_id NOT NULL.
    # Rebuild that table so public applications can enter the employee approval queue.
    cols = conn.execute("PRAGMA table_info(study_applications)").fetchall()
    emp_col = next((r for r in cols if r[1] == "employee_id"), None)
    if emp_col and emp_col[3] == 1:
        conn.execute("""CREATE TABLE IF NOT EXISTS study_applications_mig (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_id INTEGER,
            name TEXT NOT NULL, type TEXT NOT NULL, vassa TEXT NOT NULL,
            level TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending', created_at TEXT NOT NULL,
            FOREIGN KEY (employee_id) REFERENCES employees(id) ON DELETE CASCADE
        )""")
        conn.execute("""INSERT INTO study_applications_mig
            (id,employee_id,name,type,vassa,level,status,created_at)
            SELECT id,employee_id,name,type,vassa,level,status,created_at FROM study_applications""")
        conn.execute("DROP TABLE study_applications")
        conn.execute("ALTER TABLE study_applications_mig RENAME TO study_applications")

    conn.execute("INSERT OR IGNORE INTO salary_settings(id, is_open) VALUES (1, 0)")
    conn.commit()
    conn.close()

# Initialize before handling requests, including Gunicorn/Render.
init_db()

# ------------------------- Helpers -------------------------

def csrf_token():
    if "csrf" not in session:
        session["csrf"] = secrets.token_urlsafe(24)
    return session["csrf"]

def check_csrf():
    token = request.form.get("_csrf", "")
    return secrets.compare_digest(token, session.get("csrf", ""))

# Make the CSRF helper available inside all Jinja templates.
app.jinja_env.globals["csrf_token"] = csrf_token

def require_csrf():
    if not check_csrf():
        abort(400, "Invalid request token")

def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if session.get("role") != "admin":
            flash("กรุณาเข้าสู่ระบบผู้ดูแลก่อน", "error")
            return redirect(url_for("admin_login"))
        return fn(*args, **kwargs)
    return wrapper

def employee_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if session.get("role") != "employee":
            flash("กรุณาเข้าสู่ระบบพนักงานก่อน", "error")
            return redirect(url_for("employee_login"))
        return fn(*args, **kwargs)
    return wrapper

def preceptor_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if session.get("role") != "preceptor":
            flash("กรุณาเข้าสู่ระบบพระอุปัชฌาย์ก่อน", "error")
            return redirect(url_for("preceptor_login"))
        return fn(*args, **kwargs)
    return wrapper

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

def save_upload(file_storage, prefix):
    if not file_storage or not file_storage.filename:
        return ""
    if not allowed_file(file_storage.filename):
        raise ValueError("รองรับเฉพาะ PNG, JPG, JPEG, WEBP และ GIF")
    ext = secure_filename(file_storage.filename).rsplit(".", 1)[1].lower()
    filename = f"{prefix}_{secrets.token_hex(8)}.{ext}"
    file_storage.save(UPLOAD_DIR / filename)
    return filename

def next_law_order(conn):
    row = conn.execute("SELECT COALESCE(MAX(sort_order), 0) + 1 AS n FROM laws").fetchone()
    return int(row["n"])

def current_employee():
    if session.get("role") != "employee":
        return None
    conn = db()
    row = conn.execute("SELECT * FROM employees WHERE id=?", (session["user_id"],)).fetchone()
    conn.close()
    return row

# ------------------------- UI -------------------------

CSS = r"""
:root{
  --bg:#f4efe7; --paper:#fffdf9; --ink:#171512; --muted:#6d665e;
  --line:#ddd2c4; --accent:#7a4b24; --accent2:#b98245;
  --good:#2e6b43; --bad:#9a3c32; --shadow:0 10px 30px rgba(45,30,18,.08);
}
*{box-sizing:border-box}
body{margin:0;background:linear-gradient(135deg,#f7f2eb,#eee5d8);color:var(--ink);
font-family:system-ui,-apple-system,"Noto Sans Thai","Tahoma",sans-serif;line-height:1.65}
a{color:inherit;text-decoration:none}
.container{width:min(1120px,92%);margin:auto}
.topbar{position:sticky;top:0;z-index:10;background:rgba(255,253,249,.94);backdrop-filter:blur(10px);
border-bottom:1px solid var(--line)}
.nav{min-height:68px;display:flex;align-items:center;justify-content:space-between;gap:12px}
.brand{font-weight:900;letter-spacing:.2px}.brand small{display:block;font-weight:500;color:var(--muted);font-size:11px}
.navlinks{display:flex;gap:7px;flex-wrap:wrap;justify-content:flex-end}
.navlinks a,.btn{border:1px solid var(--line);border-radius:12px;padding:8px 12px;background:#fff;
font-weight:700;font-size:14px}
.navlinks a:hover,.btn:hover{border-color:var(--accent2);transform:translateY(-1px)}
.hero{padding:54px 0 28px}.hero h1{font-size:clamp(28px,5vw,48px);margin:0 0 10px}
.hero p{color:var(--muted);max-width:780px;margin:0}
.grid{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;padding:20px 0 44px}
.card{background:rgba(255,253,249,.96);border:1px solid var(--line);border-radius:20px;padding:20px;box-shadow:var(--shadow)}
.card h2,.card h3{margin-top:0}.card p{color:var(--muted)}
.icon{font-size:30px}.cardsmall{min-height:155px;display:flex;flex-direction:column;justify-content:space-between}
.section{padding:30px 0}.sectionhead{display:flex;justify-content:space-between;align-items:center;gap:12px;margin-bottom:16px}
.sectionhead h1{margin:0}.muted{color:var(--muted)}
.form{display:grid;gap:13px}.formgrid{display:grid;grid-template-columns:1fr 1fr;gap:14px}
label{font-weight:800;font-size:14px}input,textarea,select{width:100%;border:1px solid #cfc3b5;border-radius:12px;padding:12px;
font:inherit;background:#fff;color:var(--ink);outline:none}textarea{min-height:120px;resize:vertical}
input:focus,textarea:focus,select:focus{border-color:var(--accent2);box-shadow:0 0 0 3px rgba(185,130,69,.12)}
button{cursor:pointer}.btn{display:inline-block}.btn.primary{background:var(--accent);color:#fff;border-color:var(--accent)}
.btn.good{background:#edf7ef;border-color:#a9d0b2}.btn.bad{background:#fff0ee;border-color:#e1aaa3}
.btn.warn{background:#fff8e9;border-color:#e8c786}
.actions{display:flex;gap:8px;flex-wrap:wrap}.inline{display:inline}.tablewrap{overflow:auto}
table{width:100%;border-collapse:collapse;min-width:720px}th,td{padding:12px 10px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}
th{background:#f5eee4}.badge{display:inline-block;padding:3px 9px;border-radius:999px;background:#eee6db;font-size:12px;font-weight:800}
.badge.good{background:#e5f3e8}.badge.bad{background:#f8e3df}.badge.warn{background:#fff1cf}
.flash{margin:15px 0;padding:12px 14px;border-radius:12px;background:#fff;border:1px solid var(--line)}
.flash.error{border-color:#e1aaa3;background:#fff3f1}.flash.success{border-color:#abd1b3;background:#f0faf2}
.login{width:min(460px,92%);margin:60px auto}.login .card{padding:28px}
.adminbar{background:#201b16;color:#fff;padding:10px 0}.adminbar .nav{min-height:48px}.adminbar a{color:#fff}
.list{display:grid;gap:12px}.item{background:#fff;border:1px solid var(--line);border-radius:16px;padding:16px}
.kpi{font-size:30px;font-weight:900}.footer{padding:30px 0 60px;color:var(--muted);text-align:center}
img.preview{max-width:280px;max-height:220px;border-radius:14px;border:1px solid var(--line);display:block;margin-top:8px}
.empty{text-align:center;padding:28px;color:var(--muted)}
@media(max-width:800px){.grid{grid-template-columns:1fr 1fr}.formgrid{grid-template-columns:1fr}.nav{align-items:flex-start;padding:10px 0}.navlinks{justify-content:flex-start}}
@media(max-width:540px){.grid{grid-template-columns:1fr}.hero{padding-top:32px}.card{border-radius:16px}.navlinks a{font-size:12px;padding:7px 9px}}
"""

BASE = r"""
<!doctype html><html lang="th"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{{ title }} — พระสงฆ์สมไอซ์</title><style>{{ css|safe }}</style></head>
<body>
<header class="topbar"><div class="container nav">
<a class="brand" href="{{ url_for('home') }}">🙏 พระสงฆ์สมไอซ์<small>ระบบกฎหมายคณะสงฆ์และงานบริหาร</small></a>
<div class="navlinks">
<a href="{{ url_for('laws') }}">📜 กฎหมาย</a><a href="{{ url_for('temples') }}">🏯 ทะเบียนวัด</a>
<a href="{{ url_for('council') }}">🪷 มหาเถรสมาคม</a><a href="{{ url_for('prayers') }}">📖 บทสวด</a>
</div></div></header>
{% if session.get('role') in ['admin','employee','preceptor'] %}
<div class="adminbar"><div class="container nav">
<div>{{ {'admin':'ผู้ดูแลระบบ','employee':'ระบบพนักงาน','preceptor':'ระบบพระอุปัชฌาย์'}[session.get('role')] }}</div>
<div class="navlinks">
{% if session.get('role')=='admin' %}<a href="{{ url_for('admin') }}">หลังบ้าน</a>{% endif %}
{% if session.get('role')=='employee' %}<a href="{{ url_for('employee') }}">หน้าพนักงาน</a>{% endif %}
{% if session.get('role')=='preceptor' %}<a href="{{ url_for('preceptor') }}">หน้าอุปัชฌาย์</a>{% endif %}
<a href="{{ url_for('logout') }}">ออกจากระบบ</a></div></div></div>
{% endif %}
<main class="container">
{% with messages=get_flashed_messages(with_categories=true) %}
{% for category,message in messages %}<div class="flash {{ category }}">{{ message }}</div>{% endfor %}
{% endwith %}
{{ body|safe }}
</main>
<footer class="footer">พระสงฆ์สมไอซ์ • ระบบตัวอย่างสำหรับใช้งานภายในกลุ่ม</footer>
</body></html>
"""

def page(title, body, **ctx):
    return render_template_string(BASE, title=title, body=render_template_string(body, **ctx), css=CSS)

# ------------------------- Public -------------------------

@app.get("/")
def home():
    body = """
    <section class="hero">
      <h1>ระบบพระสงฆ์สมไอซ์</h1>
      <p>ศูนย์รวมกฎหมายคณะสงฆ์ ทะเบียน งานบวช การศึกษา ผลงาน และระบบบริหารภายในกลุ่ม</p>
    </section>
    <section class="grid">
      <a class="card cardsmall" href="{{ url_for('laws') }}"><div><div class="icon">📜</div><h3>กฎหมายคณะสงฆ์</h3><p>อ่านกฎหมายและมาตราที่ผู้ดูแลเพิ่มเข้าระบบ</p></div><b>เปิดดู →</b></a>
      <a class="card cardsmall" href="{{ url_for('temples') }}"><div><div class="icon">🏯</div><h3>ทะเบียนวัด</h3><p>รายชื่อพระ/เณรและสถานะการศึกษา</p></div><b>เปิดดู →</b></a>
      <a class="card cardsmall" href="{{ url_for('council') }}"><div><div class="icon">🪷</div><h3>ทะเบียนมหาเถรสมาคม</h3><p>ข้อมูลราชทินนามและวัดที่ประจำ</p></div><b>เปิดดู →</b></a>
      <a class="card cardsmall" href="{{ url_for('ordination') }}"><div><div class="icon">🙏</div><h3>ระบบบวช</h3><p>ยื่นคำขอบวชเพื่อส่งให้พระอุปัชฌาย์</p></div><b>ยื่นคำขอ →</b></a>
      <a class="card cardsmall" href="{{ url_for('education') }}"><div><div class="icon">📚</div><h3>สมัครเรียนนักธรรมและเปรียญธรรม</h3><p>ส่งใบสมัครเข้าสู่ระบบพนักงาน</p></div><b>สมัคร →</b></a>
      <a class="card cardsmall" href="{{ url_for('employee_login') }}"><div><div class="icon">👨‍💼</div><h3>ระบบพนักงาน</h3><p>ลงผลงาน สมัครเรียน และเบิกเงินเดือน</p></div><b>เข้าสู่ระบบ →</b></a>
      <a class="card cardsmall" href="{{ url_for('preceptor_login') }}"><div><div class="icon">🧘</div><h3>ระบบพระอุปัชฌาย์</h3><p>รับคำขอ อนุมัติ และบันทึกการบวช</p></div><b>เข้าสู่ระบบ →</b></a>
      <a class="card cardsmall" href="{{ url_for('prayers') }}"><div><div class="icon">📖</div><h3>บทสวดมนต์</h3><p>ข้อความ ลิงก์ และรูปบทสวด</p></div><b>เปิดดู →</b></a>
      <a class="card cardsmall" href="{{ url_for('admin_login') }}"><div><div class="icon">⚙️</div><h3>ระบบหลังบ้าน</h3><p>จัดการข้อมูลทั้งหมดของระบบ</p></div><b>Admin →</b></a>
    </section>
    """
    return page("หน้าแรก", body)

@app.get("/laws")
def laws():
    conn=db(); rows=conn.execute("SELECT * FROM laws ORDER BY sort_order,id").fetchall(); conn.close()
    body="""
    <section class="section"><div class="sectionhead"><h1>📜 กฎหมายคณะสงฆ์</h1><span class="badge">{{ laws|length }} รายการ</span></div>
    <div class="list">
    {% for x in laws %}<article class="item"><h2>{{ x.sort_order }}. {{ x.title }}</h2><p><b>มาตรา:</b> {{ x.section }}</p><p style="white-space:pre-wrap">{{ x.content }}</p>{% if x.penalty %}<p><b>โทษ/ความผิด:</b> {{ x.penalty }}</p>{% endif %}</article>
    {% else %}<div class="card empty">ยังไม่มีข้อมูลกฎหมาย</div>{% endfor %}</div></section>"""
    return page("กฎหมายคณะสงฆ์",body,laws=rows)

@app.route("/temples")
def temples():
    conn=db(); rows=conn.execute("SELECT * FROM temples ORDER BY id DESC").fetchall(); conn.close()
    body="""<section class="section"><div class="sectionhead"><h1>🏯 ทะเบียนวัด</h1></div>
    <div class="tablewrap"><table><tr><th>ลำดับ</th><th>ชื่อ/ฉายา</th><th>วันที่บวช</th><th>วัด</th><th>สถานะ</th></tr>
    {% for x in rows %}<tr><td>{{ loop.index }}</td><td>{{ x.name }}</td><td>{{ x.ordination_date or '-' }}</td><td>{{ x.temple }}</td><td><span class="badge">{{ x.status }}</span></td></tr>
    {% else %}<tr><td colspan="5" class="empty">ยังไม่มีรายชื่อ</td></tr>{% endfor %}</table></div></section>"""
    return page("ทะเบียนวัด",body,rows=rows)

@app.get("/council")
def council():
    conn=db(); rows=conn.execute("SELECT * FROM council ORDER BY id DESC").fetchall(); conn.close()
    body="""<section class="section"><h1>🪷 ทะเบียนมหาเถรสมาคม</h1><div class="list">
    {% for x in rows %}<article class="item"><h2>{{ x.royal_name }}</h2><p><b>วันที่ประจำ:</b> {{ x.active_date or '-' }}</p><p><b>วัด:</b> {{ x.temple }}</p><p style="white-space:pre-wrap">{{ x.details }}</p></article>
    {% else %}<div class="card empty">ยังไม่มีข้อมูล</div>{% endfor %}</div></section>"""
    return page("ทะเบียนมหาเถรสมาคม",body,rows=rows)

@app.route("/ordination", methods=["GET","POST"])
def ordination():
    if request.method=="POST":
        require_csrf()
        try:
            age=int(request.form.get("age","0"))
        except ValueError: age=0
        fields=["real_name","temple","chant","kind","birth_temple","reason"]
        if not request.form.get("real_name") or age < 1 or any(not request.form.get(f) for f in fields):
            flash("กรอกข้อมูลระบบบวชให้ครบ", "error")
        else:
            conn=db()
            real_name=request.form["real_name"].strip()
            temple=request.form["temple"].strip()
            chant=request.form["chant"].strip()
            kind=request.form["kind"].strip()
            birth_temple=request.form["birth_temple"].strip()
            reason=request.form["reason"].strip()
            if age < 1 or age > 120 or chant not in ("ได้","ไม่ได้") or kind not in ("พระ","เณร"):
                flash("ข้อมูลอายุ/ตัวเลือกไม่ถูกต้อง", "error")
            else:
                conn.execute("""INSERT INTO ordination_requests
                (real_name,age,temple,chant,kind,birth_temple,reason,status,created_at)
                VALUES(?,?,?,?,?,?,?, 'pending', ?)""",
                (real_name,age,temple,chant,kind,birth_temple,reason,now()))
                conn.commit(); flash("ส่งคำขอบวชเรียบร้อยแล้ว","success")
        return redirect(url_for("ordination"))
    conn=db(); rows=conn.execute("SELECT real_name,kind,status,created_at FROM ordination_requests ORDER BY id DESC LIMIT 20").fetchall(); conn.close()
    body="""<section class="section"><h1>🙏 ระบบบวช</h1><div class="card"><form class="form" method="post">
    <input type="hidden" name="_csrf" value="{{ csrf_token() }}"><div class="formgrid">
    <div><label>1. ชื่อจริง</label><input name="real_name" required></div>
    <div><label>2. อายุ</label><input name="age" type="number" min="1" max="120" required></div>
    <div><label>3. สังกัดวัด</label><input name="temple" required></div>
    <div><label>4. ท่องบทสวดได้</label><select name="chant"><option>ได้</option><option>ไม่ได้</option></select></div>
    <div><label>5. สถานะบวช</label><select name="kind"><option>พระ</option><option>เณร</option></select></div>
    <div><label>6. วัดเกิด</label><input name="birth_temple" required></div></div>
    <div><label>7. เหตุผล</label><textarea name="reason" required></textarea></div>
    <button class="btn primary" type="submit">ยืนยันส่งคำขอบวช</button></form></div>
    <h2>สถานะคำขอล่าสุด</h2><div class="list">{% for x in rows %}<div class="item"><b>{{x.real_name}}</b> • {{x.kind}} <span class="badge">{{x.status}}</span></div>{% else %}<div class="empty">ยังไม่มีคำขอ</div>{% endfor %}</div></section>"""
    return page("ระบบบวช",body,rows=rows)

@app.route("/education", methods=["GET","POST"])
def education():
    if request.method=="POST":
        require_csrf()
        conn=db()
        name=request.form.get("name","").strip(); typ=request.form.get("type","").strip(); vassa=request.form.get("vassa","").strip(); level=request.form.get("level","").strip()
        if not name or typ not in ("นักธรรม","เปรียญธรรม") or not vassa or not level:
            conn.close(); flash("กรอกข้อมูลสมัครเรียนให้ครบและถูกต้อง","error")
        else:
            dup=conn.execute("SELECT id FROM study_applications WHERE employee_id IS NULL AND name=? AND type=? AND level=? AND status='pending'",(name,typ,level)).fetchone()
            if dup:
                conn.close(); flash("มีใบสมัครเดียวกันที่กำลังรออนุมัติอยู่แล้ว","error")
            else:
                conn.execute("""INSERT INTO study_applications(employee_id,name,type,vassa,level,status,created_at)
                VALUES(NULL,?,?,?,?, 'pending', ?)""",
                (name,typ,vassa,level,now()))
                conn.commit(); conn.close(); flash("ส่งใบสมัครเข้าสู่ระบบพนักงานแล้ว","success")
        return redirect(url_for("education"))
    # Public form intentionally permits application without employee login; employee_id is linked later by admin/employee.
    body="""<section class="section"><h1>📚 สมัครเรียนนักธรรมและเปรียญธรรม</h1>
    <div class="grid">
    <div class="card"><h2>สมัครนักธรรม</h2><form class="form" method="post"><input type="hidden" name="_csrf" value="{{csrf_token()}}">
    <input type="hidden" name="type" value="นักธรรม"><label>ชื่อ</label><input name="name" required><label>พรรษา</label><input name="vassa" required>
    <label>ชั้นธรรมที่สมัคร</label><input name="level" placeholder="ตรี / โท / เอก" required><button class="btn primary">ส่งสมัครนักธรรม</button></form></div>
    <div class="card"><h2>สมัครเปรียญธรรม</h2><form class="form" method="post"><input type="hidden" name="_csrf" value="{{csrf_token()}}">
    <input type="hidden" name="type" value="เปรียญธรรม"><label>ชื่อ</label><input name="name" required><label>พรรษา</label><input name="vassa" required>
    <label>ชั้นที่จะสมัคร</label><input name="level" placeholder="ป.ธ. 1-2 / 3 / ..." required><button class="btn primary">ส่งสมัครเปรียญธรรม</button></form></div></div></section>"""
    return page("สมัครเรียน",body)

@app.get("/prayers")
def prayers():
    conn=db(); rows=conn.execute("SELECT * FROM prayers ORDER BY id DESC").fetchall(); conn.close()
    body="""<section class="section"><h1>📖 บทสวดมนต์</h1><div class="list">
    {% for x in rows %}<article class="item"><h2>{{x.title}}</h2>{% if x.body %}<p style="white-space:pre-wrap">{{x.body}}</p>{% endif %}
    {% if x.link %}<p><a class="btn" href="{{x.link}}" target="_blank" rel="noopener">เปิดลิงก์หนังสือสวดมนต์</a></p>{% endif %}
    {% if x.image_file %}<img class="preview" src="{{url_for('uploaded_file',filename=x.image_file)}}" alt="บทสวด">{% endif %}</article>
    {% else %}<div class="card empty">ยังไม่มีบทสวดมนต์</div>{% endfor %}</div></section>"""
    return page("บทสวดมนต์",body,rows=rows)

@app.get("/uploads/<path:filename>")
def uploaded_file(filename):
    return send_from_directory(UPLOAD_DIR, filename)

# ------------------------- Admin -------------------------

@app.route("/admin/login", methods=["GET","POST"])
def admin_login():
    if request.method=="POST":
        require_csrf()
        if request.form.get("username")==ADMIN_USER and request.form.get("password")==ADMIN_PASS:
            session.clear(); session["role"]="admin"; session["csrf"]=secrets.token_urlsafe(24)
            flash("เข้าสู่ระบบผู้ดูแลแล้ว","success"); return redirect(url_for("admin"))
        flash("ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง","error")
    body="""<section class="login"><div class="card"><h1>⚙️ เข้าสู่ระบบหลังบ้าน</h1>
    <form class="form" method="post"><input type="hidden" name="_csrf" value="{{csrf_token()}}">
    <label>ชื่อผู้ใช้</label><input name="username" autocomplete="username" required><label>รหัส</label><input name="password" type="password" autocomplete="current-password" required>
    <button class="btn primary">เข้าสู่ระบบ</button></form></div></section>"""
    return page("Admin Login",body)

@app.get("/admin/logout")
def admin_logout():
    session.clear(); return redirect(url_for("home"))

@app.get("/logout")
def logout():
    session.clear(); return redirect(url_for("home"))

@app.get("/admin")
@admin_required
def admin():
    conn=db()
    counts={
        "laws":conn.execute("SELECT COUNT(*) n FROM laws").fetchone()["n"],
        "temples":conn.execute("SELECT COUNT(*) n FROM temples").fetchone()["n"],
        "ord":conn.execute("SELECT COUNT(*) n FROM ordination_requests WHERE status='pending'").fetchone()["n"],
        "works":conn.execute("SELECT COUNT(*) n FROM works WHERE status='pending'").fetchone()["n"],
        "study":conn.execute("SELECT COUNT(*) n FROM study_applications WHERE status='pending'").fetchone()["n"],
        "preapp":conn.execute("SELECT COUNT(*) n FROM preceptor_applications WHERE status='pending'").fetchone()["n"],
        "salary":conn.execute("SELECT COUNT(*) n FROM salary_requests WHERE status='pending'").fetchone()["n"],
    }
    conn.close()
    body="""<section class="hero"><h1>⚙️ หลังบ้านผู้ดูแล</h1><p>จัดการข้อมูลและคำขอของระบบพระสงฆ์สมไอซ์</p></section>
    <section class="grid">
    <a class="card cardsmall" href="{{url_for('admin_laws')}}"><h3>📜 จัดการกฎหมาย</h3><div class="kpi">{{c.laws}}</div><span>เพิ่ม/ลบ/เรียงลำดับ</span></a>
    <a class="card cardsmall" href="{{url_for('admin_temple')}}"><h3>🏯 จัดการทะเบียนวัด</h3><div class="kpi">{{c.temples}}</div><span>เพิ่มบุคคลเข้าวัด</span></a>
    <a class="card cardsmall" href="{{url_for('admin_council')}}"><h3>🪷 จัดการมหาเถรสมาคม</h3><span>เพิ่ม/ลบข้อมูล</span></a>
    <a class="card cardsmall" href="{{url_for('admin_ordination')}}"><h3>🙏 คำขอบวช</h3><div class="kpi">{{c.ord}}</div><span>มอบหมายอุปัชฌาย์</span></a>
    <a class="card cardsmall" href="{{url_for('admin_employees')}}"><h3>👨‍💼 ระบบพนักงาน</h3><span>เพิ่มบัญชีพนักงาน</span></a>
    <a class="card cardsmall" href="{{url_for('admin_works')}}"><h3>🏆 อนุมัติผลงาน</h3><div class="kpi">{{c.works}}</div><span>อนุมัติ/ปฏิเสธ</span></a>
    <a class="card cardsmall" href="{{url_for('admin_study')}}"><h3>📚 ใบสมัครเรียน</h3><div class="kpi">{{c.study}}</div><span>พนักงานเป็นผู้อนุมัติ • Admin ตรวจสอบ</span></a>
    <a class="card cardsmall" href="{{url_for('admin_preceptor')}}"><h3>🧘 ระบบพระอุปัชฌาย์</h3><div class="kpi">{{c.preapp}}</div><span>บัญชี/สมัครอุปัชฌาย์</span></a>
    <a class="card cardsmall" href="{{url_for('admin_prayers')}}"><h3>📖 บทสวดมนต์</h3><span>ข้อความ/ลิงก์/รูป</span></a>
    <a class="card cardsmall" href="{{url_for('admin_salary')}}"><h3>💰 เงินเดือน</h3><div class="kpi">{{c.salary}}</div><span>เปิด/ปิดและอนุมัติคำขอ</span></a>
    </section>"""
    return page("หลังบ้าน",body,c=counts)

@app.route("/admin/laws", methods=["GET","POST"])
@admin_required
def admin_laws():
    conn=db()
    if request.method=="POST":
        require_csrf()
        action=request.form.get("action")
        if action=="add":
            title=request.form.get("title","").strip(); section=request.form.get("section","").strip()
            content=request.form.get("content","").strip(); penalty=request.form.get("penalty","").strip()
            if not title or not section or not content:
                flash("กรอกชื่อกฎหมาย มาตรา และเนื้อหาให้ครบ","error")
            else:
                conn.execute("INSERT INTO laws(sort_order,title,section,content,penalty,created_at) VALUES(?,?,?,?,?,?)",
                             (next_law_order(conn),title,section,content,penalty,now()))
                conn.commit(); flash("เพิ่มกฎหมายเรียบร้อย","success")
        elif action=="delete":
            lid=int(request.form.get("id",0))
            conn.execute("DELETE FROM laws WHERE id=?", (lid,)); conn.commit()
            # Re-number 1..N after deletion.
            rows=conn.execute("SELECT id FROM laws ORDER BY sort_order,id").fetchall()
            for i,row in enumerate(rows,1):
                conn.execute("UPDATE laws SET sort_order=? WHERE id=?",(i,row["id"]))
            conn.commit(); flash("ลบกฎหมายและจัดลำดับใหม่แล้ว","success")
        return redirect(url_for("admin_laws"))
    rows=conn.execute("SELECT * FROM laws ORDER BY sort_order,id").fetchall(); conn.close()
    body="""<section class="section"><div class="sectionhead"><h1>📜 จัดการกฎหมายคณะสงฆ์</h1><a class="btn" href="{{url_for('admin')}}">← หลังบ้าน</a></div>
    <div class="card"><h2>เพิ่มกฎหมาย</h2><form class="form" method="post"><input type="hidden" name="_csrf" value="{{csrf_token()}}"><input type="hidden" name="action" value="add">
    <label>ชื่อกฎหมาย</label><input name="title" required><label>มาตรา</label><input name="section" placeholder="เช่น มาตรา 1" required>
    <label>เนื้อหา</label><textarea name="content" required></textarea><label>โทษ/ความผิด</label><textarea name="penalty"></textarea>
    <button class="btn primary">ยืนยันเพิ่มกฎหมาย</button></form></div>
    <h2>รายการกฎหมายทั้งหมด</h2><div class="list">{% for x in rows %}<article class="item"><h3>{{x.sort_order}}. {{x.title}}</h3><p><b>{{x.section}}</b></p><p style="white-space:pre-wrap">{{x.content}}</p>{% if x.penalty %}<p><b>โทษ/ความผิด:</b> {{x.penalty}}</p>{% endif %}
    <form method="post" onsubmit="return confirm('ยืนยันการลบกฎหมายรายการนี้หรือไม่?');"><input type="hidden" name="_csrf" value="{{csrf_token()}}"><input type="hidden" name="action" value="delete"><input type="hidden" name="id" value="{{x.id}}"><button class="btn bad">ลบรายการนี้</button></form></article>{% else %}<div class="empty">ยังไม่มีรายการ</div>{% endfor %}</div></section>"""
    return page("จัดการกฎหมาย",body,rows=rows)

@app.route("/admin/temple", methods=["GET","POST"])
@admin_required
def admin_temple():
    conn=db()
    if request.method=="POST":
        require_csrf(); action=request.form.get("action")
        if action=="add":
            conn.execute("INSERT INTO temples(name,ordination_date,temple,status,source,created_at) VALUES(?,?,?,?,?,?)",
                         (request.form["name"],request.form.get("ordination_date",""),request.form["temple"],request.form.get("status","บวชแล้ว"),"manual",now()))
            conn.commit(); flash("เพิ่มบุคคลเข้าทะเบียนวัดแล้ว","success")
        elif action=="delete":
            conn.execute("DELETE FROM temples WHERE id=?",(request.form["id"],)); conn.commit(); flash("ลบรายการแล้ว","success")
        return redirect(url_for("admin_temple"))
    rows=conn.execute("SELECT * FROM temples ORDER BY id DESC").fetchall(); conn.close()
    body="""<section class="section"><h1>🏯 จัดการทะเบียนวัด</h1><div class="card"><form class="form" method="post">
    <input type="hidden" name="_csrf" value="{{csrf_token()}}"><input type="hidden" name="action" value="add">
    <div class="formgrid"><div><label>ชื่อ/ฉายา</label><input name="name" required></div><div><label>วันที่บวช</label><input name="ordination_date" type="date"></div>
    <div><label>วัดที่ประจำ</label><input name="temple" required></div><div><label>สถานะ</label><input name="status" value="บวชแล้ว"></div></div>
    <button class="btn primary">เพิ่มเข้าทะเบียนวัด</button></form></div>
    <div class="tablewrap"><table><tr><th>ชื่อ</th><th>วันที่บวช</th><th>วัด</th><th>สถานะ</th><th></th></tr>
    {% for x in rows %}<tr><td>{{x.name}}</td><td>{{x.ordination_date or '-'}}</td><td>{{x.temple}}</td><td>{{x.status}}</td><td><form method="post" onsubmit="return confirm('ยืนยันลบรายการนี้?')"><input type="hidden" name="_csrf" value="{{csrf_token()}}"><input type="hidden" name="action" value="delete"><input type="hidden" name="id" value="{{x.id}}"><button class="btn bad">ลบ</button></form></td></tr>{% endfor %}</table></div></section>"""
    return page("จัดการทะเบียนวัด",body,rows=rows)

@app.route("/admin/council", methods=["GET","POST"])
@admin_required
def admin_council():
    conn=db()
    if request.method=="POST":
        require_csrf()
        if request.form.get("action")=="add":
            conn.execute("INSERT INTO council(royal_name,active_date,temple,details,created_at) VALUES(?,?,?,?,?)",
                         (request.form["royal_name"],request.form.get("active_date",""),request.form["temple"],request.form.get("details",""),now()))
            conn.commit(); flash("เพิ่มทะเบียนมหาเถรสมาคมแล้ว","success")
        else:
            conn.execute("DELETE FROM council WHERE id=?",(request.form["id"],)); conn.commit(); flash("ลบรายการแล้ว","success")
        return redirect(url_for("admin_council"))
    rows=conn.execute("SELECT * FROM council ORDER BY id DESC").fetchall(); conn.close()
    body="""<section class="section"><h1>🪷 จัดการทะเบียนมหาเถรสมาคม</h1><div class="card"><form class="form" method="post">
    <input type="hidden" name="_csrf" value="{{csrf_token()}}"><input type="hidden" name="action" value="add">
    <label>ชื่อราชทินนาม</label><input name="royal_name" required><label>วันที่ประจำ</label><input name="active_date" type="date">
    <label>วัดที่ประจำการ</label><input name="temple" required><label>รายละเอียด</label><textarea name="details"></textarea><button class="btn primary">เพิ่มข้อมูล</button></form></div>
    <div class="list">{% for x in rows %}<div class="item"><h3>{{x.royal_name}}</h3><p>{{x.active_date}} • {{x.temple}}</p><p>{{x.details}}</p>
    <form method="post" onsubmit="return confirm('ยืนยันลบรายการนี้?')"><input type="hidden" name="_csrf" value="{{csrf_token()}}"><input type="hidden" name="id" value="{{x.id}}"><button class="btn bad">ลบ</button></form></div>{% endfor %}</div></section>"""
    return page("จัดการมหาเถรสมาคม",body,rows=rows)

@app.route("/admin/ordination", methods=["GET","POST"])
@admin_required
def admin_ordination():
    conn=db()
    if request.method=="POST":
        require_csrf(); action=request.form.get("action"); oid=int(request.form["id"])
        if action=="assign":
            try: pid=int(request.form["preceptor_id"])
            except (TypeError,ValueError): pid=0
            pre=conn.execute("SELECT id FROM preceptors WHERE id=?",(pid,)).fetchone()
            if not pre:
                flash("ไม่พบพระอุปัชฌาย์ที่เลือก", "error")
            else:
                cur=conn.execute("UPDATE ordination_requests SET assigned_preceptor_id=?,status='รออนุมัติจากพระอุปัชฌาย์' WHERE id=? AND status='pending'",(pid,oid))
                if not cur.rowcount:
                    flash("คำขอนี้ถูกมอบหมายหรือดำเนินการไปแล้ว", "error")
                else:
                    conn.commit(); flash("ส่งคำขอไปยังพระอุปัชฌาย์แล้ว","success")
        elif action=="reject":
            cur=conn.execute("UPDATE ordination_requests SET status='ปฏิเสธ' WHERE id=? AND status='pending'",(oid,))
            if cur.rowcount: conn.commit(); flash("ปฏิเสธคำขอแล้ว","success")
            else: flash("คำขอนี้ถูกดำเนินการไปแล้ว", "error")
        return redirect(url_for("admin_ordination"))
    rows=conn.execute("""SELECT o.*,p.username preceptor_username,p.display_name preceptor_name
                         FROM ordination_requests o LEFT JOIN preceptors p ON p.id=o.assigned_preceptor_id
                         ORDER BY o.id DESC""").fetchall()
    preceptors=conn.execute("SELECT * FROM preceptors ORDER BY id DESC").fetchall(); conn.close()
    body="""<section class="section"><h1>🙏 จัดการคำขอบวช</h1><div class="list">
    {% for x in rows %}<article class="item"><h3>{{x.real_name}} • {{x.kind}}</h3><p>อายุ {{x.age}} • สังกัด {{x.temple}} • ท่องบทสวด: {{x.chant}}</p><p>วัดเกิด: {{x.birth_temple}}</p><p>เหตุผล: {{x.reason}}</p><p>สถานะ: <span class="badge">{{x.status}}</span></p>
    {% if x.status=='pending' %}
    <form class="form" method="post" onsubmit="return confirm('ยืนยันส่งคำขอนี้ให้พระอุปัชฌาย์ที่เลือก?')"><input type="hidden" name="_csrf" value="{{csrf_token()}}"><input type="hidden" name="id" value="{{x.id}}"><input type="hidden" name="action" value="assign">
    <label>เลือกพระอุปัชฌาย์</label><select name="preceptor_id" required><option value="">-- เลือก --</option>{% for p in preceptors %}<option value="{{p.id}}">{{p.display_name or p.username}} ({{p.username}})</option>{% endfor %}</select><button class="btn primary">ส่งให้พระอุปัชฌาย์</button></form>
    {% endif %}{% if x.status=='pending' %}<form method="post" style="margin-top:8px" onsubmit="return confirm('ยืนยันปฏิเสธคำขอบวชนี้?')"><input type="hidden" name="_csrf" value="{{csrf_token()}}"><input type="hidden" name="id" value="{{x.id}}"><input type="hidden" name="action" value="reject"><button class="btn bad">ปฏิเสธ</button></form>{% endif %}
    </article>{% else %}<div class="empty">ไม่มีคำขอ</div>{% endfor %}</div></section>"""
    return page("คำขอบวช",body,rows=rows,preceptors=preceptors)

@app.route("/admin/employees", methods=["GET","POST"])
@admin_required
def admin_employees():
    conn=db()
    if request.method=="POST":
        require_csrf()
        username=request.form["username"].strip(); password=request.form["password"]; display=request.form.get("display_name","").strip()
        try:
            conn.execute("INSERT INTO employees(username,password_hash,display_name,created_at) VALUES(?,?,?,?)",
                         (username,generate_password_hash(password),display,now()))
            conn.commit(); flash("เพิ่มบัญชีพนักงานแล้ว","success")
        except sqlite3.IntegrityError: flash("ชื่อผู้ใช้นี้มีอยู่แล้ว","error")
        return redirect(url_for("admin_employees"))
    rows=conn.execute("SELECT id,username,display_name,total_works,created_at FROM employees ORDER BY id DESC").fetchall(); conn.close()
    body="""<section class="section"><h1>👨‍💼 ระบบพนักงาน</h1><div class="card"><form class="form" method="post">
    <input type="hidden" name="_csrf" value="{{csrf_token()}}"><div class="formgrid"><div><label>ชื่อผู้ใช้</label><input name="username" required></div>
    <div><label>รหัสผู้ใช้</label><input name="password" type="password" required></div><div><label>ชื่อ</label><input name="display_name"></div></div><button class="btn primary">เพิ่มบัญชีพนักงาน</button></form></div>
    <div class="tablewrap"><table><tr><th>ชื่อผู้ใช้</th><th>ชื่อ</th><th>ผลงานสะสม</th></tr>{% for x in rows %}<tr><td>{{x.username}}</td><td>{{x.display_name}}</td><td>{{x.total_works}}</td></tr>{% endfor %}</table></div></section>"""
    return page("ระบบพนักงาน",body,rows=rows)

@app.route("/admin/works", methods=["GET","POST"])
@admin_required
def admin_works():
    conn=db()
    if request.method=="POST":
        require_csrf(); wid=int(request.form["id"]); action=request.form["action"]
        row=conn.execute("SELECT * FROM works WHERE id=?",(wid,)).fetchone()
        if row and row["status"]=="pending" and action in ("approve","reject"):
            status="approved" if action=="approve" else "rejected"
            cur=conn.execute("UPDATE works SET status=? WHERE id=? AND status='pending'",(status,wid))
            if cur.rowcount:
                if status=="approved":
                    conn.execute("UPDATE employees SET total_works=total_works+? WHERE id=?",(row["work_count"],row["employee_id"]))
                conn.commit(); flash("อนุมัติ/ปฏิเสธผลงานเรียบร้อยแล้ว","success")
            else:
                flash("รายการนี้ถูกดำเนินการไปแล้ว","error")
        return redirect(url_for("admin_works"))
    rows=conn.execute("""SELECT w.*,e.username,e.display_name FROM works w JOIN employees e ON e.id=w.employee_id ORDER BY w.id DESC""").fetchall(); conn.close()
    body="""<section class="section"><h1>🏆 อนุมัติผลงาน</h1><div class="list">{% for x in rows %}<article class="item"><h3>{{x.name}} • {{x.work_count}} ผลงาน</h3>
    <p>พนักงาน: {{x.display_name or x.username}} • <span class="badge">{{x.status}}</span></p>{% if x.image_file %}<img class="preview" src="{{url_for('uploaded_file',filename=x.image_file)}}">{% endif %}
    {% if x.status=='pending' %}<div class="actions"><form method="post" onsubmit="return confirm('ยืนยันอนุมัติผลงานรายการนี้?')"><input type="hidden" name="_csrf" value="{{csrf_token()}}"><input type="hidden" name="id" value="{{x.id}}"><input type="hidden" name="action" value="approve"><button class="btn good">อนุมัติ</button></form>
    <form method="post" onsubmit="return confirm('ยืนยันปฏิเสธผลงานรายการนี้?')"><input type="hidden" name="_csrf" value="{{csrf_token()}}"><input type="hidden" name="id" value="{{x.id}}"><input type="hidden" name="action" value="reject"><button class="btn bad">ปฏิเสธ</button></form></div>{% endif %}</article>{% else %}<div class="empty">ไม่มีรายการ</div>{% endfor %}</div></section>"""
    return page("อนุมัติผลงาน",body,rows=rows)

@app.get("/admin/study")
@admin_required
def admin_study():
    conn=db()
    rows=conn.execute("SELECT s.*,e.username,e.display_name FROM study_applications s LEFT JOIN employees e ON e.id=s.employee_id ORDER BY s.id DESC").fetchall()
    conn.close()
    body="""<section class="section"><h1>📚 ใบสมัครนักธรรม/เปรียญธรรม</h1>
    <div class="card"><p><b>ผู้อนุมัติหลัก:</b> ระบบพนักงาน</p><p class="muted">หน้านี้สำหรับผู้ดูแลตรวจสอบสถานะเท่านั้น เพื่อป้องกันการอนุมัติซ้ำจากหลายระบบ</p></div>
    <div class="list">{% for x in rows %}<article class="item"><h3>{{x.name}} • {{x.type}} {{x.level}}</h3>
    <p>พรรษา {{x.vassa}} • ผู้ส่ง: {{x.display_name or x.username or 'สมัครจากหน้าแรก'}} • <span class="badge">{{x.status}}</span></p>
    {% else %}<div class="empty">ยังไม่มีใบสมัคร</div>{% endfor %}</div></section>"""
    return page("ตรวจสอบใบสมัครเรียน",body,rows=rows)

@app.route("/admin/preceptor", methods=["GET","POST"])
@admin_required
def admin_preceptor():
    conn=db()
    if request.method=="POST":
        require_csrf(); action=request.form.get("action")
        if action=="create":
            try:
                conn.execute("INSERT INTO preceptors(username,password_hash,display_name,created_at) VALUES(?,?,?,?)",
                             (request.form["username"],generate_password_hash(request.form["password"]),request.form.get("display_name",""),now()))
                conn.commit(); flash("สร้างบัญชีพระอุปัชฌาย์แล้ว","success")
            except sqlite3.IntegrityError: flash("ชื่อผู้ใช้นี้มีอยู่แล้ว","error")
        elif action in ("approve","reject"):
            pid=int(request.form["id"])
            row=conn.execute("SELECT * FROM preceptor_applications WHERE id=? AND status='pending'",(pid,)).fetchone()
            if not row:
                flash("คำขอนี้ถูกดำเนินการไปแล้วหรือไม่พบข้อมูล", "error")
            else:
                status="approved" if action=="approve" else "rejected"
                conn.execute("UPDATE preceptor_applications SET status=? WHERE id=? AND status='pending'",(status,pid))
                if status=="approved":
                    # Avoid duplicate temple entries if the request is ever retried.
                    exists=conn.execute("SELECT id FROM temples WHERE source='preceptor_application' AND source_ref=?",(str(row["id"]),)).fetchone()
                    if not exists:
                        conn.execute("INSERT INTO temples(name,ordination_date,temple,status,source,source_ref,created_at) VALUES(?,?,?,?,?,?,?)",
                                     (row["name"],"",row["temple"],"รอสอบอุปัชฌาย์","preceptor_application",str(row["id"]),now()))
                conn.commit(); flash("ดำเนินการสมัครอุปัชฌาย์แล้ว","success")
        return redirect(url_for("admin_preceptor"))
    preceptors=conn.execute("SELECT * FROM preceptors ORDER BY id DESC").fetchall()
    apps=conn.execute("SELECT a.*,e.username FROM preceptor_applications a LEFT JOIN employees e ON e.id=a.employee_id ORDER BY a.id DESC").fetchall()
    conn.close()
    body="""<section class="section"><h1>🧘 ระบบพระอุปัชฌาย์</h1><div class="card"><h2>เพิ่มบัญชีพระอุปัชฌาย์</h2><form class="form" method="post"><input type="hidden" name="_csrf" value="{{csrf_token()}}"><input type="hidden" name="action" value="create">
    <div class="formgrid"><div><label>ชื่อผู้ใช้</label><input name="username" required></div><div><label>รหัสผู้ใช้</label><input name="password" type="password" required></div><div><label>ชื่อ</label><input name="display_name"></div></div><button class="btn primary">สร้างบัญชี</button></form></div>
    <h2>คำขอสมัครอุปัชฌาย์</h2><div class="list">{% for x in apps %}<div class="item"><h3>{{x.name}}</h3><p>พรรษา {{x.vassa}} • {{x.temple}} • <span class="badge">{{x.status}}</span></p>{% if x.status=='pending' %}<div class="actions"><form method="post" onsubmit="return confirm('ยืนยันการดำเนินการกับคำขอนี้?')"><input type="hidden" name="_csrf" value="{{csrf_token()}}"><input type="hidden" name="id" value="{{x.id}}"><button class="btn good" name="action" value="approve">อนุมัติ</button><button class="btn bad" name="action" value="reject">ปฏิเสธ</button></form></div>{% endif %}</div>{% else %}<div class="empty">ไม่มีคำขอ</div>{% endfor %}</div>
    <h2>บัญชีพระอุปัชฌาย์</h2><div class="tablewrap"><table><tr><th>ผู้ใช้</th><th>ชื่อ</th></tr>{% for x in preceptors %}<tr><td>{{x.username}}</td><td>{{x.display_name}}</td></tr>{% endfor %}</table></div></section>"""
    return page("ระบบพระอุปัชฌาย์",body,preceptors=preceptors,apps=apps)

@app.route("/admin/prayers", methods=["GET","POST"])
@admin_required
def admin_prayers():
    conn=db()
    if request.method=="POST":
        require_csrf()
        if request.form.get("action")=="delete":
            conn.execute("DELETE FROM prayers WHERE id=?",(request.form["id"],)); conn.commit(); flash("ลบบทสวดแล้ว","success")
        else:
            img=save_upload(request.files.get("image"),"prayer")
            conn.execute("INSERT INTO prayers(title,link,image_file,body,created_at) VALUES(?,?,?,?,?)",
                         (request.form["title"],request.form.get("link",""),img,request.form.get("body",""),now()))
            conn.commit(); flash("เพิ่มบทสวดแล้ว","success")
        return redirect(url_for("admin_prayers"))
    rows=conn.execute("SELECT * FROM prayers ORDER BY id DESC").fetchall(); conn.close()
    body="""<section class="section"><h1>📖 จัดการบทสวดมนต์</h1><div class="card"><form class="form" method="post" enctype="multipart/form-data">
    <input type="hidden" name="_csrf" value="{{csrf_token()}}"><label>ชื่อบทสวด/หนังสือ</label><input name="title" required><label>ลิงก์</label><input name="link" type="url" placeholder="https://..."><label>รูปภาพ</label><input name="image" type="file" accept="image/*"><label>ข้อความบทสวด</label><textarea name="body"></textarea><button class="btn primary">เพิ่มบทสวด</button></form></div>
    <div class="list">{% for x in rows %}<div class="item"><h3>{{x.title}}</h3>{% if x.link %}<p>{{x.link}}</p>{% endif %}{% if x.image_file %}<img class="preview" src="{{url_for('uploaded_file',filename=x.image_file)}}">{% endif %}<form method="post" onsubmit="return confirm('ยืนยันลบบทสวดนี้?')"><input type="hidden" name="_csrf" value="{{csrf_token()}}"><input type="hidden" name="action" value="delete"><input type="hidden" name="id" value="{{x.id}}"><button class="btn bad">ลบ</button></form></div>{% endfor %}</div></section>"""
    return page("จัดการบทสวด",body,rows=rows)

@app.route("/admin/salary", methods=["GET","POST"])
@admin_required
def admin_salary():
    conn=db()
    if request.method=="POST":
        require_csrf(); action=request.form.get("action")
        if action=="toggle":
            openv=int(request.form["value"]); conn.execute("UPDATE salary_settings SET is_open=? WHERE id=1",(openv,)); conn.commit()
            flash("เปลี่ยนสถานะการรับคำขอเงินเดือนแล้ว","success")
        elif action in ("approve","reject"):
            rid=int(request.form["id"]); status="approved" if action=="approve" else "rejected"
            cur=conn.execute("UPDATE salary_requests SET status=? WHERE id=? AND status='pending'",(status,rid))
            if cur.rowcount:
                conn.commit(); flash("ดำเนินการคำขอเงินเดือนแล้ว","success")
            else:
                flash("คำขอนี้ถูกดำเนินการไปแล้ว","error")
        elif action=="delete":
            cur=conn.execute("DELETE FROM salary_requests WHERE id=? AND status='approved'",(request.form["id"],))
            if cur.rowcount:
                conn.commit(); flash("ลบรายการหลังยืนยันว่าจ่ายเงินแล้ว","success")
            else:
                flash("ลบได้เฉพาะรายการที่อนุมัติแล้ว","error")
        return redirect(url_for("admin_salary"))
    setting=conn.execute("SELECT is_open FROM salary_settings WHERE id=1").fetchone()
    rows=conn.execute("SELECT s.*,e.username,e.display_name FROM salary_requests s JOIN employees e ON e.id=s.employee_id ORDER BY s.id DESC").fetchall(); conn.close()
    body="""<section class="section"><h1>💰 ระบบเงินเดือน</h1><div class="card"><h2>รับคำขอเงินเดือน: <span class="badge {{'good' if setting.is_open else 'bad'}}">{{'เปิดรับ' if setting.is_open else 'ปิดรับ'}}</span></h2>
    <div class="actions"><form method="post"><input type="hidden" name="_csrf" value="{{csrf_token()}}"><input type="hidden" name="action" value="toggle"><input type="hidden" name="value" value="1"><button class="btn good">เปิดรับเงินเดือน</button></form>
    <form method="post"><input type="hidden" name="_csrf" value="{{csrf_token()}}"><input type="hidden" name="action" value="toggle"><input type="hidden" name="value" value="0"><button class="btn bad">ปิดรับเงินเดือน</button></form></div></div>
    <h2>คำขอเงินเดือน</h2><div class="list">{% for x in rows %}<article class="item"><h3>{{x.name}} • {{x.total_works}} ผลงาน</h3><p>วัด: {{x.temple}} • ช่องทาง: {{x.payment_channel}}</p><p>สถานะ: <span class="badge">{{x.status}}</span></p>
    {% if x.status=='pending' %}<form method="post" onsubmit="return confirm('ยืนยันการดำเนินการกับคำขอเงินเดือนนี้?')"><input type="hidden" name="_csrf" value="{{csrf_token()}}"><input type="hidden" name="id" value="{{x.id}}"><button class="btn good" name="action" value="approve">อนุมัติ</button><button class="btn bad" name="action" value="reject">ปฏิเสธ</button></form>{% elif x.status=='approved' %}<p><b>ช่องทางรับเงิน:</b> {{x.payment_channel}}</p><form method="post" onsubmit="return confirm('ยืนยันว่าจ่ายเงินแล้วและต้องการลบรายการนี้?')"><input type="hidden" name="_csrf" value="{{csrf_token()}}"><input type="hidden" name="id" value="{{x.id}}"><button class="btn warn" name="action" value="delete">ลบหลังจ่ายเงิน</button></form>{% endif %}</article>{% else %}<div class="empty">ไม่มีคำขอ</div>{% endfor %}</div></section>"""
    return page("ระบบเงินเดือน",body,setting=setting,rows=rows)

# ------------------------- Employee -------------------------

@app.route("/employee/login", methods=["GET","POST"])
def employee_login():
    if request.method=="POST":
        require_csrf(); conn=db()
        row=conn.execute("SELECT * FROM employees WHERE username=?",(request.form["username"],)).fetchone(); conn.close()
        if row and check_password_hash(row["password_hash"],request.form["password"]):
            session.clear(); session["role"]="employee"; session["user_id"]=row["id"]; session["csrf"]=secrets.token_urlsafe(24)
            return redirect(url_for("employee"))
        flash("ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง","error")
    body="""<section class="login"><div class="card"><h1>👨‍💼 ระบบพนักงาน</h1><form class="form" method="post"><input type="hidden" name="_csrf" value="{{csrf_token()}}">
    <label>ชื่อ</label><input name="username" required><label>รหัส</label><input name="password" type="password" required><button class="btn primary">เข้าสู่ระบบ</button></form></div></section>"""
    return page("เข้าสู่ระบบพนักงาน",body)

@app.route("/employee", methods=["GET","POST"])
@employee_required
def employee():
    emp=current_employee()
    conn=db()
    if request.method=="POST":
        require_csrf(); action=request.form["action"]
        if action=="work":
            name=request.form.get("name","").strip()
            try: count=int(request.form.get("work_count","0"))
            except (TypeError,ValueError): count=0
            if not name or count < 1 or count > 100000:
                flash("กรอกชื่อผลงานและจำนวนผลงานให้ถูกต้อง (1-100000)","error")
            else:
                img=save_upload(request.files.get("image"),"work")
                conn.execute("INSERT INTO works(employee_id,name,work_count,image_file,created_at) VALUES(?,?,?,?,?)",
                             (emp["id"],name,count,img,now())); conn.commit(); flash("ส่งผลงานรออนุมัติแล้ว","success")
        elif action=="study":
            name=request.form.get("name","").strip(); typ=request.form.get("type","").strip(); vassa=request.form.get("vassa","").strip(); level=request.form.get("level","").strip()
            if not name or typ not in ("นักธรรม","เปรียญธรรม") or not vassa or not level:
                flash("กรอกข้อมูลสมัครเรียนให้ครบและถูกต้อง","error")
            else:
                dup=conn.execute("SELECT id FROM study_applications WHERE employee_id=? AND name=? AND type=? AND level=? AND status='pending'",(emp["id"],name,typ,level)).fetchone()
                if dup: flash("มีใบสมัครรายการเดียวกันที่กำลังรออนุมัติอยู่แล้ว","error")
                else:
                    conn.execute("INSERT INTO study_applications(employee_id,name,type,vassa,level,created_at) VALUES(?,?,?,?,?,?)",
                                 (emp["id"],name,typ,vassa,level,now())); conn.commit(); flash("ส่งสมัครเรียนแล้ว","success")
        elif action=="study_approve" or action=="study_reject":
            sid=int(request.form["study_id"])
            row=conn.execute("SELECT * FROM study_applications WHERE id=? AND status='pending' AND (employee_id IS NULL OR employee_id != ?)",(sid,emp['id'])).fetchone()
            if not row:
                flash("ใบสมัครนี้ถูกดำเนินการไปแล้วหรือไม่พบข้อมูล", "error")
            elif action=="study_reject":
                cur=conn.execute("UPDATE study_applications SET status='rejected',employee_id=COALESCE(employee_id,?) WHERE id=? AND status='pending'",(emp["id"],sid))
                if cur.rowcount:
                    conn.commit(); flash("ปฏิเสธใบสมัครเรียนแล้ว","success")
            else:
                temple=request.form.get("temple","").strip()
                if not temple:
                    flash("ต้องระบุวัดก่อนอนุมัติใบสมัคร", "error")
                else:
                    cur=conn.execute("UPDATE study_applications SET status='approved',employee_id=COALESCE(employee_id,?) WHERE id=? AND status='pending'",(emp["id"],sid))
                    if cur.rowcount:
                        label=f"รอสอบ{row['type']} {row['level']}"
                        conn.execute("""INSERT INTO temples(name,ordination_date,temple,status,source,source_ref,created_at)
                                       SELECT ?,?,?,?,?,?,? WHERE NOT EXISTS (SELECT 1 FROM temples WHERE source='study' AND source_ref=?)""",
                                     (row["name"],"",temple,label,"study",str(sid),now(),str(sid)))
                        conn.commit(); flash("อนุมัติใบสมัครเรียนและเพิ่มสถานะในทะเบียนวัดแล้ว","success")
                    else:
                        flash("ใบสมัครนี้ถูกดำเนินการไปแล้ว", "error")
        elif action=="preceptor_apply":
            name=request.form.get("name","").strip(); vassa=request.form.get("vassa","").strip(); temple=request.form.get("temple","").strip()
            if not name or not vassa or not temple:
                flash("กรอกข้อมูลสมัครอุปัชฌาย์ให้ครบ","error")
            else:
                dup=conn.execute("SELECT id FROM preceptor_applications WHERE employee_id=? AND status='pending'",(emp["id"],)).fetchone()
                if dup: flash("มีคำขอสมัครอุปัชฌาย์ที่กำลังรออนุมัติอยู่แล้ว","error")
                else:
                    conn.execute("INSERT INTO preceptor_applications(employee_id,name,vassa,temple,created_at) VALUES(?,?,?,?,?)",
                                 (emp["id"],name,vassa,temple,now())); conn.commit(); flash("ส่งสมัครอุปัชฌาย์แล้ว","success")
        elif action=="salary":
            setting=conn.execute("SELECT is_open FROM salary_settings WHERE id=1").fetchone()
            if not setting["is_open"]:
                flash("ขณะนี้ปิดรับคำขอเงินเดือน","error")
            else:
                name=request.form.get("name","").strip(); temple=request.form.get("temple","").strip(); channel=request.form.get("payment_channel","").strip()
                try: total_works=int(request.form.get("total_works","0"))
                except (TypeError,ValueError): total_works=-1
                if not name or not temple or not channel or total_works < 0:
                    flash("กรอกข้อมูลเงินเดือนให้ครบและถูกต้อง","error")
                else:
                    dup=conn.execute("SELECT id FROM salary_requests WHERE employee_id=? AND status='pending'",(emp["id"],)).fetchone()
                    if dup: flash("มีคำขอเงินเดือนที่กำลังรออนุมัติอยู่แล้ว","error")
                    else:
                        conn.execute("INSERT INTO salary_requests(employee_id,name,temple,total_works,payment_channel,created_at) VALUES(?,?,?,?,?,?)",
                                     (emp["id"],name,temple,total_works,channel,now()))
                        conn.commit(); flash("ส่งคำขอเงินเดือนแล้ว","success")
        return redirect(url_for("employee"))
    works=conn.execute("SELECT * FROM works WHERE employee_id=? ORDER BY id DESC",(emp["id"],)).fetchall()
    study=conn.execute("SELECT * FROM study_applications WHERE employee_id=? OR employee_id IS NULL ORDER BY id DESC",(emp["id"],)).fetchall()
    pending_public_study=conn.execute("SELECT * FROM study_applications WHERE status='pending' AND (employee_id IS NULL OR employee_id != ?) ORDER BY id DESC",(emp['id'],)).fetchall()
    preapps=conn.execute("SELECT * FROM preceptor_applications WHERE employee_id=? ORDER BY id DESC",(emp["id"],)).fetchall()
    setting=conn.execute("SELECT is_open FROM salary_settings WHERE id=1").fetchone()
    salary=conn.execute("SELECT * FROM salary_requests WHERE employee_id=? ORDER BY id DESC",(emp["id"],)).fetchall(); conn.close()
    body="""<section class="section"><div class="sectionhead"><div><h1>👨‍💼 {{emp.display_name or emp.username}}</h1><p class="muted">ผลงานสะสม <b>{{emp.total_works}}</b> รายการ</p></div></div>
    <div class="grid">
    <div class="card"><h2>🏆 ลงผลงาน</h2><form class="form" method="post" enctype="multipart/form-data"><input type="hidden" name="_csrf" value="{{csrf_token()}}"><input type="hidden" name="action" value="work">
    <label>ชื่อผลงาน/ชื่อ</label><input name="name" required><label>จำนวนผลงาน</label><input name="work_count" type="number" min="1" required><label>รูปภาพผลงาน</label><input name="image" type="file" accept="image/*"><button class="btn primary">ส่งผลงาน</button></form></div>
    <div class="card"><h2>📚 สมัครนักธรรม/เปรียญธรรม</h2><form class="form" method="post"><input type="hidden" name="_csrf" value="{{csrf_token()}}"><input type="hidden" name="action" value="study">
    <label>ชื่อ</label><input name="name" required><label>ประเภท</label><select name="type"><option>นักธรรม</option><option>เปรียญธรรม</option></select><label>พรรษา</label><input name="vassa" required><label>ชั้น</label><input name="level" required><button class="btn primary">ส่งสมัคร</button></form></div>
    <div class="card"><h2>📚 อนุมัติใบสมัครเรียน</h2><p class="muted">ใบสมัครที่ส่งจากหน้าแรกจะมารอที่นี่</p>
    {% for x in pending_public_study %}<form class="form" method="post" style="border-top:1px solid var(--line);padding-top:10px;margin-top:10px"><input type="hidden" name="_csrf" value="{{csrf_token()}}"><input type="hidden" name="study_id" value="{{x.id}}"><input name="temple" placeholder="วัดสำหรับทะเบียนวัด" required value=""><b>{{x.name}} • {{x.type}} {{x.level}} • พรรษา {{x.vassa}}</b><div class="actions"><button class="btn good" name="action" value="study_approve" onclick="return confirm('ยืนยันอนุมัติใบสมัครเรียนนี้?')">อนุมัติ</button><button class="btn bad" name="action" value="study_reject" onclick="return confirm('ยืนยันปฏิเสธใบสมัครเรียนนี้?')">ปฏิเสธ</button></div></form>{% else %}<p>ไม่มีใบสมัครรออนุมัติ</p>{% endfor %}</div>
    <div class="card"><h2>🧘 สมัครอุปัชฌาย์</h2><form class="form" method="post"><input type="hidden" name="_csrf" value="{{csrf_token()}}"><input type="hidden" name="action" value="preceptor_apply">
    <label>ชื่อ</label><input name="name" required><label>พรรษา</label><input name="vassa" required><label>สังกัดวัด</label><input name="temple" required><button class="btn primary">ส่งสมัคร</button></form></div>
    <div class="card"><h2>💰 เบิกเงินเดือน</h2>{% if setting.is_open %}<form class="form" method="post"><input type="hidden" name="_csrf" value="{{csrf_token()}}"><input type="hidden" name="action" value="salary">
    <label>ชื่อ</label><input name="name" required><label>สังกัดวัด</label><input name="temple" required><label>ผลงานทั้งหมด</label><input name="total_works" type="number" min="0" value="{{emp.total_works}}" required><label>ช่องทางรับเงิน</label><input name="payment_channel" placeholder="เช่น พร้อมเพย์/บัญชี..." required><button class="btn primary">ส่งคำขอเงินเดือน</button></form>{% else %}<p>ผู้ดูแลยังไม่เปิดรับคำขอเงินเดือน</p>{% endif %}</div></div>
    <h2>ประวัติผลงาน</h2><div class="list">{% for x in works %}<div class="item">{{x.name}} • {{x.work_count}} • <span class="badge">{{x.status}}</span>{% if x.image_file %}<img class="preview" src="{{url_for('uploaded_file',filename=x.image_file)}}">{% endif %}</div>{% endfor %}</div>
    <h2>สถานะสมัครเรียน</h2><div class="list">{% for x in study %}<div class="item">{{x.type}} {{x.level}} • <span class="badge">{{x.status}}</span></div>{% else %}<div class="empty">ยังไม่มี</div>{% endfor %}</div>
    <h2>สถานะสมัครอุปัชฌาย์</h2><div class="list">{% for x in preapps %}<div class="item">{{x.name}} • <span class="badge">{{x.status}}</span></div>{% else %}<div class="empty">ยังไม่มี</div>{% endfor %}</div>
    <h2>สถานะเงินเดือน</h2><div class="list">{% for x in salary %}<div class="item">{{x.total_works}} ผลงาน • <span class="badge">{{x.status}}</span>{% if x.status=='approved' %}<p><b>ช่องทางรับเงิน:</b> {{x.payment_channel}}</p>{% endif %}</div>{% else %}<div class="empty">ยังไม่มี</div>{% endfor %}</div>
    </section>"""
    return page("ระบบพนักงาน",body,emp=emp,works=works,study=study,pending_public_study=pending_public_study,preapps=preapps,setting=setting,salary=salary)

# ------------------------- Preceptor -------------------------

@app.route("/preceptor/login", methods=["GET","POST"])
def preceptor_login():
    if request.method=="POST":
        require_csrf(); conn=db()
        row=conn.execute("SELECT * FROM preceptors WHERE username=?",(request.form["username"],)).fetchone(); conn.close()
        if row and check_password_hash(row["password_hash"],request.form["password"]):
            session.clear(); session["role"]="preceptor"; session["user_id"]=row["id"]; session["csrf"]=secrets.token_urlsafe(24)
            return redirect(url_for("preceptor"))
        flash("ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง","error")
    body="""<section class="login"><div class="card"><h1>🧘 ระบบพระอุปัชฌาย์</h1><form class="form" method="post"><input type="hidden" name="_csrf" value="{{csrf_token()}}">
    <label>ชื่อผู้ใช้</label><input name="username" required><label>รหัสผู้ใช้</label><input name="password" type="password" required><button class="btn primary">เข้าสู่ระบบ</button></form></div></section>"""
    return page("เข้าสู่ระบบพระอุปัชฌาย์",body)

@app.route("/preceptor", methods=["GET","POST"])
@preceptor_required
def preceptor():
    conn=db()
    if request.method=="POST":
        require_csrf(); oid=int(request.form["id"]); action=request.form["action"]
        row=conn.execute("SELECT * FROM ordination_requests WHERE id=? AND assigned_preceptor_id=?",
                         (oid,session["user_id"])).fetchone()
        if not row: flash("ไม่พบคำขอหรือคำขอนี้ไม่ได้มอบหมายให้คุณ","error")
        elif action=="approve":
            cur=conn.execute("UPDATE ordination_requests SET status='ผ่านการอนุมัติ รอเข้ารอบบวช' WHERE id=? AND assigned_preceptor_id=? AND status='รออนุมัติจากพระอุปัชฌาย์'",(oid,session["user_id"]))
            if cur.rowcount: conn.commit(); flash("อนุมัติคำขอแล้ว และย้ายเข้ารอบบวชแล้ว","success")
            else: flash("คำขอนี้ถูกดำเนินการไปแล้ว", "error")
        elif action=="reject":
            cur=conn.execute("UPDATE ordination_requests SET status='ปฏิเสธโดยพระอุปัชฌาย์' WHERE id=? AND assigned_preceptor_id=? AND status='รออนุมัติจากพระอุปัชฌาย์'",(oid,session["user_id"]))
            if cur.rowcount: conn.commit(); flash("ปฏิเสธคำขอแล้ว","success")
            else: flash("คำขอนี้ถูกดำเนินการไปแล้ว", "error")
        elif action in ("approve_preceptor", "reject_preceptor"):
            # Kept only for backward compatibility with old forms. Approval authority is Admin.
            flash("การสมัครอุปัชฌาย์ต้องให้ผู้ดูแลระบบอนุมัติ", "error")
        elif action=="complete":
            monastic=request.form["monastic_name"]; date=request.form["ordination_date"]; temple=request.form["affiliated_temple"]
            if not monastic or not date or not temple: flash("กรอกข้อมูลหลังบวชให้ครบ","error")
            else:
                cur=conn.execute("""UPDATE ordination_requests SET status='บวชแล้ว',monastic_name=?,ordination_date=?,affiliated_temple=? WHERE id=? AND assigned_preceptor_id=? AND status='ผ่านการอนุมัติ รอเข้ารอบบวช'""",
                             (monastic,date,temple,oid,session["user_id"]))
                if cur.rowcount:
                    conn.execute("""INSERT INTO temples(name,ordination_date,temple,status,source,source_ref,created_at)
                                    SELECT ?,?,?,?,?,?,? WHERE NOT EXISTS (
                                      SELECT 1 FROM temples WHERE source='ordination' AND source_ref=?
                                    )""",(monastic,date,temple,"บวชแล้ว","ordination",str(oid),now(),str(oid)))
                    conn.commit(); flash("บันทึกการบวชและเพิ่มเข้าทะเบียนวัดแล้ว","success")
                else:
                    flash("คำขอนี้บันทึกการบวชไปแล้วหรือไม่อยู่ในรอบบวช", "error")
        return redirect(url_for("preceptor"))
    assigned=conn.execute("""SELECT * FROM ordination_requests WHERE assigned_preceptor_id=? AND status='รออนุมัติจากพระอุปัชฌาย์' ORDER BY id DESC""",(session["user_id"],)).fetchall()
    queue=conn.execute("""SELECT * FROM ordination_requests WHERE assigned_preceptor_id=? AND status='ผ่านการอนุมัติ รอเข้ารอบบวช' ORDER BY id DESC""",(session["user_id"],)).fetchall()
    preceptor_apps=conn.execute("SELECT * FROM preceptor_applications WHERE status='approved' ORDER BY id DESC LIMIT 50").fetchall()
    conn.close()
    body="""<section class="section"><h1>🧘 ระบบพระอุปัชฌาย์</h1><h2>คำขอบวชที่รออนุมัติ</h2><div class="list">
    {% for x in assigned %}<article class="item"><h3>{{x.real_name}} • {{x.kind}}</h3><p>อายุ {{x.age}} • {{x.temple}} • ท่องบทสวด {{x.chant}}</p><p>วัดเกิด {{x.birth_temple}} • {{x.reason}}</p>
    <form method="post" onsubmit="return confirm('ยืนยันการดำเนินการกับคำขอบวชนี้?')"><input type="hidden" name="_csrf" value="{{csrf_token()}}"><input type="hidden" name="id" value="{{x.id}}"><button class="btn good" name="action" value="approve">อนุมัติ</button><button class="btn bad" name="action" value="reject">ปฏิเสธ</button></form></article>{% else %}<div class="empty">ไม่มีคำขอรออนุมัติ</div>{% endfor %}</div>
    <h2>🧘 ผู้สมัครอุปัชฌาย์ที่ Admin อนุมัติแล้ว</h2><div class="list">{% for x in preceptor_apps %}<article class="item"><h3>{{x.name}}</h3><p>พรรษา {{x.vassa}} • {{x.temple}} • <span class="badge good">ผ่านการอนุมัติจาก Admin</span></p></article>{% else %}<div class="empty">ยังไม่มีผู้สมัครที่ Admin อนุมัติ</div>{% endfor %}</div>
    <h2>รอบบวช</h2><div class="list">{% for x in queue %}<article class="item"><h3>{{x.real_name}}</h3><p>{{x.kind}} • {{x.temple}}</p>
    <form class="form" method="post" onsubmit="return confirm('ยืนยันว่าบวชเสร็จแล้วและบันทึกเข้าทะเบียนวัด?')"><input type="hidden" name="_csrf" value="{{csrf_token()}}"><input type="hidden" name="id" value="{{x.id}}"><input type="hidden" name="action" value="complete">
    <label>ชื่อฉายา</label><input name="monastic_name" required><label>วันที่บวช</label><input name="ordination_date" type="date" required><label>สังกัดวัด</label><input name="affiliated_temple" required><button class="btn primary">บันทึกว่าบวชเสร็จแล้ว</button></form></article>{% else %}<div class="empty">ยังไม่มีรอบบวช</div>{% endfor %}</div></section>"""
    return page("ระบบพระอุปัชฌาย์",body,assigned=assigned,queue=queue,preceptor_apps=preceptor_apps)

# ------------------------- Run -------------------------

@app.get("/health")
def health():
    return {"status":"ok","service":"somice-sangha"}

@app.errorhandler(413)
def too_large(_):
    return page("ไฟล์ใหญ่เกินไป","""<section class="section"><div class="card"><h1>ไฟล์ใหญ่เกินไป</h1><p>จำกัดไฟล์อัปโหลดไม่เกิน 12 MB</p><a class="btn" href="javascript:history.back()">กลับ</a></div></section>"""), 413

if __name__ == "__main__":
    host=os.environ.get("HOST","0.0.0.0")
    port=int(os.environ.get("PORT","5000"))
    app.run(host=host,port=port,debug=False)

from flask import Flask, request, redirect, url_for, session, render_template_string, flash
import sqlite3
from functools import wraps
from datetime import datetime
from pathlib import Path

app = Flask(__name__)
app.secret_key = "somice-sangha-law-demo-secret-change-this"
DB_PATH = Path(__file__).with_name("sangha_database.db")

# =========================================================
# ตั้งค่าผู้ดูแลระบบตามที่ผู้ใช้กำหนด
# =========================================================
ADMIN_NAME = "1389"
ADMIN_PASSWORD = "184224"


# =========================================================
# Database
# =========================================================
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS laws (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            section TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS temples (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            ordination_date TEXT NOT NULL,
            temple TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS sangha_council (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            royal_name TEXT NOT NULL,
            active_date TEXT NOT NULL,
            temple TEXT NOT NULL,
            details TEXT,
            created_at TEXT NOT NULL
        )
    """)

    conn.commit()
    conn.close()


# =========================================================
# Authentication
# =========================================================
def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("admin_logged_in"):
            return redirect(url_for("admin_login"))
        return view(*args, **kwargs)
    return wrapped


# =========================================================
# Shared HTML
# =========================================================
BASE_HEAD = """
<!doctype html>
<html lang="th">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{ title }} | พระสงฆ์สมไอซ์</title>
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+Thai:wght@400;500;600;700;800&display=swap');

*{box-sizing:border-box}
body{
    margin:0;
    font-family:"Noto Sans Thai",sans-serif;
    background:#f6f1e7;
    color:#332818;
}
a{text-decoration:none;color:inherit}
.navbar{
    position:sticky;top:0;z-index:20;
    background:#5b3517;
    color:#fff;
    box-shadow:0 3px 12px rgba(0,0,0,.15);
}
.nav-inner{
    max-width:1100px;margin:auto;
    min-height:66px;padding:10px 18px;
    display:flex;align-items:center;justify-content:space-between;
    gap:15px;
}
.brand{font-size:20px;font-weight:800}
.brand small{display:block;font-size:11px;font-weight:400;color:#e9d8af}
.nav-links{display:flex;gap:7px;flex-wrap:wrap}
.nav-links a{
    padding:8px 12px;border-radius:9px;
    font-size:14px;color:#fff;
}
.nav-links a:hover{background:#7a4c24}
.container{max-width:1100px;margin:auto;padding:28px 16px 50px}
.hero{
    background:linear-gradient(135deg,#6b3f1d,#a56b29);
    color:white;border-radius:24px;padding:38px 28px;
    box-shadow:0 12px 30px rgba(74,42,14,.2);
    margin-bottom:25px;
}
.hero h1{margin:0 0 8px;font-size:32px}
.hero p{margin:0;color:#f7e9cf}
.grid{
    display:grid;
    grid-template-columns:repeat(3,1fr);
    gap:18px;
}
.card{
    background:#fff;
    border:1px solid #eadfcf;
    border-radius:18px;
    padding:24px;
    box-shadow:0 6px 20px rgba(60,40,20,.07);
}
.card h2,.card h3{margin-top:0}
.menu-card{
    min-height:190px;
    display:flex;flex-direction:column;
    justify-content:space-between;
    transition:.2s;
}
.menu-card:hover{transform:translateY(-3px);box-shadow:0 12px 28px rgba(60,40,20,.12)}
.icon{
    width:50px;height:50px;border-radius:14px;
    display:grid;place-items:center;
    background:#f4e4c8;font-size:25px;
}
.btn{
    display:inline-block;border:0;cursor:pointer;
    background:#8b572a;color:#fff;
    padding:11px 17px;border-radius:10px;
    font-family:inherit;font-weight:700;
}
.btn:hover{background:#6d411d}
.btn-danger{background:#b33a32}
.btn-danger:hover{background:#8e2823}
.btn-light{background:#efe4d2;color:#51341d}
.btn-green{background:#527a45}
form{margin:0}
label{display:block;font-weight:700;margin:14px 0 6px}
input,textarea{
    width:100%;padding:12px 13px;
    border:1px solid #d9cbb8;border-radius:10px;
    font-family:inherit;font-size:15px;background:#fffdf9;
}
textarea{min-height:150px;resize:vertical}
input:focus,textarea:focus{outline:2px solid #d9b36a;border-color:#b88239}
.form-card{max-width:760px;margin:auto}
.actions{display:flex;gap:8px;flex-wrap:wrap;margin-top:18px}
.flash{
    padding:12px 15px;border-radius:10px;margin-bottom:16px;
    background:#fff0c9;border:1px solid #e6c77d;
}
.law{
    background:#fff;border:1px solid #eadfcf;
    border-radius:16px;padding:20px;margin-bottom:15px;
}
.law-number{
    color:#9b682d;font-weight:800;font-size:14px;
}
.law h2{margin:5px 0;font-size:20px}
.meta{color:#806f5b;font-size:14px}
.content{white-space:pre-wrap;line-height:1.8;margin-top:12px}
.table-wrap{overflow-x:auto}
table{width:100%;border-collapse:collapse;background:#fff}
th,td{padding:12px;border-bottom:1px solid #eadfcf;text-align:left;vertical-align:top}
th{background:#f3e6d2}
.empty{
    text-align:center;padding:45px 15px;
    color:#806f5b;background:#fff;border-radius:15px;
}
.login-box{max-width:430px;margin:45px auto}
.center{text-align:center}
.badge{
    display:inline-block;padding:5px 9px;border-radius:20px;
    background:#f1e2cb;color:#70491f;font-size:12px;font-weight:700
}
.footer{text-align:center;color:#806f5b;font-size:13px;padding:20px}
@media(max-width:800px){
    .grid{grid-template-columns:1fr}
    .hero h1{font-size:25px}
    .nav-inner{align-items:flex-start;flex-direction:column}
    .nav-links{width:100%}
    .nav-links a{padding:7px 9px}
}
</style>
</head>
<body>
<nav class="navbar">
<div class="nav-inner">
<a class="brand" href="{{ url_for('home') }}">
พระสงฆ์สมไอซ์
<small>ระบบข้อมูลกฎหมายและทะเบียนคณะสงฆ์</small>
</a>
<div class="nav-links">
<a href="{{ url_for('home') }}">หน้าแรก</a>
<a href="{{ url_for('laws') }}">กฎหมายคณะสงฆ์</a>
<a href="{{ url_for('temple_register') }}">ทะเบียนวัด</a>
<a href="{{ url_for('council_register') }}">ทะเบียนมหาเถรสมาคม</a>
{% if session.get("admin_logged_in") %}
<a href="{{ url_for('admin_dashboard') }}">หลังบ้าน</a>
<a href="{{ url_for('admin_logout') }}">ออกจากระบบ</a>
{% else %}
<a href="{{ url_for('admin_login') }}">Admin</a>
{% endif %}
</div>
</div>
</nav>
<div class="container">
{% with messages = get_flashed_messages() %}
{% for message in messages %}
<div class="flash">{{ message }}</div>
{% endfor %}
{% endwith %}
"""

BASE_FOOT = """
</div>
<div class="footer">
พระสงฆ์สมไอซ์ • ระบบตัวอย่างสำหรับจัดเก็บข้อมูลภายในกลุ่ม
</div>
</body>
</html>
"""


# =========================================================
# Public pages
# =========================================================
@app.route("/")
def home():
    conn = get_db()
    law_count = conn.execute("SELECT COUNT(*) FROM laws").fetchone()[0]
    temple_count = conn.execute("SELECT COUNT(*) FROM temples").fetchone()[0]
    council_count = conn.execute("SELECT COUNT(*) FROM sangha_council").fetchone()[0]
    conn.close()

    html = BASE_HEAD + """
<div class="hero">
    <h1>พระสงฆ์สมไอซ์</h1>
    <p>ศูนย์รวมข้อมูลกฎหมายคณะสงฆ์ ทะเบียนวัด และทะเบียนมหาเถรสมาคม</p>
</div>

<div class="grid">
    <a class="card menu-card" href="{{ url_for('laws') }}">
        <div>
            <div class="icon">📜</div>
            <h2>กฎหมายคณะสงฆ์</h2>
            <p>ดูรายการกฎหมาย มาตรา เนื้อหา และโทษความผิดที่ผู้ดูแลระบบบันทึกไว้</p>
        </div>
        <span class="badge">{{ law_count }} รายการ</span>
    </a>

    <a class="card menu-card" href="{{ url_for('temple_register') }}">
        <div>
            <div class="icon">🏯</div>
            <h2>ทะเบียนวัด</h2>
            <p>ตรวจดูรายชื่อและข้อมูลผู้ที่ถูกบันทึกไว้ในทะเบียนวัด</p>
        </div>
        <span class="badge">{{ temple_count }} รายการ</span>
    </a>

    <a class="card menu-card" href="{{ url_for('council_register') }}">
        <div>
            <div class="icon">🪷</div>
            <h2>ทะเบียนมหาเถรสมาคม</h2>
            <p>แสดงข้อมูลราชทินนาม วันที่ประจำ และวัดที่ประจำการ</p>
        </div>
        <span class="badge">{{ council_count }} รายการ</span>
    </a>
</div>
"""
    return render_template_string(html + BASE_FOOT, title="หน้าแรก",
                                  law_count=law_count,
                                  temple_count=temple_count,
                                  council_count=council_count)


@app.route("/laws")
def laws():
    conn = get_db()
    rows = conn.execute("SELECT * FROM laws ORDER BY id ASC").fetchall()
    conn.close()

    html = BASE_HEAD + """
<div class="hero">
    <h1>📜 กฎหมายคณะสงฆ์</h1>
    <p>รายการกฎหมายที่บันทึกไว้ในระบบ</p>
</div>

{% if rows %}
{% for law in rows %}
<div class="law">
    <div class="law-number">ลำดับ {{ loop.index }}</div>
    <h2>{{ law["title"] }}</h2>
    <div class="meta">มาตรา {{ law["section"] }}</div>
    <div class="content">{{ law["content"] }}</div>
</div>
{% endfor %}
{% else %}
<div class="empty">ยังไม่มีข้อมูลกฎหมายในระบบ</div>
{% endif %}
"""
    return render_template_string(html + BASE_FOOT, title="กฎหมายคณะสงฆ์", rows=rows)


@app.route("/temple-register")
def temple_register():
    conn = get_db()
    rows = conn.execute("SELECT * FROM temples ORDER BY id ASC").fetchall()
    conn.close()

    html = BASE_HEAD + """
<div class="hero">
    <h1>🏯 ทะเบียนวัด</h1>
    <p>ข้อมูลที่ผู้ดูแลระบบเพิ่มเข้าสู่ทะเบียน</p>
</div>

{% if rows %}
<div class="card table-wrap">
<table>
<thead>
<tr>
<th>ลำดับ</th>
<th>ชื่อ / ฉายา</th>
<th>วันที่บวช</th>
<th>วัดที่ประจำ</th>
</tr>
</thead>
<tbody>
{% for row in rows %}
<tr>
<td>{{ loop.index }}</td>
<td>{{ row["name"] }}</td>
<td>{{ row["ordination_date"] }}</td>
<td>{{ row["temple"] }}</td>
</tr>
{% endfor %}
</tbody>
</table>
</div>
{% else %}
<div class="empty">ยังไม่มีข้อมูลทะเบียนวัด</div>
{% endif %}
"""
    return render_template_string(html + BASE_FOOT, title="ทะเบียนวัด", rows=rows)


@app.route("/council-register")
def council_register():
    conn = get_db()
    rows = conn.execute("SELECT * FROM sangha_council ORDER BY id ASC").fetchall()
    conn.close()

    html = BASE_HEAD + """
<div class="hero">
    <h1>🪷 ทะเบียนมหาเถรสมาคม</h1>
    <p>ข้อมูลที่ผู้ดูแลระบบบันทึกไว้</p>
</div>

{% if rows %}
<div class="card table-wrap">
<table>
<thead>
<tr>
<th>ลำดับ</th>
<th>ราชทินนาม</th>
<th>วันที่ประจำ</th>
<th>วัดที่ประจำการ</th>
<th>รายละเอียด</th>
</tr>
</thead>
<tbody>
{% for row in rows %}
<tr>
<td>{{ loop.index }}</td>
<td>{{ row["royal_name"] }}</td>
<td>{{ row["active_date"] }}</td>
<td>{{ row["temple"] }}</td>
<td>{{ row["details"] or "-" }}</td>
</tr>
{% endfor %}
</tbody>
</table>
</div>
{% else %}
<div class="empty">ยังไม่มีข้อมูลทะเบียนมหาเถรสมาคม</div>
{% endif %}
"""
    return render_template_string(html + BASE_FOOT, title="ทะเบียนมหาเถรสมาคม", rows=rows)


# =========================================================
# Admin login
# =========================================================
@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        name = request.form.get("name", "")
        password = request.form.get("password", "")

        if name == ADMIN_NAME and password == ADMIN_PASSWORD:
            session["admin_logged_in"] = True
            return redirect(url_for("admin_dashboard"))

        flash("ชื่อหรือรหัสผ่านไม่ถูกต้อง")

    html = BASE_HEAD + """
<div class="card login-box">
<div class="center">
    <div class="icon" style="margin:auto">🔐</div>
    <h1>เข้าสู่ระบบหลังบ้าน</h1>
    <p class="meta">สำหรับผู้ดูแลระบบ</p>
</div>

<form method="post">
<label>ชื่อผู้ใช้</label>
<input name="name" required autocomplete="username">

<label>รหัสผ่าน</label>
<input type="password" name="password" required autocomplete="current-password">

<div class="actions">
<button class="btn" type="submit">เข้าสู่ระบบ</button>
<a class="btn btn-light" href="{{ url_for('home') }}">กลับหน้าแรก</a>
</div>
</form>
</div>
"""
    return render_template_string(html + BASE_FOOT, title="Admin")


@app.route("/admin/logout")
def admin_logout():
    session.clear()
    return redirect(url_for("home"))


# =========================================================
# Admin dashboard
# =========================================================
@app.route("/admin")
@admin_required
def admin_dashboard():
    conn = get_db()
    law_count = conn.execute("SELECT COUNT(*) FROM laws").fetchone()[0]
    temple_count = conn.execute("SELECT COUNT(*) FROM temples").fetchone()[0]
    council_count = conn.execute("SELECT COUNT(*) FROM sangha_council").fetchone()[0]
    conn.close()

    html = BASE_HEAD + """
<div class="hero">
    <h1>⚙️ ระบบหลังบ้าน</h1>
    <p>จัดการข้อมูลของเว็บไซต์พระสงฆ์สมไอซ์</p>
</div>

<div class="grid">
<a class="card menu-card" href="{{ url_for('admin_laws') }}">
    <div>
        <div class="icon">📜</div>
        <h2>จัดการกฎหมาย</h2>
        <p>เพิ่มและลบรายการกฎหมายคณะสงฆ์</p>
    </div>
    <span class="badge">{{ law_count }} รายการ</span>
</a>

<a class="card menu-card" href="{{ url_for('admin_temples') }}">
    <div>
        <div class="icon">🏯</div>
        <h2>เพิ่มบุคคลเข้าวัด</h2>
        <p>เพิ่มชื่อ/ฉายา วันที่บวช และวัดที่ประจำ</p>
    </div>
    <span class="badge">{{ temple_count }} รายการ</span>
</a>

<a class="card menu-card" href="{{ url_for('admin_council') }}">
    <div>
        <div class="icon">🪷</div>
        <h2>ทะเบียนมหาเถรสมาคม</h2>
        <p>เพิ่มข้อมูลราชทินนามและรายละเอียดการประจำ</p>
    </div>
    <span class="badge">{{ council_count }} รายการ</span>
</a>
</div>
"""
    return render_template_string(html + BASE_FOOT, title="หลังบ้าน",
                                  law_count=law_count,
                                  temple_count=temple_count,
                                  council_count=council_count)


# =========================================================
# Admin - Laws
# =========================================================
@app.route("/admin/laws")
@admin_required
def admin_laws():
    conn = get_db()
    rows = conn.execute("SELECT * FROM laws ORDER BY id ASC").fetchall()
    conn.close()

    html = BASE_HEAD + """
<div class="hero">
    <h1>📜 จัดการกฎหมาย</h1>
    <p>เพิ่มหรือลบข้อมูลกฎหมายในระบบ</p>
</div>

<div class="actions">
<a class="btn" href="{{ url_for('admin_add_law') }}">＋ เพิ่มกฎหมาย</a>
<a class="btn btn-light" href="{{ url_for('admin_dashboard') }}">กลับหลังบ้าน</a>
</div>

<div style="margin-top:18px">
{% if rows %}
{% for law in rows %}
<div class="law">
    <div class="law-number">ลำดับ {{ loop.index }}</div>
    <h2>{{ law["title"] }}</h2>
    <div class="meta">มาตรา {{ law["section"] }}</div>
    <div class="content">{{ law["content"] }}</div>

    <div class="actions">
        <form method="post" action="{{ url_for('admin_delete_law', law_id=law['id']) }}"
              onsubmit="return confirm('ต้องการลบกฎหมายรายการนี้หรือไม่?')">
            <button class="btn btn-danger" type="submit">ลบ</button>
        </form>
    </div>
</div>
{% endfor %}
{% else %}
<div class="empty">ยังไม่มีรายการกฎหมาย</div>
{% endif %}
</div>
"""
    return render_template_string(html + BASE_FOOT, title="จัดการกฎหมาย", rows=rows)


@app.route("/admin/laws/add", methods=["GET", "POST"])
@admin_required
def admin_add_law():
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        section = request.form.get("section", "").strip()
        content = request.form.get("content", "").strip()

        if not title or not section or not content:
            flash("กรุณากรอกข้อมูลกฎหมายให้ครบทุกช่อง")
            return redirect(url_for("admin_add_law"))

        conn = get_db()
        conn.execute("""
            INSERT INTO laws (title, section, content, created_at)
            VALUES (?, ?, ?, ?)
        """, (title, section, content, datetime.now().isoformat(timespec="seconds")))
        conn.commit()
        conn.close()

        flash("เพิ่มกฎหมายเรียบร้อยแล้ว")
        return redirect(url_for("admin_laws"))

    html = BASE_HEAD + """
<div class="card form-card">
<h1>＋ เพิ่มกฎหมายคณะสงฆ์</h1>
<p class="meta">กรอกข้อมูลให้ครบแล้วกดยืนยัน</p>

<form method="post">
<label>ชื่อกฎหมายหลัก</label>
<input name="title" placeholder="เช่น พระราชบัญญัติคณะสงฆ์" required>

<label>มาตรา</label>
<input name="section" placeholder="เช่น มาตรา 15" required>

<label>เนื้อหา / โทษความผิด</label>
<textarea name="content"
placeholder="ใส่เนื้อหากฎหมายหรือรายละเอียดโทษความผิด..."
required></textarea>

<div class="actions">
<button class="btn" type="submit">ยืนยันการเพิ่ม</button>
<a class="btn btn-light" href="{{ url_for('admin_laws') }}">ยกเลิก</a>
</div>
</form>
</div>
"""
    return render_template_string(html + BASE_FOOT, title="เพิ่มกฎหมาย")


@app.post("/admin/laws/delete/<int:law_id>")
@admin_required
def admin_delete_law(law_id):
    conn = get_db()
    conn.execute("DELETE FROM laws WHERE id = ?", (law_id,))
    conn.commit()
    conn.close()
    flash("ลบกฎหมายเรียบร้อยแล้ว")
    return redirect(url_for("admin_laws"))


# =========================================================
# Admin - Temple Register
# =========================================================
@app.route("/admin/temples")
@admin_required
def admin_temples():
    conn = get_db()
    rows = conn.execute("SELECT * FROM temples ORDER BY id ASC").fetchall()
    conn.close()

    html = BASE_HEAD + """
<div class="hero">
    <h1>🏯 เพิ่มบุคคลเข้าวัด</h1>
    <p>จัดการข้อมูลทะเบียนวัด</p>
</div>

<div class="card">
<h2>เพิ่มข้อมูล</h2>
<form method="post" action="{{ url_for('admin_add_temple') }}">
<label>ชื่อ / ฉายา</label>
<input name="name" placeholder="เช่น พระสมชาย สุเมโธ" required>

<label>วันที่บวช</label>
<input type="date" name="ordination_date" required>

<label>วัดที่ประจำ</label>
<input name="temple" placeholder="ชื่อวัด" required>

<div class="actions">
<button class="btn" type="submit">ยืนยันการเพิ่ม</button>
<a class="btn btn-light" href="{{ url_for('admin_dashboard') }}">กลับหลังบ้าน</a>
</div>
</form>
</div>

<div style="margin-top:20px" class="card">
<h2>รายการทะเบียนวัด</h2>
{% if rows %}
<div class="table-wrap">
<table>
<tr><th>ลำดับ</th><th>ชื่อ / ฉายา</th><th>วันที่บวช</th><th>วัด</th><th>จัดการ</th></tr>
{% for row in rows %}
<tr>
<td>{{ loop.index }}</td>
<td>{{ row["name"] }}</td>
<td>{{ row["ordination_date"] }}</td>
<td>{{ row["temple"] }}</td>
<td>
<form method="post" action="{{ url_for('admin_delete_temple', item_id=row['id']) }}"
onsubmit="return confirm('ยืนยันการลบข้อมูลนี้หรือไม่?')">
<button class="btn btn-danger" type="submit">ลบ</button>
</form>
</td>
</tr>
{% endfor %}
</table>
</div>
{% else %}
<p class="meta">ยังไม่มีข้อมูล</p>
{% endif %}
</div>
"""
    return render_template_string(html + BASE_FOOT, title="จัดการทะเบียนวัด", rows=rows)


@app.post("/admin/temples/add")
@admin_required
def admin_add_temple():
    name = request.form.get("name", "").strip()
    ordination_date = request.form.get("ordination_date", "").strip()
    temple = request.form.get("temple", "").strip()

    if not name or not ordination_date or not temple:
        flash("กรุณากรอกข้อมูลทะเบียนวัดให้ครบ")
        return redirect(url_for("admin_temples"))

    conn = get_db()
    conn.execute("""
        INSERT INTO temples (name, ordination_date, temple, created_at)
        VALUES (?, ?, ?, ?)
    """, (name, ordination_date, temple, datetime.now().isoformat(timespec="seconds")))
    conn.commit()
    conn.close()

    flash("เพิ่มข้อมูลทะเบียนวัดเรียบร้อยแล้ว")
    return redirect(url_for("admin_temples"))


@app.post("/admin/temples/delete/<int:item_id>")
@admin_required
def admin_delete_temple(item_id):
    conn = get_db()
    conn.execute("DELETE FROM temples WHERE id = ?", (item_id,))
    conn.commit()
    conn.close()
    flash("ลบข้อมูลทะเบียนวัดเรียบร้อยแล้ว")
    return redirect(url_for("admin_temples"))


# =========================================================
# Admin - Sangha Council Register
# =========================================================
@app.route("/admin/council")
@admin_required
def admin_council():
    conn = get_db()
    rows = conn.execute("SELECT * FROM sangha_council ORDER BY id ASC").fetchall()
    conn.close()

    html = BASE_HEAD + """
<div class="hero">
    <h1>🪷 ทะเบียนมหาเถรสมาคม</h1>
    <p>เพิ่มข้อมูลราชทินนามและรายละเอียดการประจำการ</p>
</div>

<div class="card">
<h2>เพิ่มข้อมูล</h2>
<form method="post" action="{{ url_for('admin_add_council') }}">
<label>ราชทินนาม</label>
<input name="royal_name" placeholder="เช่น พระราช... " required>

<label>วันที่ประจำ</label>
<input type="date" name="active_date" required>

<label>วัดที่ประจำการ</label>
<input name="temple" placeholder="ชื่อวัด" required>

<label>รายละเอียดเพิ่มเติม</label>
<textarea name="details" placeholder="รายละเอียดเพิ่มเติม (ถ้ามี)"></textarea>

<div class="actions">
<button class="btn" type="submit">ยืนยันการเพิ่ม</button>
<a class="btn btn-light" href="{{ url_for('admin_dashboard') }}">กลับหลังบ้าน</a>
</div>
</form>
</div>

<div style="margin-top:20px" class="card">
<h2>รายการทะเบียน</h2>
{% if rows %}
<div class="table-wrap">
<table>
<tr>
<th>ลำดับ</th>
<th>ราชทินนาม</th>
<th>วันที่ประจำ</th>
<th>วัดที่ประจำการ</th>
<th>รายละเอียด</th>
<th>จัดการ</th>
</tr>
{% for row in rows %}
<tr>
<td>{{ loop.index }}</td>
<td>{{ row["royal_name"] }}</td>
<td>{{ row["active_date"] }}</td>
<td>{{ row["temple"] }}</td>
<td>{{ row["details"] or "-" }}</td>
<td>
<form method="post" action="{{ url_for('admin_delete_council', item_id=row['id']) }}"
onsubmit="return confirm('ยืนยันการลบข้อมูลนี้หรือไม่?')">
<button class="btn btn-danger" type="submit">ลบ</button>
</form>
</td>
</tr>
{% endfor %}
</table>
</div>
{% else %}
<p class="meta">ยังไม่มีข้อมูล</p>
{% endif %}
</div>
"""
    return render_template_string(html + BASE_FOOT, title="ทะเบียนมหาเถรสมาคม", rows=rows)


@app.post("/admin/council/add")
@admin_required
def admin_add_council():
    royal_name = request.form.get("royal_name", "").strip()
    active_date = request.form.get("active_date", "").strip()
    temple = request.form.get("temple", "").strip()
    details = request.form.get("details", "").strip()

    if not royal_name or not active_date or not temple:
        flash("กรุณากรอกข้อมูลให้ครบ")
        return redirect(url_for("admin_council"))

    conn = get_db()
    conn.execute("""
        INSERT INTO sangha_council
        (royal_name, active_date, temple, details, created_at)
        VALUES (?, ?, ?, ?, ?)
    """, (
        royal_name,
        active_date,
        temple,
        details,
        datetime.now().isoformat(timespec="seconds")
    ))
    conn.commit()
    conn.close()

    flash("เพิ่มข้อมูลทะเบียนมหาเถรสมาคมเรียบร้อยแล้ว")
    return redirect(url_for("admin_council"))


@app.post("/admin/council/delete/<int:item_id>")
@admin_required
def admin_delete_council(item_id):
    conn = get_db()
    conn.execute("DELETE FROM sangha_council WHERE id = ?", (item_id,))
    conn.commit()
    conn.close()
    flash("ลบข้อมูลทะเบียนมหาเถรสมาคมเรียบร้อยแล้ว")
    return redirect(url_for("admin_council"))


# =========================================================
# Start
# =========================================================
with app.app_context():
        init_db()
    
if __name__ == "__main__":
    print("==============================================")
    print(" พระสงฆ์สมไอซ์ - Sangha Law Website")
    print(" เปิดที่: http://127.0.0.1:5000")
    print(" Admin name: 1389")
    print(" Admin password: 184224")
    print("==============================================")
    app.run(host="0.0.0.0", port=5000, debug=False)

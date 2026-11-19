# -*- coding: utf-8 -*-
"""
เว็บไซต์คลังข้อมูล กองพันสารวัตรทหารบกที่ ๑๑ - แผนกตรวจสอบภายใน  (ธีมน้ำเงิน)
------------------------------------------------------------------
วิธีใช้:
  1) บันทึกไฟล์นี้เป็น app.py
  2) pip install flask          (แนะนำเพิ่ม: pip install waitress เพื่อความเสถียรสูงสุด)
  3) python app.py   แล้วเปิด http://localhost:5000
"""
import os, time, uuid, secrets, sqlite3, logging
from datetime import timedelta
from functools import wraps
from flask import Flask, request, jsonify, session, send_from_directory, Response, g
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.exceptions import HTTPException

# ============================ ตั้งค่า (แก้ตรงนี้) ============================
ADMIN_USERNAME = "1482"          # ชื่อผู้ดูแล
ADMIN_PASSWORD = "1842111482"      # รหัสผู้ดูแลเริ่มต้น (แก้เป็นของคุณเอง)
# หมายเหตุ: ถ้าผู้ดูแลกด "เปลี่ยนรหัสผ่าน" ในเว็บ ระบบจะใช้รหัสใหม่แทนรหัสด้านบน
# ถ้าลืมรหัสที่เปลี่ยนไว้ ให้ตั้งค่าเป็น True แล้วรันใหม่ 1 ครั้ง (ระบบจะกลับมาใช้รหัสด้านบน) จากนั้นเปลี่ยนกลับเป็น False
RESET_ADMIN_PASSWORD_ON_START = False
HOST = "0.0.0.0"
PORT = 5000
SITE_TITLE = "กองพันสารวัตรทหารบกที่ ๑๑"
SITE_SUBTITLE = "แผนกตรวจสอบภายใน"
LOGO_URL = "https://i.postimg.cc/K4X6ngv7/inbound936785273759467197.png"
# ===========================================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "data.db")
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)


def load_secret():
    p = os.path.join(BASE_DIR, ".secret_key")
    if os.path.exists(p):
        with open(p, "r", encoding="utf-8") as f:
            k = f.read().strip()
            if k:
                return k
    k = secrets.token_hex(32)
    with open(p, "w", encoding="utf-8") as f:
        f.write(k)
    return k


app = Flask(__name__)
app.secret_key = load_secret()
app.config.update(
    MAX_CONTENT_LENGTH=60 * 1024 * 1024,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_HTTPONLY=True,
    PERMANENT_SESSION_LIFETIME=timedelta(hours=12),
    JSON_AS_ASCII=False,
)
logging.basicConfig(level=logging.INFO)
FAILS = {}

# ------------------------------- ฐานข้อมูล -------------------------------
def db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH, timeout=20)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys=ON")
    return g.db


@app.teardown_appcontext
def close_db(_e):
    d = g.pop("db", None)
    if d is not None:
        d.close()


def q(sql, args=(), one=False):
    cur = db().execute(sql, args)
    rows = cur.fetchall()
    cur.close()
    if one:
        return rows[0] if rows else None
    return rows


def execute(sql, args=()):
    c = db()
    cur = c.execute(sql, args)
    c.commit()
    return cur.lastrowid


def init_db():
    c = sqlite3.connect(DB_PATH, timeout=20)
    c.execute("PRAGMA journal_mode=WAL")
    c.executescript("""
    CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS categories(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        position INTEGER NOT NULL DEFAULT 0,
        is_home INTEGER NOT NULL DEFAULT 0);
    CREATE TABLE IF NOT EXISTS blocks(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        category_id INTEGER NOT NULL REFERENCES categories(id) ON DELETE CASCADE,
        title TEXT NOT NULL DEFAULT '',
        body TEXT NOT NULL DEFAULT '',
        image TEXT NOT NULL DEFAULT '',
        position INTEGER NOT NULL DEFAULT 0);
    CREATE TABLE IF NOT EXISTS images(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        filename TEXT NOT NULL,
        original TEXT NOT NULL DEFAULT '',
        created INTEGER NOT NULL);
    CREATE TABLE IF NOT EXISTS settings(
        k TEXT PRIMARY KEY, v TEXT NOT NULL DEFAULT '');
    CREATE TABLE IF NOT EXISTS audit_log(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts INTEGER NOT NULL,
        actor TEXT NOT NULL DEFAULT '',
        role TEXT NOT NULL DEFAULT '',
        ip TEXT NOT NULL DEFAULT '',
        action TEXT NOT NULL DEFAULT '',
        place TEXT NOT NULL DEFAULT '',
        detail TEXT NOT NULL DEFAULT '');
    """)
    if not c.execute("SELECT 1 FROM categories WHERE is_home=1").fetchone():
        c.execute("INSERT INTO categories(name,position,is_home) VALUES('หน้าหลัก',0,1)")
    c.execute("INSERT OR IGNORE INTO settings(k,v) VALUES('description','คลังข้อมูลของแผนกตรวจสอบภายใน')")
    if RESET_ADMIN_PASSWORD_ON_START:
        c.execute("DELETE FROM settings WHERE k='admin_pw_hash'")
    c.commit()
    c.close()


init_db()

# ------------------------------- ตัวช่วย -------------------------------
def err(msg, code=400):
    return jsonify(error=msg), code


def clean(v, n):
    return (v if isinstance(v, str) else "").strip()[:n]


def valid_img(u):
    return u == "" or u.startswith("/uploads/") or u.startswith("http://") or u.startswith("https://")


def sn(s, n=400):
    s = s or ""
    return s if len(s) <= n else s[:n] + "…"


def show(v, n=400):
    return sn(v, n) if v else "(ว่าง)"


def cplace(name):
    return 'หมวด "%s"' % name


def bplace(cname, title, bid):
    t = title if title else "(ไม่มีหัวข้อ)"
    return 'หมวด "%s" › ช่อง "%s" (รหัสช่อง #%s)' % (cname, t, bid)


def throttled(key):
    now = time.time()
    h = [t for t in FAILS.get(key, []) if now - t < 300]
    if h:
        FAILS[key] = h
    else:
        FAILS.pop(key, None)
    return len(h) >= 8


def fail(key):
    FAILS.setdefault(key, []).append(time.time())


def audit(action, place="", detail="", actor=None, role=""):
    """บันทึกการกระทำลงประวัติ (ผู้ดูแลดูได้ที่ปุ่ม เช็คย้อนหลัง)"""
    if actor is None:
        u = current_user()
        actor, role = (u["username"], u["role"]) if u else ("-", "")
    execute("INSERT INTO audit_log(ts,actor,role,ip,action,place,detail) VALUES(?,?,?,?,?,?,?)",
            (int(time.time()), actor[:100], role, (request.remote_addr or "")[:60], action[:100], place[:600], detail[:6000]))


def admin_pw_ok(p):
    r = q("SELECT v FROM settings WHERE k='admin_pw_hash'", one=True)
    if r and r["v"]:
        return check_password_hash(r["v"], p)
    return secrets.compare_digest(p.encode(), ADMIN_PASSWORD.encode())


def current_user():
    role = session.get("role")
    if role == "admin" and session.get("username") == ADMIN_USERNAME:
        return {"role": "admin", "username": ADMIN_USERNAME}
    if role == "director":
        r = q("SELECT id,username FROM users WHERE id=?", (session.get("uid"),), one=True)
        if r:
            return {"role": "director", "username": r["username"]}
    session.clear()
    return None


def staff(f):
    @wraps(f)
    def w(*a, **k):
        if not current_user():
            return err("กรุณาเข้าสู่ระบบ", 401)
        return f(*a, **k)
    return w


def admin_only(f):
    @wraps(f)
    def w(*a, **k):
        u = current_user()
        if not u:
            return err("กรุณาเข้าสู่ระบบ", 401)
        if u["role"] != "admin":
            return err("เฉพาะผู้ดูแลเท่านั้น", 403)
        return f(*a, **k)
    return w


def move_item(table, item_id, direction, where="", args=(), order="position, id", lock_first=False):
    """คืนค่า (ลำดับเดิม, ลำดับใหม่) ถ้าเลื่อนสำเร็จ ไม่เช่นนั้นคืน None"""
    ids = [r["id"] for r in q(f"SELECT id FROM {table} {where} ORDER BY {order}", args)]
    if item_id not in ids:
        return None
    i = ids.index(item_id)
    j = i + (1 if direction == "down" else -1)
    if j < 0 or j >= len(ids):
        return None
    if lock_first and (i == 0 or j == 0):
        return None
    ids[i], ids[j] = ids[j], ids[i]
    c = db()
    c.executemany(f"UPDATE {table} SET position=? WHERE id=?", [(p, r) for p, r in enumerate(ids)])
    c.commit()
    return (i + 1, j + 1)


@app.after_request
def headers(r):
    r.headers["X-Content-Type-Options"] = "nosniff"
    if request.path.startswith("/api/"):
        r.headers["Cache-Control"] = "no-store"
    return r


@app.errorhandler(Exception)
def on_error(e):
    if isinstance(e, HTTPException):
        if e.code == 413:
            return err("ไฟล์ใหญ่เกินไป", 413)
        if request.path.startswith("/api/"):
            return err(e.description or "ผิดพลาด", e.code or 400)
        return e
    logging.exception("server error")
    return err("เกิดข้อผิดพลาดภายในเซิร์ฟเวอร์", 500)

# ------------------------------- API -------------------------------
@app.get("/api/state")
def api_state():
    cats = [dict(id=r["id"], name=r["name"], is_home=bool(r["is_home"]))
            for r in q("SELECT * FROM categories ORDER BY is_home DESC, position, id")]
    d = q("SELECT v FROM settings WHERE k='description'", one=True)
    return jsonify(site=dict(title=SITE_TITLE, subtitle=SITE_SUBTITLE, logo=LOGO_URL,
                             description=d["v"] if d else ""),
                   cats=cats, me=current_user())


@app.post("/api/login")
def api_login():
    ip = request.remote_addr or "?"
    if throttled(ip):
        return err("พยายามเข้าสู่ระบบบ่อยเกินไป กรุณารอ 5 นาที", 429)
    d = request.get_json(silent=True) or {}
    u = clean(d.get("username"), 100)
    p = d.get("password") if isinstance(d.get("password"), str) else ""
    if secrets.compare_digest(u.encode(), ADMIN_USERNAME.encode()) and admin_pw_ok(p):
        session.clear()
        session.update(role="admin", username=ADMIN_USERNAME)
        role, actor = "admin", ADMIN_USERNAME
    else:
        r = q("SELECT * FROM users WHERE username=?", (u,), one=True)
        if r and check_password_hash(r["password_hash"], p):
            session.clear()
            session.update(role="director", uid=r["id"], username=r["username"])
            role, actor = "director", r["username"]
        else:
            fail(ip)
            audit("เข้าสู่ระบบไม่สำเร็จ", "หน้าเข้าสู่ระบบ",
                  'มีผู้พยายามเข้าสู่ระบบด้วยชื่อผู้ใช้ "%s" แต่ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง' % u[:60], actor=u[:60] or "-")
            return err("ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง", 401)
    FAILS.pop(ip, None)
    session.permanent = True
    audit("เข้าสู่ระบบ", "หน้าเข้าสู่ระบบ", "เข้าสู่ระบบสำเร็จ", actor=actor, role=role)
    return jsonify(ok=True)


@app.post("/api/logout")
def api_logout():
    if current_user():
        audit("ออกจากระบบ", "ระบบ", "ออกจากระบบ")
    session.clear()
    return jsonify(ok=True)


@app.post("/api/password")
@staff
def api_password():
    u = current_user()
    d = request.get_json(silent=True) or {}
    cur = d.get("current") if isinstance(d.get("current"), str) else ""
    new = d.get("new") if isinstance(d.get("new"), str) else ""
    key = "pw:" + u["username"]
    if throttled(key):
        return err("ใส่รหัสผิดบ่อยเกินไป กรุณารอ 5 นาที", 429)
    if len(new) < 4:
        return err("รหัสผ่านใหม่ต้องมีอย่างน้อย 4 ตัวอักษร")
    if len(new) > 200:
        return err("รหัสผ่านยาวเกินไป")
    if cur == new:
        return err("รหัสผ่านใหม่ต้องไม่เหมือนรหัสปัจจุบัน")
    if u["role"] == "admin":
        if not admin_pw_ok(cur):
            fail(key)
            return err("รหัสผ่านปัจจุบันไม่ถูกต้อง", 403)
        execute("INSERT OR REPLACE INTO settings(k,v) VALUES('admin_pw_hash',?)", (generate_password_hash(new),))
    else:
        r = q("SELECT * FROM users WHERE id=?", (session.get("uid"),), one=True)
        if not r or not check_password_hash(r["password_hash"], cur):
            fail(key)
            return err("รหัสผ่านปัจจุบันไม่ถูกต้อง", 403)
        execute("UPDATE users SET password_hash=? WHERE id=?", (generate_password_hash(new), r["id"]))
    FAILS.pop(key, None)
    audit("เปลี่ยนรหัสผ่าน", "บัญชีของตนเอง", "เปลี่ยนรหัสผ่านของบัญชี %s สำเร็จ (ไม่บันทึกตัวรหัสผ่าน)" % u["username"])
    return jsonify(ok=True)


@app.post("/api/description")
@staff
def api_desc():
    d = request.get_json(silent=True) or {}
    new = clean(d.get("description"), 3000)
    old = q("SELECT v FROM settings WHERE k='description'", one=True)
    old = old["v"] if old else ""
    execute("INSERT OR REPLACE INTO settings(k,v) VALUES('description',?)", (new,))
    audit("แก้ไขคำอธิบายหน้าเว็บ", "ส่วนหัวเว็บไซต์ › คำอธิบาย",
          "• คำอธิบาย\n   เดิม: %s\n   ใหม่: %s" % (show(old, 800), show(new, 800)) if old != new else "ไม่มีการเปลี่ยนแปลงข้อมูล")
    return jsonify(ok=True)

# ---- หมวดหมู่ ----
@app.post("/api/category")
@staff
def cat_add():
    name = clean((request.get_json(silent=True) or {}).get("name"), 60)
    if not name:
        return err("กรุณาตั้งชื่อหมวดหมู่")
    pos = q("SELECT COALESCE(MAX(position),0)+1 AS p FROM categories", one=True)["p"]
    cid = execute("INSERT INTO categories(name,position) VALUES(?,?)", (name, pos))
    audit("เพิ่มหมวดหมู่", cplace(name), 'สร้างหมวดหมู่ใหม่ชื่อ "%s" (รหัสหมวด #%s) ต่อท้ายแถบหมวดหมู่' % (name, cid))
    return jsonify(id=cid)


@app.put("/api/category/<int:cid>")
@staff
def cat_edit(cid):
    name = clean((request.get_json(silent=True) or {}).get("name"), 60)
    if not name:
        return err("กรุณาตั้งชื่อหมวดหมู่")
    old = q("SELECT name FROM categories WHERE id=?", (cid,), one=True)
    if not old:
        return err("ไม่พบหมวดหมู่", 404)
    execute("UPDATE categories SET name=? WHERE id=?", (name, cid))
    audit("เปลี่ยนชื่อหมวดหมู่", cplace(old["name"]), 'เปลี่ยนชื่อหมวดหมู่ (รหัสหมวด #%s)\n   เดิม: %s\n   ใหม่: %s' % (cid, old["name"], name))
    return jsonify(ok=True)


@app.delete("/api/category/<int:cid>")
@staff
def cat_del(cid):
    r = q("SELECT name,is_home FROM categories WHERE id=?", (cid,), one=True)
    if not r:
        return err("ไม่พบหมวดหมู่", 404)
    if r["is_home"]:
        return err("ลบหน้าหลักไม่ได้")
    blocks = q("SELECT id,title FROM blocks WHERE category_id=? ORDER BY position,id", (cid,))
    lst = "\n".join("   - #%s %s" % (b["id"], b["title"] or "(ไม่มีหัวข้อ)") for b in blocks[:40])
    execute("DELETE FROM categories WHERE id=?", (cid,))
    audit("ลบหมวดหมู่", cplace(r["name"]),
          'ลบหมวดหมู่ "%s" (รหัสหมวด #%s) พร้อมช่องทั้งหมดในหมวด จำนวน %d ช่อง%s' %
          (r["name"], cid, len(blocks), (":\n" + lst) if blocks else ""))
    return jsonify(ok=True)


@app.post("/api/category/<int:cid>/move")
@staff
def cat_move(cid):
    down = (request.get_json(silent=True) or {}).get("dir") == "down"
    r = q("SELECT name FROM categories WHERE id=?", (cid,), one=True)
    res = move_item("categories", cid, "down" if down else "up", order="is_home DESC, position, id", lock_first=True)
    if res and r:
        audit("เลื่อนลำดับหมวดหมู่", cplace(r["name"]),
              "เลื่อน%s จากตำแหน่งที่ %d เป็นตำแหน่งที่ %d ในแถบหมวดหมู่ด้านบน" % ("ไปทางขวา" if down else "ไปทางซ้าย", res[0], res[1]))
    return jsonify(ok=True)


@app.get("/api/category/<int:cid>")
def cat_get(cid):
    if not q("SELECT 1 FROM categories WHERE id=?", (cid,), one=True):
        return err("ไม่พบหมวดหมู่", 404)
    rows = q("SELECT id,title,body,image FROM blocks WHERE category_id=? ORDER BY position, id", (cid,))
    return jsonify(blocks=[dict(r) for r in rows])

# ---- ช่อง (บล็อก) ----
def block_fields(d):
    t, b, im = clean(d.get("title"), 200), clean(d.get("body"), 20000), clean(d.get("image"), 500)
    if not valid_img(im):
        return None, "ลิงก์รูปภาพไม่ถูกต้อง"
    if not (t or b or im):
        return None, "กรุณากรอกหัวข้อ รายละเอียด หรือเลือกรูปภาพอย่างน้อยหนึ่งอย่าง"
    return dict(title=t, body=b, image=im), None


@app.post("/api/block")
@staff
def block_add():
    d = request.get_json(silent=True) or {}
    cid = d.get("category_id")
    cat = q("SELECT name FROM categories WHERE id=?", (cid,), one=True) if isinstance(cid, int) else None
    if not cat:
        return err("ไม่พบหมวดหมู่", 404)
    f, e = block_fields(d)
    if e:
        return err(e)
    pos = q("SELECT COALESCE(MAX(position),0)+1 AS p FROM blocks WHERE category_id=?", (cid,), one=True)["p"]
    bid = execute("INSERT INTO blocks(category_id,title,body,image,position) VALUES(?,?,?,?,?)",
                  (cid, f["title"], f["body"], f["image"], pos))
    audit("เพิ่มข้อมูล (เพิ่มช่อง)", bplace(cat["name"], f["title"], bid),
          "เพิ่มช่องใหม่ในหมวด \"%s\"\n• หัวข้อ: %s\n• รายละเอียด: %s\n• รูปภาพ: %s\n• ลำดับในหมวด: %d" %
          (cat["name"], show(f["title"]), show(f["body"]), show(f["image"]), pos))
    return jsonify(id=bid)


@app.put("/api/block/<int:bid>")
@staff
def block_edit(bid):
    f, e = block_fields(request.get_json(silent=True) or {})
    if e:
        return err(e)
    old = q("SELECT b.*, c.name AS cname FROM blocks b JOIN categories c ON c.id=b.category_id WHERE b.id=?", (bid,), one=True)
    if not old:
        return err("ไม่พบช่อง", 404)
    execute("UPDATE blocks SET title=?, body=?, image=? WHERE id=?", (f["title"], f["body"], f["image"], bid))
    out = []
    for k, label in (("title", "หัวข้อ"), ("body", "รายละเอียด"), ("image", "รูปภาพ")):
        if old[k] != f[k]:
            out.append("• %s\n   เดิม: %s\n   ใหม่: %s" % (label, show(old[k]), show(f[k])))
    audit("แก้ไขข้อมูล (แก้ไขช่อง)", bplace(old["cname"], old["title"], bid), "\n".join(out) or "ไม่มีการเปลี่ยนแปลงข้อมูล")
    return jsonify(ok=True)


@app.delete("/api/block/<int:bid>")
@staff
def block_del(bid):
    old = q("SELECT b.*, c.name AS cname FROM blocks b JOIN categories c ON c.id=b.category_id WHERE b.id=?", (bid,), one=True)
    if not old:
        return err("ไม่พบช่อง", 404)
    execute("DELETE FROM blocks WHERE id=?", (bid,))
    audit("ลบข้อมูล (ลบช่อง)", bplace(old["cname"], old["title"], bid),
          "ลบช่องออกจากหมวด \"%s\"\nข้อมูลที่ถูกลบ:\n• หัวข้อ: %s\n• รายละเอียด: %s\n• รูปภาพ: %s" %
          (old["cname"], show(old["title"]), show(old["body"]), show(old["image"])))
    return jsonify(ok=True)


@app.post("/api/block/<int:bid>/move")
@staff
def block_move(bid):
    r = q("SELECT b.title, b.category_id, c.name AS cname FROM blocks b JOIN categories c ON c.id=b.category_id WHERE b.id=?", (bid,), one=True)
    if r:
        down = (request.get_json(silent=True) or {}).get("dir") == "down"
        res = move_item("blocks", bid, "down" if down else "up", "WHERE category_id=?", (r["category_id"],))
        if res:
            audit("เลื่อนลำดับช่อง", bplace(r["cname"], r["title"], bid),
                  "เลื่อน%s จากลำดับที่ %d เป็นลำดับที่ %d ในหมวด \"%s\"" % ("ลง" if down else "ขึ้น", res[0], res[1], r["cname"]))
    return jsonify(ok=True)

# ---- คลังรูปภาพ ----
ALLOWED_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}


@app.get("/api/images")
@staff
def img_list():
    rows = q("SELECT * FROM images ORDER BY id DESC")
    return jsonify(images=[dict(id=r["id"], url="/uploads/" + r["filename"], name=r["original"]) for r in rows])


@app.post("/api/images")
@staff
def img_up():
    files = request.files.getlist("files")
    if not files:
        return err("ไม่พบไฟล์")
    done, skipped = [], []
    for f in files:
        ext = os.path.splitext(f.filename or "")[1].lower()
        if ext not in ALLOWED_EXT:
            skipped.append(clean(f.filename, 80) or "(ไม่มีชื่อ)")
            continue
        name = uuid.uuid4().hex + ext
        f.save(os.path.join(UPLOAD_DIR, name))
        execute("INSERT INTO images(filename,original,created) VALUES(?,?,?)", (name, clean(f.filename, 200), int(time.time())))
        done.append("%s  →  /uploads/%s" % (clean(f.filename, 80), name))
    if not done:
        return err("รองรับเฉพาะไฟล์รูป png jpg gif webp bmp")
    d = "อัปโหลดรูปเข้าคลังรูปภาพ %d ไฟล์:\n%s" % (len(done), "\n".join("   - " + x for x in done))
    if skipped:
        d += "\nไฟล์ที่ถูกข้าม (ชนิดไฟล์ไม่รองรับ): " + ", ".join(skipped)
    audit("อัปโหลดรูปภาพ", "คลังรูปภาพ", d)
    return jsonify(ok=True, count=len(done))


@app.delete("/api/images/<int:iid>")
@staff
def img_del(iid):
    r = q("SELECT filename,original FROM images WHERE id=?", (iid,), one=True)
    if not r:
        return err("ไม่พบรูปภาพ", 404)
    url = "/uploads/" + r["filename"]
    used = q("SELECT b.id,b.title,c.name AS cname FROM blocks b JOIN categories c ON c.id=b.category_id WHERE b.image=?", (url,))
    try:
        os.remove(os.path.join(UPLOAD_DIR, r["filename"]))
    except OSError:
        pass
    c = db()
    c.execute("UPDATE blocks SET image='' WHERE image=?", (url,))
    c.execute("DELETE FROM images WHERE id=?", (iid,))
    c.commit()
    d = "ลบรูป \"%s\" (%s) ออกจากคลังรูปภาพ" % (r["original"] or "-", url)
    if used:
        d += "\nช่องที่เคยใช้รูปนี้ (ถูกเอารูปออกให้อัตโนมัติ) %d ช่อง:\n%s" % (
            len(used), "\n".join("   - %s" % bplace(u["cname"], u["title"], u["id"]) for u in used[:30]))
    audit("ลบรูปภาพ", "คลังรูปภาพ", d)
    return jsonify(ok=True)


@app.get("/uploads/<path:name>")
def serve_upload(name):
    return send_from_directory(UPLOAD_DIR, name)

# ---- จัดการผู้อำนวยการ (เฉพาะผู้ดูแล) ----
def check_cred(username, password, need_pw):
    if len(username) < 3:
        return "ชื่อผู้ใช้ต้องมีอย่างน้อย 3 ตัวอักษร"
    if username == ADMIN_USERNAME:
        return "ชื่อผู้ใช้นี้ถูกใช้โดยผู้ดูแล"
    if (need_pw or password) and len(password) < 4:
        return "รหัสผ่านต้องมีอย่างน้อย 4 ตัวอักษร"
    return None


@app.get("/api/directors")
@admin_only
def dir_list():
    return jsonify(directors=[dict(id=r["id"], username=r["username"]) for r in q("SELECT id,username FROM users ORDER BY id")])


@app.post("/api/directors")
@admin_only
def dir_add():
    d = request.get_json(silent=True) or {}
    u = clean(d.get("username"), 60)
    p = d.get("password") if isinstance(d.get("password"), str) else ""
    e = check_cred(u, p, True)
    if e:
        return err(e)
    try:
        uid = execute("INSERT INTO users(username,password_hash) VALUES(?,?)", (u, generate_password_hash(p)))
    except sqlite3.IntegrityError:
        return err("มีชื่อผู้ใช้นี้อยู่แล้ว")
    audit("เพิ่มบัญชีผู้อำนวยการ", "จัดการผู้อำนวยการ", 'เพิ่มบัญชีผู้อำนวยการใหม่ ชื่อผู้ใช้ "%s" (รหัสบัญชี #%s)' % (u, uid))
    return jsonify(ok=True)


@app.put("/api/directors/<int:uid>")
@admin_only
def dir_edit(uid):
    d = request.get_json(silent=True) or {}
    u = clean(d.get("username"), 60)
    p = d.get("password") if isinstance(d.get("password"), str) else ""
    e = check_cred(u, p, False)
    if e:
        return err(e)
    old = q("SELECT username FROM users WHERE id=?", (uid,), one=True)
    if not old:
        return err("ไม่พบบัญชี", 404)
    try:
        if p:
            execute("UPDATE users SET username=?, password_hash=? WHERE id=?", (u, generate_password_hash(p), uid))
        else:
            execute("UPDATE users SET username=? WHERE id=?", (u, uid))
    except sqlite3.IntegrityError:
        return err("มีชื่อผู้ใช้นี้อยู่แล้ว")
    audit("แก้ไขบัญชีผู้อำนวยการ", 'บัญชี "%s" (รหัสบัญชี #%s)' % (old["username"], uid),
          "• ชื่อผู้ใช้: %s\n• เปลี่ยนรหัสผ่าน: %s" % (
              ("%s → %s" % (old["username"], u)) if old["username"] != u else "ไม่เปลี่ยน (%s)" % u,
              "ใช่ (ผู้ดูแลตั้งรหัสใหม่ให้ ไม่บันทึกตัวรหัสผ่าน)" if p else "ไม่"))
    return jsonify(ok=True)


@app.delete("/api/directors/<int:uid>")
@admin_only
def dir_del(uid):
    old = q("SELECT username FROM users WHERE id=?", (uid,), one=True)
    if not old:
        return err("ไม่พบบัญชี", 404)
    execute("DELETE FROM users WHERE id=?", (uid,))
    audit("ลบบัญชีผู้อำนวยการ", 'บัญชี "%s" (รหัสบัญชี #%s)' % (old["username"], uid), 'ลบบัญชีผู้อำนวยการ "%s" ออกจากระบบ' % old["username"])
    return jsonify(ok=True)

# ---- เช็คย้อนหลัง (เฉพาะผู้ดูแล) ----
@app.get("/api/audit")
@admin_only
def audit_list():
    term = clean(request.args.get("q"), 100)
    before = request.args.get("before", type=int)
    where, args = [], []
    if before:
        where.append("id<?")
        args.append(before)
    if term:
        like = "%" + term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        where.append("(actor LIKE ? ESCAPE '\\' OR action LIKE ? ESCAPE '\\' OR place LIKE ? ESCAPE '\\' OR detail LIKE ? ESCAPE '\\')")
        args += [like] * 4
    sql = "SELECT * FROM audit_log" + (" WHERE " + " AND ".join(where) if where else "") + " ORDER BY id DESC LIMIT 101"
    rows = q(sql, args)
    return jsonify(logs=[dict(r) for r in rows[:100]], more=len(rows) > 100)


@app.get("/")
def index():
    return Response(INDEX_HTML, mimetype="text/html")

# ------------------------------- หน้าเว็บ -------------------------------
INDEX_HTML = r'''<!DOCTYPE html>
<html lang="th">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>กองพันสารวัตรทหารบกที่ ๑๑ - แผนกตรวจสอบภายใน</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Kanit:wght@400;500;600;800&display=swap">
<style>
:root{--bg:#030814;--b1:#1f6bff;--b2:#4aa3ff;--cy:#22d3ee;--vi:#7c5cff;--sv:#c7d2e8;--line:#1b2a4a}
*{box-sizing:border-box}
html,body{margin:0;min-height:100%}
body{font-family:'Kanit','Sarabun','Noto Sans Thai',system-ui,sans-serif;background:var(--bg);color:#e6eeff;overflow-x:hidden}
body:before{content:"";position:fixed;inset:0;z-index:0;pointer-events:none;background:radial-gradient(ellipse at 50% 0,rgba(31,107,255,.34),transparent 60%),radial-gradient(ellipse at 90% 100%,rgba(124,92,255,.2),transparent 55%),radial-gradient(ellipse at 5% 80%,rgba(34,211,238,.13),transparent 50%)}
body:after{content:"";position:fixed;inset:0;z-index:0;pointer-events:none;background:repeating-linear-gradient(0deg,rgba(160,200,255,.025) 0 1px,transparent 1px 3px)}
#bg{position:fixed;inset:0;overflow:hidden;z-index:0;pointer-events:none}
.em{position:absolute;opacity:0;will-change:transform;filter:drop-shadow(0 0 12px rgba(74,163,255,.75))}
.em.up{bottom:-100px;animation:up linear infinite}
.em.dn{top:-100px;animation:dn linear infinite}
@keyframes up{0%{transform:translateY(0);opacity:0}10%,90%{opacity:.6}100%{transform:translateY(-125vh);opacity:0}}
@keyframes dn{0%{transform:translateY(0);opacity:0}10%,90%{opacity:.6}100%{transform:translateY(125vh);opacity:0}}
.em i{display:inline-block;font-style:normal;animation:sway ease-in-out infinite alternate}
@keyframes sway{from{transform:translateX(calc(var(--sw) * -1))}to{transform:translateX(var(--sw))}}
.page{position:relative;z-index:1}
#landing{min-height:100vh;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:18px;padding:30px 16px;text-align:center}
#landing img{width:min(72vw,340px);height:auto;filter:drop-shadow(0 0 28px rgba(31,107,255,.8));animation:pulse 3s ease-in-out infinite}
@keyframes pulse{50%{filter:drop-shadow(0 0 54px rgba(74,163,255,1))}}
h1.big{margin:0;font-size:clamp(30px,6.5vw,68px);font-weight:800;letter-spacing:1px;background:linear-gradient(180deg,#fff 30%,#8fc0ff);-webkit-background-clip:text;background-clip:text;color:transparent;filter:drop-shadow(0 0 18px rgba(31,107,255,.8))}
h2.sub{margin:0;font-size:clamp(20px,3.6vw,34px);font-weight:500;color:var(--cy);letter-spacing:3px;text-shadow:0 0 16px rgba(34,211,238,.45)}
.btn{cursor:pointer;border:1px solid var(--b2);background:linear-gradient(180deg,#2563eb,#0f2d7a);color:#fff;font:600 16px 'Kanit',sans-serif;padding:9px 20px;border-radius:4px;transition:.2s}
.btn:hover{box-shadow:0 0 18px rgba(74,163,255,.75);filter:brightness(1.18)}
.btn:focus-visible,.tab:focus-visible{outline:2px solid #f5c400;outline-offset:2px}
.btn.big{font-size:22px;padding:14px 48px;border:none;margin-top:10px;background:linear-gradient(90deg,#1d4ed8,#2f8cff,#22d3ee);clip-path:polygon(14px 0,100% 0,calc(100% - 14px) 100%,0 100%)}
.btn.sm{font-size:14px;padding:5px 12px}
.btn.ghost{background:#0c1424;border-color:#2b3b5e}
.btn.danger{background:#4a0f26;border-color:#ff5c7a}
#app{display:none;min-height:100vh;padding-bottom:60px}
header.top{display:flex;gap:18px;align-items:center;padding:18px 52px 14px 18px;border-bottom:2px solid transparent;border-image:linear-gradient(90deg,#1f6bff,#22d3ee,#7c5cff,#1f6bff) 1;background:linear-gradient(180deg,rgba(2,6,18,.9),rgba(8,20,60,.6))}
header .logo{width:clamp(56px,9vw,96px);height:auto;filter:drop-shadow(0 0 12px rgba(31,107,255,.8))}
header h1{margin:0;font-size:clamp(20px,4vw,40px);font-weight:800;background:linear-gradient(180deg,#fff 30%,#8fc0ff);-webkit-background-clip:text;background-clip:text;color:transparent;filter:drop-shadow(0 0 12px rgba(31,107,255,.7))}
header h2{margin:2px 0 0;font-size:clamp(14px,2.4vw,22px);color:var(--cy);font-weight:500}
.desc{margin-top:6px;color:#aebfdc;white-space:pre-wrap;font-size:15px;max-width:80ch}
.sbar{display:flex;flex-wrap:wrap;gap:8px;align-items:center;padding:8px 14px;background:#07122e;border-bottom:1px solid var(--b1)}
nav{position:sticky;top:0;z-index:5;display:flex;gap:6px;flex-wrap:wrap;padding:10px 52px 10px 14px;background:rgba(3,8,20,.94);border-bottom:1px solid var(--line);backdrop-filter:blur(6px)}
.tab{cursor:pointer;background:#0b1426;color:#cfdcf5;border:1px solid #243457;border-bottom:3px solid #243457;padding:8px 18px;font:500 16px 'Kanit',sans-serif;border-radius:3px;transition:.15s}
.tab:hover{border-bottom-color:var(--cy);color:#fff}
.tab.on{background:linear-gradient(180deg,#143a96,#0b2160);color:#fff;border-color:var(--b1);border-bottom-color:var(--cy)}
.tab.add{border-style:dashed;color:#f5c400}
main{max-width:1200px;margin:0 auto;padding:18px}
.ctools{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin-bottom:16px;padding:10px;border:1px dashed #254a9c;background:rgba(10,25,70,.5)}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:16px}
.card{background:rgba(8,15,34,.9);border:1px solid var(--line);border-left:4px solid var(--b1);border-radius:4px;overflow:hidden;transition:.2s}
.card:hover{box-shadow:0 0 22px rgba(47,140,255,.28)}
.card:nth-child(4n+2){border-left-color:var(--cy)}
.card:nth-child(4n+3){border-left-color:var(--vi)}
.card:nth-child(4n){border-left-color:var(--sv)}
.cimg{display:block;width:100%;max-height:380px;object-fit:contain;background:#000;cursor:zoom-in}
.cb{padding:14px}
.cb h3{margin:0 0 8px;font-size:21px;color:#fff}
.txt{white-space:pre-wrap;word-break:break-word;color:#c3d0ea;line-height:1.6}
.row{display:flex;flex-wrap:wrap;gap:8px;margin-top:12px;align-items:center}
.row.end{justify-content:flex-end}
.grow{flex:1}
.muted{color:#7f92b8}
.ov{position:fixed;inset:0;background:rgba(1,4,12,.82);z-index:50;display:flex;align-items:center;justify-content:center;padding:14px;overflow:auto}
.box{background:#07101f;border:1px solid var(--b1);box-shadow:0 0 40px rgba(31,107,255,.45);border-radius:6px;padding:20px;width:min(520px,100%);max-height:92vh;overflow:auto}
.box.wide{width:min(900px,100%)}
.box h3{margin:0 0 14px;font-size:22px}
.fld{display:block;margin-bottom:12px}
.fld>span{display:block;margin-bottom:5px;color:#a9bad9;font-size:14px}
input,textarea{width:100%;background:#030814;border:1px solid #2b3b5e;color:#fff;padding:10px;border-radius:4px;font:16px 'Kanit',sans-serif}
input:focus,textarea:focus{outline:none;border-color:var(--b2);box-shadow:0 0 8px rgba(74,163,255,.55)}
.err{color:#ff8fa6;min-height:18px;font-size:14px}
.pv{max-width:100%;max-height:180px;margin-bottom:6px;border:1px solid #2b3b5e}
.gal{display:grid;grid-template-columns:repeat(auto-fill,minmax(120px,1fr));gap:10px;margin:12px 0}
.gi{position:relative;aspect-ratio:1;background:#000;border:1px solid #2b3b5e}
.gi img{width:100%;height:100%;object-fit:cover;cursor:pointer;display:block}
.gi .x{position:absolute;top:3px;right:3px;background:#4a0f26;color:#fff;border:1px solid #ff5c7a;border-radius:3px;cursor:pointer;font-size:13px;padding:1px 6px}
.drow{display:flex;gap:8px;align-items:center;padding:8px 0;border-bottom:1px solid #1b2a4a}
.lg{border:1px solid var(--line);border-left:4px solid var(--b2);background:#060c1b;padding:10px 12px;margin-bottom:10px;border-radius:4px}
.lg .t{color:#93a8d0;font-size:13px}
.lg .pl{color:#d3e3ff;font-weight:500}
.lg pre{margin:8px 0 0;white-space:pre-wrap;word-break:break-word;font:14px/1.55 'Kanit',sans-serif;color:#c3d0ea;background:#02050d;padding:8px 10px;border-radius:3px}
.bd{display:inline-block;padding:1px 10px;border-radius:10px;font-size:13px;margin-right:8px}
.b-add{background:#0b3b4a;color:#5eead4}.b-edit{background:#11307a;color:#9ec5ff}.b-del{background:#4a0f26;color:#ff8fa6}.b-auth{background:#2a1f6b;color:#c4b5ff}
.lb{background:rgba(0,0,0,.93);cursor:zoom-out}
.lb img{max-width:96vw;max-height:92vh}
#secret{position:fixed;top:0;right:0;width:38px;height:30px;z-index:40;cursor:default}
#secret i{position:absolute;top:9px;right:9px;width:14px;height:3px;background:#f5c400;opacity:.85;border-radius:2px}
.toast{position:fixed;left:50%;bottom:40px;transform:translateX(-50%);background:#0a1a3f;border:1px solid var(--b2);padding:10px 18px;border-radius:6px;z-index:99;max-width:90vw}
@media(prefers-reduced-motion:reduce){.em,.em i{animation-duration:120s!important}}
</style>
</head>
<body>
<div id="bg"></div>
<div id="secret" title=""><i></i></div>

<div class="page">
  <section id="landing">
    <img id="l-logo" alt="โลโก้">
    <h1 class="big" id="l-title"></h1>
    <h2 class="sub" id="l-sub"></h2>
    <button class="btn big" id="enter">เข้าสู่ระบบเว็บไซต์</button>
  </section>

  <section id="app">
    <header class="top">
      <img class="logo" id="a-logo" alt="โลโก้">
      <div>
        <h1 id="a-title"></h1>
        <h2 id="a-sub"></h2>
        <div class="desc" id="a-desc"></div>
        <div id="a-desc-tools"></div>
      </div>
    </header>
    <div class="sbar" id="sbar" style="display:none"></div>
    <nav id="nav"></nav>
    <main id="main"></main>
  </section>
</div>

<script>
const $=s=>document.querySelector(s);
const S={site:{},cats:[],me:null,cur:null};

function h(tag,props,...kids){
  const e=document.createElement(tag);
  for(const[k,v]of Object.entries(props||{})){
    if(v===false||v==null)continue;
    if(k==='class')e.className=v;
    else if(k==='value')e.value=v;
    else if(k.startsWith('on'))e.addEventListener(k.slice(2),v);
    else e.setAttribute(k,v);
  }
  for(const c of kids.flat()){if(c===null||c===undefined||c===false)continue;e.append(c)}
  return e;
}
function toast(m){const t=h('div',{class:'toast'},m);document.body.append(t);setTimeout(()=>t.remove(),3800)}

async function api(method,url,body){
  const o={method,headers:{},credentials:'same-origin'};
  if(body instanceof FormData)o.body=body;
  else if(body!==undefined){o.headers['Content-Type']='application/json';o.body=JSON.stringify(body)}
  let r;
  try{r=await fetch(url,o)}catch(e){throw new Error('เชื่อมต่อเซิร์ฟเวอร์ไม่ได้')}
  let d={};try{d=await r.json()}catch(e){}
  if(!r.ok)throw new Error(d.error||('เกิดข้อผิดพลาด ('+r.status+')'));
  return d;
}

/* ---------- พื้นหลัง ⚖️ 📁 🔎 ขึ้นสลับลง และแกว่งซ้ายสลับขวา ---------- */
(function(){
  const EM=['⚖️','📁','🔎'];
  const bg=$('#bg');
  for(let i=0;i<30;i++){
    const inner=h('i',{},EM[i%3]);
    const s=h('span',{class:'em '+(i%2?'dn':'up')},inner);
    s.style.cssText='left:'+(Math.random()*96)+'%;font-size:'+(28+Math.random()*50)+'px;animation-duration:'+(18+Math.random()*24)+'s;animation-delay:-'+(Math.random()*40)+'s';
    inner.style.cssText='--sw:'+(30+Math.random()*90)+'px;animation-duration:'+(4+Math.random()*5)+'s;animation-direction:'+(i%4<2?'alternate':'alternate-reverse');
    bg.append(s);
  }
})();

/* ---------- ป๊อปอัป ---------- */
function overlay(node,cls){
  const ov=h('div',{class:'ov '+(cls||'')},node);
  const close=()=>ov.remove();
  ov.addEventListener('mousedown',e=>{if(e.target===ov)close()});
  document.body.append(ov);
  return close;
}
function zoom(src){const c=overlay(h('img',{src,onclick:()=>c()}),'lb')}

function imgField(v){
  let val=v;
  const pv=h('img',{class:'pv',alt:''});
  const draw=()=>{pv.style.display=val?'block':'none';if(val)pv.src=val};
  const root=h('div',{},pv,h('div',{class:'row',style:'margin-top:0'},
    h('button',{type:'button',class:'btn sm',onclick:()=>library(u=>{val=u;draw()})},'📁 เลือกจากคลังรูปภาพ'),
    h('button',{type:'button',class:'btn sm ghost',onclick:()=>{val='';draw()}},'ไม่ใช้รูป')));
  draw();
  return{root,get:()=>val};
}

function ask(title,fields,okText,submit){
  const got={};const form=h('div',{});
  const msg=h('div',{class:'err'});
  let busy=false;
  const ok=h('button',{class:'btn',onclick:async()=>{
    if(busy)return;busy=true;msg.textContent='';
    const o={};for(const k in got)o[k]=got[k]();
    try{await submit(o);close()}catch(e){msg.textContent=e.message}
    busy=false;
  }},okText||'ตกลง');
  for(const f of fields){
    let node,get;
    if(f.type==='image'){const x=imgField(f.value||'');node=x.root;get=x.get}
    else{
      const el=f.type==='textarea'?h('textarea',{rows:7}):h('input',{type:f.type||'text',autocomplete:'off'});
      el.value=f.value||'';
      if(f.type!=='textarea')el.addEventListener('keydown',e=>{if(e.key==='Enter')ok.click()});
      node=el;get=()=>el.value;
    }
    got[f.key]=get;
    form.append(h('div',{class:'fld'},h('span',{},f.label),node));
  }
  const close=overlay(h('div',{class:'box'},h('h3',{},title),form,msg,
    h('div',{class:'row end'},h('button',{class:'btn ghost',onclick:()=>close()},'ยกเลิก'),ok)));
  const first=form.querySelector('input,textarea');if(first)first.focus();
}

/* ---------- คลังรูปภาพ ---------- */
function library(onPick){
  const grid=h('div',{class:'gal'});
  const file=h('input',{type:'file',accept:'image/*',multiple:'multiple',style:'display:none'});
  async function load(){
    try{
      const d=await api('GET','/api/images');
      grid.replaceChildren(...d.images.map(im=>h('div',{class:'gi'},
        h('img',{src:im.url,loading:'lazy',alt:im.name||'',onclick:()=>{if(onPick){onPick(im.url);close()}else zoom(im.url)}}),
        h('button',{class:'x',title:'ลบรูป',onclick:async e=>{
          e.stopPropagation();if(!confirm('ลบรูปนี้ออกจากคลัง?'))return;
          try{await api('DELETE','/api/images/'+im.id);load()}catch(x){toast(x.message)}}},'✕'))));
      if(!d.images.length)grid.replaceChildren(h('p',{class:'muted'},'ยังไม่มีรูปในคลัง กดอัปโหลดเพื่อเพิ่มรูป'));
    }catch(e){toast(e.message)}
  }
  file.addEventListener('change',async()=>{
    if(!file.files.length)return;
    const fd=new FormData();for(const f of file.files)fd.append('files',f);
    try{await api('POST','/api/images',fd);toast('อัปโหลดสำเร็จ')}catch(e){toast(e.message)}
    file.value='';load();
  });
  const close=overlay(h('div',{class:'box wide'},
    h('h3',{},onPick?'🖼️ เลือกรูปจากคลังรูปภาพ':'🖼️ คลังรูปภาพ'),
    h('div',{class:'row',style:'margin-top:0'},h('button',{class:'btn',onclick:()=>file.click()},'⬆️ อัปโหลดรูป'),file),
    grid,h('div',{class:'row end'},h('button',{class:'btn ghost',onclick:()=>close()},'ปิด'))));
  load();
}

/* ---------- แสดงผล ---------- */
async function refreshState(){
  const d=await api('GET','/api/state');
  S.site=d.site;S.cats=d.cats;S.me=d.me;
  if(!S.cats.find(c=>c.id===S.cur))S.cur=S.cats.length?S.cats[0].id:null;
}
function fillLanding(){
  $('#l-logo').src=S.site.logo;$('#l-title').textContent=S.site.title;$('#l-sub').textContent=S.site.subtitle;
  $('#a-logo').src=S.site.logo;$('#a-title').textContent=S.site.title;$('#a-sub').textContent=S.site.subtitle;
}
function enter(){
  $('#landing').style.display='none';$('#app').style.display='block';
  window.scrollTo(0,0);renderAll();
}
function renderAll(){renderHeader();renderBar();renderNav();renderPage()}

function renderHeader(){
  $('#a-desc').textContent=S.site.description||'';
  const t=$('#a-desc-tools');t.replaceChildren();
  if(S.me)t.append(h('button',{class:'btn sm ghost',style:'margin-top:8px',onclick:editDesc},'✏️ แก้ไขคำอธิบาย'));
}
function editDesc(){
  ask('แก้ไขคำอธิบาย',[{key:'description',label:'คำอธิบาย',type:'textarea',value:S.site.description}],'บันทึก',async v=>{
    await api('POST','/api/description',v);await refreshState();renderHeader()});
}
function renderBar(){
  const b=$('#sbar');
  if(!S.me){b.style.display='none';b.replaceChildren();return}
  b.style.display='flex';
  b.replaceChildren(
    h('b',{},'👤 '+S.me.username+' ('+(S.me.role==='admin'?'ผู้ดูแล':'ผู้อำนวยการ')+')'),
    h('span',{class:'grow'}),
    h('button',{class:'btn sm',onclick:()=>library(null)},'🖼️ คลังรูปภาพ'),
    h('button',{class:'btn sm',onclick:changePw},'🔑 เปลี่ยนรหัสผ่าน'),
    S.me.role==='admin'&&h('button',{class:'btn sm',onclick:auditView},'📜 เช็คย้อนหลัง'),
    S.me.role==='admin'&&h('button',{class:'btn sm',onclick:directors},'👥 จัดการผู้อำนวยการ'),
    h('button',{class:'btn sm ghost',onclick:logout},'🚪 ออกจากระบบ'));
}
function renderNav(){
  const n=$('#nav');
  n.replaceChildren(...S.cats.map(c=>h('button',{class:'tab'+(c.id===S.cur?' on':''),onclick:()=>{S.cur=c.id;renderNav();renderPage()}},(c.is_home?'🏠 ':'')+c.name)));
  if(S.me)n.append(h('button',{class:'tab add',onclick:addCat},'＋ เพิ่มหมวดหมู่'));
}
let rtok=0;
async function renderPage(){
  const m=$('#main');const tok=++rtok;
  const cat=S.cats.find(c=>c.id===S.cur);
  if(!cat){m.replaceChildren();return}
  let d;
  try{d=await api('GET','/api/category/'+cat.id)}catch(e){m.replaceChildren(h('p',{class:'muted'},e.message));return}
  if(tok!==rtok)return;
  const kids=[];
  if(S.me)kids.push(h('div',{class:'ctools'},h('b',{},'หมวด: '+cat.name),
    h('button',{class:'btn sm',onclick:()=>blockForm(null)},'＋ เพิ่มช่อง'),
    h('button',{class:'btn sm ghost',onclick:()=>renameCat(cat)},'✏️ เปลี่ยนชื่อ'),
    !cat.is_home&&h('button',{class:'btn sm ghost',onclick:()=>moveCat(cat.id,'up')},'◀ เลื่อนซ้าย'),
    !cat.is_home&&h('button',{class:'btn sm ghost',onclick:()=>moveCat(cat.id,'down')},'เลื่อนขวา ▶'),
    !cat.is_home&&h('button',{class:'btn sm danger',onclick:()=>delCat(cat)},'🗑 ลบหมวดหมู่')));
  if(d.blocks.length)kids.push(h('div',{class:'grid'},d.blocks.map(card)));
  else kids.push(h('p',{class:'muted'},S.me?'ยังไม่มีช่องในหมวดนี้ กด "＋ เพิ่มช่อง" เพื่อเริ่มต้น':'ยังไม่มีข้อมูลในหมวดนี้'));
  m.replaceChildren(...kids);
}
function card(b){
  const body=h('div',{class:'cb'});
  if(b.title)body.append(h('h3',{},b.title));
  if(b.body)body.append(h('div',{class:'txt'},b.body));
  if(S.me)body.append(h('div',{class:'row'},
    h('button',{class:'btn sm ghost',onclick:()=>blockForm(b)},'✏️ แก้ไข'),
    h('button',{class:'btn sm ghost',onclick:()=>moveBlock(b.id,'up')},'▲'),
    h('button',{class:'btn sm ghost',onclick:()=>moveBlock(b.id,'down')},'▼'),
    h('button',{class:'btn sm danger',onclick:()=>delBlock(b.id)},'🗑 ลบ')));
  return h('div',{class:'card'},b.image&&h('img',{class:'cimg',src:b.image,alt:b.title||'',loading:'lazy',onclick:()=>zoom(b.image)}),body);
}

/* ---------- การกระทำของผู้อำนวยการ/ผู้ดูแล ---------- */
const guard=fn=>async(...a)=>{try{await fn(...a)}catch(e){toast(e.message)}};
function addCat(){
  ask('เพิ่มหมวดหมู่',[{key:'name',label:'ชื่อหมวดหมู่'}],'ตกลง',async v=>{
    const d=await api('POST','/api/category',v);await refreshState();S.cur=d.id;renderAll()});
}
function renameCat(c){
  ask('เปลี่ยนชื่อหมวดหมู่',[{key:'name',label:'ชื่อหมวดหมู่',value:c.name}],'บันทึก',async v=>{
    await api('PUT','/api/category/'+c.id,v);await refreshState();renderNav();renderPage()});
}
const moveCat=guard(async(id,dir)=>{await api('POST','/api/category/'+id+'/move',{dir});await refreshState();renderNav()});
const delCat=guard(async c=>{
  if(!confirm('ลบหมวดหมู่ "'+c.name+'" และทุกช่องในหมวดนี้?'))return;
  await api('DELETE','/api/category/'+c.id);S.cur=null;await refreshState();renderAll()});
function blockForm(b){
  ask(b?'แก้ไขช่อง':'เพิ่มช่อง',[
    {key:'title',label:'หัวข้อ',value:b?b.title:''},
    {key:'body',label:'รายละเอียด',type:'textarea',value:b?b.body:''},
    {key:'image',label:'รูปภาพ (เลือกจากคลังรูปภาพ)',type:'image',value:b?b.image:''}],'ตกลง',async v=>{
    if(b)await api('PUT','/api/block/'+b.id,v);
    else await api('POST','/api/block',{...v,category_id:S.cur});
    renderPage()});
}
const moveBlock=guard(async(id,dir)=>{await api('POST','/api/block/'+id+'/move',{dir});renderPage()});
const delBlock=guard(async id=>{if(!confirm('ลบช่องนี้?'))return;await api('DELETE','/api/block/'+id);renderPage()});

function changePw(){
  ask('🔑 เปลี่ยนรหัสผ่าน',[
    {key:'current',label:'รหัสผ่านปัจจุบัน',type:'password'},
    {key:'new',label:'รหัสผ่านใหม่',type:'password'}],'เปลี่ยนรหัสผ่าน',async v=>{
    await api('POST','/api/password',v);toast('เปลี่ยนรหัสผ่านเรียบร้อยแล้ว')});
}

function directors(){
  const list=h('div',{});
  const close=overlay(h('div',{class:'box wide'},h('h3',{},'👥 จัดการผู้อำนวยการ'),list,
    h('div',{class:'row end'},h('button',{class:'btn',onclick:addDir},'＋ เพิ่มผู้อำนวยการ'),h('button',{class:'btn ghost',onclick:()=>close()},'ปิด'))));
  async function load(){
    try{
      const d=await api('GET','/api/directors');
      list.replaceChildren(...(d.directors.length?d.directors.map(u=>h('div',{class:'drow'},
        h('b',{},u.username),h('span',{class:'grow'}),
        h('button',{class:'btn sm',onclick:()=>editDir(u)},'✏️ แก้ไข'),
        h('button',{class:'btn sm danger',onclick:async()=>{
          if(!confirm('ลบบัญชี '+u.username+' ?'))return;
          try{await api('DELETE','/api/directors/'+u.id);load()}catch(e){toast(e.message)}}},'🗑 ลบ'))):[h('p',{class:'muted'},'ยังไม่มีผู้อำนวยการ')]));
    }catch(e){toast(e.message)}
  }
  function addDir(){ask('เพิ่มผู้อำนวยการ',[{key:'username',label:'ชื่อผู้ใช้'},{key:'password',label:'รหัสผ่าน',type:'password'}],'ตกลง',async v=>{await api('POST','/api/directors',v);load()})}
  function editDir(u){ask('แก้ไขบัญชี '+u.username,[{key:'username',label:'ชื่อผู้ใช้',value:u.username},{key:'password',label:'รหัสผ่านใหม่ (เว้นว่าง = ไม่เปลี่ยน)',type:'password'}],'บันทึก',async v=>{await api('PUT','/api/directors/'+u.id,v);load()})}
  load();
}

/* ---------- เช็คย้อนหลัง (ผู้ดูแล) ---------- */
function fmtTime(ts){
  return new Date(ts*1000).toLocaleString('th-TH',{timeZone:'Asia/Bangkok',day:'2-digit',month:'2-digit',year:'numeric',hour:'2-digit',minute:'2-digit',second:'2-digit',hourCycle:'h23'})+' น.';
}
function logRow(l){
  const a=l.action;
  const cls=/ลบ|ไม่สำเร็จ/.test(a)?'b-del':/เพิ่ม|สร้าง|อัปโหลด/.test(a)?'b-add':/เข้าสู่ระบบ|ออกจากระบบ/.test(a)?'b-auth':'b-edit';
  const who=l.actor+(l.role?' ('+(l.role==='admin'?'ผู้ดูแล':'ผู้อำนวยการ')+')':'');
  return h('div',{class:'lg'},
    h('div',{class:'t'},'🕒 วันที่/เวลา: '+fmtTime(l.ts)+'   •   👤 '+who+(l.ip?'   •   IP '+l.ip:'')),
    h('div',{style:'margin-top:4px'},h('span',{class:'bd '+cls},a),h('span',{class:'pl'},l.place?'📍 '+l.place:'')),
    l.detail&&h('pre',{},l.detail));
}
function auditView(){
  const list=h('div',{});
  const more=h('button',{class:'btn sm ghost',style:'display:none',onclick:()=>load(false)},'โหลดรายการที่เก่ากว่า');
  const qi=h('input',{type:'text',placeholder:'ค้นหา: ชื่อผู้ใช้ / การกระทำ / ช่อง / รายละเอียด',style:'flex:1;min-width:180px;width:auto'});
  let last=0,term='';
  const search=h('button',{class:'btn sm',onclick:()=>{term=qi.value.trim();load(true)}},'🔎 ค้นหา');
  qi.addEventListener('keydown',e=>{if(e.key==='Enter')search.click()});
  const close=overlay(h('div',{class:'box wide'},h('h3',{},'📜 เช็คย้อนหลัง — บันทึกการกระทำทั้งหมด'),
    h('div',{class:'row',style:'margin:0 0 12px'},qi,search),list,
    h('div',{class:'row end'},more,h('button',{class:'btn ghost',onclick:()=>close()},'ปิด'))));
  async function load(reset){
    if(reset){last=0;list.replaceChildren()}
    try{
      const d=await api('GET','/api/audit?q='+encodeURIComponent(term)+(last?'&before='+last:''));
      d.logs.forEach(l=>list.append(logRow(l)));
      if(d.logs.length)last=d.logs[d.logs.length-1].id;
      more.style.display=d.more?'':'none';
      if(!list.children.length)list.append(h('p',{class:'muted'},'ไม่พบบันทึก'));
    }catch(e){toast(e.message)}
  }
  load(true);
}

/* ---------- เข้า/ออกจากระบบ ---------- */
$('#secret').addEventListener('click',()=>{
  if(S.me){toast('เข้าสู่ระบบอยู่แล้ว');return}
  ask('เข้าสู่ระบบผู้อำนวยการ / ผู้ดูแล',[{key:'username',label:'ชื่อผู้ใช้'},{key:'password',label:'รหัสผ่าน',type:'password'}],'เข้าสู่ระบบ',async v=>{
    await api('POST','/api/login',v);await refreshState();enter()});
});
const logout=guard(async()=>{await api('POST','/api/logout');await refreshState();renderAll()});
$('#enter').addEventListener('click',enter);

(async()=>{
  try{await refreshState()}catch(e){toast(e.message)}
  fillLanding();
})();
</script>
</body>
</html>
'''

# ------------------------------- เริ่มทำงาน -------------------------------
if __name__ == "__main__":
    print("เปิดเว็บที่ http://localhost:%d" % PORT)
    try:
        from waitress import serve
        serve(app, host=HOST, port=PORT, threads=8)
    except ImportError:
        app.run(host=HOST, port=PORT, threaded=True)

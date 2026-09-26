from flask import Flask,request,redirect,url_for,session,render_template_string,flash,send_from_directory
import sqlite3,os
from pathlib import Path
from functools import wraps
from werkzeug.utils import secure_filename
from datetime import datetime
app=Flask(__name__);app.secret_key='CHANGE-SOMICE-SECRET-KEY'
BASE=Path(__file__).parent;DB=BASE/'somice.db';UP=BASE/'uploads';UP.mkdir(exist_ok=True)
ADMIN=('1389','184224');IMG={'png','jpg','jpeg','webp','gif'}
def con():
 c=sqlite3.connect(DB);c.row_factory=sqlite3.Row;return c
def now():return datetime.now().strftime('%Y-%m-%d %H:%M:%S')
def init():
 c=con();c.executescript('''
CREATE TABLE IF NOT EXISTS laws(id INTEGER PRIMARY KEY AUTOINCREMENT,title,section,content,created);
CREATE TABLE IF NOT EXISTS temples(id INTEGER PRIMARY KEY AUTOINCREMENT,name,ordination_date,temple,status,created);
CREATE TABLE IF NOT EXISTS council(id INTEGER PRIMARY KEY AUTOINCREMENT,royal_name,active_date,temple,details,created);
CREATE TABLE IF NOT EXISTS ordination(id INTEGER PRIMARY KEY AUTOINCREMENT,name,age,temple,chant,kind,birth_temple,reason,status,created);
CREATE TABLE IF NOT EXISTS preceptors(id INTEGER PRIMARY KEY AUTOINCREMENT,username UNIQUE,password,created);
CREATE TABLE IF NOT EXISTS employees(id INTEGER PRIMARY KEY AUTOINCREMENT,username UNIQUE,password,created);
CREATE TABLE IF NOT EXISTS works(id INTEGER PRIMARY KEY AUTOINCREMENT,employee_id,name,count,image,status,created);
CREATE TABLE IF NOT EXISTS study(id INTEGER PRIMARY KEY AUTOINCREMENT,employee_id,name,vassa,level,kind,status,created);
CREATE TABLE IF NOT EXISTS preq(id INTEGER PRIMARY KEY AUTOINCREMENT,employee_id,name,vassa,temple,status,created);
CREATE TABLE IF NOT EXISTS prayers(id INTEGER PRIMARY KEY AUTOINCREMENT,title,link,content,image,created);
CREATE TABLE IF NOT EXISTS salary_setting(id INTEGER PRIMARY KEY CHECK(id=1),open INTEGER);
CREATE TABLE IF NOT EXISTS salary(id INTEGER PRIMARY KEY AUTOINCREMENT,employee_id,name,temple,works,channel,status,created);
''');c.execute('INSERT OR IGNORE INTO salary_setting VALUES(1,0)');c.commit();c.close()
def req(role):
 def deco(f):
  @wraps(f)
  def w(*a,**k):
   if session.get('role')!=role:return redirect(url_for('home'))
   return f(*a,**k)
  return w
 return deco
HEAD='''<!doctype html><html lang="th"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{{title}} | พระสงฆ์สมไอซ์</title><style>@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+Thai:wght@400;600;700;800&display=swap');*{box-sizing:border-box}body{margin:0;background:#f6f0e5;color:#35291d;font-family:"Noto Sans Thai",sans-serif}nav{background:#5b3518;color:#fff;position:sticky;top:0;z-index:5}.nav{max-width:1150px;margin:auto;padding:11px 15px;display:flex;justify-content:space-between;align-items:center;gap:10px}.brand{font-weight:800;font-size:19px}.brand small{display:block;font-size:10px;color:#e8d5b0}.links{display:flex;flex-wrap:wrap;gap:4px}.links a{padding:7px 9px;border-radius:8px;font-size:12px}.links a:hover{background:#7a4c27}.box{max-width:1150px;margin:auto;padding:25px 15px 50px}.hero{background:linear-gradient(135deg,#633b1d,#a96e2c);color:white;padding:30px 23px;border-radius:22px;margin-bottom:18px}.hero h1{margin:0 0 6px}.hero p{margin:0;color:#f8e8ca}.grid{display:grid;grid-template-columns:repeat(3,1fr);gap:15px}.card,.item{background:#fff;border:1px solid #e5d8c5;border-radius:16px;padding:18px;box-shadow:0 5px 18px #55320e0d}.menu{min-height:160px;display:flex;flex-direction:column;justify-content:space-between}.icon{width:46px;height:46px;border-radius:12px;background:#f0e0c6;display:grid;place-items:center;font-size:22px}label{display:block;font-weight:700;margin:11px 0 5px}input,textarea,select{width:100%;padding:11px;border:1px solid #d7c7b1;border-radius:9px;font:inherit}textarea{min-height:120px}.btn{border:0;border-radius:9px;background:#875126;color:white;padding:9px 14px;font:inherit;font-weight:700;cursor:pointer;display:inline-block}.danger{background:#b43c32}.green{background:#507846}.gray{background:#eadfce;color:#50371f}.actions{display:flex;gap:6px;flex-wrap:wrap;margin-top:12px}.badge{background:#f0e2cd;color:#70491f;padding:4px 8px;border-radius:20px;font-size:12px;font-weight:700}.muted{color:#806f5b}.content{white-space:pre-wrap;line-height:1.7}.table{overflow:auto}table{border-collapse:collapse;width:100%}th,td{padding:10px;border-bottom:1px solid #e8dece;text-align:left;vertical-align:top}th{background:#f0e4d1}.flash{background:#fff0c6;border:1px solid #e1c575;padding:10px;border-radius:9px;margin-bottom:14px}.login{max-width:420px;margin:30px auto}.center{text-align:center}.footer{text-align:center;color:#806f5b;font-size:12px;padding:20px}@media(max-width:800px){.grid{grid-template-columns:1fr}.nav{flex-direction:column;align-items:flex-start}.hero h1{font-size:25px}}</style></head><body><nav><div class="nav"><a class="brand" href="/">พระสงฆ์สมไอซ์<small>ระบบบริหารข้อมูลคณะสงฆ์</small></a><div class="links"><a href="/">หน้าแรก</a><a href="/laws">กฎหมาย</a><a href="/temples">ทะเบียนวัด</a><a href="/council">มหาเถรสมาคม</a><a href="/ordination">ระบบบวช</a><a href="/education">นักธรรม/เปรียญ</a><a href="/prayers">บทสวด</a><a href="/salary">เงินเดือน</a>{%if session.get('role')=='admin'%}<a href="/admin">Admin</a>{%elif session.get('role')=='employee'%}<a href="/employee">พนักงาน</a>{%elif session.get('role')=='preceptor'%}<a href="/preceptor">อุปัชฌาย์</a>{%endif%}{%if session.get('role')%}<a href="/logout">ออก</a>{%endif%}</div></div></nav><main class="box">{%for m in get_flashed_messages()%}<div class="flash">{{m}}</div>{%endfor%}'''
FOOT='</main><div class="footer">พระสงฆ์สมไอซ์ • ระบบตัวอย่างสำหรับใช้งานภายในกลุ่ม</div></body></html>'
def page(b,title='พระสงฆ์สมไอซ์',**x):return render_template_string(HEAD+b+FOOT,title=title,**x)
@app.route('/')
def home():
 return page('''<div class="hero"><h1>พระสงฆ์สมไอซ์</h1><p>ศูนย์รวมกฎหมาย ทะเบียน ระบบบวช การศึกษา ผลงาน และเงินเดือน</p></div><div class="grid">{%for u,ic,t,d in items%}<a class="card menu" href="{{u}}"><div><div class="icon">{{ic}}</div><h2>{{t}}</h2><p class="muted">{{d}}</p></div></a>{%endfor%}</div>''',items=[('/laws','📜','กฎหมายคณะสงฆ์','อ่านกฎหมาย มาตรา และเนื้อหา'),('/temples','🏯','ทะเบียนวัด','รายชื่อและสถานะในทะเบียน'),('/council','🪷','ทะเบียนมหาเถรสมาคม','ราชทินนามและวัดที่ประจำ'),('/ordination','🙏','ระบบบวช','ส่งคำขอบวช'),('/education','📚','สมัครนักธรรมและเปรียญธรรม','ส่งใบสมัคร'),('/employee/login','👨‍💼','ระบบพนักงาน','ลงผลงานและเบิกเงินเดือน'),('/preceptor/login','🧘','ระบบพระอุปัชฌาย์','จัดการคำขอบวช'),('/prayers','📖','บทสวดมนต์','หนังสือ ลิงก์ รูปภาพ ข้อความ'),('/admin/login','⚙️','ระบบ Admin','จัดการข้อมูลทั้งหมด')])
@app.route('/laws')
def laws():
 c=con();r=c.execute('select * from laws order by id').fetchall();c.close();return page('''<div class="hero"><h1>📜 กฎหมายคณะสงฆ์</h1></div>{%for x in r%}<div class="item"><b>ลำดับ {{loop.index}}</b><h2>{{x.title}}</h2><div class="muted">มาตรา {{x.section}}</div><div class="content">{{x.content}}</div></div>{%else%}<div class="card center">ยังไม่มีข้อมูล</div>{%endfor%}''','กฎหมาย',r=r)
@app.route('/temples')
def temples():
 c=con();r=c.execute('select * from temples order by id').fetchall();c.close();return page('''<div class="hero"><h1>🏯 ทะเบียนวัด</h1></div><div class="card table"><table><tr><th>ลำดับ</th><th>ชื่อ/ฉายา</th><th>วันที่บวช</th><th>วัด</th><th>สถานะ</th></tr>{%for x in r%}<tr><td>{{loop.index}}</td><td>{{x.name}}</td><td>{{x.ordination_date}}</td><td>{{x.temple}}</td><td>{{x.status}}</td></tr>{%else%}<tr><td colspan="5">ยังไม่มีข้อมูล</td></tr>{%endfor%}</table></div>''','ทะเบียนวัด',r=r)
@app.route('/council')
def council():
 c=con();r=c.execute('select * from council order by id').fetchall();c.close();return page('''<div class="hero"><h1>🪷 ทะเบียนมหาเถรสมาคม</h1></div><div class="card table"><table><tr><th>ราชทินนาม</th><th>วันที่ประจำ</th><th>วัด</th><th>รายละเอียด</th></tr>{%for x in r%}<tr><td>{{x.royal_name}}</td><td>{{x.active_date}}</td><td>{{x.temple}}</td><td>{{x.details}}</td></tr>{%else%}<tr><td colspan="4">ยังไม่มีข้อมูล</td></tr>{%endfor%}</table></div>''','มหาเถรสมาคม',r=r)
@app.route('/ordination',methods=['GET','POST'])
def ordination():
 if request.method=='POST':
  f=[request.form.get(x,'').strip() for x in ['name','age','temple','chant','kind','birth','reason']]
  if all(f):
   c=con();c.execute('insert into ordination(name,age,temple,chant,kind,birth_temple,reason,status,created) values(?,?,?,?,?,?,?,?,?)',(*f,'รออนุมัติ',now()));c.commit();c.close();flash('ส่งคำขอบวชไปยังระบบพระอุปัชฌาย์แล้ว')
 c=con();r=c.execute('select * from ordination order by id desc').fetchall();c.close();return page('''<div class="hero"><h1>🙏 ระบบบวช</h1></div><div class="card"><form method="post"><label>ชื่อจริง</label><input name="name" required><label>อายุ</label><input name="age" required><label>สังกัดวัด</label><input name="temple" required><label>ท่องบทสวดได้</label><select name="chant"><option>ได้</option><option>ไม่ได้</option></select><label>บวชสถานะ</label><select name="kind"><option>พระ</option><option>เณร</option></select><label>วัดเกิด</label><input name="birth" required><label>เหตุผล</label><textarea name="reason" required></textarea><button class="btn">ส่งคำขอ</button></form></div><div class="card" style="margin-top:15px"><h2>สถานะ</h2>{%for x in r%}<div class="item">{{x.name}} — <span class="badge">{{x.status}}</span></div>{%endfor%}</div>''','ระบบบวช',r=r)
@app.route('/education',methods=['GET','POST'])
def education():
 if request.method=='POST':
  c=con();c.execute('insert into study(employee_id,name,vassa,level,kind,status,created) values(?,?,?,?,?,?,?)',(0,request.form['name'],request.form['vassa'],request.form['level'],request.form['kind'],'รออนุมัติ',now()));c.commit();c.close();flash('ส่งใบสมัครแล้ว')
 return page('''<div class="hero"><h1>📚 สมัครเรียนนักธรรมและเปรียญธรรม</h1></div><div class="grid">{%for k,t in [('นักธรรม','สมัครนักธรรม'),('เปรียญธรรม','สมัครเปรียญธรรม')]%}<div class="card"><h2>{{t}}</h2><form method="post"><input type="hidden" name="kind" value="{{k}}"><label>ชื่อ</label><input name="name" required><label>พรรษา</label><input name="vassa" required><label>ชั้นที่จะสมัคร</label><input name="level" required><button class="btn">ส่งสมัคร</button></form></div>{%endfor%}</div>''','การศึกษา')
@app.route('/prayers')
def prayers():
 c=con();r=c.execute('select * from prayers order by id desc').fetchall();c.close();return page('''<div class="hero"><h1>📖 บทสวดมนต์</h1></div>{%for x in r%}<div class="item"><h2>{{x.title}}</h2>{%if x.image%}<img src="/uploads/{{x.image}}" style="max-width:100%;border-radius:10px">{%endif%}<div class="content">{{x.content}}</div>{%if x.link%}<a class="btn" href="{{x.link}}" target="_blank">เปิดลิงก์</a>{%endif%}</div>{%else%}<div class="card center">ยังไม่มีบทสวด</div>{%endfor%}''','บทสวดมนต์',r=r)
@app.route('/uploads/<path:f>')
def uploads(f):return send_from_directory(UP,f)
@app.route('/admin/login',methods=['GET','POST'])
def admin_login():
 if request.method=='POST' and (request.form['u'],request.form['p'])==ADMIN:session.clear();session['role']='admin';return redirect('/admin')
 if request.method=='POST':flash('ชื่อหรือรหัส Admin ไม่ถูกต้อง')
 return page('''<div class="card login"><h1>🔐 Admin</h1><form method="post"><label>ชื่อผู้ใช้</label><input name="u" required><label>รหัส</label><input type="password" name="p" required><button class="btn">เข้าสู่ระบบ</button></form></div>''','Admin')
@app.route('/logout')
def logout():session.clear();return redirect('/')
@app.route('/admin')
@req('admin')
def admin():return page('''<div class="hero"><h1>⚙️ ระบบ Admin</h1><p>จัดการข้อมูลทั้งหมด</p></div><div class="grid">{%for u,i,t in links%}<a class="card menu" href="{{u}}"><div class="icon">{{i}}</div><h2>{{t}}</h2></a>{%endfor%}</div>''','Admin',links=[('/admin/laws','📜','จัดการกฎหมาย'),('/admin/temple','🏯','ทะเบียนวัด'),('/admin/council','🪷','มหาเถรสมาคม'),('/admin/ordination','🙏','คำขอบวช'),('/admin/employees','👨‍💼','พนักงาน'),('/admin/works','🏆','อนุมัติผลงาน'),('/admin/study','📚','อนุมัตินักธรรม/เปรียญ'),('/admin/preceptor','🧘','พระอุปัชฌาย์'),('/admin/prayers','📖','บทสวดมนต์'),('/admin/salary','💰','เงินเดือน')])
@app.route('/admin/laws',methods=['GET','POST'])
@req('admin')
def admin_laws():
 if request.method=='POST':
  c=con();c.execute('insert into laws(title,section,content,created) values(?,?,?,?)',(request.form['title'],request.form['section'],request.form['content'],now()));c.commit();c.close();return redirect('/admin/laws')
 c=con();r=c.execute('select * from laws order by id').fetchall();c.close();return page('''<div class="hero"><h1>📜 จัดการกฎหมาย</h1></div><div class="card"><form method="post"><label>ชื่อกฎหมายหลัก</label><input name="title" required><label>มาตรา</label><input name="section" required><label>เนื้อหา/โทษความผิด</label><textarea name="content" required></textarea><button class="btn">ยืนยันเพิ่ม</button></form></div>{%for x in r%}<div class="item"><b>ลำดับ {{loop.index}}</b><h2>{{x.title}}</h2><div>มาตรา {{x.section}}</div><div class="content">{{x.content}}</div><form method="post" action="/admin/laws/del/{{x.id}}" onsubmit="return confirm('ยืนยันการลบ?')"><button class="btn danger">ลบ</button></form></div>{%endfor%}''','จัดการกฎหมาย',r=r)
@app.post('/admin/laws/del/<int:id>')
@req('admin')
def del_law(id):
 c=con();c.execute('delete from laws where id=?',(id,));c.commit();c.close();return redirect('/admin/laws')
@app.route('/admin/temple',methods=['GET','POST'])
@req('admin')
def admin_temple():
 if request.method=='POST':
  c=con();c.execute('insert into temples(name,ordination_date,temple,status,created) values(?,?,?,?,?)',(request.form['name'],request.form['date'],request.form['temple'],request.form.get('status',''),now()));c.commit();c.close()
 c=con();r=c.execute('select * from temples order by id').fetchall();c.close();return page('''<div class="hero"><h1>🏯 เพิ่มบุคคลเข้าวัด</h1></div><div class="card"><form method="post"><label>ชื่อ/ฉายา</label><input name="name" required><label>วันที่บวช</label><input type="date" name="date"><label>วัดที่ประจำ</label><input name="temple" required><label>สถานะ</label><input name="status"><button class="btn">เพิ่ม</button></form></div><div class="card table" style="margin-top:15px"><table><tr><th>ชื่อ</th><th>วันที่</th><th>วัด</th><th>สถานะ</th></tr>{%for x in r%}<tr><td>{{x.name}}</td><td>{{x.ordination_date}}</td><td>{{x.temple}}</td><td>{{x.status}}</td></tr>{%endfor%}</table></div>''','ทะเบียนวัด',r=r)
@app.route('/admin/council',methods=['GET','POST'])
@req('admin')
def admin_council():
 if request.method=='POST':
  c=con();c.execute('insert into council(royal_name,active_date,temple,details,created) values(?,?,?,?,?)',(request.form['name'],request.form['date'],request.form['temple'],request.form['details'],now()));c.commit();c.close()
 c=con();r=c.execute('select * from council order by id').fetchall();c.close();return page('''<div class="hero"><h1>🪷 ทะเบียนมหาเถรสมาคม</h1></div><div class="card"><form method="post"><label>ราชทินนาม</label><input name="name" required><label>วันที่ประจำ</label><input type="date" name="date"><label>วัดที่ประจำการ</label><input name="temple" required><label>รายละเอียด</label><textarea name="details"></textarea><button class="btn">เพิ่ม</button></form></div><div class="card table" style="margin-top:15px"><table><tr><th>ราชทินนาม</th><th>วันที่</th><th>วัด</th><th>รายละเอียด</th></tr>{%for x in r%}<tr><td>{{x.royal_name}}</td><td>{{x.active_date}}</td><td>{{x.temple}}</td><td>{{x.details}}</td></tr>{%endfor%}</table></div>''','มหาเถรสมาคม',r=r)
@app.route('/admin/ordination')
@req('admin')
def admin_ord():
 c=con();r=c.execute('select * from ordination order by id desc').fetchall();c.close();return page('''<div class="hero"><h1>🙏 คำขอบวช</h1></div>{%for x in r%}<div class="item"><h2>{{x.name}} <span class="badge">{{x.status}}</span></h2><p>อายุ {{x.age}} • วัด {{x.temple}} • {{x.kind}} • บทสวด {{x.chant}}</p><p>วัดเกิด {{x.birth_temple}}<br>{{x.reason}}</p>{%if x.status=='รออนุมัติ'%}<div class="actions"><a class="btn green" href="/admin/ord/{{x.id}}/อนุมัติ">อนุมัติ</a><a class="btn danger" href="/admin/ord/{{x.id}}/ปฏิเสธ">ปฏิเสธ</a></div>{%elif x.status=='อนุมัติ'%}<form method="post" action="/admin/ord/complete/{{x.id}}"><label>ชื่อฉายา</label><input name="monastic" required><label>วันที่บวช</label><input type="date" name="date" required><label>สังกัดวัด</label><input name="temple" value="{{x.temple}}" required><button class="btn green">ยืนยันบวชเสร็จ</button></form>{%endif%}</div>{%endfor%}''','คำขอบวช',r=r)
@app.get('/admin/ord/<int:id>/<decision>')
@req('admin')
def decide_ord(id,decision):
 if decision in ['อนุมัติ','ปฏิเสธ']:
  c=con();c.execute('update ordination set status=? where id=?',(decision,id));c.commit();c.close()
 return redirect('/admin/ordination')
@app.post('/admin/ord/complete/<int:id>')
@req('admin')
def complete(id):
 c=con();x=c.execute('select * from ordination where id=?',(id,)).fetchone();m=request.form['monastic'];d=request.form['date'];t=request.form['temple'];c.execute('insert into temples(name,ordination_date,temple,status,created) values(?,?,?,?,?)',(m,d,t,'บวชแล้ว',now()));c.execute("update ordination set status='บวชเสร็จ' where id=?",(id,));c.commit();c.close();return redirect('/admin/ordination')
@app.route('/admin/employees',methods=['GET','POST'])
@req('admin')
def admin_emp():
 if request.method=='POST':
  try:
   c=con();c.execute('insert into employees(username,password,created) values(?,?,?)',(request.form['name'],request.form['pass'],now()));c.commit();c.close()
  except sqlite3.IntegrityError:flash('ชื่อพนักงานซ้ำ')
 c=con();r=c.execute('select * from employees').fetchall();c.close();return page('''<div class="hero"><h1>👨‍💼 ระบบพนักงาน</h1></div><div class="card"><form method="post"><label>ชื่อ</label><input name="name" required><label>รหัส</label><input name="pass" required><button class="btn">เพิ่มพนักงาน</button></form></div><div class="card" style="margin-top:15px">{%for x in r%}<div class="item">{{x.username}}</div>{%endfor%}</div>''','พนักงาน',r=r)
@app.route('/employee/login',methods=['GET','POST'])
def emp_login():
 if request.method=='POST':
  c=con();x=c.execute('select * from employees where username=? and password=?',(request.form['u'],request.form['p'])).fetchone();c.close()
  if x:session.clear();session.update(role='employee',eid=x.id);return redirect('/employee')
  flash('ข้อมูลพนักงานไม่ถูกต้อง')
 return page('''<div class="card login"><h1>👨‍💼 พนักงาน</h1><form method="post"><label>ชื่อ</label><input name="u" required><label>รหัส</label><input type="password" name="p" required><button class="btn">เข้าสู่ระบบ</button></form></div>''','พนักงาน')
@app.route('/employee',methods=['GET'])
@req('employee')
def employee():
 c=con();e=c.execute('select * from employees where id=?',(session['eid'],)).fetchone();w=c.execute('select * from works where employee_id=? order by id desc',(e.id,)).fetchall();total=c.execute("select coalesce(sum(count),0) from works where employee_id=? and status='อนุมัติ'",(e.id,)).fetchone()[0];op=c.execute('select open from salary_setting where id=1').fetchone()[0];c.close();return page('''<div class="hero"><h1>👨‍💼 {{e.username}}</h1><p>ผลงานที่อนุมัติ {{total}} รายการ</p></div><div class="grid"><div class="card"><h2>🏆 ลงผลงาน</h2><form method="post" action="/employee/work" enctype="multipart/form-data"><label>ชื่อ</label><input name="name" required><label>จำนวนผลงาน</label><input type="number" name="count" required><label>รูปภาพผลงาน</label><input type="file" name="image" accept="image/*"><button class="btn">ส่งผลงาน</button></form></div><div class="card"><h2>📚 สมัครนักธรรม/เปรียญ</h2><form method="post" action="/employee/study"><label>ประเภท</label><select name="kind"><option>นักธรรม</option><option>เปรียญธรรม</option></select><label>ชื่อ</label><input name="name" required><label>พรรษา</label><input name="vassa" required><label>ชั้น</label><input name="level" required><button class="btn">ส่งสมัคร</button></form></div><div class="card"><h2>🧘 สมัครอุปัชฌาย์</h2><form method="post" action="/employee/preq"><label>ชื่อ</label><input name="name" required><label>พรรษา</label><input name="vassa" required><label>สังกัดวัด</label><input name="temple" required><button class="btn">ส่งคำขอ</button></form></div><div class="card"><h2>💰 เบิกเงินเดือน</h2><p>สถานะ: {{'เปิดรับ' if op else 'ปิดรับ'}}</p>{%if op%}<form method="post" action="/employee/salary"><label>ชื่อ</label><input name="name" value="{{e.username}}" required><label>สังกัดวัด</label><input name="temple" required><label>ผลงานทั้งหมด</label><input name="works" value="{{total}}" required><label>ช่องทางรับเงิน</label><input name="channel" required><button class="btn">ส่งคำขอเงินเดือน</button></form>{%endif%}</div></div><div class="card" style="margin-top:15px"><h2>ผลงานของฉัน</h2>{%for x in w%}<div class="item">{{x.name}} — {{x.count}} — <span class="badge">{{x.status}}</span>{%if x.image%}<br><img src="/uploads/{{x.image}}" style="max-width:180px;margin-top:8px;border-radius:8px">{%endif%}</div>{%endfor%}</div>''','พนักงาน',e=e,w=w,total=total,op=op)
@app.post('/employee/work')
@req('employee')
def addwork():
 f=request.files.get('image');fn=''
 if f and f.filename:
  ext=f.filename.rsplit('.',1)[-1].lower()
  if ext in IMG:fn=f"{datetime.now().strftime('%Y%m%d%H%M%S%f')}_{secure_filename(f.filename)}";f.save(UP/fn)
 c=con();c.execute('insert into works(employee_id,name,count,image,status,created) values(?,?,?,?,?,?)',(session['eid'],request.form['name'],request.form['count'],fn,'รออนุมัติ',now()));c.commit();c.close();return redirect('/employee')
@app.post('/employee/study')
@req('employee')
def empstudy():
 c=con();c.execute('insert into study(employee_id,name,vassa,level,kind,status,created) values(?,?,?,?,?,?,?)',(session['eid'],request.form['name'],request.form['vassa'],request.form['level'],request.form['kind'],'รออนุมัติ',now()));c.commit();c.close();return redirect('/employee')
@app.post('/employee/preq')
@req('employee')
def emp_pre():
 c=con();c.execute('insert into preq(employee_id,name,vassa,temple,status,created) values(?,?,?,?,?,?)',(session['eid'],request.form['name'],request.form['vassa'],request.form['temple'],'รออนุมัติ',now()));c.commit();c.close();return redirect('/employee')
@app.post('/employee/salary')
@req('employee')
def emp_sal():
 c=con();op=c.execute('select open from salary_setting where id=1').fetchone()[0]
 if op:c.execute('insert into salary(employee_id,name,temple,works,channel,status,created) values(?,?,?,?,?,?,?)',(session['eid'],request.form['name'],request.form['temple'],request.form['works'],request.form['channel'],'รออนุมัติ',now()));c.commit()
 c.close();return redirect('/employee')
@app.route('/admin/works')
@req('admin')
def admin_works():
 c=con();r=c.execute('select works.*,employees.username from works left join employees on employees.id=works.employee_id order by works.id desc').fetchall();c.close();return page('''<div class="hero"><h1>🏆 อนุมัติผลงาน</h1></div>{%for x in r%}<div class="item"><h2>{{x.name}} <span class="badge">{{x.status}}</span></h2><p>พนักงาน {{x.username}} • {{x.count}} ผลงาน</p>{%if x.image%}<img src="/uploads/{{x.image}}" style="max-width:300px;border-radius:10px">{%endif%}{%if x.status=='รออนุมัติ'%}<div class="actions"><a class="btn green" href="/admin/work/{{x.id}}/อนุมัติ">อนุมัติ</a><a class="btn danger" href="/admin/work/{{x.id}}/ปฏิเสธ">ปฏิเสธ</a></div>{%endif%}</div>{%endfor%}''','ผลงาน',r=r)
@app.get('/admin/work/<int:id>/<decision>')
@req('admin')
def work_dec(id,decision):
 if decision in ['อนุมัติ','ปฏิเสธ']:
  c=con();c.execute('update works set status=? where id=?',(decision,id));c.commit();c.close()
 return redirect('/admin/works')
@app.route('/admin/study')
@req('admin')
def admin_study():
 c=con();r=c.execute('select * from study order by id desc').fetchall();c.close();return page('''<div class="hero"><h1>📚 อนุมัติการศึกษา</h1></div>{%for x in r%}<div class="item"><h3>{{x.name}} <span class="badge">{{x.kind}}</span></h3><p>พรรษา {{x.vassa}} • {{x.level}} • {{x.status}}</p>{%if x.status=='รออนุมัติ'%}<a class="btn green" href="/admin/study/{{x.id}}/อนุมัติ">อนุมัติ</a> <a class="btn danger" href="/admin/study/{{x.id}}/ปฏิเสธ">ปฏิเสธ</a>{%endif%}</div>{%endfor%}''','การศึกษา',r=r)
@app.get('/admin/study/<int:id>/<decision>')
@req('admin')
def study_dec(id,decision):
 if decision in ['อนุมัติ','ปฏิเสธ']:
  c=con();x=c.execute('select * from study where id=?',(id,)).fetchone();c.execute('update study set status=? where id=?',(decision,id));
  if decision=='อนุมัติ':c.execute('insert into temples(name,ordination_date,temple,status,created) values(?,?,?,?,?)',(x['name'],'','จากใบสมัคร',f"รอสอบ{x['kind']} {x['level']}",now()))
  c.commit();c.close()
 return redirect('/admin/study')
@app.route('/admin/preceptor',methods=['GET','POST'])
@req('admin')
def admin_pre():
 if request.method=='POST':
  try:c=con();c.execute('insert into preceptors(username,password,created) values(?,?,?)',(request.form['u'],request.form['p'],now()));c.commit();c.close()
  except sqlite3.IntegrityError:flash('ชื่อผู้ใช้ซ้ำ')
 c=con();r=c.execute('select * from preq order by id desc').fetchall();p=c.execute('select * from preceptors').fetchall();c.close();return page('''<div class="hero"><h1>🧘 พระอุปัชฌาย์</h1></div><div class="card"><form method="post"><label>ชื่อผู้ใช้</label><input name="u" required><label>รหัสผู้ใช้</label><input name="p" required><button class="btn">เพิ่มบัญชีอุปัชฌาย์</button></form></div><h2>คำขอสมัครอุปัชฌาย์</h2>{%for x in r%}<div class="item"><h3>{{x.name}}</h3><p>พรรษา {{x.vassa}} • {{x.temple}} • {{x.status}}</p>{%if x.status=='รออนุมัติ'%}<a class="btn green" href="/admin/preq/{{x.id}}/อนุมัติ">อนุมัติ</a> <a class="btn danger" href="/admin/preq/{{x.id}}/ปฏิเสธ">ปฏิเสธ</a>{%endif%}</div>{%endfor%}''','อุปัชฌาย์',r=r,p=p)
@app.get('/admin/preq/<int:id>/<decision>')
@req('admin')
def pre_dec(id,decision):
 if decision in ['อนุมัติ','ปฏิเสธ']:
  c=con();x=c.execute('select * from preq where id=?',(id,)).fetchone();c.execute('update preq set status=? where id=?',(decision,id));
  if decision=='อนุมัติ':c.execute('insert into temples(name,ordination_date,temple,status,created) values(?,?,?,?,?)',(x['name'],'',x['temple'],'รอสอบอุปัชฌาย์',now()))
  c.commit();c.close()
 return redirect('/admin/preceptor')
@app.route('/preceptor/login',methods=['GET','POST'])
def prelogin():
 if request.method=='POST':
  c=con();x=c.execute('select * from preceptors where username=? and password=?',(request.form['u'],request.form['p'])).fetchone();c.close()
  if x:session.clear();session.update(role='preceptor',pid=x.id);return redirect('/preceptor')
  flash('ข้อมูลไม่ถูกต้อง')
 return page('''<div class="card login"><h1>🧘 พระอุปัชฌาย์</h1><form method="post"><label>ชื่อผู้ใช้</label><input name="u"><label>รหัสผู้ใช้</label><input type="password" name="p"><button class="btn">เข้าสู่ระบบ</button></form></div>''','อุปัชฌาย์')
@app.route('/preceptor')
@req('preceptor')
def prehome():
 c=con();r=c.execute("select * from ordination where status='อนุมัติ' order by id desc").fetchall();q=c.execute("select * from preq where status='รออนุมัติ' order by id desc").fetchall();c.close();return page('''<div class="hero"><h1>🧘 ระบบพระอุปัชฌาย์</h1></div><h2>คำขอบวช</h2>{%for x in r%}<div class="item"><h3>{{x.name}}</h3><p>สังกัด {{x.temple}} • {{x.kind}}</p><form method="post" action="/preceptor/complete/{{x.id}}"><label>ชื่อฉายา</label><input name="monastic" required><label>วันที่บวช</label><input type="date" name="date" required><label>สังกัดวัด</label><input name="temple" value="{{x.temple}}" required><button class="btn green">บวชเสร็จ/เข้าทะเบียน</button></form></div>{%endfor%}<h2>คำขอสมัครอุปัชฌาย์</h2>{%for x in q%}<div class="item">{{x.name}} • {{x.vassa}} • {{x.temple}}</div>{%endfor%}''','อุปัชฌาย์',r=r,q=q)
@app.post('/preceptor/complete/<int:id>')
@req('preceptor')
def pre_complete(id):
 c=con();x=c.execute('select * from ordination where id=?',(id,)).fetchone();c.execute('insert into temples(name,ordination_date,temple,status,created) values(?,?,?,?,?)',(request.form['monastic'],request.form['date'],request.form['temple'],'บวชแล้ว',now()));c.execute("update ordination set status='บวชเสร็จ' where id=?",(id,));c.commit();c.close();return redirect('/preceptor')
@app.route('/admin/prayers',methods=['GET','POST'])
@req('admin')
def admin_prayers():
 if request.method=='POST':
  f=request.files.get('image');fn=''
  if f and f.filename and f.filename.rsplit('.',1)[-1].lower() in IMG:fn=f"pr_{datetime.now().strftime('%Y%m%d%H%M%S%f')}_{secure_filename(f.filename)}";f.save(UP/fn)
  c=con();c.execute('insert into prayers(title,link,content,image,created) values(?,?,?,?,?)',(request.form['title'],request.form.get('link',''),request.form.get('content',''),fn,now()));c.commit();c.close()
 c=con();r=c.execute('select * from prayers order by id desc').fetchall();c.close();return page('''<div class="hero"><h1>📖 บทสวดมนต์</h1></div><div class="card"><form method="post" enctype="multipart/form-data"><label>ชื่อบทสวด/หนังสือ</label><input name="title" required><label>ลิงก์</label><input name="link"><label>รูปภาพ</label><input type="file" name="image" accept="image/*"><label>ข้อความ</label><textarea name="content"></textarea><button class="btn">เพิ่ม</button></form></div>{%for x in r%}<div class="item"><h2>{{x.title}}</h2>{%if x.image%}<img src="/uploads/{{x.image}}" style="max-width:250px;border-radius:9px">{%endif%}<form method="post" action="/admin/prayer/del/{{x.id}}"><button class="btn danger">ลบ</button></form></div>{%endfor%}''','บทสวด',r=r)
@app.post('/admin/prayer/del/<int:id>')
@req('admin')
def delpr(id):
 c=con();c.execute('delete from prayers where id=?',(id,));c.commit();c.close();return redirect('/admin/prayers')
@app.route('/salary')
def salary():
 o=con().execute('select open from salary_setting where id=1').fetchone()[0];return page('''<div class="hero"><h1>💰 เงินเดือน</h1><p>{{'เปิดรับคำขอ' if o else 'ปิดรับคำขอ'}}</p></div><div class="card center"><a class="btn" href="/employee/login">เข้าสู่ระบบพนักงาน</a></div>''','เงินเดือน',o=o)
@app.route('/admin/salary',methods=['GET','POST'])
@req('admin')
def admin_salary():
 if request.method=='POST':
  c=con();c.execute('update salary_setting set open=? where id=1',(1 if request.form['x']=='open' else 0,));c.commit();c.close()
 c=con();o=c.execute('select open from salary_setting where id=1').fetchone()[0];r=c.execute('select salary.*,employees.username from salary left join employees on employees.id=salary.employee_id order by salary.id desc').fetchall();c.close();return page('''<div class="hero"><h1>💰 เงินเดือน</h1><p>{{'เปิดรับ' if o else 'ปิดรับ'}}</p></div><div class="card"><form method="post"><button class="btn green" name="x" value="open">เปิดรับเงินเดือน</button> <button class="btn danger" name="x" value="close">ปิดรับเงินเดือน</button></form></div>{%for x in r%}<div class="item"><h3>{{x.name}} <span class="badge">{{x.status}}</span></h3><p>วัด {{x.temple}} • ผลงาน {{x.works}}</p>{%if x.status=='รออนุมัติ'%}<a class="btn green" href="/admin/salary/{{x.id}}/อนุมัติ">อนุมัติ</a> <a class="btn danger" href="/admin/salary/{{x.id}}/ปฏิเสธ">ปฏิเสธ</a>{%elif x.status=='อนุมัติ'%}<p><b>ช่องทางรับเงิน:</b> {{x.channel}}</p><a class="btn danger" href="/admin/salary/del/{{x.id}}">ลบหลังจ่าย</a>{%endif%}</div>{%endfor%}''','เงินเดือน',o=o,r=r)
@app.get('/admin/salary/<int:id>/<decision>')
@req('admin')
def saldec(id,decision):
 if decision in ['อนุมัติ','ปฏิเสธ']:
  c=con();c.execute('update salary set status=? where id=?',(decision,id));c.commit();c.close()
 return redirect('/admin/salary')
@app.get('/admin/salary/del/<int:id>')
@req('admin')
def saldel(id):
 c=con();c.execute('delete from salary where id=?',(id,));c.commit();c.close();return redirect('/admin/salary')
if __name__=='__main__':
 init();print('พระสงฆ์สมไอซ์: http://127.0.0.1:5000');app.run(host='0.0.0.0',port=5000,debug=False)

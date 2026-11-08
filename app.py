from flask import Flask, render_template, request, redirect, url_for, flash, send_file
import sqlite3, csv, io, os
from datetime import datetime
from search_engine import discover

BASE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE, "leads.db")
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-this-secret-key")

def connect():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c

def init_db():
    with connect() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS leads (
            id INTEGER PRIMARY KEY AUTOINCREMENT, company TEXT NOT NULL,
            phone TEXT DEFAULT '', website TEXT DEFAULT '', country TEXT DEFAULT '',
            city TEXT DEFAULT '', category TEXT DEFAULT '', notes TEXT DEFAULT '',
            source TEXT DEFAULT 'manual', created_at TEXT NOT NULL)""")
        existing = {r[1] for r in c.execute("PRAGMA table_info(leads)")}
        for name, kind in [("email","TEXT DEFAULT ''"),("source_url","TEXT DEFAULT ''"),
                           ("search_query","TEXT DEFAULT ''"),("last_seen_at","TEXT DEFAULT ''")]:
            if name not in existing: c.execute(f"ALTER TABLE leads ADD COLUMN {name} {kind}")
        c.execute("""CREATE TABLE IF NOT EXISTS search_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT, query TEXT, country TEXT, city TEXT,
            found INTEGER DEFAULT 0, scanned INTEGER DEFAULT 0, status TEXT,
            details TEXT DEFAULT '', created_at TEXT NOT NULL)""")

@app.route("/")
def index():
    q=request.args.get("q","").strip(); country=request.args.get("country","").strip()
    category=request.args.get("category","").strip()
    sql="SELECT * FROM leads WHERE 1=1"; args=[]
    if q:
        sql += " AND (company LIKE ? OR phone LIKE ? OR email LIKE ? OR website LIKE ? OR city LIKE ?)"
        args += [f"%{q}%"]*5
    if country: sql += " AND country LIKE ?"; args.append(f"%{country}%")
    if category: sql += " AND category LIKE ?"; args.append(f"%{category}%")
    sql += " ORDER BY id DESC LIMIT 500"
    with connect() as c:
        leads=c.execute(sql,args).fetchall()
        total=c.execute("SELECT COUNT(*) FROM leads").fetchone()[0]
        countries=c.execute("SELECT COUNT(DISTINCT country) FROM leads WHERE country!=''").fetchone()[0]
        runs=c.execute("SELECT * FROM search_runs ORDER BY id DESC LIMIT 5").fetchall()
    return render_template("index.html",leads=leads,total=total,countries=countries,q=q,country=country,category=category,runs=runs)

@app.post("/search")
def search():
    keyword=request.form.get("keyword","").strip()
    country=request.form.get("country","السعودية").strip()
    city=request.form.get("city","").strip()
    try: limit=max(1,min(int(request.form.get("limit",10)),20))
    except ValueError: limit=10
    if not keyword:
        flash("اكتب نوع الشركات أو النشاط المطلوب البحث عنه.","error")
        return redirect(url_for("index"))
    if country not in ("السعودية","الإمارات"):
        flash("اختر السعودية أو الإمارات.","error"); return redirect(url_for("index"))
    query=" ".join(x for x in [keyword,city,country,"شركة OR مؤسسة OR خدمات"] if x)
    now=datetime.utcnow().isoformat(timespec="seconds")
    try:
        records, scanned=discover(query,country,limit)
        inserted=updated=0
        with connect() as c:
            for r in records:
                existing=c.execute("SELECT id FROM leads WHERE (phone!='' AND phone=?) OR (website!='' AND website=?) LIMIT 1",
                                   (r["phone"],r["website"])).fetchone()
                if existing:
                    c.execute("""UPDATE leads SET company=?,phone=?,email=?,website=?,country=?,source='web_search',
                        source_url=?,search_query=?,last_seen_at=? WHERE id=?""",
                        (r["company"],r["phone"],r["email"],r["website"],r["country"],r["source_url"],query,now,existing["id"]))
                    updated+=1
                else:
                    c.execute("""INSERT INTO leads(company,phone,email,website,country,city,category,notes,source,source_url,search_query,created_at,last_seen_at)
                        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (r["company"] or r["domain"],r["phone"],r["email"],r["website"],country,city,keyword,r["notes"],
                         "web_search",r["source_url"],query,now,now))
                    inserted+=1
            c.execute("INSERT INTO search_runs(query,country,city,found,scanned,status,details,created_at) VALUES(?,?,?,?,?,?,?,?)",
                      (query,country,city,inserted+updated,scanned,"success",f"جديد: {inserted}، محدث: {updated}",now))
        flash(f"انتهى البحث: {inserted} شركة جديدة و{updated} سجل محدث. تمت مراجعة {scanned} نتيجة بحث.", "success")
    except Exception as e:
        with connect() as c:
            c.execute("INSERT INTO search_runs(query,country,city,found,scanned,status,details,created_at) VALUES(?,?,?,?,?,?,?,?)",
                      (query,country,city,0,0,"error",str(e)[:500],now))
        flash(f"تعذر تنفيذ البحث: {e}", "error")
    return redirect(url_for("index"))

@app.post("/add")
def add():
    fields=["company","phone","email","website","country","city","category","notes"]
    data=[request.form.get(k,"").strip() for k in fields]
    if not data[0]:
        flash("اسم الشركة مطلوب","error"); return redirect(url_for("index"))
    with connect() as c:
        c.execute("""INSERT INTO leads(company,phone,email,website,country,city,category,notes,source,created_at)
        VALUES(?,?,?,?,?,?,?,?,'manual',?)""",(*data,datetime.utcnow().isoformat(timespec="seconds")))
    flash("تمت إضافة الشركة بنجاح","success"); return redirect(url_for("index"))

@app.post("/delete/<int:lead_id>")
def delete(lead_id):
    with connect() as c: c.execute("DELETE FROM leads WHERE id=?",(lead_id,))
    flash("تم حذف السجل","success"); return redirect(url_for("index"))

@app.post("/import")
def import_csv():
    f=request.files.get("file")
    if not f or not f.filename.lower().endswith(".csv"):
        flash("ارفع ملف CSV فقط","error"); return redirect(url_for("index"))
    try:
        rows=csv.DictReader(io.StringIO(f.stream.read().decode("utf-8-sig"))); count=0
        with connect() as c:
            for r in rows:
                company=(r.get("company") or r.get("الشركة") or r.get("name") or "").strip()
                if not company: continue
                c.execute("""INSERT INTO leads(company,phone,email,website,country,city,category,notes,source,created_at)
                VALUES(?,?,?,?,?,?,?,?,'csv',?)""",(company,r.get("phone",r.get("الهاتف","")),r.get("email",r.get("البريد","")),
                r.get("website",r.get("الموقع","")),r.get("country",r.get("الدولة","")),r.get("city",r.get("المدينة","")),
                r.get("category",r.get("النشاط","")),r.get("notes",r.get("ملاحظات","")),datetime.utcnow().isoformat(timespec="seconds")))
                count+=1
        flash(f"تم استيراد {count} سجل","success")
    except Exception as e: flash(f"تعذر قراءة الملف: {e}","error")
    return redirect(url_for("index"))

@app.get("/export")
def export():
    with connect() as c:
        rows=c.execute("SELECT company,phone,email,website,country,city,category,source,source_url,notes FROM leads ORDER BY id DESC").fetchall()
    out=io.StringIO(); w=csv.writer(out)
    w.writerow(["company","phone","email","website","country","city","category","source","source_url","notes"])
    w.writerows([tuple(r) for r in rows])
    data=io.BytesIO(("\ufeff"+out.getvalue()).encode("utf-8")); data.seek(0)
    return send_file(data,mimetype="text/csv",as_attachment=True,download_name="leads_generation.csv")

@app.get("/health")
def health(): return {"status":"ok","app":"leads_generation"}

init_db()
if __name__=="__main__":
    app.run(host="0.0.0.0",port=int(os.environ.get("PORT",5000)),debug=False)

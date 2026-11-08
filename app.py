from flask import Flask, render_template, request, redirect, url_for, flash, send_file
import sqlite3, csv, io, os
from datetime import datetime

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

@app.route("/")
def index():
    q = request.args.get("q", "").strip()
    country = request.args.get("country", "").strip()
    category = request.args.get("category", "").strip()
    sql, args = "SELECT * FROM leads WHERE 1=1", []
    for field, value in [("company", q), ("phone", q), ("website", q), ("city", q)]:
        if value:
            if field == "company":
                sql += " AND (" + " OR ".join(f"{f} LIKE ?" for f in ["company","phone","website","city"]) + ")"
                args.extend([f"%{q}%"]*4)
                break
    if country: sql += " AND country LIKE ?"; args.append(f"%{country}%")
    if category: sql += " AND category LIKE ?"; args.append(f"%{category}%")
    sql += " ORDER BY id DESC"
    with connect() as c:
        leads = c.execute(sql,args).fetchall()
        total = c.execute("SELECT COUNT(*) FROM leads").fetchone()[0]
        countries = c.execute("SELECT COUNT(DISTINCT country) FROM leads WHERE country!=''").fetchone()[0]
    return render_template("index.html", leads=leads,total=total,countries=countries,q=q,country=country,category=category)

@app.post("/add")
def add():
    fields = ["company","phone","website","country","city","category","notes"]
    data = [request.form.get(k,"").strip() for k in fields]
    if not data[0]:
        flash("اسم الشركة مطلوب","error"); return redirect(url_for("index"))
    with connect() as c:
        c.execute("""INSERT INTO leads(company,phone,website,country,city,category,notes,source,created_at)
        VALUES(?,?,?,?,?,?,?,'manual',?)""", (*data,datetime.utcnow().isoformat(timespec="seconds")))
    flash("تمت إضافة الشركة بنجاح","success")
    return redirect(url_for("index"))

@app.post("/delete/<int:lead_id>")
def delete(lead_id):
    with connect() as c: c.execute("DELETE FROM leads WHERE id=?",(lead_id,))
    flash("تم حذف السجل","success"); return redirect(url_for("index"))

@app.post("/import")
def import_csv():
    f = request.files.get("file")
    if not f or not f.filename.lower().endswith(".csv"):
        flash("ارفع ملف CSV فقط","error"); return redirect(url_for("index"))
    try:
        rows = csv.DictReader(io.StringIO(f.stream.read().decode("utf-8-sig")))
        count=0
        with connect() as c:
            for r in rows:
                company=(r.get("company") or r.get("الشركة") or r.get("name") or "").strip()
                if not company: continue
                c.execute("""INSERT INTO leads(company,phone,website,country,city,category,notes,source,created_at)
                VALUES(?,?,?,?,?,?,?,'csv',?)""",(company,r.get("phone",r.get("الهاتف","")),r.get("website",r.get("الموقع","")),r.get("country",r.get("الدولة","")),r.get("city",r.get("المدينة","")),r.get("category",r.get("النشاط","")),r.get("notes",r.get("ملاحظات","")),datetime.utcnow().isoformat(timespec="seconds")))
                count+=1
        flash(f"تم استيراد {count} سجل","success")
    except Exception as e: flash(f"تعذر قراءة الملف: {e}","error")
    return redirect(url_for("index"))

@app.get("/export")
def export():
    with connect() as c: rows=c.execute("SELECT company,phone,website,country,city,category,source,notes FROM leads ORDER BY id DESC").fetchall()
    out=io.StringIO(); w=csv.writer(out)
    w.writerow(["company","phone","website","country","city","category","source","notes"])
    w.writerows([tuple(r) for r in rows])
    data=io.BytesIO(("\ufeff"+out.getvalue()).encode("utf-8")); data.seek(0)
    return send_file(data,mimetype="text/csv",as_attachment=True,download_name="leads_generation.csv")

@app.get("/health")
def health(): return {"status":"ok","app":"leads_generation"}

init_db()
if __name__ == "__main__":
    app.run(host="0.0.0.0",port=int(os.environ.get("PORT",5000)),debug=False)

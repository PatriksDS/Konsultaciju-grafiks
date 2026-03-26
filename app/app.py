from flask import Flask, render_template, request, redirect, session, url_for, flash
import os
import json
import re
from datetime import datetime
from threading import Lock
from datetime import datetime, timedelta
app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET", "dev-only-change-me")

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
REG_PATH = os.path.join(DATA_DIR, "registracija.json")
PIET_PATH = os.path.join(DATA_DIR, "pieteikumi.json")

write_lock = Lock()

def ensure_files():
    os.makedirs(DATA_DIR, exist_ok=True)
    if not os.path.isfile(REG_PATH):
        with open(REG_PATH, "w", encoding="utf-8") as f:
            json.dump({"users": []}, f, ensure_ascii=False, indent=2)
    if not os.path.isfile(PIET_PATH):
        with open(PIET_PATH, "w", encoding="utf-8") as f:
            json.dump({"pieteikumi": []}, f, ensure_ascii=False, indent=2)

def read_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)

def write_json_atomic(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)

def weekday_lv(ddmmyyyy):
    m = re.match(r"^(\d{2})\.(\d{2})\.(\d{4})$", ddmmyyyy or "")
    if not m:
        return None
    d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
    try:
        dt = datetime(y, mo, d)
    except Exception:
        return None
    map_ = {
        0: "Pirmdiena",
        1: "Otrdiena",
        2: "Trešdiena",
        3: "Ceturtdiena",
        4: "Piektdiena",
        5: "Sestdiena",
        6: "Svētdiena"
    }
    return map_.get(dt.weekday())
def next_date_for_weekday_lv(lv_weekday):
    map_ = {
        "Pirmdiena": 0,
        "Otrdiena": 1,
        "Trešdiena": 2,
        "Ceturtdiena": 3,
        "Piektdiena": 4,
        "Sestdiena": 5,
        "Svētdiena": 6
    }
    target = map_.get(lv_weekday)
    if target is None:
        return None
    today = datetime.now()
    delta = (target - today.weekday()) % 7
    if delta == 0:
        delta = 7
    dt = today.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=delta)
    return dt.strftime("%d.%m.%Y")

def current_user():
    if "tips" not in session:
        return None
    return {
        "tips": session.get("tips"),
        "profils": session.get("profils"),
        "klase": session.get("klase")
    }

@app.before_request
def _init():
    ensure_files()

@app.get("/")
def index():
    if current_user():
        if session["tips"] == "skolens":
            return redirect(url_for("student"))
        return redirect(url_for("teacher"))
    return redirect(url_for("login"))

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return render_template("login.html")

    tips = (request.form.get("tips") or "").strip()
    lietotajvards = (request.form.get("lietotajvards") or "").strip()
    parole = (request.form.get("parole") or "").strip()

    if tips not in ("skolens", "skolotajs") or not lietotajvards or not parole:
        flash("Aizpildi visus laukus.")
        return redirect(url_for("login"))

    reg = read_json(REG_PATH)
    user = None
    for u in reg.get("users", []):
        if u.get("tips") == tips and u.get("lietotajvards") == lietotajvards and u.get("parole") == parole:
            user = u
            break

    if not user:
        flash("Nepareizs lietotājvārds vai parole.")
        return redirect(url_for("login"))

    session["tips"] = tips
    session["profils"] = user.get("profils", "")
    session["klase"] = user.get("klase", "")
    return redirect(url_for("student" if tips == "skolens" else "teacher"))

@app.post("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.get("/student")
def student():
    u = current_user()
    if not u or u["tips"] != "skolens":
        return redirect(url_for("login"))

    reg = read_json(REG_PATH)
    teachers = [x for x in reg.get("users", []) if x.get("tips") == "skolotajs"]

    teacher_filter = request.args.get("teacher", "Skolotājs")
    subject_filter = request.args.get("subject", "Priekšmets")
    date_filter = request.args.get("date", "Datums")

    if date_filter != "Datums":
        wd = weekday_lv(date_filter)
        if wd:
            teachers = [t for t in teachers if (t.get("nedelas_diena") or "") == wd]

    if teacher_filter != "Skolotājs":
        teachers = [t for t in teachers if t.get("profils") == teacher_filter]
    if subject_filter != "Priekšmets":
        teachers = [t for t in teachers if t.get("prieksmets") == subject_filter]

    teachers_sorted = sorted(teachers, key=lambda x: (x.get("profils") or ""))

    piet = read_json(PIET_PATH).get("pieteikumi", [])
    def count_for(t):
        return sum(1 for p in piet if p.get("skolotajs") == t.get("profils") and p.get("prieksmets") == t.get("prieksmets"))
    def exists_for(t):
        return any(p.get("skolotajs") == t.get("profils") and p.get("skolens") == u["profils"] for p in piet)

    teacher_names = sorted({t.get("profils","") for t in reg.get("users", []) if t.get("tips") == "skolotajs" and t.get("profils")})
    subjects = sorted({t.get("prieksmets","") for t in reg.get("users", []) if t.get("tips") == "skolotajs" and t.get("prieksmets")})

    return render_template(
        "student.html",
        user=u,
        rows=teachers_sorted,
        teacher_names=teacher_names,
        subjects=subjects,
        teacher_filter=teacher_filter,
        subject_filter=subject_filter,
        date_filter=date_filter,
        count_for=count_for,
        exists_for=exists_for
    )

@app.post("/student/apply")
def student_apply():
    u = current_user()
    if not u or u["tips"] != "skolens":
        return redirect(url_for("login"))

    skolotajs = (request.form.get("skolotajs") or "").strip()
    prieksmets = (request.form.get("prieksmets") or "").strip()
    kabinets = (request.form.get("kabinets") or "").strip()
    laiks = (request.form.get("laiks") or "").strip()
    datums = (request.form.get("datums") or "").strip()
    iemesls = (request.form.get("iemesls") or "").strip()

    if not skolotajs or not prieksmets or not kabinets or not laiks or not iemesls:
        flash("Trūkst datu.")
        return redirect(url_for("student"))

    if not datums or datums == "Datums":
        nedelas_diena = (request.form.get("nedelas_diena") or "").strip()
        auto_datums = next_date_for_weekday_lv(nedelas_diena)
        if auto_datums:
            datums = auto_datums
        else:
            datums = datetime.now().strftime("%d.%m.%Y")


    with write_lock:
        db = read_json(PIET_PATH)
        arr = db.get("pieteikumi", [])
        if any(p.get("skolotajs") == skolotajs and p.get("skolens") == u["profils"] for p in arr):
            flash("Tu jau esi pieteicies pie šī skolotāja.")
            return redirect(url_for("student"))

        arr.append({
            "skolotajs": skolotajs,
            "prieksmets": prieksmets,
            "kabinets": kabinets,
            "laiks": laiks,
            "skolens": u["profils"],
            "klase": u["klase"],
            "datums": datums,
            "iemesls": iemesls,
            "created_at": datetime.utcnow().isoformat() + "Z"
        })
        db["pieteikumi"] = arr
        write_json_atomic(PIET_PATH, db)

    return redirect(url_for("student"))

@app.post("/student/cancel")
def student_cancel():
    u = current_user()
    if not u or u["tips"] != "skolens":
        return redirect(url_for("login"))

    skolotajs = (request.form.get("skolotajs") or "").strip()
    if not skolotajs:
        return redirect(url_for("student"))

    with write_lock:
        db = read_json(PIET_PATH)
        arr = db.get("pieteikumi", [])
        db["pieteikumi"] = [p for p in arr if not (p.get("skolotajs") == skolotajs and p.get("skolens") == u["profils"])]
        write_json_atomic(PIET_PATH, db)

    return redirect(url_for("student"))

@app.get("/teacher")
def teacher():
    u = current_user()
    if not u or u["tips"] != "skolotajs":
        return redirect(url_for("login"))

    reg = read_json(REG_PATH)
    students = [x for x in reg.get("users", []) if x.get("tips") == "skolens"]

    student_filter = request.args.get("student", "Skolēns")
    class_filter = request.args.get("class", "Klase")
    date_filter = request.args.get("date", "Datums")

    piet = read_json(PIET_PATH).get("pieteikumi", [])
    p = [x for x in piet if x.get("skolotajs") == u["profils"]]

    if student_filter != "Skolēns":
        p = [x for x in p if x.get("skolens") == student_filter]
    if class_filter != "Klase":
        p = [x for x in p if x.get("klase") == class_filter]
    if date_filter != "Datums":
        p = [x for x in p if x.get("datums") == date_filter]

    p.sort(key=lambda x: (x.get("created_at") or ""), reverse=True)

    student_names = sorted({s.get("profils","") for s in students if s.get("profils")})
    classes = sorted({s.get("klase","") for s in students if s.get("klase")})

    return render_template(
        "teacher.html",
        user=u,
        rows=p,
        student_names=student_names,
        classes=classes,
        student_filter=student_filter,
        class_filter=class_filter,
        date_filter=date_filter
    )

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)

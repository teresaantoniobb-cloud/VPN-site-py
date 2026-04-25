import os, json, time, random, shutil
from pathlib import Path
from datetime import datetime
from flask import (Flask, render_template, redirect, url_for,
                   request, session, send_from_directory, abort, flash)
from werkzeug.utils import secure_filename

app = Flask(__name__)

# ── CONFIGURAÇÃO ──────────────────────────────────────────────
app.secret_key   = os.environ.get("SESSION_SECRET", "vpnfree_angola_2024_secret")
SITE_NAME        = "VPN Free AO"
ADMIN_USER       = os.environ.get("ADMIN_USER", "admin")
ADMIN_PASS       = os.environ.get("ADMIN_PASS", "admin123")
PORT             = int(os.environ.get("PORT", 3000))

BASE_DIR         = Path(__file__).parent
UPLOAD_DIR       = BASE_DIR / "static" / "uploads"
DATA_FILE        = BASE_DIR / "data" / "db.json"
ALLOWED_EXT      = {".ehi",".npv",".ovpn",".bdnet",".zip",".json",".txt",".apnalite",".bin",".maya"}
MAX_FILE_MB      = 50

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
(BASE_DIR / "data").mkdir(exist_ok=True)

# ── BASE DE DADOS JSON ────────────────────────────────────────
def read_db():
    if not DATA_FILE.exists():
        return init_db()
    try:
        return json.loads(DATA_FILE.read_text(encoding="utf-8"))
    except Exception:
        return init_db()

def write_db(data):
    DATA_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

def init_db():
    data = {
        "apps": [
            {"id":1,"slug":"http-injector","name":"HTTP Injector",  "icon":"💉","color":"#00e5ff","description":"Configurações para HTTP Injector. Importa o ficheiro .ehi directamente na app.","sort_order":1},
            {"id":2,"slug":"bd-net",       "name":"BD Net",          "icon":"🌐","color":"#00ff88","description":"Configurações para BD Net. Ficheiros prontos para importar na aplicação.","sort_order":2},
            {"id":3,"slug":"apna-tunnel",  "name":"APNA Tunnel Lite","icon":"⚡","color":"#ff6b35","description":"Configurações para APNA Tunnel Lite. Rápido e fácil de configurar.","sort_order":3},
            {"id":4,"slug":"maya-tun",     "name":"Maya Tun Pro",    "icon":"🌀","color":"#bd5fff","description":"Configurações para Maya Tun Pro. Alta velocidade e estabilidade.","sort_order":4},
        ],
        "files": [],
        "next_id": 1
    }
    write_db(data)
    return data

# Helpers
def get_apps():
    return sorted(read_db()["apps"], key=lambda a: a["sort_order"])

def get_app_by_slug(slug):
    return next((a for a in read_db()["apps"] if a["slug"] == slug), None)

def count_files(app_id):
    return sum(1 for f in read_db()["files"] if f["app_id"] == app_id)

def get_files_by_app(app_id):
    files = [f for f in read_db()["files"] if f["app_id"] == app_id]
    return sorted(files, key=lambda f: f["sort_order"])[:5]

def get_file_by_id(fid):
    db   = read_db()
    f    = next((f for f in db["files"] if f["id"] == fid), None)
    if not f: return None
    app  = next((a for a in db["apps"] if a["id"] == f["app_id"]), {})
    return {**f, "app_name": app.get("name",""), "app_icon": app.get("icon",""), "app_color": app.get("color","")}

def add_file(data):
    db = read_db()
    f  = {**data, "id": db["next_id"], "downloads": 0, "created_at": datetime.now().isoformat()}
    db["next_id"] += 1
    db["files"].append(f)
    write_db(db)

def update_file(fid, data):
    db = read_db()
    for i, f in enumerate(db["files"]):
        if f["id"] == fid:
            db["files"][i] = {**f, **data}
            break
    write_db(db)

def delete_file(fid):
    db = read_db()
    db["files"] = [f for f in db["files"] if f["id"] != fid]
    write_db(db)

def increment_download(fid):
    db = read_db()
    for f in db["files"]:
        if f["id"] == fid:
            f["downloads"] = f.get("downloads", 0) + 1
            break
    write_db(db)

def get_all_files(app_id=0):
    db   = read_db()
    apps = {a["id"]: a for a in db["apps"]}
    lst  = [f for f in db["files"] if not app_id or f["app_id"] == app_id]
    lst  = sorted(lst, key=lambda f: (f["app_id"], f["sort_order"]))
    return [{**f,
             "app_name":  apps.get(f["app_id"],{}).get("name",""),
             "app_icon":  apps.get(f["app_id"],{}).get("icon",""),
             "app_color": apps.get(f["app_id"],{}).get("color","")}
            for f in lst]

def total_downloads():
    return sum(f.get("downloads",0) for f in read_db()["files"])

def format_bytes(n):
    n = int(n or 0)
    if n >= 1_048_576: return f"{n/1_048_576:.1f} MB"
    if n >= 1_024:     return f"{n//1_024} KB"
    return f"{n} B"

def allowed_file(filename):
    return Path(filename).suffix.lower() in ALLOWED_EXT

def save_upload(file):
    ext      = Path(file.filename).suffix.lower()
    new_name = f"vpn_{int(time.time())}_{random.randint(1000,9999)}{ext}"
    file.save(UPLOAD_DIR / new_name)
    return new_name

# Injeta variáveis em todas as templates
@app.context_processor
def inject_globals():
    return {"site_name": SITE_NAME, "now": datetime.now(), "format_bytes": format_bytes}

# Auth guard
def require_admin():
    if not session.get("admin"):
        return redirect(url_for("admin_login"))

# ── ROTAS PÚBLICAS ────────────────────────────────────────────
@app.route("/")
def index():
    apps   = get_apps()
    counts = {a["id"]: count_files(a["id"]) for a in apps}
    return render_template("index.html", apps=apps, counts=counts)

@app.route("/app/<slug>")
def app_page(slug):
    vpn_app = get_app_by_slug(slug)
    if not vpn_app:
        return redirect(url_for("index"))
    files = get_files_by_app(vpn_app["id"])
    return render_template("app.html", vpn_app=vpn_app, files=files)

@app.route("/download/<int:fid>")
def download(fid):
    f = get_file_by_id(fid)
    if not f:
        abort(404)
    fp = UPLOAD_DIR / f["filename"]
    if not fp.exists():
        abort(404)
    increment_download(fid)
    return send_from_directory(UPLOAD_DIR, f["filename"],
                               as_attachment=True,
                               download_name=f["original_name"])

# ── ADMIN ─────────────────────────────────────────────────────
@app.route("/admin/login", methods=["GET","POST"])
def admin_login():
    if session.get("admin"):
        return redirect(url_for("admin_dashboard"))
    error = None
    if request.method == "POST":
        if request.form["username"] == ADMIN_USER and request.form["password"] == ADMIN_PASS:
            session["admin"] = True
            return redirect(url_for("admin_dashboard"))
        error = "Credenciais inválidas."
    return render_template("admin/login.html", error=error)

@app.route("/admin/logout")
def admin_logout():
    session.clear()
    return redirect(url_for("admin_login"))

@app.route("/admin")
def admin_dashboard():
    if not session.get("admin"): return redirect(url_for("admin_login"))
    apps   = get_apps()
    counts = {a["id"]: count_files(a["id"]) for a in apps}
    return render_template("admin/dashboard.html",
        apps=apps, counts=counts,
        total_files=len(read_db()["files"]),
        total_dl=total_downloads(), page="dash")

@app.route("/admin/upload", methods=["GET","POST"])
def admin_upload():
    if not session.get("admin"): return redirect(url_for("admin_login"))
    apps   = get_apps()
    counts = {a["id"]: count_files(a["id"]) for a in apps}
    msg = err = None

    if request.method == "POST":
        app_id = int(request.form.get("app_id", 0))
        title  = request.form.get("title", "").strip()
        f      = request.files.get("vpn_file")

        if not app_id or not title or not f or not f.filename:
            err = "Preenche todos os campos e selecciona um ficheiro."
        elif not allowed_file(f.filename):
            err = f"Extensão não permitida: {Path(f.filename).suffix}"
        elif count_files(app_id) >= 5:
            err = "Esta app já tem 5 ficheiros. Elimina um primeiro."
        else:
            f.seek(0, 2)
            size = f.tell(); f.seek(0)
            if size > MAX_FILE_MB * 1_048_576:
                err = f"Ficheiro demasiado grande (máx {MAX_FILE_MB}MB)."
            else:
                fname = save_upload(f)
                add_file({
                    "app_id":        app_id,
                    "title":         title,
                    "description":   request.form.get("description","").strip(),
                    "filename":      fname,
                    "original_name": f.filename,
                    "file_size":     size,
                    "password":      request.form.get("password","").strip(),
                    "server":        request.form.get("server","").strip(),
                    "sort_order":    int(request.form.get("sort_order",0)),
                })
                msg = "Ficheiro carregado com sucesso!"

    pre_app = int(request.args.get("app", 0))
    return render_template("admin/upload.html",
        apps=apps, counts=counts, pre_app=pre_app, msg=msg, err=err, page="upload")

@app.route("/admin/files")
def admin_files():
    if not session.get("admin"): return redirect(url_for("admin_login"))
    sel_app = int(request.args.get("app", 0))
    return render_template("admin/files.html",
        apps=get_apps(), files=get_all_files(sel_app), sel_app=sel_app, page="files")

@app.route("/admin/edit/<int:fid>", methods=["GET","POST"])
def admin_edit(fid):
    if not session.get("admin"): return redirect(url_for("admin_login"))
    f = get_file_by_id(fid)
    if not f: return redirect(url_for("admin_files"))
    msg = None

    if request.method == "POST":
        updates = {
            "title":       request.form.get("title","").strip(),
            "description": request.form.get("description","").strip(),
            "app_id":      int(request.form.get("app_id", f["app_id"])),
            "password":    request.form.get("password","").strip(),
            "server":      request.form.get("server","").strip(),
            "sort_order":  int(request.form.get("sort_order",0)),
        }
        new_file = request.files.get("vpn_file")
        if new_file and new_file.filename and allowed_file(new_file.filename):
            old = UPLOAD_DIR / f["filename"]
            if old.exists(): old.unlink()
            fname = save_upload(new_file)
            new_file.seek(0,2); size = new_file.tell()
            updates.update({"filename": fname, "original_name": new_file.filename, "file_size": size})
        update_file(fid, updates)
        msg = "Guardado com sucesso!"
        f   = get_file_by_id(fid)

    return render_template("admin/edit.html", f=f, apps=get_apps(), msg=msg, page="files")

@app.route("/admin/delete/<int:fid>")
def admin_delete(fid):
    if not session.get("admin"): return redirect(url_for("admin_login"))
    f = get_file_by_id(fid)
    if f:
        fp = UPLOAD_DIR / f["filename"]
        if fp.exists(): fp.unlink()
        delete_file(fid)
    return redirect(url_for("admin_files"))

# ── START ─────────────────────────────────────────────────────
if __name__ == "__main__":
    print(f"\n✅  VPN Free AO → http://localhost:{PORT}")
    print(f"⚙   Admin      → http://localhost:{PORT}/admin/login")
    print(f"👤  Login: {ADMIN_USER} / {ADMIN_PASS}\n")
    app.run(host="0.0.0.0", port=PORT, debug=False)

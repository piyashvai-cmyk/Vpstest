import os, json, subprocess, shutil, time, threading, zipfile, traceback
from datetime import datetime, timedelta
from pathlib import Path
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, send_from_directory
from werkzeug.utils import secure_filename
import psutil

# ---------- INIT ----------
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'ghost-secret-2024')
BASE_DIR = Path(__file__).parent
SERVERS_DIR = BASE_DIR / 'servers'
CONFIG_FILE = BASE_DIR / 'config.json'
SERVERS_FILE = BASE_DIR / 'servers.json'
LOGIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'admin')

# Create folders
SERVERS_DIR.mkdir(exist_ok=True)

# ---------- CONFIG ----------
DEFAULT_CONFIG = {
    "theme": "night",
    "font_family": "default",
    "site_title": "GHOST Panel",
    "site_header": "GHOST",
    "icon_url": "https://i.ibb.co/0jqYbKJ/ghost-icon.png",
    "password": LOGIN_PASSWORD,
    "colors": {
        "matrix": {"primary":"#00ff00","secondary":"#00cc00","accent":"#00ff80","background":"#000000","card_bg":"#0a0a0a","text":"#ffffff","danger":"#ff0000","header_text":"#ffffff","stats_text":"#ffffff"},
        "night": {"primary":"#4d88ff","secondary":"#3366cc","accent":"#aa88ff","background":"#000000","card_bg":"#0a0a0a","text":"#ffffff","danger":"#ff4d4d","header_text":"#ffffff","stats_text":"#ffffff"},
        "ocean": {"primary":"#3399ff","secondary":"#0066cc","accent":"#ff99cc","background":"#000000","card_bg":"#0a0a0a","text":"#ffffff","danger":"#ff4d4d","header_text":"#ffffff","stats_text":"#ffffff"},
        "sunset": {"primary":"#ff9933","secondary":"#cc6600","accent":"#ff66b3","background":"#000000","card_bg":"#0a0a0a","text":"#ffffff","danger":"#ff4d4d","header_text":"#ffffff","stats_text":"#ffffff"},
        "blood": {"primary":"#ff4d4d","secondary":"#cc0000","accent":"#ff80bf","background":"#000000","card_bg":"#0a0a0a","text":"#ffffff","danger":"#ff0000","header_text":"#ffffff","stats_text":"#ffffff"},
        "neon": {"primary":"#ff66ff","secondary":"#cc33cc","accent":"#ffff80","background":"#000000","card_bg":"#0a0a0a","text":"#ffffff","danger":"#ff4d4d","header_text":"#ffffff","stats_text":"#ffffff"},
        "cyber": {"primary":"#33ffff","secondary":"#00cccc","accent":"#ff80ff","background":"#000000","card_bg":"#0a0a0a","text":"#ffffff","danger":"#ff4d4d","header_text":"#ffffff","stats_text":"#ffffff"},
        "vapor": {"primary":"#ff99ff","secondary":"#cc66cc","accent":"#80ffff","background":"#000000","card_bg":"#0a0a0a","text":"#ffffff","danger":"#ff4d4d","header_text":"#ffffff","stats_text":"#ffffff"},
        "gold": {"primary":"#ffcc66","secondary":"#cc9933","accent":"#ffb380","background":"#000000","card_bg":"#0a0a0a","text":"#ffffff","danger":"#ff4d4d","header_text":"#ffffff","stats_text":"#ffffff"},
        "silver": {"primary":"#b3b3b3","secondary":"#808080","accent":"#cccccc","background":"#000000","card_bg":"#0a0a0a","text":"#ffffff","danger":"#ff4d4d","header_text":"#ffffff","stats_text":"#ffffff"}
    },
    "fonts": {
        "default": "'Courier New', monospace",
        "hacker": "'Fira Code', monospace",
        "terminal": "'Roboto Mono', monospace",
        "code": "'Source Code Pro', monospace",
        "retro": "'Press Start 2P', cursive"
    }
}

def load_config():
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE) as f:
            return json.load(f)
    return DEFAULT_CONFIG.copy()

def save_config(config):
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=2)

config = load_config()

# ---------- SERVER PROCESS MANAGEMENT ----------
# In-memory store: {server_id: {"process": Popen, "log": "", "status": "running"/"stopped", ...}}
server_processes = {}

def load_servers():
    if SERVERS_FILE.exists():
        with open(SERVERS_FILE) as f:
            return json.load(f)
    return {}

def save_servers(servers):
    with open(SERVERS_FILE, 'w') as f:
        json.dump(servers, f, indent=2, default=str)

servers = load_servers()

def get_server_dir(server_id):
    return SERVERS_DIR / server_id

def read_log(server_id):
    if server_id in server_processes:
        return server_processes[server_id].get("log", "")
    return ""

def update_process_status(server_id):
    if server_id not in servers:
        return
    info = servers[server_id]
    if server_id in server_processes and server_processes[server_id].get("process"):
        proc = server_processes[server_id]["process"]
        if proc.poll() is None:
            info["status"] = "running"
        else:
            info["status"] = "stopped"
    else:
        info["status"] = "stopped"
    save_servers(servers)

def start_server_process(server_id):
    if server_id not in servers:
        return
    info = servers[server_id]
    cmd = info["cmd"]
    cwd = str(get_server_dir(server_id) / info.get("cwd", ""))
    try:
        proc = subprocess.Popen(
            cmd, shell=True, cwd=cwd,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1, universal_newlines=True
        )
        server_processes[server_id] = {
            "process": proc,
            "log": "",
            "last_start": int(time.time())
        }
        # Start log reader thread
        def reader():
            while True:
                line = proc.stdout.readline()
                if not line and proc.poll() is not None:
                    break
                if line:
                    server_processes[server_id]["log"] += line
                    # Keep only last 5000 chars
                    if len(server_processes[server_id]["log"]) > 5000:
                        server_processes[server_id]["log"] = server_processes[server_id]["log"][-5000:]
        threading.Thread(target=reader, daemon=True).start()
        servers[server_id]["status"] = "running"
        servers[server_id]["last_start_time"] = int(time.time())
        save_servers(servers)
    except Exception as e:
        servers[server_id]["status"] = "stopped"
        save_servers(servers)

def stop_server_process(server_id):
    if server_id in server_processes:
        proc = server_processes[server_id].get("process")
        if proc and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
        del server_processes[server_id]
    servers[server_id]["status"] = "stopped"
    save_servers(servers)

# ---------- AUTO RESTART MONITOR ----------
def auto_restart_checker():
    while True:
        time.sleep(30)
        for sid, info in servers.items():
            if info.get("auto_restart") and info.get("status") == "running":
                interval_str = info.get("restart_interval", "1h")
                interval_map = {
                    '30s':30,'1m':60,'5m':300,'10m':600,'30m':1800,
                    '1h':3600,'2h':7200,'3h':10800,'6h':21600,
                    '12h':43200,'24h':86400
                }
                interval = interval_map.get(interval_str, 3600)
                last_start = info.get("last_start_time", 0)
                if time.time() - last_start >= interval:
                    stop_server_process(sid)
                    start_server_process(sid)
                    servers[sid]["last_start_time"] = int(time.time())
                    save_servers(servers)

threading.Thread(target=auto_restart_checker, daemon=True).start()

# ---------- AUTH ----------
@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        pwd = request.form.get('password')
        if pwd == config.get("password", LOGIN_PASSWORD):
            session['logged_in'] = True
            return redirect(url_for('index'))
        error = "Invalid credentials"
    return render_template('login.html', config=config, error=error)

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('login'))

def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

# ---------- ROUTES ----------
@app.route('/')
@login_required
def index():
    # Refresh statuses
    for sid in servers:
        update_process_status(sid)
    cpu = psutil.cpu_percent(interval=0.5)
    ram = psutil.virtual_memory().percent
    running_count = sum(1 for s in servers.values() if s.get("status") == "running")
    total_count = len(servers)
    return render_template('index.html',
                           config=config,
                           cpu=cpu,
                           ram=ram,
                           servers=servers,
                           running_count=running_count,
                           total_count=total_count,
                           colors=config["colors"][config["theme"]])

@app.route('/create_server', methods=['POST'])
@login_required
def create_server():
    name = request.form.get('server_name', '').strip()
    cmd = request.form.get('start_command', '').strip()
    file = request.files.get('file')
    if not name or not cmd:
        return "Name and command required", 400
    server_id = secure_filename(name.lower().replace(' ', '_'))
    if server_id in servers:
        return "Server ID already exists", 400

    # Create server dir
    server_dir = SERVERS_DIR / server_id
    server_dir.mkdir(parents=True, exist_ok=True)

    # Save uploaded file if present
    if file and file.filename:
        filename = secure_filename(file.filename)
        file.save(server_dir / filename)

    # Default cwd is server_dir relative to servers dir? Let's store as empty string = server root
    servers[server_id] = {
        "cmd": cmd,
        "cwd": "",
        "auto_restart": False,
        "restart_interval": "1h",
        "status": "stopped",
        "last_start_time": 0
    }
    save_servers(servers)
    # Start it
    start_server_process(server_id)
    return redirect(url_for('index'))

@app.route('/action/<server_id>/<action>')
@login_required
def server_action(server_id, action):
    if server_id not in servers:
        return "Server not found", 404
    if action == "start":
        start_server_process(server_id)
    elif action == "stop":
        stop_server_process(server_id)
    elif action == "restart":
        stop_server_process(server_id)
        start_server_process(server_id)
    elif action == "delete":
        stop_server_process(server_id)
        # Remove directory
        shutil.rmtree(get_server_dir(server_id), ignore_errors=True)
        del servers[server_id]
        save_servers(servers)
    else:
        return "Invalid action", 400
    return redirect(url_for('index'))

@app.route('/get_logs/<server_id>')
@login_required
def get_logs(server_id):
    if server_id not in servers:
        return jsonify({"logs": ""})
    # If process is running, return log from in-memory, else try reading from file?
    log = read_log(server_id)
    return jsonify({"logs": log})

@app.route('/system_stats')
@login_required
def system_stats():
    cpu = psutil.cpu_percent(interval=0.1)
    ram = psutil.virtual_memory().percent
    return jsonify({"cpu": cpu, "ram": ram})

# ---------- FILE MANAGEMENT ----------
@app.route('/files/<server_id>')
@login_required
def list_files(server_id):
    if server_id not in servers:
        return jsonify({"files": [], "cmd": "", "cwd": "", "auto_restart": False, "restart_interval": "1h"})
    path = request.args.get('path', '')
    server_dir = get_server_dir(server_id)
    target = (server_dir / path).resolve()
    # Security: ensure within server_dir
    if not str(target).startswith(str(server_dir.resolve())):
        return jsonify({"files": [], "error": "Access denied"}), 403
    files = []
    if target.exists() and target.is_dir():
        for f in target.iterdir():
            stat = f.stat()
            size = stat.st_size
            if f.is_dir():
                size_str = "DIR"
            else:
                if size < 1024:
                    size_str = f"{size} B"
                elif size < 1024*1024:
                    size_str = f"{size/1024:.1f} KB"
                else:
                    size_str = f"{size/(1024*1024):.1f} MB"
            files.append({
                "name": f.name,
                "type": "dir" if f.is_dir() else "file",
                "size": size_str,
                "raw_size": size
            })
    return jsonify({
        "files": files,
        "cmd": servers[server_id].get("cmd", ""),
        "cwd": servers[server_id].get("cwd", ""),
        "auto_restart": servers[server_id].get("auto_restart", False),
        "restart_interval": servers[server_id].get("restart_interval", "1h")
    })

@app.route('/create_file/<server_id>', methods=['POST'])
@login_required
def create_file(server_id):
    data = request.form
    filename = data.get('filename')
    content = data.get('content', '')
    path = data.get('path', '')
    server_dir = get_server_dir(server_id)
    target_dir = (server_dir / path).resolve()
    if not str(target_dir).startswith(str(server_dir.resolve())):
        return jsonify({"status": "error", "error": "Access denied"}), 403
    target_dir.mkdir(parents=True, exist_ok=True)
    (target_dir / filename).write_text(content)
    return jsonify({"status": "ok"})

@app.route('/create_folder/<server_id>', methods=['POST'])
@login_required
def create_folder(server_id):
    name = request.form.get('name')
    path = request.form.get('path', '')
    server_dir = get_server_dir(server_id)
    target_dir = (server_dir / path).resolve()
    if not str(target_dir).startswith(str(server_dir.resolve())):
        return jsonify({"status": "error"}), 403
    (target_dir / name).mkdir(exist_ok=True)
    return jsonify({"status": "ok"})

@app.route('/upload/<server_id>', methods=['POST'])
@login_required
def upload_file(server_id):
    file = request.files.get('file')
    path = request.form.get('path', '')
    if not file:
        return jsonify({"status": "error"}), 400
    server_dir = get_server_dir(server_id)
    target_dir = (server_dir / path).resolve()
    if not str(target_dir).startswith(str(server_dir.resolve())):
        return jsonify({"status": "error"}), 403
    target_dir.mkdir(parents=True, exist_ok=True)
    filename = secure_filename(file.filename)
    file.save(target_dir / filename)
    return jsonify({"status": "ok"})

@app.route('/delete_file/<server_id>/<path:filename>')
@login_required
def delete_file(server_id, filename):
    path = request.args.get('path', '')
    server_dir = get_server_dir(server_id)
    target = (server_dir / path / filename).resolve()
    if not str(target).startswith(str(server_dir.resolve())):
        return "Access denied", 403
    if target.exists():
        if target.is_dir():
            shutil.rmtree(target)
        else:
            target.unlink()
    return redirect(url_for('list_files', server_id=server_id, path=path))

@app.route('/rename_file/<server_id>', methods=['POST'])
@login_required
def rename_file(server_id):
    old = request.form.get('old_name')
    new = request.form.get('new_name')
    path = request.form.get('path', '')
    server_dir = get_server_dir(server_id)
    target_dir = (server_dir / path).resolve()
    if not str(target_dir).startswith(str(server_dir.resolve())):
        return jsonify({"status": "error", "error": "Access denied"}), 403
    (target_dir / old).rename(target_dir / new)
    return jsonify({"status": "ok"})

@app.route('/file_content/<server_id>')
@login_required
def file_content(server_id):
    filename = request.args.get('filename')
    path = request.args.get('path', '')
    server_dir = get_server_dir(server_id)
    target = (server_dir / path / filename).resolve()
    if not str(target).startswith(str(server_dir.resolve())):
        return jsonify({"content": ""}), 403
    try:
        content = target.read_text()
        return jsonify({"content": content})
    except:
        return jsonify({"content": ""})

@app.route('/save_file/<server_id>', methods=['POST'])
@login_required
def save_file(server_id):
    filename = request.form.get('filename')
    content = request.form.get('content')
    path = request.form.get('path', '')
    server_dir = get_server_dir(server_id)
    target = (server_dir / path / filename).resolve()
    if not str(target).startswith(str(server_dir.resolve())):
        return jsonify({"status": "error"}), 403
    target.write_text(content)
    return jsonify({"status": "ok"})

@app.route('/extract_archive/<server_id>/<path:filename>', methods=['POST'])
@login_required
def extract_archive(server_id, filename):
    path = request.form.get('path', '')
    server_dir = get_server_dir(server_id)
    archive_path = (server_dir / path / filename).resolve()
    if not str(archive_path).startswith(str(server_dir.resolve())):
        return jsonify({"status": "error"}), 403
    extract_to = archive_path.parent / archive_path.stem
    try:
        if filename.endswith('.zip'):
            with zipfile.ZipFile(archive_path, 'r') as zf:
                zf.extractall(extract_to)
        elif filename.endswith('.7z'):
            import py7zr
            with py7zr.SevenZipFile(archive_path, mode='r') as z:
                z.extractall(path=extract_to)
        else:
            return jsonify({"status": "error", "error": "Unsupported format"}), 400
        return jsonify({"status": "ok"})
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500

@app.route('/download/<server_id>/<path:filename>')
@login_required
def download_file(server_id, filename):
    path = request.args.get('path', '')
    server_dir = get_server_dir(server_id)
    target_dir = (server_dir / path).resolve()
    if not str(target_dir).startswith(str(server_dir.resolve())):
        return "Access denied", 403
    return send_from_directory(target_dir, filename, as_attachment=True)

# ---------- PACKAGE MANAGEMENT ----------
@app.route('/install_pkg/<server_id>', methods=['POST'])
@login_required
def install_pkg(server_id):
    if server_id not in servers:
        return jsonify({"status": "error"}), 404
    ptype = request.form.get('type')
    pname = request.form.get('name')
    cwd = str(get_server_dir(server_id) / servers[server_id].get("cwd", ""))
    try:
        if ptype == 'pip':
            subprocess.run(['pip', 'install', pname], cwd=cwd, check=True)
        elif ptype == 'npm':
            subprocess.run(['npm', 'install', pname], cwd=cwd, check=True)
        elif ptype == 'apt':
            subprocess.run(['apt-get', 'install', '-y', pname], cwd=cwd, check=True)
        elif ptype == 'pkg':
            subprocess.run(['pkg', 'install', '-y', pname], cwd=cwd, check=True)
        else:
            return jsonify({"status": "error", "error": "Unknown package type"}), 400
        return jsonify({"status": "ok"})
    except subprocess.CalledProcessError as e:
        return jsonify({"status": "error", "error": str(e)}), 500

@app.route('/uninstall_pkg/<server_id>', methods=['POST'])
@login_required
def uninstall_pkg(server_id):
    if server_id not in servers:
        return jsonify({"status": "error"}), 404
    ptype = request.form.get('type')
    pname = request.form.get('name')
    cwd = str(get_server_dir(server_id) / servers[server_id].get("cwd", ""))
    try:
        if ptype == 'pip':
            subprocess.run(['pip', 'uninstall', '-y', pname], cwd=cwd, check=True)
        elif ptype == 'npm':
            subprocess.run(['npm', 'uninstall', pname], cwd=cwd, check=True)
        elif ptype == 'apt':
            subprocess.run(['apt-get', 'remove', '-y', pname], cwd=cwd, check=True)
        elif ptype == 'pkg':
            subprocess.run(['pkg', 'uninstall', '-y', pname], cwd=cwd, check=True)
        else:
            return jsonify({"status": "error", "error": "Unknown package type"}), 400
        return jsonify({"status": "ok"})
    except subprocess.CalledProcessError as e:
        return jsonify({"status": "error", "error": str(e)}), 500

# ---------- CONSOLE INPUT ----------
@app.route('/send_input/<server_id>', methods=['POST'])
@login_required
def send_input(server_id):
    if server_id not in server_processes or not server_processes[server_id].get("process"):
        return jsonify({"status": "error", "message": "Server not running"}), 400
    cmd = request.form.get('command')
    proc = server_processes[server_id]["process"]
    if proc.poll() is None:
        proc.stdin.write(cmd + "\n")
        proc.stdin.flush()
        # Also log the command
        server_processes[server_id]["log"] += f"> {cmd}\n"
        return jsonify({"status": "ok"})
    return jsonify({"status": "error", "message": "Process finished"}), 400

# ---------- TELEGRAM BOT DEPLOY ----------
@app.route('/telegram_bot', methods=['POST'])
@login_required
def telegram_bot():
    token = request.form.get('token')
    if not token or ':' not in token:
        return jsonify({"status": "error", "error": "Invalid token"}), 400
    # Create a simple aiogram bot script and deploy as a server
    bot_id = "telegram_bot_" + token.split(":")[0]
    server_dir = SERVERS_DIR / bot_id
    server_dir.mkdir(exist_ok=True)
    bot_script = f'''
import asyncio, time, os, json, requests
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command

TOKEN = "{token}"
bot = Bot(token=TOKEN)
dp = Dispatcher()

@dp.message(Command("start"))
async def start(msg: types.Message):
    await msg.answer("GHOST Bot is online! Use /help for commands.")

@dp.message(Command("help"))
async def help_cmd(msg: types.Message):
    await msg.answer("/start /help /api /ping /uptime /info")

@dp.message(Command("ping"))
async def ping(msg: types.Message):
    await msg.answer("Pong!")

@dp.message(Command("uptime"))
async def uptime(msg: types.Message):
    await msg.answer(f"Uptime: {{time.time() - ps}}s")

@dp.message(Command("info"))
async def info(msg: types.Message):
    await msg.answer("GHOST Bot v1.0")

@dp.message(Command("api"))
async def api(msg: types.Message):
    # Simple api checker example
    await msg.answer("API endpoint: /api/check")

async def main():
    global ps
    ps = time.time()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
'''
    (server_dir / "bot.py").write_text(bot_script)
    # Server config
    servers[bot_id] = {
        "cmd": "python bot.py",
        "cwd": "",
        "auto_restart": True,
        "restart_interval": "24h",
        "status": "stopped",
        "last_start_time": 0
    }
    save_servers(servers)
    start_server_process(bot_id)
    return jsonify({"status": "ok", "server_name": bot_id})

# ---------- UPDATE SETTINGS ----------
@app.route('/update_settings/<server_id>', methods=['POST'])
@login_required
def update_settings(server_id):
    if server_id not in servers:
        return "Not found", 404
    cmd = request.form.get('cmd')
    cwd = request.form.get('cwd', '')
    auto_restart = request.form.get('auto_restart', 'false').lower() == 'true'
    restart_interval = request.form.get('restart_interval', '1h')
    servers[server_id].update({
        "cmd": cmd,
        "cwd": cwd,
        "auto_restart": auto_restart,
        "restart_interval": restart_interval
    })
    save_servers(servers)
    return jsonify({"status": "ok"})

@app.route('/server_info/<server_id>')
@login_required
def server_info(server_id):
    if server_id not in servers:
        return jsonify({}), 404
    info = servers[server_id]
    info['last_start_time'] = info.get('last_start_time', 0)
    return jsonify(info)

# ---------- CONFIG UPDATE ----------
@app.route('/update_config', methods=['POST'])
@login_required
def update_config():
    theme = request.form.get('theme')
    font_family = request.form.get('font_family')
    site_title = request.form.get('site_title')
    site_header = request.form.get('site_header')
    icon_url = request.form.get('icon_url')
    if theme:
        config['theme'] = theme
    if font_family:
        config['font_family'] = font_family
    if site_title:
        config['site_title'] = site_title
    if site_header:
        config['site_header'] = site_header
    if icon_url:
        config['icon_url'] = icon_url
    save_config(config)
    return jsonify({"status": "ok"})

@app.route('/change_password', methods=['POST'])
@login_required
def change_password():
    current = request.form.get('current_password')
    new = request.form.get('new_password')
    if current != config.get('password', LOGIN_PASSWORD):
        return jsonify({"status": "error", "error": "Current password incorrect"}), 403
    config['password'] = new
    save_config(config)
    return jsonify({"status": "ok"})

# ---------- MAIN ----------
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=False)
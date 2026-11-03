# ============================================================
# OpenCode Workstation on Kaggle — v11.1 (una sola celda)
# ============================================================
# v11: igual a v10 pero SIN los parches base64. La v10 escribia
# persistence.py / checkpoint.py / bootstrap.py desde blobs de
# 56ca89a porque el repo en main estaba roto (99ae57d los habia
# vaciado). Eso ya se arreglo EN EL REPO (commits 0793c6c y
# 784bd42): main trae los archivos restaurados, el fix del
# __init__ que sombreaba el modulo bootstrap y el nuevo
# RESTORED_WITH_WARNINGS. La celda ahora usa el repo tal cual.
# ============================================================

import builtins
if getattr(builtins, "_OPENCODE_WS_STARTED", False):
    raise RuntimeError("Esta celda ya corrió en este kernel. Reiniciá la sesión (Run > Restart session) y ejecutá de nuevo.")
builtins._OPENCODE_WS_STARTED = True


from pathlib import Path
import base64, os, sys, subprocess, json, time, socket, re, shutil, urllib.request, urllib.parse


try:
    sys.stdout.reconfigure(line_buffering=True)
except Exception:
    pass


def log(*a, **k):
    k.setdefault("flush", True)
    print(*a, **k)


def run(cmd, check=True, **kw):
    log(" $", " ".join(str(c) for c in cmd))
    return subprocess.run(cmd, check=check, **kw)


REPO = Path("/kaggle/working/opencode-workstation")
WORKSPACE = Path("/kaggle/working/opencode_cloud/workspace")
DATASET_ID = os.environ.get("OPENCODE_CLOUD_DATASET", "yourcompiler/opencode-workstation-persistence")
PORT = 4096


log("=" * 60)
log("OpenCode Workstation v11.1")
log("=" * 60)


# --- secrets ---
try:
    from kaggle_secrets import UserSecretsClient
    usc = UserSecretsClient()
    for key in ("NVIDIA_API_KEY", "OPENCODE_CLOUD_DATASET", "OPENCODE_SERVER_PASSWORD", "OPENCODE_SERVER_USERNAME"):
        try:
            val = usc.get_secret(key)
            if val:
                os.environ[key] = val
                if key == "OPENCODE_CLOUD_DATASET":
                    DATASET_ID = val
        except Exception:
            pass
except Exception as e:
    log("secrets:", type(e).__name__)


if not os.environ.get("NVIDIA_API_KEY"):
    # El bootstrap trata NVIDIA_API_KEY como OPCIONAL (arranca sin
    # modelos NVIDIA). La v10/v11 abortaba aca y dejaba la
    # workstation sin arrancar por un secret no adjuntado.
    log("AVISO: sin secret NVIDIA_API_KEY - arranco igual, sin modelos NVIDIA")
    log("       Adjuntarlo despues: Add-ons > Secrets, etiqueta exacta NVIDIA_API_KEY")
os.environ["OPENCODE_CLOUD_DATASET"] = DATASET_ID
log("Dataset:", DATASET_ID)


# --- deps ---
for mod, pkg in [("kagglehub", "kagglehub"), ("requests", "requests")]:
    try:
        __import__(mod)
    except ImportError:
        run([sys.executable, "-m", "pip", "install", "-q", pkg], timeout=300)


# --- repo (main ya trae los archivos corregidos; sin parches) ---
if not (REPO / "src/opencode_kaggle/bootstrap.py").exists():
    if REPO.exists():
        shutil.rmtree(REPO)
    run(["git", "clone", "--depth", "1", "https://github.com/enrrutador/opencode-workstation.git", str(REPO)], timeout=180)
else:
    log("repo presente")


for m in list(sys.modules):
    if m == "opencode_cloud" or m.startswith("opencode_cloud.") or m == "opencode_kaggle" or m.startswith("opencode_kaggle."):
        del sys.modules[m]
sys.path.insert(0, str(REPO / "src"))


WORKSPACE.mkdir(parents=True, exist_ok=True)
if not (WORKSPACE / ".git").exists():
    run(["git", "init"], cwd=str(WORKSPACE), check=False)
    run(["git", "-C", str(WORKSPACE), "config", "user.email", "opencode@kaggle.local"], check=False)
    run(["git", "-C", str(WORKSPACE), "config", "user.name", "OpenCode"], check=False)
    (WORKSPACE / "README.md").write_text("# OpenCode workspace\n", encoding="utf-8")
    run(["git", "-C", str(WORKSPACE), "add", "-A"], check=False)
    run(["git", "-C", str(WORKSPACE), "commit", "-m", "init"], check=False)


# --- bootstrap ---
log("\n[bootstrap]")
from opencode_cloud.checkpoint import CheckpointPolicy
from opencode_kaggle.bootstrap import bootstrap


policy = CheckpointPolicy(
    local_interval=120,
    min_publish_interval=900,  # 15 min
)
info = bootstrap(dataset_id=DATASET_ID, opencode_port=PORT, policy=policy, enable_access_layer=True)
log(json.dumps({k: v for k, v in info.items() if k != "shutdown"}, indent=2, default=str))
if not info.get("ok"):
    raise RuntimeError(f"Bootstrap falló: {info}")


recovery = info.get("recovery", "")
log("Recovery:", recovery)


# --- URL pública ---
wa = info.get("web_access") or {}
base_url = (wa.get("url") or "").rstrip("/")
if not base_url:
    lp = Path("/kaggle/working/opencode_cloud/logs/cloudflare-tunnel.log")
    if lp.exists():
        m = re.search(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com", lp.read_text())
        if m:
            base_url = m.group(0).rstrip("/")
if not base_url:
    raise RuntimeError("Sin URL de túnel")


# base64 estilo OpenCode (url-safe, sin =)
ws_b64 = base64.urlsafe_b64encode(str(WORKSPACE).encode()).decode().rstrip("=")
PROJECT_URL = f"{base_url}/{ws_b64}"
SESSION_URL = f"{base_url}/{ws_b64}/session"


# --- listar / crear sesión vía API ---
def api(method, path, data=None):
    url = f"http://127.0.0.1:{PORT}{path}"
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    pw = os.environ.get("OPENCODE_SERVER_PASSWORD", "")
    user = os.environ.get("OPENCODE_SERVER_USERNAME", "opencode")
    if pw:
        tok = base64.b64encode(f"{user}:{pw}".encode()).decode()
        req.add_header("Authorization", f"Basic {tok}")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode() or "null")


q = "?directory=" + urllib.parse.quote(str(WORKSPACE))
sessions = []
try:
    sessions = api("GET", "/session" + q) or []
    if not isinstance(sessions, list):
        sessions = []
except Exception as e:
    log("GET /session:", type(e).__name__, e)


if not sessions:
    try:
        s = api("POST", "/session" + q, b"{}")
        if s and s.get("id"):
            sessions = [s]
            log("Creada sesión seed:", s.get("id"), s.get("title"))
    except Exception as e:
        log("POST /session:", type(e).__name__, e)


# ordenar por updated
def _upd(s):
    return (s.get("time") or {}).get("updated") or 0
sessions = sorted(sessions, key=_upd, reverse=True)


links = []
for s in sessions[:8]:
    sid = s.get("id")
    if not sid:
        continue
    links.append({
        "id": sid,
        "title": s.get("title") or sid,
        "url": f"{base_url}/{ws_b64}/session/{sid}",
    })


# guardar links
out = Path("/kaggle/working/opencode_cloud/OPEN_THIS_URL.txt")
lines = [SESSION_URL, ""]
for L in links:
    lines.append(f"{L['title']}: {L['url']}")
out.write_text("\n".join(lines) + "\n", encoding="utf-8")


log("")
log("######## COPIÁ PEGÁ (una sola línea) ########")
print(SESSION_URL, flush=True)
log("#############################################")
if links:
    log("\nSesiones existentes (copiá el link completo):")
    for L in links:
        log(f"  - {L['title']}")
        print(L["url"], flush=True)
else:
    log("No hay sesiones aún. Abrí SESSION_URL, escribí un mensaje.")
log("")
log("NO uses /new-session ni la raíz del túnel.")
log("Workspace:", WORKSPACE)
log("Recovery:", recovery)
log("Links también en:", out)
log("Fin.")


OPEN_CODE_URL = SESSION_URL
OPEN_CODE_PROJECT_URL = PROJECT_URL
OPEN_CODE_SESSIONS = links
WORKSTATION_RESULT = info

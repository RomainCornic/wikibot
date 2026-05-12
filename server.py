# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "fastapi",
#   "uvicorn",
# ]
# ///

"""
server.py — Serveur FastAPI qui relie l'interface HTML aux bots Playwright

Lancement :
  uv run uvicorn server:app --reload
  ou
  python server.py

Puis ouvrir : http://localhost:8000
"""

import asyncio
import json
import os
import subprocess
from datetime import datetime
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# ─── Config ───────────────────────────────────────────────────────────────────

REPORTS_DIR = "reports"
BOTS_DB_PATH = os.path.join(REPORTS_DIR, "bots_db.json")
SCREENSHOTS_DIR = "screenshots"

# File des logs en mémoire (partagé entre tous les process)
log_queue: asyncio.Queue = asyncio.Queue()

# Suivi des process actifs { email: subprocess }
active_processes: dict[str, subprocess.Popen] = {}


# ─── App ──────────────────────────────────────────────────────────────────────

app = FastAPI(title="WikiMasters Bot Manager", version="1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Servir les screenshots statiquement
if os.path.exists(SCREENSHOTS_DIR):
    app.mount(
        "/screenshots", StaticFiles(directory=SCREENSHOTS_DIR), name="screenshots"
    )


# ─── DB helpers ───────────────────────────────────────────────────────────────


def load_db() -> dict:
    if os.path.exists(BOTS_DB_PATH):
        with open(BOTS_DB_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"bots": []}


def save_db(db: dict):
    os.makedirs(REPORTS_DIR, exist_ok=True)
    with open(BOTS_DB_PATH, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)


def push_log(msg: str, level: str = "info"):
    entry = {"time": datetime.now().strftime("%H:%M:%S"), "msg": msg, "level": level}
    try:
        log_queue.put_nowait(entry)
    except Exception:
        pass


# ─── Background runner ────────────────────────────────────────────────────────


def run_script(script: str, args: list[str], label: str, email: str = None):
    """Lance un script Python en subprocess et streame ses logs."""
    cmd = ["uv", "run", script] + args
    push_log(f"▶ Lancement : {label}", "info")

    if email:
        active_processes[email] = None

    try:
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1
        )
        if email:
            active_processes[email] = proc

        for line in proc.stdout:
            line = line.rstrip()
            if not line:
                continue
            level = (
                "success"
                if "✅" in line
                else "error"
                if "❌" in line
                else "warn"
                if "⚠️" in line
                else "info"
            )
            push_log(line, level)

        proc.wait()
        if proc.returncode == 0:
            push_log(f"✅ {label} terminé avec succès", "success")
        else:
            push_log(f"❌ {label} terminé avec code {proc.returncode}", "error")

    except Exception as e:
        push_log(f"❌ Erreur lancement {label} : {e}", "error")
    finally:
        if email and email in active_processes:
            del active_processes[email]


# ─── Routes API ───────────────────────────────────────────────────────────────

# -- Bots CRUD -----------------------------------------------------------------


@app.get("/api/bots")
def get_bots():
    """Retourne tous les bots avec stats calculées."""
    db = load_db()
    bots = db.get("bots", [])

    enriched = []
    for bot in bots:
        sessions = bot.get("sessions", [])
        total_paquets = sum(s.get("paquets_opened", 0) for s in sessions)
        last_session = sessions[-1] if sessions else None
        has_error = bool(last_session and last_session.get("errors"))
        status = (
            "running"
            if bot.get("email") in active_processes
            else "error"
            if has_error
            else "idle"
            if not sessions
            else "ok"
        )
        enriched.append(
            {
                **bot,
                "total_paquets": total_paquets,
                "total_sessions": len(sessions),
                "status": status,
                "last_run": last_session["date"] if last_session else None,
            }
        )

    return {"bots": enriched, "count": len(enriched)}


@app.delete("/api/bots/{email}")
def delete_bot(email: str):
    """Supprime un bot par email."""
    db = load_db()
    bots = db.get("bots", [])
    before = len(bots)
    db["bots"] = [b for b in bots if b.get("email") != email]

    if len(db["bots"]) == before:
        raise HTTPException(status_code=404, detail="Bot non trouvé")

    save_db(db)
    push_log(f"🗑 Bot supprimé : {email}", "warn")
    return {"ok": True}


@app.get("/api/bots/{email}/sessions")
def get_sessions(email: str):
    """Retourne les sessions d'un bot."""
    db = load_db()
    bot = next((b for b in db.get("bots", []) if b.get("email") == email), None)
    if not bot:
        raise HTTPException(status_code=404, detail="Bot non trouvé")
    return {"sessions": bot.get("sessions", []), "username": bot.get("username")}


class RunSessionRequest(BaseModel):
    email: str


class RunAllRequest(BaseModel):
    parallel: bool = False
    max_parallel: int = 3


@app.post("/api/bots/new")
def new_bot(background_tasks: BackgroundTasks):
    """Lance la création d'un nouveau bot (src/bot.py)."""
    background_tasks.add_task(run_script, "src/bot.py", [], "Nouveau bot")
    return {"ok": True, "msg": "Nouveau bot en cours de création…"}


@app.post("/api/bots/session")
def run_session(req: RunSessionRequest, background_tasks: BackgroundTasks):
    """Relance une session pour un bot existant."""
    if req.email in active_processes:
        raise HTTPException(
            status_code=409, detail="Ce bot est déjà en cours d'exécution"
        )

    db = load_db()
    bot = next((b for b in db.get("bots", []) if b.get("email") == req.email), None)
    if not bot:
        raise HTTPException(status_code=404, detail="Bot non trouvé")

    background_tasks.add_task(
        run_script,
        "src/bot_session.py",
        ["--email", req.email],
        f"Session {bot.get('username')}",
        email=req.email,
    )
    return {"ok": True, "msg": f"Session lancée pour {bot.get('username')}"}


@app.post("/api/bots/run-all")
def run_all(req: RunAllRequest, background_tasks: BackgroundTasks):
    """Relance tous les bots (séquentiellement ou en parallèle)."""
    db = load_db()
    bots = db.get("bots", [])

    if not bots:
        raise HTTPException(status_code=404, detail="Aucun bot disponible")

    if req.parallel:
        # Lance jusqu'à max_parallel bots en simultané
        launched = 0
        for bot in bots:
            email = bot.get("email")
            if email in active_processes:
                continue
            if launched >= req.max_parallel:
                break
            background_tasks.add_task(
                run_script,
                "src/bot_session.py",
                ["--email", email],
                f"Session {bot.get('username')}",
                email=email,
            )
            launched += 1
        return {"ok": True, "msg": f"{launched} bot(s) lancés en parallèle"}
    else:
        # Séquentiel via src/bot_session.py --all
        background_tasks.add_task(
            run_script, "src/bot_session.py", ["--all"], "Tous les bots (séquentiel)"
        )
        return {"ok": True, "msg": f"{len(bots)} bot(s) en file séquentielle"}


@app.get("/api/bots/active")
def get_active():
    """Retourne les emails des bots actuellement en cours."""
    return {"active": list(active_processes.keys())}


# -- Stats ---------------------------------------------------------------------


@app.get("/api/stats")
def get_stats():
    db = load_db()
    bots = db.get("bots", [])
    sessions, paquets, success = 0, 0, 0

    for bot in bots:
        for s in bot.get("sessions", []):
            sessions += 1
            paquets += s.get("paquets_opened", 0)
            if not s.get("errors"):
                success += 1

    rate = round((success / sessions) * 100) if sessions > 0 else 0
    return {
        "total_bots": len(bots),
        "total_sessions": sessions,
        "total_paquets": paquets,
        "success_rate": rate,
        "active_bots": len(active_processes),
    }


# -- Logs SSE ------------------------------------------------------------------


@app.get("/api/logs")
async def stream_logs():
    """Server-Sent Events : streame les logs en temps réel vers le navigateur."""

    async def event_generator():
        yield 'data: {"msg": "Connecté au log stream", "level": "info", "time": "--:--:--"}\n\n'
        while True:
            try:
                entry = await asyncio.wait_for(log_queue.get(), timeout=15.0)
                yield f"data: {json.dumps(entry)}\n\n"
            except asyncio.TimeoutError:
                yield ": keepalive\n\n"  # évite la déconnexion

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# -- Interface HTML ------------------------------------------------------------


@app.get("/", response_class=HTMLResponse)
def serve_dashboard():
    """Sert le dashboard HTML."""
    html_path = Path("bot_manager.html")
    if html_path.exists():
        return HTMLResponse(content=html_path.read_text(encoding="utf-8"))
    return HTMLResponse(
        "<h2>bot_manager.html introuvable — place-le dans le même dossier que server.py</h2>"
    )


# ─── Entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)

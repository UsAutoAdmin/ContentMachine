import json
from datetime import datetime
from pathlib import Path

from app.config import DATA_DIR

STATE_PATH = DATA_DIR / "command_state.json"
DEFAULT_STATE = {
    "messages": [],
    "tasks": [],
    "last_updated": None,
}


def _load_state() -> dict:
    if not STATE_PATH.exists():
        return DEFAULT_STATE.copy()
    try:
        return json.loads(STATE_PATH.read_text())
    except Exception:
        return DEFAULT_STATE.copy()


def _save_state(state: dict) -> dict:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    state["last_updated"] = datetime.utcnow().isoformat() + "Z"
    STATE_PATH.write_text(json.dumps(state, indent=2))
    return state


def get_state() -> dict:
    return _load_state()


def add_message(role: str, body: str) -> dict:
    state = _load_state()
    state.setdefault("messages", []).append({
        "role": role,
        "body": body,
        "created_at": datetime.utcnow().isoformat() + "Z",
    })
    return _save_state(state)


def add_task(title: str, status: str = "open") -> dict:
    state = _load_state()
    tasks = state.setdefault("tasks", [])
    next_id = max([t.get("id", 0) for t in tasks] + [0]) + 1
    tasks.append({
        "id": next_id,
        "title": title,
        "status": status,
        "created_at": datetime.utcnow().isoformat() + "Z",
    })
    return _save_state(state)


def update_task(task_id: int, status: str) -> dict:
    state = _load_state()
    for task in state.setdefault("tasks", []):
        if task.get("id") == task_id:
            task["status"] = status
            task["updated_at"] = datetime.utcnow().isoformat() + "Z"
            break
    return _save_state(state)

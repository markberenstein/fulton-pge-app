"""Simple JSON-file storage for reimbursement runs.

Runs are stored under DATA_DIR (mounted as a persistent Railway volume in
production, same pattern as the Buildium balances app) so history survives
redeploys.
"""
import json
import os
import uuid
from datetime import datetime, timezone

DATA_DIR = os.environ.get("DATA_DIR", os.path.join(os.path.dirname(__file__), "..", "data"))
RUNS_DIR = os.path.join(DATA_DIR, "runs")


def _ensure_dirs():
    os.makedirs(RUNS_DIR, exist_ok=True)


def new_run_id() -> str:
    return uuid.uuid4().hex[:12]


def save_run(run_id: str, data: dict):
    _ensure_dirs()
    data["run_id"] = run_id
    data.setdefault("created_at", datetime.now(timezone.utc).isoformat())
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    path = os.path.join(RUNS_DIR, f"{run_id}.json")
    with open(path, "w") as f:
        json.dump(data, f, indent=2, default=str)


def load_run(run_id: str) -> dict | None:
    path = os.path.join(RUNS_DIR, f"{run_id}.json")
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return json.load(f)


def list_runs() -> list[dict]:
    _ensure_dirs()
    runs = []
    for fname in os.listdir(RUNS_DIR):
        if fname.endswith(".json"):
            with open(os.path.join(RUNS_DIR, fname)) as f:
                runs.append(json.load(f))
    runs.sort(key=lambda r: r.get("created_at", ""), reverse=True)
    return runs


SETTINGS_PATH = None  # set lazily so DATA_DIR env override still applies


def _settings_path():
    return os.path.join(DATA_DIR, "settings.json")


DEFAULT_SETTINGS = {
    "billed_entity": "BA Partners LLC",
    "contact_name": "Mark",
    "contact_phone": "650-350-8212",
    "sender_name": "Adam",
    "subject_template": "",  # blank = use built-in default
    "body_template": "",     # blank = use built-in default
}


def get_settings() -> dict:
    _ensure_dirs()
    path = _settings_path()
    if not os.path.exists(path):
        return dict(DEFAULT_SETTINGS)
    with open(path) as f:
        saved = json.load(f)
    merged = dict(DEFAULT_SETTINGS)
    merged.update(saved)
    return merged


def save_settings(data: dict):
    _ensure_dirs()
    with open(_settings_path(), "w") as f:
        json.dump(data, f, indent=2)

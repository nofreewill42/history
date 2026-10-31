"""Model registry, download status, install/delete, and default-model settings."""

from __future__ import annotations

import importlib.util
import json
import shutil
import threading
from pathlib import Path

from .paths import LOCAL_JSON, MODELS_JSON, SETTINGS_JSON

ENGINE_MODULES = {
    "faster-whisper": ["faster_whisper"],
    "nemo": ["nemo", "torch"],
    "transformers": ["transformers", "torch", "torchaudio", "peft"],
}
ENGINE_EXTRA = {"faster-whisper": "whisper", "nemo": "nemo", "transformers": "transformers"}

_downloads: dict[str, dict] = {}  # model id -> {"state", "error", "total", "done"}
_lock = threading.Lock()


# --- registry ----------------------------------------------------------------

def registry() -> list[dict]:
    """models.json merged with studio/local.json (local entries win on id clash)."""
    entries = {m["id"]: dict(m, local=False) for m in json.loads(MODELS_JSON.read_text())}
    if LOCAL_JSON.exists():
        for m in json.loads(LOCAL_JSON.read_text()):
            entries[m["id"]] = dict(m, local=True)
    return list(entries.values())


def get(model_id: str) -> dict:
    for m in registry():
        if m["id"] == model_id:
            return m
    raise KeyError(f"unknown model: {model_id}")


# --- settings ----------------------------------------------------------------

def settings() -> dict:
    s = {"live_model": None, "final_model": None}
    if SETTINGS_JSON.exists():
        s.update(json.loads(SETTINGS_JSON.read_text()))
    return s


def save_settings(**changes) -> dict:
    s = settings()
    s.update({k: v for k, v in changes.items() if k in s})
    SETTINGS_JSON.write_text(json.dumps(s, indent=2) + "\n")
    return s


# --- status ------------------------------------------------------------------

def engine_missing(engine: str) -> list[str]:
    return [m for m in ENGINE_MODULES[engine] if importlib.util.find_spec(m) is None]


def local_path(entry: dict) -> Path | None:
    """Where the weights are on disk, or None if not downloaded."""
    repo = entry["hf_repo"]
    if entry.get("local") or Path(repo).expanduser().is_absolute():
        p = Path(repo).expanduser()
        return p if p.exists() else None
    from huggingface_hub import snapshot_download
    try:
        return Path(snapshot_download(repo, local_files_only=True))
    except Exception:
        return None


def revision(entry: dict) -> str | None:
    """Hugging Face commit of the downloaded snapshot (the folder name)."""
    p = local_path(entry)
    if p is None or entry.get("local") or p.parent.name != "snapshots":
        return None
    return p.name


def _cache_size(repo: str) -> int:
    from huggingface_hub.constants import HF_HUB_CACHE
    d = Path(HF_HUB_CACHE) / ("models--" + repo.replace("/", "--"))
    if not d.exists():
        return 0
    return sum(f.stat().st_size for f in d.rglob("*") if f.is_file() and not f.is_symlink())


def status(entry: dict) -> dict:
    dl = _downloads.get(entry["id"])
    if dl and dl["state"] == "downloading":
        dl = dict(dl, done=_cache_size(entry["hf_repo"]))
    return {
        "engine_missing": engine_missing(entry["engine"]),
        "engine_extra": ENGINE_EXTRA[entry["engine"]],
        "installed": local_path(entry) is not None,
        "download": dl,
    }


def all_status() -> list[dict]:
    return [dict(m, status=status(m)) for m in registry()]


# --- install / delete ----------------------------------------------------------

def install(model_id: str) -> None:
    """Download weights into the Hugging Face cache in a background thread."""
    entry = get(model_id)
    if entry.get("local"):
        raise ValueError("local checkpoints are not downloaded")
    with _lock:
        if _downloads.get(model_id, {}).get("state") == "downloading":
            return
        _downloads[model_id] = {"state": "downloading", "error": None, "total": None, "done": 0}

    def run():
        from huggingface_hub import HfApi, snapshot_download
        try:
            try:
                info = HfApi().model_info(entry["hf_repo"], files_metadata=True)
                _downloads[model_id]["total"] = sum((s.size or 0) for s in info.siblings)
            except Exception:
                pass  # progress is optional
            snapshot_download(entry["hf_repo"])
            _downloads[model_id].update(state="done")
        except Exception as e:  # shown in the Models panel
            _downloads[model_id].update(state="error", error=f"{type(e).__name__}: {e}")

    threading.Thread(target=run, daemon=True, name=f"download-{model_id}").start()


def delete(model_id: str) -> None:
    """Remove downloaded weights from the Hugging Face cache."""
    entry = get(model_id)
    if entry.get("local"):
        raise ValueError("local checkpoints are not deleted by the studio")
    from huggingface_hub import scan_cache_dir
    cache = scan_cache_dir()
    revs = [r.commit_hash for repo in cache.repos if repo.repo_id == entry["hf_repo"] for r in repo.revisions]
    if revs:
        cache.delete_revisions(*revs).execute()
    else:  # half-finished download with no complete revision
        from huggingface_hub.constants import HF_HUB_CACHE
        shutil.rmtree(Path(HF_HUB_CACHE) / ("models--" + entry["hf_repo"].replace("/", "--")), ignore_errors=True)
    _downloads.pop(model_id, None)

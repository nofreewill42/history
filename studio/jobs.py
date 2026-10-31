"""Background work: the final transcription pass (a queue) and the live preview."""

from __future__ import annotations

import itertools
import json
import queue
import threading
import time
import traceback
from datetime import datetime

from . import audio, engines, gitops, models, sessions

# --- final pass ---------------------------------------------------------------

_jobs: dict[int, dict] = {}
_queue: queue.Queue[int] = queue.Queue()
_ids = itertools.count(1)


def submit(sid: str, model_id: str) -> dict:
    models.get(model_id)  # unknown ids fail here, not in the worker
    sessions.session_dir(sid)
    job = {"id": next(_ids), "session": sid, "model": model_id, "state": "queued",
           "progress": 0.0, "error": None, "commit": None, "note": None}
    _jobs[job["id"]] = job
    _queue.put(job["id"])
    return job


def list_jobs() -> list[dict]:
    return sorted(_jobs.values(), key=lambda j: -j["id"])


def _audio_source(d):
    if (d / "original.wav").exists():
        return d / "original.wav"
    opus = d / "audio.opus"
    if opus.exists() and opus.read_bytes()[:40].startswith(b"version https://git-lfs"):
        raise RuntimeError("audio.opus is an LFS pointer; fetch the audio first: git lfs pull")
    if not opus.exists():
        raise RuntimeError("no audio in this session")
    return opus


def _has_checked(path) -> bool:
    if not path.exists():
        return False
    return any(json.loads(line).get("checked") for line in path.read_text(encoding="utf-8").splitlines() if line.strip())


def _run(job: dict) -> None:
    d = sessions.session_dir(job["session"])
    entry = models.get(job["model"])
    eng = engines.load(job["model"])
    src = _audio_source(d)
    x = audio.load_for_asr(src)

    def progress(f):
        job["progress"] = round(f, 3)

    segments = engines.run(eng, x, progress=progress)
    result = {
        "model": {"id": entry["id"], "name": entry["name"], "engine": entry["engine"],
                  "hf_repo": entry["hf_repo"], "revision": models.revision(entry)},
        "settings": eng.settings(),
        "created": datetime.now().astimezone().isoformat(timespec="seconds"),
        "audio": {"file": src.name, "duration_s": round(len(x) / audio.ASR_RATE, 1)},
        "segments": segments,
    }
    asr_dir = d / "asr"
    asr_dir.mkdir(exist_ok=True)
    asr_file = asr_dir / f"{entry['id']}.json"
    asr_file.write_text(json.dumps(result, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")

    paths = [asr_file]
    transcript = d / "transcript.jsonl"
    if _has_checked(transcript):
        job["note"] = "transcript.jsonl has checked segments, so it was kept; only asr/ was updated"
    else:
        lines = [json.dumps({"start": s["start"], "end": s["end"], "text": s["text"], "source": entry["id"],
                             "checked": False, "lang": "en", "kind": "comment", "ref": None}, ensure_ascii=False)
                 for s in segments if s["text"]]
        transcript.write_text("".join(line + "\n" for line in lines), encoding="utf-8")
        paths.append(transcript)
    try:
        job["commit"] = gitops.commit(paths, f"Transcribe session {job['session']} with {entry['id']}")
    except Exception as e:
        job["note"] = f"saved but not committed: {getattr(e, 'stderr', '') or e}"


def _worker() -> None:
    while True:
        job = _jobs[_queue.get()]
        job["state"] = "running"
        try:
            _run(job)
            job["state"], job["progress"] = "done", 1.0
        except Exception as e:
            job["state"], job["error"] = "error", f"{type(e).__name__}: {e}"
            traceback.print_exc()


# --- live preview ---------------------------------------------------------------

LIVE_WINDOW_S = 15.0
LIVE_EVERY_S = 3.0

_live = {"session": None, "text": "", "error": None, "model": None, "updated": 0.0}


def live_start(sid: str) -> None:
    _live.update(session=sid, text="", error=None, model=models.settings()["live_model"], updated=0.0)


def live_stop() -> None:
    _live.update(session=None)


def live_state() -> dict:
    return dict(_live)


def _live_worker() -> None:
    last_size = -1
    while True:
        time.sleep(LIVE_EVERY_S)
        sid, model_id = _live["session"], _live["model"]
        if not sid:
            last_size = -1
            continue
        if not model_id:
            _live["error"] = "no live model chosen in the Models panel"
            continue
        try:
            wav = sessions.session_dir(sid) / "original.wav"
            size = wav.stat().st_size
            if size == last_size:
                continue
            last_size = size
            x = audio.wav_tail(wav, LIVE_WINDOW_S)
            if len(x) < audio.ASR_RATE:
                continue
            eng = engines.load(model_id)
            segs = eng.transcribe(x)
            if _live["session"] == sid:
                _live.update(text=" ".join(s["text"] for s in segs).strip(), error=None, updated=time.time())
        except Exception as e:
            _live["error"] = f"{type(e).__name__}: {e}"


def start_workers() -> None:
    threading.Thread(target=_worker, daemon=True, name="final-pass").start()
    threading.Thread(target=_live_worker, daemon=True, name="live-pass").start()

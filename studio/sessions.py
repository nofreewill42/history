"""Recording sessions on disk, in the layout of sessions/README.md."""

from __future__ import annotations

import json
import socket
import threading
from datetime import datetime
from pathlib import Path

from . import audio, gitops
from .paths import SESSIONS

RECORDING_MARKER = ".recording.json"  # git-ignored; exists only while a session is unfinished

_locks: dict[str, threading.Lock] = {}
_next_seq: dict[str, int] = {}


def _lock(sid: str) -> threading.Lock:
    return _locks.setdefault(sid, threading.Lock())


def session_dir(sid: str) -> Path:
    if not sid[:4].isdigit() or "/" in sid or ".." in sid:
        raise ValueError(f"bad session id: {sid}")
    return SESSIONS / sid[:4] / sid


def _now() -> datetime:
    return datetime.now().astimezone()


# --- create / record ------------------------------------------------------------

def create(sample_rate: int, mic: str = "", device: str = "") -> dict:
    started = _now()
    base = started.strftime("%Y-%m-%dT%H%M")
    sid, n = base, 1
    while session_dir(sid).exists():
        n += 1
        sid = f"{base}-{n}"
    d = session_dir(sid)
    d.mkdir(parents=True)
    audio.wav_create(d / "original.wav", sample_rate)
    (d / "nav.jsonl").touch()
    meta = {"id": sid, "started": started.isoformat(timespec="seconds"),
            "device": device or socket.gethostname(), "mic": mic, "sample_rate": sample_rate}
    (d / RECORDING_MARKER).write_text(json.dumps(meta) + "\n")
    _next_seq[sid] = 0
    return meta


def append_audio(sid: str, seq: int, pcm16: bytes) -> float:
    """Append chunk number `seq`. Re-sent chunks are ignored, so the page can retry safely."""
    d = session_dir(sid)
    with _lock(sid):
        if not (d / RECORDING_MARKER).exists():
            raise ValueError("session is not recording")
        expected = _next_seq.get(sid, 0)
        if seq < expected:
            pass  # duplicate of a chunk already written
        elif seq > expected:
            raise ValueError(f"chunk {seq} arrived before chunk {expected}")
        else:
            audio.wav_append(d / "original.wav", pcm16)
            _next_seq[sid] = seq + 1
        rate, data = audio.wav_info(d / "original.wav")
        return data / 2 / rate


def append_nav(sid: str, events: list[dict]) -> None:
    d = session_dir(sid)
    lines = []
    for e in events:
        ev = {"t": round(float(e["t"]), 3), "text": e["text"], "ref": e.get("ref")}
        if e.get("heading"):
            ev["heading"] = e["heading"]
        lines.append(json.dumps(ev, ensure_ascii=False))
    with _lock(sid), open(d / "nav.jsonl", "a", encoding="utf-8") as f:
        f.write("".join(line + "\n" for line in lines))


# --- finish ------------------------------------------------------------------

def _texts_touched(d: Path) -> list[str]:
    seen = []
    for line in (d / "nav.jsonl").read_text(encoding="utf-8").splitlines():
        if line.strip():
            t = json.loads(line)["text"]
            if t not in seen:
                seen.append(t)
    return seen


def finish(sid: str, notes: str = "", recovered: bool = False) -> dict:
    """Close the WAV, encode audio.opus, write session.json, commit. Returns a report."""
    d = session_dir(sid)
    with _lock(sid):
        marker = d / RECORDING_MARKER
        meta = json.loads(marker.read_text())
        duration = audio.wav_repair(d / "original.wav")
        audio.encode_opus(d / "original.wav", d / "audio.opus")
        if recovered:
            notes = (notes + " " if notes else "") + "recovered after interruption"
        session = {
            "id": sid,
            "started": meta["started"],
            "duration_s": round(duration, 1),
            "device": meta["device"],
            "mic": meta["mic"],
            "audio": {"codec": "opus", "bitrate_kbps": 24, "channels": 1},
            "texts": _texts_touched(d),
            "notes": notes,
        }
        (d / "session.json").write_text(json.dumps(session, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        marker.unlink()
        _next_seq.pop(sid, None)
    report = {"session": session, "commit": None, "warning": None}
    problem = gitops.lfs_problem(d / "audio.opus")
    if problem:
        report["warning"] = f"Session saved but not committed: {problem}"
        return report
    try:
        report["commit"] = gitops.commit(
            [d / "session.json", d / "audio.opus", d / "nav.jsonl"],
            f"Add reading session {sid}\n\n{session['duration_s']} s; texts: {', '.join(session['texts']) or 'none'}.",
        )
    except Exception as e:
        report["warning"] = f"Session saved but the commit failed: {getattr(e, 'stderr', '') or e}"
    return report


def recover_unfinished() -> list[dict]:
    """Finish sessions left open by a crash (marker file still present)."""
    reports = []
    for marker in sorted(SESSIONS.glob(f"*/*/{RECORDING_MARKER}")):
        sid = marker.parent.name
        if sid in _next_seq:  # being recorded right now by this process
            continue
        try:
            reports.append(finish(sid, recovered=True))
        except Exception as e:
            reports.append({"session": {"id": sid}, "commit": None, "warning": f"recovery failed: {e}"})
    return reports


# --- listing -------------------------------------------------------------------

def list_sessions() -> list[dict]:
    out = []
    for f in sorted(SESSIONS.glob("*/*/session.json"), reverse=True):
        s = json.loads(f.read_text(encoding="utf-8"))
        d = f.parent
        out.append({
            **s,
            "asr": sorted(p.stem for p in (d / "asr").glob("*.json")),
            "transcript": (d / "transcript.jsonl").exists(),
            "has_original": (d / "original.wav").exists(),
            "has_audio": (d / "audio.opus").exists() and (d / "audio.opus").stat().st_size > 1024,
        })
    return out

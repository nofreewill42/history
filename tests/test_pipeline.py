"""Pipeline tests that need no ASR weights: a fake engine stands in for the model.

Run with: uv run pytest
"""

import json
import struct

import numpy as np
import pytest

from studio import audio, engines, gitops, jobs, models, sessions


def tone(seconds, rate, freq=220.0):
    t = np.arange(int(seconds * rate)) / rate
    return (0.3 * np.sin(2 * np.pi * freq * t) * 32767).astype("<i2").tobytes()


# --- audio -------------------------------------------------------------------------

def test_wav_is_valid_after_every_chunk(tmp_path):
    w = tmp_path / "original.wav"
    audio.wav_create(w, 48000)
    audio.wav_append(w, tone(1, 48000))
    audio.wav_append(w, tone(0.5, 48000))
    head = w.read_bytes()[:44]
    assert struct.unpack("<I", head[40:44])[0] == 2 * 72000
    assert len(audio.load_for_asr(w)) == 24000  # ffmpeg reads it: 1.5 s at 16 kHz


def test_repair_after_crash(tmp_path):
    w = tmp_path / "original.wav"
    audio.wav_create(w, 16000)
    with open(w, "ab") as f:  # data written but header never updated, plus a torn sample
        f.write(tone(2, 16000) + b"\x01")
    assert audio.wav_repair(w) == pytest.approx(2.0)
    assert struct.unpack("<I", w.read_bytes()[40:44])[0] == 64000


def test_split_points_cut_in_silence():
    rate = audio.ASR_RATE
    speech = np.ones(rate * 38, dtype=np.float32) * 0.5
    silence = np.zeros(rate // 2, dtype=np.float32)
    x = np.concatenate([speech, silence, speech, silence, speech])
    pieces = audio.split_points(x, 40)
    assert pieces[0][0] == 0 and pieces[-1][1] == len(x)
    assert all(b - a <= 40 * rate for a, b in pieces)
    assert all(a == b for (_, a), (b, _) in zip(pieces, pieces[1:]))  # contiguous
    first_cut = pieces[0][1] / rate
    assert 38.0 <= first_cut <= 38.5  # inside the silence


# --- sessions ------------------------------------------------------------------------

@pytest.fixture
def repo(tmp_path, monkeypatch):
    root = tmp_path / "sessions"
    root.mkdir()
    monkeypatch.setattr(sessions, "SESSIONS", root)
    commits = []
    monkeypatch.setattr(gitops, "lfs_problem", lambda p: None)
    monkeypatch.setattr(gitops, "commit", lambda paths, msg: commits.append((paths, msg)) or "abc1234")
    return root, commits


def test_session_record_and_finish(repo):
    root, commits = repo
    meta = sessions.create(48000, mic="Test mic", device="test-pc")
    sid = meta["id"]
    sessions.append_audio(sid, 0, tone(5, 48000))
    sessions.append_audio(sid, 0, tone(5, 48000))  # retry of chunk 0: ignored
    with pytest.raises(ValueError):
        sessions.append_audio(sid, 2, tone(1, 48000))  # chunk 1 missing
    assert sessions.append_audio(sid, 1, tone(2.5, 48000)) == pytest.approx(7.5)
    sessions.append_nav(sid, [{"t": 0, "text": "1-enoch", "ref": None, "heading": "The Book of Enoch"},
                              {"t": 3.25, "text": "1-enoch", "ref": "22:5", "heading": "Sheol"}])
    report = sessions.finish(sid)
    d = root / sid[:4] / sid
    s = json.loads((d / "session.json").read_text())
    assert list(s) == ["id", "started", "duration_s", "device", "mic", "audio", "texts", "notes"]
    assert s["duration_s"] == 7.5 and s["texts"] == ["1-enoch"] and s["mic"] == "Test mic"
    assert s["audio"] == {"codec": "opus", "bitrate_kbps": 24, "channels": 1}
    assert (d / "audio.opus").stat().st_size > 1000
    assert not (d / sessions.RECORDING_MARKER).exists()
    nav = [json.loads(line) for line in (d / "nav.jsonl").read_text().splitlines()]
    assert nav[1] == {"t": 3.25, "text": "1-enoch", "ref": "22:5", "heading": "Sheol"}
    assert report["commit"] == "abc1234"
    assert {p.name for p in commits[0][0]} == {"session.json", "audio.opus", "nav.jsonl"}


def test_same_minute_gets_suffix(repo, monkeypatch):
    from datetime import datetime, timedelta, timezone
    fixed = datetime(2026, 11, 1, 21, 7, 30, tzinfo=timezone(timedelta(hours=1)))
    monkeypatch.setattr(sessions, "_now", lambda: fixed)
    ids = [sessions.create(16000)["id"] for _ in range(3)]
    assert ids == ["2026-11-01T2107", "2026-11-01T2107-2", "2026-11-01T2107-3"]
    assert json.loads((repo[0] / "2026" / ids[0] / sessions.RECORDING_MARKER).read_text())["started"] == "2026-11-01T21:07:30+01:00"


def test_recover_unfinished(repo):
    root, _ = repo
    sid = sessions.create(16000)["id"]
    sessions.append_audio(sid, 0, tone(1, 16000))
    sessions._next_seq.pop(sid)  # simulate a studio restart
    reports = sessions.recover_unfinished()
    assert reports[0]["session"]["notes"] == "recovered after interruption"
    assert (root / sid[:4] / sid / "session.json").exists()


def test_no_commit_without_lfs(repo, monkeypatch):
    monkeypatch.setattr(gitops, "lfs_problem", lambda p: "git-lfs is not installed")
    sid = sessions.create(16000)["id"]
    sessions.append_audio(sid, 0, tone(1, 16000))
    report = sessions.finish(sid)
    assert report["commit"] is None and "git-lfs is not installed" in report["warning"]


# --- final pass with a fake engine ---------------------------------------------------------

class FakeEngine(engines.Engine):
    """Returns one segment per 2 s of audio, with words, like faster-whisper."""

    def __init__(self, entry):
        self.entry, self.path, self.device = entry, None, "cpu"

    def transcribe(self, x, prompt=None, progress=None):
        n = len(x) / audio.ASR_RATE
        return [{"start": t, "end": min(t + 2, n), "text": f"words at {t}",
                 "words": [{"start": t, "end": t + 0.5, "word": "words", "probability": 0.9}]}
                for t in np.arange(0, n, 2.0).tolist()]


@pytest.fixture
def fake_model(monkeypatch):
    entry = models.get("whisper-tiny.en")
    monkeypatch.setattr(engines, "load", lambda mid: FakeEngine(dict(entry, chunk_s=3)))
    monkeypatch.setattr(models, "revision", lambda e: "deadbeef")
    return entry


def test_final_pass_writes_asr_and_seeds_transcript(repo, fake_model):
    root, commits = repo
    sid = sessions.create(16000)["id"]
    sessions.append_audio(sid, 0, tone(7, 16000))
    sessions.finish(sid)
    job = jobs.submit(sid, "whisper-tiny.en")
    jobs._run(job)
    d = root / sid[:4] / sid
    asr = json.loads((d / "asr" / "whisper-tiny.en.json").read_text())
    assert list(asr) == ["model", "settings", "created", "audio", "segments"]
    assert asr["model"]["revision"] == "deadbeef" and asr["audio"] == {"file": "original.wav", "duration_s": 7.0}
    assert asr["settings"]["language"] == "en" and asr["settings"]["task"] == "transcribe"
    starts = [s["start"] for s in asr["segments"]]
    assert starts == sorted(starts) and asr["segments"][-1]["end"] <= 7.0  # chunk offsets applied
    lines = [json.loads(line) for line in (d / "transcript.jsonl").read_text().splitlines()]
    assert list(lines[0]) == ["start", "end", "text", "source", "checked", "lang", "kind", "ref"]
    assert lines[0]["source"] == "whisper-tiny.en" and lines[0]["kind"] == "comment" and lines[0]["ref"] is None
    assert commits[-1][1] == f"Transcribe session {sid} with whisper-tiny.en"

    # A re-run must not overwrite a transcript that has checked segments.
    lines[0]["checked"] = True
    (d / "transcript.jsonl").write_text("".join(json.dumps(x) + "\n" for x in lines))
    job2 = jobs.submit(sid, "whisper-tiny.en")
    jobs._run(job2)
    assert json.loads((d / "transcript.jsonl").read_text().splitlines()[0])["checked"] is True
    assert "kept" in job2["note"]


def test_registry_fields():
    required = {"id", "name", "engine", "hf_repo", "languages", "english_only", "params", "vram_gb",
                "license", "word_timestamps", "supports_prompt", "notes"}
    reg = models.registry()
    assert {m["id"] for m in reg} >= {"canary-qwen-2.5b", "parakeet-tdt-0.6b-v2", "parakeet-tdt-0.6b-v3",
                                      "whisper-large-v3", "whisper-large-v3-turbo", "granite-speech-3.3-8b"}
    for m in reg:
        assert required <= set(m), m["id"]
        assert m["engine"] in engines.ENGINES

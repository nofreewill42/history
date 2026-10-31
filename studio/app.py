"""The studio: a local FastAPI app. Start with `uv run studio`."""

from __future__ import annotations

import argparse
import webbrowser

from fastapi import Body, FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles

from . import audio, gitops, jobs, models, sessions, texts
from .paths import READER, SESSIONS, TEXTS

app = FastAPI(title="history studio")
_recovered: list[dict] = []


def _bad(e: Exception, code: int = 400):
    raise HTTPException(code, f"{e}")


# --- status, texts -----------------------------------------------------------------

@app.get("/api/status")
def status():
    return {
        "ffmpeg": audio.ffmpeg_path() is not None,
        "lfs_problem": gitops.lfs_problem(SESSIONS / "0000" / "0000" / "audio.opus"),
        "settings": models.settings(),
        "recovered": _recovered,
    }


@app.get("/api/texts")
def list_texts():
    return texts.list_texts()


# --- models ------------------------------------------------------------------------

@app.get("/api/models")
def list_models():
    return {"models": models.all_status(), "settings": models.settings()}


@app.post("/api/models/{model_id}/install")
def install_model(model_id: str):
    try:
        models.install(model_id)
    except (KeyError, ValueError) as e:
        _bad(e)
    return {"ok": True}


@app.delete("/api/models/{model_id}")
def delete_model(model_id: str):
    try:
        from . import engines
        engines.unload(model_id)
        models.delete(model_id)
    except (KeyError, ValueError) as e:
        _bad(e)
    return {"ok": True}


@app.put("/api/settings")
def put_settings(body: dict = Body(...)):
    for key in ("live_model", "final_model"):
        if body.get(key):
            try:
                models.get(body[key])
            except KeyError as e:
                _bad(e)
    return models.save_settings(**body)


# --- sessions ------------------------------------------------------------------------

@app.get("/api/sessions")
def list_sessions():
    return sessions.list_sessions()


@app.post("/api/sessions")
def create_session(body: dict = Body(...)):
    rate = int(body.get("sample_rate", 0))
    if not 8000 <= rate <= 192000:
        _bad(ValueError("sample_rate must be between 8000 and 192000"))
    meta = sessions.create(rate, mic=str(body.get("mic", ""))[:200])
    if body.get("live"):
        jobs.live_start(meta["id"])
    return meta


@app.post("/api/sessions/{sid}/audio")
async def session_audio(sid: str, seq: int, request: Request):
    data = await request.body()
    try:
        return {"duration_s": sessions.append_audio(sid, seq, data)}
    except (ValueError, FileNotFoundError) as e:
        _bad(e, 409)


@app.post("/api/sessions/{sid}/nav")
def session_nav(sid: str, events: list[dict] = Body(...)):
    try:
        sessions.append_nav(sid, events)
    except (ValueError, KeyError, FileNotFoundError) as e:
        _bad(e)
    return {"ok": True}


@app.post("/api/sessions/{sid}/live")
def session_live(sid: str, body: dict = Body(...)):
    if body.get("enabled"):
        jobs.live_start(sid)
    else:
        jobs.live_stop()
    return jobs.live_state()


@app.get("/api/live")
def live():
    return jobs.live_state()


@app.post("/api/sessions/{sid}/stop")
def stop_session(sid: str, body: dict = Body(default={})):
    if jobs.live_state()["session"] == sid:
        jobs.live_stop()
    try:
        report = sessions.finish(sid, notes=str(body.get("notes", "")))
    except (ValueError, FileNotFoundError) as e:
        _bad(e)
    final = models.settings()["final_model"]
    report["job"] = jobs.submit(sid, final) if final else None
    if not final:
        report["warning"] = ((report["warning"] + " ") if report["warning"] else "") + \
            "No final model chosen, so nothing was transcribed. Choose one in the Models panel."
    return report


@app.post("/api/sessions/{sid}/transcribe")
def transcribe_session(sid: str, body: dict = Body(...)):
    try:
        return jobs.submit(sid, body["model"])
    except (KeyError, ValueError) as e:
        _bad(e)


@app.get("/api/jobs")
def list_jobs():
    return jobs.list_jobs()


# --- static files (mounted last so /api wins) -------------------------------------

app.mount("/texts", StaticFiles(directory=TEXTS), name="texts")
app.mount("/", StaticFiles(directory=READER, html=True), name="reader")


def main() -> None:
    parser = argparse.ArgumentParser(description="history studio: reader page, recording and ASR")
    parser.add_argument("--host", default="127.0.0.1", help="listen address (default: localhost only)")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true", help="don't open the page in a browser")
    args = parser.parse_args()

    if audio.ffmpeg_path() is None:
        raise SystemExit("ffmpeg not found. Install it first (e.g. sudo apt install ffmpeg).")
    SESSIONS.mkdir(exist_ok=True)
    _recovered.extend(sessions.recover_unfinished())
    for r in _recovered:
        print(f"recovered session {r['session']['id']}: commit={r.get('commit')} {r.get('warning') or ''}")
    jobs.start_workers()
    final = models.settings()["final_model"]
    if final:
        for r in _recovered:
            if "duration_s" in r["session"]:
                jobs.submit(r["session"]["id"], final)

    url = f"http://{'localhost' if args.host in ('127.0.0.1', '0.0.0.0') else args.host}:{args.port}/"
    print(f"history studio: {url}")
    if not args.no_browser:
        webbrowser.open(url)

    import uvicorn
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")

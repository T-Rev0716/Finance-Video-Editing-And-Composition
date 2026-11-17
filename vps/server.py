"""Local web server. Binds to 127.0.0.1 only - this app is for your own machine."""
from __future__ import annotations

import threading

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import __version__, config, pipeline, projects, reports
from .sources import fred
from .sources.http import FetchError

WEB_DIR = config.ROOT / "web"
MAX_TRANSCRIPT_BYTES = 5 * 1024 * 1024

app = FastAPI(title="Video Prep Studio", version=__version__, docs_url=None, redoc_url=None)

# Progress of running generations, kept in memory: {project_id: {"steps": [...], "done": bool, "error": str}}
_jobs: dict[str, dict] = {}
_jobs_lock = threading.Lock()


class NewProject(BaseModel):
    topic: str
    theme_index: int | None = None
    extra_series: str = ""


class SettingsUpdate(BaseModel):
    values: dict[str, str]
    clear: list[str] = []


class Checks(BaseModel):
    checks: dict[str, bool]


def _project_or_404(project_id: str) -> dict:
    try:
        return projects.load(project_id)
    except (FileNotFoundError, ValueError):
        raise HTTPException(404, "Project not found") from None


@app.get("/")
def index() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html", headers={"Cache-Control": "no-store"})


@app.get("/api/state")
def state() -> dict:
    settings = config.load_settings()
    report = reports.latest_report()
    return {
        "version": __version__,
        "report": report,
        "report_files": [p.name for p in reports.list_report_files()],
        "reports_folder": str(config.reports_dir()),
        "projects": projects.list_projects(),
        "keys": {"fred": bool(settings["FRED_API_KEY"]), "llm": bool(settings["ANTHROPIC_API_KEY"])},
    }


def _run_job(project_id: str, topic: str, theme: dict | None, report: dict | None, extra: list[str]) -> None:
    def progress(message: str) -> None:
        with _jobs_lock:
            _jobs[project_id]["steps"].append(message)

    try:
        pipeline.generate(project_id, topic, theme, report, extra, progress)
    except Exception as exc:  # the pipeline has already saved the error into project.json
        with _jobs_lock:
            _jobs[project_id]["error"] = str(exc)
    finally:
        with _jobs_lock:
            _jobs[project_id]["done"] = True


@app.post("/api/projects")
def create_project(body: NewProject) -> dict:
    topic = " ".join(body.topic.split())
    if not topic:
        raise HTTPException(400, "Type a topic or pick one of the cards.")
    if len(topic) > 300:
        raise HTTPException(400, "Keep the topic under 300 characters.")
    report = reports.latest_report()
    theme = None
    if body.theme_index is not None and report and 0 <= body.theme_index < len(report["themes"]):
        theme = report["themes"][body.theme_index]
    extra = [s for s in body.extra_series.replace(",", " ").split() if s][:4]
    project_id = projects.new_project_id(topic)
    projects.project_dir(project_id).mkdir(parents=True, exist_ok=True)
    with _jobs_lock:
        _jobs[project_id] = {"steps": ["Starting"], "done": False, "error": ""}
    threading.Thread(target=_run_job, args=(project_id, topic, theme, report, extra), daemon=True).start()
    return {"id": project_id}


@app.get("/api/projects/{project_id}/progress")
def progress(project_id: str) -> dict:
    with _jobs_lock:
        job = dict(_jobs.get(project_id) or {})
    if job:
        return {"steps": list(job["steps"]), "done": job["done"], "error": job["error"]}
    project = _project_or_404(project_id)  # e.g. after a restart: read the saved status
    return {"steps": [], "done": project.get("status") != "generating", "error": project.get("error", "")}


@app.get("/api/projects/{project_id}")
def get_project(project_id: str) -> dict:
    return _project_or_404(project_id)


@app.get("/api/projects/{project_id}/file/{relative:path}")
def project_file(project_id: str, relative: str, download: int = 0) -> FileResponse:
    try:
        path = projects.safe_file(project_id, relative)
    except (FileNotFoundError, ValueError):
        raise HTTPException(404, "File not found") from None
    return FileResponse(path, filename=path.name if download else None)


@app.post("/api/projects/{project_id}/transcript")
async def upload_transcript(project_id: str, file: UploadFile = File(...)) -> dict:
    _project_or_404(project_id)
    name = file.filename or "transcript.txt"
    if not name.lower().endswith((".srt", ".txt")):
        raise HTTPException(400, "Upload a .srt or .txt transcript.")
    raw = await file.read(MAX_TRANSCRIPT_BYTES + 1)
    if len(raw) > MAX_TRANSCRIPT_BYTES:
        raise HTTPException(400, "That file is larger than 5 MB. Upload the transcript, not the video.")
    text = raw.decode("utf-8-sig", errors="replace")
    if not text.strip():
        raise HTTPException(400, "That file is empty.")
    # Clip selection can call the LLM, so run it off the event loop.
    import anyio
    return await anyio.to_thread.run_sync(pipeline.add_transcript, project_id, name, text)


@app.post("/api/projects/{project_id}/checks")
def save_checks(project_id: str, body: Checks) -> dict:
    _project_or_404(project_id)
    return pipeline.set_manual_checks(project_id, body.checks)


@app.get("/api/projects/{project_id}/export")
def export_zip(project_id: str) -> Response:
    _project_or_404(project_id)
    return Response(projects.zip_bytes(project_id), media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="{project_id}.zip"'})


@app.get("/api/settings")
def get_settings() -> dict:
    return {"settings": config.public_settings(), "env_file": str(config.env_path())}


@app.post("/api/settings")
def update_settings(body: SettingsUpdate) -> dict:
    updates: dict[str, str] = {}
    for key, value in body.values.items():
        if key not in config.SETTING_KEYS:
            continue
        secret = config.SETTING_KEYS[key][1]
        value = value.strip()
        if secret and not value:
            continue  # a blank key field means "keep what is saved"
        if key == "CHART_THEME" and value not in ("dark", "light"):
            continue
        updates[key] = value
    for key in body.clear:
        if key in config.SETTING_KEYS:
            updates[key] = ""
    config.save_settings(updates)
    return get_settings()


@app.post("/api/settings/test-fred")
def test_fred() -> dict:
    key = config.load_settings()["FRED_API_KEY"]
    try:
        series = fred.fetch_series("DGS10", api_key=key)
    except FetchError as exc:
        return {"ok": False, "message": f"Could not reach FRED: {exc}"}
    if key and series.fetched_via != "fred_api":
        return {"ok": False, "message": "FRED did not accept the key, but the public download works. " + " ".join(series.notes)}
    how = "with your API key" if key else "without a key (public download)"
    return {"ok": True, "message": f"FRED works {how}. Latest 10-year Treasury yield: {series.latest_value:.2f}% on {series.latest_date}."}


app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")

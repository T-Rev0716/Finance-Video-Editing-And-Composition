"""Local web server. Binds to 127.0.0.1 only - this app is for your own machine."""
from __future__ import annotations

import threading
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import (__version__, asset_board, config, fact_diff, graphics, learning_log, llm, pipeline, projects,
               recording_cards, reports, thumbnails, timeline, transcribe)
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
        "wording_engine": llm.provider(settings),
        "radar_dir": settings["RADAR_REPORTS_DIR"],
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
        if key == "LLM_PROVIDER" and value not in ("auto", "anthropic", "ollama", "templates"):
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



# =====================================================================================
# Creator studio: recording cards, asset board, thumbnails, graphics
# =====================================================================================
USER_ERRORS = (asset_board.AssetError, thumbnails.ThumbnailError, graphics.GraphicsError, fact_diff.FactDiffError,
               transcribe.Unavailable, reports.RadarImportError, ValueError)


def _try(action):
    """Run a studio action; turn 'the user asked for something not allowed' into a clear 400."""
    try:
        return action()
    except KeyError as exc:
        raise HTTPException(404, f"Not found: {exc.args[0]}") from None
    except FileNotFoundError:
        raise HTTPException(404, "Not found") from None
    except USER_ERRORS as exc:
        raise HTTPException(400, str(exc)) from None


class CardEdit(BaseModel):
    text: str | None = None
    pronunciation: str | None = None
    fact_ids: list[str] | None = None
    checkpoint: bool = True


class CardStatus(BaseModel):
    status: str


class CardMove(BaseModel):
    delta: int


class CardOrder(BaseModel):
    order: list[str]


class TextCheck(BaseModel):
    text: str


class Cues(BaseModel):
    cues: list[dict]
    total_seconds: float = 0


def _cards_view(project_id: str, state: dict | None = None) -> dict:
    project = _project_or_404(project_id)
    return recording_cards.view(state or recording_cards.load(project_id, project), project)


@app.get("/api/projects/{project_id}/cards")
def get_cards(project_id: str) -> dict:
    return _cards_view(project_id)


@app.put("/api/projects/{project_id}/cards/{card_id}")
def edit_card(project_id: str, card_id: str, body: CardEdit) -> dict:
    _project_or_404(project_id)
    changes = {k: v for k, v in body.model_dump().items() if k != "checkpoint" and v is not None}
    return _cards_view(project_id, _try(lambda: recording_cards.update_card(project_id, card_id, changes, body.checkpoint)))


@app.post("/api/projects/{project_id}/cards/{card_id}/status")
def card_status(project_id: str, card_id: str, body: CardStatus) -> dict:
    _project_or_404(project_id)
    state = _try(lambda: recording_cards.set_status(project_id, card_id, body.status))
    view = _cards_view(project_id, state)
    if body.status == "recorded":  # freeze what was recorded against, the first time
        view["frozen_at"] = fact_diff.ensure_frozen(project_id, "first card marked recorded")["frozen_at"]
    return view


@app.post("/api/projects/{project_id}/cards/{card_id}/move")
def card_move(project_id: str, card_id: str, body: CardMove) -> dict:
    _project_or_404(project_id)
    return _cards_view(project_id, _try(lambda: recording_cards.move(project_id, card_id, body.delta)))


@app.post("/api/projects/{project_id}/cards/{card_id}/reset")
def card_reset(project_id: str, card_id: str) -> dict:
    _project_or_404(project_id)
    return _cards_view(project_id, _try(lambda: recording_cards.reset_card(project_id, card_id)))


@app.post("/api/projects/{project_id}/cards-order")
def cards_order(project_id: str, body: CardOrder) -> dict:
    _project_or_404(project_id)
    return _cards_view(project_id, _try(lambda: recording_cards.reorder(project_id, body.order)))


@app.post("/api/projects/{project_id}/cards-undo")
def cards_undo(project_id: str) -> dict:
    _project_or_404(project_id)
    return _cards_view(project_id, recording_cards.undo(project_id))


@app.post("/api/projects/{project_id}/cards-redo")
def cards_redo(project_id: str) -> dict:
    _project_or_404(project_id)
    return _cards_view(project_id, recording_cards.redo(project_id))


@app.post("/api/projects/{project_id}/cards-check")
def cards_check(project_id: str, body: TextCheck) -> dict:
    """Live number-guard and compliance check while typing (nothing is saved)."""
    return recording_cards.check_text(body.text, _project_or_404(project_id))


@app.post("/api/projects/{project_id}/cards-cues")
def cards_cues(project_id: str, body: Cues) -> dict:
    _project_or_404(project_id)
    return _cards_view(project_id, _try(lambda: recording_cards.set_cues(project_id, body.cues, body.total_seconds)))


@app.get("/api/projects/{project_id}/timeline/{name}")
def timeline_file(project_id: str, name: str) -> PlainTextResponse:
    project = _project_or_404(project_id)
    state = recording_cards.load(project_id, project)
    record = project.get("recording") or {}
    uri = Path(record["path"]).as_uri() if record.get("path") and Path(record["path"]).is_absolute() else ""
    files = timeline.export_all(project, state, uri)
    if name not in files:
        raise HTTPException(404, "Choose chapters.txt, timeline.edl or timeline.fcpxml")
    folder = projects.project_dir(project_id) / "timeline"
    folder.mkdir(exist_ok=True)
    for file_name, text in files.items():
        (folder / file_name).write_text(text, encoding="utf-8")
    return PlainTextResponse(files[name], headers={"Content-Disposition": f'attachment; filename="{name}"'})


# ---------------------------------------------------------------- visual asset board
class SlotStatus(BaseModel):
    status: str


class LibraryPick(BaseModel):
    library_id: str


@app.get("/api/projects/{project_id}/asset-board")
def get_board(project_id: str) -> dict:
    return asset_board.view(asset_board.load(project_id, _project_or_404(project_id)))


@app.post("/api/projects/{project_id}/shots/{shot_n}/asset")
def upload_asset(project_id: str, shot_n: int, file: UploadFile = File(...), save_to_library: bool = Form(False)) -> dict:
    _project_or_404(project_id)
    name = file.filename or "asset"
    return asset_board.view(_try(lambda: asset_board.attach_file(project_id, shot_n, name, file.file, save_to_library)))


@app.post("/api/projects/{project_id}/shots/{shot_n}/asset-status")
def asset_status(project_id: str, shot_n: int, body: SlotStatus) -> dict:
    _project_or_404(project_id)
    return asset_board.view(_try(lambda: asset_board.set_status(project_id, shot_n, body.status)))


@app.post("/api/projects/{project_id}/shots/{shot_n}/asset-library")
def asset_from_library(project_id: str, shot_n: int, body: LibraryPick) -> dict:
    _project_or_404(project_id)
    return asset_board.view(_try(lambda: asset_board.assign_from_library(project_id, shot_n, body.library_id)))


@app.post("/api/projects/{project_id}/shots/{shot_n}/asset-clear")
def asset_clear(project_id: str, shot_n: int) -> dict:
    _project_or_404(project_id)
    return asset_board.view(_try(lambda: asset_board.clear(project_id, shot_n)))


@app.get("/api/library")
def library() -> dict:
    return {"items": asset_board.library_list()}


@app.get("/api/library/file/{file_id}")
def library_file(file_id: str) -> FileResponse:
    return FileResponse(_try(lambda: asset_board.library_file(file_id)))


@app.delete("/api/library/{file_id}")
def library_delete(file_id: str) -> dict:
    return {"items": _try(lambda: asset_board.library_remove(file_id))}


# ---------------------------------------------------------------- thumbnail workshop
class Preset(BaseModel):
    name: str
    layout: str
    theme: str
    host: str = ""


@app.get("/api/thumbnails/options")
def thumbnail_options() -> dict:
    return thumbnails.options()


@app.get("/api/assets/hosts")
def hosts() -> dict:
    return {"hosts": thumbnails.list_hosts()}


@app.post("/api/assets/hosts")
def add_host(file: UploadFile = File(...)) -> dict:
    name = file.filename or "host.png"
    _try(lambda: thumbnails.add_host(name, file.file))
    return {"hosts": thumbnails.list_hosts()}


@app.get("/api/assets/hosts/file/{name}")
def host_image(name: str) -> FileResponse:
    return FileResponse(_try(lambda: thumbnails.host_file(name)))


@app.delete("/api/assets/hosts/{name}")
def delete_host(name: str) -> dict:
    return {"hosts": _try(lambda: thumbnails.remove_host(name))}


@app.post("/api/projects/{project_id}/thumbnails")
def make_thumbnail(project_id: str, body: dict) -> dict:
    _project_or_404(project_id)
    channel = config.load_settings()["CHANNEL_NAME"]
    return _try(lambda: thumbnails.create(project_id, body, channel))


@app.delete("/api/projects/{project_id}/thumbnails/{number}")
def delete_thumbnail(project_id: str, number: int) -> dict:
    _project_or_404(project_id)
    return {"thumbnail_renders": thumbnails.remove(project_id, number)}


@app.post("/api/thumbnails/presets")
def save_preset(body: Preset) -> dict:
    return {"presets": _try(lambda: thumbnails.save_preset(body.name, body.layout, body.theme, body.host))}


@app.delete("/api/thumbnails/presets/{name}")
def delete_preset(name: str) -> dict:
    return {"presets": thumbnails.delete_preset(name)}


# ---------------------------------------------------------------- explanation graphics
@app.post("/api/projects/{project_id}/graphics")
def make_graphic(project_id: str, body: dict) -> dict:
    _project_or_404(project_id)
    kind = body.get("type")
    if kind == "reveal":
        return _try(lambda: graphics.reveal_animation(project_id, int(body.get("chart_n") or 0)))
    if kind == "highlight":
        return _try(lambda: graphics.highlight_chart(project_id, int(body.get("chart_n") or 0), str(body.get("when", "")),
                                                     str(body.get("label", "")), int(body.get("series_index") or 0)))
    if kind == "comparison":
        return _try(lambda: graphics.comparison_card(project_id, str(body.get("title", "")), body.get("fact_ids") or None,
                                                     body.get("chart_n"), body.get("dates"), int(body.get("series_index") or 0)))
    if kind == "flow":
        return _try(lambda: graphics.flow_diagram(project_id, body.get("steps") or [], str(body.get("title", ""))))
    raise HTTPException(400, "type must be reveal, highlight, comparison or flow")


@app.delete("/api/projects/{project_id}/graphics/{number}")
def delete_graphic(project_id: str, number: int) -> dict:
    _project_or_404(project_id)
    return {"graphics": graphics.remove(project_id, number)}


# =====================================================================================
# Fact freeze, learning log, local post-production
# =====================================================================================
class Decisions(BaseModel):
    decisions: dict[str, str]


@app.post("/api/projects/{project_id}/freeze-facts")
def freeze_facts(project_id: str) -> dict:
    _project_or_404(project_id)
    snapshot = fact_diff.freeze(project_id, "manual")
    return {"frozen_at": snapshot["frozen_at"], "facts": len(snapshot["facts"]), "series": len(snapshot["series"])}


@app.post("/api/projects/{project_id}/check-changes")
def check_changes(project_id: str) -> dict:
    _project_or_404(project_id)
    return _try(lambda: fact_diff.check_changes(project_id))


@app.get("/api/projects/{project_id}/fact-changes")
def fact_changes(project_id: str) -> dict:
    _project_or_404(project_id)
    snapshot = fact_diff.frozen(project_id)
    return {"frozen": {"frozen_at": snapshot["frozen_at"], "reason": snapshot["reason"], "facts": len(snapshot["facts"])} if snapshot else None,
            "report": fact_diff.last_report(project_id)}


@app.post("/api/projects/{project_id}/resolve-changes")
def resolve_changes(project_id: str, body: Decisions) -> dict:
    _project_or_404(project_id)
    return _try(lambda: fact_diff.resolve(project_id, body.decisions))


@app.get("/api/projects/{project_id}/learning-log")
def get_learning(project_id: str) -> dict:
    _project_or_404(project_id)
    return learning_log.load(project_id)


@app.post("/api/projects/{project_id}/learning-log")
def save_learning(project_id: str, body: dict) -> dict:
    _project_or_404(project_id)
    return _try(lambda: learning_log.save(project_id, body))


@app.get("/api/learning-log")
def learning_summary() -> dict:
    return learning_log.summarize()


class RecordingPath(BaseModel):
    path: str


class DeadAir(BaseModel):
    min_silence: float = transcribe.MIN_SILENCE


class ShortRequest(BaseModel):
    chart_n: int | None = None


@app.get("/api/capabilities")
def capabilities() -> dict:
    return transcribe.capabilities()


@app.post("/api/projects/{project_id}/recording")
def upload_recording(project_id: str, file: UploadFile = File(...)) -> dict:
    _project_or_404(project_id)
    name = file.filename or "recording.mp4"
    return _try(lambda: transcribe.add_upload(project_id, name, file.file))


@app.post("/api/projects/{project_id}/recording-path")
def recording_from_path(project_id: str, body: RecordingPath) -> dict:
    _project_or_404(project_id)
    return _try(lambda: transcribe.add_path(project_id, body.path))


def _run_transcription(project_id: str) -> None:
    key = f"{project_id}:transcribe"

    def progress(message: str) -> None:
        with _jobs_lock:
            _jobs[key]["steps"].append(message)

    try:
        project = projects.load(project_id)
        source = transcribe.recording_path(project)
        segments, _label = transcribe.transcribe(source, config.load_settings()["WHISPER_MODEL"], progress)
        progress("Checking spoken numbers against the fact sheet and planning clips")
        pipeline.add_transcript(project_id, "transcript.srt", transcribe.segments_to_srt(segments))
    except Exception as exc:
        with _jobs_lock:
            _jobs[key]["error"] = str(exc)
    finally:
        with _jobs_lock:
            _jobs[key]["done"] = True


@app.post("/api/projects/{project_id}/transcribe")
def start_transcription(project_id: str) -> dict:
    project = _project_or_404(project_id)
    _try(lambda: transcribe.recording_path(project))
    if not transcribe.capabilities()["faster_whisper"]:
        raise HTTPException(400, transcribe.capabilities()["transcribe_note"])
    with _jobs_lock:
        _jobs[f"{project_id}:transcribe"] = {"steps": ["Loading the speech model"], "done": False, "error": ""}
    threading.Thread(target=_run_transcription, args=(project_id,), daemon=True).start()
    return {"started": True}


@app.get("/api/projects/{project_id}/transcribe/progress")
def transcription_progress(project_id: str) -> dict:
    with _jobs_lock:
        job = dict(_jobs.get(f"{project_id}:transcribe") or {"steps": [], "done": True, "error": ""})
    return {"steps": list(job["steps"]), "done": job["done"], "error": job["error"]}


@app.post("/api/projects/{project_id}/strip-dead-air")
def strip_dead_air(project_id: str, body: DeadAir) -> dict:
    _project_or_404(project_id)
    if not 0.2 <= body.min_silence <= 5:
        raise HTTPException(400, "Choose a silence length between 0.2 and 5 seconds.")
    return _try(lambda: transcribe.strip_dead_air(project_id, body.min_silence))


@app.post("/api/projects/{project_id}/clips/{clip_n}/short")
def make_short(project_id: str, clip_n: int, body: ShortRequest) -> dict:
    _project_or_404(project_id)
    return _try(lambda: transcribe.export_short(project_id, clip_n, body.chart_n))


@app.get("/api/ollama/models")
def ollama_models() -> dict:
    try:
        return {"ok": True, "models": llm.ollama_models(config.load_settings())}
    except llm.LLMUnavailable as exc:
        return {"ok": False, "models": [], "message": str(exc)}


@app.post("/api/reports/refresh")
def refresh_reports() -> dict:
    return _try(lambda: reports.import_latest_radar(config.load_settings()["RADAR_REPORTS_DIR"]))


app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")

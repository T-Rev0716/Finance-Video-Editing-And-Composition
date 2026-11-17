"""Project storage: one folder per video under projects/. Plain files, nothing hidden."""
from __future__ import annotations

import io
import json
import re
import zipfile
from datetime import datetime
from pathlib import Path

from . import config, exports


ZIP_SKIP = {"recording", "staging"}


def slugify(text: str, limit: int = 48) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:limit].rstrip("-") or "topic"


def new_project_id(topic: str, now: datetime | None = None) -> str:
    now = now or datetime.now()
    base = f"{now:%Y-%m-%d}_{slugify(topic)}"
    candidate, n = base, 2
    while (config.projects_dir() / candidate).exists():
        candidate, n = f"{base}-{n}", n + 1
    return candidate


def project_dir(project_id: str) -> Path:
    """Resolve a project folder, refusing anything that points outside projects/."""
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", project_id) or ".." in project_id:
        raise ValueError("invalid project id")
    root = config.projects_dir().resolve()
    path = (root / project_id).resolve()
    if path.parent != root:
        raise ValueError("invalid project id")
    return path


def safe_file(project_id: str, relative: str) -> Path:
    """A file inside the project folder (used to serve charts)."""
    base = project_dir(project_id)
    path = (base / relative).resolve()
    if base not in path.parents or not path.is_file():
        raise FileNotFoundError(relative)
    return path


def save(project: dict) -> None:
    folder = project_dir(project["id"])
    folder.mkdir(parents=True, exist_ok=True)
    tmp = folder / "project.json.tmp"
    tmp.write_text(json.dumps(project, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(folder / "project.json")


def load(project_id: str) -> dict:
    path = project_dir(project_id) / "project.json"
    if not path.exists():
        raise FileNotFoundError(project_id)
    return json.loads(path.read_text(encoding="utf-8"))


def list_projects() -> list[dict]:
    out = []
    for folder in config.projects_dir().iterdir():
        meta = folder / "project.json"
        if not meta.is_file():
            continue
        try:
            project = json.loads(meta.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue
        out.append({"id": project.get("id", folder.name), "topic": project.get("topic", ""),
                    "created": project.get("created", ""), "status": project.get("status", ""),
                    "charts": len(project.get("charts", [])),
                    "compliance": (project.get("compliance") or {}).get("summary", "")})
    return sorted(out, key=lambda p: p["created"], reverse=True)


def write_exports(project: dict) -> None:
    """(Re)write the human-readable files from project.json."""
    folder = project_dir(project["id"])
    files = {
        "fact_sheet.md": exports.fact_sheet_md(project),
        "outline.md": exports.outline_md(project),
        "shot_list.md": exports.shot_list_md(project),
        "titles_and_thumbnails.md": exports.titles_md(project),
        "youtube_description.txt": project["description"],
        "compliance_checklist.md": exports.compliance_md(project),
    }
    if project.get("clips"):
        files["clip_plan.md"] = exports.clips_md(project)
    for name, content in files.items():
        (folder / name).write_text(content, encoding="utf-8")


def zip_bytes(project_id: str) -> bytes:
    """The whole project folder as a ZIP."""
    folder = project_dir(project_id)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(folder.rglob("*")):
            top = path.relative_to(folder).parts[0]
            if top in ZIP_SKIP:  # raw recordings can be many GB; staging is a scratch area
                continue
            if path.is_file() and not path.name.endswith(".tmp"):
                archive.write(path, f"{folder.name}/{path.relative_to(folder).as_posix()}")
    return buffer.getvalue()

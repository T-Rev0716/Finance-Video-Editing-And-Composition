"""Visual asset board: one slot per planned scene, filled with a local file.

Charts made by the pipeline are linked automatically. Headline screenshots and B-roll
are dropped in by the user (no external service involved). Files live in the project's
assets/ folder; evergreen clips can also be saved to a library shared by every episode.
"""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import BinaryIO

from . import config, projects, store

BOARD_FILE = "asset_board.json"
MEDIA_TYPES = {".mp4": "video", ".mov": "video", ".webm": "video",
               ".png": "image", ".jpg": "image", ".jpeg": "image", ".gif": "image"}
MAX_BYTES = 4 * 1024 ** 3  # 4 GB per file
LIBRARY_INDEX = "library.json"


class AssetError(ValueError):
    """A file or request the board cannot accept. The message is shown to the user."""


def slot_kind(shot: dict) -> str:
    kind = shot["type"]
    if kind.startswith("CHART"):
        return "chart"
    if kind.startswith("HEADLINE"):
        return "headline"
    if kind.startswith("B-ROLL"):
        return "broll"
    return "talking_head"


def _new_slot(shot: dict) -> dict:
    kind = slot_kind(shot)
    slot = {"shot_n": shot["n"], "kind": kind, "section": shot["section"], "what": shot["what"],
            "required": kind != "talking_head", "status": "missing", "file": "", "media": "",
            "source": "", "original_name": "", "label": shot.get("label", ""), "blocked": bool(shot.get("blocked"))}
    if kind == "chart" and shot.get("file"):
        slot.update(file=f"charts/{shot['file']}", media="image", source="pipeline", status="ready")
    if kind == "talking_head":
        slot["status"] = "camera"  # recorded on camera; no file needed
    return slot


def _path(project_id: str) -> Path:
    return projects.project_dir(project_id) / BOARD_FILE


def load(project_id: str, project: dict | None = None) -> dict:
    """The board, kept in step with the project's shot list (existing slots are never reset)."""
    project = project or projects.load(project_id)
    board = store.read_json(_path(project_id), None) or {"slots": {}}
    changed = False
    wanted = {str(shot["n"]) for shot in project.get("shots", [])}
    for shot in project.get("shots", []):
        key = str(shot["n"])
        if key not in board["slots"]:
            board["slots"][key] = _new_slot(shot)
            changed = True
    for key in [k for k in board["slots"] if k not in wanted]:
        del board["slots"][key]
        changed = True
    if changed or "asset_board" not in project:
        _save(project_id, board)
    return board


def _save(project_id: str, board: dict) -> None:
    board["updated"] = store.now_iso()
    store.write_json(_path(project_id), board)
    try:
        project = projects.load(project_id)
    except FileNotFoundError:
        return
    project["asset_board"] = board
    projects.save(project)


def summary(board: dict) -> dict:
    """The tracker line: 'X of Y scene visuals ready - Z missing'."""
    required = [s for s in board["slots"].values() if s["required"]]
    ready = sum(1 for s in required if s["status"] == "ready")
    replace = sum(1 for s in required if s["status"] == "needs_replacement")
    missing = len(required) - ready
    text = f"{ready} of {len(required)} scene visuals ready — {missing} missing"
    if replace:
        text += f" ({replace} marked for replacement)"
    return {"total": len(required), "ready": ready, "missing": missing, "needs_replacement": replace, "text": text}


def view(board: dict) -> dict:
    slots = sorted(board["slots"].values(), key=lambda s: s["shot_n"])
    return {"slots": slots, "summary": summary(board)}


def _slot(board: dict, shot_n: int) -> dict:
    slot = board["slots"].get(str(shot_n))
    if slot is None:
        raise AssetError(f"There is no scene {shot_n} in this project.")
    return slot


def _media(name: str) -> str:
    media = MEDIA_TYPES.get(Path(name).suffix.lower())
    if not media:
        raise AssetError("Use a .mp4, .mov, .webm, .png, .jpg or .gif file.")
    return media


def _copy_limited(source: BinaryIO, target: Path) -> int:
    size = 0
    with open(target, "wb") as out:
        while chunk := source.read(1024 * 1024):
            size += len(chunk)
            if size > MAX_BYTES:
                out.close()
                target.unlink(missing_ok=True)
                raise AssetError("That file is larger than 4 GB.")
            out.write(chunk)
    if size == 0:
        target.unlink(missing_ok=True)
        raise AssetError("That file is empty.")
    return size


def attach_file(project_id: str, shot_n: int, filename: str, source: BinaryIO, save_to_library: bool = False) -> dict:
    """Import a local file into the project and link it to a scene."""
    board = load(project_id)
    slot = _slot(board, shot_n)
    media = _media(filename)
    folder = projects.project_dir(project_id) / "assets"
    folder.mkdir(exist_ok=True)
    target = store.unique_path(folder, f"shot_{shot_n:02d}_{store.safe_name(filename, 'asset')}")
    _copy_limited(source, target)
    slot.update(file=f"assets/{target.name}", media=media, source="upload", status="ready",
                original_name=Path(filename.replace("\\", "/")).name)
    if save_to_library:
        entry = library_add(target, slot["original_name"], project_id, slot["what"])
        slot["library_id"] = entry["id"]
    _save(project_id, board)
    return board


def set_status(project_id: str, shot_n: int, status: str) -> dict:
    if status not in ("ready", "needs_replacement"):
        raise AssetError("Status must be 'ready' or 'needs_replacement'.")
    board = load(project_id)
    slot = _slot(board, shot_n)
    if not slot["file"]:
        raise AssetError("Add a file to this scene first.")
    slot["status"] = status
    _save(project_id, board)
    return board


def clear(project_id: str, shot_n: int) -> dict:
    """Unlink a scene's file. Imported files stay on disk in assets/; charts are re-linked."""
    board = load(project_id)
    project = projects.load(project_id)
    shot = next(s for s in project["shots"] if s["n"] == shot_n)
    board["slots"][str(shot_n)] = _new_slot(shot)
    _save(project_id, board)
    return board


# ---------------------------------------------------------------- reusable library
def library_dir() -> Path:
    path = config.assets_dir() / "library"
    path.mkdir(parents=True, exist_ok=True)
    return path


def library_list() -> list[dict]:
    items = store.read_json(library_dir() / LIBRARY_INDEX, [])
    return [i for i in items if (library_dir() / i["file"]).is_file()]


def library_add(source: Path, name: str, from_project: str = "", note: str = "") -> dict:
    media = _media(name)
    target = store.unique_path(library_dir(), store.safe_name(name, "asset"))
    shutil.copyfile(source, target)
    items = library_list()
    entry = {"id": target.name, "name": name, "file": target.name, "media": media, "note": note,
             "from_project": from_project, "added": store.now_iso()}
    items.append(entry)
    store.write_json(library_dir() / LIBRARY_INDEX, items)
    return entry


def library_file(file_id: str) -> Path:
    """A library file by id, refusing anything outside the library folder."""
    for item in library_list():
        if item["id"] == file_id:
            return library_dir() / item["file"]
    raise FileNotFoundError(file_id)


def library_remove(file_id: str) -> list[dict]:
    path = library_file(file_id)
    path.unlink(missing_ok=True)
    items = [i for i in library_list() if i["id"] != file_id]
    store.write_json(library_dir() / LIBRARY_INDEX, items)
    return items


def assign_from_library(project_id: str, shot_n: int, file_id: str) -> dict:
    """Copy a library asset into this project and link it to a scene (the ZIP stays self-contained)."""
    try:
        source = library_file(file_id)
    except FileNotFoundError:
        raise AssetError("That library item no longer exists.") from None
    board = load(project_id)
    slot = _slot(board, shot_n)
    folder = projects.project_dir(project_id) / "assets"
    folder.mkdir(exist_ok=True)
    target = store.unique_path(folder, f"shot_{shot_n:02d}_{source.name}")
    shutil.copyfile(source, target)
    slot.update(file=f"assets/{target.name}", media=_media(source.name), source="library", status="ready",
                original_name=source.name, library_id=file_id)
    _save(project_id, board)
    return board

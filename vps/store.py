"""Small JSON file helpers shared by the studio features."""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path


def read_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def write_json(path: Path, data) -> None:
    """Write via a temp file so a crash never leaves a half-written file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def safe_name(name: str, fallback: str = "file") -> str:
    """A file name with no folders and only plain characters; keeps the extension."""
    name = Path(name.replace("\\", "/")).name
    stem, dot, ext = name.rpartition(".")
    if not dot:
        stem, ext = name, ""
    stem = re.sub(r"[^A-Za-z0-9_-]+", "-", stem).strip("-")[:60] or fallback
    ext = re.sub(r"[^A-Za-z0-9]", "", ext).lower()[:8]
    return f"{stem}.{ext}" if ext else stem


def unique_path(folder: Path, name: str) -> Path:
    """folder/name, or folder/name-2.ext etc. if that already exists."""
    path = folder / name
    stem, suffix, n = path.stem, path.suffix, 2
    while path.exists():
        path = folder / f"{stem}-{n}{suffix}"
        n += 1
    return path

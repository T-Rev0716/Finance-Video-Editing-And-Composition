"""Paths and settings. Secrets live in .env only - nothing is hard-coded."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import dotenv_values, set_key

ROOT = Path(__file__).resolve().parent.parent

DEFAULT_DISCLAIMER = (
    "This video is for education and commentary only. It is not investment, tax or legal "
    "advice, and nothing in it is a recommendation to buy or sell any security. I am not a "
    "licensed financial advisor. Past performance does not guarantee future results. "
    "Talk to a licensed professional about your own situation."
)

DEFAULT_RADAR_DIR = r"C:\Users\T-Rev\OpenBot\Shared\Council-of-the-Future\topic-radar\reports"

# key -> (default, is_secret)
SETTING_KEYS: dict[str, tuple[str, bool]] = {
    "FRED_API_KEY": ("", True),
    "ANTHROPIC_API_KEY": ("", True),
    "ANTHROPIC_MODEL": ("claude-opus-5-5", False),
    "BLS_API_KEY": ("", True),
    "SEC_CONTACT": ("", False),
    "CHART_THEME": ("dark", False),
    "CHANNEL_NAME": ("", False),
    "DISCLAIMER": (DEFAULT_DISCLAIMER, False),
    # Wording engine: auto = Anthropic if a key is saved, else built-in templates.
    # "ollama" uses a model running on this computer (free); "templates" never calls a model.
    "LLM_PROVIDER": ("auto", False),
    "OLLAMA_URL": ("http://127.0.0.1:11434", False),
    "OLLAMA_MODEL": ("", False),  # blank = first installed model with "qwen" in its name, else the first one
    "WHISPER_MODEL": ("auto", False),  # auto = large-v3 on an NVIDIA GPU, small on CPU
    "RADAR_REPORTS_DIR": (DEFAULT_RADAR_DIR, False),
}


def _dir(env_name: str, default: Path) -> Path:
    value = os.environ.get(env_name)
    return Path(value) if value else default


def reports_dir() -> Path:
    return _dir("VPS_REPORTS_DIR", ROOT / "reports")


def projects_dir() -> Path:
    path = _dir("VPS_PROJECTS_DIR", ROOT / "projects")
    path.mkdir(parents=True, exist_ok=True)
    return path


def cache_dir() -> Path:
    path = _dir("VPS_CACHE_DIR", ROOT / ".cache")
    path.mkdir(parents=True, exist_ok=True)
    return path


def assets_dir() -> Path:
    """Things reused across episodes: presenter photos, the B-roll library, thumbnail presets."""
    path = _dir("VPS_ASSETS_DIR", ROOT / "assets")
    path.mkdir(parents=True, exist_ok=True)
    return path


def user_data_dir() -> Path:
    """Cross-project records the app writes (the learning log index)."""
    path = _dir("VPS_USER_DATA_DIR", ROOT / "data")
    path.mkdir(parents=True, exist_ok=True)
    return path


def env_path() -> Path:
    return _dir("VPS_ENV_FILE", ROOT / ".env")


def load_settings() -> dict[str, str]:
    """Settings from .env. Real environment variables are a fallback, never the reverse,
    so what the Settings page shows is what the app uses."""
    file_values = dotenv_values(env_path()) if env_path().exists() else {}
    settings: dict[str, str] = {}
    for key, (default, secret) in SETTING_KEYS.items():
        value = file_values.get(key)
        if not value:
            # API keys are read from .env only; plain options may also come from the environment.
            value = default if secret else os.environ.get(key, default)
        settings[key] = value
    return settings


def save_settings(updates: dict[str, str]) -> None:
    path = env_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text("", encoding="utf-8")
    for key, value in updates.items():
        if key not in SETTING_KEYS:
            continue
        set_key(str(path), key, (value or "").strip(), quote_mode="always")


def public_settings() -> dict[str, dict]:
    """What the browser may see: secrets are reduced to set/unset plus the last 4 chars."""
    out: dict[str, dict] = {}
    for key, value in load_settings().items():
        secret = SETTING_KEYS[key][1]
        if secret:
            out[key] = {"secret": True, "set": bool(value), "hint": ("..." + value[-4:]) if len(value) >= 8 else ""}
        else:
            out[key] = {"secret": False, "value": value}
    return out

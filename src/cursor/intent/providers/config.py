"""Provider configuration from environment / `.env`.

OpenAI API only:

    OPENAI_API_KEY / OPENAI_KEY
    ASR_PROVIDER=openai
    ASR_MODEL=whisper-1
    ASR_BASE_URL=https://api.openai.com/v1
    LLM_PROVIDER=openai
    LLM_MODEL=gpt-4o-mini
    LLM_BASE_URL=https://api.openai.com/v1
    LLM_TEMPERATURE=1
"""

from __future__ import annotations

import os
from pathlib import Path

# Repo root (…/cursor-predict) so `.env` resolves next to pyproject.toml.
PROJECT = Path(__file__).resolve().parents[4]

_DEFAULTS = {
    "ASR_PROVIDER": "openai",
    "ASR_MODEL": "whisper-1",
    "ASR_BASE_URL": "https://api.openai.com/v1",
    "LLM_PROVIDER": "openai",
    "LLM_MODEL": "gpt-4o-mini",
    "LLM_BASE_URL": "https://api.openai.com/v1",
    "LLM_TEMPERATURE": "1",
}

_dotenv_loaded = False


def _load_dotenv():
    """Minimal .env loader (KEY=VALUE lines); real env vars win."""
    global _dotenv_loaded
    if _dotenv_loaded:
        return
    _dotenv_loaded = True
    env_file = PROJECT / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k, v = k.strip(), v.strip().strip("'\"")
        if k and k not in os.environ:
            os.environ[k] = v


def get(key: str, default: str | None = None) -> str | None:
    _load_dotenv()
    return os.environ.get(key, _DEFAULTS.get(key, default))


def api_key() -> str | None:
    _load_dotenv()
    return os.environ.get("OPENAI_API_KEY") or os.environ.get("OPENAI_KEY")

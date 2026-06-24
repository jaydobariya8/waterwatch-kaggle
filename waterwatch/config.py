"""Runtime configuration, sourced entirely from environment variables.

Secrets (API keys) never live in code — they are read from the environment at runtime,
mirroring the Secret Manager design described in the project plan. Every setting has a
safe default so the system runs fully offline with zero configuration.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
FRONTEND_DIR = BASE_DIR.parent / "frontend"


def _env(*names: str, default: str | None = None) -> str | None:
    """Return the first set environment variable among ``names``."""
    for name in names:
        value = os.environ.get(name)
        if value:
            return value
    return default


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    """Immutable application settings."""

    app_name: str = "WaterWatch"
    version: str = "1.0.0"

    # --- Gemini / Vertex AI ---------------------------------------------------
    # When a key is present the LLM-backed agents (parser, health phrasing, complaint
    # drafting) use Gemini. When absent, deterministic engines run instead so the
    # whole pipeline still works end-to-end with no external dependency.
    gemini_api_key: str | None = field(
        default_factory=lambda: _env("GEMINI_API_KEY", "GOOGLE_API_KEY")
    )
    gemini_model_pro: str = field(
        default_factory=lambda: _env("GEMINI_MODEL_PRO", default="gemini-2.5-pro") or "gemini-2.5-pro"
    )
    gemini_model_flash: str = field(
        default_factory=lambda: _env("GEMINI_MODEL_FLASH", default="gemini-2.5-flash") or "gemini-2.5-flash"
    )

    # --- External civic data (data.gov.in / CPCB) -----------------------------
    data_gov_api_key: str | None = field(default_factory=lambda: _env("DATA_GOV_API_KEY"))

    # --- State / memory -------------------------------------------------------
    # "local" uses a JSON file (zero-setup); "firestore" uses Google Firestore.
    store_backend: str = field(
        default_factory=lambda: _env("STORE_BACKEND", default="local") or "local"
    )
    firestore_project: str | None = field(
        default_factory=lambda: _env("FIRESTORE_PROJECT", "GOOGLE_CLOUD_PROJECT")
    )
    local_store_path: Path = field(
        default_factory=lambda: Path(
            _env(
                "WATERWATCH_STORE_PATH",
                default=str(BASE_DIR.parent / ".waterwatch_store.json"),
            )
            or str(BASE_DIR.parent / ".waterwatch_store.json")
        )
    )

    # --- Watchdog / civic policy ---------------------------------------------
    escalation_days: int = field(default_factory=lambda: _env_int("ESCALATION_DAYS", 14))
    cluster_threshold: int = field(default_factory=lambda: _env_int("CLUSTER_THRESHOLD", 3))

    # --- Web / CORS -----------------------------------------------------------
    cors_origins: tuple[str, ...] = field(
        default_factory=lambda: tuple(
            o.strip()
            for o in (_env("CORS_ORIGINS", default="*") or "*").split(",")
            if o.strip()
        )
    )

    log_level: str = field(default_factory=lambda: _env("LOG_LEVEL", default="INFO") or "INFO")

    @property
    def llm_enabled(self) -> bool:
        return bool(self.gemini_api_key)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a process-wide cached :class:`Settings` instance."""
    return Settings()

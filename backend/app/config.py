"""Application settings, read from environment variables and the repo-root .env file.

This is the only Python module that names Gemini models. Everything else must
call `get_settings()` instead of reading os.environ directly.
"""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# backend/app/config.py -> parents[2] is the repo root.
REPO_ROOT: Path = Path(__file__).resolve().parents[2]
ENV_PATH: Path = REPO_ROOT / ".env"

_TRUE_VALUES = {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    """All configuration for the backend. Secrets live here and nowhere else."""

    gemini_api_key: str
    gemini_model: str
    gemini_fallback_model: str
    gemini_tts_model: str
    nessie_base_url: str
    nessie_api_key: str
    nessie_customer_id: str
    nessie_account_id: str
    # Our own seeded merchants (utility, clinic, landlord). Nessie's merchant list is
    # shared by every hackathon team, so policy must only trust these ids.
    nessie_merchant_ids: tuple[str, ...]
    seed_balance_cents: int
    mongodb_uri: str
    demo_offline: bool
    token_secret: str


def _env(name: str, default: str = "") -> str:
    """Read one variable, trimmed. An empty value falls back to the default."""
    value = os.environ.get(name, "").strip()
    return value or default


def _env_bool(name: str) -> bool:
    """True for "1", "true", "yes" or "on" (any letter case); False otherwise."""
    return _env(name).lower() in _TRUE_VALUES


def _env_int(name: str, default: int) -> int:
    """Read a whole number, with a clear error if the value is not one."""
    raw = _env(name)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        raise ValueError(f"{name} must be a whole number, got {raw!r}") from None


def get_settings() -> Settings:
    """Build Settings from the environment.

    The .env file is loaded first, but it never overrides variables that are
    already set. os.environ is read on every call, so tests can monkeypatch it.
    """
    load_dotenv(ENV_PATH, override=False)
    return Settings(
        gemini_api_key=_env("GEMINI_API_KEY"),
        gemini_model=_env("GEMINI_MODEL", "gemini-3.8-flash"),
        gemini_fallback_model=_env("GEMINI_FALLBACK_MODEL", "gemini-3.5-flash-lite"),
        gemini_tts_model=_env("GEMINI_TTS_MODEL", "gemini-3.8-flash-tts"),
        nessie_base_url=_env("NESSIE_BASE_URL", "https://api.nessieisreal.com"),
        nessie_api_key=_env("NESSIE_API_KEY"),
        nessie_customer_id=_env("NESSIE_CUSTOMER_ID"),
        nessie_account_id=_env("NESSIE_ACCOUNT_ID"),
        nessie_merchant_ids=tuple(
            part.strip() for part in _env("NESSIE_MERCHANT_IDS").split(",") if part.strip()
        ),
        seed_balance_cents=_env_int("SEED_BALANCE_CENTS", 200000),
        mongodb_uri=_env("MONGODB_URI"),
        demo_offline=_env_bool("DEMO_OFFLINE"),
        token_secret=_env("TOKEN_SECRET"),
    )

"""Central configuration for VAuth backend (env-driven, safe defaults)."""
from __future__ import annotations

import os
from functools import lru_cache

from pydantic import BaseModel


def _getenv(key: str, default: str = "") -> str:
    return os.environ.get(key, default)


def _getenv_float(key: str, default: float) -> float:
    try:
        return float(os.environ.get(key, str(default)))
    except ValueError:
        return default


def _getenv_int(key: str, default: int) -> int:
    try:
        return int(os.environ.get(key, str(default)))
    except ValueError:
        return default


def _getenv_bool(key: str, default: bool) -> bool:
    raw = os.environ.get(key, str(default)).strip().lower()
    return raw in ("1", "true", "yes", "on")


class Settings(BaseModel):
    app_name: str = "VAuth"
    version: str = "0.1.0"
    environment: str = _getenv("VAUTH_ENV", "development")

    # Audio pipeline
    target_sample_rate: int = _getenv_int("VAUTH_TARGET_SR", 16000)
    window_seconds: float = _getenv_float("VAUTH_WINDOW_SECONDS", 2.5)
    min_window_seconds: float = _getenv_float("VAUTH_MIN_WINDOW_SECONDS", 1.0)
    max_audio_seconds: float = _getenv_float("VAUTH_MAX_AUDIO_SECONDS", 30.0)
    max_upload_bytes: int = _getenv_int("VAUTH_MAX_UPLOAD_BYTES", 10 * 1024 * 1024)
    max_ws_bytes: int = _getenv_int("VAUTH_MAX_WS_BYTES", 2 * 1024 * 1024)

    # Risk engine
    rolling_window_size: int = _getenv_int("VAUTH_ROLLING_SIZE", 5)
    green_threshold: float = _getenv_float("VAUTH_GREEN_T", 0.60)
    yellow_threshold: float = _getenv_float("VAUTH_YELLOW_T", 0.75)
    orange_threshold: float = _getenv_float("VAUTH_ORANGE_T", 0.90)

    # Model selection: demo | ml(=torch AASIST) | aasist | spectra | spectra3 | w2v2_aasist
    detector: str = _getenv("VAUTH_DETECTOR", "demo")
    model_path: str = _getenv("VAUTH_MODEL_PATH", "models/AASIST.pth")
    model_device: str = _getenv("VAUTH_DEVICE", "cpu")
    calibration_path: str = _getenv("VAUTH_CALIBRATION_PATH", "models/calibration.json")

    # Privacy: never store raw audio by default
    store_raw_audio: bool = _getenv_bool("VAUTH_STORE_RAW_AUDIO", False)

    # CORS
    cors_origins: str = _getenv("VAUTH_CORS_ORIGINS", "*")

    # Twilio (optional, never required for local demo)
    twilio_account_sid: str = _getenv("TWILIO_ACCOUNT_SID", "")
    twilio_auth_token: str = _getenv("TWILIO_AUTH_TOKEN", "")
    twilio_phone_number: str = _getenv("TWILIO_PHONE_NUMBER", "")

    # Vonage Voice API (optional input adapter; disabled by default).
    # Never required for local/demo usage; missing config never breaks startup.
    vonage_enabled: bool = _getenv_bool("VONAGE_ENABLED", False)
    vonage_public_ws_host: str = _getenv("VONAGE_PUBLIC_WS_HOST", "")
    vonage_application_id: str = _getenv("VONAGE_APPLICATION_ID", "")
    vonage_private_key_path: str = _getenv("VONAGE_PRIVATE_KEY_PATH", "")
    vonage_number: str = _getenv("VONAGE_NUMBER", "")
    vonage_verify_jwt: bool = _getenv_bool("VONAGE_VERIFY_JWT", True)
    vonage_ws_auth_token: str = _getenv("VONAGE_WS_AUTH_TOKEN", "")

    # History
    history_limit: int = _getenv_int("VAUTH_HISTORY_LIMIT", 200)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()

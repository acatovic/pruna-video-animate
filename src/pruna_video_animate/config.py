from __future__ import annotations

import os

from dotenv import load_dotenv

from .errors import PrunaAuthError

BASE_URL = "https://api.pruna.ai/v1"

DEFAULT_RESOLUTION = "720p"
DEFAULT_TARGET_FPS = "original"
DEFAULT_SAVE_AUDIO = True
DEFAULT_INSTRUCTION_PROMPT = (
    "Animate the reference subject using the motion from the source video."
)

POLL_INITIAL_SECONDS = 2.0
POLL_MAX_SECONDS = 10.0
POLL_TIMEOUT_SECONDS = 30 * 60.0

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
VIDEO_EXTENSIONS = {".mp4"}


def get_api_key() -> str:
    load_dotenv()
    api_key = os.getenv("PRUNA_API_KEY")
    if not api_key:
        raise PrunaAuthError("Missing PRUNA_API_KEY. Set it in the environment or .env.")
    return api_key

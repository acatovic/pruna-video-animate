from __future__ import annotations

import os
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from .config import (
    BASE_URL,
    DEFAULT_INSTRUCTION_PROMPT,
    DEFAULT_RESOLUTION,
    DEFAULT_SAVE_AUDIO,
    DEFAULT_TARGET_FPS,
    IMAGE_EXTENSIONS,
    POLL_INITIAL_SECONDS,
    POLL_MAX_SECONDS,
    POLL_TIMEOUT_SECONDS,
    VIDEO_EXTENSIONS,
    get_api_key,
)
from .errors import (
    PrunaDownloadError,
    PrunaError,
    PrunaPredictionError,
    PrunaTimeoutError,
    PrunaUploadError,
)

ProgressCallback = Callable[[str], None]
SleepCallable = Callable[[float], None]
ClockCallable = Callable[[], float]

IN_PROGRESS_STATUSES = {"starting", "processing", "queued", "pending"}
FAILURE_STATUSES = {"failed", "canceled", "cancelled", "error"}


class PrunaClient:
    def __init__(
        self,
        api_key: str | None = None,
        *,
        base_url: str = BASE_URL,
        http_client: httpx.Client | None = None,
        timeout_seconds: float = 60.0,
        poll_initial_seconds: float = POLL_INITIAL_SECONDS,
        poll_max_seconds: float = POLL_MAX_SECONDS,
        poll_timeout_seconds: float = POLL_TIMEOUT_SECONDS,
        sleep: SleepCallable = time.sleep,
        monotonic: ClockCallable = time.monotonic,
    ) -> None:
        self.api_key = api_key if api_key is not None else get_api_key()
        self.base_url = base_url.rstrip("/")
        self.poll_initial_seconds = poll_initial_seconds
        self.poll_max_seconds = poll_max_seconds
        self.poll_timeout_seconds = poll_timeout_seconds
        self.sleep = sleep
        self.monotonic = monotonic
        self._client = http_client or httpx.Client(timeout=timeout_seconds)
        self._owns_client = http_client is None

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> PrunaClient:
        return self

    def __exit__(self, *_exc_info: object) -> None:
        self.close()

    def upload_file(self, path: Path) -> str:
        path = Path(path)
        if not path.is_file():
            raise PrunaUploadError(f"Input file does not exist: {path}")

        with path.open("rb") as file_handle:
            response = self._client.post(
                f"{self.base_url}/files",
                headers=self._headers(),
                files={"content": (path.name, file_handle)},
            )

        self._raise_for_status(response, PrunaUploadError, "File upload failed")
        payload = self._json(response, PrunaUploadError, "Upload response was not JSON")
        file_url = payload.get("urls", {}).get("get")
        if not file_url:
            raise PrunaUploadError("Upload response missing urls.get")
        return str(file_url)

    def create_animation_prediction(
        self,
        video_url: str,
        image_url: str,
        *,
        resolution: str = DEFAULT_RESOLUTION,
        target_fps: str = DEFAULT_TARGET_FPS,
        save_audio: bool = DEFAULT_SAVE_AUDIO,
        instruction_prompt: str = DEFAULT_INSTRUCTION_PROMPT,
        seed: int | None = None,
    ) -> str:
        prediction_input: dict[str, Any] = {
            "video": video_url,
            "image": image_url,
            "resolution": resolution,
            "target_fps": target_fps,
            "save_audio": save_audio,
            "instruction_prompt": instruction_prompt,
        }
        if seed is not None:
            prediction_input["seed"] = seed

        response = self._client.post(
            f"{self.base_url}/predictions",
            headers=self._headers({"Model": "p-video-animate", "Content-Type": "application/json"}),
            json={"input": prediction_input},
        )

        self._raise_for_status(
            response,
            PrunaPredictionError,
            "Prediction creation failed",
        )
        payload = self._json(
            response,
            PrunaPredictionError,
            "Prediction creation response was not JSON",
        )

        get_url = payload.get("get_url")
        if get_url:
            return str(get_url)

        prediction_id = payload.get("id")
        if prediction_id:
            return f"{self.base_url}/predictions/status/{prediction_id}"

        raise PrunaPredictionError("Prediction response missing both get_url and id")

    def poll_until_complete(
        self,
        status_url: str,
        *,
        on_status: ProgressCallback | None = None,
    ) -> str:
        started_at = self.monotonic()
        delay = self.poll_initial_seconds
        last_status = "unknown"

        while True:
            response = self._client.get(status_url, headers=self._headers())
            self._raise_for_status(response, PrunaPredictionError, "Status polling failed")
            payload = self._json(
                response,
                PrunaPredictionError,
                "Status response was not JSON",
            )

            raw_status = payload.get("status")
            if not raw_status:
                raise PrunaPredictionError("Status response missing status")

            status = str(raw_status).lower()
            last_status = status
            if on_status is not None:
                on_status(status)

            if status == "succeeded":
                generation_url = payload.get("generation_url")
                if not generation_url:
                    raise PrunaPredictionError("Prediction succeeded without generation_url")
                return str(generation_url)

            if status in FAILURE_STATUSES:
                detail = self._status_detail(payload)
                raise PrunaPredictionError(f"Prediction {status}: {detail}")

            if status not in IN_PROGRESS_STATUSES:
                raise PrunaPredictionError(f"Unexpected prediction status: {status}")

            elapsed = self.monotonic() - started_at
            remaining = self.poll_timeout_seconds - elapsed
            if remaining <= 0:
                raise PrunaTimeoutError(
                    f"Timed out after {self.poll_timeout_seconds:g}s waiting for prediction. "
                    f"Last status: {last_status}"
                )

            sleep_seconds = min(delay, remaining)
            self.sleep(sleep_seconds)
            delay = min(delay * 1.5, self.poll_max_seconds)

    def download_file(self, url: str, output_path: Path) -> Path:
        output_path = Path(output_path)
        if output_path.suffix.lower() != ".mp4":
            raise PrunaDownloadError(f"Output path must end with .mp4: {output_path}")

        output_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = output_path.with_name(f"{output_path.name}.tmp")
        url_looks_mp4 = urlparse(url).path.lower().endswith(".mp4")
        first_bytes = bytearray()
        bytes_written = 0
        content_type = ""

        try:
            with self._client.stream("GET", url, headers=self._headers()) as response:
                self._raise_for_status(response, PrunaDownloadError, "MP4 download failed")
                content_type = response.headers.get("content-type", "").lower()

                with tmp_path.open("wb") as file_handle:
                    for chunk in response.iter_bytes():
                        if not chunk:
                            continue
                        if len(first_bytes) < 16:
                            first_bytes.extend(chunk[: 16 - len(first_bytes)])
                        file_handle.write(chunk)
                        bytes_written += len(chunk)

            if bytes_written == 0:
                raise PrunaDownloadError("Downloaded MP4 response was empty")

            content_type_ok = not content_type or "mp4" in content_type or "octet-stream" in content_type
            header_looks_mp4 = len(first_bytes) >= 8 and bytes(first_bytes[4:8]) == b"ftyp"
            if not content_type_ok:
                raise PrunaDownloadError(f"Download did not return MP4 content-type: {content_type}")
            if not (url_looks_mp4 or header_looks_mp4 or "mp4" in content_type):
                raise PrunaDownloadError("Downloaded output does not look like an MP4")

            os.replace(tmp_path, output_path)
            return output_path
        except PrunaError:
            tmp_path.unlink(missing_ok=True)
            raise
        except httpx.HTTPError as exc:
            tmp_path.unlink(missing_ok=True)
            raise PrunaDownloadError(f"MP4 download failed: {exc}") from exc

    def _headers(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        headers = {"apikey": self.api_key}
        if extra:
            headers.update(extra)
        return headers

    @staticmethod
    def _json(response: httpx.Response, error_type: type[PrunaError], message: str) -> dict[str, Any]:
        try:
            payload = response.json()
        except ValueError as exc:
            raise error_type(message) from exc
        if not isinstance(payload, dict):
            raise error_type(message)
        return payload

    @staticmethod
    def _raise_for_status(
        response: httpx.Response,
        error_type: type[PrunaError],
        message: str,
    ) -> None:
        if response.status_code < 400:
            return
        try:
            excerpt = response.text[:300].replace("\n", " ")
        except httpx.ResponseNotRead:
            excerpt = response.read().decode("utf-8", errors="replace")[:300].replace("\n", " ")
        raise error_type(f"{message}: HTTP {response.status_code}. {excerpt}")

    @staticmethod
    def _status_detail(payload: dict[str, Any]) -> str:
        parts = [str(payload[field]) for field in ("message", "error") if payload.get(field)]
        return " | ".join(parts) if parts else "No error detail provided"


def animate_image_with_reference_video(
    image_path: Path,
    video_path: Path,
    output_path: Path | None = None,
    *,
    progress: ProgressCallback | None = None,
    client: PrunaClient | None = None,
) -> Path:
    image_path = Path(image_path)
    video_path = Path(video_path)
    output_path = Path(output_path) if output_path is not None else default_output_path()

    _validate_image_path(image_path)
    _validate_video_path(video_path)

    owns_client = client is None
    pruna_client = client or PrunaClient()

    try:
        _progress(progress, "Uploading reference video...")
        video_url = pruna_client.upload_file(video_path)

        _progress(progress, "Uploading reference image...")
        image_url = pruna_client.upload_file(image_path)

        _progress(progress, "Creating animation job...")
        status_url = pruna_client.create_animation_prediction(
            video_url=video_url,
            image_url=image_url,
        )

        _progress(progress, "Polling prediction status...")
        generation_url = pruna_client.poll_until_complete(
            status_url,
            on_status=lambda status: _progress(progress, f"Status: {status}"),
        )

        saved_path = pruna_client.download_file(generation_url, output_path)
        _progress(progress, "Animation complete.")
        _progress(progress, f"Saved MP4: {saved_path}")
        return saved_path
    finally:
        if owns_client:
            pruna_client.close()


def default_output_path() -> Path:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return Path(f"animated-{timestamp}.mp4")


def _validate_image_path(path: Path) -> None:
    if not path.is_file():
        raise PrunaUploadError(f"Reference image does not exist: {path}")
    if path.suffix.lower() not in IMAGE_EXTENSIONS:
        allowed = ", ".join(sorted(IMAGE_EXTENSIONS))
        raise PrunaUploadError(f"Unsupported reference image extension {path.suffix!r}. Use one of: {allowed}")


def _validate_video_path(path: Path) -> None:
    if not path.is_file():
        raise PrunaUploadError(f"Reference video does not exist: {path}")
    if path.suffix.lower() not in VIDEO_EXTENSIONS:
        allowed = ", ".join(sorted(VIDEO_EXTENSIONS))
        raise PrunaUploadError(f"Unsupported reference video extension {path.suffix!r}. Use one of: {allowed}")


def _progress(progress: ProgressCallback | None, message: str) -> None:
    if progress is not None:
        progress(message)

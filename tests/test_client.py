from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
import respx

from pruna_video_animate.client import PrunaClient
from pruna_video_animate.errors import (
    PrunaDownloadError,
    PrunaPredictionError,
    PrunaTimeoutError,
)

BASE_URL = "https://api.pruna.ai/v1"


def make_client(**kwargs: object) -> PrunaClient:
    return PrunaClient(api_key="test-key", sleep=lambda _seconds: None, **kwargs)


@respx.mock
def test_upload_video_returns_get_url(tmp_path: Path) -> None:
    video_path = tmp_path / "reference.mp4"
    video_path.write_bytes(b"video")
    route = respx.post(f"{BASE_URL}/files").mock(
        return_value=httpx.Response(200, json={"id": "file-video", "urls": {"get": "https://api.pruna.ai/v1/files/file-video"}})
    )

    file_url = make_client().upload_file(video_path)

    assert file_url == "https://api.pruna.ai/v1/files/file-video"
    assert route.called
    assert route.calls[0].request.headers["apikey"] == "test-key"


@respx.mock
def test_upload_image_returns_get_url(tmp_path: Path) -> None:
    image_path = tmp_path / "reference.png"
    image_path.write_bytes(b"image")
    respx.post(f"{BASE_URL}/files").mock(
        return_value=httpx.Response(200, json={"id": "file-image", "urls": {"get": "https://api.pruna.ai/v1/files/file-image"}})
    )

    file_url = make_client().upload_file(image_path)

    assert file_url == "https://api.pruna.ai/v1/files/file-image"


@respx.mock
def test_prediction_creation_sends_model_header_async_payload_and_keeps_video_image_order() -> None:
    route = respx.post(f"{BASE_URL}/predictions").mock(
        return_value=httpx.Response(200, json={"get_url": f"{BASE_URL}/predictions/status/prediction-id"})
    )

    status_url = make_client().create_animation_prediction(
        video_url="https://api.pruna.ai/v1/files/video-file",
        image_url="https://api.pruna.ai/v1/files/image-file",
    )

    request = route.calls[0].request
    payload = json.loads(request.content)
    assert status_url == f"{BASE_URL}/predictions/status/prediction-id"
    assert request.headers["Model"] == "p-video-animate"
    assert request.headers["Content-Type"].startswith("application/json")
    assert "Try-Sync" not in request.headers
    assert payload["input"]["video"] == "https://api.pruna.ai/v1/files/video-file"
    assert payload["input"]["image"] == "https://api.pruna.ai/v1/files/image-file"
    assert payload["input"]["resolution"] == "720p"
    assert payload["input"]["target_fps"] == "original"
    assert payload["input"]["save_audio"] is True


@respx.mock
def test_prediction_creation_constructs_status_url_from_id() -> None:
    respx.post(f"{BASE_URL}/predictions").mock(
        return_value=httpx.Response(200, json={"id": "prediction-id"})
    )

    status_url = make_client().create_animation_prediction(
        video_url="video-url",
        image_url="image-url",
    )

    assert status_url == f"{BASE_URL}/predictions/status/prediction-id"


@respx.mock
def test_polling_handles_starting_processing_then_succeeded() -> None:
    status_url = f"{BASE_URL}/predictions/status/prediction-id"
    generation_url = f"{BASE_URL}/predictions/delivery/prediction-id/output.mp4"
    respx.get(status_url).mock(
        side_effect=[
            httpx.Response(200, json={"status": "starting", "message": "Generation in progress"}),
            httpx.Response(200, json={"status": "processing", "message": "Generation in progress"}),
            httpx.Response(200, json={"status": "succeeded", "generation_url": generation_url}),
        ]
    )
    statuses: list[str] = []

    result = make_client().poll_until_complete(status_url, on_status=statuses.append)

    assert result == generation_url
    assert statuses == ["starting", "processing", "succeeded"]


@respx.mock
def test_polling_raises_on_failed_status() -> None:
    status_url = f"{BASE_URL}/predictions/status/prediction-id"
    respx.get(status_url).mock(
        return_value=httpx.Response(
            200,
            json={"status": "failed", "message": "Prediction failed", "error": "bad input"},
        )
    )

    with pytest.raises(PrunaPredictionError, match="Prediction failed.*bad input"):
        make_client().poll_until_complete(status_url)


@respx.mock
def test_polling_times_out() -> None:
    status_url = f"{BASE_URL}/predictions/status/prediction-id"
    respx.get(status_url).mock(
        return_value=httpx.Response(200, json={"status": "processing", "message": "Generation in progress"})
    )

    with pytest.raises(PrunaTimeoutError, match="Last status: processing"):
        make_client(poll_timeout_seconds=0).poll_until_complete(status_url)


@respx.mock
def test_download_writes_mp4_file(tmp_path: Path) -> None:
    generation_url = f"{BASE_URL}/predictions/delivery/prediction-id/output.mp4"
    output_path = tmp_path / "animated.mp4"
    mp4_bytes = b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00"
    route = respx.get(generation_url).mock(
        return_value=httpx.Response(200, headers={"content-type": "video/mp4"}, content=mp4_bytes)
    )

    saved_path = make_client().download_file(generation_url, output_path)

    assert saved_path == output_path
    assert output_path.read_bytes() == mp4_bytes
    assert route.calls[0].request.headers["apikey"] == "test-key"


@respx.mock
def test_download_rejects_non_mp4_output_path(tmp_path: Path) -> None:
    with pytest.raises(PrunaDownloadError, match="must end with .mp4"):
        make_client().download_file("https://example.test/output.mp4", tmp_path / "animated.mov")

from __future__ import annotations

from pathlib import Path

import pytest

from pruna_video_animate import cli


def test_cli_accepts_image_video_and_optional_output(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    image_path = tmp_path / "reference.png"
    video_path = tmp_path / "reference.mp4"
    output_path = tmp_path / "animated.mp4"
    image_path.write_bytes(b"image")
    video_path.write_bytes(b"video")
    calls: list[dict[str, Path | object]] = []

    def fake_animate_image_with_reference_video(
        *,
        image_path: Path,
        video_path: Path,
        output_path: Path | None,
        progress: object,
    ) -> Path:
        calls.append(
            {
                "image_path": image_path,
                "video_path": video_path,
                "output_path": output_path,
                "progress": progress,
            }
        )
        return output_path or tmp_path / "default.mp4"

    monkeypatch.setattr(
        cli,
        "animate_image_with_reference_video",
        fake_animate_image_with_reference_video,
    )

    exit_code = cli.main([str(image_path), str(video_path), "--output", str(output_path)])

    assert exit_code == 0
    assert calls == [
        {
            "image_path": image_path,
            "video_path": video_path,
            "output_path": output_path,
            "progress": print,
        }
    ]


def test_cli_rejects_unexpected_extra_argument(tmp_path: Path) -> None:
    image_path = tmp_path / "reference.png"
    video_path = tmp_path / "reference.mp4"

    with pytest.raises(SystemExit) as exc_info:
        cli.main([str(image_path), str(video_path), "extra"])

    assert exc_info.value.code == 2

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .client import animate_image_with_reference_video
from .errors import PrunaError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pruna-animate",
        description="Animate a local reference image using a local reference video through Pruna.",
    )
    parser.add_argument(
        "image_path",
        metavar="IMAGE_PATH",
        type=Path,
        help="Local reference subject image, e.g. .png, .jpg, .jpeg, .webp",
    )
    parser.add_argument(
        "video_path",
        metavar="VIDEO_PATH",
        type=Path,
        help="Local source motion/audio video, preferably .mp4",
    )
    parser.add_argument(
        "--output",
        dest="output_path",
        type=Path,
        default=None,
        help="Local MP4 path to write. Defaults to ./animated-<timestamp>.mp4",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        animate_image_with_reference_video(
            image_path=args.image_path,
            video_path=args.video_path,
            output_path=args.output_path,
            progress=print,
        )
    except PrunaError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    return 0


def run() -> None:
    raise SystemExit(main())

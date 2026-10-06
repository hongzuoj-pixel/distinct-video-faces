#!/usr/bin/env python3
"""Sample audit frames from a video using ffprobe and ffmpeg."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path


def probe_duration(video: Path) -> float:
    command = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(video),
    ]
    result = subprocess.run(command, check=True, capture_output=True, text=True)
    return float(result.stdout.strip())


def sample_times(duration: float, count: int) -> list[float]:
    if count < 3:
        raise ValueError("samples must be at least 3")
    margin = min(0.05, duration / 20)
    usable = max(0.0, duration - 2 * margin)
    return [round(margin + usable * index / (count - 1), 3) for index in range(count)]


def extract(video: Path, output: Path, times: list[float]) -> list[dict[str, object]]:
    output.mkdir(parents=True, exist_ok=True)
    frames: list[dict[str, object]] = []
    for index, timestamp in enumerate(times, start=1):
        filename = f"frame-{index:02d}-{timestamp:08.3f}s.jpg"
        destination = output / filename
        command = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-ss",
            str(timestamp),
            "-i",
            str(video),
            "-frames:v",
            "1",
            "-q:v",
            "2",
            "-y",
            str(destination),
        ]
        subprocess.run(command, check=True)
        frames.append({"index": index, "timestamp_seconds": timestamp, "file": filename})
    return frames


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video", type=Path)
    parser.add_argument("--out", type=Path, default=Path("audit-frames"))
    parser.add_argument("--samples", type=int, default=7)
    args = parser.parse_args()

    if not args.video.is_file():
        print(f"Video not found: {args.video}", file=sys.stderr)
        return 2
    missing = [binary for binary in ("ffprobe", "ffmpeg") if shutil.which(binary) is None]
    if missing:
        print(f"Missing required command(s): {', '.join(missing)}", file=sys.stderr)
        return 2

    try:
        duration = probe_duration(args.video)
        if duration <= 0:
            raise ValueError("video duration must be positive")
        times = sample_times(duration, args.samples)
        frames = extract(args.video, args.out, times)
    except (ValueError, subprocess.CalledProcessError) as exc:
        print(f"Could not sample video: {exc}", file=sys.stderr)
        return 1

    manifest = {
        "source": str(args.video.resolve()),
        "duration_seconds": round(duration, 3),
        "samples": frames,
        "review": "Compare identity geometry, cast distinctiveness, texture, asymmetry, expression anatomy, and temporal stability against approved anchors.",
    }
    manifest_path = args.out / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(manifest_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

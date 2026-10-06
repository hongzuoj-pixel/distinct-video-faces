#!/usr/bin/env python3
"""Sample audit frames from a video using ffmpeg (ffprobe optional).

Samples uniform frames (first/middle/last among them) plus the highest-motion
"stress" frames, so identity drift surfaces where it is most likely: fast
motion, head turns, and speech. Requires ffmpeg on PATH; ffprobe is used for
durations when present and otherwise parsed from ffmpeg's own output.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from collections import namedtuple
from pathlib import Path

MOTION_FPS = 6
MOTION_WIDTH = 64
MOTION_HEIGHT = 36

FrameSample = namedtuple("FrameSample", ["path", "timestamp", "role"])


def probe_duration(video: Path) -> float:
    """Duration in seconds; ffprobe first, ffmpeg stderr as fallback."""
    if shutil.which("ffprobe"):
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
        try:
            result = subprocess.run(command, check=True, capture_output=True, text=True)
            duration = float(result.stdout.strip())
            if duration > 0:
                return duration
        except (OSError, ValueError, subprocess.SubprocessError):
            pass
    command = ["ffmpeg", "-hide_banner", "-i", str(video)]
    result = subprocess.run(command, check=False, capture_output=True, text=True)
    match = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", result.stderr)
    if match is None:
        raise ValueError("could not determine video duration (no ffprobe and no Duration line)")
    hours, minutes, seconds = (float(part) for part in match.groups())
    return hours * 3600 + minutes * 60 + seconds


def sample_times(duration: float, count: int) -> list[float]:
    if count < 3:
        raise ValueError("samples must be at least 3")
    margin = min(0.05, duration / 20)
    usable = max(0.0, duration - 2 * margin)
    return [round(margin + usable * index / (count - 1), 3) for index in range(count)]


def compute_motion_scores(video: Path, fps: int = MOTION_FPS, width: int = MOTION_WIDTH, height: int = MOTION_HEIGHT) -> list[float]:
    """Mean absolute pixel difference between consecutive downscaled frames.

    Index i is the motion leading into timestamp i / fps. ffmpeg decodes and
    downscales; the differencing runs on raw bytes in stdlib Python.
    """
    command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-an",
        "-i",
        str(video),
        "-vf",
        f"fps={fps},scale={width}:{height},format=gray",
        "-f",
        "rawvideo",
        "pipe:1",
    ]
    frame_size = width * height
    scores: list[float] = []
    previous: bytes | None = None
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    assert process.stdout is not None
    try:
        while True:
            data = process.stdout.read(frame_size)
            if not data or len(data) < frame_size:
                break
            if previous is None:
                scores.append(0.0)
            else:
                total = sum(abs(a - b) for a, b in zip(previous, data))
                scores.append(total / frame_size)
            previous = data
    finally:
        process.stdout.close()
        return_code = process.wait()
    if return_code != 0:
        raise subprocess.CalledProcessError(return_code, command)
    return scores


def pick_stress_times(
    scores: list[float],
    fps: int,
    count: int,
    duration: float,
    margin: float,
    exclude: list[float],
    min_gap: float = 0.5,
) -> list[float]:
    """Timestamps of the highest-motion frames, spaced away from uniform picks."""
    candidates = sorted(
        (
            (index / fps, score)
            for index, score in enumerate(scores)
            if score > 0.0
        ),
        key=lambda item: item[1],
        reverse=True,
    )
    chosen: list[float] = []
    for timestamp, _score in candidates:
        if len(chosen) >= count:
            break
        if timestamp < margin or timestamp > duration - margin:
            continue
        if any(abs(timestamp - existing) < min_gap for existing in exclude):
            continue
        if any(abs(timestamp - existing) < min_gap for existing in chosen):
            continue
        chosen.append(timestamp)
    return sorted(round(timestamp, 3) for timestamp in chosen)


def extract_frame(video: Path, destination: Path, timestamp: float) -> None:
    base = ["ffmpeg", "-hide_banner", "-loglevel", "error"]
    commands = [
        base + ["-ss", str(timestamp), "-i", str(video), "-frames:v", "1", "-y", str(destination)],
        base + ["-i", str(video), "-ss", str(timestamp), "-frames:v", "1", "-y", str(destination)],
        base + ["-sseof", "-0.2", "-i", str(video), "-frames:v", "1", "-y", str(destination)],
    ]
    last_error = "no frame was written"
    for command in commands:
        if destination.exists():
            destination.unlink()
        result = subprocess.run(command, check=False, capture_output=True, text=True)
        if result.returncode == 0 and destination.is_file() and destination.stat().st_size > 0:
            return
        last_error = result.stderr.strip() or f"ffmpeg exited {result.returncode}"
    raise ValueError(f"ffmpeg could not extract a frame at {timestamp}s from {video}: {last_error}")


def sample_video(video: Path, output: Path, samples: int = 7, stress: int = 2) -> list[FrameSample]:
    """Write uniform + stress frames into output; return them in time order."""
    if stress < 0:
        raise ValueError("stress must be 0 or greater")
    output.mkdir(parents=True, exist_ok=True)
    duration = probe_duration(video)
    if duration <= 0:
        raise ValueError("video duration must be positive")
    margin = min(0.05, duration / 20)
    uniform = sample_times(duration, samples)
    stress_times: list[float] = []
    if stress > 0:
        try:
            scores = compute_motion_scores(video)
            stress_times = pick_stress_times(
                scores, MOTION_FPS, stress, duration, margin, exclude=uniform
            )
        except (OSError, ValueError, subprocess.SubprocessError) as exc:
            print(f"Motion sampling skipped ({exc}); using uniform frames only.", file=sys.stderr)

    planned: list[tuple[float, str]] = [(timestamp, "uniform") for timestamp in uniform]
    planned += [(timestamp, "stress") for timestamp in stress_times]
    planned.sort(key=lambda item: item[0])

    sampled: list[FrameSample] = []
    for index, (timestamp, role) in enumerate(planned, start=1):
        filename = f"frame-{index:02d}-{role}-{timestamp:08.3f}s.png"
        destination = output / filename
        extract_frame(video, destination, timestamp)
        sampled.append(FrameSample(path=destination, timestamp=timestamp, role=role))
    return sampled


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video", type=Path)
    parser.add_argument("--out", type=Path, default=Path("audit-frames"))
    parser.add_argument("--samples", type=int, default=7, help="Uniform samples, at least 3 (default: 7).")
    parser.add_argument("--stress", type=int, default=2, help="Extra high-motion frames (default: 2, 0 disables).")
    args = parser.parse_args()

    if not args.video.is_file():
        print(f"Video not found: {args.video}", file=sys.stderr)
        return 2
    if shutil.which("ffmpeg") is None:
        print("Missing required command: ffmpeg", file=sys.stderr)
        return 2

    try:
        duration = probe_duration(args.video)
        sampled = sample_video(args.video, args.out, samples=args.samples, stress=args.stress)
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        print(f"Could not sample video: {exc}", file=sys.stderr)
        return 1

    stress_used = sorted(item.timestamp for item in sampled if item.role == "stress")
    manifest = {
        "source": str(args.video.resolve()),
        "duration_seconds": round(duration, 3),
        "stress_source": f"frame differences at {MOTION_FPS} fps" if stress_used else None,
        "samples": [
            {
                "index": index,
                "timestamp_seconds": item.timestamp,
                "role": item.role,
                "file": item.path.name,
            }
            for index, item in enumerate(sampled, start=1)
        ],
        "review": "Compare identity geometry, cast distinctiveness, texture, asymmetry, expression anatomy, and temporal stability against approved anchors. Stress frames mark the highest-motion moments; check them first for drift.",
    }
    manifest_path = args.out / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(manifest_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

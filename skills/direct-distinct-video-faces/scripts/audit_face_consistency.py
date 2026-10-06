#!/usr/bin/env python3
"""Embedding-based face audit for AI-video QC.

Measures two things the text audits cannot see:

1. Within-character drift: how far each sampled frame's face embedding moves
   from the character's approved anchor (or from the most central frame when
   no anchors are supplied).
2. Between-character distinctiveness: how similar two different characters'
   embeddings are, across all frames and inside two-shots.

This is a ranking and localization signal, not identity proof. Confirm every
borderline case against the sampled images before regenerating anything.

Recognizer backends (--recognizer):
  sface        OpenCV SFace, 128-d, light and dependency-light (default).
  insightface  ArcFace via the insightface package, 512-d, EXPERIMENTAL.
               Requires --recognizer-model pointing at a buffalo-style
               recognition ONNX (e.g. w600k_r50.onnx) and heavier installs.

Requirements for the default backend (optional extras, kept out of the text
audits):
    pip install opencv-contrib-python numpy
Detector (YuNet) and default recognizer (SFace) models download on first use
into the model cache directory (override with --models-dir or the
DVF_MODELS_DIR environment variable). Set --no-download to require
pre-placed model files instead. With --report-dir, annotated frames and a
single-file HTML report are written alongside the numbers.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path
from statistics import fmean
from typing import Any

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

DEFAULTS = {
    "drift_fail": 0.363,  # OpenCV SFace cosine same/not-same threshold
    "drift_warn": 0.45,
    "collision_fail": 0.363,
    "collision_warn": 0.25,
    "assign": 0.363,
    "min_face_score": 0.60,
    "min_face_px": 40,
}

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}

MODELS = {
    "face_detection_yunet_2023mar.onnx": {
        "size": 232_589,
        "sha256": "8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4",
        "urls": (
            "https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx",
            "https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx",
        ),
    },
    "face_recognition_sface_2021dec.onnx": {
        "size": 38_696_353,
        "sha256": "0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79",
        "urls": (
            "https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx",
            "https://github.com/opencv/opencv_zoo/raw/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx",
        ),
    },
}

REPORT_NOTES = (
    "Cosine similarity of face embeddings is a heuristic ranking signal, "
    "not identity proof. Values are not calibrated probabilities: clean frontal "
    "crops from the same source can score very highly, but real same-identity "
    "scores vary by recognizer, crop, pose, and image quality. Motion blur, "
    "occlusion, extreme angles, heavy stylization, and "
    "beautification all lower scores without implying a real identity change. "
    "Use the numbers to localize and rank problems, then confirm against the "
    "sampled frames before prescribing regeneration."
)


class AuditError(Exception):
    """Operational failure the user can act on."""


# ---------------------------------------------------------------------------
# Recognizer backends
# ---------------------------------------------------------------------------


class SFaceBackend:
    """OpenCV SFace recognizer — 128-d, light, ships with opencv-contrib."""

    name = "sface"
    dimensions = 128
    model_file = "face_recognition_sface_2021dec.onnx"
    # OpenCV's documented SFace cosine same/not-same threshold.
    default_thresholds = {
        "drift_fail": 0.363,
        "drift_warn": 0.45,
        "collision_fail": 0.363,
        "collision_warn": 0.25,
        "assign": 0.363,
    }

    def __init__(self, cv2, model_path: Path):
        self.recognizer = cv2.FaceRecognizerSF.create(str(model_path), "")

    def embed(self, cv2, image, face_row) -> list[float]:
        aligned = self.recognizer.alignCrop(image, face_row)
        feature = self.recognizer.feature(aligned)
        return [float(value) for value in feature.ravel()]


class InsightFaceBackend:
    """ArcFace via the insightface package — 512-d, EXPERIMENTAL.

    Detection stays with YuNet; only the embedding model is swapped. Requires
    --recognizer-model pointing at a buffalo-style recognition ONNX such as
    w600k_r50.onnx. Threshold defaults are the commonly used ArcFace cosine
    operating point and should be re-tuned per pipeline like any other model.
    """

    name = "insightface"
    dimensions = 512
    model_file = None  # supplied via --recognizer-model
    default_thresholds = {
        "drift_fail": 0.40,
        "drift_warn": 0.50,
        "collision_fail": 0.40,
        "collision_warn": 0.28,
        "assign": 0.40,
    }

    def __init__(self, cv2, model_path: Path):
        try:
            import onnxruntime
            from insightface.utils import face_align
        except ImportError as exc:
            raise AuditError(
                "The insightface backend needs heavier extras:\n"
                "  pip install onnxruntime insightface\n"
                "and a recognition model via --recognizer-model "
                "(e.g. w600k_r50.onnx from the buffalo_l pack)."
            ) from exc
        self._face_align = face_align
        self.session = onnxruntime.InferenceSession(
            str(model_path), providers=["CPUExecutionProvider"]
        )
        self.input_name = self.session.get_inputs()[0].name

    def embed(self, cv2, image, face_row) -> list[float]:
        import numpy as np

        landmarks = np.array(face_row[4:14], dtype=np.float32).reshape(5, 2)
        aligned = self._face_align.norm_crop(image, landmarks, image_size=112)
        blob = cv2.dnn.blobFromImage(
            aligned, 1.0 / 127.5, (112, 112), (127.5, 127.5, 127.5), swapRB=True
        )
        feature = self.session.run(None, {self.input_name: blob})[0][0]
        return [float(value) for value in feature.ravel()]


BACKENDS = {"sface": SFaceBackend, "insightface": InsightFaceBackend}


def require_cv():
    try:
        import cv2  # noqa: F401
        import numpy  # noqa: F401

        return cv2
    except ImportError:
        raise AuditError(
            "Face auditing needs the optional CV extras. Install them with:\n"
            "  pip install opencv-contrib-python numpy"
        )


# ---------------------------------------------------------------------------
# Pure scoring helpers (no cv2/numpy required — unit-tested directly)
# ---------------------------------------------------------------------------


def cosine(left: Any, right: Any) -> float:
    """Cosine similarity between two equal-length vectors, clamped to [-1, 1]."""
    if len(left) != len(right):
        raise ValueError("embedding vectors must have the same length")
    dot = 0.0
    left_norm = 0.0
    right_norm = 0.0
    for a, b in zip(left, right):
        a = float(a)
        b = float(b)
        dot += a * b
        left_norm += a * a
        right_norm += b * b
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    return max(-1.0, min(1.0, dot / (math.sqrt(left_norm) * math.sqrt(right_norm))))


def summarize(scores: list[float]) -> dict[str, float] | None:
    if not scores:
        return None
    return {
        "n": len(scores),
        "min": round(min(scores), 4),
        "mean": round(fmean(scores), 4),
        "max": round(max(scores), 4),
    }


def classify_drift(worst: float | None, thresholds: dict[str, float]) -> str:
    """Lower similarity means more drift. Worst frame drives the verdict."""
    if worst is None:
        return "NOT_EVALUATED"
    if worst < thresholds["drift_fail"]:
        return "FAIL"
    if worst < thresholds["drift_warn"]:
        return "REVIEW"
    return "PASS"


def classify_collision(score: float | None, thresholds: dict[str, float]) -> str:
    """Higher similarity between identities means less distinctiveness."""
    if score is None:
        return "NOT_EVALUATED"
    if score > thresholds["collision_fail"]:
        return "FAIL"
    if score > thresholds["collision_warn"]:
        return "REVIEW"
    return "PASS"


def validate_thresholds(thresholds: dict[str, float]) -> None:
    cosine_keys = ("drift_fail", "drift_warn", "collision_fail", "collision_warn", "assign")
    for key in cosine_keys:
        if not -1.0 <= thresholds[key] <= 1.0:
            raise AuditError(f"{key} must be between -1 and 1")
    if thresholds["drift_fail"] > thresholds["drift_warn"]:
        raise AuditError("drift_fail must be less than or equal to drift_warn")
    if thresholds["collision_warn"] > thresholds["collision_fail"]:
        raise AuditError("collision_warn must be less than or equal to collision_fail")
    if not 0.0 <= thresholds["min_face_score"] <= 1.0:
        raise AuditError("min_face_score must be between 0 and 1")
    if thresholds["min_face_px"] <= 0:
        raise AuditError("min_face_px must be greater than 0")


def best_anchor(
    embedding: list[float],
    anchor_names: list[str],
    anchor_embeddings: list[list[float]],
) -> tuple[str | None, float]:
    """Nearest anchor identity by cosine, regardless of any threshold."""
    if not anchor_names:
        return None, 0.0
    best_name: str | None = None
    best_score = -1.0
    for name, reference in zip(anchor_names, anchor_embeddings):
        score = cosine(embedding, reference)
        if score > best_score:
            best_name = name
            best_score = score
    return best_name, best_score


def reference_frame_index(embeddings: list[list[float]]) -> int:
    """Index of the embedding closest to the mean of all embeddings."""
    if not embeddings:
        raise ValueError("embeddings must be non-empty")
    centroid = [fmean(column) for column in zip(*embeddings)]
    best_index = 0
    best_score = -2.0
    for index, embedding in enumerate(embeddings):
        score = cosine(embedding, centroid)
        if score > best_score:
            best_index = index
            best_score = score
    return best_index


def build_report(
    records: list[dict[str, Any]],
    anchors: dict[str, dict[str, Any]],
    thresholds: dict[str, float],
    source: str,
    model_meta: dict[str, str],
    sampled_times: list[float] | None = None,
) -> dict[str, Any]:
    """Aggregate per-frame detection records into the final audit report.

    Each record is {"frame", "file", "timestamp", "faces": [{"embedding",
    "identity", "anchor_score", "detect_score", "area"}]}. Pure function.
    """
    frame_count = len(records)
    anchor_names = sorted(anchors)

    # Per-identity drift against the assigned anchor (or the central frame).
    identities: dict[str, Any] = {}
    if anchor_names:
        for name in anchor_names:
            frame_scores: list[tuple[int, float]] = []
            discontinuity_frames: list[int] = []
            for record in records:
                matched = [
                    face["anchor_score"]
                    for face in record["faces"]
                    if face["identity"] == name and face["anchor_score"] is not None
                ]
                if matched:
                    frame_scores.append((record["frame"], max(matched)))
                    continue
                # The identity is absent but a near-miss face points at it:
                # treat that face's similarity as drift evidence.
                near_miss = [
                    face["best_anchor_score"]
                    for face in record["faces"]
                    if face["identity"] is None and face.get("best_anchor") == name
                ]
                if near_miss:
                    frame_scores.append((record["frame"], max(near_miss)))
                    discontinuity_frames.append(record["frame"])
            entry: dict[str, Any] = {
                "anchor": anchors[name]["file"],
                "frames_present": sum(
                    1
                    for record in records
                    if any(face["identity"] == name for face in record["faces"])
                ),
                "frames_missing": [
                    record["frame"] for record in records if not any(
                        face["identity"] == name for face in record["faces"]
                    )
                ],
                "discontinuity_frames": discontinuity_frames,
            }
            if frame_scores:
                scores = [score for _, score in frame_scores]
                worst_frame, worst = min(frame_scores, key=lambda item: item[1])
                entry["drift"] = {**summarize(scores), "worst_frame": worst_frame}
                worst_score = worst
            else:
                worst_score = None
            entry["verdict"] = classify_drift(worst_score, thresholds)
            identities[name] = entry
    else:
        subject_embeddings: list[list[float]] = []
        subject_frames: list[int] = []
        previous_embedding: list[float] | None = None
        for record in records:
            if record["faces"]:
                selected = record["faces"][0] if previous_embedding is None else max(
                    record["faces"], key=lambda face: cosine(previous_embedding, face["embedding"])
                )
                previous_embedding = selected["embedding"]
                subject_embeddings.append(selected["embedding"])
                subject_frames.append(record["frame"])
        if subject_embeddings:
            ref_index = reference_frame_index(subject_embeddings)
            scores = [
                cosine(subject_embeddings[ref_index], embedding)
                for embedding in subject_embeddings
            ]
            worst = min(scores)
            worst_frame = subject_frames[scores.index(worst)]
            identities["subject"] = {
                "anchor": None,
                "reference_frame": subject_frames[ref_index],
                "frames_present": len(scores),
                "frames_missing": [
                    record["frame"]
                    for record in records
                    if not record["faces"]
                ],
                "drift": {**summarize(scores), "worst_frame": worst_frame},
                "verdict": classify_drift(worst, thresholds),
            }

    # Cross-identity distinctiveness.
    pairs: list[dict[str, Any]] = []
    if anchor_names:
        for left_index, left in enumerate(anchor_names):
            for right in anchor_names[left_index + 1 :]:
                left_faces = [
                    (record["frame"], face["embedding"])
                    for record in records
                    for face in record["faces"]
                    if face["identity"] == left
                ]
                right_faces = [
                    (record["frame"], face["embedding"])
                    for record in records
                    for face in record["faces"]
                    if face["identity"] == right
                ]
                scores = [
                    cosine(left_embedding, right_embedding)
                    for _, left_embedding in left_faces
                    for _, right_embedding in right_faces
                ]
                co_frames = sorted(
                    {
                        record["frame"]
                        for record in records
                        if {
                            face["identity"] for face in record["faces"]
                        } >= {left, right}
                    }
                )
                entry = {
                    "a": left,
                    "b": right,
                    "similarity": summarize(scores),
                    "co_frame_frames": co_frames,
                }
                entry["verdict"] = classify_collision(
                    entry["similarity"]["max"] if scores else None, thresholds
                )
                pairs.append(entry)
    else:
        # No anchors: compare faces that co-occur inside one frame (two-shots)
        # and report the most distant pair of subject faces (identity swap).
        for record in records:
            faces = record["faces"]
            for left_index in range(len(faces)):
                for right_index in range(left_index + 1, len(faces)):
                    score = cosine(faces[left_index]["embedding"], faces[right_index]["embedding"])
                    pairs.append(
                        {
                            "a": f"frame-{record['frame']:02d}:face-{left_index + 1}",
                            "b": f"frame-{record['frame']:02d}:face-{right_index + 1}",
                            "similarity": {"n": 1, "min": round(score, 4), "mean": round(score, 4), "max": round(score, 4)},
                            "co_frame_frames": [record["frame"]],
                            "verdict": classify_collision(score, thresholds),
                        }
                    )

    no_face_frames = [record["frame"] for record in records if not record["faces"]]
    unassigned = [
        {"frame": record["frame"], "file": record["file"], "detect_score": round(face["detect_score"], 3)}
        for record in records
        for face in record["faces"]
        if anchor_names and face["identity"] is None
    ]
    multi_face_frames = [record["frame"] for record in records if len(record["faces"]) > 1]

    verdicts = [entry["verdict"] for entry in identities.values()] + [
        entry["verdict"] for entry in pairs
    ]
    findings: list[str] = []
    for name, entry in identities.items():
        if entry["verdict"] == "FAIL":
            drift = entry.get("drift", {})
            findings.append(
                f"identity drift: {name} drops to {drift.get('min')} similarity at frame {drift.get('worst_frame')}."
            )
        elif entry["verdict"] == "REVIEW":
            drift = entry.get("drift", {})
            findings.append(
                f"borderline drift: {name} worst similarity {drift.get('min')} at frame {drift.get('worst_frame')}."
            )
        if entry.get("discontinuity_frames"):
            findings.append(
                f"identity discontinuity: {name} is absent in frame(s) {entry['discontinuity_frames']} "
                "while an unmatched face was present — likely a recast, heavy drift, or an extra."
            )
        if anchor_names and entry["frames_present"] == 0:
            findings.append(
                f"identity {name} never matched any sampled frame; check the anchor image or --assign-threshold."
            )
    for entry in pairs:
        if entry["verdict"] == "FAIL":
            findings.append(
                f"cast collision: {entry['a']} and {entry['b']} peak similarity {entry['similarity']['max']}."
            )
        elif entry["verdict"] == "REVIEW":
            findings.append(
                f"borderline pair: {entry['a']} and {entry['b']} peak similarity {entry['similarity']['max']}."
            )
    if unassigned:
        findings.append(
            f"{len(unassigned)} detected face(s) matched no anchor identity; they may be extras or a drifted recast."
        )
    if no_face_frames:
        findings.append(
            f"no detectable face in frame(s) {no_face_frames}: occlusion, framing, or a missed identity."
        )
    if not anchor_names and multi_face_frames:
        findings.append(
            "anchor-free subject tracking saw multiple faces in frame(s) "
            f"{multi_face_frames}; add --anchors for reliable per-character drift attribution."
        )

    if any(value == "FAIL" for value in verdicts):
        verdict = "FAIL"
    elif any(value in {"REVIEW", "NOT_EVALUATED"} for value in verdicts) or unassigned or no_face_frames or (not anchor_names and multi_face_frames):
        verdict = "REVIEW"
    else:
        verdict = "PASS"

    return {
        "tool": "audit_face_consistency",
        "input": str(source),
        "frames_evaluated": frame_count,
        "sampled_times": sampled_times,
        "model": model_meta,
        "thresholds": {key: thresholds[key] for key in sorted(thresholds)},
        "anchors": {name: anchors[name]["file"] for name in anchor_names},
        "identities": identities,
        "pairs": pairs,
        "unassigned_faces": unassigned,
        "no_face_frames": no_face_frames,
        "multi_face_frames": multi_face_frames,
        "verdict": verdict,
        "findings": findings,
        "notes": REPORT_NOTES,
    }


# ---------------------------------------------------------------------------
# Model management
# ---------------------------------------------------------------------------


def default_models_dir() -> Path:
    env = os.environ.get("DVF_MODELS_DIR")
    if env:
        return Path(env)
    return Path.home() / ".cache" / "distinct-video-faces" / "models"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def ensure_model(name: str, spec: dict[str, Any], models_dir: Path, allow_unverified: bool, allow_download: bool) -> Path:
    target = models_dir / name
    if target.is_file():
        if allow_unverified or sha256_file(target) == spec["sha256"]:
            return target
        raise AuditError(
            f"{target} exists but does not match the published checksum. "
            "Delete it and re-run to download a fresh copy, or pass --allow-unverified."
        )
    if not allow_download:
        raise AuditError(
            f"Model missing: {target}\n"
            f"Download it manually from {spec['urls'][0]} or re-run without --no-download."
        )
    models_dir.mkdir(parents=True, exist_ok=True)
    partial = target.with_suffix(target.suffix + ".part")
    last_error: Exception | None = None
    for url in spec["urls"]:
        try:
            print(f"Downloading {name} ({spec['size'] / 1e6:.1f} MB) from {url} ...", file=sys.stderr)
            with urllib.request.urlopen(url, timeout=120) as response, partial.open("wb") as handle:
                while True:
                    chunk = response.read(1 << 20)
                    if not chunk:
                        break
                    handle.write(chunk)
            if partial.stat().st_size != spec["size"]:
                raise AuditError(f"Downloaded {name} has {partial.stat().st_size} bytes, expected {spec['size']}.")
            if not allow_unverified:
                actual = sha256_file(partial)
                if actual != spec["sha256"]:
                    raise AuditError(f"Downloaded {name} failed checksum verification ({actual}).")
            partial.replace(target)
            return target
        except Exception as exc:  # noqa: BLE001 - try the next mirror
            last_error = exc
            print(f"  download failed: {exc}", file=sys.stderr)
            if partial.exists():
                partial.unlink()
    raise AuditError(f"Could not download {name}: {last_error}")


# ---------------------------------------------------------------------------
# Detection and embedding I/O
# ---------------------------------------------------------------------------


def load_image(cv2, path: Path):
    """Read an image with unicode-safe decoding (Windows CJK paths)."""
    import numpy as np

    try:
        data = np.fromfile(str(path), dtype=np.uint8)
    except OSError as exc:
        raise AuditError(f"Could not read image: {path}") from exc
    image = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if image is None:
        raise AuditError(f"Could not decode image: {path}")
    return image


def largest_face_row(faces) -> Any:
    if faces is None or len(faces) == 0:
        return None
    return max(faces, key=lambda row: float(row[2]) * float(row[3]))


def detect_faces(cv2, detector, image, min_face_score: float, min_face_px: float) -> list[Any]:
    height, width = image.shape[:2]
    detector.setInputSize((width, height))
    detected = detector.detect(image)
    # OpenCV returns (retval, faces) in the Python bindings; be tolerant of
    # both that layout and a bare faces array.
    if isinstance(detected, tuple):
        detected = detected[-1]
    if detected is None or len(detected) == 0:
        return []
    rows = []
    for row in detected:
        score = float(row[14])
        box_w = float(row[2])
        box_h = float(row[3])
        if score >= min_face_score and min(box_w, box_h) >= min_face_px:
            rows.append(row)
    rows.sort(key=lambda row: float(row[2]) * float(row[3]), reverse=True)
    return rows


def iter_images(directory: Path) -> list[Path]:
    return sorted(
        (
            path
            for path in directory.iterdir()
            if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
        ),
        key=lambda path: path.name.lower(),
    )


def collect_frames(cv2, detector, backend, image_paths, thresholds) -> list[dict[str, Any]]:
    records = []
    for index, path in enumerate(image_paths):
        image = load_image(cv2, path)
        faces = detect_faces(cv2, detector, image, thresholds["min_face_score"], thresholds["min_face_px"])
        record = {"frame": index, "file": path.name, "timestamp": None, "faces": []}
        for face_row in faces:
            record["faces"].append(
                {
                    "embedding": backend.embed(cv2, image, face_row),
                    "identity": None,
                    "anchor_score": None,
                    "detect_score": float(face_row[14]),
                    "area": float(face_row[2]) * float(face_row[3]),
                    "box": [float(value) for value in face_row[:4]],
                }
            )
        records.append(record)
    return records


def assign_anchors(records, anchors, thresholds) -> None:
    """Attach anchors with a one-face/one-identity constraint per frame.

    Faces below the threshold keep `identity=None` but retain their best
    candidate and score, so a frame where an identity disappears while a
    near-miss face appears can be reported as an identity discontinuity.
    """
    names = sorted(anchors)
    embeddings = [anchors[name]["embedding"] for name in names]
    for record in records:
        candidates: list[tuple[float, int, str]] = []
        for face_index, face in enumerate(record["faces"]):
            name, score = best_anchor(face["embedding"], names, embeddings)
            face["best_anchor"] = name
            face["best_anchor_score"] = score
            face["identity"] = None
            face["anchor_score"] = None
            for anchor_name, anchor_embedding in zip(names, embeddings):
                candidates.append((cosine(face["embedding"], anchor_embedding), face_index, anchor_name))
        assigned_faces: set[int] = set()
        assigned_names: set[str] = set()
        for score, face_index, name in sorted(candidates, reverse=True):
            if score < thresholds["assign"]:
                break
            if face_index in assigned_faces or name in assigned_names:
                continue
            record["faces"][face_index]["identity"] = name
            record["faces"][face_index]["anchor_score"] = score
            assigned_faces.add(face_index)
            assigned_names.add(name)


def load_anchors(cv2, detector, backend, anchor_dir: Path, thresholds) -> dict[str, dict[str, Any]]:
    if not anchor_dir.is_dir():
        raise AuditError(f"Anchor directory not found: {anchor_dir}")
    anchors: dict[str, dict[str, Any]] = {}
    for path in iter_images(anchor_dir):
        image = load_image(cv2, path)
        faces = detect_faces(cv2, detector, image, thresholds["min_face_score"], thresholds["min_face_px"])
        row = largest_face_row(faces)
        if row is None:
            raise AuditError(f"Anchor image contains no detectable face: {path}")
        if path.stem in anchors:
            raise AuditError(f"Duplicate anchor identity stem '{path.stem}'. Rename one file.")
        anchors[path.stem] = {"file": path.name, "embedding": backend.embed(cv2, image, row)}
    if not anchors:
        raise AuditError(f"No anchor images found in: {anchor_dir}")
    return anchors


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------


def format_report(report: dict[str, Any]) -> str:
    lines = [f"FACE AUDIT — {report['input']} — {report['verdict']}"]
    model = report["model"]
    lines.append(
        f"Model: {model['recognizer']} embeddings, cosine metric | frames: {report['frames_evaluated']}"
    )
    for name, entry in report["identities"].items():
        drift = entry.get("drift")
        if drift:
            lines.append(
                f"  {name}: {entry['frames_present']}/{report['frames_evaluated']} frames, "
                f"drift mean {drift['mean']} min {drift['min']} (frame {drift['worst_frame']}) — {entry['verdict']}"
            )
        else:
            lines.append(f"  {name}: 0/{report['frames_evaluated']} frames — {entry['verdict']}")
    for pair in report["pairs"]:
        similarity = pair["similarity"]
        label = " + ".join([pair["a"], pair["b"]]) if "frame-" in pair["a"] else f"PAIR {pair['a']} / {pair['b']}"
        if similarity:
            lines.append(f"  {label}: mean {similarity['mean']} max {similarity['max']} — {pair['verdict']}")
        else:
            lines.append(f"  {label}: no comparable detections — {pair['verdict']}")
    if report["no_face_frames"]:
        lines.append(f"  Frames without a detectable face: {report['no_face_frames']}")
    for finding in report["findings"]:
        lines.append(f"  NOTE: {finding}")
    lines.append("  Reminder: cosine values rank and localize problems; confirm borderline frames visually.")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Visual report (annotated frames + single-file HTML)
# ---------------------------------------------------------------------------


def identity_tags(report: dict[str, Any]) -> dict[str, str]:
    """Short numeric tags for drawing; cv2 fonts cannot render CJK names."""
    return {name: str(index) for index, name in enumerate(sorted(report["identities"]))}


def highlight_frames(report: dict[str, Any]) -> set[int]:
    """Frames human review should look at first."""
    highlighted: set[int] = set(report["no_face_frames"])
    for entry in report["identities"].values():
        highlighted.update(entry.get("discontinuity_frames") or [])
        drift = entry.get("drift")
        if drift and entry["verdict"] in {"FAIL", "REVIEW"} and drift.get("worst_frame") is not None:
            highlighted.add(drift["worst_frame"])
    for pair in report["pairs"]:
        if pair["verdict"] in {"FAIL", "REVIEW"}:
            highlighted.update(pair.get("co_frame_frames") or [])
    return highlighted


def face_label(face: dict[str, Any], tags: dict[str, str]) -> str:
    if face.get("identity"):
        score = face.get("anchor_score")
        tag = tags.get(face["identity"], "?")
    else:
        score = face.get("best_anchor_score")
        best = face.get("best_anchor")
        tag = f"?{tags[best]}" if best in tags else "?"
    return f"{tag}:{score:.2f}" if score is not None else str(tag)


def annotate_frame(cv2, image, record: dict[str, Any], tags: dict[str, str]):
    """Draw boxes and numeric tags; green = assigned, orange = unmatched."""
    annotated = image.copy()
    for face in record["faces"]:
        x, y, w, h = (int(round(float(value))) for value in face["box"])
        if face.get("identity"):
            color = (60, 180, 75)
        else:
            color = (0, 140, 255)
        cv2.rectangle(annotated, (x, y), (x + w, y + h), color, 2)
        label = face_label(face, tags)
        cv2.putText(
            annotated, label, (x, max(14, y - 6)),
            cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1, cv2.LINE_AA,
        )
    return annotated


def make_thumbnail_data_uri(cv2, image, max_width: int = 360, quality: int = 80) -> str:
    import base64

    height, width = image.shape[:2]
    if width > max_width:
        scale = max_width / width
        image = cv2.resize(image, (max_width, int(height * scale)), interpolation=cv2.INTER_AREA)
    ok, buffer = cv2.imencode(".jpg", image, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
    if not ok:
        return ""
    return "data:image/jpeg;base64," + base64.b64encode(buffer.tobytes()).decode("ascii")


def build_html(report: dict[str, Any], gallery: list[dict[str, Any]]) -> str:
    """Render the single-file HTML report. Pure string building."""
    import html as html_module

    e = html_module.escape
    verdict = report["verdict"]
    model = report["model"]
    tags = identity_tags(report)
    legend = (
        ", ".join(
            f"{e(tag)} = {e(name)}"
            for name, tag in sorted(tags.items(), key=lambda item: int(item[1]))
        )
        or "no anchors — subject mode"
    )

    identity_rows = "".join(
        f"<tr><td>{e(name)}</td>"
        f"<td>{entry['frames_present']}/{report['frames_evaluated']}</td>"
        f"<td>{e(_drift_text(entry)) or '—'}</td>"
        f"<td class='v-{e(entry['verdict'].lower())}'>{e(entry['verdict'])}</td></tr>"
        for name, entry in report["identities"].items()
    ) or "<tr><td colspan='4'>No identities evaluated.</td></tr>"

    pair_rows = "".join(
        f"<tr><td>{e(pair['a'])}</td><td>{e(pair['b'])}</td>"
        f"<td>{pair['similarity']['mean'] if pair['similarity'] else '—'}</td>"
        f"<td>{pair['similarity']['max'] if pair['similarity'] else '—'}</td>"
        f"<td class='v-{e(pair['verdict'].lower())}'>{e(pair['verdict'])}</td></tr>"
        for pair in report["pairs"]
    ) or "<tr><td colspan='5'>No pairs evaluated.</td></tr>"

    findings = "".join(f"<li>{e(finding)}</li>" for finding in report["findings"]) or "<li>None.</li>"
    cards = "".join(
        f"<div class='card {'highlight' if item['highlight'] else ''}'>"
        f"<img src='{item['data_uri']}' alt='frame {item['frame']}'/>"
        f"<div class='cap'>frame {item['frame']} · {e(item['file'])}<br/>{e(', '.join(item['labels'])) or 'no face'}</div></div>"
        for item in gallery
    )
    th = report["thresholds"]
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"/>
<title>Face audit — {e(str(report["input"]))}</title>
<style>
body{{font-family:Segoe UI,system-ui,sans-serif;margin:24px;color:#1a1a1a;max-width:1100px}}
h1{{font-size:20px}} .verdict{{padding:2px 10px;border-radius:4px;color:#fff;font-weight:600}}
.v-pass{{background:#2e7d32}} .v-fail{{background:#c62828}} .v-review{{background:#ef6c00}}
.v-not_evaluated{{background:#616161}} table{{border-collapse:collapse;margin:12px 0}}
td,th{{border:1px solid #ddd;padding:4px 10px;font-size:13px;text-align:left}}
.card{{display:inline-block;margin:8px;vertical-align:top;text-align:center}}
.card img{{border:3px solid #ccc;border-radius:4px;display:block}}
.card.highlight img{{border-color:#c62828}}
.cap{{font-size:11px;color:#444;margin-top:2px}}
.note{{font-size:12px;color:#555;background:#f5f5f5;padding:8px 12px;border-radius:4px}}
</style></head><body>
<h1>Face audit — {e(str(report["input"]))} <span class="verdict v-{e(verdict.lower())}">{e(verdict)}</span></h1>
<p><b>Model:</b> {e(model["recognizer"])} · {model["dimensions"]}-d · cosine |
<b>Frames:</b> {report["frames_evaluated"]} |
<b>Tags:</b> {legend}</p>
<h2>Identity drift</h2>
<table><tr><th>Identity</th><th>Frames present</th><th>Drift (min/mean, worst frame)</th><th>Verdict</th></tr>{identity_rows}</table>
<h2>Pairwise distinctiveness</h2>
<table><tr><th>A</th><th>B</th><th>Mean similarity</th><th>Max</th><th>Verdict</th></tr>{pair_rows}</table>
<h2>Findings</h2><ul>{findings}</ul>
<h2>Frames</h2>
<p class="note">Red border = flagged for review (worst drift, discontinuity, collision, or no face). Tags: number = identity, ? = unmatched.</p>
{cards}
<h2>Thresholds</h2>
<p class="note">{e(", ".join(f"{k}={v}" for k, v in th.items()))}</p>
<p class="note">{e(report["notes"])}</p>
</body></html>
"""


def _drift_text(entry: dict[str, Any]) -> str:
    drift = entry.get("drift")
    if not drift:
        return ""
    return f"min {drift['min']} / mean {drift['mean']} (frame {drift['worst_frame']})"


def write_visual_report(cv2, report_dir: Path, records, image_paths, report: dict[str, Any]) -> Path:
    """Write annotated frames and report.html; return the HTML path."""
    frames_dir = report_dir / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    tags = identity_tags(report)
    highlights = highlight_frames(report)
    gallery: list[dict[str, Any]] = []
    for record, path in zip(records, image_paths):
        image = load_image(cv2, path)
        annotated = annotate_frame(cv2, image, record, tags)
        ok, buffer = cv2.imencode(".png", annotated)
        if ok:
            buffer.tofile(str(frames_dir / f"frame-{record['frame']:02d}-annotated.png"))
        gallery.append(
            {
                "frame": record["frame"],
                "file": record["file"],
                "data_uri": make_thumbnail_data_uri(cv2, annotated),
                "labels": [face_label(face, tags) for face in record["faces"]],
                "highlight": record["frame"] in highlights,
            }
        )
    html_path = report_dir / "report.html"
    html_path.write_text(build_html(report, gallery), encoding="utf-8")
    return html_path


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("input", type=Path, help="A video file or a directory of ordered frames (jpg/png/...).")
    parser.add_argument("--anchors", type=Path, default=None, help="Directory of reference stills; each image filename stem becomes an identity.")
    parser.add_argument("--models-dir", type=Path, default=None, help=f"Model cache directory (default: {default_models_dir()} or DVF_MODELS_DIR).")
    parser.add_argument("--recognizer", choices=sorted(BACKENDS), default="sface", help="Embedding backend (default: sface). insightface is experimental.")
    parser.add_argument("--recognizer-model", type=Path, default=None, help="Recognition ONNX for the insightface backend (e.g. w600k_r50.onnx from buffalo_l).")
    parser.add_argument("--samples", type=int, default=7, help="Uniform frames to sample when INPUT is a video (default: 7).")
    parser.add_argument("--stress", type=int, default=2, help="Extra high-motion frames to sample when INPUT is a video (default: 2).")
    parser.add_argument("--out", type=Path, default=None, help="Also write the JSON report to this path.")
    parser.add_argument("--report-dir", type=Path, default=None, help="Write annotated frames and a single-file HTML report here.")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
    parser.add_argument("--strict", action="store_true", help="Exit 1 on REVIEW as well as FAIL.")
    parser.add_argument("--no-download", action="store_true", help="Never download models; require pre-placed files.")
    parser.add_argument("--allow-unverified", action="store_true", help="Skip checksum verification (not recommended).")

    parser.add_argument("--drift-fail", type=float, default=None, help="Below this frame-to-anchor cosine, the identity FAILs (default: backend-specific).")
    parser.add_argument("--drift-warn", type=float, default=None, help="Below this cosine the identity is flagged for review (default: backend-specific).")
    parser.add_argument("--collision-fail", type=float, default=None, help="Cross-identity mean cosine above this FAILs distinctiveness (default: backend-specific).")
    parser.add_argument("--collision-warn", type=float, default=None, help="Cross-identity mean cosine above this is flagged for review (default: backend-specific).")
    parser.add_argument("--assign-threshold", type=float, default=None, help="Minimum cosine to assign a detected face to an anchor identity (default: backend-specific).")
    parser.add_argument("--min-face-score", type=float, default=DEFAULTS["min_face_score"], help="YuNet detector score threshold (default: %(default)s).")
    parser.add_argument("--min-face-px", type=float, default=DEFAULTS["min_face_px"], help="Ignore faces smaller than this many pixels on the short side (default: %(default)s).")

    args = parser.parse_args()
    backend_cls = BACKENDS[args.recognizer]
    thresholds = {**DEFAULTS, **backend_cls.default_thresholds}
    explicit = {
        key: value
        for key, value in (
            ("drift_fail", args.drift_fail),
            ("drift_warn", args.drift_warn),
            ("collision_fail", args.collision_fail),
            ("collision_warn", args.collision_warn),
            ("assign", args.assign_threshold),
        )
        if value is not None
    }
    thresholds.update(explicit)
    thresholds["min_face_score"] = args.min_face_score
    thresholds["min_face_px"] = args.min_face_px

    try:
        validate_thresholds(thresholds)
        if args.samples < 3:
            raise AuditError("--samples must be at least 3")
        if args.stress < 0:
            raise AuditError("--stress must be 0 or greater")
    except AuditError as exc:
        print(f"Invalid arguments: {exc}", file=sys.stderr)
        return 2

    if not args.input.exists():
        print(f"Input not found: {args.input}", file=sys.stderr)
        return 2

    temp_dir: tempfile.TemporaryDirectory | None = None
    visual_html: Path | None = None
    try:
        cv2 = require_cv()
        models_dir = args.models_dir or default_models_dir()
        detector_path = ensure_model(
            "face_detection_yunet_2023mar.onnx",
            MODELS["face_detection_yunet_2023mar.onnx"],
            models_dir,
            args.allow_unverified,
            not args.no_download,
        )
        detector = cv2.FaceDetectorYN.create(str(detector_path), "", (320, 320), 0.6, 0.3, 5000)
        if backend_cls is SFaceBackend:
            recognizer_path = ensure_model(
                SFaceBackend.model_file,
                MODELS[SFaceBackend.model_file],
                models_dir,
                args.allow_unverified,
                not args.no_download,
            )
            backend = SFaceBackend(cv2, recognizer_path)
            recognizer_meta = recognizer_path.name
        else:
            if args.recognizer_model is None or not args.recognizer_model.is_file():
                raise AuditError(
                    "--recognizer insightface requires --recognizer-model PATH to a "
                    "recognition ONNX (e.g. w600k_r50.onnx from the buffalo_l pack)."
                )
            backend = backend_cls(cv2, args.recognizer_model)
            recognizer_meta = args.recognizer_model.name
        model_meta = {
            "detector": detector_path.name,
            "recognizer": f"{backend.name}:{recognizer_meta}",
            "metric": "cosine",
            "dimensions": backend.dimensions,
        }

        anchors: dict[str, dict[str, Any]] = {}
        if args.anchors:
            anchors = load_anchors(cv2, detector, backend, args.anchors, thresholds)

        if args.input.is_dir():
            image_paths = iter_images(args.input)
            if not image_paths:
                raise AuditError(f"No jpg/png images found in: {args.input}")
            sampled_times = None
        else:
            import sample_video_frames

            if shutil.which("ffmpeg") is None:
                raise AuditError("INPUT is a video but ffmpeg was not found on PATH.")
            temp_dir = tempfile.TemporaryDirectory(prefix="dvf-face-audit-")
            out_dir = Path(temp_dir.name)
            try:
                sampled = sample_video_frames.sample_video(
                    args.input, out_dir, samples=args.samples, stress=args.stress
                )
            except (ValueError, OSError, subprocess.SubprocessError) as exc:
                raise AuditError(f"Could not sample video: {exc}") from exc
            image_paths = [item.path for item in sampled]
            sampled_times = [item.timestamp for item in sampled]

        records = collect_frames(cv2, detector, backend, image_paths, thresholds)
        if anchors:
            assign_anchors(records, anchors, thresholds)
        report = build_report(records, anchors, thresholds, args.input, model_meta, sampled_times)
        if args.report_dir:
            # Inside the try: in video mode the sampled frames live in a temp
            # directory that the finally block deletes.
            visual_html = write_visual_report(cv2, args.report_dir, records, image_paths, report)
    except AuditError as exc:
        print(f"Could not run face audit: {exc}", file=sys.stderr)
        return 2
    finally:
        if temp_dir is not None:
            temp_dir.cleanup()

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(format_report(report))
        if visual_html is not None:
            print(f"Visual report: {visual_html}")

    if report["verdict"] == "FAIL":
        return 1
    if report["verdict"] == "REVIEW" and args.strict:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import importlib.util
import hashlib
import os
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "direct-distinct-video-faces" / "scripts"


def load_module(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load {name}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


face_audit = load_module("audit_face_consistency")

T = dict(face_audit.DEFAULTS)


def vec(direction: int, dim: int = 8, scale: float = 1.0) -> list[float]:
    """Unit vector pointing along `direction` in `dim`-dimensional space."""
    values = [0.0] * dim
    values[direction % dim] = scale
    return values


def mix(base: list[float], other: list[float], weight: float) -> list[float]:
    """Blend two vectors; weight 0.9 means mostly `base`."""
    return [weight * a + (1.0 - weight) * b for a, b in zip(base, other)]


def face(embedding, identity=None, anchor_score=None, detect_score=0.9):
    return {
        "embedding": embedding,
        "identity": identity,
        "anchor_score": anchor_score,
        "detect_score": detect_score,
        "area": 10000.0,
    }


def record(index, faces, file="frame.jpg"):
    return {"frame": index, "file": file, "timestamp": None, "faces": faces}


class CosineTests(unittest.TestCase):
    def test_identical_and_orthogonal(self):
        self.assertAlmostEqual(face_audit.cosine(vec(0), vec(0)), 1.0)
        self.assertAlmostEqual(face_audit.cosine(vec(0), vec(1)), 0.0)
        self.assertAlmostEqual(face_audit.cosine(vec(0, scale=5.0), vec(0)), 1.0)
        self.assertEqual(face_audit.cosine(vec(0), [0.0] * 8), 0.0)
        with self.assertRaises(ValueError):
            face_audit.cosine([1.0, 0.0], [1.0])


class VerdictTests(unittest.TestCase):
    def test_drift_classification_uses_lower_is_worse(self):
        self.assertEqual(face_audit.classify_drift(0.10, T), "FAIL")
        self.assertEqual(face_audit.classify_drift(0.40, T), "REVIEW")
        self.assertEqual(face_audit.classify_drift(0.60, T), "PASS")
        self.assertEqual(face_audit.classify_drift(None, T), "NOT_EVALUATED")

    def test_collision_classification_uses_higher_is_worse(self):
        self.assertEqual(face_audit.classify_collision(0.50, T), "FAIL")
        self.assertEqual(face_audit.classify_collision(0.30, T), "REVIEW")
        self.assertEqual(face_audit.classify_collision(0.05, T), "PASS")
        self.assertEqual(face_audit.classify_collision(None, T), "NOT_EVALUATED")


class AssignTests(unittest.TestCase):
    def test_assignment_is_one_to_one_inside_a_frame(self):
        anchors = {"A": {"file": "a.png", "embedding": vec(0)}, "B": {"file": "b.png", "embedding": vec(1)}}
        records = [record(0, [face(mix(vec(0), vec(1), 0.99)), face(mix(vec(0), vec(1), 0.70))])]
        face_audit.assign_anchors(records, anchors, {**T, "assign": 0.25})
        self.assertEqual({item["identity"] for item in records[0]["faces"]}, {"A", "B"})

    def test_best_anchor_returns_nearest_identity(self):
        names = ["A", "B"]
        anchors = [vec(0), vec(1)]
        name, score = face_audit.best_anchor(vec(0), names, anchors)
        self.assertEqual(name, "A")
        self.assertAlmostEqual(score, 1.0)
        name, score = face_audit.best_anchor(vec(2), names, anchors)
        self.assertEqual(name, "A")  # nearest candidate even below threshold
        self.assertAlmostEqual(score, 0.0)
        name, score = face_audit.best_anchor(mix(vec(0), vec(1), 0.9), names, anchors)
        self.assertEqual(name, "A")
        self.assertGreater(score, 0.9)
        # Without anchors there is nothing to return.
        self.assertEqual(face_audit.best_anchor(vec(0), [], []), (None, 0.0))

    def test_reference_frame_is_central_not_outlier(self):
        cluster = [vec(0) for _ in range(4)]
        outlier = vec(1)
        index = face_audit.reference_frame_index([*cluster, outlier])
        self.assertLess(index, 4)

    def test_discontinuity_frame_counts_toward_drift(self):
        # Frame 3 contains a face whose nearest anchor is A but below the
        # assignment threshold — an identity discontinuity that must FAIL A.
        anchor_a = {"file": "a.png", "embedding": vec(0)}
        matched = face(vec(0), "A", 0.90)
        matched["best_anchor"] = "A"
        matched["best_anchor_score"] = 0.90
        swapped = face(vec(2), None, None)
        swapped["best_anchor"] = "A"
        swapped["best_anchor_score"] = 0.12
        records = [
            record(0, [matched]),
            record(1, [swapped]),
            record(2, [matched]),
        ]
        report = face_audit.build_report(records, {"A": anchor_a}, T, "clip.mp4", {})
        entry = report["identities"]["A"]
        self.assertEqual(entry["verdict"], "FAIL")
        self.assertEqual(entry["discontinuity_frames"], [1])
        self.assertEqual(entry["drift"]["worst_frame"], 1)
        self.assertEqual(entry["drift"]["min"], 0.12)
        self.assertTrue(any("identity discontinuity: A" in finding for finding in report["findings"]))


class BuildReportTests(unittest.TestCase):
    def test_pair_verdict_uses_peak_not_diluted_mean(self):
        anchors = {"A": {"file": "a.png", "embedding": vec(0)}, "B": {"file": "b.png", "embedding": vec(1)}}
        records = [record(0, [face(vec(0), "A", 0.9), face(vec(0), "B", 0.9)]), record(1, [face(vec(2), "A", 0.9), face(vec(3), "B", 0.9)])]
        pair = face_audit.build_report(records, anchors, T, "clip.mp4", {})["pairs"][0]
        self.assertLess(pair["similarity"]["mean"], T["collision_fail"])
        self.assertEqual(pair["similarity"]["max"], 1.0)
        self.assertEqual(pair["verdict"], "FAIL")

    def test_anchor_mode_flags_drifting_frame_and_keeps_pair_distinct(self):
        anchor_a = {"file": "a.png", "embedding": vec(0)}
        anchor_b = {"file": "b.png", "embedding": vec(1)}
        records = [
            record(0, [face(vec(0), "A", 0.90), face(vec(1), "B", 0.88)]),
            record(1, [face(vec(0), "A", 0.85), face(vec(1), "B", 0.91)]),
            record(2, [face(vec(2), "A", 0.00), face(vec(1), "B", 0.87)]),
            record(3, [face(vec(0), "A", 0.92), face(vec(1), "B", 0.89)]),
        ]
        report = face_audit.build_report(records, {"A": anchor_a, "B": anchor_b}, T, "clip.mp4", {})

        self.assertEqual(report["identities"]["A"]["verdict"], "FAIL")
        self.assertEqual(report["identities"]["A"]["drift"]["worst_frame"], 2)
        self.assertEqual(report["identities"]["A"]["drift"]["min"], 0.0)
        self.assertEqual(report["identities"]["B"]["verdict"], "PASS")
        self.assertEqual(len(report["pairs"]), 1)
        self.assertEqual(report["pairs"][0]["verdict"], "PASS")
        self.assertEqual(report["pairs"][0]["co_frame_frames"], [0, 1, 2, 3])
        self.assertEqual(report["verdict"], "FAIL")
        self.assertTrue(any("identity drift: A" in finding for finding in report["findings"]))

    def test_anchor_mode_flags_cast_collision(self):
        anchor_a = {"file": "a.png", "embedding": vec(0)}
        anchor_b = {"file": "b.png", "embedding": mix(vec(0), vec(1), 0.95)}
        records = [
            record(0, [face(vec(0), "A", 0.95), face(mix(vec(0), vec(1), 0.95), "B", 0.95)]),
            record(1, [face(vec(0), "A", 0.93), face(mix(vec(0), vec(1), 0.90), "B", 0.94)]),
        ]
        report = face_audit.build_report(records, {"A": anchor_a, "B": anchor_b}, T, "clip.mp4", {})
        self.assertEqual(report["pairs"][0]["verdict"], "FAIL")
        self.assertEqual(report["verdict"], "FAIL")
        self.assertTrue(any("cast collision" in finding for finding in report["findings"]))

    def test_anchor_mode_reports_never_matched_identity(self):
        anchor_a = {"file": "a.png", "embedding": vec(0)}
        anchor_b = {"file": "b.png", "embedding": vec(1)}
        records = [record(0, [face(vec(0), "A", 0.90)])]
        report = face_audit.build_report(records, {"A": anchor_a, "B": anchor_b}, T, "clip.mp4", {})
        self.assertEqual(report["identities"]["B"]["verdict"], "NOT_EVALUATED")
        self.assertEqual(report["verdict"], "REVIEW")
        self.assertTrue(any("never matched" in finding for finding in report["findings"]))

    def test_anchorless_mode_detects_subject_swap(self):
        # The subject is identity A in frames 0, 2, 3 and becomes identity B in
        # frame 1 — the drift series must bottom out exactly at frame 1.
        records = [
            record(0, [face(vec(0))]),
            record(1, [face(vec(1))]),
            record(2, [face(vec(0))]),
            record(3, [face(vec(0))]),
        ]
        report = face_audit.build_report(records, {}, T, "clip.mp4", {})
        subject = report["identities"]["subject"]
        self.assertEqual(subject["verdict"], "FAIL")
        self.assertEqual(subject["drift"]["worst_frame"], 1)
        self.assertEqual(subject["drift"]["min"], 0.0)
        self.assertEqual(report["no_face_frames"], [])

    def test_clean_anchorless_single_subject_can_pass(self):
        report = face_audit.build_report([record(i, [face(vec(0))]) for i in range(3)], {}, T, "clip.mp4", {})
        self.assertEqual(report["unassigned_faces"], [])
        self.assertEqual(report["verdict"], "PASS")

    def test_anchorless_mode_flags_two_shot_collision(self):
        records = [
            record(0, [face(vec(0)), face(mix(vec(0), vec(1), 0.95))]),
            record(1, [face(vec(0)), face(mix(vec(0), vec(1), 0.90))]),
        ]
        report = face_audit.build_report(records, {}, T, "clip.mp4", {})
        self.assertEqual(len(report["pairs"]), 2)
        self.assertTrue(all(pair["verdict"] == "FAIL" for pair in report["pairs"]))

    def test_no_face_frames_and_unassigned_faces_drive_review(self):
        anchor_a = {"file": "a.png", "embedding": vec(0)}
        records = [
            record(0, [face(vec(0), "A", 0.90)]),
            record(1, []),
            record(2, [face(vec(2), None, None)]),
        ]
        report = face_audit.build_report(records, {"A": anchor_a}, T, "clip.mp4", {})
        self.assertEqual(report["no_face_frames"], [1])
        self.assertEqual(len(report["unassigned_faces"]), 1)
        self.assertEqual(report["identities"]["A"]["verdict"], "PASS")
        self.assertEqual(report["verdict"], "REVIEW")


class ModelCacheTests(unittest.TestCase):
    def test_sha256_file_matches_standard_library(self):
        payload = (b"distinct-video-faces\x00" * 100_000) + b"tail"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "model.onnx"
            path.write_bytes(payload)
            self.assertEqual(face_audit.sha256_file(path), hashlib.sha256(payload).hexdigest())

    @unittest.skipUnless(
        os.environ.get("DVF_MODELS_DIR")
        and all(
            (Path(os.environ["DVF_MODELS_DIR"]) / name).is_file()
            for name in face_audit.MODELS
        ),
        "set DVF_MODELS_DIR to a populated model cache to run",
    )
    def test_ensure_model_accepts_cached_files(self):
        models_dir = Path(os.environ["DVF_MODELS_DIR"])
        for name, spec in face_audit.MODELS.items():
            path = face_audit.ensure_model(
                name, spec, models_dir, allow_unverified=False, allow_download=False
            )
            self.assertTrue(path.is_file())


class VisualReportTests(unittest.TestCase):
    def test_missing_pair_detections_render_without_crashing(self):
        report = {"input": "clip.mp4", "frames_evaluated": 1, "model": {"recognizer": "sface:x.onnx", "dimensions": 128}, "thresholds": {}, "notes": "heuristic", "no_face_frames": [], "identities": {}, "pairs": [{"a": "A", "b": "B", "similarity": None, "co_frame_frames": [], "verdict": "NOT_EVALUATED"}], "findings": [], "verdict": "REVIEW"}
        self.assertIn("no comparable detections", face_audit.format_report(report))
        self.assertIn("NOT_EVALUATED", face_audit.build_html(report, []))

    def test_identity_tags_are_stable_and_numbered(self):
        report = {"identities": {"周宁": {}, "Lin Qiao": {}}}
        tags = face_audit.identity_tags(report)
        self.assertEqual(tags, {"Lin Qiao": "0", "周宁": "1"})

    def test_highlight_frames_collect_review_targets(self):
        report = {
            "no_face_frames": [4],
            "identities": {
                "A": {"verdict": "FAIL", "drift": {"worst_frame": 2}, "discontinuity_frames": [1]},
                "B": {"verdict": "PASS", "drift": {"worst_frame": 3}, "discontinuity_frames": []},
            },
            "pairs": [
                {"a": "A", "b": "B", "verdict": "PASS", "co_frame_frames": [0]},
                {"a": "A", "b": "C", "verdict": "REVIEW", "co_frame_frames": [5]},
            ],
        }
        self.assertEqual(face_audit.highlight_frames(report), {1, 2, 4, 5})

    def test_face_label_formats_assigned_and_unmatched(self):
        tags = {"A": "0"}
        self.assertEqual(face_audit.face_label({"identity": "A", "anchor_score": 0.9123}, tags), "0:0.91")
        self.assertEqual(
            face_audit.face_label({"identity": None, "best_anchor": "A", "best_anchor_score": 0.12}, tags),
            "?0:0.12",
        )
        self.assertEqual(face_audit.face_label({"identity": None}, tags), "?")

    def test_build_html_escapes_and_contains_report_parts(self):
        report = {
            "tool": "audit_face_consistency",
            "input": "clip<script>.mp4",
            "frames_evaluated": 2,
            "model": {"recognizer": "sface:x.onnx", "dimensions": 128},
            "thresholds": {"drift_fail": 0.363},
            "notes": "heuristic",
            "no_face_frames": [],
            "identities": {
                "A & B": {
                    "anchor": "a.png",
                    "frames_present": 2,
                    "frames_missing": [],
                    "discontinuity_frames": [],
                    "drift": {"n": 2, "min": 0.9, "mean": 0.95, "max": 1.0, "worst_frame": 1},
                    "verdict": "PASS",
                }
            },
            "pairs": [
                {
                    "a": "A & B",
                    "b": "C",
                    "similarity": {"n": 1, "min": 0.05, "mean": 0.05, "max": 0.05},
                    "co_frame_frames": [0],
                    "verdict": "PASS",
                }
            ],
            "findings": [],
            "verdict": "PASS",
        }
        gallery = [{"frame": 0, "file": "f0.png", "data_uri": "data:image/jpeg;base64,AAA", "labels": ["0:0.95"], "highlight": True}]
        html = face_audit.build_html(report, gallery)
        self.assertIn("A &amp; B", html)  # escaped
        self.assertIn("clip&lt;script&gt;.mp4", html)
        self.assertIn("data:image/jpeg;base64,AAA", html)
        self.assertIn("v-pass", html)
        self.assertIn("card highlight", html)


class BackendTests(unittest.TestCase):
    def test_backends_registry_and_defaults(self):
        self.assertEqual(set(face_audit.BACKENDS), {"sface", "insightface"})
        self.assertEqual(face_audit.SFaceBackend.dimensions, 128)
        self.assertEqual(face_audit.SFaceBackend.default_thresholds["drift_fail"], 0.363)
        self.assertEqual(face_audit.InsightFaceBackend.dimensions, 512)
        # ArcFace's operating point differs from SFace's; the defaults must
        # not silently mix.
        self.assertNotEqual(
            face_audit.SFaceBackend.default_thresholds["drift_fail"],
            face_audit.InsightFaceBackend.default_thresholds["drift_fail"],
        )

    def test_insightface_backend_requires_package(self):
        try:
            import insightface  # noqa: F401
            import onnxruntime  # noqa: F401

            has_extras = True
        except ImportError:
            has_extras = False
        if has_extras:
            self.skipTest("insightface extras installed; error path not reachable")
        with self.assertRaises(face_audit.AuditError):
            face_audit.InsightFaceBackend(None, Path("missing.onnx"))


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from subprocess import CalledProcessError, CompletedProcess
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "direct-distinct-video-faces" / "scripts"


def load_module(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load {name}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


character_audit = load_module("audit_character_pack")
prompt_audit = load_module("audit_prompt_pack")
frame_sampler = load_module("sample_video_frames")


class CharacterAuditTests(unittest.TestCase):
    def test_examples_pass_without_collision(self):
        data = json.loads((ROOT / "examples" / "character-pack.json").read_text(encoding="utf-8"))
        result = character_audit.audit(data)
        self.assertTrue(result["valid"])
        self.assertFalse(any(pair["collision"] for pair in result["pairs"]))
        self.assertGreaterEqual(result["pairs"][0]["uniqueness_score"], 70)

    def test_similar_cast_is_flagged(self):
        data = json.loads((ROOT / "examples" / "character-pack.json").read_text(encoding="utf-8"))
        duplicate = json.loads(json.dumps(data["characters"][0]))
        duplicate["name"] = "Near Duplicate"
        duplicate["identity_lock"] = "A beautiful model face with the same proportions."
        data["characters"].append(duplicate)
        result = character_audit.audit(data)
        self.assertTrue(any(pair["collision"] for pair in result["pairs"]))
        self.assertTrue(any("beauty pressure" in warning for warning in result["warnings"]))

    def test_thresholds_are_configurable(self):
        data = json.loads((ROOT / "examples" / "character-pack.json").read_text(encoding="utf-8"))
        loose = character_audit.audit(data, similar_axis=0.05, collision_axes=1)
        self.assertTrue(any(pair["collision"] for pair in loose["pairs"]))
        strict_unique = character_audit.audit(data, min_uniqueness=95.0)
        self.assertTrue(any(pair["collision"] for pair in strict_unique["pairs"]))
        default = character_audit.audit(data)
        self.assertFalse(any(pair["collision"] for pair in default["pairs"]))

    def test_generic_cjk_anatomy_bigrams_do_not_create_similarity(self):
        # Both descriptions share the anatomical words 下颌/鼻梁; only the
        # distinguishing qualifiers should count as similarity evidence.
        self.assertEqual(character_audit.similarity("宽下颌", "窄下颌"), 0.0)
        self.assertEqual(character_audit.similarity("低鼻梁", "高鼻梁"), 0.0)
        # Identical text is still identical.
        self.assertEqual(character_audit.similarity("低鼻梁", "低鼻梁"), 1.0)
        # Distinctive qualifiers still produce similarity when they match.
        self.assertGreater(character_audit.similarity("宽下颌", "宽下颌骨"), 0.0)
        self.assertNotIn("颌低", character_audit.tokens("宽下颌，低鼻梁"))


class PromptAuditTests(unittest.TestCase):
    def test_duplicate_character_and_invalid_duration_fail(self):
        data = {"characters": [{"name": "A", "identity_lock": "broad lower face"}, {"name": "A", "identity_lock": "narrow lower face"}], "shots": [{"id": "S1", "mode": "image-to-video", "duration_seconds": 0, "characters": ["A"], "references": ["a.png"], "prompt": "A turns.", "preserve": ["jaw"], "avoid": ["drift"]}]}
        result = prompt_audit.audit(data)
        self.assertFalse(result["valid"])
        self.assertTrue(any("Duplicate character" in error for error in result["errors"]))
        self.assertTrue(any("duration_seconds" in error for error in result["errors"]))

    def test_example_prompt_pack_passes(self):
        data = json.loads((ROOT / "examples" / "prompt-pack.json").read_text(encoding="utf-8"))
        result = prompt_audit.audit(data)
        self.assertTrue(result["valid"])
        self.assertEqual(result["warnings"], [])

    def test_missing_text_identity_lock_blocks(self):
        data = {
            "characters": [{"name": "A", "identity_lock": "A has a broad lower face."}],
            "shots": [
                {
                    "id": "S1",
                    "mode": "text-to-video",
                    "duration_seconds": 5,
                    "characters": ["A"],
                    "prompt": "A beautiful woman, pan tilt zoom orbit.",
                    "preserve": [],
                    "avoid": [],
                }
            ],
        }
        result = prompt_audit.audit(data)
        self.assertFalse(result["valid"])
        self.assertTrue(any("literal identity lock" in error for error in result["errors"]))
        self.assertTrue(any("camera moves" in warning for warning in result["warnings"]))

    def test_reworded_identity_lock_warns_instead_of_erroring(self):
        data = {
            "characters": [{"name": "A", "identity_lock": "A has a broad lower face."}],
            "shots": [
                {
                    "id": "S1",
                    "mode": "text-to-video",
                    "duration_seconds": 5,
                    "characters": ["A"],
                    "prompt": "A speaks softly. Broad lower face shape stays still.",
                    "preserve": ["broad lower face"],
                    "avoid": ["jaw narrowing"],
                }
            ],
        }
        result = prompt_audit.audit(data)
        self.assertTrue(result["valid"])
        self.assertTrue(any("appears reworded" in warning for warning in result["warnings"]))

    def test_camera_overload_threshold_is_configurable(self):
        shot = {
            "id": "S1",
            "mode": "image-to-video",
            "characters": ["A"],
            "references": ["a.png"],
            "prompt": "pan tilt zoom across the room.",
            "preserve": ["broad lower face"],
            "avoid": ["jaw narrowing"],
        }
        data = {
            "characters": [{"name": "A", "identity_lock": "A has a broad lower face."}],
            "shots": [{**shot, "duration_seconds": 9}],
        }
        self.assertEqual(prompt_audit.audit(data)["warnings"], [])
        lenient = prompt_audit.audit(data, max_shot_seconds=10.0)
        self.assertTrue(any("camera moves" in warning for warning in lenient["warnings"]))
        many_moves = prompt_audit.audit(data, max_camera_moves=3)
        self.assertEqual(many_moves["warnings"], [])


class FrameSamplerTests(unittest.TestCase):
    def test_probe_duration_falls_back_when_ffprobe_fails(self):
        fallback = CompletedProcess(["ffmpeg"], 1, stdout="", stderr="Duration: 00:00:02.50, start: 0.0")
        with mock.patch.object(frame_sampler.shutil, "which", return_value="ffprobe"), mock.patch.object(frame_sampler.subprocess, "run", side_effect=[CalledProcessError(1, ["ffprobe"]), fallback]):
            self.assertEqual(frame_sampler.probe_duration(Path("clip.mp4")), 2.5)

    def test_extract_frame_tries_fallback_after_failed_seek(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "frame.png"
            calls = 0
            def fake_run(command, **_kwargs):
                nonlocal calls
                calls += 1
                if calls == 2:
                    destination.write_bytes(b"png")
                    return CompletedProcess(command, 0, stdout="", stderr="")
                return CompletedProcess(command, 1, stdout="", stderr="seek failed")
            with mock.patch.object(frame_sampler.subprocess, "run", side_effect=fake_run):
                frame_sampler.extract_frame(Path("clip.mp4"), destination, 9.95)
            self.assertEqual(calls, 2)

    def test_sample_times_include_near_edges_and_midpoint(self):
        times = frame_sampler.sample_times(10.0, 3)
        self.assertEqual(times, [0.05, 5.0, 9.95])

    def test_sample_count_must_be_at_least_three(self):
        with self.assertRaises(ValueError):
            frame_sampler.sample_times(10.0, 2)

    def test_pick_stress_times_excludes_uniform_and_respects_gap(self):
        # 10 s of motion scores at 6 fps: peaks at 2.0 s, 5.0 s, and 7.5 s.
        scores = [0.0] * 61
        scores[12] = 5.0  # t = 2.0 s
        scores[30] = 10.0  # t = 5.0 s — coincides with the uniform midpoint
        scores[45] = 3.0  # t = 7.5 s
        times = frame_sampler.pick_stress_times(
            scores,
            fps=6,
            count=2,
            duration=10.0,
            margin=0.05,
            exclude=[0.05, 5.0, 9.95],
        )
        self.assertEqual(times, [2.0, 7.5])

    def test_pick_stress_times_returns_empty_without_candidates(self):
        times = frame_sampler.pick_stress_times(
            [0.0] * 61, fps=6, count=2, duration=10.0, margin=0.05, exclude=[]
        )
        self.assertEqual(times, [])


if __name__ == "__main__":
    unittest.main()

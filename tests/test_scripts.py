from __future__ import annotations

import importlib.util
import json
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


class PromptAuditTests(unittest.TestCase):
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


class FrameSamplerTests(unittest.TestCase):
    def test_sample_times_include_near_edges_and_midpoint(self):
        times = frame_sampler.sample_times(10.0, 3)
        self.assertEqual(times, [0.05, 5.0, 9.95])

    def test_sample_count_must_be_at_least_three(self):
        with self.assertRaises(ValueError):
            frame_sampler.sample_times(10.0, 2)


if __name__ == "__main__":
    unittest.main()

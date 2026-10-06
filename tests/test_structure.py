from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "direct-distinct-video-faces"


class SkillStructureTests(unittest.TestCase):
    def test_required_files_exist(self):
        self.assertTrue((SKILL / "SKILL.md").is_file())
        self.assertTrue((SKILL / "agents" / "openai.yaml").is_file())
        for script in (
            "audit_character_pack.py",
            "audit_face_consistency.py",
            "audit_prompt_pack.py",
            "sample_video_frames.py",
        ):
            self.assertTrue((SKILL / "scripts" / script).is_file())
        self.assertTrue((SKILL / "requirements-cv.txt").is_file())

    def test_frontmatter_has_name_and_description(self):
        text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        self.assertTrue(text.startswith("---\n"))
        frontmatter = text.split("---", 2)[1]
        self.assertRegex(frontmatter, r"(?m)^name:\s+direct-distinct-video-faces$")
        self.assertRegex(frontmatter, r"(?m)^description:\s+\S")

    def test_local_markdown_references_exist(self):
        text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        targets = re.findall(r"\[[^\]]+\]\(([^)]+)\)", text)
        local_targets = [target for target in targets if "://" not in target]
        self.assertTrue(local_targets)
        for target in local_targets:
            self.assertTrue((SKILL / target).exists(), target)


if __name__ == "__main__":
    unittest.main()

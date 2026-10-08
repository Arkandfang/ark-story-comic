import json
import re
import subprocess
import sys
import unittest
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]


class DistributionReadinessTest(unittest.TestCase):
    def test_storyboard_examples_only_use_bundled_template_ids(self):
        catalog = json.loads(
            (SKILL_ROOT / "assets" / "storyboard-library" / "catalog.json").read_text(
                encoding="utf-8"
            )
        )
        valid_ids = {item["templateId"] for item in catalog["templates"]}
        selection = (SKILL_ROOT / "references" / "storyboard-selection.md").read_text(
            encoding="utf-8"
        )
        referenced_ids = set(re.findall(r"\bSB-\d{3}\b", selection))
        self.assertTrue(referenced_ids)
        self.assertEqual(set(), referenced_ids - valid_ids)
        ranked_ids = set(
            re.findall(r"^\|\s*\d+\s*\|\s*([A-Za-z0-9-]+)\s*\|", selection, re.MULTILINE)
        )
        self.assertTrue(ranked_ids)
        self.assertEqual(set(), ranked_ids - valid_ids)

    def test_entrypoint_declares_image_generation_gate_and_fallback(self):
        skill_text = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("## 运行能力门禁", skill_text)
        self.assertIn("图像生成能力", skill_text)
        self.assertIn("图像编辑能力", skill_text)
        self.assertIn("不能生成最终漫画成片", skill_text)

    def test_end_to_end_smoke_command(self):
        result = subprocess.run(
            [sys.executable, str(SKILL_ROOT / "scripts" / "smoke_test.py")],
            text=True,
            capture_output=True,
        )
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn("ARK_STORY_COMIC_SMOKE_PASS", result.stdout)


if __name__ == "__main__":
    unittest.main()

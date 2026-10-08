import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]


class GenericSkillTest(unittest.TestCase):
    def test_identity_is_generic(self):
        skill_text = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("name: ark-story-comic", skill_text)
        self.assertEqual(
            {
                "project-schema.md",
                "story-design.md",
                "storyboard-library.md",
                "storyboard-selection.md",
                "typesetting-qa.md",
                "visual-assets.md",
                "workflow.md",
            },
            {path.name for path in (SKILL_ROOT / "references").glob("*.md")},
        )

    def test_scaffold_uses_explicit_project_spec_without_optional_baggage(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            project = Path(temp_dir) / "comic"
            subprocess.run(
                [
                    sys.executable,
                    str(SKILL_ROOT / "scripts" / "init_comic_project.py"),
                    str(project),
                    "--title",
                    "测试漫画",
                    "--episode",
                    "episode-01",
                    "--pages",
                    "3",
                    "--width",
                    "900",
                    "--height",
                    "900",
                ],
                check=True,
                text=True,
                capture_output=True,
            )
            episode = project / "episodes" / "episode-01"
            layout = json.loads(
                (episode / "final-v1" / "comic-layout.json").read_text(encoding="utf-8")
            )
            self.assertEqual((900, 900), (layout["width"], layout["height"]))
            self.assertEqual(3, len(layout["pages"]))
            self.assertTrue((episode / "final-v1" / "qa" / "review-preview-pages").is_dir())
            self.assertFalse((episode / "publish").exists())
            self.assertFalse((project / "style-tests").exists())

    def test_optional_scaffold_parts_are_opt_in(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            project = Path(temp_dir) / "comic"
            subprocess.run(
                [
                    sys.executable,
                    str(SKILL_ROOT / "scripts" / "init_comic_project.py"),
                    str(project),
                    "--episode",
                    "episode-01",
                    "--pages",
                    "1",
                    "--width",
                    "1600",
                    "--height",
                    "900",
                    "--with-publish",
                    "--with-style-tests",
                ],
                check=True,
                text=True,
                capture_output=True,
            )
            self.assertTrue((project / "style-tests").is_dir())
            self.assertTrue(
                (project / "episodes" / "episode-01" / "publish" / "release-copy.md").is_file()
            )


if __name__ == "__main__":
    unittest.main()

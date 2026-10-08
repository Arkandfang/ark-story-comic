import json
import subprocess
import sys
import unittest
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
SYNC_SCRIPT = SKILL_ROOT / "scripts" / "sync_handraw_storyboards.py"
SEARCH_SCRIPT = SKILL_ROOT / "scripts" / "search_storyboards.py"


class BundledStoryboardLibraryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dest = SKILL_ROOT / "assets" / "storyboard-library"
        cls.catalog_path = cls.dest / "catalog.json"
        cls.catalog = json.loads(cls.catalog_path.read_text(encoding="utf-8"))

    def test_bundles_all_68_storyboard_recipes(self):
        templates = self.catalog["templates"]
        self.assertEqual(68, len(templates))
        self.assertEqual(
            [f"SB-{index:03d}" for index in range(1, 69)],
            [template["templateId"] for template in templates],
        )
        self.assertEqual("reference-recipe", self.catalog["templateKind"])

    def test_public_skill_is_runtime_independent(self):
        self.assertNotIn("source", self.catalog)
        forbidden_fields = {
            "sourcePath",
            "bundledSource",
            "sourcePreviewPath",
        }
        for template in self.catalog["templates"]:
            self.assertTrue(forbidden_fields.isdisjoint(template))
            self.assertTrue((self.dest / template["preview"]).is_file())
        self.assertFalse((self.dest / "sources").exists())
        self.assertFalse(SYNC_SCRIPT.exists())
        notice = (self.dest / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
        self.assertIn("https://github.com/yang0/handraw-style", notice)

    def test_preserves_prompts_previews_and_attribution(self):
        for template in self.catalog["templates"]:
            self.assertTrue(template["titleZh"])
            self.assertIn("漫画分镜", template["promptZh"])
            self.assertIn("Comic storyboard", template["promptEn"])
            self.assertEqual("reference-only", template["geometryStatus"])
            self.assertNotIn("panels", template)
            self.assertTrue(template["strengths"])
            self.assertIn("capacities", template)
            self.assertIn("requirements", template)
            self.assertIn("risks", template)
            preview = self.dest / template["preview"]
            self.assertTrue(preview.is_file(), preview)
            self.assertGreater(template["previewSize"]["width"], 0)
            self.assertGreater(template["previewSize"]["height"], 0)
            self.assertRegex(template["previewSha256"], r"^[0-9a-f]{64}$")
        self.assertTrue((self.dest / "LICENSE.handraw-style").is_file())
        notice = (self.dest / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
        self.assertIn("yang0", notice)
        self.assertIn("https://github.com/yang0/handraw-style", notice)

    def search(self, query, top=5):
        result = subprocess.run(
            [
                sys.executable,
                str(SEARCH_SCRIPT),
                "--catalog",
                str(self.catalog_path),
                "--query",
                query,
                "--top",
                str(top),
                "--json",
            ],
            check=True,
            text=True,
            capture_output=True,
        )
        return json.loads(result.stdout)

    def test_retrieves_real_candidates_for_different_story_types(self):
        dialogue = self.search("双人日常对白，稳定阅读顺序", top=8)
        chase = self.search("多阶段高速追逐，连续动作和速度感", top=8)
        quiet = self.search("安静诗意的告别，大量留白，低对白", top=5)

        self.assertTrue({"SB-001", "SB-025"} & {x["templateId"] for x in dialogue})
        self.assertTrue(
            {"SB-027", "SB-028", "SB-049"}
            & {x["templateId"] for x in chase}
        )
        self.assertEqual("SB-054", quiet[0]["templateId"])
        for result_set in (dialogue, chase, quiet):
            for candidate in result_set:
                self.assertTrue(candidate["preview"])
                self.assertTrue(candidate["evidence"])
                self.assertEqual("reference-only", candidate["geometryStatus"])
                self.assertNotIn("sourcePath", candidate)
                self.assertNotIn("bundledSource", candidate)
                self.assertNotIn("sourcePreviewPath", candidate)

    def test_supports_hard_positive_and_negative_filters(self):
        result = subprocess.run(
            [
                sys.executable,
                str(SEARCH_SCRIPT),
                "--catalog",
                str(self.catalog_path),
                "--query",
                "安静诗意告别，克制留白",
                "--require-tag",
                "quiet",
                "--exclude-tag",
                "impact",
                "--forbid-requirement",
                "preceding-intensity",
                "--top",
                "10",
                "--json",
            ],
            check=True,
            text=True,
            capture_output=True,
        )
        candidates = json.loads(result.stdout)
        self.assertEqual("SB-054", candidates[0]["templateId"])
        self.assertTrue(all("quiet" in item["tags"] for item in candidates))
        self.assertTrue(all("impact" not in item["tags"] for item in candidates))
        self.assertTrue(
            all(
                "preceding-intensity" not in item["requirements"]
                for item in candidates
            )
        )

    def test_does_not_pad_results_with_zero_score_candidates(self):
        candidates = self.search("双人面对面对话", top=68)
        self.assertTrue(candidates)
        self.assertTrue(all(item["score"] > 0 for item in candidates))
        self.assertLess(len(candidates), 68)

    def test_uses_capacity_filters_and_requirement_aliases(self):
        result = subprocess.run(
            [
                sys.executable,
                str(SEARCH_SCRIPT),
                "--catalog",
                str(self.catalog_path),
                "--query",
                "安静诗意留白",
                "--dialogue-density",
                "none",
                "--forbid-requirement",
                "preceding-intensity",
                "--top",
                "20",
                "--json",
            ],
            check=True,
            text=True,
            capture_output=True,
        )
        candidates = json.loads(result.stdout)
        ids = {item["templateId"] for item in candidates}
        self.assertIn("SB-054", ids)
        self.assertNotIn("SB-030", ids)
        self.assertNotIn("SB-031", ids)
        sb054 = next(
            item for item in self.catalog["templates"] if item["templateId"] == "SB-054"
        )
        self.assertEqual(
            ["none", "low"], sb054["capacities"]["recommendedDialogueDensity"]
        )

    def test_rejects_unknown_filter_names(self):
        result = subprocess.run(
            [
                sys.executable,
                str(SEARCH_SCRIPT),
                "--catalog",
                str(self.catalog_path),
                "--query",
                "对白",
                "--require-tag",
                "not-a-real-tag",
                "--json",
            ],
            text=True,
            capture_output=True,
        )
        self.assertNotEqual(0, result.returncode)
        self.assertIn("unknown tag", result.stderr)

if __name__ == "__main__":
    unittest.main()

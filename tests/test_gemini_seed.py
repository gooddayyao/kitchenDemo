"""Tests for Gemini seed JSON parsing (no API call)."""

from __future__ import annotations

import unittest

from src.gemini_seed import SeedObject, clamp_seeds_to_unit, parse_gemini_objects


class GeminiSeedParseTests(unittest.TestCase):
    def test_parse_objects_normalized(self) -> None:
        payload = {
            "objects": [
                {
                    "id": "cucumber",
                    "label": "小黃瓜",
                    "confidence": 0.9,
                    "bbox": {"x": 0.1, "y": 0.2, "w": 0.5, "h": 0.25},
                }
            ]
        }
        seeds = parse_gemini_objects(payload)
        self.assertEqual(len(seeds), 1)
        self.assertEqual(seeds[0].ingredient_id, "cucumber")
        self.assertAlmostEqual(seeds[0].x, 0.1)
        self.assertAlmostEqual(seeds[0].w, 0.5)

    def test_chinese_alias(self) -> None:
        payload = {
            "objects": [
                {"name": "小黃瓜", "bbox": {"x": 0.2, "y": 0.2, "w": 0.3, "h": 0.2}}
            ]
        }
        seeds = parse_gemini_objects(payload)
        self.assertEqual(seeds[0].ingredient_id, "cucumber")

    def test_xyxy_list(self) -> None:
        payload = {"objects": [{"id": "apple", "bbox": [0.1, 0.1, 0.4, 0.5]}]}
        seeds = parse_gemini_objects(payload)
        self.assertEqual(seeds[0].ingredient_id, "apple")
        self.assertAlmostEqual(seeds[0].w, 0.3, places=3)
        self.assertAlmostEqual(seeds[0].h, 0.4, places=3)

    def test_pixel_clamp(self) -> None:
        seed = SeedObject("cucumber", "小黃瓜", 0.8, 100, 50, 200, 80)
        fixed = clamp_seeds_to_unit([seed], 400, 300)
        self.assertAlmostEqual(fixed[0].x, 100 / 400)
        self.assertAlmostEqual(fixed[0].w, 200 / 400)

    def test_to_detection(self) -> None:
        seed = SeedObject("cucumber", "小黃瓜", 0.8, 0.25, 0.25, 0.5, 0.5)
        det = seed.to_detection(200, 100)
        self.assertEqual(det.name, "cucumber")
        self.assertAlmostEqual(det.x1, 50)
        self.assertAlmostEqual(det.y2, 75)


if __name__ == "__main__":
    unittest.main()

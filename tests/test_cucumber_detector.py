"""Unit tests for green cucumber heuristic detector."""

from __future__ import annotations

import unittest

import numpy as np

from src.cucumber_detector import detect_cucumber


class CucumberDetectorTests(unittest.TestCase):
    def test_finds_green_elongated_blob(self) -> None:
        img = np.zeros((240, 320, 3), dtype=np.uint8)
        # BGR green cucumber-like bar
        img[100:140, 40:280] = (40, 180, 40)
        dets = detect_cucumber(img, min_area_ratio=0.005, min_aspect=1.5)
        self.assertEqual(len(dets), 1)
        self.assertEqual(dets[0].name, "cucumber")
        self.assertGreater(dets[0].x2 - dets[0].x1, dets[0].y2 - dets[0].y1)
        self.assertIsNotNone(dets[0].contour)
        self.assertGreaterEqual(len(dets[0].contour), 3)

    def test_empty_on_blank(self) -> None:
        img = np.zeros((240, 320, 3), dtype=np.uint8)
        self.assertEqual(detect_cucumber(img), [])


if __name__ == "__main__":
    unittest.main()

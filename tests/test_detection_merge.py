"""Tests for produce vs YOLO conflict merge."""

from __future__ import annotations

import unittest

import numpy as np

from src.detection_merge import merge_produce_and_yolo
from src.recipe_manager import Detection


class DetectionMergeTests(unittest.TestCase):
    def test_suppresses_knife_overlapping_cucumber(self) -> None:
        frame = np.zeros((200, 300, 3), dtype=np.uint8)
        frame[80:120, 40:260] = (40, 180, 40)
        cucumber = Detection("cucumber", 0.9, 40, 80, 260, 120)
        knife = Detection("knife", 0.95, 50, 85, 250, 115)
        out = merge_produce_and_yolo(frame, [cucumber], [knife])
        names = [d.name for d in out]
        self.assertIn("cucumber", names)
        self.assertNotIn("knife", names)

    def test_rejects_green_knife_without_cucumber(self) -> None:
        frame = np.zeros((200, 300, 3), dtype=np.uint8)
        frame[80:120, 40:260] = (40, 180, 40)
        knife = Detection("knife", 0.9, 40, 80, 260, 120)
        out = merge_produce_and_yolo(frame, [], [knife])
        self.assertEqual(out, [])

    def test_keeps_apple(self) -> None:
        frame = np.zeros((200, 300, 3), dtype=np.uint8)
        apple = Detection("apple", 0.9, 10, 10, 60, 60)
        out = merge_produce_and_yolo(frame, [], [apple])
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0].name, "apple")


if __name__ == "__main__":
    unittest.main()

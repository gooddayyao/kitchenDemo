"""Tests for CSRT multi-object tracker (offline, synthetic frames)."""

from __future__ import annotations

import unittest

import numpy as np

from src.object_tracker import MultiObjectTracker, _create_tracker
from src.recipe_manager import Detection


class ObjectTrackerTests(unittest.TestCase):
    def test_create_tracker_available(self) -> None:
        tracker = _create_tracker()
        self.assertIsNotNone(tracker)

    def test_seed_and_update(self) -> None:
        frame = np.zeros((240, 320, 3), dtype=np.uint8)
        # Bright rectangle to track
        frame[80:140, 100:180] = (0, 220, 0)
        det = Detection("cucumber", 0.9, 100, 80, 180, 140)
        multi = MultiObjectTracker(max_lose_frames=5)
        n = multi.seed_from_detections(frame, [det])
        self.assertEqual(n, 1)
        # Shift blob slightly and update
        frame2 = np.zeros_like(frame)
        frame2[85:145, 110:190] = (0, 220, 0)
        outs = multi.update(frame2)
        self.assertEqual(len(outs), 1)
        self.assertEqual(outs[0].name, "cucumber")
        self.assertFalse(multi.target_lost("cucumber"))


if __name__ == "__main__":
    unittest.main()

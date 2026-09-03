"""Lock detections at high confidence and sample glow color."""

from __future__ import annotations

import unittest

import numpy as np

from src.detection_lock import DetectionLock, dominant_bgr
from src.recipe_manager import Detection


class DetectionLockTests(unittest.TestCase):
    def test_dominant_color_is_green(self) -> None:
        frame = np.zeros((120, 200, 3), dtype=np.uint8)
        frame[30:90, 40:160] = (30, 190, 40)
        det = Detection("cucumber", 0.8, 40, 30, 160, 90)
        b, g, r = dominant_bgr(frame, det)
        self.assertGreater(g, b)
        self.assertGreater(g, r)

    def test_locks_at_threshold_and_follows_later_box(self) -> None:
        locker = DetectionLock(min_conf=0.7)
        frame = np.zeros((120, 160, 3), dtype=np.uint8)
        frame[20:80, 20:80] = (20, 180, 30)
        first = Detection("cucumber", 0.74, 20, 20, 80, 80)
        out = locker.update(frame, [first])
        locked = [d for d in out if d.locked]
        self.assertEqual(len(locked), 1)
        glow = locked[0].glow_color

        frame2 = np.zeros((120, 160, 3), dtype=np.uint8)
        frame2[40:100, 50:120] = (20, 180, 30)
        moved = Detection("cucumber", 0.91, 50, 40, 120, 100)
        out2 = locker.update(frame2, [moved])
        cucumber = [d for d in out2 if d.name == "cucumber"]
        self.assertEqual(len(cucumber), 1)
        self.assertTrue(cucumber[0].locked)
        self.assertEqual(cucumber[0].glow_color, glow)
        self.assertGreater(cucumber[0].x1, first.x1)
        self.assertGreater(cucumber[0].y1, first.y1)
        self.assertIn("cucumber", locker.locked_names)

    def test_drops_lock_when_object_missing(self) -> None:
        locker = DetectionLock(min_conf=0.7, lost_sec=0.5)
        frame = np.zeros((120, 160, 3), dtype=np.uint8)
        frame[20:80, 20:80] = (20, 180, 30)
        first = Detection("cucumber", 0.8, 20, 20, 80, 80)
        locker.update(frame, [first], detections_fresh=True, now=1.0)
        self.assertIn("cucumber", locker.locked_names)

        empty = np.zeros((120, 160, 3), dtype=np.uint8)
        locker.update(empty, [], detections_fresh=True, now=1.2)
        self.assertIn("cucumber", locker.locked_names)
        out = locker.update(empty, [], detections_fresh=True, now=1.8)
        self.assertEqual(locker.locked_names, set())
        self.assertEqual([d for d in out if d.locked], [])

    def test_below_threshold_stays_live(self) -> None:
        locker = DetectionLock(min_conf=0.7)
        frame = np.zeros((80, 80, 3), dtype=np.uint8)
        weak = Detection("cucumber", 0.55, 10, 10, 40, 40)
        out = locker.update(frame, [weak])
        self.assertFalse(out[0].locked)
        self.assertEqual(locker.locked_names, set())

    def test_does_not_lock_confirm_mouse(self) -> None:
        locker = DetectionLock(min_conf=0.7)
        frame = np.zeros((80, 80, 3), dtype=np.uint8)
        mouse = Detection("mouse", 0.99, 5, 5, 25, 25)
        out = locker.update(frame, [mouse])
        self.assertFalse(out[0].locked)
        self.assertEqual(locker.locked_names, set())


if __name__ == "__main__":
    unittest.main()

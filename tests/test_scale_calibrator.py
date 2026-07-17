"""Unit tests for plane scale / cut-line spacing (no camera required)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.scale_calibrator import PlaneScale, compute_mm_per_px, cut_line_positions


class ScaleCalibratorTests(unittest.TestCase):
    def test_compute_mm_per_px_axis_aligned(self) -> None:
        # 400x300 px board = 40x30 cm → 1 px = 1 mm
        corners = [(0, 0), (400, 0), (400, 300), (0, 300)]
        mm_per_px = compute_mm_per_px(corners, width_mm=400.0, height_mm=300.0)
        self.assertAlmostEqual(mm_per_px, 1.0, places=5)

    def test_compute_mm_per_px_40x30_cm(self) -> None:
        # Same pixel rectangle, real size 40x30 cm
        corners = [(10, 20), (410, 20), (410, 320), (10, 320)]
        mm_per_px = compute_mm_per_px(corners, width_mm=400.0, height_mm=300.0)
        self.assertAlmostEqual(mm_per_px, 1.0, places=5)

    def test_cut_line_positions_1cm(self) -> None:
        # 150 px length, 10 mm spacing at 1 mm/px → lines at 10,20,...,140
        pos = cut_line_positions(150.0, 10.0)
        self.assertEqual(pos[0], 10.0)
        self.assertEqual(pos[-1], 140.0)
        self.assertEqual(len(pos), 14)

    def test_cut_line_positions_empty_when_too_small(self) -> None:
        self.assertEqual(cut_line_positions(8.0, 10.0), [])

    def test_plane_scale_roundtrip(self) -> None:
        scale = PlaneScale(
            mm_per_px=0.5,
            width_mm=400.0,
            height_mm=300.0,
            corners=[(0, 0), (800, 0), (800, 600), (0, 600)],
            frame_w=1280,
            frame_h=720,
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "scale.json"
            scale.save(path)
            loaded = PlaneScale.load(path)
            assert loaded is not None
            self.assertAlmostEqual(loaded.mm_per_px, 0.5)
            self.assertEqual(len(loaded.corners), 4)


if __name__ == "__main__":
    unittest.main()

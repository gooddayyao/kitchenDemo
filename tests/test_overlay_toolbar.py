"""Toolbar layout / hit-testing / object outline (no camera required)."""

from __future__ import annotations

import unittest

import cv2
import numpy as np

from src.overlay_renderer import OverlayRenderer, hit_toolbar, layout_toolbar
from src.recipe_manager import Detection


class OverlayToolbarTests(unittest.TestCase):
    def test_layout_has_all_shortcut_actions(self) -> None:
        buttons = layout_toolbar(1280)
        ids = [b["id"] for b in buttons]
        self.assertEqual(ids, ["restart", "calibrate", "next", "quit"])
        self.assertTrue(all(b["y"] < 52 for b in buttons))

    def test_hit_toolbar(self) -> None:
        buttons = layout_toolbar(1280)
        first = buttons[0]
        last = buttons[-1]
        self.assertEqual(hit_toolbar(buttons, first["x"] + 4, first["y"] + 4), "restart")
        self.assertEqual(hit_toolbar(buttons, last["x"] + 4, last["y"] + 4), "quit")
        self.assertIsNone(hit_toolbar(buttons, 2, 2))
        self.assertIsNone(hit_toolbar(buttons, first["x"] + 4, 200))


class OverlayOutlineTests(unittest.TestCase):
    def test_extracts_green_blob_silhouette(self) -> None:
        frame = np.full((240, 320, 3), 36, dtype=np.uint8)
        cv2.ellipse(frame, (160, 120), (90, 28), 18, 0, 360, (40, 180, 60), -1)
        det = Detection(
            name="cucumber",
            conf=0.92,
            x1=55.0,
            y1=78.0,
            x2=265.0,
            y2=162.0,
            locked=True,
            glow_color=(30, 220, 70),
        )
        renderer = OverlayRenderer()
        pts = renderer._extract_outline(frame, det)
        self.assertIsNotNone(pts)
        assert pts is not None
        self.assertEqual(len(pts), 48)
        self.assertAlmostEqual(float(pts[:, 0].mean()), 160.0, delta=22)
        self.assertAlmostEqual(float(pts[:, 1].mean()), 120.0, delta=18)

        out = renderer.render(frame, [det])
        self.assertEqual(out.shape, frame.shape)


class OverlayErrorBannerTests(unittest.TestCase):
    def test_error_banner_changes_top_bar(self) -> None:
        frame = np.full((240, 640, 3), 22, dtype=np.uint8)
        out = OverlayRenderer().render(
            frame, [], error_message="無法開啟鏡頭 index 0"
        )
        self.assertEqual(out.shape, frame.shape)
        band = out[52:90, :, :]
        self.assertGreater(int(band[:, :, 2].mean()), int(band[:, :, 0].mean()))


if __name__ == "__main__":
    unittest.main()

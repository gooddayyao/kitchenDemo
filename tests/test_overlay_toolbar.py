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
        self.assertEqual(ids, ["restart", "calibrate", "toggle_camera", "next", "quit"])
        self.assertTrue(all(b["y"] < 52 for b in buttons))

    def test_toggle_camera_label(self) -> None:
        shown = layout_toolbar(1280, show_camera=True)
        hidden = layout_toolbar(1280, show_camera=False)
        cam_on = next(b for b in shown if b["id"] == "toggle_camera")
        cam_off = next(b for b in hidden if b["id"] == "toggle_camera")
        self.assertEqual(cam_on["label"], "隱藏相機")
        self.assertEqual(cam_off["label"], "顯示相機")

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
        self.assertGreaterEqual(len(pts), 80)
        self.assertLessEqual(len(pts), 256)
        self.assertAlmostEqual(float(pts[:, 0].mean()), 160.0, delta=22)
        self.assertAlmostEqual(float(pts[:, 1].mean()), 120.0, delta=18)

        out = renderer.render(frame, [det])
        self.assertEqual(out.shape, frame.shape)

    def test_hide_camera_keeps_marks_without_video_pixels(self) -> None:
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
        renderer.show_camera = False
        out = renderer.render(frame, [det], draw_cut_lines=False)
        self.assertEqual(out.shape, frame.shape)
        # Live cucumber green (~180) should be gone; blank board + soft wash only.
        self.assertLess(int(out[120, 160, 1]), 120)
        # Soft glow / rim still boosts green somewhere in the bbox.
        roi = out[78:162, 55:265]
        self.assertGreater(int(roi[:, :, 1].max()), 150)
        with_cuts = renderer.render(frame, [det], draw_cut_lines=True)
        self.assertGreater(int(with_cuts[:, :, 1].max()), int(out[:, :, 1].max()) - 5)


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

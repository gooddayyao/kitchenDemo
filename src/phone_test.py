"""
KITCHEN Phase 1 — phone / local-video AR preview.

Usage:
  python -m src.phone_test --source path/to/video.mp4
  python -m src.phone_test --source 0
  python -m src.phone_test --source rtsp://192.168.x.x:8080/h264_ulaw.sdp
  # IP Webcam HTTP (lower latency than browser page; still prefer RTSP if available):
  python -m src.phone_test --source http://192.168.x.x:8080/video

Low-latency tips (IP Webcam):
  - Video Preferences: 640x480, FPS 10–15, JPEG quality ~50
  - Use /video or RTSP, not the web browser preview page
  - Same 5GHz Wi-Fi; disable phone power-saving for the app

Keys:
  Physical mouse in green zone ~2s — confirm / next step (YOLO class "mouse")
  N / Space  — manual confirm / next step
  Q / ESC / window X  — quit
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import cv2

# Allow `python src/phone_test.py` as well as `python -m src.phone_test`
if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import config
from src.detector import Detector
from src.overlay_renderer import OverlayRenderer
from src.recipe_manager import RecipeManager
from src.stream_reader import StreamReader


def window_closed(window_name: str) -> bool:
    """True when user clicked the window X (OpenCV does not stop the loop by itself)."""
    try:
        # After X is clicked, property becomes < 1 on most backends.
        prop = cv2.getWindowProperty(window_name, cv2.WND_PROP_VISIBLE)
        return prop < 1
    except cv2.error:
        return True


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="KITCHEN Phase 1 AR preview (YOLOv8 + OpenCV)")
    p.add_argument(
        "--source",
        default=str(config.DEFAULT_SOURCE),
        help="Webcam index, video file path, or RTSP/HTTP URL",
    )
    p.add_argument(
        "--recipe",
        default=str(config.DEFAULT_CV_RECIPE),
        help="KITCHEN CV recipe JSON path",
    )
    p.add_argument("--model", default=config.YOLO_MODEL, help="Ultralytics model weights")
    p.add_argument("--conf", type=float, default=config.YOLO_CONF, help="YOLO confidence")
    p.add_argument("--no-loop", action="store_true", help="Do not loop local video files")
    p.add_argument("--device", default=None, help="YOLO device, e.g. cpu / 0")
    p.add_argument(
        "--detect-every",
        type=int,
        default=2,
        help="Run YOLO every N frames (default 2). Higher = less lag / lower CPU.",
    )
    p.add_argument(
        "--infer-width",
        type=int,
        default=640,
        help="Resize width before YOLO (0 = full res). Lower = faster, less lag.",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    recipe_path = Path(args.recipe)
    if not recipe_path.exists():
        print(f"Recipe not found: {recipe_path}", file=sys.stderr)
        return 1

    manager = RecipeManager.from_path(recipe_path)
    renderer = OverlayRenderer()
    print(f"Loading YOLO model: {args.model} …")
    detector = Detector(model_name=args.model, conf=args.conf, device=args.device)
    print(f"Recipe: {manager.name}")
    print(f"Source: {args.source}")
    print("PoC class map:", config.POC_CLASS_MAP)
    print(f"Latency: detect_every={args.detect_every}, infer_width={args.infer_width}")

    try:
        stream = StreamReader(args.source, loop_file=not args.no_loop, low_latency=True)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        print(
            "Hint: for no-camera dev, pass --source path/to/video.mp4 "
            "(use banana/apple footage for PoC).",
            file=sys.stderr,
        )
        return 1

    cv2.namedWindow(config.WINDOW_NAME, cv2.WINDOW_NORMAL)
    last_log = 0.0
    frame_i = 0
    detections = []
    detect_every = max(1, args.detect_every)

    try:
        while True:
            if window_closed(config.WINDOW_NAME):
                break

            ok, frame = stream.read()
            if not ok or frame is None:
                if stream._is_file and args.no_loop:
                    break
                key = cv2.waitKey(30) & 0xFF
                if key in (27, ord("q")) or window_closed(config.WINDOW_NAME):
                    break
                continue

            h, w = frame.shape[:2]
            step = manager.current_step()
            yolo_target = manager.resolve_yolo_class(step.get("target_ingredient") if step else None)
            class_filter = list(config.DETECT_CLASSES)

            frame_i += 1
            if frame_i % detect_every == 0:
                infer = frame
                scale = 1.0
                if args.infer_width and w > args.infer_width:
                    scale = args.infer_width / float(w)
                    infer = cv2.resize(frame, (args.infer_width, int(h * scale)))
                detections = detector.detect(infer, class_filter=class_filter)
                if scale != 1.0:
                    inv = 1.0 / scale
                    for d in detections:
                        d.x1 *= inv
                        d.y1 *= inv
                        d.x2 *= inv
                        d.y2 *= inv

            manager.update(detections, w, h)

            step = manager.current_step()
            draw_cuts = bool(step and step.get("guide_lines"))
            step_label = (
                f"{manager.name}  ·  step {manager.current_index + 1}/"
                f"{len(manager.recipe.get('steps') or [])}"
                if step
                else f"{manager.name}  ·  done"
            )
            hold = manager.hold_progress
            if manager.mouse_confirm_progress > hold:
                hold = manager.mouse_confirm_progress
            overlay = renderer.render(
                frame,
                detections,
                highlight_class=yolo_target,
                draw_cut_lines=draw_cuts,
                dropzone=manager.dropzone,
                instruction=manager.message,
                step_label=step_label,
                timer_remaining=manager.timer_remaining,
                hold_progress=hold if hold > 0 else None,
            )

            cv2.imshow(config.WINDOW_NAME, overlay)
            now = time.monotonic()
            if now - last_log > 2.0:
                names = [f"{d.name}:{d.conf:.2f}" for d in detections]
                print(f"[{step_label}] dets={names or '-'} hold={manager.hold_progress:.2f}")
                last_log = now

            key = cv2.waitKey(1) & 0xFF
            if key in (27, ord("q")) or window_closed(config.WINDOW_NAME):
                break
            if key in (ord("n"), ord("N"), 32):  # Space
                manager.confirm()
                if manager.is_finished():
                    print("Recipe finished.")
    except KeyboardInterrupt:
        print("\nInterrupted.")
    finally:
        stream.release()
        cv2.destroyAllWindows()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

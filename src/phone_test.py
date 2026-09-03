"""
KITCHEN Phase 1 — phone / local-video / webcam AR preview.

Usage:
  # Easiest on Windows: double-click start-webcam.bat
  start-webcam.bat
  start-webcam.bat 1
  start-webcam.bat --list

  python -m src.phone_test --webcam
  python -m src.phone_test --webcam 1
  python -m src.phone_test --list-cameras
  python -m src.phone_test --source path/to/video.mp4
  python -m src.phone_test --source rtsp://192.168.x.x:8080/h264_ulaw.sdp
  python -m src.phone_test --source http://192.168.x.x:8080/video

Low-latency tips (IP Webcam):
  - Video Preferences: 640x480, FPS 10–15, JPEG quality ~50
  - Use /video or RTSP, not the web browser preview page
  - Same 5GHz Wi-Fi; disable phone power-saving for the app

Keys / on-screen buttons (top row):
  重新開始 (R)     — restart demo from step 1
  校正尺度 (C)     — calibrate cutting-board scale
  下一步 (N/Space) — manual confirm / next step
  離開 (Q/ESC)     — quit
  G              — Gemini re-identify (when --gemini-track)
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import List, Optional

import cv2
import numpy as np

# Allow `python src/phone_test.py` as well as `python -m src.phone_test`
if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import config
from src.detection_lock import DetectionLock
from src.detection_merge import merge_produce_and_yolo
from src.detector import Detector
from src.gemini_seed import seed_from_frame
from src.ingredient_catalog import label_for, summarize_detectable, yolo_class_names
from src.object_tracker import MultiObjectTracker
from src.overlay_renderer import OverlayRenderer
from src.recipe_manager import Detection, RecipeManager
from src.scale_calibrator import PlaneScale, ScaleCalibrator
from src.stream_reader import StreamReader, is_image_source, parse_source
from services.gemini_client import get_api_key


def key_to_action(key: int) -> Optional[str]:
    if key in (27, ord("q"), ord("Q")):
        return "quit"
    if key in (ord("r"), ord("R")):
        return "restart"
    if key in (ord("c"), ord("C")):
        return "calibrate"
    if key in (ord("n"), ord("N"), 32):
        return "next"
    return None


def window_closed(window_name: str) -> bool:
    """True when user clicked the window X (OpenCV does not stop the loop by itself)."""
    try:
        # After X is clicked, property becomes < 1 on most backends.
        prop = cv2.getWindowProperty(window_name, cv2.WND_PROP_VISIBLE)
        return prop < 1
    except cv2.error:
        return True


def list_cameras(max_index: int = 6) -> List[int]:
    """Probe local camera indices; return those that open and return a frame."""
    # Silence OpenCV noise while probing missing indices (DSHOW/obsensor spam).
    prev_level = None
    try:
        prev_level = cv2.utils.logging.getLogLevel()
        cv2.utils.logging.setLogLevel(cv2.utils.logging.LOG_LEVEL_SILENT)
    except Exception:
        pass

    found: List[int] = []
    try:
        for i in range(max_index):
            backends = []
            if hasattr(cv2, "CAP_DSHOW"):
                backends.append(cv2.CAP_DSHOW)
            backends.append(cv2.CAP_ANY)
            for backend in backends:
                cap = cv2.VideoCapture(i, backend)
                if not cap.isOpened():
                    cap.release()
                    continue
                ok, frame = cap.read()
                cap.release()
                if ok and frame is not None:
                    found.append(i)
                    break
    finally:
        if prev_level is not None:
            try:
                cv2.utils.logging.setLogLevel(prev_level)
            except Exception:
                pass
    return found


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="KITCHEN Phase 1 AR preview (YOLOv8 + OpenCV)")
    p.add_argument(
        "--source",
        default=None,
        help="Webcam index, video file path, or RTSP/HTTP URL (default: 0 if no --webcam)",
    )
    p.add_argument(
        "--webcam",
        nargs="?",
        const="0",
        default=None,
        metavar="INDEX",
        help="Use PC / USB webcam (default index 0). Example: --webcam 1",
    )
    p.add_argument(
        "--list-cameras",
        action="store_true",
        help="List available local webcam indices and exit",
    )
    p.add_argument(
        "--recipe",
        default=str(config.DEFAULT_CV_RECIPE),
        help="Recipe JSON path (CookingRecipe or KITCHEN CV)",
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
    p.add_argument(
        "--calibrate",
        action="store_true",
        help="Force cutting-board scale calibration at startup",
    )
    p.add_argument(
        "--image",
        default=None,
        metavar="PATH",
        help="Use a still image of cucumber (jpg/png). Skips YOLO; treats image as cucumber.",
    )
    p.add_argument(
        "--gemini-track",
        action="store_true",
        help="Keyframe Gemini identify + local CSRT tracking (skips YOLO). Needs GEMINI_API_KEY.",
    )
    return p


def resolve_source(args: argparse.Namespace) -> str:
    if args.image is not None:
        return str(args.image)
    if args.webcam is not None:
        return str(args.webcam)
    if args.source is not None:
        return str(args.source)
    return str(config.DEFAULT_SOURCE)


def synthetic_cucumber(frame) -> Detection:
    """Place an elongated cucumber bbox at frame center for image demos."""
    h, w = frame.shape[:2]
    bw = max(40, int(w * 0.55))
    bh = max(24, int(h * 0.20))
    cx, cy = w // 2, int(h * 0.55)
    return Detection(
        name="cucumber",
        conf=0.99,
        x1=float(cx - bw // 2),
        y1=float(cy - bh // 2),
        x2=float(cx + bw // 2),
        y2=float(cy + bh // 2),
    )


def _read_frame(stream: StreamReader):
    ok, frame = stream.read()
    if ok and frame is not None:
        return frame
    return None


def describe_stream_error(
    source: object,
    detail: Optional[str] = None,
    *,
    no_frame: bool = False,
) -> str:
    src = str(source)
    extra = (detail or "").strip()
    if src.startswith(("http://", "https://", "rtsp://", "rtsps://")):
        if no_frame:
            return f"相機沒有畫面：{src}。請確認 IP Webcam 已按 Start、IP 正確、與電腦同一網路。"
        return f"無法連接手機畫面：{src}。請確認手機已開始串流。"
    if src.isdigit():
        if no_frame:
            return f"鏡頭 index {src} 沒有畫面。請檢查是否被占用，或 Windows 相機隱私權。"
        return f"無法開啟鏡頭 index {src}。可執行 start-webcam.bat --list 查看可用鏡頭。"
    if no_frame:
        return f"影像來源沒有畫面：{src}。"
    return f"無法開啟影像來源 {src}" + (f"：{extra}" if extra else "。")


def placeholder_frame(width: int = 1280, height: int = 720) -> "np.ndarray":
    return np.full((height, width, 3), 22, dtype=np.uint8)


def wait_for_frame(stream: StreamReader, timeout_sec: float = 20.0):
    """Block until the stream delivers a real frame (important for phone IP Webcam)."""
    if not stream.is_ready():
        return None

    deadline = time.monotonic() + timeout_sec
    last_log = 0.0
    while time.monotonic() < deadline:
        frame = _read_frame(stream)
        if frame is not None:
            return frame
        now = time.monotonic()
        if now - last_log > 2.0:
            print("[stream] waiting for first camera frame…")
            last_log = now
        time.sleep(0.05)
    return None


def run_scale_calibration(stream: StreamReader) -> Optional[PlaneScale]:
    # Same window as main preview so the camera feed is visible while calibrating.
    calibrator = ScaleCalibrator(window_name=config.WINDOW_NAME)
    return calibrator.run(lambda: _read_frame(stream))


def gemini_reseed(
    frame,
    tracker: MultiObjectTracker,
    manager: RecipeManager,
    *,
    reason: str,
) -> str:
    """Ask Gemini on this keyframe and (re)init CSRT trackers. Returns status text."""
    step = manager.current_step()
    focus = []
    if step and step.get("target_ingredient"):
        focus.append(str(step["target_ingredient"]))
    for ing in manager.required_ingredients():
        iid = str(ing.get("id") or "")
        if iid and iid not in focus:
            focus.append(iid)

    hint = step.get("instruction") if step else None
    tracker.status = "seeding"
    print(f"[gemini] seeding ({reason}) …")
    try:
        seeds = seed_from_frame(frame, focus_ids=focus or None, hint=hint)
    except Exception as exc:
        tracker.last_seed_error = str(exc)
        tracker.status = "lost"
        msg = f"Gemini 失敗：{exc}"
        print(f"[gemini] {msg}")
        return msg

    h, w = frame.shape[:2]
    dets = [s.to_detection(w, h) for s in seeds]
    n = tracker.seed_from_detections(frame, dets)
    names = ", ".join(f"{s.ingredient_id}/{s.label}" for s in seeds) or "(none)"
    msg = f"Gemini 鎖定 {n} 個：{names}"
    print(f"[gemini] {msg}")
    tracker.last_seed_error = ""
    return msg


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.list_cameras:
        print("Scanning local cameras (index 0–5)…")
        found = list_cameras()
        if not found:
            print("No cameras found. Check USB connection / privacy settings.")
            return 1
        print("Available camera index(es):", ", ".join(str(i) for i in found))
        print("Launch with:  start-webcam.bat <index>")
        print("         or:  python -m src.phone_test --webcam <index>")
        return 0

    source = resolve_source(args)
    recipe_path = Path(args.recipe)
    if not recipe_path.exists():
        print(f"Recipe not found: {recipe_path}", file=sys.stderr)
        return 1

    manager = RecipeManager.from_path(recipe_path)
    renderer = OverlayRenderer()
    locker = DetectionLock()
    image_demo = is_image_source(parse_source(source))
    gemini_track = bool(args.gemini_track)

    tracker: Optional[MultiObjectTracker] = None
    if gemini_track:
        if not get_api_key():
            print(
                "[gemini-track] GEMINI_API_KEY is not set. "
                "Set it then re-run with --gemini-track.",
                file=sys.stderr,
            )
            return 1
        print("[gemini-track] Mode ON — Gemini keyframe seed + CSRT (YOLO skipped).")
        tracker = MultiObjectTracker(max_lose_frames=config.GEMINI_TRACK_MAX_LOSE_FRAMES)

    print(f"Recipe: {manager.name}")
    print(f"Source: {source}")
    print("Class map:", config.POC_CLASS_MAP)
    print("Detectable now:", summarize_detectable())

    stream = StreamReader(
        source, loop_file=not args.no_loop, low_latency=True, strict=False
    )

    camera_error = None
    if stream.last_error:
        camera_error = describe_stream_error(source, stream.last_error)
        print(camera_error, file=sys.stderr)

    cv2.namedWindow(config.WINDOW_NAME, cv2.WINDOW_NORMAL)
    first_frame = wait_for_frame(stream, timeout_sec=25.0) if stream.is_ready() else None
    live_ok = first_frame is not None
    if not live_ok:
        if not camera_error:
            camera_error = describe_stream_error(source, stream.last_error, no_frame=True)
            print(camera_error, file=sys.stderr)
        first_frame = placeholder_frame()
    else:
        camera_error = None
        print("[stream] camera frame OK")

    detector = None
    if gemini_track:
        pass  # YOLO skipped in gemini-track mode
    elif image_demo:
        print("[image-demo] Still image mode — cucumber bbox on image (no YOLO).")
    else:
        boot = renderer.render(
            first_frame,
            [],
            instruction="載入辨識模型中…" if not camera_error else manager.message,
            step_label=manager.name,
            error_message=camera_error or "",
        )
        cv2.imshow(config.WINDOW_NAME, boot)
        cv2.waitKey(1)
        print(f"Loading YOLO model: {args.model} …")
        detector = Detector(model_name=args.model, conf=args.conf, device=args.device)
    if not image_demo and not gemini_track:
        print(f"Latency: detect_every={args.detect_every}, infer_width={args.infer_width}")

    cv2.imshow(config.WINDOW_NAME, first_frame)
    cv2.waitKey(1)

    plane_scale = PlaneScale.load()
    if live_ok and (args.calibrate or plane_scale is None):
        if plane_scale is None:
            print("[scale] No saved calibration — please mark the cutting board.")
        else:
            print("[scale] Recalibrating (--calibrate).")
        calibrated = run_scale_calibration(stream)
        if calibrated is not None:
            plane_scale = calibrated
        elif plane_scale is None:
            print(
                "[scale] Skipped. Cut lines will use equal-split fallback until you click 校正尺度.",
                file=sys.stderr,
            )
        # Recreate clean main window (removes calibration trackbars).
        try:
            cv2.destroyWindow(config.WINDOW_NAME)
        except cv2.error:
            pass
        cv2.namedWindow(config.WINDOW_NAME, cv2.WINDOW_NORMAL)
    elif plane_scale is not None:
        print(
            f"[scale] Loaded {config.SCALE_CALIBRATION_PATH.name}: "
            f"{plane_scale.width_mm/10:.0f}x{plane_scale.height_mm/10:.0f} cm, "
            f"{plane_scale.mm_per_px:.4f} mm/px  (click 校正尺度 to redo)"
        )
    else:
        print("[scale] Camera unavailable — calibration skipped until the stream is connected.")

    last_log = 0.0
    last_retry = 0.0
    last_good = first_frame if live_ok else None
    frame_i = 0
    detections = []
    detect_every = max(1, args.detect_every)
    pending_actions: List[str] = []

    def on_mouse(event, x, y, _flags, _param) -> None:
        # HighGUI already reports image-pixel coords (even if the window is resized).
        if event == cv2.EVENT_MOUSEMOVE:
            renderer.set_hover(x, y)
        elif event == cv2.EVENT_LBUTTONDOWN:
            action = renderer.hit_action(x, y)
            if action:
                pending_actions.append(action)

    def bind_toolbar_mouse() -> None:
        cv2.setMouseCallback(config.WINDOW_NAME, on_mouse)

    bind_toolbar_mouse()

    last_step_id = None
    gemini_status = ""
    force_reseed = False

    if gemini_track and tracker is not None and first_frame is not None:
        # Banner while blocking on API
        banner = first_frame.copy()
        cv2.putText(
            banner,
            "Gemini identifying ingredients...",
            (24, 48),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.9,
            (0, 220, 255),
            2,
        )
        cv2.imshow(config.WINDOW_NAME, banner)
        cv2.waitKey(1)
        gemini_status = gemini_reseed(first_frame, tracker, manager, reason="startup")
        last_step_id = (
            int(manager.current_step()["step_id"]) if manager.current_step() else None
        )

    try:
        while True:
            if window_closed(config.WINDOW_NAME):
                break

            ok, frame = stream.read()
            live_frame = bool(ok and frame is not None)
            if live_frame:
                if camera_error:
                    print("[stream] camera frame OK")
                camera_error = None
                last_good = frame
            else:
                if stream._is_file and args.no_loop:
                    break
                if stream.is_ready() and last_good is not None:
                    key = cv2.waitKey(1) & 0xFF
                    mapped = key_to_action(key)
                    if mapped:
                        pending_actions.append(mapped)
                    if mapped == "quit" or window_closed(config.WINDOW_NAME):
                        break
                    continue
                now = time.monotonic()
                if now - last_retry >= 2.0:
                    last_retry = now
                    if not stream.is_ready():
                        stream.open()
                    if stream.last_error:
                        camera_error = describe_stream_error(source, stream.last_error)
                    else:
                        camera_error = describe_stream_error(
                            source, stream.last_error, no_frame=True
                        )
                frame = last_good if last_good is not None else placeholder_frame()

            h, w = frame.shape[:2]
            step = manager.current_step()
            yolo_target = manager.resolve_yolo_class(step.get("target_ingredient") if step else None)
            step_id = int(step["step_id"]) if step else None

            frame_i += 1
            if gemini_track and tracker is not None:
                need_reseed = force_reseed
                force_reseed = False
                if last_step_id is not None and step_id != last_step_id:
                    need_reseed = True
                    print(f"[gemini] step changed {last_step_id} → {step_id}")
                last_step_id = step_id

                target_name = step.get("target_ingredient") if step else None
                if tracker.target_lost(str(target_name) if target_name else None):
                    cooled = (time.monotonic() - tracker.last_seed_at) >= config.GEMINI_RESEED_COOLDOWN_SEC
                    if cooled or tracker.last_seed_at == 0:
                        need_reseed = True

                if need_reseed:
                    tip = frame.copy()
                    cv2.putText(
                        tip,
                        "Gemini re-identifying...",
                        (24, 48),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.9,
                        (0, 220, 255),
                        2,
                    )
                    cv2.imshow(config.WINDOW_NAME, tip)
                    cv2.waitKey(1)
                    gemini_status = gemini_reseed(
                        frame, tracker, manager, reason="reseed"
                    )

                detections = tracker.update(frame)
            elif image_demo:
                detections = [synthetic_cucumber(frame)]
            elif live_frame and frame_i % detect_every == 0:
                detections = []
                yolo_dets: list = []
                if detector is not None:
                    infer = frame
                    scale = 1.0
                    if args.infer_width and w > args.infer_width:
                        scale = args.infer_width / float(w)
                        infer = cv2.resize(frame, (args.infer_width, int(h * scale)))
                    yolo_filter = list(
                        dict.fromkeys([*yolo_class_names(), config.CONFIRM_OBJECT_CLASS])
                    )
                    yolo_dets = detector.detect(infer, class_filter=yolo_filter)
                    if scale != 1.0:
                        inv = 1.0 / scale
                        for d in yolo_dets:
                            d.x1 *= inv
                            d.y1 *= inv
                            d.x2 *= inv
                            d.y2 *= inv
                detections = merge_produce_and_yolo(frame, [], yolo_dets)
            elif not live_frame:
                detections = []

            detections = locker.update(
                frame,
                detections,
                detections_fresh=live_frame and (image_demo or (frame_i % detect_every == 0)),
            )
            if live_frame:
                manager.update(detections, w, h)

            step = manager.current_step()
            draw_cuts = bool(step and step.get("guide_lines"))
            cut_spacing_mm = None
            if step and step.get("cut_spacing_mm") is not None:
                try:
                    cut_spacing_mm = float(step["cut_spacing_mm"])
                except (TypeError, ValueError):
                    cut_spacing_mm = None

            mm_per_px = plane_scale.mm_per_px if plane_scale else None
            if draw_cuts and cut_spacing_mm and mm_per_px:
                scale_hint = f"cut {cut_spacing_mm:.0f}mm  ({mm_per_px:.3f} mm/px)"
            elif draw_cuts and not mm_per_px:
                scale_hint = "請點「校正尺度」"
            elif plane_scale:
                scale_hint = f"scale {plane_scale.mm_per_px:.3f} mm/px"
            else:
                scale_hint = "no scale"
            if gemini_track and tracker is not None:
                scale_hint = (
                    f"gemini:{tracker.status} n={tracker.alive_count}  |  {scale_hint}"
                )
                if gemini_status:
                    scale_hint = f"{gemini_status[:40]}  |  {scale_hint}"

            step_label = (
                f"{manager.name}  ·  step {manager.current_index + 1}/"
                f"{len(manager.recipe.get('steps') or [])}"
                if step
                else f"{manager.name}  ·  done"
            )
            hold = manager.hold_progress
            if manager.mouse_confirm_progress > hold:
                hold = manager.mouse_confirm_progress
            highlight = yolo_target
            if gemini_track and step and step.get("target_ingredient"):
                highlight = str(step["target_ingredient"])
            overlay = renderer.render(
                frame,
                detections,
                highlight_class=highlight,
                draw_cut_lines=draw_cuts,
                cut_spacing_mm=cut_spacing_mm,
                mm_per_px=mm_per_px,
                dropzone=manager.dropzone,
                instruction=manager.message,
                step_label=step_label,
                timer_remaining=manager.timer_remaining,
                hold_progress=hold if hold > 0 else None,
                scale_hint=scale_hint,
                ingredients=manager.ingredient_checklist(),
                error_message=camera_error or "",
            )

            cv2.imshow(config.WINDOW_NAME, overlay)
            now = time.monotonic()
            if now - last_log > 2.0:
                names = [f"{d.name}:{d.conf:.2f}" for d in detections]
                print(f"[{step_label}] dets={names or '-'} hold={manager.hold_progress:.2f}")
                last_log = now

            key = cv2.waitKey(1 if live_frame else 30) & 0xFF
            actions = list(pending_actions)
            pending_actions.clear()
            mapped = key_to_action(key)
            if mapped:
                actions.append(mapped)
            if window_closed(config.WINDOW_NAME):
                break

            stop = False
            for action in actions:
                if action == "quit":
                    stop = True
                    break
                if action == "restart":
                    manager.reset()
                    renderer.clear()
                    locker.clear()
                    if tracker is not None:
                        tracker.clear()
                        force_reseed = True
                    print("[demo] restarted")
                elif action == "calibrate":
                    if camera_error or not stream.is_ready():
                        camera_error = camera_error or describe_stream_error(
                            source, stream.last_error, no_frame=True
                        )
                        print(camera_error, file=sys.stderr)
                        continue
                    calibrated = run_scale_calibration(stream)
                    if calibrated is not None:
                        plane_scale = calibrated
                    try:
                        cv2.destroyWindow(config.WINDOW_NAME)
                    except cv2.error:
                        pass
                    cv2.namedWindow(config.WINDOW_NAME, cv2.WINDOW_NORMAL)
                    bind_toolbar_mouse()
                elif action == "next":
                    manager.confirm()
                    if manager.is_finished():
                        print("Recipe finished.")
            if stop:
                break
            if key in (ord("g"), ord("G")) and gemini_track:
                force_reseed = True
    except KeyboardInterrupt:
        print("\nInterrupted.")
    finally:
        stream.release()
        cv2.destroyAllWindows()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

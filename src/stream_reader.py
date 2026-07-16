"""Video / RTSP / HTTP capture with reconnect and low-latency latest-frame grab."""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Iterator, Optional, Tuple, Union

import cv2
import numpy as np

from src import config

SourceType = Union[str, int, Path]


def parse_source(source: Optional[str] = None) -> SourceType:
    raw = source if source is not None else config.DEFAULT_SOURCE
    if isinstance(raw, int):
        return raw
    text = str(raw).strip()
    if text.isdigit():
        return int(text)
    path = Path(text)
    if path.exists():
        return path
    return text  # RTSP / HTTP URL


def _is_network_source(source: SourceType) -> bool:
    if isinstance(source, int) or isinstance(source, Path):
        return False
    s = str(source).lower()
    return s.startswith(("rtsp://", "rtsps://", "http://", "https://"))


class StreamReader:
    """
    OpenCV VideoCapture wrapper.

    For network streams (HTTP/RTSP), a background thread continuously reads and
    keeps only the newest frame so YOLO inference cannot create a multi-second backlog.
    """

    def __init__(
        self,
        source: Optional[str] = None,
        loop_file: bool = True,
        low_latency: bool = True,
    ) -> None:
        self.source = parse_source(source)
        self.loop_file = loop_file
        self.low_latency = low_latency
        self.cap: Optional[cv2.VideoCapture] = None
        self._fail_count = 0
        self._is_file = isinstance(self.source, Path) or (
            isinstance(self.source, str)
            and not _is_network_source(self.source)
            and Path(self.source).exists()
        )
        self._is_network = _is_network_source(self.source)

        self._lock = threading.Lock()
        self._latest: Optional[np.ndarray] = None
        self._latest_ok = False
        self._running = False
        self._thread: Optional[threading.Thread] = None

        self.open()

    def open(self) -> None:
        self.release()
        src: SourceType = self.source
        if isinstance(src, Path):
            src = str(src)

        self.cap = self._open_capture(src)
        if self.cap is None or not self.cap.isOpened():
            hint = ""
            if isinstance(self.source, int):
                hint = (
                    " Try another index (e.g. --webcam 1) or run "
                    "`python -m src.phone_test --list-cameras`."
                )
            raise RuntimeError(f"Cannot open video source: {self.source}.{hint}")

        # Shrink capture buffer when supported (helps USB cam; mixed support for IP).
        try:
            self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        except Exception:
            pass

        self._fail_count = 0

        if self.low_latency and (self._is_network or not self._is_file):
            self._start_grabber()

    def _open_capture(self, src: SourceType) -> Optional[cv2.VideoCapture]:
        """Open capture with a backend suited to the source type."""
        if self._is_network:
            return cv2.VideoCapture(src, cv2.CAP_FFMPEG)
        if isinstance(src, int) and hasattr(cv2, "CAP_DSHOW"):
            cap = cv2.VideoCapture(src, cv2.CAP_DSHOW)
            if cap.isOpened():
                return cap
            cap.release()
        return cv2.VideoCapture(src)

    def _start_grabber(self) -> None:
        self._running = True
        self._thread = threading.Thread(target=self._grab_loop, name="stream-grabber", daemon=True)
        self._thread.start()

    def _grab_loop(self) -> None:
        """Always discard stale frames; keep only the newest decoded image."""
        while self._running:
            cap = self.cap
            if cap is None:
                time.sleep(0.05)
                continue
            ok = cap.grab()
            if not ok:
                with self._lock:
                    self._latest_ok = False
                time.sleep(0.01)
                if self._is_network:
                    self._fail_count += 1
                    if self._fail_count >= config.READ_FAIL_RECONNECT_AFTER:
                        self._fail_count = 0
                        try:
                            # Soft reopen inside grabber
                            self._reopen_capture()
                        except RuntimeError:
                            time.sleep(config.RECONNECT_DELAY_SEC)
                continue

            ok, frame = cap.retrieve()
            if ok and frame is not None:
                with self._lock:
                    self._latest = frame
                    self._latest_ok = True
                self._fail_count = 0
            else:
                time.sleep(0.001)

    def _reopen_capture(self) -> None:
        src: SourceType = self.source
        if isinstance(src, Path):
            src = str(src)
        old = self.cap
        new_cap = self._open_capture(src)
        if new_cap is None or not new_cap.isOpened():
            if new_cap is not None:
                new_cap.release()
            raise RuntimeError(f"Cannot reopen video source: {self.source}")
        try:
            new_cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        except Exception:
            pass
        self.cap = new_cap
        if old is not None:
            old.release()

    def release(self) -> None:
        self._running = False
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=1.5)
        self._thread = None
        if self.cap is not None:
            self.cap.release()
            self.cap = None
        with self._lock:
            self._latest = None
            self._latest_ok = False

    def reconnect(self) -> bool:
        time.sleep(config.RECONNECT_DELAY_SEC)
        try:
            self.open()
            return True
        except RuntimeError:
            return False

    def read(self) -> Tuple[bool, Optional[np.ndarray]]:
        # Low-latency path: return newest frame from grabber thread.
        if self._thread is not None and self._running:
            with self._lock:
                if self._latest_ok and self._latest is not None:
                    return True, self._latest.copy()
            return False, None

        if self.cap is None:
            if not self.reconnect():
                return False, None
        assert self.cap is not None

        # Drain a few buffered frames for non-threaded path.
        if self.low_latency and not self._is_file:
            for _ in range(config.DRAIN_EXTRA_GRABS):
                self.cap.grab()

        ok, frame = self.cap.read()
        if ok and frame is not None:
            self._fail_count = 0
            return True, frame

        self._fail_count += 1

        if self._is_file:
            if self.loop_file:
                self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                ok, frame = self.cap.read()
                if ok:
                    self._fail_count = 0
                    return True, frame
            return False, None

        if self._fail_count >= config.READ_FAIL_RECONNECT_AFTER:
            self.reconnect()
        return False, None

    def frames(self) -> Iterator[np.ndarray]:
        while True:
            ok, frame = self.read()
            if not ok or frame is None:
                if self._is_file and not self.loop_file:
                    break
                time.sleep(0.005)
                continue
            yield frame

    def __enter__(self) -> "StreamReader":
        return self

    def __exit__(self, *args: object) -> None:
        self.release()

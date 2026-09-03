"""Stream open failure should not raise when strict=False."""

from __future__ import annotations

import unittest

from src.phone_test import describe_stream_error
from src.stream_reader import StreamReader


class StreamOfflineTests(unittest.TestCase):
    def test_strict_false_missing_file(self) -> None:
        stream = StreamReader("no_such_camera_feed.mp4", strict=False)
        try:
            self.assertFalse(stream.is_ready())
            self.assertIsNotNone(stream.last_error)
            ok, frame = stream.read()
            self.assertFalse(ok)
            self.assertIsNone(frame)
        finally:
            stream.release()

    def test_describe_webcam_error(self) -> None:
        msg = describe_stream_error("0")
        self.assertIn("index 0", msg)
        self.assertIn("無法開啟鏡頭", msg)


if __name__ == "__main__":
    unittest.main()

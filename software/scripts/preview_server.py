#!/usr/bin/env python3
from __future__ import annotations

import io
import time
import signal
import atexit
import threading
from dataclasses import dataclass

import cv2
import numpy as np
from flask import Flask, Response, jsonify, render_template_string
from picamera2 import Picamera2


HTML_PAGE = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Vivian Camera Preview</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <style>
    body {
      margin: 0;
      background: #111;
      color: #eee;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      display: flex;
      flex-direction: column;
      align-items: center;
    }
    .wrap {
      width: min(95vw, 1400px);
      margin: 24px auto;
    }
    h1 {
      font-size: 20px;
      font-weight: 600;
      margin: 0 0 12px 0;
    }
    .sub {
      color: #aaa;
      font-size: 13px;
      margin-bottom: 16px;
    }
    .viewer {
      background: #000;
      border-radius: 14px;
      overflow: hidden;
      border: 1px solid #2a2a2a;
      box-shadow: 0 10px 30px rgba(0,0,0,0.35);
    }
    img {
      display: block;
      width: 100%;
      height: auto;
    }
    .meta {
      margin-top: 14px;
      font-size: 13px;
      color: #bbb;
      display: flex;
      gap: 18px;
      flex-wrap: wrap;
    }
    code {
      background: #1c1c1c;
      padding: 2px 6px;
      border-radius: 6px;
    }
  </style>
</head>
<body>
  <div class="wrap">
    <h1>Vivian Camera Dual Preview</h1>
    <div class="sub">
      Left + Right live preview from Raspberry Pi
    </div>
    <div class="viewer">
      <img src="/stream.mjpg" alt="Dual camera preview">
    </div>
    <div class="meta">
      <div>Stream: <code>/stream.mjpg</code></div>
      <div>Status: <code>/status</code></div>
    </div>
  </div>
</body>
</html>
"""


@dataclass
class PreviewConfig:
    left_index: int = 0
    right_index: int = 1
    width: int = 640
    height: int = 480
    fps: int = 20
    jpeg_quality: int = 85
    divider_width: int = 2
    hflip_left: bool = False
    hflip_right: bool = False
    vflip_left: bool = False
    vflip_right: bool = False


class DualPreviewServer:
    def __init__(self, config: PreviewConfig) -> None:
        self.config = config
        self.picam_left: Picamera2 | None = None
        self.picam_right: Picamera2 | None = None
        self.running = False
        self.frame_lock = threading.Lock()
        self.latest_jpeg: bytes | None = None
        self.capture_thread: threading.Thread | None = None
        self.frame_count = 0
        self.last_frame_time = 0.0
        self.start_time = 0.0

    def start(self) -> None:
        self.picam_left = Picamera2(self.config.left_index)
        self.picam_right = Picamera2(self.config.right_index)

        left_cfg = self.picam_left.create_preview_configuration(
            main={"size": (self.config.width, self.config.height), "format": "RGB888"},
            controls={"FrameRate": self.config.fps},
        )
        right_cfg = self.picam_right.create_preview_configuration(
            main={"size": (self.config.width, self.config.height), "format": "RGB888"},
            controls={"FrameRate": self.config.fps},
        )

        self.picam_left.configure(left_cfg)
        self.picam_right.configure(right_cfg)

        self.picam_left.start()
        self.picam_right.start()

        time.sleep(0.5)

        self.running = True
        self.start_time = time.time()
        self.capture_thread = threading.Thread(target=self._capture_loop, daemon=True)
        self.capture_thread.start()

    def stop(self) -> None:
        self.running = False

        if self.capture_thread and self.capture_thread.is_alive():
            self.capture_thread.join(timeout=2.0)

        if self.picam_left is not None:
            try:
                self.picam_left.stop()
            except Exception:
                pass

        if self.picam_right is not None:
            try:
                self.picam_right.stop()
            except Exception:
                pass

    def _apply_flips(self, frame: np.ndarray, *, hflip: bool, vflip: bool) -> np.ndarray:
        if hflip:
            frame = cv2.flip(frame, 1)
        if vflip:
            frame = cv2.flip(frame, 0)
        return frame

    def _capture_loop(self) -> None:
        target_interval = 1.0 / max(self.config.fps, 1)

        while self.running:
            loop_start = time.time()

            try:
                assert self.picam_left is not None and self.picam_right is not None

                left = self.picam_left.capture_array("main")
                right = self.picam_right.capture_array("main")

                left = self._apply_flips(
                    left,
                    hflip=self.config.hflip_left,
                    vflip=self.config.vflip_left,
                )
                right = self._apply_flips(
                    right,
                    hflip=self.config.hflip_right,
                    vflip=self.config.vflip_right,
                )

                # Picamera2 returns RGB888 here; OpenCV encode expects BGR.
                left_bgr = cv2.cvtColor(left, cv2.COLOR_RGB2BGR)
                right_bgr = cv2.cvtColor(right, cv2.COLOR_RGB2BGR)

                if self.config.divider_width > 0:
                    divider = np.full(
                        (self.config.height, self.config.divider_width, 3),
                        255,
                        dtype=np.uint8,
                    )
                    combined = np.hstack((left_bgr, divider, right_bgr))
                else:
                    combined = np.hstack((left_bgr, right_bgr))

                ok, buffer = cv2.imencode(
                    ".jpg",
                    combined,
                    [int(cv2.IMWRITE_JPEG_QUALITY), self.config.jpeg_quality],
                )
                if ok:
                    with self.frame_lock:
                        self.latest_jpeg = buffer.tobytes()
                        self.frame_count += 1
                        self.last_frame_time = time.time()

            except Exception as exc:
                error_frame = np.zeros((300, 900, 3), dtype=np.uint8)
                cv2.putText(
                    error_frame,
                    f"Preview error: {exc}",
                    (20, 150),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.8,
                    (255, 255, 255),
                    2,
                    cv2.LINE_AA,
                )
                ok, buffer = cv2.imencode(".jpg", error_frame)
                if ok:
                    with self.frame_lock:
                        self.latest_jpeg = buffer.tobytes()

                time.sleep(0.2)

            elapsed = time.time() - loop_start
            sleep_time = max(0.0, target_interval - elapsed)
            if sleep_time > 0:
                time.sleep(sleep_time)

    def mjpeg_generator(self):
        while True:
            with self.frame_lock:
                frame = self.latest_jpeg

            if frame is None:
                time.sleep(0.05)
                continue

            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n" + frame + b"\r\n"
            )
            time.sleep(0.001)

    def status(self) -> dict:
        uptime = time.time() - self.start_time if self.start_time else 0.0
        return {
            "running": self.running,
            "left_index": self.config.left_index,
            "right_index": self.config.right_index,
            "resolution_each": [self.config.width, self.config.height],
            "target_fps": self.config.fps,
            "frame_count": self.frame_count,
            "uptime_sec": round(uptime, 2),
            "last_frame_age_sec": round(time.time() - self.last_frame_time, 3)
            if self.last_frame_time
            else None,
        }


def create_app(server: DualPreviewServer) -> Flask:
    app = Flask(__name__)

    @app.route("/")
    def index():
        return render_template_string(HTML_PAGE)

    @app.route("/stream.mjpg")
    def stream():
        return Response(
            server.mjpeg_generator(),
            mimetype="multipart/x-mixed-replace; boundary=frame",
        )

    @app.route("/status")
    def status():
        return jsonify(server.status())

    return app


def main() -> None:
    config = PreviewConfig(
        left_index=0,
        right_index=1,
        width=640,
        height=480,
        fps=20,
        jpeg_quality=85,
        divider_width=2,
        hflip_left=False,
        hflip_right=False,
        vflip_left=False,
        vflip_right=False,
    )

    server = DualPreviewServer(config)
    server.start()

    def _cleanup(*_args):
        server.stop()

    atexit.register(_cleanup)
    signal.signal(signal.SIGINT, _cleanup)
    signal.signal(signal.SIGTERM, _cleanup)

    app = create_app(server)
    app.run(host="0.0.0.0", port=5000, threaded=True)


if __name__ == "__main__":
    main()
import atexit
import os
import threading
import time
from typing import Any, Optional

import cv2
import numpy as np
from flask import Flask, Response, jsonify, render_template

app = Flask(__name__)

START_TIME = time.time()


def use_mock_preview() -> bool:
    return os.environ.get("USE_MOCK_PREVIEW", "1") == "1"


def load_picamera2_class():
    try:
        from picamera2 import Picamera2
        return Picamera2
    except Exception as exc:
        raise RuntimeError(
            "picamera2 is unavailable. Real camera mode requires Raspberry Pi "
            "with Picamera2 installed. Use USE_MOCK_PREVIEW=1 on Mac/local development."
        ) from exc


def format_uptime(total_seconds: int) -> str:
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def generate_mock_jpeg() -> bytes:
    width = 1280
    height = 720
    image = np.zeros((height, width, 3), dtype=np.uint8)

    image[:] = (18, 20, 24)

    cv2.rectangle(image, (60, 80), (width // 2 - 20, height - 120), (55, 60, 70), 2)
    cv2.rectangle(image, (width // 2 + 20, 80), (width - 60, height - 120), (55, 60, 70), 2)

    cv2.putText(
        image,
        "LEFT CAMERA",
        (160, height // 2),
        cv2.FONT_HERSHEY_SIMPLEX,
        1.0,
        (210, 215, 225),
        2,
        cv2.LINE_AA,
    )
    cv2.putText(
        image,
        "RIGHT CAMERA",
        (width // 2 + 140, height // 2),
        cv2.FONT_HERSHEY_SIMPLEX,
        1.0,
        (210, 215, 225),
        2,
        cv2.LINE_AA,
    )
    cv2.putText(
        image,
        "MOCK PREVIEW",
        (50, 45),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.9,
        (120, 220, 150),
        2,
        cv2.LINE_AA,
    )

    ok, encoded = cv2.imencode(".jpg", image, [int(cv2.IMWRITE_JPEG_QUALITY), 75])
    if not ok:
        raise RuntimeError("Failed to encode mock JPEG frame.")
    return encoded.tobytes()


class MockPreviewStreamer:
    def __init__(self) -> None:
        self.preview_width = 640
        self.preview_height = 360
        self.main_width = 0
        self.main_height = 0
        self.target_fps = max(int(os.environ.get("TARGET_FPS", "12")), 1)
        self.jpeg_quality = int(os.environ.get("JPEG_QUALITY", "70"))

        self.running = False
        self.last_error: Optional[str] = None

        self.latest_jpeg: Optional[bytes] = None
        self.latest_frame_ts = 0.0
        self.frame_count = 0

        self._lock = threading.Lock()
        self._new_frame = threading.Condition(self._lock)
        self._worker: Optional[threading.Thread] = None

    def start(self) -> None:
        if self.running:
            return

        self.running = True
        self.last_error = None
        self._worker = threading.Thread(target=self._capture_loop, daemon=True)
        self._worker.start()

    def stop(self) -> None:
        self.running = False
        with self._new_frame:
            self._new_frame.notify_all()

        if self._worker is not None and self._worker.is_alive():
            self._worker.join(timeout=1.0)

    def _capture_loop(self) -> None:
        frame_interval = 1.0 / self.target_fps

        while self.running:
            loop_started = time.time()
            try:
                jpeg = generate_mock_jpeg()
                now = time.time()

                with self._new_frame:
                    self.latest_jpeg = jpeg
                    self.latest_frame_ts = now
                    self.frame_count += 1
                    self._new_frame.notify_all()

            except Exception as exc:
                self.last_error = f"Mock preview failed: {exc}"
                time.sleep(0.2)

            elapsed = time.time() - loop_started
            sleep_time = frame_interval - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

    def wait_for_frame(self, timeout: float = 1.0) -> Optional[bytes]:
        deadline = time.time() + timeout
        with self._new_frame:
            while self.latest_jpeg is None and self.running:
                remaining = deadline - time.time()
                if remaining <= 0:
                    break
                self._new_frame.wait(timeout=remaining)
            return self.latest_jpeg

    def get_latest_jpeg(self) -> bytes:
        jpeg = self.wait_for_frame(timeout=1.0)
        if jpeg is None:
            raise RuntimeError("Mock preview frame is not available yet.")
        return jpeg

    def frame_age_seconds(self) -> Optional[float]:
        if self.latest_frame_ts <= 0:
            return None
        return time.time() - self.latest_frame_ts

    def preview_resolution_text(self) -> str:
        return f"{self.preview_width} × {self.preview_height}"

    def capture_resolution_text(self) -> str:
        return "--"


class DualCameraStreamer:
    def __init__(self) -> None:
        self.left_index = int(os.environ.get("LEFT_CAMERA_INDEX", "0"))
        self.right_index = int(os.environ.get("RIGHT_CAMERA_INDEX", "1"))

        # 预览参数：只服务 live preview
        self.preview_width = int(os.environ.get("PREVIEW_WIDTH", "640"))
        self.preview_height = int(os.environ.get("PREVIEW_HEIGHT", "360"))
        self.target_fps = max(int(os.environ.get("TARGET_FPS", "12")), 1)
        self.jpeg_quality = int(os.environ.get("JPEG_QUALITY", "65"))

        # 仅展示信息；当前 preview pipeline 不常驻开高分辨率 main
        self.main_width = int(os.environ.get("CAPTURE_WIDTH", "2304"))
        self.main_height = int(os.environ.get("CAPTURE_HEIGHT", "1296"))

        self.left_cam: Optional[Any] = None
        self.right_cam: Optional[Any] = None

        self.running = False
        self.last_error: Optional[str] = None

        self.latest_jpeg: Optional[bytes] = None
        self.latest_frame_ts = 0.0
        self.frame_count = 0

        self._camera_lock = threading.Lock()
        self._state_lock = threading.Lock()
        self._new_frame = threading.Condition(self._state_lock)
        self._worker: Optional[threading.Thread] = None

    def start(self) -> None:
        with self._camera_lock:
            if self.running:
                return

            try:
                Picamera2 = load_picamera2_class()

                self.left_cam = Picamera2(self.left_index)
                self.right_cam = Picamera2(self.right_index)

                # 这里只开 lores 预览流，不再常驻大 main
                left_config = self.left_cam.create_preview_configuration(
                    lores={"size": (self.preview_width, self.preview_height), "format": "RGB888"},
                    buffer_count=4,
                    queue=True,
                )
                right_config = self.right_cam.create_preview_configuration(
                    lores={"size": (self.preview_width, self.preview_height), "format": "RGB888"},
                    buffer_count=4,
                    queue=True,
                )

                self.left_cam.configure(left_config)
                self.right_cam.configure(right_config)

                self.left_cam.start()
                self.right_cam.start()

                time.sleep(0.6)

                self.running = True
                self.last_error = None

            except Exception as exc:
                self.last_error = f"Failed to start cameras: {exc}"
                self.running = False
                self.stop()
                raise

        self._worker = threading.Thread(target=self._capture_loop, daemon=True)
        self._worker.start()

    def stop(self) -> None:
        self.running = False

        with self._new_frame:
            self._new_frame.notify_all()

        if self._worker is not None and self._worker.is_alive():
            self._worker.join(timeout=1.5)

        with self._camera_lock:
            for cam in (self.left_cam, self.right_cam):
                if cam is not None:
                    try:
                        cam.stop()
                    except Exception:
                        pass
                    try:
                        cam.close()
                    except Exception:
                        pass

            self.left_cam = None
            self.right_cam = None

    def _capture_preview_pair(self) -> tuple[np.ndarray, np.ndarray]:
        if not self.running or self.left_cam is None or self.right_cam is None:
            raise RuntimeError("Cameras are not running.")

        with self._camera_lock:
            left_rgb = self.left_cam.capture_array("lores")
            right_rgb = self.right_cam.capture_array("lores")

        return left_rgb, right_rgb

    def _capture_loop(self) -> None:
        frame_interval = 1.0 / self.target_fps

        while self.running:
            loop_started = time.time()

            try:
                left_rgb, right_rgb = self._capture_preview_pair()
                combined_rgb = np.hstack((left_rgb, right_rgb))
                frame_bgr = cv2.cvtColor(combined_rgb, cv2.COLOR_RGB2BGR)

                ok, encoded = cv2.imencode(
                    ".jpg",
                    frame_bgr,
                    [int(cv2.IMWRITE_JPEG_QUALITY), self.jpeg_quality],
                )
                if not ok:
                    raise RuntimeError("Failed to encode JPEG frame.")

                now = time.time()
                jpeg_bytes = encoded.tobytes()

                with self._new_frame:
                    self.latest_jpeg = jpeg_bytes
                    self.latest_frame_ts = now
                    self.frame_count += 1
                    self.last_error = None
                    self._new_frame.notify_all()

            except Exception as exc:
                self.last_error = f"Preview loop error: {exc}"
                time.sleep(0.15)

            elapsed = time.time() - loop_started
            sleep_time = frame_interval - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

    def wait_for_frame(self, timeout: float = 1.0) -> Optional[bytes]:
        deadline = time.time() + timeout
        with self._new_frame:
            while self.latest_jpeg is None and self.running:
                remaining = deadline - time.time()
                if remaining <= 0:
                    break
                self._new_frame.wait(timeout=remaining)
            return self.latest_jpeg

    def get_latest_jpeg(self) -> bytes:
        jpeg = self.wait_for_frame(timeout=1.0)
        if jpeg is None:
            raise RuntimeError("Preview frame is not available yet.")
        return jpeg

    def frame_age_seconds(self) -> Optional[float]:
        if self.latest_frame_ts <= 0:
            return None
        return time.time() - self.latest_frame_ts

    def preview_resolution_text(self) -> str:
        return f"{self.preview_width} × {self.preview_height}"

    def capture_resolution_text(self) -> str:
        return f"{self.main_width} × {self.main_height}"


streamer: Optional[object] = None

if use_mock_preview():
    streamer = MockPreviewStreamer()
    streamer.start()
else:
    streamer = DualCameraStreamer()
    try:
        streamer.start()
    except Exception as exc:
        print(f"[preview_server] Camera startup failed: {exc}")


def mjpeg_generator():
    while True:
        try:
            if streamer is None or not streamer.running:
                raise RuntimeError("Preview streamer is not running.")

            jpeg = streamer.get_latest_jpeg()

            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n"
                b"Cache-Control: no-store, no-cache, must-revalidate, max-age=0\r\n"
                b"Pragma: no-cache\r\n\r\n" + jpeg + b"\r\n"
            )

        except GeneratorExit:
            break
        except Exception as exc:
            print(f"[preview_server] Stream error: {exc}")
            time.sleep(0.2)


@app.route("/")
def index():
    return render_template(
        "preview.html",
        mock_preview=use_mock_preview(),
    )


@app.route("/status")
def status():
    uptime_seconds = int(time.time() - START_TIME)

    is_mock = use_mock_preview()
    frame_age = None if streamer is None else streamer.frame_age_seconds()
    frame_age_text = "--" if frame_age is None else f"{frame_age:.2f}s"

    cameras_ready = False
    status_kind = "disconnected"
    status_text = "Camera not ready"

    if is_mock:
        status_kind = "mock"
        status_text = "Mock Preview"
    else:
        if (
            streamer is not None
            and streamer.running
            and getattr(streamer, "left_cam", None) is not None
            and getattr(streamer, "right_cam", None) is not None
            and frame_age is not None
        ):
            cameras_ready = True
            status_kind = "ready"
            status_text = "Dual cameras ready"

    if streamer is not None and streamer.last_error:
        status_kind = "error"
        status_text = streamer.last_error
        cameras_ready = False

    return jsonify(
        {
            "connected": cameras_ready,
            "cameras_ready": cameras_ready,
            "is_mock": is_mock,
            "status_kind": status_kind,
            "status_text": status_text,
            "resolution": streamer.preview_resolution_text() if streamer else "--",
            "capture_resolution": streamer.capture_resolution_text() if streamer else "--",
            "target_fps": int(os.environ.get("TARGET_FPS", "12")),
            "frame_count": streamer.frame_count if streamer else 0,
            "uptime": format_uptime(uptime_seconds),
            "left_camera_index": int(os.environ.get("LEFT_CAMERA_INDEX", "0")),
            "right_camera_index": int(os.environ.get("RIGHT_CAMERA_INDEX", "1")),
            "last_frame_age": frame_age_text,
        }
    )


@app.route("/frame.jpg")
def frame_jpg():
    try:
        if streamer is None or not streamer.running:
            raise RuntimeError("Preview streamer is not running.")

        jpeg = streamer.get_latest_jpeg()

        response = Response(jpeg, mimetype="image/jpeg")
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response

    except Exception as exc:
        error_text = f"Frame endpoint error: {exc}"
        print(f"[preview_server] {error_text}")
        return Response(error_text, status=500, mimetype="text/plain")


@app.route("/stream.mjpg")
def stream_mjpg():
    return Response(
        mjpeg_generator(),
        mimetype="multipart/x-mixed-replace; boundary=frame",
    )


@atexit.register
def cleanup():
    global streamer
    if streamer is not None:
        streamer.stop()


if __name__ == "__main__":
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "5000"))

    app.run(host=host, port=port, debug=False, use_reloader=False, threaded=True)
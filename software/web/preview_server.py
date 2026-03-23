import atexit
import os
import threading
import time
from typing import Optional, Any

import cv2
import numpy as np
from flask import Flask, Response, jsonify, render_template

app = Flask(__name__)

START_TIME = time.time()
FRAME_COUNT = 0


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


class DualCameraStreamer:
    def __init__(self) -> None:
        self.lock = threading.Lock()

        self.left_index = int(os.environ.get("LEFT_CAMERA_INDEX", "0"))
        self.right_index = int(os.environ.get("RIGHT_CAMERA_INDEX", "1"))

        # main: 留给未来正式拍摄
        self.main_width = int(os.environ.get("CAPTURE_WIDTH", "2304"))
        self.main_height = int(os.environ.get("CAPTURE_HEIGHT", "1296"))

        # lores: 专门用于实时预览
        self.preview_width = int(os.environ.get("PREVIEW_WIDTH", "640"))
        self.preview_height = int(os.environ.get("PREVIEW_HEIGHT", "360"))

        self.target_fps = int(os.environ.get("TARGET_FPS", "12"))
        self.jpeg_quality = int(os.environ.get("JPEG_QUALITY", "70"))

        self.left_cam: Optional[Any] = None
        self.right_cam: Optional[Any] = None

        self.running = False
        self.last_frame = None
        self.last_frame_ts = 0.0
        self.last_error = None

    def start(self) -> None:
        with self.lock:
            if self.running:
                return

            try:
                Picamera2 = load_picamera2_class()

                self.left_cam = Picamera2(self.left_index)
                self.right_cam = Picamera2(self.right_index)

                left_config = self.left_cam.create_preview_configuration(
                    main={"size": (self.main_width, self.main_height), "format": "RGB888"},
                    lores={"size": (self.preview_width, self.preview_height), "format": "RGB888"},
                    buffer_count=4,
                    queue=True,
                )
                right_config = self.right_cam.create_preview_configuration(
                    main={"size": (self.main_width, self.main_height), "format": "RGB888"},
                    lores={"size": (self.preview_width, self.preview_height), "format": "RGB888"},
                    buffer_count=4,
                    queue=True,
                )

                self.left_cam.configure(left_config)
                self.right_cam.configure(right_config)

                self.left_cam.start()
                self.right_cam.start()

                time.sleep(1.0)

                self.running = True
                self.last_error = None

            except Exception as exc:
                self.last_error = f"Failed to start cameras: {exc}"
                self.running = False
                self.stop()
                raise

    def stop(self) -> None:
        with self.lock:
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
            self.running = False

    def _capture_preview_pair(self) -> tuple[np.ndarray, np.ndarray]:
        if not self.running or self.left_cam is None or self.right_cam is None:
            raise RuntimeError("Cameras are not running.")

        with self.lock:
            left_rgb = self.left_cam.capture_array("lores")
            right_rgb = self.right_cam.capture_array("lores")

        return left_rgb, right_rgb

    def get_combined_preview_frame(self) -> np.ndarray:
        left_rgb, right_rgb = self._capture_preview_pair()

        combined_rgb = np.hstack((left_rgb, right_rgb))
        self.last_frame = combined_rgb
        self.last_frame_ts = time.time()
        return combined_rgb

    def get_preview_jpeg_bytes(self) -> bytes:
        frame_rgb = self.get_combined_preview_frame()
        frame_bgr = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2BGR)

        ok, encoded = cv2.imencode(
            ".jpg",
            frame_bgr,
            [int(cv2.IMWRITE_JPEG_QUALITY), self.jpeg_quality],
        )
        if not ok:
            raise RuntimeError("Failed to encode JPEG frame.")

        return encoded.tobytes()

    def frame_age_seconds(self) -> Optional[float]:
        if self.last_frame_ts <= 0:
            return None
        return time.time() - self.last_frame_ts

    def preview_resolution_text(self) -> str:
        return f"{self.preview_width} × {self.preview_height}"

    def capture_resolution_text(self) -> str:
        return f"{self.main_width} × {self.main_height}"


camera_streamer: Optional[DualCameraStreamer] = None

if not use_mock_preview():
    camera_streamer = DualCameraStreamer()
    try:
        camera_streamer.start()
    except Exception as exc:
        print(f"[preview_server] Camera startup failed: {exc}")


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


def mjpeg_generator():
    global FRAME_COUNT
    frame_interval = 1.0 / max(int(os.environ.get("TARGET_FPS", "12")), 1)

    while True:
        try:
            if use_mock_preview():
                jpeg = generate_mock_jpeg()
            else:
                if camera_streamer is None or not camera_streamer.running:
                    raise RuntimeError("Camera streamer is not available.")
                jpeg = camera_streamer.get_preview_jpeg_bytes()

            FRAME_COUNT += 1

            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n" + jpeg + b"\r\n"
            )

            time.sleep(frame_interval)

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

    if use_mock_preview():
        return jsonify(
            {
                "connected": True,
                "status_text": "Mock Preview Ready",
                "resolution": "640 × 360",
                "capture_resolution": "--",
                "target_fps": int(os.environ.get("TARGET_FPS", "12")),
                "frame_count": FRAME_COUNT,
                "uptime": format_uptime(uptime_seconds),
                "left_camera_index": 0,
                "right_camera_index": 1,
                "last_frame_age": "0.00s",
            }
        )

    connected = camera_streamer is not None and camera_streamer.running
    frame_age = None if camera_streamer is None else camera_streamer.frame_age_seconds()
    frame_age_text = "--" if frame_age is None else f"{frame_age:.2f}s"

    status_text = "Live Preview Ready" if connected else "Camera Not Ready"
    if camera_streamer is not None and camera_streamer.last_error:
        status_text = camera_streamer.last_error

    return jsonify(
        {
            "connected": connected,
            "status_text": status_text,
            "resolution": camera_streamer.preview_resolution_text() if camera_streamer else "--",
            "capture_resolution": camera_streamer.capture_resolution_text() if camera_streamer else "--",
            "target_fps": int(os.environ.get("TARGET_FPS", "12")),
            "frame_count": FRAME_COUNT,
            "uptime": format_uptime(uptime_seconds),
            "left_camera_index": int(os.environ.get("LEFT_CAMERA_INDEX", "0")),
            "right_camera_index": int(os.environ.get("RIGHT_CAMERA_INDEX", "1")),
            "last_frame_age": frame_age_text,
        }
    )


@app.route("/frame.jpg")
def frame_jpg():
    global FRAME_COUNT

    try:
        if use_mock_preview():
            jpeg = generate_mock_jpeg()
        else:
            if camera_streamer is None or not camera_streamer.running:
                raise RuntimeError("Camera streamer is not available.")
            jpeg = camera_streamer.get_preview_jpeg_bytes()

        FRAME_COUNT += 1

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
    if camera_streamer is not None:
        camera_streamer.stop()


if __name__ == "__main__":
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "5000"))

    app.run(host=host, port=port, debug=False, use_reloader=False, threaded=True)
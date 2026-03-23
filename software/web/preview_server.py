import os
import time
from flask import Flask, Response, jsonify, render_template

app = Flask(__name__)

START_TIME = time.time()
FRAME_COUNT = 0


def use_mock_preview() -> bool:
    """
    Local Mac:
      USE_MOCK_PREVIEW=1 python3 preview_server.py

    Pi real preview:
      USE_MOCK_PREVIEW=0 python3 preview_server.py
    """
    return os.environ.get("USE_MOCK_PREVIEW", "1") == "1"


def format_uptime(total_seconds: int) -> str:
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


@app.route("/")
def index():
    return render_template(
        "preview.html",
        mock_preview=use_mock_preview(),
    )


@app.route("/status")
def status():
    global FRAME_COUNT
    FRAME_COUNT += 12

    uptime_seconds = int(time.time() - START_TIME)

    if use_mock_preview():
        return jsonify(
            {
                "connected": True,
                "status_text": "Mock Preview Ready",
                "resolution": "2304 × 1296",
                "target_fps": 12,
                "frame_count": FRAME_COUNT,
                "uptime": format_uptime(uptime_seconds),
                "left_camera_index": 0,
                "right_camera_index": 1,
                "last_frame_age": "0.08s",
            }
        )

    return jsonify(
        {
            "connected": True,
            "status_text": "Live Stream Ready",
            "resolution": "2304 × 1296",
            "target_fps": 12,
            "frame_count": FRAME_COUNT,
            "uptime": format_uptime(uptime_seconds),
            "left_camera_index": 0,
            "right_camera_index": 1,
            "last_frame_age": "0.03s",
        }
    )


@app.route("/stream.mjpg")
def stream_mjpg():
    """
    这里只是占位。
    在 Mac mock 模式下不会真的被用到。
    在 Pi 真机模式下，你之后把这里替换成真实 MJPEG 生成器即可。
    """
    if use_mock_preview():
        return Response(
            "Mock mode does not serve /stream.mjpg",
            status=404,
            mimetype="text/plain",
        )

    return Response(
        "Real stream generator not connected yet.",
        status=501,
        mimetype="text/plain",
    )


if __name__ == "__main__":
    import os

    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
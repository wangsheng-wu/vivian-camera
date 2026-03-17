#!/usr/bin/env python3

from __future__ import annotations

import sys
from pathlib import Path


CURRENT_FILE = Path(__file__).resolve()
SOFTWARE_DIR = CURRENT_FILE.parent.parent
if str(SOFTWARE_DIR) not in sys.path:
    sys.path.insert(0, str(SOFTWARE_DIR))

from core.camera_manager import CameraManager  # noqa: E402
from core.capture_manager import CaptureManager  # noqa: E402
from core.storage_manager import StorageManager  # noqa: E402


def main() -> None:
    config_path = SOFTWARE_DIR / "config" / "camera.yaml"

    camera_manager = CameraManager(config_path=config_path)
    config = camera_manager.get_config()

    storage_manager = StorageManager(config=config)
    capture_manager = CaptureManager(
        config=config,
        storage_manager=storage_manager,
    )

    print("=== Vivian Camera: capture pair ===")
    print(f"Using config: {config_path}")
    print()

    detected = camera_manager.detect_available_cameras()
    print(f"Detected cameras: {len(detected)}")
    if len(detected) < 2:
        raise RuntimeError("At least 2 cameras are required for stereo capture.")

    print("Setting up cameras...")
    camera_manager.setup_cameras()

    left_cam = camera_manager.get_camera("left")
    right_cam = camera_manager.get_camera("right")

    if left_cam is None:
        raise RuntimeError("Left camera is not available after setup.")
    if right_cam is None:
        raise RuntimeError("Right camera is not available after setup.")

    try:
        print("Starting cameras...")
        camera_manager.start_all()

        print("Warming up cameras...")
        camera_manager.warmup_all()

        session_dir = storage_manager.create_session_dir()
        print(f"Session directory: {session_dir}")

        print("Capturing pair_0001...")
        result = capture_manager.capture_pair(
            left_cam=left_cam,
            right_cam=right_cam,
            session_dir=session_dir,
            pair_index=1,
        )

        print()
        print("Capture completed.")
        print(f"Left image : {result['files']['left']}")
        print(f"Right image: {result['files']['right']}")
        print(f"Sensor delta (ns): {result['timing']['sensor_delta_ns']}")

    finally:
        print()
        print("Shutting down cameras...")
        camera_manager.shutdown_all()
        print("Done.")


if __name__ == "__main__":
    main()
#!/usr/bin/env python3

from __future__ import annotations

import sys
from pathlib import Path


CURRENT_FILE = Path(__file__).resolve()
SOFTWARE_DIR = CURRENT_FILE.parent.parent
if str(SOFTWARE_DIR) not in sys.path:
    sys.path.insert(0, str(SOFTWARE_DIR))


from core.camera_manager import CameraManager  # noqa: E402


def main() -> None:
    config_path = SOFTWARE_DIR / "config" / "camera.yaml"
    manager = CameraManager(config_path=config_path)

    cameras = manager.detect_available_cameras()

    print("=== Vivian Camera: detected cameras ===")
    print(f"Config file: {config_path}")
    print(f"Detected count: {len(cameras)}")
    print()

    if not cameras:
        print("No cameras detected.")
        return

    for item in cameras:
        detected_order = item["detected_order"]
        info = item["info"]

        print(f"[{detected_order}]")
        print(info)
        print()


if __name__ == "__main__":
    main()
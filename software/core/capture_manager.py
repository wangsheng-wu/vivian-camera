from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Dict

from picamera2 import Picamera2

from core.storage_manager import StorageManager


class CaptureManager:
    """
    Responsible for:
    - capturing a stereo pair
    - saving images
    - saving capture metadata
    """

    def __init__(self, config: Dict[str, Any], storage_manager: StorageManager) -> None:
        self.config = config
        self.storage_manager = storage_manager

    def _capture_one_request(self, cam: Picamera2):
        return cam.capture_request(flush=True)

    def _save_request(self, request, output_path: Path) -> Dict[str, Any]:
        request.save("main", str(output_path))
        metadata = request.get_metadata()
        request.release()
        return metadata

    def _extract_useful_metadata(self, metadata: Dict[str, Any]) -> Dict[str, Any]:
        keys_of_interest = [
            "SensorTimestamp",
            "ExposureTime",
            "AnalogueGain",
            "DigitalGain",
            "Lux",
            "FrameDuration",
            "ColourGains",
        ]
        return {k: metadata.get(k) for k in keys_of_interest if k in metadata}

    def capture_pair(
        self,
        left_cam: Picamera2,
        right_cam: Picamera2,
        session_dir: str | Path,
        pair_index: int,
    ) -> Dict[str, Any]:
        """
        Capture left/right requests as close together as possible in software.
        """
        session_dir = Path(session_dir)
        paths = self.storage_manager.build_pair_paths(session_dir, pair_index)

        t0_ns = time.monotonic_ns()

        with ThreadPoolExecutor(max_workers=2) as executor:
            future_left = executor.submit(self._capture_one_request, left_cam)
            future_right = executor.submit(self._capture_one_request, right_cam)

            left_request = future_left.result()
            right_request = future_right.result()

        t1_ns = time.monotonic_ns()

        left_meta = self._save_request(left_request, paths["left_image"])
        right_meta = self._save_request(right_request, paths["right_image"])

        left_ts = left_meta.get("SensorTimestamp")
        right_ts = right_meta.get("SensorTimestamp")

        sensor_delta_ns = None
        if left_ts is not None and right_ts is not None:
            sensor_delta_ns = abs(int(left_ts) - int(right_ts))

        result = {
            "pair_index": pair_index,
            "capture_call_start_monotonic_ns": t0_ns,
            "capture_call_end_monotonic_ns": t1_ns,
            "wall_clock_iso": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "files": {
                "left": str(paths["left_image"]),
                "right": str(paths["right_image"]),
            },
            "timing": {
                "sensor_delta_ns": sensor_delta_ns,
            },
            "left_metadata": self._extract_useful_metadata(left_meta),
            "right_metadata": self._extract_useful_metadata(right_meta),
        }

        self.storage_manager.write_metadata(paths["metadata"], result)
        return result
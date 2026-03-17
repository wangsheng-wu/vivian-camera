from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from picamera2 import Picamera2

class CameraManager:
    """
    Reponsible for:
    - loading camera config
    - discovering available cameras
    - creating/configuring Picamera2 instances
    - starting/stopping all managed cameras
    """

    def __init__(self, config_path: str | Path) -> None:
        self.config_path = Path(config_path)
        self.config = self._load_config(self.config_path)
        self.cameras: Dict[str, Picamera2] = {}

    def _load_config(self, config_path: Path) -> dict[str, Any]:
        if not config_path.exists():
            raise FileNotFoundError(f"Config file not foun: {config_path}")

        with config_path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        
        if not isinstance(data, dict):
            raise ValueError("camera.yaml must contain a top-level mapping.")

        return data

    def get_config(self) -> Dict[str, Any]:
        return self.config

    def detect_available_cameras(self) -> List[Dict[str, Any]]:
        """
        Detect available cameras based on Picamera2.global_camera_info().
        """
        try:
            infos = Picamera2.global_camera_info()
        except RuntimeError as e:
            raise RuntimeError(f"Failed to detect cameras: {e}") from e
        
        if infos is None:
            return []
        
        result: List[Dict[str, Any]] = []
        for i, info in enumerate(infos):
            item = {
                "detected_order": i,
                "info": info,
            }
            result.append(item)

        return result
    
    def _build_single_camera(self, role: str) -> Picamera2:
        cameras_cfg = self.config.get("cameras", {})
        capture_cfg = self.config.get("capture", {})

        if role not in cameras_cfg:
            raise KeyError(f"Camera role '{role}' not found in config.")

        role_cfg = cameras_cfg[role]
        enabled = bool(role_cfg.get("enabled", True))
        if not enabled:
            raise ValueError(f"Camera role '{role}' is disabled in config.")
        
        camera_index = int(role_cfg["index"])
        still_width = int(capture_cfg.get("still_width", 2304))
        still_height = int(capture_cfg.get("still_height", 1296))

        picam = Picamera2(camera_index)

        still_config = picam.create_still_configuration(
            main={"size": (still_width, still_height)},
            buffer_count=3,
        )
        picam.configure(still_config)

        return picam

    def setup_cameras(self) -> Dict[str, Picamera2]:
        """
        Setup all cameras based on config.
        """
        cameras_cfg = self.config.get("cameras", {})
        created: Dict[str, Picamera2] = {}

        for role, role_cfg in cameras_cfg.items():
            if not bool(role_cfg.get("enabled", True)):
                continue
            created[role] = self._build_single_camera(role)

        self.cameras = created
        return self.cameras
    
    def start_all(self) -> None:
        if not self.cameras:
            raise RuntimeError("No cameras have been set up. Call setup_cameras() first.")

        for role, cam in self.cameras.items():
            try:
                cam.start()
            except Exception as e:
                raise RuntimeError(f"Failed to start camera '{role}': {e}") from e
    
    def warmup_all(self) -> None:
        warmup_seconds = float(self.config.get("capture", {}).get("warmup_seconds", 1.5))
        time.sleep(warmup_seconds)
    
    def stop_all(self) -> None:
        for cam in self.cameras.values():
            try:
                cam.stop()
            except Exception:
                pass
    
    def close_all(self) -> None:
        for cam in self.cameras.values():
            try:
                cam.close()
            except Exception:
                pass

    def shutdown_all(self) -> None:
        self.stop_all()
        self.close_all()

    def get_camera(self, role: str) -> Optional[Picamera2]:
        return self.cameras.get(role)
    
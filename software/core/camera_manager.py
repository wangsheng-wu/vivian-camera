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

    
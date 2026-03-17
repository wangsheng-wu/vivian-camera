from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict


class StorageManager:
    """
    Responsible for:
    - building root/session paths
    - generating pair file paths
    - writing metadata json
    """

    def __init__(self, config: Dict[str, Any]) -> None:
        self.config = config
        self.storage_cfg = config.get("storage", {})
        self.naming_cfg = config.get("naming", {})

        root_dir_raw = self.storage_cfg.get("root_dir", "~/vivian_data")
        self.root_dir = Path(root_dir_raw).expanduser()

    def ensure_root_dir(self) -> Path:
        self.root_dir.mkdir(parents=True, exist_ok=True)
        return self.root_dir

    def create_session_dir(self, custom_name: str | None = None) -> Path:
        self.ensure_root_dir()

        session_prefix = self.storage_cfg.get("session_prefix", "session")
        if custom_name is None:
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            session_name = f"{session_prefix}_{timestamp}"
        else:
            session_name = custom_name

        session_dir = self.root_dir / session_name
        session_dir.mkdir(parents=True, exist_ok=True)
        return session_dir

    def build_pair_paths(self, session_dir: str | Path, pair_index: int) -> Dict[str, Path]:
        session_dir = Path(session_dir)

        pair_prefix = self.storage_cfg.get("pair_prefix", "pair")
        left_suffix = self.naming_cfg.get("left_suffix", "left")
        right_suffix = self.naming_cfg.get("right_suffix", "right")
        metadata_suffix = self.naming_cfg.get("metadata_suffix", "meta")

        image_format = self.config.get("capture", {}).get("image_format", "jpg").lower()
        stem = f"{pair_prefix}_{pair_index:04d}"

        left_path = session_dir / f"{stem}_{left_suffix}.{image_format}"
        right_path = session_dir / f"{stem}_{right_suffix}.{image_format}"
        meta_path = session_dir / f"{stem}_{metadata_suffix}.json"

        return {
            "left_image": left_path,
            "right_image": right_path,
            "metadata": meta_path,
        }

    def write_metadata(self, metadata_path: str | Path, data: Dict[str, Any]) -> None:
        metadata_path = Path(metadata_path)
        metadata_path.parent.mkdir(parents=True, exist_ok=True)

        with metadata_path.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
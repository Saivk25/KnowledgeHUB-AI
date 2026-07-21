"""
Storage adapter.

Decision: local filesystem behind a narrow interface (save/read/delete by key)
for the 2-day MVP.
Why over S3/MinIO immediately: zero extra infrastructure for local Docker
Compose. Because every caller goes through this interface, swapping in an
S3-compatible backend later is a one-file change, not a rewrite (see ADR-0007).
"""

from __future__ import annotations

import hashlib
import os
import uuid
from pathlib import Path

from app.core.config import get_settings

settings = get_settings()


class LocalStorage:
    def __init__(self, base_dir: str | None = None):
        self.base_dir = Path(base_dir or settings.STORAGE_DIR)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def save(self, workspace_id: str, filename: str, content: bytes) -> tuple[str, str]:
        """Persist file bytes, return (storage_key, checksum)."""
        checksum = hashlib.sha256(content).hexdigest()
        key = f"{workspace_id}/{uuid.uuid4()}_{filename}"
        full_path = self.base_dir / key
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_bytes(content)
        return key, checksum

    def read(self, storage_key: str) -> bytes:
        full_path = self.base_dir / storage_key
        return full_path.read_bytes()

    def path_for(self, storage_key: str) -> str:
        return str(self.base_dir / storage_key)

    def delete(self, storage_key: str) -> None:
        full_path = self.base_dir / storage_key
        if full_path.exists():
            os.remove(full_path)


_storage: LocalStorage | None = None


def get_storage() -> LocalStorage:
    global _storage
    if _storage is None:
        _storage = LocalStorage()
    return _storage

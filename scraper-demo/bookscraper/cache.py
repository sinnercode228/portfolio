"""Tiny on-disk HTTP cache (URL -> body) with a TTL.

Good enough for scraping jobs: re-running the scraper while tweaking
parsers/exporters does not hit the site again. Files are written atomically,
so an interrupted run never leaves a half-written cache entry.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import threading
import time
from pathlib import Path


class DiskCache:
    def __init__(self, directory: str | Path, ttl_seconds: float = 24 * 3600) -> None:
        self.directory = Path(directory)
        self.ttl = ttl_seconds

    def _path(self, url: str) -> Path:
        digest = hashlib.sha256(url.encode("utf-8")).hexdigest()
        return self.directory / digest[:2] / f"{digest}.json"

    # sync API ---------------------------------------------------------------
    def get_sync(self, url: str) -> str | None:
        path = self._path(url)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError, UnicodeDecodeError):
            return None
        if not isinstance(payload, dict):
            return None
        if self.ttl > 0 and time.time() - payload.get("ts", 0) > self.ttl:
            return None
        if payload.get("url") != url:  # hash collision guard (paranoid)
            return None
        return payload.get("body")

    def set_sync(self, url: str, body: str) -> None:
        path = self._path(url)
        path.parent.mkdir(parents=True, exist_ok=True)
        # unique temp name: two writers of the same URL never share a temp file
        tmp = path.with_suffix(f".{os.getpid()}.{threading.get_ident()}.tmp")
        try:
            tmp.write_text(json.dumps({"url": url, "ts": time.time(), "body": body}), encoding="utf-8")
            os.replace(tmp, path)
        finally:
            tmp.unlink(missing_ok=True)

    # async API (file I/O off the event loop) --------------------------------
    async def get(self, url: str) -> str | None:
        return await asyncio.to_thread(self.get_sync, url)

    async def set(self, url: str, body: str) -> None:
        await asyncio.to_thread(self.set_sync, url, body)

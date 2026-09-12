"""
Process-local singleflight for chapter fill.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any


class ChapterFillGate:
    """One in-flight fill per (youversion_bible_id, book_code, chapter)."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._inflight: dict[tuple[str, str, int], asyncio.Task[Any]] = {}

    async def run(self, key: tuple[str, str, int], factory: Callable[[], Awaitable[Any]]) -> Any:
        async with self._lock:
            existing = self._inflight.get(key)
            if existing is not None:
                task = existing
            else:
                task = asyncio.create_task(factory())
                self._inflight[key] = task

        try:
            return await task
        finally:
            async with self._lock:
                current = self._inflight.get(key)
                if current is task:
                    self._inflight.pop(key, None)

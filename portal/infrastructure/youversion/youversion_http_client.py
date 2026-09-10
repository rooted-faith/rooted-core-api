"""
YouVersion Platform HTTP adapter.
"""

import asyncio
from typing import Any

import httpx

YOUVERSION_BASE_URL = "https://api.youversion.com"
YVP_AUTH_HEADER = "X-YVP-App-Key"


class YouVersionHttpError(Exception):
    """YouVersion HTTP request failed."""

    def __init__(self, status_code: int, url: str, message: str | None = None):
        self.status_code = status_code
        self.url = url
        super().__init__(message or f"HTTP {status_code} GET {url}")


class YouVersionHttpClient:
    """Fetches bible metadata, the Bible index, and chapter HTML from YouVersion."""

    def __init__(
        self, app_key: str, timeout_sec: float = 30.0, max_retries: int = 3, retry_interval: float = 5.0, transport: httpx.AsyncBaseTransport | None = None
    ):
        self._app_key = app_key
        self._timeout_sec = timeout_sec
        self._max_retries = max_retries
        self._retry_interval = retry_interval
        self._transport = transport

    async def get_bible_metadata(self, bible_id: str) -> dict[str, Any]:
        return await self._get(f"/v1/bibles/{bible_id}")

    async def get_bible_index(self, bible_id: str) -> dict[str, Any]:
        return await self._get(f"/v1/bibles/{bible_id}/index")

    async def get_chapter_passage(self, bible_id: str, chapter_usfm: str) -> dict[str, Any]:
        return await self._get(f"/v1/bibles/{bible_id}/passages/{chapter_usfm}", params={"format": "html", "include_headings": "true", "include_notes": "true"})

    async def _get(self, path: str, params: dict[str, str] | None = None) -> dict[str, Any]:
        headers = {"Accept": "application/json", YVP_AUTH_HEADER: self._app_key}
        last_error: Exception | None = None
        attempts = max(self._max_retries, 1)
        async with httpx.AsyncClient(base_url=YOUVERSION_BASE_URL, timeout=self._timeout_sec, transport=self._transport) as client:
            for attempt in range(attempts):
                try:
                    response = await client.get(path, headers=headers, params=params)
                except (httpx.TimeoutException, httpx.ConnectError) as exc:
                    last_error = exc
                    if attempt + 1 < attempts:
                        await asyncio.sleep(self._retry_interval)
                    continue
                if response.status_code >= 400:
                    raise YouVersionHttpError(response.status_code, str(response.request.url))
                return response.json()
        if last_error is not None:
            raise YouVersionHttpError(0, path, message=str(last_error)) from last_error
        raise YouVersionHttpError(0, path)

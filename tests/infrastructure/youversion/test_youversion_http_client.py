"""
YouVersion HTTP adapter: metadata, index, and chapter passage.
"""

import httpx
import pytest

from portal.infrastructure.youversion.youversion_http_client import YouVersionHttpClient, YouVersionHttpError

APP_KEY = "test-app-key-not-a-real-secret"


def _client_with_handler(handler) -> YouVersionHttpClient:
    return YouVersionHttpClient(app_key=APP_KEY, transport=httpx.MockTransport(handler))


@pytest.mark.asyncio
async def test_get_bible_metadata_sends_app_key_and_returns_json():
    captured: dict[str, httpx.Request] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["request"] = request
        return httpx.Response(200, json={"id": 1392, "abbreviation": "CCBT"})

    client = _client_with_handler(handler)
    result = await client.get_bible_metadata("1392")

    request = captured["request"]
    assert request.method == "GET"
    assert request.url.path == "/v1/bibles/1392"
    assert request.headers["X-YVP-App-Key"] == APP_KEY
    assert result == {"id": 1392, "abbreviation": "CCBT"}


@pytest.mark.asyncio
async def test_get_bible_index_sends_app_key_and_returns_json():
    captured: dict[str, httpx.Request] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["request"] = request
        return httpx.Response(200, json={"books": [{"id": "GEN"}]})

    client = _client_with_handler(handler)
    result = await client.get_bible_index("1392")

    request = captured["request"]
    assert request.method == "GET"
    assert request.url.path == "/v1/bibles/1392/index"
    assert request.headers["X-YVP-App-Key"] == APP_KEY
    assert result == {"books": [{"id": "GEN"}]}


@pytest.mark.asyncio
async def test_get_chapter_passage_requests_html_with_headings_and_notes():
    captured: dict[str, httpx.Request] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["request"] = request
        return httpx.Response(200, json={"content": "<div class=\"p\">In the beginning</div>"})

    client = _client_with_handler(handler)
    result = await client.get_chapter_passage("1392", "GEN.1")

    request = captured["request"]
    assert request.method == "GET"
    assert request.url.path == "/v1/bibles/1392/passages/GEN.1"
    assert request.url.params["format"] == "html"
    assert request.url.params["include_headings"] == "true"
    assert request.url.params["include_notes"] == "true"
    assert request.headers["X-YVP-App-Key"] == APP_KEY
    assert result == {"content": "<div class=\"p\">In the beginning</div>"}


@pytest.mark.asyncio
async def test_http_error_does_not_include_app_key():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"message": "Too Many Requests"})

    client = _client_with_handler(handler)
    with pytest.raises(YouVersionHttpError) as exc_info:
        await client.get_bible_metadata("1392")

    assert exc_info.value.status_code == 429
    assert APP_KEY not in str(exc_info.value)
    assert APP_KEY not in exc_info.value.url


@pytest.mark.asyncio
async def test_timeout_raises_without_app_key():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("timed out")

    client = YouVersionHttpClient(app_key=APP_KEY, transport=httpx.MockTransport(handler), max_retries=1, retry_interval=0)
    with pytest.raises(YouVersionHttpError) as exc_info:
        await client.get_bible_metadata("1392")

    assert exc_info.value.status_code == 0
    assert APP_KEY not in str(exc_info.value)

import json
import logging

import httpx
import pytest

from config import NOTION_VERSION, PROP
from notion_api import NotionClient, NotionError


def test_requests_send_the_auth_and_version_headers():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"ok": True})

    with _client(handler) as client:
        assert client._request("GET", "/v1/users/me") == {"ok": True}

    request = seen[0]
    assert request.headers["Authorization"] == "Bearer test-token"
    assert request.headers["Notion-Version"] == NOTION_VERSION
    assert request.headers["Content-Type"] == "application/json"
    assert str(request.url) == "https://api.notion.com/v1/users/me"


def test_a_429_is_retried_after_the_retry_after_header():
    sleeps: list[float] = []
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(429, headers={"Retry-After": "2"})
        return httpx.Response(200, json={"ok": True})

    with _client(handler, sleeps.append) as client:
        assert client._request("GET", "/v1/users/me") == {"ok": True}

    assert calls == 2
    assert sleeps == [2]


def test_a_5xx_is_retried_three_times_then_raises():
    sleeps: list[float] = []
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(500)

    with _client(handler, sleeps.append) as client:
        with pytest.raises(NotionError) as exc_info:
            client._request("GET", "/v1/users/me")

    assert calls == 4
    assert sleeps == [1, 2, 4]
    assert exc_info.value.status == 500


def test_a_network_error_is_retried_then_raises_with_status_zero():
    sleeps: list[float] = []
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise httpx.ConnectError("connection refused")

    with _client(handler, sleeps.append) as client:
        with pytest.raises(NotionError) as exc_info:
            client._request("GET", "/v1/users/me")

    assert calls == 4
    assert sleeps == [1, 2, 4]
    error = exc_info.value
    assert error.status == 0
    assert error.code is None
    assert error.message == "connection refused"


def test_a_400_raises_at_once_with_the_api_code_and_message():
    sleeps: list[float] = []
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(
            400,
            json={
                "object": "error",
                "status": 400,
                "code": "validation_error",
                "message": "The request body is invalid.",
            },
        )

    with _client(handler, sleeps.append) as client:
        with pytest.raises(NotionError) as exc_info:
            client._request("POST", "/v1/pages", json={"properties": {}})

    assert calls == 1
    assert sleeps == []
    error = exc_info.value
    assert error.status == 400
    assert error.code == "validation_error"
    assert error.message == "The request body is invalid."
    assert str(error) == "400 validation_error The request body is invalid."


def test_query_sends_an_or_filter_with_each_column():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"results": [], "has_more": False})

    with _client(handler, data_source_id="ds-42") as client:
        assert client.query_pipeline_items(["TO REFINE", "PLAN"]) == []

    request = seen[0]
    assert request.method == "POST"
    assert request.url.path == "/v1/data_sources/ds-42/query"
    assert json.loads(request.content) == {
        "filter": {
            "or": [
                {"property": PROP["pipeline"], "select": {"equals": "TO REFINE"}},
                {"property": PROP["pipeline"], "select": {"equals": "PLAN"}},
            ]
        },
        "page_size": 100,
    }


def test_query_follows_pagination_and_keeps_only_pages():
    page_one = {"object": "page", "id": "page-1"}
    page_two = {"object": "page", "id": "page-2"}
    payloads = [
        {
            "results": [page_one, {"object": "data_source", "id": "ds-other"}],
            "has_more": True,
            "next_cursor": "cursor-2",
        },
        {
            "results": [page_two],
            "has_more": False,
            "next_cursor": None,
        },
    ]
    seen: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return httpx.Response(200, json=payloads[len(seen) - 1])

    with _client(handler, data_source_id="ds-42") as client:
        assert client.query_pipeline_items(["AI EXECUTE"]) == [page_one, page_two]

    assert "start_cursor" not in seen[0]
    assert seen[1]["start_cursor"] == "cursor-2"
    assert seen[1]["page_size"] == 100


def test_get_page_markdown_returns_the_markdown_and_warns_when_truncated(caplog):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/v1/pages/page-1/markdown"
        return httpx.Response(
            200,
            json={"markdown": "# Titulo\n\ntexto", "truncated": True},
        )

    caplog.set_level(logging.WARNING)
    with _client(handler) as client:
        assert client.get_page_markdown("page-1") == "# Titulo\n\ntexto"

    assert "page-1" in caplog.text
    assert any(record.levelno == logging.WARNING for record in caplog.records)


def test_insert_markdown_sends_the_insert_content_body():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"object": "page_markdown"})

    with _client(handler) as client:
        client.insert_markdown("page-9", "novo bloco", "end")

    request = seen[0]
    assert request.method == "PATCH"
    assert request.url.path == "/v1/pages/page-9/markdown"
    assert json.loads(request.content) == {
        "type": "insert_content",
        "insert_content": {
            "content": "novo bloco",
            "position": {"type": "end"},
        },
    }


def test_update_properties_sends_a_patch_with_the_properties():
    seen: list[httpx.Request] = []
    properties = {"Pipeline": {"select": {"name": "PLAN"}}}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"object": "page", "id": "page-9"})

    with _client(handler) as client:
        client.update_properties("page-9", properties)

    request = seen[0]
    assert request.method == "PATCH"
    assert request.url.path == "/v1/pages/page-9"
    assert json.loads(request.content) == {"properties": properties}


def _client(
    handler,
    sleep=lambda _seconds: None,
    *,
    data_source_id: str = "data-source-1",
) -> NotionClient:
    return NotionClient(
        "test-token",
        data_source_id,
        transport=httpx.MockTransport(handler),
        sleep=sleep,
    )

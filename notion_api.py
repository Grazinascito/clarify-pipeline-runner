import logging
import time
from collections.abc import Callable
from typing import Literal

import httpx

from config import NOTION_VERSION, PROP

_MAX_ATTEMPTS = 4
_SERVER_ERROR_DELAYS = (1, 2, 4)


class NotionError(Exception):
    def __init__(self, status: int, code: str | None, message: str) -> None:
        self.status = status
        self.code = code
        self.message = message
        super().__init__(status, code, message)

    def __str__(self) -> str:
        return f"{self.status} {self.code} {self.message}"


class NotionClient:
    def __init__(
        self,
        token: str,
        data_source_id: str,
        *,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._data_source_id = data_source_id
        self._sleep = sleep
        self._client = httpx.Client(
            base_url="https://api.notion.com",
            timeout=30,
            headers={
                "Authorization": f"Bearer {token}",
                "Notion-Version": NOTION_VERSION,
                "Content-Type": "application/json",
            },
            transport=transport,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> NotionClient:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: object,
    ) -> None:
        self.close()

    def _request(self, method: str, path: str, json: dict | None = None) -> dict:
        for attempt in range(_MAX_ATTEMPTS):
            try:
                response = self._client.request(method, path, json=json)
            except httpx.TransportError as exc:
                error = NotionError(0, None, str(exc))
                if attempt == _MAX_ATTEMPTS - 1:
                    raise error
                self._sleep(_SERVER_ERROR_DELAYS[attempt])
                continue

            if response.status_code == 429 or response.status_code >= 500:
                error = _error_from_response(response)
                if attempt == _MAX_ATTEMPTS - 1:
                    raise error
                if response.status_code == 429:
                    self._sleep(_retry_after_seconds(response))
                else:
                    self._sleep(_SERVER_ERROR_DELAYS[attempt])
                continue

            if response.status_code >= 400:
                raise _error_from_response(response)

            payload = response.json()
            if not isinstance(payload, dict):
                raise NotionError(
                    response.status_code,
                    None,
                    "Response JSON is not an object",
                )
            return payload

        raise NotionError(0, None, "Request failed without a response")

    def query_pipeline_items(self, columns: list[str]) -> list[dict]:
        pages: list[dict] = []
        body: dict = {
            "filter": {
                "or": [
                    {
                        "property": PROP["pipeline"],
                        "select": {"equals": column},
                    }
                    for column in columns
                ]
            },
            "page_size": 100,
        }
        while True:
            payload = self._request(
                "POST",
                f"/v1/data_sources/{self._data_source_id}/query",
                json=body,
            )
            for result in payload["results"]:
                if result.get("object") == "page":
                    pages.append(result)
            if not payload.get("has_more"):
                return pages
            body = {**body, "start_cursor": payload["next_cursor"]}

    def get_page_markdown(self, page_id: str) -> str:
        body = self._request("GET", f"/v1/pages/{page_id}/markdown")
        if body.get("truncated"):
            logging.getLogger(__name__).warning(
                "Notion markdown response truncated for page %s",
                page_id,
            )
        return body["markdown"]

    def insert_markdown(
        self,
        page_id: str,
        content: str,
        position: Literal["start", "end"],
    ) -> None:
        self._request(
            "PATCH",
            f"/v1/pages/{page_id}/markdown",
            json={
                "type": "insert_content",
                "insert_content": {
                    "content": content,
                    "position": {"type": position},
                },
            },
        )

    def update_properties(self, page_id: str, properties: dict) -> None:
        self._request(
            "PATCH",
            f"/v1/pages/{page_id}",
            json={"properties": properties},
        )


def _retry_after_seconds(response: httpx.Response) -> float:
    header = response.headers.get("Retry-After")
    if header is None or header.strip() == "":
        return 1
    return float(header)


def _error_from_response(response: httpx.Response) -> NotionError:
    code: str | None = None
    message = ""
    try:
        body = response.json()
    except ValueError:
        body = None
    if isinstance(body, dict):
        raw_code = body.get("code")
        raw_message = body.get("message")
        if isinstance(raw_code, str):
            code = raw_code
        if isinstance(raw_message, str):
            message = raw_message
    return NotionError(response.status_code, code, message)

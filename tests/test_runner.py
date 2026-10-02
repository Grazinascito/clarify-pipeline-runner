import logging
from datetime import datetime, timedelta, timezone

from claude_runner import ClaudeError, ClaudeResult
from config import COL_REFINED, COL_TO_REFINE, IA_ERROR, IA_RUNNING, PROP, Settings
from items import Item

import runner

NOW = datetime(2026, 10, 1, 14, 5, tzinfo=timezone.utc)
SETTINGS = Settings(
    notion_token="notion-token",
    glm_api_key="glm-key",
    notion_data_source_id="data-source",
)
PAGE_ID = "11111111-1111-4111-8111-111111111111"


def test_process_item_writes_the_original_record_before_the_section(monkeypatch):
    client = FakeClient("página sem registro")
    monkeypatch.setattr(runner, "run_claude", _claude_ok)

    runner.process_item(client, _item(), SETTINGS, lambda: NOW)

    assert [call[0] for call in client.calls] == [
        "update_properties",
        "get_page_markdown",
        "insert_markdown",
        "insert_markdown",
        "update_properties",
    ]
    assert client.calls[0][2][PROP["ia_status"]]["select"]["name"] == IA_RUNNING
    assert client.calls[2][3] == "start"
    assert client.calls[3][3] == "end"
    assert client.calls[4][2][PROP["pipeline"]]["select"]["name"] == COL_REFINED


def test_process_item_skips_the_original_record_when_it_already_exists(monkeypatch):
    client = FakeClient("## 📝 Registro original\n\n> comprar organizador de remedio")
    monkeypatch.setattr(runner, "run_claude", _claude_ok)

    runner.process_item(client, _item(), SETTINGS, lambda: NOW)

    positions = [call[3] for call in client.calls if call[0] == "insert_markdown"]
    assert "start" not in positions
    assert positions == ["end"]


def test_process_item_marks_error_when_claude_fails(monkeypatch):
    def fail_claude(*_args, **_kwargs):
        raise ClaudeError("max_turns", "Claude atingiu o limite de turnos")

    client = FakeClient("")
    monkeypatch.setattr(runner, "run_claude", fail_claude)

    runner.process_item(client, _item(), SETTINGS, lambda: NOW)

    assert client.calls[-1][0] == "update_properties"
    assert client.calls[-1][2][PROP["ia_status"]]["select"]["name"] == IA_ERROR
    notes = [call[2] for call in client.calls if call[0] == "insert_markdown"]
    assert any("max_turns" in note for note in notes)


def test_process_item_marks_error_on_an_unexpected_exception(monkeypatch):
    def fail_claude(*_args, **_kwargs):
        raise RuntimeError("inesperado")

    client = FakeClient("")
    monkeypatch.setattr(runner, "run_claude", fail_claude)

    runner.process_item(client, _item(), SETTINGS, lambda: NOW)

    assert client.calls[-1][0] == "update_properties"
    assert client.calls[-1][2][PROP["ia_status"]]["select"]["name"] == IA_ERROR


def test_mark_stale_items_marks_error_and_removes_the_card():
    stale = _item(
        page_id="stale-page",
        ia_status=IA_RUNNING,
        ia_updated_at=NOW - timedelta(minutes=31),
    )
    fresh = _item(page_id="fresh-page", ia_status=None)
    client = FakeClient("")

    remaining = runner.mark_stale_items(client, [stale, fresh], NOW)

    assert [item.page_id for item in remaining] == ["fresh-page"]
    assert client.calls[0][0] == "insert_markdown"
    assert client.calls[0][1] == "stale-page"
    assert "travado" in client.calls[0][2]
    assert client.calls[1][0] == "update_properties"
    assert client.calls[1][1] == "stale-page"
    assert client.calls[1][2][PROP["ia_status"]]["select"]["name"] == IA_ERROR


def test_main_returns_one_and_logs_when_settings_fail(tmp_path, monkeypatch):
    logs = tmp_path / "logs"
    monkeypatch.setattr(runner, "LOGS_DIR", logs)
    monkeypatch.setattr(runner, "LOCK_PATH", tmp_path / "run" / "runner.lock")

    def fail_settings():
        raise SystemExit("Falta NOTION_TOKEN no .env")

    monkeypatch.setattr(runner, "load_settings", fail_settings)

    try:
        code = runner.main([])
        text = (logs / "runner.log").read_text()
    finally:
        _close_loggers()

    assert code == 1
    assert "- - falha na rodada: SystemExit: Falta NOTION_TOKEN no .env" in text


class FakeClient:
    def __init__(self, markdown: str) -> None:
        self.markdown = markdown
        self.calls: list[tuple] = []

    def query_pipeline_items(self, columns: list[str]) -> list[dict]:
        self.calls.append(("query_pipeline_items", columns))
        return []

    def get_page_markdown(self, page_id: str) -> str:
        self.calls.append(("get_page_markdown", page_id))
        return self.markdown

    def insert_markdown(self, page_id: str, content: str, position: str) -> None:
        self.calls.append(("insert_markdown", page_id, content, position))

    def update_properties(self, page_id: str, properties: dict) -> None:
        self.calls.append(("update_properties", page_id, properties))


def _claude_ok(*_args, **_kwargs) -> ClaudeResult:
    return ClaudeResult(
        markdown="### Contexto\n\ntexto",
        new_title=None,
        ia_status="ok",
        suggested_executor=None,
        num_turns=1,
        session_id="test-session",
    )


def _item(**overrides) -> Item:
    fields = {
        "page_id": PAGE_ID,
        "url": "https://www.notion.so/card",
        "title": "comprar organizador de remedio",
        "pipeline": COL_TO_REFINE,
        "executor": None,
        "ia_status": None,
        "ia_updated_at": None,
        "created": datetime(2026, 9, 1, tzinfo=timezone.utc),
        "type": None,
        "area": None,
        "details": "",
        "due_date": None,
    }
    fields.update(overrides)
    return Item(**fields)


def _close_loggers() -> None:
    for name in ("clarify-pipeline-runner", "notion_api"):
        logger = logging.getLogger(name)
        for handler in list(logger.handlers):
            handler.close()
            logger.removeHandler(handler)

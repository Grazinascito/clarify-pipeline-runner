import argparse
import fcntl
import logging
from collections.abc import Callable
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

from claude_runner import ClaudeError, run_claude, write_mcp_config
from config import (
    LOCK_PATH,
    LOGS_DIR,
    MAX_ITEMS_PER_RUN,
    MCP_CONFIG_PATH,
    RUNS_LOG_DIR,
    STAGES,
    Settings,
    load_settings,
)
from items import (
    Item,
    is_stale,
    parse_item,
    props_error,
    props_running,
    props_success,
    select_items,
)
from notion_api import NotionClient, NotionError
from page_writer import (
    build_context,
    build_error_note,
    build_original_record,
    build_section,
    needs_original_record,
)

_LOGGER_NAME = "clarify-pipeline-runner"


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    logger = setup_logging(LOGS_DIR)
    lock = _acquire_lock(LOCK_PATH)
    if lock is None:
        _log(logger, "-", "-", "rodada anterior ainda em andamento")
        return 0
    try:
        settings = load_settings()
        with NotionClient(settings.notion_token, settings.notion_data_source_id) as client:
            if not args.dry_run:
                write_mcp_config(MCP_CONFIG_PATH, settings.glm_api_key)
            items = fetch_candidates(client)
            if not args.dry_run:
                items = mark_stale_items(client, items, _local_now(), logger)
            if args.page is not None:
                items = [item for item in items if _same_page(item.page_id, args.page)]
            limit = len(items) if args.page is not None else MAX_ITEMS_PER_RUN
            chosen = select_items(items, limit)
            if args.dry_run:
                _log_dry_run(logger, chosen, args.page)
                return 0
            if args.page is not None and not chosen:
                _log(logger, args.page, "-", "fora da rodada")
                return 0
            for item in chosen:
                process_item(client, item, settings, _local_now, logger)
        return 0
    finally:
        lock.close()


def fetch_candidates(client: NotionClient) -> list[Item]:
    pages = client.query_pipeline_items(list(STAGES))
    return [parse_item(page) for page in pages]


def mark_stale_items(
    client: NotionClient,
    items: list[Item],
    now: datetime,
    logger: logging.Logger | None = None,
) -> list[Item]:
    logger = logger or logging.getLogger(_LOGGER_NAME)
    fresh: list[Item] = []
    for item in items:
        if not is_stale(item, now):
            fresh.append(item)
            continue
        stage = item.pipeline or "-"
        try:
            client.insert_markdown(
                item.page_id,
                build_error_note("travado", "runner.log", now),
                "end",
            )
            client.update_properties(item.page_id, props_error(now))
            _log(logger, item.page_id, stage, "travado")
        except NotionError as exc:
            _log(logger, item.page_id, stage, f"travado {exc}", level=logging.ERROR)
    return fresh


def process_item(
    client: NotionClient,
    item: Item,
    settings: Settings,
    now_fn: Callable[[], datetime],
    logger: logging.Logger | None = None,
) -> None:
    logger = logger or logging.getLogger(_LOGGER_NAME)
    pipeline = item.pipeline or "-"
    stage_name = pipeline
    log_name = "runner.log"
    try:
        if pipeline not in STAGES:
            raise ValueError(f"card {item.page_id} fora das colunas da IA")
        stage = STAGES[pipeline]
        stage_name = stage.column
        client.update_properties(item.page_id, props_running(now_fn()))
        page_markdown = client.get_page_markdown(item.page_id)
        if needs_original_record(page_markdown):
            client.insert_markdown(item.page_id, build_original_record(item), "start")
        log_path = RUNS_LOG_DIR / f"{now_fn():%Y%m%dT%H%M%S}-{item.page_id}.json"
        log_name = log_path.name
        result = run_claude(stage, build_context(item, page_markdown), settings, log_path)
        finished = now_fn()
        client.insert_markdown(
            item.page_id,
            build_section(stage, result.markdown, finished),
            "end",
        )
        client.update_properties(
            item.page_id,
            props_success(stage, item, result, finished),
        )
        _log(logger, item.page_id, stage_name, result.ia_status)
    except Exception as exc:
        _record_failure(client, item, stage_name, exc, log_name, now_fn(), logger)


def setup_logging(log_dir: Path) -> logging.Logger:
    log_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(_LOGGER_NAME)
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    logger.propagate = False
    formatter = logging.Formatter("%(asctime)s %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    file_handler = RotatingFileHandler(
        log_dir / "runner.log",
        maxBytes=1_000_000,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)
    notion_logger = logging.getLogger("notion_api")
    notion_logger.setLevel(logging.INFO)
    notion_logger.handlers.clear()
    notion_logger.propagate = False
    notion_logger.addHandler(file_handler)
    notion_logger.addHandler(stream_handler)
    return logger


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="runner.py")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--page")
    return parser.parse_args(argv)


def _acquire_lock(lock_path: Path):
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    handle = lock_path.open("a+")
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        handle.close()
        return None
    return handle


def _record_failure(
    client: NotionClient,
    item: Item,
    stage: str,
    exc: Exception,
    log_name: str,
    now: datetime,
    logger: logging.Logger,
) -> None:
    kind = _error_kind(exc)
    _log(logger, item.page_id, stage, kind, level=logging.ERROR)
    try:
        client.insert_markdown(item.page_id, build_error_note(kind, log_name, now), "end")
        client.update_properties(item.page_id, props_error(now))
    except NotionError as write_error:
        _log(
            logger,
            item.page_id,
            stage,
            f"falha ao gravar erro {write_error}",
            level=logging.ERROR,
        )


def _error_kind(exc: Exception) -> str:
    if isinstance(exc, ClaudeError):
        return exc.kind
    if isinstance(exc, NotionError):
        if exc.status == 0:
            return "rede"
        return "notion"
    return type(exc).__name__


def _log_dry_run(logger: logging.Logger, chosen: list[Item], page: str | None) -> None:
    if not chosen:
        result = "nenhum card para processar" if page is None else "fora da rodada"
        _log(logger, page or "-", "-", result)
        return
    for item in chosen:
        title = " ".join(item.title.split())
        _log(logger, item.page_id, item.pipeline or "-", f"dry-run {title}")


def _log(
    logger: logging.Logger,
    page_id: str,
    stage: str,
    result: str,
    *,
    level: int = logging.INFO,
) -> None:
    logger.log(level, "%s %s %s", page_id, stage, result)


def _local_now() -> datetime:
    return datetime.now().astimezone()


def _same_page(left: str, right: str) -> bool:
    return left.replace("-", "").lower() == right.replace("-", "").lower()


if __name__ == "__main__":
    raise SystemExit(main())

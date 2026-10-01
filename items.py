from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol

from config import (
    COL_AI_EXECUTE,
    COL_HUMAN_EXECUTE,
    COL_PLAN,
    COL_REFINED,
    COL_REVIEW,
    COL_TO_REFINE,
    EXECUTOR_AI,
    EXECUTOR_HUMAN,
    IA_ERROR,
    IA_NEEDS_YOU,
    IA_RUNNING,
    PROP,
    RESULT_NEEDS_YOU,
    RESULT_OK,
    STAGES,
    STALE_AFTER_MINUTES,
    Stage,
)


@dataclass(frozen=True)
class Item:
    page_id: str
    url: str
    title: str
    pipeline: str | None
    executor: str | None
    ia_status: str | None
    ia_updated_at: datetime | None
    created: datetime
    type: str | None
    area: str | None
    details: str
    due_date: str | None


class ClaudeResultLike(Protocol):
    new_title: str | None
    ia_status: str
    suggested_executor: str | None


def parse_item(page: dict) -> Item:
    properties = page["properties"]
    ia_updated_raw = _date_start(properties[PROP["ia_updated_at"]])
    return Item(
        page_id=page["id"],
        url=page["url"],
        title=_plain_text(properties[PROP["name"]]["title"]),
        pipeline=_select_name(properties[PROP["pipeline"]]),
        executor=_select_name(properties[PROP["executor"]]),
        ia_status=_select_name(properties[PROP["ia_status"]]),
        ia_updated_at=None if ia_updated_raw is None else datetime.fromisoformat(ia_updated_raw),
        created=datetime.fromisoformat(properties[PROP["created"]]["created_time"]),
        type=_select_name(properties[PROP["type"]]),
        area=_select_name(properties[PROP["area"]]),
        details=_plain_text(properties[PROP["details"]]["rich_text"]),
        due_date=_date_start(properties[PROP["due_date"]]),
    )


def is_stale(item: Item, now: datetime) -> bool:
    if item.ia_status != IA_RUNNING:
        return False
    if item.ia_updated_at is None:
        return True
    return now - item.ia_updated_at > timedelta(minutes=STALE_AFTER_MINUTES)


def select_items(items: list[Item], limit: int) -> list[Item]:
    stage_index = {column: index for index, column in enumerate(STAGES)}
    chosen = [
        item
        for item in items
        if item.pipeline in stage_index and item.ia_status in (None, IA_NEEDS_YOU)
    ]

    def sort_key(item: Item) -> tuple[int, datetime]:
        pipeline = item.pipeline
        assert pipeline is not None
        return (stage_index[pipeline], item.created)

    chosen.sort(key=sort_key)
    return chosen[:limit]


def next_column(stage: Stage, executor: str | None, ia_status: str) -> str:
    if stage.column == COL_TO_REFINE:
        return COL_REFINED
    if stage.column == COL_AI_EXECUTE:
        return COL_REVIEW
    if stage.column == COL_PLAN:
        if executor == EXECUTOR_HUMAN:
            return COL_HUMAN_EXECUTE
        if executor is None:
            return COL_REFINED
        if executor == EXECUTOR_AI and ia_status == RESULT_OK:
            return COL_AI_EXECUTE
        if executor == EXECUTOR_AI and ia_status == RESULT_NEEDS_YOU:
            return COL_REFINED
    raise ValueError(
        f"sem coluna seguinte para {stage.column}, executor={executor}, ia_status={ia_status}"
    )


def props_running(now: datetime) -> dict:
    return {
        PROP["ia_status"]: _select_property(IA_RUNNING),
        PROP["ia_updated_at"]: _date_property(now),
    }


def props_success(stage: Stage, item: Item, result: ClaudeResultLike, now: datetime) -> dict:
    if result.ia_status == RESULT_NEEDS_YOU or _plan_without_executor(stage, item):
        ia_status = IA_NEEDS_YOU
    else:
        ia_status = None
    properties = {
        PROP["pipeline"]: _select_property(next_column(stage, item.executor, result.ia_status)),
        PROP["ia_status"]: _select_property(ia_status),
        PROP["ia_updated_at"]: _date_property(now),
    }
    new_title = result.new_title
    if stage.can_rename and new_title is not None and new_title.strip():
        properties[PROP["name"]] = {"title": [{"text": {"content": new_title}}]}
    if item.executor is None and result.suggested_executor is not None:
        properties[PROP["executor"]] = _select_property(result.suggested_executor)
    return properties


def props_error(now: datetime) -> dict:
    return {
        PROP["ia_status"]: _select_property(IA_ERROR),
        PROP["ia_updated_at"]: _date_property(now),
    }


def _plan_without_executor(stage: Stage, item: Item) -> bool:
    return stage.column == COL_PLAN and item.executor is None


def _plain_text(parts: list) -> str:
    return "".join(part["plain_text"] for part in parts)


def _select_name(prop: dict) -> str | None:
    selected = prop["select"]
    if selected is None:
        return None
    return selected["name"]


def _date_start(prop: dict) -> str | None:
    date = prop["date"]
    if date is None:
        return None
    return date["start"]


def _select_property(name: str | None) -> dict:
    if name is None:
        return {"select": None}
    return {"select": {"name": name}}


def _date_property(moment: datetime) -> dict:
    return {"date": {"start": moment.isoformat()}}

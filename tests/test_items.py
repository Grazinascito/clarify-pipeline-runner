import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

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
)
from items import (
    Item,
    is_stale,
    next_column,
    parse_item,
    props_error,
    props_success,
    select_items,
)

FIXTURE = Path(__file__).parent / "fixtures" / "query_response.json"
NOW = datetime(2026, 10, 1, 14, 0, tzinfo=timezone.utc)


@dataclass(frozen=True)
class FakeResult:
    new_title: str | None
    ia_status: str
    suggested_executor: str | None


def test_parse_item_reads_pipeline_executor_and_ia_status_from_a_real_query_response():
    payload = json.loads(FIXTURE.read_text())
    items = [parse_item(page) for page in payload["results"]]

    assert [(item.pipeline, item.executor, item.ia_status) for item in items] == [
        (COL_TO_REFINE, None, None),
        (COL_PLAN, EXECUTOR_AI, IA_NEEDS_YOU),
        (COL_AI_EXECUTE, EXECUTOR_HUMAN, IA_RUNNING),
    ]
    assert items[0].ia_updated_at is None
    assert items[1].ia_updated_at == datetime.fromisoformat("2026-09-30T12:00:00.000Z")
    assert items[2].ia_updated_at == datetime.fromisoformat("2026-09-30T13:00:00.000Z")
    assert [item.title for item in items] == [
        "Card de teste 1",
        "Card de teste 2",
        "Card de teste 3",
    ]
    assert [item.details for item in items] == [
        "Card de teste 1",
        "Card de teste 2",
        "Card de teste 3",
    ]
    assert all(item.created.tzinfo is not None for item in items)


def test_select_items_skips_cards_that_are_running_or_in_error():
    ready = _item(page_id="ready", pipeline=COL_TO_REFINE, ia_status=None)
    running = _item(page_id="running", pipeline=COL_PLAN, ia_status=IA_RUNNING)
    error = _item(page_id="error", pipeline=COL_AI_EXECUTE, ia_status=IA_ERROR)

    selected = select_items([running, error, ready], 3)

    assert [item.page_id for item in selected] == ["ready"]


def test_select_items_keeps_cards_marked_as_needing_you():
    needs_you = _item(page_id="needs-you", pipeline=COL_PLAN, ia_status=IA_NEEDS_YOU)

    selected = select_items([needs_you], 3)

    assert [item.page_id for item in selected] == ["needs-you"]


def test_select_items_returns_at_most_three_cards_ordered_by_column_then_by_age():
    to_refine = _item(
        page_id="refine",
        pipeline=COL_TO_REFINE,
        created=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    plan = _item(
        page_id="plan",
        pipeline=COL_PLAN,
        created=datetime(2026, 3, 1, tzinfo=timezone.utc),
    )
    plan_error = _item(
        page_id="plan-error",
        pipeline=COL_PLAN,
        ia_status=IA_ERROR,
        created=datetime(2026, 2, 1, tzinfo=timezone.utc),
    )
    ai_older = _item(
        page_id="ai-older",
        pipeline=COL_AI_EXECUTE,
        created=datetime(2026, 4, 1, tzinfo=timezone.utc),
    )
    ai_newer = _item(
        page_id="ai-newer",
        pipeline=COL_AI_EXECUTE,
        created=datetime(2026, 8, 1, tzinfo=timezone.utc),
    )

    selected = select_items([ai_newer, plan_error, ai_older, plan, to_refine], 3)

    assert [item.page_id for item in selected] == ["refine", "plan", "ai-older"]


def test_is_stale_is_true_only_after_thirty_minutes_of_running():
    assert is_stale(_item(ia_status=IA_RUNNING, ia_updated_at=NOW - timedelta(minutes=29)), NOW) is False
    assert is_stale(_item(ia_status=IA_RUNNING, ia_updated_at=NOW - timedelta(minutes=31)), NOW) is True
    assert is_stale(_item(ia_status=IA_RUNNING, ia_updated_at=None), NOW) is True
    assert is_stale(_item(ia_status=IA_ERROR, ia_updated_at=NOW - timedelta(minutes=31)), NOW) is False


def test_next_column_moves_a_plan_to_ai_execute_when_the_executor_is_ia():
    assert next_column(STAGES[COL_PLAN], EXECUTOR_AI, RESULT_OK) == COL_AI_EXECUTE


def test_next_column_moves_a_plan_to_human_execute_when_the_executor_is_humano():
    assert next_column(STAGES[COL_PLAN], EXECUTOR_HUMAN, RESULT_OK) == COL_HUMAN_EXECUTE
    assert next_column(STAGES[COL_PLAN], EXECUTOR_HUMAN, RESULT_NEEDS_YOU) == COL_HUMAN_EXECUTE


def test_next_column_keeps_a_plan_out_of_ai_execute_when_it_has_open_questions():
    assert next_column(STAGES[COL_PLAN], EXECUTOR_AI, RESULT_NEEDS_YOU) == COL_REFINED


def test_next_column_keeps_a_plan_out_of_ai_execute_when_there_is_no_executor():
    assert next_column(STAGES[COL_PLAN], None, RESULT_OK) == COL_REFINED


def test_next_column_sends_refine_to_refined_and_ai_execute_to_review():
    assert next_column(STAGES[COL_TO_REFINE], None, RESULT_OK) == COL_REFINED
    assert next_column(STAGES[COL_AI_EXECUTE], EXECUTOR_AI, RESULT_OK) == COL_REVIEW


def test_props_success_never_overwrites_an_executor_chosen_by_the_user():
    item = _item(pipeline=COL_PLAN, executor=EXECUTOR_HUMAN)
    result = FakeResult(new_title=None, ia_status=RESULT_OK, suggested_executor=EXECUTOR_AI)

    props = props_success(STAGES[COL_PLAN], item, result, NOW)

    assert PROP["executor"] not in props
    assert props[PROP["pipeline"]] == {"select": {"name": COL_HUMAN_EXECUTE}}


def test_props_success_renames_the_card_only_in_the_refine_stage():
    item = _item(executor=EXECUTOR_AI)
    result = FakeResult(new_title="Titulo novo", ia_status=RESULT_OK, suggested_executor=None)

    plan_props = props_success(STAGES[COL_PLAN], item, result, NOW)
    refine_props = props_success(STAGES[COL_TO_REFINE], item, result, NOW)

    assert PROP["name"] not in plan_props
    assert refine_props[PROP["name"]] == {"title": [{"text": {"content": "Titulo novo"}}]}


def test_props_success_marks_needs_you_when_a_plan_has_no_executor():
    item = _item(pipeline=COL_PLAN, executor=None)
    result = FakeResult(new_title=None, ia_status=RESULT_OK, suggested_executor=EXECUTOR_AI)

    props = props_success(STAGES[COL_PLAN], item, result, NOW)

    assert props[PROP["pipeline"]] == {"select": {"name": COL_REFINED}}
    assert props[PROP["ia_status"]] == {"select": {"name": IA_NEEDS_YOU}}
    assert props[PROP["executor"]] == {"select": {"name": EXECUTOR_AI}}


def test_props_error_keeps_the_pipeline_column():
    props = props_error(NOW)

    assert PROP["pipeline"] not in props
    assert props[PROP["ia_status"]] == {"select": {"name": IA_ERROR}}
    assert props[PROP["ia_updated_at"]] == {"date": {"start": NOW.isoformat()}}


def _item(**overrides) -> Item:
    fields = {
        "page_id": "11111111-1111-4111-8111-111111111111",
        "url": "https://app.notion.com/p/card-de-teste-1-11111111111141118111111111111111",
        "title": "Card de teste",
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

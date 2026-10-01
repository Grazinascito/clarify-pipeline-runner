from datetime import datetime
from zoneinfo import ZoneInfo

from config import STAGES
from items import Item
from page_writer import (
    ORIGINAL_RECORD_TITLE,
    build_context,
    build_error_note,
    build_original_record,
    build_section,
    needs_original_record,
)

NOW = datetime(2026, 10, 1, 14, 5, tzinfo=ZoneInfo("America/Sao_Paulo"))


def test_needs_original_record_is_false_when_the_page_already_has_the_original_record():
    page = f"## {ORIGINAL_RECORD_TITLE}\n\n> comprar organizador de remedio"

    assert needs_original_record(page) is False


def test_needs_original_record_is_true_for_an_empty_page():
    assert needs_original_record("") is True


def test_build_original_record_quotes_the_title_and_adds_details_when_present():
    item = make_item(details="ver na shopee")

    assert build_original_record(item) == (
        "## 📝 Registro original\n"
        "\n"
        "> comprar organizador de remedio\n"
        "\n"
        "**Details:**\n"
        "ver na shopee"
    )


def test_build_original_record_skips_details_when_empty():
    text = build_original_record(make_item())

    assert "**Details:**" not in text


def test_build_original_record_quotes_every_line_of_a_multiline_title():
    item = make_item(title="comprar organizador\nde remedio")

    text = build_original_record(item)

    assert "> comprar organizador\n> de remedio" in text


def test_build_section_starts_with_the_stage_heading_and_the_local_date():
    section = build_section(STAGES["TO REFINE"], "corpo", NOW)

    assert section.splitlines()[0] == "## 🔍 Refinamento — 01/10/2026 14:05"


def test_build_section_removes_a_repeated_stage_heading_from_the_body():
    body = "## 🔍 Refinamento\n\nO modelo repetiu o título."

    section = build_section(STAGES["TO REFINE"], body, NOW)

    assert section.count("## 🔍 Refinamento") == 1
    assert section.endswith("O modelo repetiu o título.")


def test_build_section_keeps_other_headings_in_the_body():
    body = "### Contexto\n\ndetalhe"

    section = build_section(STAGES["TO REFINE"], body, NOW)

    assert "### Contexto" in section.splitlines()


def test_build_error_note_has_the_kind_and_the_log_name():
    note = build_error_note("timeout", "20261001-140500-abc123.json", NOW)

    assert note == "⚠️ Falha da IA em 01/10 14:05: timeout. Log: 20261001-140500-abc123.json."


def test_build_context_includes_the_adjustments_section_when_it_exists():
    page = "## ✏️ Ajustes\n\nmudar o prazo para sexta"

    context = build_context(make_item(), page)

    assert page in context


def test_build_context_marks_empty_properties():
    context = build_context(make_item(type=None), "página")

    assert "- Type: (vazio)" in context


def test_build_context_marks_an_empty_page():
    context = build_context(make_item(), "  \n")

    assert context.endswith("(página vazia)")


def make_item(**overrides) -> Item:
    fields = {
        "page_id": "11111111-1111-4111-8111-111111111111",
        "url": "https://app.notion.com/p/card-11111111111141118111111111111111",
        "title": "comprar organizador de remedio",
        "pipeline": None,
        "executor": None,
        "ia_status": None,
        "ia_updated_at": None,
        "created": datetime(2026, 9, 1, tzinfo=ZoneInfo("America/Sao_Paulo")),
        "type": None,
        "area": None,
        "details": "",
        "due_date": None,
    }
    fields.update(overrides)
    return Item(**fields)

from datetime import datetime

from config import Stage
from items import Item

ORIGINAL_RECORD_TITLE = "📝 Registro original"


def needs_original_record(page_markdown: str) -> bool:
    return ORIGINAL_RECORD_TITLE not in page_markdown


def build_original_record(item: Item) -> str:
    quoted_title = "\n".join(f"> {line}" for line in item.title.splitlines())
    blocks = [f"## {ORIGINAL_RECORD_TITLE}"]
    if quoted_title:
        blocks.append(quoted_title)
    if item.details.strip():
        blocks.append(f"**Details:**\n{item.details}")
    return "\n\n".join(blocks)


def build_section(stage: Stage, body: str, now: datetime) -> str:
    heading = f"## {stage.section_title} — {now:%d/%m/%Y %H:%M}"
    content = _without_repeated_heading(body, stage.section_title).strip()
    if not content:
        return heading
    return f"{heading}\n\n{content}"


def build_error_note(kind: str, log_name: str, now: datetime) -> str:
    return f"⚠️ Falha da IA em {now:%d/%m %H:%M}: {kind}. Log: {log_name}."


def build_context(item: Item, page_markdown: str) -> str:
    page = page_markdown.strip()
    page_text = page if page else "(página vazia)"
    lines = [
        "# Card",
        "",
        f"- Título: {_or_empty(item.title)}",
        f"- Type: {_or_empty(item.type)}",
        f"- Area: {_or_empty(item.area)}",
        f"- Due Date: {_or_empty(item.due_date)}",
        f"- Executor: {_or_empty(item.executor)}",
        f"- Details: {_or_empty(item.details)}",
        "",
        "# Página do card (markdown)",
        "",
        page_text,
    ]
    return "\n".join(lines)


def _or_empty(value: str | None) -> str:
    if value is None or value == "":
        return "(vazio)"
    return value


def _without_repeated_heading(body: str, section_title: str) -> str:
    lines = body.splitlines()
    for index, line in enumerate(lines):
        if line.strip() == "":
            continue
        if line.startswith("#") and section_title in line:
            del lines[index]
        break
    return "\n".join(lines)

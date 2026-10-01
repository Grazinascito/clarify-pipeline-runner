from dataclasses import dataclass
from pathlib import Path

from dotenv import dotenv_values

NOTION_VERSION = "2026-03-11"
MAX_ITEMS_PER_RUN = 3
STALE_AFTER_MINUTES = 30
CLAUDE_TIMEOUT_SECONDS = 900

BASE_DIR = Path(__file__).resolve().parent
CLAUDE_BIN = Path.home() / ".local/bin/claude"
ENV_PATH = BASE_DIR / ".env"
PROMPTS_DIR = BASE_DIR / "prompts"
OUTPUT_SCHEMA_PATH = BASE_DIR / "output_schema.json"
RUN_DIR = BASE_DIR / "run"
MCP_CONFIG_PATH = RUN_DIR / "mcp.json"
LOCK_PATH = RUN_DIR / "runner.lock"
WORKSPACE_DIR = BASE_DIR / "workspace"
LOGS_DIR = BASE_DIR / "logs"
RUNS_LOG_DIR = LOGS_DIR / "runs"

PROP = {
    "pipeline": "Pipeline",
    "executor": "Executor",
    "ia_status": "IA status",
    "ia_updated_at": "IA atualizado em",
    "name": "Name",
    "details": "Details",
    "type": "Type",
    "area": "Area",
    "due_date": "Due Date",
    "created": "Created",
}

COL_BACKLOG = "BACKLOG"
COL_TO_REFINE = "TO REFINE"
COL_REFINED = "REFINED"
COL_PLAN = "PLAN"
COL_HUMAN_EXECUTE = "HUMAN EXECUTE"
COL_AI_EXECUTE = "AI EXECUTE"
COL_REVIEW = "REVIEW"
COL_DONE = "DONE"
COL_ARCHIVED = "ARCHIVED"

IA_RUNNING = "⏳ rodando"
IA_NEEDS_YOU = "❓ precisa de você"
IA_ERROR = "⚠️ erro"
EXECUTOR_HUMAN = "Humano"
EXECUTOR_AI = "IA"
RESULT_OK = "ok"
RESULT_NEEDS_YOU = "precisa_de_voce"


@dataclass(frozen=True)
class Stage:
    column: str
    prompt_file: str
    section_title: str
    max_turns: int
    can_rename: bool


STAGES: dict[str, Stage] = {
    COL_TO_REFINE: Stage(COL_TO_REFINE, "refine.md", "🔍 Refinamento", 15, True),
    COL_PLAN: Stage(COL_PLAN, "plan.md", "🗺️ Plano", 10, False),
    COL_AI_EXECUTE: Stage(COL_AI_EXECUTE, "execute.md", "✅ Resultado", 25, False),
}


@dataclass(frozen=True)
class Settings:
    notion_token: str
    glm_api_key: str
    notion_data_source_id: str


def load_settings(env_path: Path = ENV_PATH) -> Settings:
    values = dotenv_values(env_path)
    required = ("NOTION_TOKEN", "GLM_API_KEY", "NOTION_DATA_SOURCE_ID")
    loaded: dict[str, str] = {}
    for name in required:
        raw = values.get(name)
        if raw is None or raw == "":
            raise SystemExit(f"Falta {name} no .env")
        loaded[name] = raw
    return Settings(
        notion_token=loaded["NOTION_TOKEN"],
        glm_api_key=loaded["GLM_API_KEY"],
        notion_data_source_id=loaded["NOTION_DATA_SOURCE_ID"],
    )

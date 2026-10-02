import json
import os
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import jsonschema

from config import (
    CLAUDE_BIN,
    CLAUDE_TIMEOUT_SECONDS,
    MCP_CONFIG_PATH,
    OUTPUT_SCHEMA_PATH,
    PROMPTS_DIR,
    WORKSPACE_DIR,
    Settings,
    Stage,
)


@dataclass(frozen=True)
class ClaudeResult:
    markdown: str
    new_title: str | None
    ia_status: str
    suggested_executor: str | None
    num_turns: int
    session_id: str


class ClaudeError(Exception):
    def __init__(self, kind: str, message: str) -> None:
        self.kind = kind
        self.message = message
        super().__init__(message)

    def __str__(self) -> str:
        return f"{self.kind}: {self.message}"


def write_mcp_config(path: Path, glm_api_key: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "mcpServers": {
            "web-search-prime": _http_mcp(
                "https://api.z.ai/api/mcp/web_search_prime/mcp",
                glm_api_key,
            ),
            "web-reader": _http_mcp(
                "https://api.z.ai/api/mcp/web_reader/mcp",
                glm_api_key,
            ),
        }
    }
    data = (json.dumps(payload, indent=2) + "\n").encode()
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, data)
    finally:
        os.close(fd)


def build_system_prompt(stage: Stage, prompts_dir: Path = PROMPTS_DIR) -> str:
    base = (prompts_dir / "base.md").read_text()
    stage_prompt = (prompts_dir / stage.prompt_file).read_text()
    return f"{base.rstrip()}\n\n{stage_prompt.lstrip()}"


def build_command(stage: Stage, system_prompt: str, schema: str) -> list[str]:
    return [
        str(CLAUDE_BIN),
        "-p",
        "--bare",
        "--model",
        "sonnet",
        "--append-system-prompt",
        system_prompt,
        "--output-format",
        "json",
        "--json-schema",
        schema,
        "--mcp-config",
        str(MCP_CONFIG_PATH),
        "--strict-mcp-config",
        "--permission-mode",
        "dontAsk",
        "--allowedTools",
        "mcp__web-search-prime,mcp__web-reader",
        "--disallowedTools",
        "Bash,Edit,Write,WebSearch,WebFetch,NotebookEdit",
        "--max-turns",
        str(stage.max_turns),
        "--no-session-persistence",
    ]


def build_env(glm_api_key: str, base_env: Mapping[str, str]) -> dict[str, str]:
    return {
        "ANTHROPIC_BASE_URL": "https://api.z.ai/api/anthropic",
        "ANTHROPIC_AUTH_TOKEN": glm_api_key,
        "ANTHROPIC_DEFAULT_SONNET_MODEL": "glm-5.3[1m]",
        "ANTHROPIC_DEFAULT_HAIKU_MODEL": "glm-5.3-flash[1m]",
        "API_TIMEOUT_MS": "3000000",
        "PATH": base_env.get("PATH", ""),
        "HOME": base_env.get("HOME", ""),
    }


def parse_output(stdout: str) -> ClaudeResult:
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise ClaudeError("invalid_json", "A saída do Claude não é JSON") from exc
    if not isinstance(payload, dict):
        raise ClaudeError("invalid_json", "A saída do Claude não é um objeto JSON")

    if payload.get("subtype") == "error_max_turns":
        raise ClaudeError("max_turns", "Claude atingiu o limite de turnos")

    if payload.get("is_error") is True:
        result = payload.get("result")
        message = result if isinstance(result, str) else ""
        raise ClaudeError("api_error", message)

    structured = payload.get("structured_output")
    if not isinstance(structured, dict):
        raise ClaudeError("schema", "structured_output ausente")

    schema = json.loads(OUTPUT_SCHEMA_PATH.read_text())
    try:
        jsonschema.validate(structured, schema)
    except jsonschema.ValidationError as exc:
        raise ClaudeError("schema", exc.message) from exc

    num_turns = payload.get("num_turns")
    session_id = payload.get("session_id")
    if isinstance(num_turns, bool) or not isinstance(num_turns, int):
        raise ClaudeError("schema", "num_turns ausente")
    if not isinstance(session_id, str) or not session_id:
        raise ClaudeError("schema", "session_id ausente")

    return ClaudeResult(
        markdown=structured["markdown"],
        new_title=_normalize_new_title(structured["new_title"]),
        ia_status=structured["ia_status"],
        suggested_executor=structured["suggested_executor"],
        num_turns=num_turns,
        session_id=session_id,
    )


def run_claude(
    stage: Stage,
    context: str,
    settings: Settings,
    log_path: Path,
) -> ClaudeResult:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)
    command = build_command(
        stage,
        build_system_prompt(stage),
        OUTPUT_SCHEMA_PATH.read_text(),
    )
    secrets = (settings.glm_api_key, settings.notion_token)
    try:
        completed = subprocess.run(
            command,
            input=context,
            capture_output=True,
            text=True,
            cwd=WORKSPACE_DIR,
            env=build_env(settings.glm_api_key, os.environ),
            timeout=CLAUDE_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        _write_run_log(log_path, stage, None, exc.stdout, exc.stderr, secrets)
        raise ClaudeError("timeout", "Claude excedeu o tempo limite") from exc

    _write_run_log(
        log_path,
        stage,
        completed.returncode,
        completed.stdout,
        completed.stderr,
        secrets,
    )
    if completed.stdout != "":
        try:
            return parse_output(completed.stdout)
        except ClaudeError as exc:
            if exc.kind == "invalid_json" and completed.returncode != 0:
                raise ClaudeError("exit_code", _exit_detail(completed)) from exc
            raise
    if completed.returncode != 0:
        raise ClaudeError("exit_code", _exit_detail(completed))
    return parse_output(completed.stdout)


def _normalize_new_title(value: str | None) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    if stripped == "" or stripped.casefold() in {"null", "none"}:
        return None
    return stripped


def _http_mcp(url: str, glm_api_key: str) -> dict:
    return {
        "type": "http",
        "url": url,
        "headers": {"Authorization": f"Bearer {glm_api_key}"},
    }


def _write_run_log(
    log_path: Path,
    stage: Stage,
    returncode: int | None,
    stdout: str | bytes | None,
    stderr: str | bytes | None,
    secrets: tuple[str, ...],
) -> None:
    payload = {
        "stage": stage.column,
        "returncode": returncode,
        "stdout": _redact(_as_text(stdout), secrets),
        "stderr": _redact(_as_text(stderr), secrets),
    }
    log_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def _redact(text: str, secrets: tuple[str, ...]) -> str:
    for secret in secrets:
        if secret:
            text = text.replace(secret, "[redacted]")
    return text


def _exit_detail(completed: subprocess.CompletedProcess[str]) -> str:
    detail = completed.stderr.strip()
    if detail:
        return detail
    return f"Claude saiu com código {completed.returncode}"


def _as_text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode()
    return value

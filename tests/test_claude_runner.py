import json
import subprocess
from pathlib import Path

import pytest

from config import COL_AI_EXECUTE, COL_TO_REFINE, STAGES, Settings
from claude_runner import (
    ClaudeError,
    build_command,
    build_env,
    build_system_prompt,
    parse_output,
    run_claude,
    write_mcp_config,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _result_payload(new_title: str) -> dict:
    return {
        "type": "result",
        "subtype": "success",
        "is_error": False,
        "num_turns": 1,
        "session_id": "sess-title",
        "structured_output": {
            "markdown": "texto",
            "new_title": new_title,
            "ia_status": "ok",
            "suggested_executor": None,
        },
    }


def test_parse_output_returns_a_claude_result_from_a_successful_run():
    stdout = (FIXTURES / "claude_success.json").read_text()
    payload = json.loads(stdout)
    structured = payload["structured_output"]

    result = parse_output(stdout)

    assert result.markdown == structured["markdown"]
    assert result.new_title == structured["new_title"]
    assert result.ia_status == structured["ia_status"]
    assert result.suggested_executor == structured["suggested_executor"]
    assert result.num_turns == payload["num_turns"]
    assert result.session_id == payload["session_id"]


def test_parse_output_treats_null_text_as_no_new_title():
    for raw in ("null", "NULL", " None ", ""):
        result = parse_output(json.dumps(_result_payload(raw)))
        assert result.new_title is None

    result = parse_output(json.dumps(_result_payload("  Comprar caixa  ")))
    assert result.new_title == "Comprar caixa"


def test_parse_output_raises_max_turns_when_the_agent_hits_the_turn_limit():
    stdout = (FIXTURES / "claude_max_turns.json").read_text()

    with pytest.raises(ClaudeError) as exc_info:
        parse_output(stdout)

    assert exc_info.value.kind == "max_turns"


def test_parse_output_raises_schema_when_structured_output_is_missing():
    stdout = (FIXTURES / "claude_no_structured.json").read_text()

    with pytest.raises(ClaudeError) as exc_info:
        parse_output(stdout)

    assert exc_info.value.kind == "schema"


def test_parse_output_raises_invalid_json_when_stdout_is_not_json():
    with pytest.raises(ClaudeError) as exc_info:
        parse_output("erro qualquer")

    assert exc_info.value.kind == "invalid_json"


def test_parse_output_raises_schema_when_structured_output_breaks_the_schema():
    payload = {
        "type": "result",
        "subtype": "success",
        "is_error": False,
        "num_turns": 1,
        "session_id": "sess-bad",
        "result": "",
        "structured_output": {
            "markdown": "texto",
            "new_title": None,
            "ia_status": "talvez",
            "suggested_executor": None,
        },
    }

    with pytest.raises(ClaudeError) as exc_info:
        parse_output(json.dumps(payload))

    assert exc_info.value.kind == "schema"


def test_parse_output_raises_api_error_when_is_error_is_true():
    payload = {
        "type": "result",
        "subtype": "error",
        "is_error": True,
        "num_turns": 1,
        "session_id": "sess-err",
        "result": "cota esgotada",
    }

    with pytest.raises(ClaudeError) as exc_info:
        parse_output(json.dumps(payload))

    error = exc_info.value
    assert error.kind == "api_error"
    assert error.message == "cota esgotada"


def test_build_command_blocks_bash_and_file_editing():
    command = build_command(STAGES[COL_TO_REFINE], "prompt", '{"type":"object"}')

    mode_index = command.index("--permission-mode")
    assert command[mode_index + 1] == "dontAsk"
    disallowed = command[command.index("--disallowedTools") + 1]
    assert "Bash" in disallowed


def test_build_command_uses_the_stage_max_turns():
    refine = build_command(STAGES[COL_TO_REFINE], "prompt", "{}")
    execute = build_command(STAGES[COL_AI_EXECUTE], "prompt", "{}")

    assert refine[refine.index("--max-turns") + 1] == "15"
    assert execute[execute.index("--max-turns") + 1] == "25"


def test_build_env_passes_only_the_allowed_variables():
    env = build_env(
        "test-key",
        {"PATH": "/bin", "HOME": "/tmp/home", "EXTRA": "nope"},
    )

    assert env == {
        "ANTHROPIC_BASE_URL": "https://api.z.ai/api/anthropic",
        "ANTHROPIC_AUTH_TOKEN": "test-key",
        "ANTHROPIC_DEFAULT_SONNET_MODEL": "glm-5.3[1m]",
        "ANTHROPIC_DEFAULT_HAIKU_MODEL": "glm-5.3-flash[1m]",
        "API_TIMEOUT_MS": "3000000",
        "PATH": "/bin",
        "HOME": "/tmp/home",
    }


def test_write_mcp_config_creates_the_file_with_permission_600(tmp_path: Path):
    path = tmp_path / "mcp.json"

    write_mcp_config(path, "test-key")

    assert path.stat().st_mode & 0o777 == 0o600
    data = json.loads(path.read_text())
    assert data["mcpServers"]["web-search-prime"]["headers"]["Authorization"] == "Bearer test-key"
    assert data["mcpServers"]["web-reader"]["url"] == "https://api.z.ai/api/mcp/web_reader/mcp"


def test_run_claude_raises_timeout_and_still_writes_the_log(tmp_path: Path, monkeypatch):
    def fake_run(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="claude", timeout=1, output="parcial", stderr="aviso")

    monkeypatch.setattr("claude_runner.subprocess.run", fake_run)
    log_path = tmp_path / "run.json"
    settings = Settings(
        notion_token="notion-test",
        glm_api_key="glm-test",
        notion_data_source_id="ds-test",
    )

    with pytest.raises(ClaudeError) as exc_info:
        run_claude(STAGES[COL_TO_REFINE], "contexto", settings, log_path)

    assert exc_info.value.kind == "timeout"
    log = json.loads(log_path.read_text())
    assert log["stage"] == COL_TO_REFINE
    assert log["returncode"] is None
    assert log["stdout"] == "parcial"
    assert log["stderr"] == "aviso"
    assert "glm-test" not in log_path.read_text()
    assert "notion-test" not in log_path.read_text()


def test_build_system_prompt_puts_base_rules_before_the_stage_file():
    headings = {
        "refine.md": "# Stage: Refine",
        "plan.md": "# Stage: Plan",
        "execute.md": "# Stage: AI execute",
    }

    for stage in STAGES.values():
        text = build_system_prompt(stage)
        heading = headings[stage.prompt_file]
        assert text.startswith("# Base rules (all stages)")
        assert heading in text
        assert text.index("# Base rules (all stages)") < text.index(heading)

import json
from datetime import UTC, datetime

import httpx
import pytest

from app.gateway.providers.live import (
    AnthropicApi,
    ClaudeCli,
    CodexCli,
    GeminiApi,
    OpenAiApi,
    OpenRouterFree,
)
from app.gateway.types import (
    MalformedOutput,
    ProviderDisabled,
    ProviderError,
    ProviderRequest,
    RateLimited,
)

REQ = ProviderRequest(model="m", prompt="hello", timeout_s=10)


def fake_cli(tmp_path, monkeypatch, name: str, stdout: str, code: int = 0, stderr: str = ""):
    bindir = tmp_path / "bin"
    bindir.mkdir(exist_ok=True)
    payload = tmp_path / f"{name}.out"
    payload.write_text(stdout)
    errf = tmp_path / f"{name}.err"
    errf.write_text(stderr)
    exe = bindir / name
    exe.write_text(
        f"#!/usr/bin/env bash\ncat >/dev/null\ncat {payload}\ncat {errf} >&2\nexit {code}\n"
    )
    exe.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bindir}:/usr/bin:/bin")


# ---------- claude_cli ----------
def test_claude_ok_with_and_without_usage(tmp_path, monkeypatch):
    fake_cli(
        tmp_path,
        monkeypatch,
        "claude",
        json.dumps({"result": "hi", "usage": {"input_tokens": 7, "output_tokens": 3}}),
    )
    r = ClaudeCli().call(REQ)
    assert (r.text, r.input_tokens, r.output_tokens) == ("hi", 7, 3)
    fake_cli(tmp_path, monkeypatch, "claude", json.dumps({"result": "hi"}))
    r = ClaudeCli().call(REQ)
    assert r.input_tokens is None and r.output_tokens is None  # never fabricated


@pytest.mark.parametrize(
    "stdout",
    [
        "",
        "not json",
        "[]",
        json.dumps({"result": ""}),
        json.dumps({"result": 5}),
        json.dumps({"x": 1}),
        "{" * 100,
    ],
)
def test_claude_malformed_outputs(tmp_path, monkeypatch, stdout):
    fake_cli(tmp_path, monkeypatch, "claude", stdout)
    with pytest.raises(MalformedOutput):
        ClaudeCli().call(REQ)


def test_claude_wrong_usage_types_become_none(tmp_path, monkeypatch):
    fake_cli(
        tmp_path,
        monkeypatch,
        "claude",
        json.dumps({"result": "ok", "usage": {"input_tokens": "7", "output_tokens": -1}}),
    )
    r = ClaudeCli().call(REQ)
    assert r.input_tokens is None and r.output_tokens is None


def test_claude_limit_text_is_rate_limited(tmp_path, monkeypatch):
    fake_cli(
        tmp_path,
        monkeypatch,
        "claude",
        json.dumps({"is_error": True, "result": "Claude usage limit reached"}),
    )
    with pytest.raises(RateLimited):
        ClaudeCli().call(REQ)


def test_claude_is_error_other(tmp_path, monkeypatch):
    fake_cli(tmp_path, monkeypatch, "claude", json.dumps({"is_error": True, "result": "boom"}))
    with pytest.raises(ProviderError):
        ClaudeCli().call(REQ)


def test_claude_huge_output_is_capped_not_crashing(tmp_path, monkeypatch):
    fake_cli(tmp_path, monkeypatch, "claude", "x" * 6_000_000)
    with pytest.raises(MalformedOutput):
        ClaudeCli().call(REQ)


def test_claude_argv_disables_tools_and_keeps_prompt_off_argv():
    argv = ClaudeCli().argv(
        ProviderRequest(model="haiku", prompt="SECRET-PROMPT", schema={"type": "object"})
    )
    assert argv[argv.index("--tools") + 1] == ""
    assert "--no-session-persistence" in argv and "--strict-mcp-config" in argv
    assert "SECRET-PROMPT" not in " ".join(argv)


# ---------- codex_cli ----------
def test_codex_jsonl(tmp_path, monkeypatch):
    lines = [
        {"type": "thread.started"},
        {"type": "item.completed", "item": {"type": "agent_message", "text": "the answer"}},
        {"type": "turn.completed", "usage": {"input_tokens": 11, "output_tokens": 4}},
    ]
    fake_cli(
        tmp_path, monkeypatch, "codex", "\n".join(json.dumps(x) for x in lines) + "\ngarbage line\n"
    )
    r = CodexCli().call(REQ)
    assert (r.text, r.input_tokens, r.output_tokens) == ("the answer", 11, 4)


def test_codex_no_message_and_nonzero_exit(tmp_path, monkeypatch):
    fake_cli(tmp_path, monkeypatch, "codex", json.dumps({"type": "turn.completed"}))
    with pytest.raises(MalformedOutput):
        CodexCli().call(REQ)
    fake_cli(tmp_path, monkeypatch, "codex", "", code=1, stderr="rate limit exceeded")
    with pytest.raises(RateLimited):
        CodexCli().call(REQ)


# ---------- HTTP providers ----------
def transport(status=200, body=None, headers=None):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json=body if body is not None else {}, headers=headers or {})

    return httpx.MockTransport(handler)


def test_anthropic_ok_missing_usage_429_500(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-key-value-123")
    ok = {
        "content": [{"type": "text", "text": "yo"}],
        "usage": {"input_tokens": 5, "output_tokens": 2},
    }
    assert AnthropicApi(transport(200, ok)).call(REQ).input_tokens == 5
    r = AnthropicApi(transport(200, {"content": [{"type": "text", "text": "yo"}]})).call(REQ)
    assert r.input_tokens is None
    with pytest.raises(RateLimited) as e:
        AnthropicApi(transport(429, {}, {"retry-after": "30"})).call(REQ)
    assert e.value.reset_at and e.value.reset_at > datetime.now(UTC)
    with pytest.raises(ProviderError, match="http_500"):
        AnthropicApi(transport(500, {"error": "secret details"})).call(REQ)


def test_anthropic_request_shape_and_key_header(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-key-value-123")
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["h"], seen["b"] = dict(request.headers), json.loads(request.content)
        return httpx.Response(200, json={"content": [{"type": "text", "text": "x"}]})

    AnthropicApi(httpx.MockTransport(handler)).call(
        ProviderRequest("claude-haiku-5-5", "p", max_output_tokens=50)
    )
    assert seen["h"]["x-api-key"] == "fake-key-value-123" and seen["b"]["max_tokens"] == 50


def test_gemini_and_openrouter_parse(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key-value-123")
    monkeypatch.setenv("OPENROUTER_API_KEY", "fake-key-value-123")
    g = {
        "candidates": [{"content": {"parts": [{"text": "g"}]}}],
        "usageMetadata": {"promptTokenCount": 3, "candidatesTokenCount": 1},
    }
    assert GeminiApi(transport(200, g)).call(REQ).text == "g"
    o = {
        "choices": [{"message": {"content": "o"}}],
        "usage": {"prompt_tokens": 2, "completion_tokens": 1},
    }
    assert OpenRouterFree(transport(200, o)).call(REQ).output_tokens == 1
    for bad in ({}, {"candidates": []}, {"choices": [{"message": {"content": None}}]}):
        with pytest.raises(MalformedOutput):
            OpenRouterFree(transport(200, bad)).call(REQ)


def test_missing_key_means_unavailable_and_error(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    assert GeminiApi().available() is False
    with pytest.raises(ProviderError, match="key_missing"):
        GeminiApi().call(REQ)


def test_network_failure_has_no_detail(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key-value-123")

    def boom(request):
        raise httpx.ConnectError("secret internals fake-key-value-123")

    with pytest.raises(ProviderError) as e:
        GeminiApi(httpx.MockTransport(boom)).call(REQ)
    assert e.value.kind == "network" and "fake-key" not in str(e.value)


def test_openai_is_disabled():
    assert OpenAiApi().available() is False
    with pytest.raises(ProviderDisabled):
        OpenAiApi().call(REQ)

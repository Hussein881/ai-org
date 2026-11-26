"""Real providers. Raw bodies and stderr are never kept: failures carry a short `kind` only."""

import json
import os
import re
import shutil
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from app.gateway.providers.base import Provider
from app.gateway.subproc import env_is_clean, run_cli
from app.gateway.types import (
    MalformedOutput,
    ProviderDisabled,
    ProviderError,
    ProviderRequest,
    ProviderResponse,
    RateLimited,
)

_LIMIT_TEXT = re.compile(
    r"(?i)usage limit|rate.?limit|limit reached|too many requests|resets? (at|in)"
)


def _int_or_none(v: Any) -> int | None:
    return v if isinstance(v, int) and not isinstance(v, bool) and v >= 0 else None


def _precheck() -> None:
    """The launch-path guard runs before the prompt exists anywhere outside this process, so any
    failure here (including being killed by a stop) means nothing was sent."""
    try:
        clean = env_is_clean()
    except ProviderError as e:
        raise ProviderError(f"precheck_{e.kind}", not_sent=True) from None
    if not clean:
        raise ProviderError("env_not_clean", not_sent=True)


class ClaudeCli:
    name = "claude_cli"

    def available(self) -> bool:
        return shutil.which("claude") is not None

    def argv(self, req: ProviderRequest) -> list[str]:
        argv = [
            "claude",
            "-p",
            "--model",
            req.model,
            "--output-format",
            "json",
            "--tools",
            "",
            "--no-session-persistence",
            "--disable-slash-commands",
            "--strict-mcp-config",
        ]
        if req.schema is not None:
            argv += ["--json-schema", json.dumps(req.schema)]
        return argv

    def call(self, req: ProviderRequest) -> ProviderResponse:
        _precheck()
        code, out, err = run_cli(self.argv(req), req.prompt, req.timeout_s)
        failed_diag = code != 0 and _LIMIT_TEXT.search(out[:2000] + err[:2000])
        try:
            data = json.loads(out)
        except json.JSONDecodeError:
            if failed_diag:
                raise RateLimited(None) from None
            raise MalformedOutput() from None
        if not isinstance(data, dict):
            raise MalformedOutput()
        # limit wording only counts in errors: a normal reply may talk about "rate limits"
        if data.get("is_error") or code != 0:
            if failed_diag or _LIMIT_TEXT.search(str(data.get("result", ""))[:2000]):
                raise RateLimited(None)
            raise ProviderError("cli_error")
        text = data.get("result")
        if code != 0 or not isinstance(text, str) or not text.strip():
            raise MalformedOutput()
        raw_usage = data.get("usage")
        usage: dict[str, Any] = raw_usage if isinstance(raw_usage, dict) else {}
        return ProviderResponse(
            text, _int_or_none(usage.get("input_tokens")), _int_or_none(usage.get("output_tokens"))
        )


class CodexCli:
    name = "codex_cli"

    def available(self) -> bool:
        return shutil.which("codex") is not None

    def call(self, req: ProviderRequest) -> ProviderResponse:
        _precheck()
        argv = [
            "codex",
            "exec",
            "--sandbox",
            "read-only",
            "--skip-git-repo-check",
            "--ephemeral",
            "--json",
            "-",
        ]
        code, out, err = run_cli(argv, req.prompt, req.timeout_s)
        if code != 0 and _LIMIT_TEXT.search(err[:2000] + out[:2000]):
            raise RateLimited(None)
        text, tin, tout = "", None, None
        for line in out.splitlines():
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(ev, dict):
                continue
            item = ev.get("item")
            if (
                isinstance(item, dict)
                and item.get("type") == "agent_message"
                and isinstance(item.get("text"), str)
            ):
                text = item["text"]
            usage = ev.get("usage")
            if ev.get("type") == "turn.completed" and isinstance(usage, dict):
                tin, tout = (
                    _int_or_none(usage.get("input_tokens")),
                    _int_or_none(usage.get("output_tokens")),
                )
        if code != 0 or not text.strip():
            raise MalformedOutput()
        return ProviderResponse(text, tin, tout)


def _reset_from_headers(h: httpx.Headers, now: datetime) -> datetime | None:
    ra = h.get("retry-after")
    if ra and ra.isdigit():
        return now + timedelta(seconds=int(ra))
    for key, value in h.items():
        if key.lower().endswith("-reset"):
            try:
                return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)
            except ValueError:
                continue
    return None


class _Http:
    name = ""
    env_key = ""
    url = ""

    def __init__(self, transport: httpx.BaseTransport | None = None) -> None:
        self.transport = transport

    def available(self) -> bool:
        return bool(os.environ.get(self.env_key))

    def build(self, req: ProviderRequest) -> tuple[str, dict[str, str], dict[str, Any]]:
        raise NotImplementedError

    def parse(self, data: dict[str, Any]) -> ProviderResponse:
        raise NotImplementedError

    def call(self, req: ProviderRequest) -> ProviderResponse:
        key = os.environ.get(self.env_key, "")
        if not key:
            raise ProviderError("key_missing")
        url, headers, body = self.build(req)
        headers = {**headers, **self.auth(key)}
        try:
            with httpx.Client(transport=self.transport, timeout=req.timeout_s) as c:
                r = c.post(url, headers=headers, json=body)
        except (httpx.ConnectError, httpx.ConnectTimeout):
            raise ProviderError("network", not_sent=True) from None
        except httpx.HTTPError:
            raise ProviderError("network") from None
        if r.status_code == 429:
            raise RateLimited(_reset_from_headers(r.headers, datetime.now(UTC)))
        if r.status_code >= 400:
            raise ProviderError(f"http_{r.status_code}")
        try:
            data = r.json()
            if not isinstance(data, dict):
                raise ValueError
            resp = self.parse(data)
        except (ValueError, KeyError, IndexError, TypeError):
            raise MalformedOutput() from None
        if not resp.text.strip():
            raise MalformedOutput()
        return resp

    def auth(self, key: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {key}"}


class AnthropicApi(_Http):
    name, env_key = "anthropic_api", "ANTHROPIC_API_KEY"

    def auth(self, key: str) -> dict[str, str]:
        return {"x-api-key": key, "anthropic-version": "2023-06-01"}

    def build(self, req: ProviderRequest) -> tuple[str, dict[str, str], dict[str, Any]]:
        body = {
            "model": req.model,
            "max_tokens": req.max_output_tokens,
            "messages": [{"role": "user", "content": req.prompt}],
        }
        return "https://api.anthropic.com/v1/messages", {}, body

    def parse(self, data: dict[str, Any]) -> ProviderResponse:
        text = "".join(b["text"] for b in data["content"] if b.get("type") == "text")
        u = data.get("usage") or {}
        return ProviderResponse(
            text, _int_or_none(u.get("input_tokens")), _int_or_none(u.get("output_tokens"))
        )


class GeminiApi(_Http):
    name, env_key = "gemini_api", "GEMINI_API_KEY"

    def auth(self, key: str) -> dict[str, str]:
        return {"x-goog-api-key": key}

    def build(self, req: ProviderRequest) -> tuple[str, dict[str, str], dict[str, Any]]:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{req.model}:generateContent"
        body = {
            "contents": [{"parts": [{"text": req.prompt}]}],
            "generationConfig": {"maxOutputTokens": req.max_output_tokens},
        }
        return url, {}, body

    def parse(self, data: dict[str, Any]) -> ProviderResponse:
        text = "".join(p["text"] for p in data["candidates"][0]["content"]["parts"] if "text" in p)
        u = data.get("usageMetadata") or {}
        return ProviderResponse(
            text,
            _int_or_none(u.get("promptTokenCount")),
            _int_or_none(u.get("candidatesTokenCount")),
        )


class OpenRouterFree(_Http):
    name, env_key = "openrouter_free", "OPENROUTER_API_KEY"

    def build(self, req: ProviderRequest) -> tuple[str, dict[str, str], dict[str, Any]]:
        body = {
            "model": req.model,
            "max_tokens": req.max_output_tokens,
            "messages": [{"role": "user", "content": req.prompt}],
        }
        return "https://openrouter.ai/api/v1/chat/completions", {}, body

    def parse(self, data: dict[str, Any]) -> ProviderResponse:
        text = data["choices"][0]["message"]["content"]
        if not isinstance(text, str):
            raise TypeError
        u = data.get("usage") or {}
        return ProviderResponse(
            text, _int_or_none(u.get("prompt_tokens")), _int_or_none(u.get("completion_tokens"))
        )


class OpenAiApi:
    """Present but disabled by policy (D-027)."""

    name = "openai_api"

    def available(self) -> bool:
        return False

    def call(self, req: ProviderRequest) -> ProviderResponse:
        raise ProviderDisabled("openai_api is disabled by policy")


def live_providers() -> dict[str, Provider]:
    return {
        "claude_cli": ClaudeCli(),
        "codex_cli": CodexCli(),
        "anthropic_api": AnthropicApi(),
        "gemini_api": GeminiApi(),
        "openrouter_free": OpenRouterFree(),
        "openai_api": OpenAiApi(),
    }

"""Secret redaction for outbound prompts, returned text, stored rows and log records."""

import base64
import logging
import os
import re
import traceback
from urllib.parse import quote

# Same pattern as scripts/check-env-clean.sh (a test parses the script so they cannot drift).
SECRET_NAME_RE = re.compile(
    r"^(ANTHROPIC_API_KEY|ANTHROPIC_AUTH_TOKEN|CLAUDE_CODE_OAUTH_TOKEN|OPENAI_API_KEY|"
    r"CODEX_API_KEY|GEMINI_API_KEY|GOOGLE_API_KEY|OPENROUTER_API_KEY|NOTION_TOKEN|"
    r"NOTION_INBOX_DB_ID|NTFY_URL|NTFY_TOPIC|NTFY_TOKEN|"
    r"[A-Z0-9_]*(_API_KEY|_TOKEN|_SECRET|_PASSWORD))$"
)
# Wider net for value-based redaction (also catches DSNs and password hashes).
_BROAD_NAME_RE = re.compile(r"(KEY|TOKEN|SECRET|PASSWORD|DATABASE_URL|HASH|DSN)", re.IGNORECASE)

_SHAPES: list[tuple[str, re.Pattern[str]]] = [
    ("anthropic_key", re.compile(r"sk-ant-[A-Za-z0-9_\-]{8,}")),
    ("openrouter_key", re.compile(r"sk-or-[A-Za-z0-9_\-]{8,}")),
    ("openai_key", re.compile(r"sk-(?:proj-)?[A-Za-z0-9_\-]{16,}")),
    ("google_key", re.compile(r"AIza[0-9A-Za-z_\-]{20,}")),
    (
        "github_token",
        re.compile(r"(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}"),
    ),
    ("slack_token", re.compile(r"xox[abprs]-[A-Za-z0-9\-]{10,}")),
    ("bearer", re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._\-~+/]{12,}=*")),
    (
        "private_key",
        re.compile(
            r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?(?:-----END [A-Z ]*PRIVATE KEY-----|$)", re.S
        ),
    ),
    ("url_credentials", re.compile(r"(?<=://)[^/\s:@]+:[^/\s@]+(?=@)")),
    (
        "assignment",
        re.compile(
            r"""(?ix)\b([A-Z0-9_]*(?:API_KEY|TOKEN|SECRET|PASSWORD)[A-Z0-9_]*)\s*[:=]\s*
                ["']?([^\s"',;]{6,})["']?"""
        ),
    ),
]
_MIN_VALUE_LEN = 8


def _known_secret_values() -> set[str]:
    values: set[str] = set()
    for name, value in os.environ.items():
        if len(value) >= _MIN_VALUE_LEN and (
            SECRET_NAME_RE.match(name) or _BROAD_NAME_RE.search(name)
        ):
            values.add(value)
            values.add(quote(value, safe=""))
            values.add(base64.b64encode(value.encode()).decode())
            values.add(base64.urlsafe_b64encode(value.encode()).decode())
            # passwords embedded in a DSN-style value
            m = re.search(r"://[^:/@\s]+:([^@\s]+)@", value)
            if m:
                values.add(m.group(1))
    return {v for v in values if len(v) >= _MIN_VALUE_LEN}


def redact(text: str) -> tuple[str, int]:
    """Return (redacted_text, number_of_replacements)."""
    count = 0
    for secret in sorted(_known_secret_values(), key=len, reverse=True):
        if secret in text:
            count += text.count(secret)
            text = text.replace(secret, "[REDACTED:env]")
    for kind, pattern in _SHAPES:
        if kind == "assignment":
            text, n = pattern.subn(lambda m: f"{m.group(1)}=[REDACTED:assignment]", text)
        else:
            text, n = pattern.subn(f"[REDACTED:{kind}]", text)
        count += n
    return text, count


def redact_text(text: str) -> str:
    return redact(text)[0]


def redact_json(value: object) -> object:
    """Recursively redact every string inside a JSON-like structure (for persisted payloads)."""
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, dict):
        return {redact_text(str(k)): redact_json(v) for k, v in value.items()}
    if isinstance(value, list):
        return [redact_json(v) for v in value]
    return value


class RedactingFilter(logging.Filter):
    """Attach to HANDLERS (not parent loggers: those miss propagated child records)."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact_text(record.getMessage())
        record.args = ()
        if record.exc_info:
            record.exc_text = redact_text("".join(traceback.format_exception(*record.exc_info)))
            record.exc_info = None
        elif record.exc_text:
            record.exc_text = redact_text(record.exc_text)
        return True


_installed = False


def install_log_redaction() -> None:
    """Redact every record at every emitting handler, including third-party ones (httpx...)."""
    global _installed
    flt = RedactingFilter()
    for handler in logging.getLogger().handlers:
        if not any(isinstance(f, RedactingFilter) for f in handler.filters):
            handler.addFilter(flt)
    if _installed:
        return
    _installed = True
    original = logging.Handler.__init__

    def patched(self: logging.Handler, *args: object, **kwargs: object) -> None:
        original(self, *args, **kwargs)  # type: ignore[arg-type]
        self.addFilter(RedactingFilter())

    logging.Handler.__init__ = patched  # type: ignore[method-assign]

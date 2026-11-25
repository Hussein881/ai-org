"""Prompt assembly: fixed, cache-friendly order; untrusted parts delimited and sanitized."""

import logging
import re
from collections.abc import Sequence

from app.gateway.types import GatewayError, PartKind, PromptPart, PromptTooLarge

log = logging.getLogger("aiorg.gateway")
ORDER: tuple[PartKind, ...] = ("constitution", "role_card", "policy", "task", "memory", "failure")

# Mitigation only. Trust is enforced at the action boundary: model output never authorises
# tools, disclosures or state changes (the gateway returns text, it does not act on it).
_INSTRUCTION_LIKE = re.compile(
    r"(?i)(ignore (all |any )?(previous|prior|above) instructions|disregard (the )?(system|above)|"
    r"you are now|new instructions:|system prompt|</?untrusted_data>|<\|im_(start|end)\|>)"
)


def sanitize_untrusted(text: str) -> str:
    return _INSTRUCTION_LIKE.sub("[removed-instruction-like-text]", text)


def estimate_tokens(text: str) -> int:
    return len(text) // 3 + 1  # deliberately conservative (over-estimates)


def assemble(parts: Sequence[PromptPart], cap_tokens: int) -> str:
    rank = {k: i for i, k in enumerate(ORDER)}
    for p in parts:
        if p.kind not in rank:
            raise GatewayError(f"unknown prompt part kind: {p.kind!r}")
    ordered = sorted(parts, key=lambda p: rank[p.kind])  # stable inside a kind
    blocks: list[str] = []
    for p in ordered:
        body = sanitize_untrusted(p.text) if p.untrusted else p.text
        if p.untrusted:
            body = f"<untrusted_data>\n{body}\n</untrusted_data>"
        blocks.append(f"## {p.kind}\n{body}")
    prompt = "\n\n".join(blocks)
    if estimate_tokens(prompt) > cap_tokens:
        log.warning(
            "prompt over cap (%d > %d tokens); refusing, not truncating",
            estimate_tokens(prompt),
            cap_tokens,
        )
        raise PromptTooLarge(f"prompt exceeds {cap_tokens} tokens")
    return prompt

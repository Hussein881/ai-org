"""python -m app.gateway.cli smoke [--provider P | --all] [--allow-during-build]

Makes one tiny public-class call per provider through the real Gateway and prints
provider/outcome/tokens/latency from the ledger. Never prints prompts, responses or env."""

import argparse
import sys

from sqlalchemy.orm import Session

from app.db.models import ModelUsage
from app.db.session import engine
from app.gateway.factory import build_gateway
from app.gateway.redact import install_log_redaction
from app.gateway.types import GatewayError, PromptPart

API_PROVIDERS = ("anthropic_api", "gemini_api", "openrouter_free")
CLI_PROVIDERS = ("claude_cli", "codex_cli")


def smoke(providers: list[str], allow_during_build: bool) -> int:
    gw = build_gateway()
    failures = 0
    for name in providers:
        pp = gw.policy.providers[name]
        if not pp.enabled:
            print(f"{name:16} disabled")
            continue
        cheapest = next(iter(pp.models))
        gw.policy.routes["smoke"] = [f"{name}:{cheapest}"]
        try:
            res = gw.complete(
                "smoke",
                None,
                [PromptPart("task", "Reply with exactly one word: pong")],
                None,
                "public",
                purpose="smoke",
                allow_during_build=allow_during_build,
                max_output_tokens=16,
            )
            with Session(engine()) as db:
                row = db.get(ModelUsage, res.usage_id)
                if row is None:
                    raise GatewayError("ledger row missing")
                print(
                    f"{name:16} ok tokens_in={row.input_tokens} tokens_out={row.output_tokens} "
                    f"latency_ms={row.latency_ms} model={row.model}"
                )
        except GatewayError as e:
            failures += 1
            print(f"{name:16} FAIL {type(e).__name__}")
    return failures


def main() -> None:
    install_log_redaction()
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sp = sub.add_parser("smoke")
    sp.add_argument("--provider", choices=[*CLI_PROVIDERS, *API_PROVIDERS])
    sp.add_argument("--all", action="store_true", help="all providers")
    sp.add_argument("--api-only", action="store_true", help="only the three API providers")
    sp.add_argument("--allow-during-build", action="store_true")
    a = ap.parse_args()
    if a.provider:
        names = [a.provider]
    elif a.api_only:
        names = list(API_PROVIDERS)
    else:
        names = [*CLI_PROVIDERS, *API_PROVIDERS]
    sys.exit(1 if smoke(names, a.allow_during_build) else 0)


if __name__ == "__main__":
    main()

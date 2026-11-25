"""The gateway: route -> data_class -> quota envelope -> fallback chain -> queue until reset."""

import logging
import subprocess
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from app.gateway import ledger
from app.gateway.assemble import assemble
from app.gateway.providers.base import Provider
from app.gateway.redact import redact_text
from app.gateway.types import (
    AllRoutesFailed,
    Clock,
    DataClass,
    DataClassRefused,
    GatewayError,
    PromptPart,
    ProviderError,
    ProviderRequest,
    ProviderResponse,
    Queued,
    RateLimited,
    Result,
    check_class,
    max_class,
    utcnow,
)
from app.policy.model_policy import PUBLIC_ONLY, ModelPolicy

log = logging.getLogger("aiorg.gateway")
# Hard floor, independent of the YAML: what each provider class may ever receive.
FLOOR_PUBLIC_ONLY = PUBLIC_ONLY


@dataclass(frozen=True)
class TaskRef:
    task_id: str | None = None
    run_id: str | None = None


def systemctl_build_active() -> bool:
    """True if the build runner is active. Unknown state counts as ACTIVE (paused)."""
    try:
        out = subprocess.run(  # noqa: S603
            ["systemctl", "is-active", "build-runner"],  # noqa: S607
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return True
    return out.stdout.strip() in ("active", "activating", "reloading")


class Gateway:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        policy: ModelPolicy,
        providers: dict[str, Provider],
        clock: Clock = utcnow,
        is_build_active: Callable[[], bool] = systemctl_build_active,
    ) -> None:
        self.sf, self.policy, self.providers = session_factory, policy, providers
        self.clock, self.is_build_active = clock, is_build_active

    # ---- helpers -------------------------------------------------------------
    def _claude_pct(self, db: Session, now: datetime) -> float:
        pp = self.policy.providers.get("claude_cli")
        if pp is None or not pp.limits:
            return 0.0
        pcts = []
        for lim in pp.limits:
            w = ledger.window_usage(db, "claude_cli", lim, now, self.policy)
            pcts.append(100.0 * w.used / w.limit if w.limit else 0.0)
        return max(pcts)

    def _candidates(
        self, role: str, purpose: str, db: Session, now: datetime
    ) -> list[tuple[str, str]]:
        cands = self.policy.route_for(role, purpose)
        key = f"{role}.{purpose}"
        if (role in self.policy.prefer_api_roles or key in self.policy.prefer_api_roles) and (
            self._claude_pct(db, now) > self.policy.prefer_api_above_pct
        ):
            cands = sorted(cands, key=lambda c: 0 if c[0] == "anthropic_api" else 1)  # stable
        return cands

    @staticmethod
    def _allowed(provider: str, pp_classes: Sequence[str], data_class: DataClass) -> bool:
        if data_class == "secret":
            return False
        if provider in FLOOR_PUBLIC_ONLY and data_class != "public":
            return False
        return data_class in pp_classes

    # ---- main entry ----------------------------------------------------------
    def complete(
        self,
        role: str,
        task_ref: TaskRef | None,
        prompt_parts: Sequence[PromptPart],
        schema: dict[str, Any] | None,
        data_class: str,
        budget_hint: int | None = None,
        *,
        purpose: str = "default",
        allow_during_build: bool = False,
        max_output_tokens: int = 1024,
        timeout_s: float = 120.0,
    ) -> Result:
        declared = check_class(data_class)
        if declared == "secret":
            raise DataClassRefused("secret data is never sent to any model")
        # secret parts are stripped BEFORE assembly; they never reach any prompt
        parts = [
            PromptPart(p.kind, "[REDACTED:secret]", "secret", False)
            if p.data_class == "secret"
            else p
            for p in prompt_parts
        ]
        effective: DataClass = declared
        for p in prompt_parts:
            if p.data_class != "secret":
                effective = max_class(effective, p.data_class)
        prompt = redact_text(assemble(parts, budget_hint or self.policy.cap_for(role)))
        ref = task_ref or TaskRef()
        refused = skipped = 0
        resets: list[datetime] = []
        with self.sf() as db:
            now = self.clock()
            candidates = self._candidates(role, purpose, db, now)
        for provider, model in candidates:
            pp = self.policy.providers[provider]
            prov = self.providers.get(provider)
            if not pp.enabled or prov is None or not prov.available():
                continue
            if not self._allowed(provider, pp.allowed_data_classes, effective):
                refused += 1
                continue
            if provider == "claude_cli" and not allow_during_build and self.is_build_active():
                skipped += 1
                continue
            outcome = self._attempt(
                prov,
                provider,
                model,
                role,
                purpose,
                ref,
                prompt,
                schema,
                max_output_tokens,
                timeout_s,
            )
            if isinstance(outcome, Result):
                return outcome
            kind, reset = outcome
            if kind == "blocked":
                skipped += 1
                if reset:
                    resets.append(reset)
        if refused and not skipped and not resets:
            raise DataClassRefused(f"no route for role {role!r} may receive {effective} data")
        if resets:
            raise Queued(min(resets))
        raise AllRoutesFailed(f"all routes failed for role {role!r}")

    def _attempt(
        self,
        prov: Provider,
        provider: str,
        model: str,
        role: str,
        purpose: str,
        ref: TaskRef,
        prompt: str,
        schema: dict[str, Any] | None,
        max_out: int,
        timeout_s: float,
    ) -> Result | tuple[str, datetime | None]:
        pp = self.policy.providers[provider]
        info = pp.models[model]
        with self.sf() as db:
            now = self.clock()
            got = ledger.reserve(
                db,
                self.policy,
                provider,
                model,
                role,
                purpose,
                ref.task_id,
                ref.run_id,
                now,
                prompt,
                max_out,
            )
            if isinstance(got, ledger.Blocked):
                return "blocked", got.resets_at
            usage_id = got
        started = time.monotonic()

        def done(**kw: Any) -> None:
            with self.sf() as db:
                ledger.finalize(
                    db,
                    usage_id,
                    now=self.clock(),
                    latency_ms=int((time.monotonic() - started) * 1000),
                    **kw,
                )

        try:
            resp: ProviderResponse = prov.call(
                ProviderRequest(
                    model=info.id,
                    prompt=prompt,
                    schema=schema,
                    timeout_s=timeout_s,
                    max_output_tokens=max_out,
                )
            )
        except RateLimited as e:
            with self.sf() as db:
                until = ledger.mark_rate_limited(db, provider, e.reset_at, self.clock())
            done(outcome="rate_limited", error_kind="rate_limited")
            return "blocked", until
        except ProviderError as e:
            done(
                outcome="malformed" if e.kind == "malformed_output" else "error", error_kind=e.kind
            )
            return "failed", None
        except GatewayError:
            done(outcome="error", error_kind="gateway_error")
            return "failed", None
        except Exception:  # never let a provider bug leak raw details
            log.exception("provider crashed")
            done(outcome="error", error_kind="provider_crash")
            return "failed", None
        cost: Decimal | None = None
        if pp.pricing_basis != "api":
            cost = Decimal(0)
        elif (
            resp.input_tokens is not None
            and resp.output_tokens is not None
            and info.price_in is not None
            and info.price_out is not None
        ):
            cost = (
                Decimal(str(info.price_in)) * resp.input_tokens
                + Decimal(str(info.price_out)) * resp.output_tokens
            ) / Decimal(1_000_000)
        done(
            outcome="ok",
            input_tokens=resp.input_tokens,
            output_tokens=resp.output_tokens,
            cost_usd=cost,
        )
        return Result(
            redact_text(resp.text),
            provider,
            info.id,
            usage_id,
            resp.input_tokens,
            resp.output_tokens,
        )

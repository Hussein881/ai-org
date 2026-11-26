"""Usage ledger and quota windows. Reservations are made atomically under a provider row lock."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, cast
from zoneinfo import ZoneInfo

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.tasks import emit
from app.db.models import Event, ModelUsage, ProviderQuota
from app.gateway.redact import redact_json
from app.policy.model_policy import Limit, ModelPolicy, ProviderPolicy

STALE_AFTER = timedelta(minutes=15)
REQUEST_OVERHEAD_TOKENS = 256


@dataclass(frozen=True)
class WindowUsage:
    used: float
    limit: float
    resets_at: datetime | None
    unit: str  # "calls" | "usd"


def _window_start(limit: Limit, now: datetime, tz: str) -> datetime:
    local = now.astimezone(ZoneInfo(tz))
    if limit.window == "5h":
        return now - timedelta(hours=5)
    if limit.window == "day":
        return local.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(UTC)
    return local.replace(day=1, hour=0, minute=0, second=0, microsecond=0).astimezone(UTC)


def _next_reset(
    limit: Limit, start: datetime, now: datetime, tz: str, oldest: datetime | None
) -> datetime:
    if limit.window == "5h":
        return (oldest or now) + timedelta(hours=5)
    local = start.astimezone(ZoneInfo(tz))
    if limit.window == "day":
        return (local + timedelta(days=1)).astimezone(UTC)
    year, month = (local.year + 1, 1) if local.month == 12 else (local.year, local.month + 1)
    return local.replace(year=year, month=month).astimezone(UTC)


def window_usage(
    db: Session,
    provider: str,
    limit: Limit,
    now: datetime,
    policy: ModelPolicy,
    model: str | None = None,
) -> WindowUsage:
    """Shared by the router and /api/usage. Membership is by reserved_at (in-flight calls count)."""
    start = _window_start(limit, now, policy.day_tz)
    member = ModelUsage.reserved_at >= start
    if limit.max_usd is not None:  # unsettled spend carries over a window rollover
        member = or_(member, ModelUsage.outcome == "reserved", ModelUsage.finished_at >= start)
    q = [ModelUsage.provider == provider, member]
    if limit.model:
        q.append(ModelUsage.model == limit.model)
    oldest = db.scalar(select(func.min(ModelUsage.reserved_at)).where(*q))
    resets = (
        None
        if (limit.window == "5h" and oldest is None)
        else _next_reset(limit, start, now, policy.day_tz, oldest)
    )
    if limit.max_usd is not None:
        # unknown or abandoned calls keep their reservation (or the nominal unknown cost)
        cost = func.coalesce(
            ModelUsage.cost_usd, ModelUsage.reserved_cost_usd, Decimal(str(policy.unknown_call_usd))
        )
        used = float(db.scalar(select(func.coalesce(func.sum(cost), 0)).where(*q)) or 0)
        return WindowUsage(used, limit.max_usd, resets, "usd")
    used = float(db.scalar(select(func.count()).select_from(ModelUsage).where(*q)) or 0)
    return WindowUsage(
        used,
        float(limit.max_calls or 0),
        resets,
        "calls",
    )


def upper_bound_cost(
    pp: ProviderPolicy, model: str, prompt: str, max_output_tokens: int
) -> Decimal | None:
    info = pp.models[model]
    if pp.pricing_basis != "api" or info.price_in is None or info.price_out is None:
        return None
    in_tokens = (
        len(prompt.encode()) + REQUEST_OVERHEAD_TOKENS
    )  # bytes >= tokens for any tokenizer: a safe upper bound
    return (
        Decimal(str(info.price_in)) * in_tokens + Decimal(str(info.price_out)) * max_output_tokens
    ) / Decimal(1_000_000)


@dataclass(frozen=True)
class Blocked:
    reason: str
    resets_at: datetime | None


def reserve(
    db: Session,
    policy: ModelPolicy,
    provider: str,
    model: str,
    role: str,
    purpose: str,
    task_id: str | None,
    run_id: str | None,
    now: datetime,
    prompt: str,
    max_output_tokens: int,
) -> str | Blocked:
    """Check block + limits and insert a `reserved` row in one transaction under a row lock."""
    pp = policy.providers[provider]
    reconcile_stale(db, now)
    quota = db.scalar(
        select(ProviderQuota).where(ProviderQuota.provider == provider).with_for_update()
    )
    if quota is None:
        quota = ProviderQuota(provider=provider)
        db.add(quota)
        db.flush()
    if quota.blocked_until and quota.blocked_until > now:
        db.rollback()
        return Blocked("rate_limited", quota.blocked_until)
    bound = upper_bound_cost(pp, model, prompt, max_output_tokens)
    for lim in pp.limits:
        if lim.model and lim.model != model:
            continue
        w = window_usage(db, provider, lim, now, policy)
        extra = (
            float(bound)
            if (lim.max_usd is not None and bound is not None)
            else (policy.unknown_call_usd if lim.max_usd is not None else 1.0)
        )
        if w.used + extra > w.limit:
            if lim.hard:
                db.rollback()
                return Blocked("envelope_exhausted", w.resets_at)
            _soft_limit_event(db, provider, lim, now, policy)
    row = ModelUsage(
        provider=provider,
        model=model,
        role=role,
        purpose=purpose,
        task_id=task_id,
        run_id=run_id,
        outcome="reserved",
        pricing_basis=pp.pricing_basis,
        reserved_at=now,
        reserved_cost_usd=bound,
    )
    db.add(row)
    db.flush()
    usage_id = row.id
    db.commit()
    return usage_id


def _soft_limit_event(
    db: Session, provider: str, lim: Limit, now: datetime, policy: ModelPolicy
) -> None:
    start = _window_start(Limit(window="day", max_calls=1), now, policy.day_tz)
    exists = db.scalar(
        select(Event.id)
        .where(
            Event.kind == "gateway.soft_limit", Event.created_at >= start, Event.actor == provider
        )
        .limit(1)
    )
    if exists is None:
        emit(
            db, "gateway.soft_limit", provider, payload={"window": lim.window, "limit": lim.max_usd}
        )


def finalize(
    db: Session,
    usage_id: str,
    *,
    outcome: str,
    now: datetime,
    latency_ms: int | None,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    cost_usd: Decimal | None = None,
    error_kind: str | None = None,
    event_payload: dict[str, object] | None = None,
) -> None:
    row = db.get(ModelUsage, usage_id, with_for_update=True)
    if row is None:
        return
    row.outcome, row.finished_at, row.latency_ms = outcome, now, latency_ms
    row.input_tokens, row.output_tokens, row.cost_usd = input_tokens, output_tokens, cost_usd
    row.error_kind = error_kind
    payload = {
        "provider": row.provider,
        "model": row.model,
        "role": row.role,
        "purpose": row.purpose,
        "outcome": outcome,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        **(event_payload or {}),
    }
    emit(
        db,
        "usage.recorded",
        row.provider,
        task_id=row.task_id,
        run_id=row.run_id,
        payload=cast(dict[str, Any], redact_json(payload)),
    )
    db.commit()


def mark_rate_limited(
    db: Session, provider: str, reset_at: datetime | None, now: datetime, default_s: int = 900
) -> datetime:
    """Blocks only ever extend (never shorten) under the provider row lock."""
    until = reset_at or (now + timedelta(seconds=default_s))
    quota = db.scalar(
        select(ProviderQuota).where(ProviderQuota.provider == provider).with_for_update()
    )
    if quota is None:
        quota = ProviderQuota(provider=provider)
        db.add(quota)
    if quota.blocked_until is None or until > quota.blocked_until:
        quota.blocked_until = until
    quota.last_rate_limit_at, quota.updated_at = now, now
    until = quota.blocked_until
    db.commit()
    return until


def reconcile_stale(db: Session, now: datetime) -> int:
    """Reserved rows whose caller vanished become `abandoned` (they keep counting toward quota)."""
    rows = db.scalars(
        select(ModelUsage)
        .where(ModelUsage.outcome == "reserved", ModelUsage.reserved_at < now - STALE_AFTER)
        .with_for_update(skip_locked=True)  # a row being finalized keeps its real outcome
    ).all()
    for r in rows:
        # the charge stays in the window where the call was made, not where it was swept
        r.outcome, r.finished_at, r.error_kind = (
            "abandoned",
            r.reserved_at + STALE_AFTER,
            "stale_reservation",
        )
    db.commit()
    return len(rows)

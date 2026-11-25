from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.auth import current_session
from app.config import get_settings
from app.db.models import ProviderQuota
from app.db.session import get_db
from app.gateway import ledger
from app.gateway.types import utcnow
from app.policy.model_policy import cached_policy

router = APIRouter(prefix="/api", tags=["usage"], dependencies=[Depends(current_session)])

LABELS = {
    "claude_cli": "Claude subscription",
    "anthropic_api": "Claude API",
    "codex_cli": "Codex",
    "gemini_api": "Gemini",
    "openrouter_free": "OpenRouter",
    "openai_api": "OpenAI",
}


class LimitGauge(BaseModel):
    window: str
    model: str | None
    unit: str
    used: float
    limit: float
    hard: bool
    resets_at: datetime | None


class ProviderGauge(BaseModel):
    provider: str
    label: str
    enabled: bool
    pricing_basis: str
    status: str  # ok | warn | exhausted | blocked | disabled
    blocked_until: datetime | None
    limits: list[LimitGauge]


class UsageOut(BaseModel):
    providers: list[ProviderGauge]


@router.get("/usage", response_model=UsageOut)
def usage(db: Session = Depends(get_db)) -> UsageOut:
    policy = cached_policy(get_settings().model_policy_path)
    now = utcnow()
    out: list[ProviderGauge] = []
    for name, pp in policy.providers.items():
        if name == "fake":
            continue
        quota = db.scalar(select(ProviderQuota).where(ProviderQuota.provider == name))
        blocked = (
            quota.blocked_until
            if quota and quota.blocked_until and quota.blocked_until > now
            else None
        )
        gauges: list[LimitGauge] = []
        worst = 0.0
        exhausted = False
        for lim in pp.limits:
            w = ledger.window_usage(db, name, lim, now, policy)
            gauges.append(
                LimitGauge(
                    window=lim.window,
                    model=lim.model,
                    unit=w.unit,
                    used=w.used,
                    limit=w.limit,
                    hard=lim.hard,
                    resets_at=w.resets_at,
                )
            )
            pct = 100 * w.used / w.limit if w.limit else 0
            worst = max(worst, pct)
            exhausted = exhausted or (lim.hard and w.used >= w.limit)
        if not pp.enabled:
            status = "disabled"
        elif blocked:
            status = "blocked"
        elif exhausted:
            status = "exhausted"
        elif worst >= policy.prefer_api_above_pct:
            status = "warn"
        else:
            status = "ok"
        out.append(
            ProviderGauge(
                provider=name,
                label=LABELS.get(name, name),
                enabled=pp.enabled,
                pricing_basis=pp.pricing_basis,
                status=status,
                blocked_until=blocked,
                limits=gauges,
            )
        )
    return UsageOut(providers=out)

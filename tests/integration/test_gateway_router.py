import copy
import logging
import threading
import time
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
import yaml
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from app.db.session import engine
from app.gateway import ledger
from app.gateway.providers.fake import FakeProvider
from app.gateway.router import Gateway, TaskRef
from app.gateway.types import (
    AllRoutesFailed,
    DataClassRefused,
    PromptPart,
    ProviderError,
    ProviderResponse,
    Queued,
    RateLimited,
)
from app.policy.model_policy import ModelPolicy

ROOT = Path(__file__).resolve().parents[2]
T0 = datetime(2026, 11, 24, 10, 0, tzinfo=UTC)


class Clock:
    def __init__(self) -> None:
        self.now = T0

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **kw: float) -> None:
        self.now += timedelta(**kw)


def make_policy(mutate=None) -> ModelPolicy:
    d = yaml.safe_load((ROOT / "config/model_policy.yaml").read_text())
    d = copy.deepcopy(d)
    # router tests need a two-step chain; the shipped ceo.ack route is single-step
    d["routes"]["ceo.ack"] = ["claude_cli:haiku", "anthropic_api:claude-haiku-5-5"]
    if mutate:
        mutate(d)
    return ModelPolicy.model_validate(d)


@pytest.fixture
def env(db_url):
    clock = Clock()
    provs = {
        n: FakeProvider(n)
        for n in (
            "fake",
            "claude_cli",
            "codex_cli",
            "anthropic_api",
            "gemini_api",
            "openrouter_free",
        )
    }

    def build(mutate=None, build_active=False) -> Gateway:
        return Gateway(
            sessionmaker(engine()), make_policy(mutate), provs, clock, lambda: build_active
        )

    return build, provs, clock


def part(text_: str, cls="public"):
    return [PromptPart("task", text_, cls)]


def rows(sql: str):
    with Session(engine()) as s:
        return s.execute(text(sql)).all()


# ---------------- data_class enforcement ----------------
def free_only(d):
    d["routes"]["scout-only"] = ["gemini_api:flash", "openrouter_free:free"]


def test_founder_private_to_free_tier_refused_and_never_called(env):
    build, provs, _ = env
    gw = build(free_only)
    with pytest.raises(DataClassRefused):
        gw.complete(
            "scout-only", None, part("my resume", "founder_private"), None, "founder_private"
        )
    assert provs["gemini_api"].calls == [] and provs["openrouter_free"].calls == []


def test_mixed_parts_escalate_the_effective_class(env):
    build, provs, _ = env
    gw = build(free_only)
    parts = [
        PromptPart("task", "public news"),
        PromptPart("memory", "founder pref", "founder_private"),
    ]
    with pytest.raises(DataClassRefused):
        gw.complete(
            "scout-only", None, parts, None, "public"
        )  # declared public, parts say otherwise
    assert provs["gemini_api"].calls == []


def test_public_data_may_use_free_tiers_and_private_skips_them(env):
    build, provs, _ = env
    gw = build(
        lambda d: d["routes"].__setitem__(
            "mix", ["gemini_api:flash", "anthropic_api:claude-haiku-5-5"]
        )
    )
    assert gw.complete("mix", None, part("news"), None, "public").provider == "gemini_api"
    r = gw.complete("mix", None, part("private", "founder_private"), None, "founder_private")
    assert r.provider == "anthropic_api"
    assert len(provs["gemini_api"].calls) == 1


def test_secret_declared_refused_and_secret_parts_never_in_prompt(env):
    build, provs, _ = env
    gw = build()
    with pytest.raises(DataClassRefused):
        gw.complete("ceo", None, part("x"), None, "secret")
    parts = [PromptPart("task", "do it"), PromptPart("memory", "TOPSECRET-VALUE-123", "secret")]
    gw.complete("ceo.ack", None, parts, None, "public", purpose="ack")
    sent = provs["claude_cli"].calls[-1].prompt
    assert "TOPSECRET-VALUE-123" not in sent and "[REDACTED:secret]" in sent


def test_unknown_data_class_rejected(env):
    build, _, _ = env
    with pytest.raises(ValueError):
        build().complete("ceo", None, part("x"), None, "top_secret")


def test_policy_floor_holds_even_if_loader_were_bypassed(env):
    build, provs, _ = env
    gw = build(free_only)
    gw.policy.providers["gemini_api"].allowed_data_classes.append(
        "founder_private"
    )  # tamper after load
    with pytest.raises(DataClassRefused):
        gw.complete("scout-only", None, part("p", "founder_private"), None, "founder_private")
    assert provs["gemini_api"].calls == []


# ---------------- envelopes, fallback, queue ----------------
def tiny_claude(d):
    d["providers"]["claude_cli"]["limits"] = [{"window": "day", "max_calls": 1}]
    d["providers"]["anthropic_api"]["limits"] = [{"window": "day", "max_usd": 0.001, "hard": True}]


def test_exhausted_envelope_falls_back_then_queues_then_recovers(env):
    build, provs, clock = env
    gw = build(tiny_claude)
    ack = dict(purpose="ack")
    assert gw.complete("ceo", None, part("a"), None, "public", **ack).provider == "claude_cli"
    # second call: claude exhausted -> falls back to anthropic (within the tiny cap)
    assert gw.complete("ceo", None, part("b"), None, "public", **ack).provider == "anthropic_api"
    # third: everything exhausted -> queued until the next reset, never silently dropped
    with pytest.raises(Queued) as q:
        gw.complete("ceo", None, part("c"), None, "public", **ack)
    assert q.value.resets_at > clock.now
    clock.now = q.value.resets_at + timedelta(seconds=1)
    assert gw.complete("ceo", None, part("d"), None, "public", **ack).provider == "claude_cli"


def test_rate_limit_blocks_until_reset_and_blocks_only_extend(env):
    build, provs, clock = env
    gw = build(lambda d: d["routes"].__setitem__("solo", ["claude_cli:haiku"]))
    provs["claude_cli"].script = [RateLimited(clock.now + timedelta(hours=2))]
    with pytest.raises(Queued):
        gw.complete("solo", None, part("a"), None, "public")
    assert len(provs["claude_cli"].calls) == 1
    with pytest.raises(Queued):  # still blocked: provider not even called
        gw.complete("solo", None, part("b"), None, "public")
    assert len(provs["claude_cli"].calls) == 1
    with Session(engine()) as s:
        ledger.mark_rate_limited(
            s, "claude_cli", clock.now + timedelta(minutes=5), clock.now
        )  # shorter
        blocked = s.execute(
            text("select blocked_until from provider_quota where provider='claude_cli'")
        ).scalar()
    assert blocked == clock.now + timedelta(hours=2)  # never shortened
    clock.advance(hours=2, seconds=1)
    assert gw.complete("solo", None, part("c"), None, "public").provider == "claude_cli"


def test_five_hour_window_is_rolling(env):
    build, _, clock = env

    def mutate(d):
        d["providers"]["claude_cli"]["limits"] = [{"window": "5h", "max_calls": 2}]
        d["routes"]["solo"] = ["claude_cli:haiku"]

    gw = build(mutate)
    gw.complete("solo", None, part("1"), None, "public")
    clock.advance(hours=1)
    gw.complete("solo", None, part("2"), None, "public")
    with pytest.raises(Queued) as q:
        gw.complete("solo", None, part("3"), None, "public")
    assert q.value.resets_at == T0 + timedelta(hours=5)  # oldest call + 5h
    clock.now = T0 + timedelta(hours=5, seconds=1)
    gw.complete("solo", None, part("4"), None, "public")


def test_opus_sub_cap_falls_to_sonnet_then_paid_opus(env):
    build, provs, _ = env

    def mutate(d):
        d["providers"]["claude_cli"]["limits"] = [
            {"window": "day", "max_calls": 50, "model": "opus"}
        ]
        d["providers"]["claude_cli"]["limits"][0]["max_calls"] = 1

    gw = build(mutate)
    assert gw.complete("board-advisor", None, part("a"), None, "public").model == "opus"
    assert gw.complete("board-advisor", None, part("b"), None, "public").model == "sonnet"


def test_hard_usd_cap_blocks_but_soft_cap_only_emits_event(env):
    build, provs, _ = env

    def mutate(d):
        d["routes"]["api"] = ["anthropic_api:claude-haiku-5-5"]
        d["providers"]["anthropic_api"]["limits"] = [
            {"window": "month", "max_usd": 0.0002, "hard": True},
            {"window": "day", "max_usd": 0.00001, "hard": False},
        ]

    gw = build(mutate)
    with pytest.raises(
        Queued
    ):  # upper bound (1024 out tokens @ $0.5/M = $0.000512) exceeds hard cap
        gw.complete("api", None, part("x"), None, "public")
    assert provs["anthropic_api"].calls == []

    def mutate2(d):
        d["routes"]["api"] = ["anthropic_api:claude-haiku-5-5"]
        d["providers"]["anthropic_api"]["limits"] = [
            {"window": "month", "max_usd": 30.0, "hard": True},
            {"window": "day", "max_usd": 0.00001, "hard": False},
        ]

    gw2 = build(mutate2)
    assert gw2.complete("api", None, part("x"), None, "public").provider == "anthropic_api"
    assert rows("select count(*) from events where kind='gateway.soft_limit'")[0][0] == 1


def test_concurrent_reservations_cannot_exceed_a_cap(env):
    build, provs, _ = env

    def mutate(d):
        d["providers"]["claude_cli"]["limits"] = [{"window": "day", "max_calls": 1}]
        d["routes"]["solo"] = ["claude_cli:haiku"]

    gw = build(mutate)
    barrier = threading.Barrier(2)
    outcomes: list[object] = []

    def slow(req):
        time.sleep(0.3)  # the first call is still in flight while the second one reserves
        return ProviderResponse("ok")

    provs["claude_cli"].script = [slow, slow]

    def worker():
        barrier.wait()
        try:
            outcomes.append(gw.complete("solo", None, part("x"), None, "public"))
        except Queued as e:
            outcomes.append(e)

    ts = [threading.Thread(target=worker) for _ in range(2)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert sum(1 for o in outcomes if isinstance(o, Queued)) == 1
    assert rows("select count(*) from model_usage where provider='claude_cli'")[0][0] == 1


# ---------------- ledger honesty ----------------
def test_ledger_never_fabricates_tokens_or_cost(env):
    build, provs, _ = env

    def mutate(d):
        d["routes"]["api"] = ["anthropic_api:claude-haiku-5-5"]
        d["routes"]["sub"] = ["claude_cli:haiku"]

    gw = build(mutate)
    gw.complete("api", None, part("x"), None, "public")
    provs["claude_cli"].script = [ProviderResponse("hi", 10, 5)]
    gw.complete("sub", None, part("y"), None, "public")
    api, sub = rows(
        "select input_tokens, cost_usd, pricing_basis from model_usage order by reserved_at"
    )
    assert api == (None, None, "api")  # unknown tokens -> NULL, unknown api cost -> NULL
    assert sub[0] == 10 and float(sub[1]) == 0.0 and sub[2] == "subscription"


def test_known_api_tokens_give_exact_cost(env):
    build, provs, _ = env
    gw = build(lambda d: d["routes"].__setitem__("api", ["anthropic_api:claude-haiku-5-5"]))
    provs["anthropic_api"].script = [ProviderResponse("ok", 1_000_000, 1_000_000)]
    gw.complete("api", None, part("x"), None, "public")
    assert float(rows("select cost_usd from model_usage")[0][0]) == pytest.approx(0.60)


def test_stale_reservations_become_abandoned_but_still_count(env):
    build, _, clock = env
    gw = build()
    with Session(engine()) as s:
        ledger.reserve(
            s, gw.policy, "claude_cli", "haiku", "ceo", "x", None, None, clock.now, "p", 10
        )
        assert ledger.reconcile_stale(s, clock.now) == 0
        assert ledger.reconcile_stale(s, clock.now + timedelta(minutes=16)) == 1
        w = ledger.window_usage(
            s, "claude_cli", gw.policy.providers["claude_cli"].limits[0], clock.now, gw.policy
        )
    assert w.used == 1
    assert rows("select outcome from model_usage")[0][0] == "abandoned"


# ---------------- redaction end to end ----------------
def test_planted_secret_never_reaches_prompt_ledger_events_results_or_logs(
    env, monkeypatch, caplog
):
    build, provs, _ = env
    planted = "sk-ant-" + "api03-PLANTED1234567890abcdef"
    monkeypatch.setenv("SOME_VENDOR_API_KEY", "envsecretvalue-98765")
    gw = build()
    provs["claude_cli"].script = [
        ProviderResponse(f"echoing {planted} and envsecretvalue-98765", 1, 1)
    ]
    ref = TaskRef()
    with caplog.at_level(logging.DEBUG):
        r = gw.complete(
            "ceo",
            ref,
            part(f"token is {planted} and envsecretvalue-98765"),
            None,
            "founder_private",
            purpose="ack",
        )
    sent = provs["claude_cli"].calls[0].prompt
    assert planted not in sent and "envsecretvalue-98765" not in sent
    assert planted not in r.text and "envsecretvalue-98765" not in r.text
    blob = str(rows("select * from model_usage")) + str(rows("select payload from events"))
    assert planted not in blob and "envsecretvalue-98765" not in blob
    assert planted not in caplog.text


def test_provider_errors_are_recorded_without_raw_detail_then_fall_through(env):
    build, provs, _ = env
    provs["claude_cli"].script = [ProviderError("http_500")]
    gw = build()
    r = gw.complete("ceo", None, part("x"), None, "public", purpose="ack")
    assert r.provider == "anthropic_api"
    assert rows("select outcome, error_kind from model_usage order by reserved_at")[0] == (
        "error",
        "http_500",
    )


def test_all_routes_failing_raises(env):
    build, provs, _ = env
    provs["claude_cli"].script = [ProviderError("x")]
    provs["anthropic_api"].script = [ProviderError("y")]
    with pytest.raises(AllRoutesFailed):
        build().complete("ceo", None, part("x"), None, "public", purpose="ack")


# ---------------- build priority and 70% rule ----------------
def test_claude_cli_is_skipped_while_build_runner_active(env):
    build, provs, _ = env
    gw = build(build_active=True)
    r = gw.complete("ceo", None, part("x"), None, "public", purpose="ack")
    assert r.provider == "anthropic_api" and provs["claude_cli"].calls == []
    gw2 = build(build_active=True)
    r2 = gw2.complete(
        "ceo", None, part("x"), None, "public", purpose="ack", allow_during_build=True
    )
    assert r2.provider == "claude_cli"


def test_routine_roles_prefer_api_above_70_percent(env):
    build, provs, _ = env

    def mutate(d):
        d["providers"]["claude_cli"]["limits"] = [{"window": "day", "max_calls": 10}]

    gw = build(mutate)
    assert (
        gw.complete("qa", None, part("n"), None, "public", purpose="narrative").provider
        == "claude_cli"
    )
    for _ in range(7):
        gw.complete("qa", None, part("n"), None, "public", purpose="narrative")
    # 8 of 10 used (>70%): the narrative role now prefers the paid Haiku API
    assert (
        gw.complete("qa", None, part("n"), None, "public", purpose="narrative").provider
        == "anthropic_api"
    )


def test_secret_in_schema_is_refused_before_any_call(env):
    build, provs, _ = env
    schema = {"description": "sk-ant-" + "api03-PLANTED1234567890abcdef"}
    with pytest.raises(DataClassRefused):
        build().complete("ceo", None, part("x"), schema, "public", purpose="ack")
    assert provs["claude_cli"].calls == []


def test_hostile_provider_exception_never_reaches_logs(env, caplog):
    build, provs, _ = env
    provs["claude_cli"].script = [RuntimeError("leaky-internal-detail-42")]
    with caplog.at_level(logging.DEBUG):
        build().complete("ceo", None, part("x"), None, "public", purpose="ack")
    assert "leaky-internal-detail-42" not in caplog.text


def test_unsettled_spend_survives_month_rollover(env):
    build, _, clock = env
    gw = build()
    clock.now = datetime(2026, 11, 30, 23, 59, tzinfo=UTC)
    with Session(engine()) as s:
        ledger.reserve(
            s,
            gw.policy,
            "anthropic_api",
            "claude-haiku-5-5",
            "ceo",
            "x",
            None,
            None,
            clock.now,
            "p",
            1000,
        )
        limit = gw.policy.providers["anthropic_api"].limits[0]
        later = datetime(2026, 12, 1, 0, 1, tzinfo=UTC)
        assert ledger.window_usage(s, "anthropic_api", limit, later, gw.policy).used > 0


@pytest.mark.parametrize(
    ("stdout", "active"),
    [
        ("inactive\n", False),
        ("failed\n", False),
        ("active\n", True),
        ("activating\n", True),
        ("", True),
        ("weird\n", True),
    ],
)
def test_build_probe_only_permits_explicitly_stopped_states(monkeypatch, stdout, active):
    import subprocess

    from app.gateway import router

    monkeypatch.setattr(
        router.subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 0, stdout, "")
    )
    assert router.systemctl_build_active() is active


def test_build_pause_with_no_fallback_queues_instead_of_failing(env):
    build, provs, clock = env
    gw = build(lambda d: d["routes"].__setitem__("solo", ["claude_cli:haiku"]), build_active=True)
    with pytest.raises(Queued) as q:
        gw.complete("solo", None, part("x"), None, "public")
    assert q.value.resets_at > clock.now and provs["claude_cli"].calls == []


def test_call_settled_after_rollover_counts_in_the_new_month(env):
    build, _, clock = env
    gw = build()
    clock.now = datetime(2026, 11, 30, 23, 59, tzinfo=UTC)
    later = datetime(2026, 12, 1, 0, 2, tzinfo=UTC)
    with Session(engine()) as s:
        uid = ledger.reserve(
            s,
            gw.policy,
            "anthropic_api",
            "claude-haiku-5-5",
            "ceo",
            "x",
            None,
            None,
            clock.now,
            "p",
            1000,
        )
        ledger.finalize(s, uid, outcome="ok", now=later, latency_ms=1, cost_usd=Decimal("2.5"))
        limit = gw.policy.providers["anthropic_api"].limits[0]
        assert ledger.window_usage(s, "anthropic_api", limit, later, gw.policy).used == 2.5


def test_escaped_known_secret_in_schema_is_refused(env, monkeypatch):
    build, provs, _ = env
    value = 'odd"value\\with-escapes-123'
    monkeypatch.setenv("SOME_VENDOR_API_KEY", value)
    with pytest.raises(DataClassRefused):
        build().complete("ceo", None, part("x"), {"enum": [value]}, "public", purpose="ack")
    assert provs["claude_cli"].calls == []

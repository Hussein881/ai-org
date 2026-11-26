import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Identity,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def _now() -> datetime:
    return datetime.now(UTC)


def _id() -> str:
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    pass


class _Row:
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    schema_version: Mapped[int] = mapped_column(Integer, default=1)
    data_class: Mapped[str] = mapped_column(String(20), default="public")


class User(_Row, Base):
    __tablename__ = "users"
    email: Mapped[str] = mapped_column(String(255), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))


class Role(_Row, Base):
    __tablename__ = "roles"
    slug: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(128))
    department: Mapped[str] = mapped_column(String(64))
    reports_to: Mapped[str] = mapped_column(String(64))
    current_version: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(32), default="idle")


class RoleVersion(_Row, Base):
    __tablename__ = "role_versions"
    __table_args__ = (UniqueConstraint("role_id", "version"),)
    role_id: Mapped[str] = mapped_column(ForeignKey("roles.id"))
    version: Mapped[int] = mapped_column(Integer)
    card: Mapped[dict[str, Any]] = mapped_column(JSON)
    actor: Mapped[str] = mapped_column(String(64), default="seed")


class Event(_Row, Base):
    """Append-only."""

    __tablename__ = "events"
    seq: Mapped[int] = mapped_column(BigInteger, Identity(), unique=True)
    kind: Mapped[str] = mapped_column(String(64))
    actor: Mapped[str] = mapped_column(String(64))
    task_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    run_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)


class Project(_Row, Base):
    __tablename__ = "projects"
    name: Mapped[str] = mapped_column(String(128), unique=True)


class Task(_Row, Base):
    __tablename__ = "tasks"
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(32), default="draft")
    assignee: Mapped[str] = mapped_column(String(64))
    actor: Mapped[str] = mapped_column(String(64))
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id"), nullable=True)
    check_record: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    status_reason: Mapped[str | None] = mapped_column(String(200), nullable=True)


class Run(_Row, Base):
    __tablename__ = "runs"
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id"))
    attempt: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(20), default="running")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


class AuditLog(_Row, Base):
    """Append-only record of state-changing actions."""

    __tablename__ = "audit_log"
    actor: Mapped[str] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(64))
    task_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    detail: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class ModelUsage(_Row, Base):
    """One gateway call. Token counts and cost stay NULL when the provider did not report them."""

    __tablename__ = "model_usage"
    provider: Mapped[str] = mapped_column(String(32))
    model: Mapped[str] = mapped_column(String(64))
    role: Mapped[str] = mapped_column(String(64))
    purpose: Mapped[str] = mapped_column(String(32), default="default")
    task_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    run_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    outcome: Mapped[str] = mapped_column(String(16), default="reserved")
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(12, 6), nullable=True)
    reserved_cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(12, 6), nullable=True)
    pricing_basis: Mapped[str] = mapped_column(String(16))
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_kind: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reserved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ProviderQuota(_Row, Base):
    __tablename__ = "provider_quota"
    provider: Mapped[str] = mapped_column(String(32), unique=True)
    blocked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_rate_limit_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class ExternalEffect(_Row, Base):
    """Task-level record of a side effect, written before it starts and after it ends."""

    __tablename__ = "external_effect"
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id"))
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"))
    kind: Mapped[str] = mapped_column(String(32))
    attempt: Mapped[int] = mapped_column(Integer)
    idempotency_key: Mapped[str] = mapped_column(String(200), unique=True)
    status: Mapped[str] = mapped_column(String(16), default="intent")
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class WorkerControl(Base):
    """Single row: emergency stop flag/generation and the current executor epoch."""

    __tablename__ = "worker_control"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    stopped: Mapped[bool] = mapped_column(Boolean, default=False)
    generation: Mapped[int] = mapped_column(Integer, default=0)
    epoch: Mapped[int] = mapped_column(Integer, default=0)
    reason: Mapped[str | None] = mapped_column(String(200), nullable=True)
    actor: Mapped[str | None] = mapped_column(String(255), nullable=True)
    requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class WorkerStatus(Base):
    __tablename__ = "worker_status"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    in_flight: Mapped[int] = mapped_column(Integer, default=0)

"""model_usage, provider_quota, tasks.retry_at

Revision ID: 0003
Revises: 0002
"""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
PROVIDERS = (
    "fake",
    "claude_cli",
    "codex_cli",
    "anthropic_api",
    "gemini_api",
    "openrouter_free",
    "openai_api",
)


def _base() -> list[sa.Column]:
    return [
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("schema_version", sa.Integer, nullable=False),
        sa.Column("data_class", sa.String(20), nullable=False),
    ]


def upgrade() -> None:
    op.add_column("tasks", sa.Column("retry_at", sa.DateTime(timezone=True), nullable=True))
    op.create_table(
        "model_usage",
        *_base(),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("model", sa.String(64), nullable=False),
        sa.Column("role", sa.String(64), nullable=False),
        sa.Column("purpose", sa.String(32), nullable=False),
        sa.Column("task_id", sa.String(36), nullable=True),
        sa.Column("run_id", sa.String(36), nullable=True),
        sa.Column("outcome", sa.String(16), nullable=False),
        sa.Column("input_tokens", sa.Integer, nullable=True),
        sa.Column("output_tokens", sa.Integer, nullable=True),
        sa.Column("cost_usd", sa.Numeric(12, 6), nullable=True),
        sa.Column("reserved_cost_usd", sa.Numeric(12, 6), nullable=True),
        sa.Column("pricing_basis", sa.String(16), nullable=False),
        sa.Column("latency_ms", sa.Integer, nullable=True),
        sa.Column("error_kind", sa.String(64), nullable=True),
        sa.Column("reserved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "outcome IN ('reserved','ok','error','rate_limited','malformed','abandoned')",
            name="ck_model_usage_outcome",
        ),
        sa.CheckConstraint(
            "pricing_basis IN ('subscription','free','api')", name="ck_model_usage_basis"
        ),
    )
    op.create_index("ix_model_usage_provider_reserved", "model_usage", ["provider", "reserved_at"])
    op.create_index("ix_model_usage_role_reserved", "model_usage", ["role", "reserved_at"])
    op.create_table(
        "provider_quota",
        *_base(),
        sa.Column("provider", sa.String(32), nullable=False, unique=True),
        sa.Column("blocked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_rate_limit_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    insert = sa.text(
        "INSERT INTO provider_quota "
        "(id, created_at, schema_version, data_class, provider, updated_at) "
        "VALUES (gen_random_uuid()::text, now(), 1, 'public', :name, now())"
    )
    for name in PROVIDERS:
        op.get_bind().execute(insert, {"name": name})


def downgrade() -> None:
    op.drop_table("provider_quota")
    op.drop_index("ix_model_usage_role_reserved", "model_usage")
    op.drop_index("ix_model_usage_provider_reserved", "model_usage")
    op.drop_table("model_usage")
    op.drop_column("tasks", "retry_at")

"""tasks, runs, projects, audit_log; events get seq/task_id/run_id

Revision ID: 0002
Revises: 0001
"""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"


def _base() -> list[sa.Column]:
    return [
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("schema_version", sa.Integer, nullable=False),
        sa.Column("data_class", sa.String(20), nullable=False),
    ]


def upgrade() -> None:
    op.add_column("events", sa.Column("seq", sa.BigInteger, sa.Identity(), nullable=False))
    op.create_unique_constraint("uq_events_seq", "events", ["seq"])
    op.add_column("events", sa.Column("task_id", sa.String(36), nullable=True))
    op.add_column("events", sa.Column("run_id", sa.String(36), nullable=True))
    op.create_index("ix_events_task_id", "events", ["task_id"])
    op.create_table(
        "projects", *_base(), sa.Column("name", sa.String(128), nullable=False, unique=True)
    )
    op.create_table(
        "tasks",
        *_base(),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("assignee", sa.String(64), nullable=False),
        sa.Column("actor", sa.String(64), nullable=False),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id"), nullable=True),
        sa.Column("check_record", sa.JSON, nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "runs",
        *_base(),
        sa.Column("task_id", sa.String(36), sa.ForeignKey("tasks.id"), nullable=False),
        sa.Column("attempt", sa.Integer, nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("result", sa.JSON, nullable=True),
    )
    op.create_table(
        "audit_log",
        *_base(),
        sa.Column("actor", sa.String(64), nullable=False),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("task_id", sa.String(36), nullable=True),
        sa.Column("detail", sa.JSON, nullable=False),
    )
    op.execute(
        "CREATE TRIGGER audit_log_no_change BEFORE UPDATE OR DELETE ON audit_log "
        "FOR EACH ROW EXECUTE FUNCTION events_append_only()"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER audit_log_no_change ON audit_log")
    for t in ("audit_log", "runs", "tasks", "projects"):
        op.drop_table(t)
    op.drop_index("ix_events_task_id", "events")
    op.drop_constraint("uq_events_seq", "events")
    for c in ("run_id", "task_id", "seq"):
        op.drop_column("events", c)

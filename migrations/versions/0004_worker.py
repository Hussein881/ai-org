"""durable worker: procrastinate schema, external_effect, worker control/status, status_reason

Revision ID: 0004
Revises: 0003
"""

from pathlib import Path

import sqlalchemy as sa
from alembic import op
from procrastinate.contrib.alembic.migrations_utils import execute_script

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

SCHEMA = Path(__file__).resolve().parents[1] / "procrastinate" / "schema-3.12.0.sql"
TS = sa.DateTime(timezone=True)


def upgrade() -> None:
    execute_script(SCHEMA.read_text())
    op.add_column("tasks", sa.Column("status_reason", sa.String(200), nullable=True))
    op.create_table(
        "external_effect",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("created_at", TS, nullable=False),
        sa.Column("schema_version", sa.Integer, nullable=False),
        sa.Column("data_class", sa.String(20), nullable=False),
        sa.Column("task_id", sa.String(36), sa.ForeignKey("tasks.id"), nullable=False),
        sa.Column("run_id", sa.String(36), sa.ForeignKey("runs.id"), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("attempt", sa.Integer, nullable=False),
        sa.Column("idempotency_key", sa.String(200), nullable=False, unique=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("result", sa.JSON, nullable=True),
        sa.Column("updated_at", TS, nullable=False),
    )
    op.create_index("ix_effect_task", "external_effect", ["task_id", "kind", "attempt"])
    op.create_table(
        "worker_control",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("stopped", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("generation", sa.Integer, nullable=False, server_default="0"),
        sa.Column("epoch", sa.Integer, nullable=False, server_default="0"),
        sa.Column("reason", sa.String(200), nullable=True),
        sa.Column("actor", sa.String(255), nullable=True),
        sa.Column("requested_at", TS, nullable=True),
        sa.Column("resumed_at", TS, nullable=True),
        sa.CheckConstraint("id = 1", name="worker_control_single_row"),
    )
    op.create_table(
        "worker_status",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("heartbeat_at", TS, nullable=True),
        sa.Column("in_flight", sa.Integer, nullable=False, server_default="0"),
        sa.CheckConstraint("id = 1", name="worker_status_single_row"),
    )
    op.execute("insert into worker_control (id) values (1)")
    op.execute("insert into worker_status (id) values (1)")


def downgrade() -> None:
    op.drop_table("worker_status")
    op.drop_table("worker_control")
    op.drop_table("external_effect")
    op.drop_column("tasks", "status_reason")
    op.execute(
        """
        do $$ declare r record; begin
          for r in select tablename from pg_tables
                   where schemaname = 'public' and tablename like 'procrastinate\\_%' loop
            execute format('drop table if exists %I cascade', r.tablename);
          end loop;
          for r in select p.oid::regprocedure as sig from pg_proc p
                   join pg_namespace n on n.oid = p.pronamespace
                   where n.nspname = 'public' and p.proname like 'procrastinate\\_%' loop
            execute 'drop function if exists ' || r.sig || ' cascade';
          end loop;
          for r in select t.typname from pg_type t join pg_namespace n on n.oid = t.typnamespace
                   where n.nspname = 'public' and t.typname like 'procrastinate\\_%'
                   and t.typtype in ('e', 'c') loop
            execute format('drop type if exists %I cascade', r.typname);
          end loop;
        end $$;
        """
    )

"""baseline: users, roles, role_versions, events

Revision ID: 0001
Revises:
"""

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None


def _base() -> list[sa.Column]:
    return [
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("schema_version", sa.Integer, nullable=False),
        sa.Column("data_class", sa.String(20), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "users",
        *_base(),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
    )
    op.create_table(
        "roles",
        *_base(),
        sa.Column("slug", sa.String(64), nullable=False, unique=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("department", sa.String(64), nullable=False),
        sa.Column("reports_to", sa.String(64), nullable=False),
        sa.Column("current_version", sa.Integer, nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
    )
    op.create_table(
        "role_versions",
        *_base(),
        sa.Column("role_id", sa.String(36), sa.ForeignKey("roles.id"), nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("card", sa.JSON, nullable=False),
        sa.Column("actor", sa.String(64), nullable=False),
        sa.UniqueConstraint("role_id", "version"),
    )
    op.create_table(
        "events",
        *_base(),
        sa.Column("kind", sa.String(64), nullable=False),
        sa.Column("actor", sa.String(64), nullable=False),
        sa.Column("payload", sa.JSON, nullable=False),
        sa.Column("note", sa.Text, nullable=True),
    )
    # Events are append-only (ARCH §Data model): reject UPDATE/DELETE at the database.
    op.execute(
        """CREATE FUNCTION events_append_only() RETURNS trigger AS $$
        BEGIN RAISE EXCEPTION 'events is append-only'; END; $$ LANGUAGE plpgsql"""
    )
    op.execute(
        "CREATE TRIGGER events_no_change BEFORE UPDATE OR DELETE ON events "
        "FOR EACH ROW EXECUTE FUNCTION events_append_only()"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER events_no_change ON events")
    op.execute("DROP FUNCTION events_append_only()")
    for t in ("events", "role_versions", "roles", "users"):
        op.drop_table(t)

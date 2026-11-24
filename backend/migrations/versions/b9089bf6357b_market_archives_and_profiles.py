"""Store archive metadata, repository documents, and user avatars."""

import sqlalchemy as sa
from alembic import op

revision = "b9089bf6357b"
down_revision = "856b13516187"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add nullable fields without changing existing accounts or releases."""
    op.add_column("users", sa.Column("avatar", sa.LargeBinary()))
    op.add_column("users", sa.Column("avatar_revision", sa.String(36)))
    op.add_column("plugins", sa.Column("stars", sa.Integer()))
    op.add_column("plugins", sa.Column("documents", sa.JSON()))
    op.add_column("plugins", sa.Column("sync_state", sa.String(20)))
    op.add_column("plugin_versions", sa.Column("package_sha256", sa.String(64)))
    op.add_column("plugin_versions", sa.Column("package_bytes", sa.Integer()))


def downgrade() -> None:
    """Remove fields added by this revision."""
    op.drop_column("plugin_versions", "package_bytes")
    op.drop_column("plugin_versions", "package_sha256")
    op.drop_column("plugins", "sync_state")
    op.drop_column("plugins", "documents")
    op.drop_column("plugins", "stars")
    op.drop_column("users", "avatar_revision")
    op.drop_column("users", "avatar")

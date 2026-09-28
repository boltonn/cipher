"""Split selector `kind` into `type` + `subtype`, add `selector.attributes`.

- ``selector_kind`` -> ``selector_type`` (the broad family: phone, email,
  crypto_address, social_handle, ...) on both ``selector`` and ``mention``.
- new ``selector_subtype`` (nullable) on both: the specific provider / network /
  scheme -- telegram, btc_address, cn_ric, ... Indexed on ``selector`` for
  per-platform filtering.
- new ``selector.attributes`` (JSONB, default ``{}``): kind-specific facts pulled
  out during validation -- IBAN country/bank code, crypto currency/network, phone
  carrier/geo, IP version, passport issuing country, ...
- enum-backed columns widen VARCHAR(14) -> VARCHAR(32) for the longer names
  (``odnoklassniki``, ``tron_address``, ``ir_code_melli``). Mirrors 0007 / 0009.
- blocking key constraint ``uq_selector_dataset_kind_value`` ->
  ``uq_selector_dataset_type_value``; partial index predicate updated.

Revision ID: 0012_selector_attributes
Revises: 0011_event_dataset_nullable
Create Date: 2026-09-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0012_selector_attributes"
down_revision: str | None = "0011_event_dataset_nullable"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_WIDE = sa.String(length=32)
_NARROW = sa.String(length=14)


def upgrade() -> None:
    # --- selector ---
    op.drop_constraint("uq_selector_dataset_kind_value", "selector", type_="unique")
    op.alter_column("selector", "selector_kind", new_column_name="selector_type", existing_type=_NARROW, type_=_WIDE)
    op.add_column("selector", sa.Column("selector_subtype", _WIDE, nullable=True))
    op.add_column(
        "selector",
        sa.Column("attributes", postgresql.JSONB(), server_default="{}", nullable=False),
    )
    op.create_index("ix_selector_selector_subtype", "selector", ["selector_subtype"])
    op.create_unique_constraint(
        "uq_selector_dataset_type_value", "selector", ["dataset_id", "selector_type", "normalized_value"]
    )

    # --- mention ---
    op.drop_index("ix_mention_selector_value", table_name="mention")
    op.alter_column("mention", "selector_kind", new_column_name="selector_type", existing_type=_NARROW, type_=_WIDE)
    op.add_column("mention", sa.Column("selector_subtype", _WIDE, nullable=True))
    op.create_index(
        "ix_mention_selector_value",
        "mention",
        ["dataset_id", "normalized_value"],
        postgresql_where=sa.text("selector_type IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_mention_selector_value", table_name="mention")
    op.drop_column("mention", "selector_subtype")
    op.alter_column("mention", "selector_type", new_column_name="selector_kind", existing_type=_WIDE, type_=_NARROW)
    op.create_index(
        "ix_mention_selector_value",
        "mention",
        ["dataset_id", "normalized_value"],
        postgresql_where=sa.text("selector_kind IS NOT NULL"),
    )

    op.drop_constraint("uq_selector_dataset_type_value", "selector", type_="unique")
    op.drop_index("ix_selector_selector_subtype", table_name="selector")
    op.drop_column("selector", "attributes")
    op.drop_column("selector", "selector_subtype")
    op.alter_column("selector", "selector_type", new_column_name="selector_kind", existing_type=_WIDE, type_=_NARROW)
    op.create_unique_constraint(
        "uq_selector_dataset_kind_value", "selector", ["dataset_id", "selector_kind", "normalized_value"]
    )

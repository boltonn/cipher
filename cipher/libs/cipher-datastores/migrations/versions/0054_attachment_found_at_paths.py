"""An email attachment's `path` is where it was found, `<email path>/<filename>`, like an archive member's.

Attachments used to be written to an attachments folder and keep that location (`.../<md5>.pdf`)
as their `path`. Their bytes stay where they are (`uri` is untouched); only `path` changes. A
filename repeated within one email gets `~2`, `~3` ... before its extension, in the order the
attachments were found. Files below a moved one (members of an attached zip, attachments of an
attached email) are re-rooted under its new path. Downgrade leaves paths as they are.

Revision ID: 0054_attachment_found_at_paths
Revises: 0053_email_conversation_id_index
Create Date: 2026-10-12
"""

from collections import Counter, defaultdict
from collections.abc import Sequence
from pathlib import PurePosixPath

import sqlalchemy as sa
from alembic import op

revision: str = "0054_attachment_found_at_paths"
down_revision: str | None = "0053_email_conversation_id_index"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _unique(name: str | None, seen: Counter[str]) -> str:
    """Same naming as the email step's blob sink: `attachment` when unnamed, `~n` on repeats."""
    name = (name or "attachment").replace("/", "_").strip() or "attachment"
    seen[name] += 1
    if seen[name] == 1:
        return name
    return f"{PurePosixPath(name).stem}~{seen[name]}{PurePosixPath(name).suffix}"


def upgrade() -> None:
    """Recompute paths below every email, then write them in two steps (no transient unique clash)."""
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            "SELECT id, parent_id, path, filename, filetype_group FROM file "
            "WHERE dataset_id IN (SELECT DISTINCT c.dataset_id FROM file c JOIN file p ON p.id = c.parent_id "
            "WHERE p.filetype_group = 'email') ORDER BY date_created, id"
        )
    ).all()
    by_id = {row.id: row for row in rows}
    children: dict[str, list] = defaultdict(list)
    for row in rows:
        if row.parent_id in by_id:
            children[row.parent_id].append(row)

    moved: dict[str, str] = {}
    stack = [row for row in rows if row.parent_id not in by_id]
    while stack:
        parent = stack.pop()
        parent_path = moved.get(parent.id, parent.path)
        seen: Counter[str] = Counter()
        for child in children[parent.id]:
            if parent.filetype_group == "email":
                new = f"{parent_path.rstrip('/')}/{_unique(child.filename, seen)}"
            elif parent.id in moved and child.path.startswith(parent.path.rstrip("/") + "/"):
                new = parent_path.rstrip("/") + child.path[len(parent.path.rstrip("/")) :]
            else:
                new = child.path
            if new != child.path:
                moved[child.id] = new
            stack.append(child)

    if not moved:
        return
    updates = [{"id": file_id, "path": path} for file_id, path in moved.items()]
    bind.execute(sa.text("UPDATE file SET path = 'moving:' || id WHERE id = :id"), [{"id": u["id"]} for u in updates])
    bind.execute(sa.text("UPDATE file SET path = :path WHERE id = :id"), updates)


def downgrade() -> None:
    """Old attachment-folder paths aren't kept; nothing to restore."""

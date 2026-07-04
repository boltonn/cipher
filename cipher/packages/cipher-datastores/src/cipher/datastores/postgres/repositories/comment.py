from sqlalchemy import asc, delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from cipher.datastores.postgres.tables.comment import CommentTable
from cipher.schemas.comment import (
    Comment,
    CommentableType,
    CommentCreate,
    CommentPublic,
    CommentUpdate,
)


class PostgresCommentRepository:
    """Postgres datastore implementation for comments using SQLAlchemy."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_table(self):
        """Create the comment table using SQLAlchemy metadata."""
        async with self.session.bind.begin() as conn:
            await conn.run_sync(CommentTable.metadata.create_all)

    async def add_comment(self, comment: CommentCreate) -> Comment:
        """Add a new comment."""
        comment_table = CommentTable(**comment.model_dump())
        self.session.add(comment_table)
        await self.session.commit()
        await self.session.refresh(comment_table)
        return Comment.model_validate(comment_table)

    async def get_comments(
        self, commentable_type: CommentableType, commentable_id: str
    ) -> list[CommentPublic]:
        """Retrieve all comments on a resource, oldest first."""
        stmt = (
            select(CommentTable)
            .options(selectinload(CommentTable.user))
            .where(
                CommentTable.commentable_type == commentable_type,
                CommentTable.commentable_id == commentable_id,
            )
            .order_by(asc(CommentTable.date_created))
        )
        result = await self.session.execute(stmt)
        comments = result.scalars().all()
        return [
            CommentPublic.model_validate({**c.__dict__, "user_name": c.user.name}) for c in comments
        ]

    async def get_comment_by_id(self, comment_id: str) -> Comment | None:
        """Retrieve a comment by ID."""
        result = await self.session.execute(select(CommentTable).where(CommentTable.id == comment_id))
        comment_table = result.scalar_one_or_none()
        return Comment.model_validate(comment_table) if comment_table else None

    async def update_comment(self, comment_id: str, data: CommentUpdate) -> Comment | None:
        """Update a comment's content."""
        update_dict = data.model_dump(exclude_unset=True)
        stmt = (
            update(CommentTable)
            .where(CommentTable.id == comment_id)
            .values(**update_dict)
            .returning(CommentTable)
        )
        result = await self.session.execute(stmt)
        comment_table = result.scalar_one_or_none()
        comment = Comment.model_validate(comment_table) if comment_table else None
        await self.session.commit()
        return comment

    async def delete_comment(self, comment_id: str) -> bool:
        """Delete a comment by ID."""
        result = await self.session.execute(delete(CommentTable).where(CommentTable.id == comment_id))
        await self.session.commit()
        return bool(result.rowcount)

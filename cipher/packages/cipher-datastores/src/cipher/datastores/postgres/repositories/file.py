from sqlalchemy import asc, desc, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from cipher.datastores.postgres.tables.file import FileTable
from cipher.schemas.file import (
    File,
    FileBrowserItem,
    FileBrowserRequest,
    FileBrowserResponse,
    FileBrowserType,
    FileCreate,
    FileInstanceSortField,
    SortOrder,
)


class PostgresFileRepository:
    """Postgres datastore implementation using SQLAlchemy."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def delete_tables(self):
        """Drop file table using SQLAlchemy metadata."""
        async with self.session.bind.begin() as conn:
            await conn.run_sync(FileTable.metadata.drop_all)

    async def create_tables(self):
        """Create file table using SQLAlchemy metadata."""
        async with self.session.bind.begin() as conn:
            await conn.run_sync(FileTable.metadata.create_all)

    async def upsert_file(self, file_data: FileCreate) -> File:
        """Upsert a file.

        Returns:
            The upserted File object.
        """
        data = file_data.model_dump()

        stmt = (
            pg_insert(FileTable)
            .values(**data)
            .on_conflict_do_nothing(index_elements=["dataset_id", "uri"])
            .returning(FileTable.id)
        )

        result = await self.session.execute(stmt)
        file_id = result.scalar_one_or_none()
        await self.session.commit()

        if file_id:
            # New file was inserted
            result = await self.session.execute(
                select(FileTable).where(FileTable.id == file_id)
            )
            file_orm = result.scalar_one()
            return File.model_validate(file_orm)

        # File already exists, fetch it
        result = await self.session.execute(
            select(FileTable).where(
                FileTable.dataset_id == data["dataset_id"],
                FileTable.uri == data["uri"],
            )
        )
        file_orm = result.scalar_one()
        return File.model_validate(file_orm)

    async def get_file_by_id(self, file_id: str) -> File | None:
        """Retrieve a file by its ID."""
        result = await self.session.execute(
            select(FileTable).where(FileTable.id == file_id)
        )
        file_orm = result.scalar_one_or_none()
        if file_orm is None:
            return None
        return File.model_validate(file_orm)

    async def get_file_by_sha256(self, sha256: str) -> File | None:
        """Retrieve a file by its SHA256 hash."""
        result = await self.session.execute(
            select(FileTable).where(FileTable.sha256 == sha256).limit(1)
        )
        file_orm = result.scalar_one_or_none()
        return File.model_validate(file_orm) if file_orm else None

    async def find_duplicates(
        self, sha256: str, exclude_dataset_id: str | None = None
    ) -> list[File]:
        """Find files with the same SHA256 hash (duplicates).

        Optionally exclude files from a specific dataset.
        """
        stmt = select(FileTable).where(FileTable.sha256 == sha256)

        if exclude_dataset_id:
            stmt = stmt.where(FileTable.dataset_id != exclude_dataset_id)

        result = await self.session.execute(stmt)
        return [File.model_validate(orm) for orm in result.scalars().all()]

    async def delete_file(self, file_id: str) -> bool:
        """Delete a file by its ID. Returns True if deleted, False if not found."""
        result = await self.session.execute(
            select(FileTable).where(FileTable.id == file_id)
        )
        file_orm = result.scalar_one_or_none()

        if file_orm:
            await self.session.delete(file_orm)
            await self.session.commit()
            return True
        return False

    async def get_files_by_dataset(
        self,
        dataset_id: str,
        *,
        path: str | None = None,
        query: str | None = None,
        limit: int,
        offset: int,
        sort_by: FileInstanceSortField,
        sort_order: SortOrder,
    ) -> list[File]:
        """List files in a dataset with optional path filtering and search."""
        stmt = select(FileTable).where(FileTable.dataset_id == dataset_id)

        # Directory-scoped listing
        if path is not None:
            prefix = "/" if path == "/" else path.rstrip("/") + "/"

            # Calculate relative path from the prefix
            relative = func.substring(
                FileTable.path,
                func.length(prefix) + 1,
            )

            # Only direct children (no slash in relative path)
            is_direct_child = func.position("/", relative) == 0

            stmt = stmt.where(FileTable.path.startswith(prefix))
            stmt = stmt.where(is_direct_child)

        # Search by filename
        if query:
            stmt = stmt.where(FileTable.filename.ilike(f"%{query}%"))

        # Sorting
        sort_column = {
            FileInstanceSortField.FILENAME: FileTable.filename,
            FileInstanceSortField.DATE_CREATED: FileTable.date_created,
            FileInstanceSortField.DATE_LAST_UPDATED: FileTable.date_last_updated,
            FileInstanceSortField.SIZE: FileTable.size,
        }[sort_by]

        stmt = stmt.order_by(
            desc(sort_column) if sort_order == SortOrder.DESC else asc(sort_column)
        )

        stmt = stmt.limit(limit).offset(offset)

        result = await self.session.execute(stmt)
        return [File.model_validate(orm) for orm in result.scalars().all()]

    async def count_files_by_dataset(
        self,
        dataset_id: str,
        *,
        path: str | None = None,
        query: str | None = None,
    ) -> int:
        """Count files in a dataset with optional path filtering and search."""
        stmt = select(func.count(FileTable.id)).where(
            FileTable.dataset_id == dataset_id
        )

        # Directory-scoped counting
        if path is not None:
            prefix = "/" if path == "/" else path.rstrip("/") + "/"
            relative = func.substring(FileTable.path, func.length(prefix) + 1)
            is_direct_child = func.position("/", relative) == 0

            stmt = stmt.where(FileTable.path.startswith(prefix))
            stmt = stmt.where(is_direct_child)

        # Search by filename
        if query:
            stmt = stmt.where(FileTable.filename.ilike(f"%{query}%"))

        result = await self.session.execute(stmt)
        return result.scalar_one()

    async def count_folders(
        self,
        dataset_id: str,
        path: str,
    ) -> int:
        """Count folders in a given path within a dataset."""
        prefix = "/" if path == "/" else path.rstrip("/") + "/"

        # Extract relative path from prefix
        relative = func.substring(
            FileTable.path,
            func.length(prefix) + 1,
        )

        # Get the first component (folder name)
        folder_name = func.split_part(relative, "/", 1)

        stmt = (
            select(func.count(func.distinct(folder_name)))
            .where(FileTable.dataset_id == dataset_id)
            .where(FileTable.path.startswith(prefix))
            .where(func.position("/", relative) > 0)  # Only paths with subfolders
        )

        result = await self.session.execute(stmt)
        return result.scalar_one()

    async def list_folders_slice(
        self,
        dataset_id: str,
        path: str,
        *,
        offset: int,
        limit: int,
    ) -> list[str]:
        """List a paginated slice of folders within a given path."""
        prefix = "/" if path == "/" else path.rstrip("/") + "/"

        # Extract relative path from prefix
        relative = func.substring(
            FileTable.path,
            func.length(prefix) + 1,
        )

        # Get the first component (folder name)
        folder_name = func.split_part(relative, "/", 1)

        stmt = (
            select(folder_name)
            .where(FileTable.dataset_id == dataset_id)
            .where(FileTable.path.startswith(prefix))
            .where(func.position("/", relative) > 0)  # Only paths with subfolders
            .distinct()
            .order_by(folder_name)
            .offset(offset)
            .limit(limit)
        )

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_files_slice(
        self,
        dataset_id: str,
        *,
        path: str | None,
        query: str | None,
        offset: int,
        limit: int,
        sort_by: FileInstanceSortField,
        sort_order: SortOrder,
    ) -> list[File]:
        """List files in a dataset, optionally scoped to a directory."""
        stmt = select(FileTable).where(FileTable.dataset_id == dataset_id)

        # Directory-scoped listing (direct children only)
        if path is not None:
            prefix = "/" if path == "/" else path.rstrip("/") + "/"

            relative = func.substring(
                FileTable.path,
                func.length(prefix) + 1,
            )

            stmt = stmt.where(FileTable.path.startswith(prefix))
            stmt = stmt.where(func.position("/", relative) == 0)  # No subdirectories

        # Search
        if query:
            stmt = stmt.where(FileTable.filename.ilike(f"%{query}%"))

        # Sorting
        sort_column = {
            FileInstanceSortField.FILENAME: FileTable.filename,
            FileInstanceSortField.DATE_CREATED: FileTable.date_created,
            FileInstanceSortField.DATE_LAST_UPDATED: FileTable.date_last_updated,
            FileInstanceSortField.SIZE: FileTable.size,
        }[sort_by]

        stmt = stmt.order_by(
            sort_column.desc() if sort_order == SortOrder.DESC else sort_column.asc()
        )

        stmt = stmt.offset(offset).limit(limit)

        result = await self.session.execute(stmt)
        return [File.model_validate(orm) for orm in result.scalars().all()]

    async def browse_directory(
        self,
        dataset_id: str,
        req: FileBrowserRequest,
    ) -> FileBrowserResponse:
        """Browse a directory or list all files in a dataset."""
        offset = (req.page - 1) * req.limit
        entries: list[FileBrowserItem] = []

        # Dataset-wide listing (no folders)
        if req.path is None:
            files = await self.list_files_slice(
                dataset_id,
                path=None,
                query=req.query,
                offset=offset,
                limit=req.limit,
                sort_by=req.sort_by,
                sort_order=req.sort_order,
            )

            entries.extend(
                FileBrowserItem(
                    type=FileBrowserType.FILE,
                    filename=f.filename,
                    path=f.path,
                    uri=f.uri,
                    device=f.device,
                    filetype_group=f.filetype_group,
                    filetype=f.filetype,
                    filetype_name=f.filetype_name,
                    md5=f.md5,
                    sha256=f.sha256,
                    mime_type=f.mime_type,
                    size=f.size,
                    date_created=f.date_created,
                    date_last_updated=f.date_last_updated,
                )
                for f in files
            )

            total = await self.count_files_by_dataset(
                dataset_id, path=None, query=req.query
            )

            return FileBrowserResponse(
                data=entries,
                page=req.page,
                limit=req.limit,
                total=total,
                total_pages=(total + req.limit - 1) // req.limit,
            )

        # Directory listing (folders + files)
        folder_count = await self.count_folders(dataset_id, req.path)

        # 1️⃣ Folders
        if offset < folder_count:
            folder_limit = min(req.limit, folder_count - offset)

            folders = await self.list_folders_slice(
                dataset_id,
                req.path,
                offset=offset,
                limit=folder_limit,
            )

            parent_path = req.path.rstrip("/")
            entries.extend(
                FileBrowserItem(
                    type=FileBrowserType.DIRECTORY,
                    filename=name,
                    path=f"{parent_path}/{name}" if parent_path else f"/{name}",
                    uri="",  # Folders don't have URIs
                    device=None,
                    filetype_group="",
                    filetype="",
                    filetype_name=None,
                    md5="",
                    sha256="",
                    mime_type="",
                    size=0,
                    date_created=None,
                    date_last_updated=None,
                )
                for name in folders
            )
        else:
            folder_limit = 0

        # 2️⃣ Files
        remaining = req.limit - folder_limit
        if remaining > 0:
            file_offset = max(0, offset - folder_count)

            files = await self.list_files_slice(
                dataset_id,
                path=req.path,
                query=req.query,
                offset=file_offset,
                limit=remaining,
                sort_by=req.sort_by,
                sort_order=req.sort_order,
            )

            entries.extend(
                FileBrowserItem(
                    type=FileBrowserType.FILE,
                    filename=f.filename,
                    path=f.path,
                    uri=f.uri,
                    device=f.device,
                    filetype_group=f.filetype_group,
                    filetype=f.filetype,
                    filetype_name=f.filetype_name,
                    md5=f.md5,
                    sha256=f.sha256,
                    mime_type=f.mime_type,
                    size=f.size,
                    date_created=f.date_created,
                    date_last_updated=f.date_last_updated,
                )
                for f in files
            )

        # Calculate total (folders + files in this directory)
        file_count = await self.count_files_by_dataset(
            dataset_id, path=req.path, query=req.query
        )
        total = folder_count + file_count

        return FileBrowserResponse(
            data=entries,
            page=req.page,
            limit=req.limit,
            total=total,
            total_pages=(total + req.limit - 1) // req.limit,
        )

    async def get_dataset_inventory(self, dataset_id: str) -> dict:
        """Get a complete breakdown of the dataset by group and type."""
        stmt = (
            select(
                FileTable.filetype_group,
                FileTable.filetype,
                func.count(FileTable.id).label("count"),
                func.sum(FileTable.size).label("total_size"),
            )
            .where(FileTable.dataset_id == dataset_id)
            .group_by(FileTable.filetype_group, FileTable.filetype)
        )

        result = await self.session.execute(stmt)
        rows = result.all()

        inventory = {}
        for row in rows:
            group = row.filetype_group or "other"
            if group not in inventory:
                inventory[group] = {"count": 0, "size_bytes": 0, "extensions": {}}

            inventory[group]["count"] += row.count
            inventory[group]["size_bytes"] += int(row.total_size or 0)
            inventory[group]["extensions"][row.filetype or "none"] = row.count

        return inventory

    async def get_stratified_samples(
        self, dataset_id: str, limit_per_group: int = 5
    ) -> list[FileTable]:
        """Grab representative files from every group to see naming/path patterns."""
        inner_stmt = (
            select(
                FileTable,
                func.row_number()
                .over(partition_by=FileTable.filetype_group, order_by=func.random())
                .label("row_num"),
            ).where(FileTable.dataset_id == dataset_id)
        ).subquery()

        stmt = select(inner_stmt).where(inner_stmt.c.row_num <= limit_per_group)
        result = await self.session.execute(stmt)
        return list(result.mappings().all())

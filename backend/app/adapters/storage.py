"""Local durable storage for asynchronously ingested upload bytes."""

import asyncio
import shutil
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from app.core.config import get_settings


@dataclass(frozen=True, slots=True)
class StoredFile:
    """An original upload that is still on disk, with the size a client needs."""

    path: Path
    size_bytes: int


class LocalUploadStorage:
    """Store each source beneath an opaque source-id directory, outside the job payload."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = root if root is not None else get_settings().upload_storage_dir

    def path_for(self, source_id: UUID, filename: str) -> Path:
        return self.root / str(source_id) / Path(filename).name

    async def save(self, source_id: UUID, filename: str, content: bytes) -> Path:
        path = self.path_for(source_id, filename)
        await asyncio.to_thread(self._write, path, content)
        return path

    async def read(self, source_id: UUID, filename: str) -> bytes:
        return await asyncio.to_thread(self.path_for(source_id, filename).read_bytes)

    async def find(self, source_id: UUID, filename: str) -> StoredFile | None:
        """Locate the original bytes, or ``None`` when this source has no stored file.

        Missing is a normal state, not a failure: the checked-in public seed libraries
        and any source ingested before durable storage existed have a database record
        and parsed text but were never written here. Callers report that difference to
        the user instead of raising.
        """

        return await asyncio.to_thread(self._find, self.path_for(source_id, filename))

    async def remove(self, source_id: UUID) -> None:
        await asyncio.to_thread(shutil.rmtree, self.root / str(source_id), True)

    @staticmethod
    def _write(path: Path, content: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)

    @staticmethod
    def _find(path: Path) -> StoredFile | None:
        if not path.is_file():
            return None
        return StoredFile(path=path, size_bytes=path.stat().st_size)

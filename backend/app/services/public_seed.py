"""Idempotent ingestion of version-controlled public rule and template libraries."""

import re
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.collection import Collection, CollectionKind, CollectionScope
from app.db.models.document import Document
from app.db.models.source import IngestStatus, Source
from app.services.ingest_service import (
    compute_content_hash,
    ingest_document,
    ingest_pending_source,
)

SEED_ROOT = Path(__file__).resolve().parents[2] / "seeds"

# A leading '---' YAML block documents a checked-in seed file for humans browsing the
# tree (e.g. which library it belongs to). Nothing parses it as data. Rule and template
# collections are injected whole into prompts (ADR decision 16), so if this block is not
# stripped before ingestion, its raw YAML becomes live prompt content on every generation.
_FRONTMATTER_PATTERN = re.compile(r"\A---\r?\n.*?\r?\n---\r?\n\r?\n?", re.DOTALL)


def _strip_frontmatter(content: bytes) -> bytes:
    """Remove a leading YAML frontmatter block, if the seed file has one."""

    text = content.decode("utf-8")
    match = _FRONTMATTER_PATTERN.match(text)
    if match is None:
        return content
    return text[match.end() :].encode("utf-8")


class SeedConfigurationError(ValueError):
    """The checked-in seed tree cannot be mapped safely to database records."""


@dataclass(frozen=True, slots=True)
class SeedLibrary:
    """One checked-in directory and its corresponding public collection."""

    directory: str
    kind: CollectionKind
    collection_name: str


@dataclass(frozen=True, slots=True)
class SeedFile:
    """A Markdown file with a stable, collection-local identity and content hash."""

    relative_path: str
    content: bytes
    content_hash: str


@dataclass(frozen=True, slots=True)
class SeedSummary:
    """Counts from one deterministic public-library synchronization run."""

    created_collections: int
    created_sources: int
    updated_sources: int
    unchanged_sources: int


PUBLIC_LIBRARIES = (
    SeedLibrary("rules", CollectionKind.RULE, "public-rules"),
    SeedLibrary("templates", CollectionKind.TEMPLATE, "public-templates"),
)


async def seed_public_libraries(
    session: AsyncSession,
    *,
    seed_root: Path = SEED_ROOT,
) -> SeedSummary:
    """Synchronize checked-in Markdown into immutable public rule/template collections.

    A seed entry is identified by its collection kind and relative Markdown path.  An
    unchanged, completed source is skipped.  Changed content retains the Source ID,
    clears its derived rows, and re-ingests it in the caller's transaction.
    """

    created_collections = 0
    created_sources = 0
    updated_sources = 0
    unchanged_sources = 0

    for library in PUBLIC_LIBRARIES:
        files = _read_library_files(seed_root, library)
        collection, created = await _get_or_create_public_collection(session, library)
        created_collections += int(created)

        sources = list(
            await session.scalars(
                select(Source)
                .where(Source.collection_id == collection.id)
                .order_by(Source.filename, Source.id)
            )
        )
        sources_by_filename: dict[str, Source] = {}
        for existing_source in sources:
            if existing_source.filename in sources_by_filename:
                raise SeedConfigurationError(
                    f"Public collection {library.collection_name!r} has multiple sources named "
                    f"{existing_source.filename!r}; resolve the duplicate before seeding."
                )
            sources_by_filename[existing_source.filename] = existing_source

        for seed_file in files:
            source = sources_by_filename.get(seed_file.relative_path)
            if (
                source is not None
                and source.content_hash == seed_file.content_hash
                and source.ingest_status is IngestStatus.COMPLETED
                and source.deleted_at is None
            ):
                unchanged_sources += 1
                continue

            await _ensure_content_hash_is_available(
                session,
                collection_id=collection.id,
                content_hash=seed_file.content_hash,
                excluding_source_id=None if source is None else source.id,
            )

            if source is None:
                result = await ingest_document(
                    session,
                    collection_id=collection.id,
                    filename=seed_file.relative_path,
                    file_bytes=seed_file.content,
                    metadata={"seed_path": seed_file.relative_path},
                )
                if result.skipped:
                    raise SeedConfigurationError(
                        f"Seed {seed_file.relative_path!r} unexpectedly matched an existing source."
                    )
                created_sources += 1
                continue

            source.content_hash = seed_file.content_hash
            source.deleted_at = None
            source.ingest_status = IngestStatus.PENDING
            source.error_message = None
            await session.execute(delete(Document).where(Document.source_id == source.id))
            await session.flush()
            await ingest_pending_source(
                session,
                source=source,
                collection=collection,
                file_bytes=seed_file.content,
                metadata={"seed_path": seed_file.relative_path},
            )
            updated_sources += 1

    return SeedSummary(
        created_collections=created_collections,
        created_sources=created_sources,
        updated_sources=updated_sources,
        unchanged_sources=unchanged_sources,
    )


def _read_library_files(seed_root: Path, library: SeedLibrary) -> list[SeedFile]:
    """Read one required Markdown directory and reject duplicate content early."""

    directory = seed_root / library.directory
    if not directory.is_dir():
        raise SeedConfigurationError(f"Required public seed directory is missing: {directory}")

    files: list[SeedFile] = []
    hashes: dict[str, str] = {}
    for path in sorted(directory.rglob("*.md")):
        if not path.is_file():
            continue
        relative_path = path.relative_to(directory).as_posix()
        content = _strip_frontmatter(path.read_bytes())
        content_hash = compute_content_hash(content)
        duplicate_path = hashes.get(content_hash)
        if duplicate_path is not None:
            raise SeedConfigurationError(
                f"Seed files {duplicate_path!r} and {relative_path!r} in {library.directory!r} "
                "have identical content; source hashes must be unique within a collection."
            )
        hashes[content_hash] = relative_path
        files.append(
            SeedFile(
                relative_path=relative_path,
                content=content,
                content_hash=content_hash,
            )
        )
    return files


async def _get_or_create_public_collection(
    session: AsyncSession,
    library: SeedLibrary,
) -> tuple[Collection, bool]:
    """Return the one public collection that owns this versioned directory."""

    collection = await session.scalar(
        select(Collection).where(
            Collection.user_id.is_(None),
            Collection.kind == library.kind,
            Collection.name == library.collection_name,
        )
    )
    if collection is not None:
        if collection.scope is not CollectionScope.PUBLIC:
            raise SeedConfigurationError(
                f"Collection {library.collection_name!r} must use public scope."
            )
        return collection, False

    collection = Collection(
        user_id=None,
        kind=library.kind,
        scope=CollectionScope.PUBLIC,
        name=library.collection_name,
    )
    session.add(collection)
    await session.flush()
    return collection, True


async def _ensure_content_hash_is_available(
    session: AsyncSession,
    *,
    collection_id: UUID,
    content_hash: str,
    excluding_source_id: UUID | None,
) -> None:
    """Avoid a late unique-constraint error with a precise seed-tree explanation."""

    statement = select(Source.filename).where(
        Source.collection_id == collection_id,
        Source.content_hash == content_hash,
    )
    if excluding_source_id is not None:
        statement = statement.where(Source.id != excluding_source_id)
    existing_filename = await session.scalar(statement)
    if existing_filename is not None:
        raise SeedConfigurationError(
            f"Seed content duplicates existing source {existing_filename!r} "
            "in this public collection."
        )

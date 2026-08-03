"""Create or synchronize the version-controlled public rule and template libraries."""

import argparse
import asyncio
from pathlib import Path

from app.services.public_seed import SEED_ROOT, seed_public_libraries


async def run(seed_root: Path) -> None:
    """Synchronize public seeds in one transaction and print an auditable summary."""

    # Keep `--help` available without constructing runtime settings or database pools.
    from app.db.session import async_session_factory, engine

    async with async_session_factory() as session:
        try:
            summary = await seed_public_libraries(session, seed_root=seed_root)
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await engine.dispose()

    print(
        "Public-library seed complete: "
        f"collections created={summary.created_collections}, "
        f"sources created={summary.created_sources}, "
        f"sources updated={summary.updated_sources}, "
        f"sources unchanged={summary.unchanged_sources}"
    )


def main() -> None:
    """Parse the optional seed directory override used by local verification."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--seed-root",
        type=Path,
        default=SEED_ROOT,
        help="directory containing rules/ and templates/ (default: repository seeds/)",
    )
    arguments = parser.parse_args()
    asyncio.run(run(arguments.seed_root))


if __name__ == "__main__":
    main()

"""User persistence tests against the migrated PostgreSQL schema."""

from sqlalchemy.ext.asyncio import AsyncSession


async def test_user_can_be_committed_and_read_back(db_session: AsyncSession) -> None:
    """A service-style commit remains removable by the outer test transaction."""

    from sqlalchemy import select

    from app.db.models.user import User

    user = User(email="step9.user@example.com")
    db_session.add(user)
    await db_session.commit()

    persisted_user = await db_session.scalar(select(User).where(User.id == user.id))

    assert persisted_user is not None
    assert persisted_user.id == user.id
    assert persisted_user.email == "step9.user@example.com"
    assert persisted_user.created_at is not None

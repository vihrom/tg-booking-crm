from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from models.models import (
    Base,
)

DATABASE_URL = "sqlite+aiosqlite:///database.db"

engine = create_async_engine(DATABASE_URL, echo=True)
async_session_factory = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,
)


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

import os

from sqlalchemy import text
from sqlmodel import Session, create_engine

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://gluekettle:gluekettle@127.0.0.1:6190/gluekettle",
)
engine = create_engine(DATABASE_URL, echo=False)


def get_session() -> Session:
    return Session(engine)


def ensure_indexes() -> None:
    """同锅同刻的未作废筛网牌唯一：抢交两张同时刻牌时只入库一张。

    PostgreSQL 与 SQLite 都支持带 WHERE 的部分唯一索引及 IF NOT EXISTS。
    """

    sql = (
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_screentags_active "
        "ON screentags (kettle_id, posted_at) WHERE revoked_at IS NULL"
    )
    with engine.begin() as conn:
        conn.execute(text(sql))

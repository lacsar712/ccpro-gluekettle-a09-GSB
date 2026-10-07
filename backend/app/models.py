from datetime import datetime, timezone
from typing import ClassVar, Optional

from sqlalchemy import Index, text
from sqlmodel import Field, Relationship, SQLModel


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(SQLModel, table=True):
    __tablename__ = "users"

    id: Optional[int] = Field(default=None, primary_key=True)
    username: str = Field(unique=True, index=True)
    password_hash: str
    role: str = "worker"


class Workshop(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    alley: str = ""
    kettles: list["Kettle"] = Relationship(back_populates="workshop")


class Kettle(SQLModel, table=True):
    STATUS_COLD: ClassVar[str] = "cold"
    STATUS_BOILING: ClassVar[str] = "boiling"
    STATUS_DRAWN: ClassVar[str] = "drawn"

    id: Optional[int] = Field(default=None, primary_key=True)
    workshop_id: int = Field(foreign_key="workshop.id")
    code: str
    status: str = STATUS_COLD
    bench: int = 0
    workshop: Optional[Workshop] = Relationship(back_populates="kettles")
    cooks: list["CookLog"] = Relationship(back_populates="kettle")
    sieve_tags: list["SieveTag"] = Relationship(back_populates="kettle")


class CookLog(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    kettle_id: int = Field(foreign_key="kettle.id")
    taken_at: datetime = Field(default_factory=utcnow)
    peak_temp_c: float
    operator: str = ""
    kettle: Optional[Kettle] = Relationship(back_populates="cooks")


class SieveTag(SQLModel, table=True):
    """筛网牌：挂在某口锅上的目数角标，作废时刻可空（空 = 未作废）。"""

    __tablename__ = "sieve_tags"
    # 同一口锅、同一挂出时刻，只许一张未作废牌入库（并发抢交时第二张被唯一索引挡住）。
    __table_args__ = (
        Index(
            "uq_sieve_tags_live_hung",
            "kettle_id",
            "hung_at",
            unique=True,
            postgresql_where=text("voided_at IS NULL"),
            sqlite_where=text("voided_at IS NULL"),
        ),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    kettle_id: int = Field(foreign_key="kettle.id", index=True)
    mesh: int
    hung_at: datetime = Field(default_factory=utcnow)
    hung_by: str = ""
    voided_at: Optional[datetime] = None
    kettle: Optional[Kettle] = Relationship(back_populates="sieve_tags")

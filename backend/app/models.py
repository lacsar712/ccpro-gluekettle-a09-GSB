from datetime import datetime, timezone
from typing import ClassVar, Optional

from sqlmodel import Field, Relationship, SQLModel


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def utcnow_second() -> datetime:
    # 挂出时刻精确到秒：同秒抢交即视为同一挂出时刻
    return datetime.now(timezone.utc).replace(microsecond=0)


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
    screen_tags: list["ScreenTag"] = Relationship(back_populates="kettle")


class CookLog(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    kettle_id: int = Field(foreign_key="kettle.id")
    taken_at: datetime = Field(default_factory=utcnow)
    peak_temp_c: float
    operator: str = ""
    kettle: Optional[Kettle] = Relationship(back_populates="cooks")


class ScreenTag(SQLModel, table=True):
    """筛网牌：一口锅挂一张，挂出时刻 + 目数；作废后作废时刻非空。"""

    __tablename__ = "screentags"

    id: Optional[int] = Field(default=None, primary_key=True)
    kettle_id: int = Field(foreign_key="kettle.id", index=True)
    mesh: int
    posted_at: datetime = Field(default_factory=utcnow_second, index=True)
    posted_by: str = ""
    revoked_at: Optional[datetime] = Field(default=None, index=True)
    revoked_by: str = ""
    kettle: Optional[Kettle] = Relationship(back_populates="screen_tags")

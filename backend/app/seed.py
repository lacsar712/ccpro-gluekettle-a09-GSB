from sqlmodel import select

from app.db import get_session
from app.models import CookLog, Kettle, ScreenTag, User, Workshop, utcnow_second
from app.security import hash_password
from datetime import timedelta


def seed_demo() -> None:
    with get_session() as session:
        admin = session.exec(select(User).where(User.username == "admin")).first()
        if admin is None:
            session.add(User(username="admin", password_hash=hash_password("123456"), role="admin"))
        else:
            admin.password_hash = hash_password("123456")
            admin.role = "admin"
        worker = session.exec(select(User).where(User.username == "worker")).first()
        if worker is None:
            session.add(User(username="worker", password_hash=hash_password("123456"), role="worker"))
        else:
            worker.password_hash = hash_password("123456")
            worker.role = "worker"
        if session.exec(select(Workshop)).first():
            _seed_demo_screen(session)
            session.commit()
            return
        shop = Workshop(name="骨巷熬胶坊", alley="西市骨巷")
        session.add(shop)
        session.flush()
        layout = [
            ("锅-1", Kettle.STATUS_BOILING, 0, 96.0),
            ("锅-2", Kettle.STATUS_COLD, 1, None),
            ("锅-3", Kettle.STATUS_DRAWN, 2, 102.0),
            ("锅-4", Kettle.STATUS_BOILING, 3, 82.0),
            ("锅-5", Kettle.STATUS_COLD, 4, None),
            ("锅-6", Kettle.STATUS_DRAWN, 5, 94.0),
        ]
        for code, status, bench, peak in layout:
            kettle = Kettle(workshop_id=shop.id, code=code, status=status, bench=bench)
            session.add(kettle)
            session.flush()
            if peak is not None:
                session.add(CookLog(kettle_id=kettle.id, peak_temp_c=peak, operator="worker"))
        session.flush()
        _seed_demo_screen(session)
        session.commit()


def _seed_demo_screen(session) -> None:
    """冷锅锅-2 挂着一张 80 目未作废牌：演示改熬煮中被中文挡住。"""

    pot2 = session.exec(select(Kettle).where(Kettle.code == "锅-2")).first()
    if pot2 is None:
        return
    exists = session.exec(
        select(ScreenTag).where(
            ScreenTag.kettle_id == pot2.id,
            ScreenTag.revoked_at.is_(None),
        )
    ).first()
    if exists is None:
        session.add(
            ScreenTag(
                kettle_id=pot2.id,
                mesh=80,
                posted_by="admin",
                posted_at=utcnow_second() - timedelta(minutes=2),
            )
        )
        session.flush()

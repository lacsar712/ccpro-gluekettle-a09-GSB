from datetime import datetime, timezone

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload
from sqlmodel import SQLModel, select

from app.db import engine, ensure_indexes, get_session
from app.domain import RuleError, assert_can_set_status, latest_peak
from app.models import CookLog, Kettle, ScreenTag, User, Workshop, utcnow_second
from app.security import make_token, parse_token, verify_password
from app.seed import seed_demo


async def current_user(request: Request) -> User | None:
    header = request.headers.get("authorization", "")
    if not header.lower().startswith("bearer "):
        return None
    username = parse_token(header.split(" ", 1)[1])
    if not username:
        return None
    with get_session() as session:
        return session.exec(select(User).where(User.username == username)).first()


def require_admin(user: User | None) -> JSONResponse | None:
    if user is None:
        return JSONResponse({"detail": "未登录"}, status_code=401)
    if user.role != "admin":
        return JSONResponse({"detail": "只有管理员能挂牌或作废筛网牌"}, status_code=403)
    return None


def load_kettle(session, kettle_id: int) -> Kettle | None:
    return session.exec(
        select(Kettle)
        .where(Kettle.id == kettle_id)
        .options(selectinload(Kettle.cooks), selectinload(Kettle.screen_tags))
    ).first()


def latest_active_screen(kettle: Kettle) -> ScreenTag | None:
    """放行依据：未作废牌里挂出时刻最晚的一张；同刻取后入库的一张。"""

    active = [t for t in (kettle.screen_tags or []) if t.revoked_at is None]
    if not active:
        return None
    return max(active, key=lambda t: (t.posted_at, t.id or 0))


def screen_json(tag: ScreenTag) -> dict:
    return {
        "id": tag.id,
        "kettleId": tag.kettle_id,
        "mesh": tag.mesh,
        "postedAt": tag.posted_at.isoformat(),
        "postedBy": tag.posted_by,
        "revokedAt": tag.revoked_at.isoformat() if tag.revoked_at else None,
        "revokedBy": tag.revoked_by,
        "active": tag.revoked_at is None,
    }


def kettle_json(kettle: Kettle) -> dict:
    screen = latest_active_screen(kettle)
    return {
        "id": kettle.id,
        "code": kettle.code,
        "status": kettle.status,
        "bench": kettle.bench,
        "latestPeakC": latest_peak(kettle),
        "cookCount": len(kettle.cooks or []),
        "latestScreen": screen_json(screen) if screen else None,
    }


async def health(request: Request):
    return JSONResponse({"status": "ok", "service": "GlueKettle"})


async def login(request: Request):
    body = await request.json()
    with get_session() as session:
        user = session.exec(select(User).where(User.username == body.get("username", ""))).first()
        if user is None or not verify_password(body.get("password", ""), user.password_hash):
            return JSONResponse({"detail": "用户名或密码错误"}, status_code=401)
        return JSONResponse(
            {"access_token": make_token(user.username), "user": {"username": user.username, "role": user.role}}
        )


async def me(request: Request):
    user = await current_user(request)
    if user is None:
        return JSONResponse({"detail": "未登录"}, status_code=401)
    return JSONResponse({"username": user.username, "role": user.role})


async def board(request: Request):
    user = await current_user(request)
    if user is None:
        return JSONResponse({"detail": "未登录"}, status_code=401)
    with get_session() as session:
        shop = session.exec(select(Workshop)).first()
        if shop is None:
            return JSONResponse({"detail": "尚无熬胶坊"}, status_code=404)
        kettles = session.exec(
            select(Kettle)
            .where(Kettle.workshop_id == shop.id)
            .options(selectinload(Kettle.cooks), selectinload(Kettle.screen_tags))
        ).all()
        loaded = sorted(kettles, key=lambda k: k.bench)
        return JSONResponse(
            {"workshop": shop.name, "alley": shop.alley, "kettles": [kettle_json(k) for k in loaded]}
        )


async def add_cook(request: Request):
    user = await current_user(request)
    if user is None:
        return JSONResponse({"detail": "未登录"}, status_code=401)
    kettle_id = int(request.path_params["kettle_id"])
    body = await request.json()
    try:
        peak = float(body.get("peakTempC"))
    except (TypeError, ValueError):
        return JSONResponse({"detail": "峰值温度必须是数字"}, status_code=400)
    with get_session() as session:
        kettle = load_kettle(session, kettle_id)
        if kettle is None:
            return JSONResponse({"detail": "锅不存在"}, status_code=404)
        session.add(CookLog(kettle_id=kettle.id, peak_temp_c=peak, operator=user.username))
        session.commit()
        kettle = load_kettle(session, kettle_id)
        return JSONResponse(kettle_json(kettle))


async def set_status(request: Request):
    user = await current_user(request)
    if user is None:
        return JSONResponse({"detail": "未登录"}, status_code=401)
    kettle_id = int(request.path_params["kettle_id"])
    body = await request.json()
    with get_session() as session:
        kettle = load_kettle(session, kettle_id)
        if kettle is None:
            return JSONResponse({"detail": "锅不存在"}, status_code=404)
        try:
            assert_can_set_status(
                kettle,
                body.get("status", ""),
                active_screen=latest_active_screen(kettle),
            )
        except RuleError as exc:
            return JSONResponse({"detail": str(exc)}, status_code=400)
        kettle.status = body.get("status")
        session.add(kettle)
        session.commit()
        kettle = load_kettle(session, kettle_id)
        return JSONResponse(kettle_json(kettle))


async def list_screens(request: Request):
    user = await current_user(request)
    if user is None:
        return JSONResponse({"detail": "未登录"}, status_code=401)
    kettle_id = int(request.path_params["kettle_id"])
    with get_session() as session:
        kettle = session.exec(select(Kettle).where(Kettle.id == kettle_id)).first()
        if kettle is None:
            return JSONResponse({"detail": "锅不存在"}, status_code=404)
        tags = session.exec(
            select(ScreenTag)
            .where(ScreenTag.kettle_id == kettle_id)
            .order_by(ScreenTag.posted_at.desc(), ScreenTag.id.desc())
        ).all()
        return JSONResponse(
            {
                "kettleId": kettle_id,
                "canManage": user.role == "admin",
                "tags": [screen_json(t) for t in tags],
            }
        )


def _parse_posted_at(raw) -> datetime | None:
    if raw in (None, ""):
        return None
    try:
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    # 统一到秒，显式传入的同刻与同秒抢交都落在同一键上
    return dt.astimezone(timezone.utc).replace(microsecond=0)


async def add_screen(request: Request):
    user = await current_user(request)
    denied = require_admin(user)
    if denied is not None:
        return denied
    kettle_id = int(request.path_params["kettle_id"])
    body = await request.json()
    try:
        mesh = int(body.get("mesh"))
    except (TypeError, ValueError):
        return JSONResponse({"detail": "目数必须是整数"}, status_code=400)
    if mesh <= 0 or mesh > 1000:
        return JSONResponse({"detail": "目数超出合理范围"}, status_code=400)
    posted_at = _parse_posted_at(body.get("postedAt"))
    if body.get("postedAt") not in (None, "") and posted_at is None:
        return JSONResponse({"detail": "挂出时刻格式无法识别"}, status_code=400)
    posted_at = posted_at or utcnow_second()
    with get_session() as session:
        kettle = session.exec(select(Kettle).where(Kettle.id == kettle_id)).first()
        if kettle is None:
            return JSONResponse({"detail": "锅不存在"}, status_code=404)
        tag = ScreenTag(
            kettle_id=kettle_id,
            mesh=mesh,
            posted_at=posted_at,
            posted_by=user.username,
        )
        session.add(tag)
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            return JSONResponse(
                {"detail": "该锅已有同一挂出时刻的未作废牌，只许入库一张"},
                status_code=409,
            )
        session.refresh(tag)
        return JSONResponse(screen_json(tag), status_code=201)


async def revoke_screen(request: Request):
    user = await current_user(request)
    denied = require_admin(user)
    if denied is not None:
        return denied
    tag_id = int(request.path_params["tag_id"])
    with get_session() as session:
        tag = session.exec(select(ScreenTag).where(ScreenTag.id == tag_id)).first()
        if tag is None:
            return JSONResponse({"detail": "筛网牌不存在"}, status_code=404)
        if tag.revoked_at is not None:
            return JSONResponse({"detail": "该筛网牌已作废"}, status_code=400)
        tag.revoked_at = datetime.now(timezone.utc)
        tag.revoked_by = user.username
        session.add(tag)
        session.commit()
        session.refresh(tag)
        return JSONResponse(screen_json(tag))


def init() -> None:
    SQLModel.metadata.create_all(engine)
    ensure_indexes()
    seed_demo()


init()

app = Starlette(
    routes=[
        Route("/api/health", health),
        Route("/api/auth/login", login, methods=["POST"]),
        Route("/api/auth/me", me),
        Route("/api/board", board),
        Route("/api/kettles/{kettle_id:int}/cooks", add_cook, methods=["POST"]),
        Route("/api/kettles/{kettle_id:int}/status", set_status, methods=["POST"]),
        Route("/api/kettles/{kettle_id:int}/screens", list_screens),
        Route("/api/kettles/{kettle_id:int}/screens", add_screen, methods=["POST"]),
        Route("/api/screens/{tag_id:int}/revoke", revoke_screen, methods=["POST"]),
    ],
    middleware=[Middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])],
)

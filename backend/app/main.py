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

from app.db import engine, get_session
from app.domain import RuleError, assert_can_set_status, latest_peak, latest_sieve_tag
from app.models import CookLog, Kettle, SieveTag, User, Workshop, utcnow
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


def admin_only(user: User) -> JSONResponse | None:
    if user.role != "admin":
        return JSONResponse({"detail": "只有管理员能挂牌或作废筛网牌"}, status_code=403)
    return None


def load_kettle(session, kettle_id: int) -> Kettle | None:
    return session.exec(
        select(Kettle)
        .where(Kettle.id == kettle_id)
        .options(selectinload(Kettle.cooks), selectinload(Kettle.sieve_tags))
    ).first()


def kettle_json(kettle: Kettle) -> dict:
    tag = latest_sieve_tag(kettle)
    return {
        "id": kettle.id,
        "code": kettle.code,
        "status": kettle.status,
        "bench": kettle.bench,
        "latestPeakC": latest_peak(kettle),
        "cookCount": len(kettle.cooks or []),
        "sieveMesh": tag.mesh if tag else None,
    }


def sieve_tag_json(tag: SieveTag) -> dict:
    return {
        "id": tag.id,
        "kettleId": tag.kettle_id,
        "kettleCode": tag.kettle.code if tag.kettle else None,
        "mesh": tag.mesh,
        "hungAt": tag.hung_at.isoformat() if tag.hung_at else None,
        "hungBy": tag.hung_by,
        "voidedAt": tag.voided_at.isoformat() if tag.voided_at else None,
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
            .options(selectinload(Kettle.cooks), selectinload(Kettle.sieve_tags))
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
            assert_can_set_status(kettle, body.get("status", ""))
        except RuleError as exc:
            return JSONResponse({"detail": str(exc)}, status_code=400)
        kettle.status = body.get("status")
        session.add(kettle)
        session.commit()
        kettle = load_kettle(session, kettle_id)
        return JSONResponse(kettle_json(kettle))


async def list_sieve_tags(request: Request):
    user = await current_user(request)
    if user is None:
        return JSONResponse({"detail": "未登录"}, status_code=401)
    kettle_id = request.query_params.get("kettle_id")
    with get_session() as session:
        query = (
            select(SieveTag)
            .options(selectinload(SieveTag.kettle))
            .order_by(SieveTag.hung_at.desc(), SieveTag.id.desc())
        )
        if kettle_id:
            query = query.where(SieveTag.kettle_id == int(kettle_id))
        tags = session.exec(query).all()
        return JSONResponse({"tags": [sieve_tag_json(t) for t in tags]})


async def hang_sieve_tag(request: Request):
    user = await current_user(request)
    if user is None:
        return JSONResponse({"detail": "未登录"}, status_code=401)
    denied = admin_only(user)
    if denied is not None:
        return denied
    kettle_id = int(request.path_params["kettle_id"])
    body = await request.json()
    try:
        mesh = int(body.get("mesh"))
        if mesh <= 0:
            raise ValueError
    except (TypeError, ValueError):
        return JSONResponse({"detail": "目数必须是正整数"}, status_code=400)
    hung_at = None
    raw_hung = str(body.get("hungAt") or "").strip()
    if raw_hung:
        try:
            hung_at = datetime.fromisoformat(raw_hung)
        except ValueError:
            return JSONResponse({"detail": "挂出时刻格式不对"}, status_code=400)
        if hung_at.tzinfo is None:
            hung_at = hung_at.replace(tzinfo=timezone.utc)
    with get_session() as session:
        kettle = session.get(Kettle, kettle_id)
        if kettle is None:
            return JSONResponse({"detail": "锅不存在"}, status_code=404)
        tag = SieveTag(kettle_id=kettle.id, mesh=mesh, hung_by=user.username)
        if hung_at is not None:
            tag.hung_at = hung_at
        session.add(tag)
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            return JSONResponse(
                {"detail": "同一挂出时刻该锅已有未作废筛网牌，只许入库一张"}, status_code=409
            )
        session.refresh(tag)
        return JSONResponse(sieve_tag_json(tag), status_code=201)


async def void_sieve_tag(request: Request):
    user = await current_user(request)
    if user is None:
        return JSONResponse({"detail": "未登录"}, status_code=401)
    denied = admin_only(user)
    if denied is not None:
        return denied
    tag_id = int(request.path_params["tag_id"])
    with get_session() as session:
        tag = session.get(SieveTag, tag_id)
        if tag is None:
            return JSONResponse({"detail": "筛网牌不存在"}, status_code=404)
        if tag.voided_at is not None:
            return JSONResponse({"detail": "该筛网牌已作废"}, status_code=400)
        tag.voided_at = utcnow()
        session.add(tag)
        session.commit()
        session.refresh(tag)
        return JSONResponse(sieve_tag_json(tag))


def init() -> None:
    SQLModel.metadata.create_all(engine)
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
        Route("/api/sieve-tags", list_sieve_tags),
        Route("/api/kettles/{kettle_id:int}/sieve-tags", hang_sieve_tag, methods=["POST"]),
        Route("/api/sieve-tags/{tag_id:int}/void", void_sieve_tag, methods=["POST"]),
    ],
    middleware=[Middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])],
)

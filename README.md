# GlueKettle-01 · 骨巷熬胶坊

一排熬锅作业台。登录后是横向锅位，点锅登记煮胶峰值并改状态。前端是原生 JS，没有 React/Vue/Svelte。

## 技术栈

| 层 | 技术 |
| --- | --- |
| Web API | Starlette 路由表（不是 FastAPI Depends） |
| 结构 | SQLModel 实体 + `domain.py` 门槛 |
| 数据 | SQLModel / SQLAlchemy · psycopg2 · PostgreSQL 15 |
| 前端 | 原生 ES Module · Vite 仅打包 |
| 部署 | Docker Compose |

## 路径与端口

- 前端：http://localhost:4790
- API：http://localhost:8790
- PostgreSQL：localhost:6190

## 演示账号

`admin` / `123456`，`worker` / `123456`

## 业务规则

- 锅不可转「熬煮中」，除非**最新一张未作废筛网牌**（按挂出时刻最晚者为准）为 **40 或 60 目**；没有未作废牌同样挡住。
- 锅不可标「已出胶」，除非最近一次煮胶峰值 **≥ 90℃**——只认峰值，筛网目数不掺进来。
- 筛网牌字段：目数、挂出时刻、挂出人、作废时刻（可空）。同一口锅同一挂出时刻只许一张未作废牌入库（数据库唯一索引兜底，并发抢交第二张会被拒）。
- 挂牌、作废仅管理员；操作工进筛网角标页只读。
- 规则在 `backend/app/domain.py`；筛网角标页独立成页，可按锅筛牌，锅位条叠目数角标。

## 快速启动

```bash
cd GlueKettle/GlueKettle-01
docker compose up --build
```

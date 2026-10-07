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

- 锅不可标「已出胶」，除非最近一次煮胶峰值 **≥ 90℃**，与筛网牌无关。规则在 `backend/app/domain.py`。
- 冷锅改「熬煮中」前，该锅必须有**未作废筛网牌**，且挂出时刻最晚的一张目数为 **40 或 60**；否则中文挡住（如 80 目：`最新筛网牌为 80 目，只认 40 或 60 目，不能改熬煮中`），无牌同样挡住。
- 筛网牌字段：目数、挂出时刻、挂出人、作废时刻（可空）。放行只认未作废牌中挂出时刻最晚的一张；同锅同挂出时刻（秒级）的未作废牌有数据库部分唯一索引，抢交只入库一张（第二张 409）。
- 只有**管理员**能挂牌 / 作废；操作工进筛网专页只读（写接口 403）。

顶栏有「锅位作业台」与「筛网角标」两页；锅位条右上角叠最新有效牌的目数角标（40 绿、60 蓝、80 等红）。

### 筛网接口

| 方法 | 路径 | 权限 |
| --- | --- | --- |
| GET | `/api/kettles/{id}/screens` | 登录可读 |
| POST | `/api/kettles/{id}/screens`（`mesh`，可选 `postedAt`） | 管理员 |
| POST | `/api/screens/{tag_id}/revoke` | 管理员 |

## 快速启动

```bash
cd GlueKettle/GlueKettle-01
docker compose up --build
```

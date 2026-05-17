# AGENTS.md

AGENTS.md 的本质是限制 AI，而不是教 AI。

## Rules

- 信息不足且决策重要时，先问用户；回答保持简洁高效。
- 修改前先看相关代码和模块 `README.md`，不要凭记忆改。
- 保持 `README.md` / `README.zh-CN.md` 面向用户；工程约束放在这里。

## Architecture

- 后端代码在 `backend/src/lsl/`，遵守 `API -> Service -> Repository -> DB`。
- `api.py` 只做路由、参数、HTTP 错误映射；禁止直接访问 DB 或写核心业务。
- `service.py` 只做业务编排；禁止写 HTTP 细节、手拼 SQL、跨模块直接调用别人的 `Repo`。
- `repo.py` 只做持久化读写；禁止做业务决策或抛 `HTTPException`。
- 新 repo 直接返回 Pydantic schema。
- `core/` 禁止依赖 `modules/`。
- 外部厂商适配代码必须放在所属模块内。
- 数据库结构必须兼容 `SQLite3` 和 `PostgreSQL`。
- 新增/修改表或列时，同步更新 `deploy/initdb/001-schema.sql`；该文件是 PostgreSQL 部署的唯一权威初始化脚本，必须和 `modules/*/model.py` 保持一致。

## Commands

- 后端测试：`env PYTHONPATH=backend/src uv run pytest backend/tests`
- 指定测试：`env PYTHONPATH=backend/src uv run pytest backend/tests/test_job_service.py`
- 导入检查：`env PYTHONPATH=backend/src uv run python -c "import lsl.main; print('main import ok')"`
- 本地后端：`uv run uvicorn --app-dir backend/src lsl.main:app --reload --env-file .env`

## Do Not

- 不要把密钥、token、完整外部响应中的敏感字段写进日志。
- 不要把业务逻辑塞进 `api.py`。
- 不要让 `repo.py` 返回随意拼出的 `dict[str, Any]` 作为主要领域对象。
- 不要引入 PostgreSQL-only 的表结构默认值，除非同时处理 SQLite 兼容。
- 不要把新模块只写代码不写模块 `README.md`。
- 不要把无关文件或用户已有改动混进当前提交。

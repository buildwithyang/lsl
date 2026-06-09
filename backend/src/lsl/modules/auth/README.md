# LSL - Auth Module

Auth 模块负责用户登录，基于 Casdoor 的 OAuth2 授权码 + PKCE 流程，登录态保存在签名的 session cookie 里。

设计原则：
- 只做认证：换 token、拉 userinfo、`upsert` 本地用户、维护 session，不掺业务逻辑。
- 登录态存浏览器签名 cookie（`AUTH_SESSION_SECRET` 签名），后端不另存会话表。
- `state` / `nonce` / `code_verifier` 在授权阶段写入 session，callback 时校验，防 CSRF 并完成 PKCE。
- `UserRepository` 只读写 `auth_users` 表；OAuth 用户用 `(provider, provider_subject)` 唯一键做幂等 `upsert`。

## 登录流程

```text
GET /auth/login      -> 生成 state/nonce/code_verifier 写入 session，302 跳 Casdoor 授权页
Casdoor 登录后回跳   -> GET /auth/callback?code&state
GET /auth/callback   -> 校验 state、用 code+code_verifier 换 token、拉 userinfo、upsert 用户
                        写入 session 后 302 跳 AUTH_FRONTEND_REDIRECT_URL
```

## 当前接口

- `GET  /auth/login`：发起授权，302 跳转 Casdoor。
- `GET  /auth/callback`：授权回调，完成换 token / 建用户 / 写 session，再跳回前端。
- `GET  /auth/me`：返回当前登录用户（未登录时 `user` 为 `null`）。
- `POST /auth/logout`：清空 session。

`/me` 与 `/logout` 统一用 `ApiResponse[AuthMeData]` 包装；其它模块如需强制登录，可复用 `require_auth_user` 依赖。

## 配置（`.env`）

```env
CASDOOR_ENDPOINT=https://your-casdoor.example.com
CASDOOR_CLIENT_ID=your-client-id
CASDOOR_CLIENT_SECRET=your-client-secret
CASDOOR_REDIRECT_URI=https://your-backend/auth/callback
CASDOOR_HTTP_TIMEOUT=15
AUTH_FRONTEND_REDIRECT_URL=https://your-frontend/
AUTH_SESSION_SECRET=change-me-in-prod
```

说明：
- `CASDOOR_REDIRECT_URI` 必须和 Casdoor 应用里的 Redirect URLs 完全一致，授权和换 token 两步都用它。
- `AUTH_FRONTEND_REDIRECT_URL` 是登录成功后浏览器的最终落点，用前端实际访问地址。
- `AUTH_SESSION_SECRET` 用于签名 session cookie，生产务必替换默认值。
- 以上 Casdoor 配置缺失时，`/auth/login`、`/auth/callback` 会返回 500（`Auth is not configured`）。

## 模块结构

```text
auth/
|- api.py       # FastAPI router + require_auth_user 依赖
|- service.py   # OAuth/PKCE 流程、token 交换、userinfo 映射
|- repo.py      # auth_users 读写与 OAuth 用户 upsert
|- model.py     # ORM 映射
|- schema.py    # Pydantic schema（ApiResponse / AuthUser / AuthMeData）
```

## 建表 SQL

表结构以 `deploy/initdb/001-schema.sql` 中的 `auth_users` 为权威，与 `model.py` 保持一致：

```sql
-- 用户主表：保存 OAuth 用户的稳定标识与基础资料
CREATE TABLE IF NOT EXISTS public.auth_users (
    user_id          VARCHAR(32) PRIMARY KEY,                     -- 内部用户 ID（uuid hex）
    provider         VARCHAR(32) NOT NULL,                        -- OAuth provider，当前为 casdoor
    provider_subject VARCHAR(255) NOT NULL,                       -- provider 侧稳定 subject
    username         VARCHAR(128),                                -- provider 用户名
    display_name     VARCHAR(255),                                -- 展示名
    email            VARCHAR(255),                                -- 邮箱（可空）
    avatar_url       VARCHAR(1024),                               -- 头像 URL（可空）
    created_at       TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP, -- 创建时间
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP  -- 更新时间
);

-- (provider, provider_subject) 唯一：同一第三方账号只对应一个本地用户
CREATE UNIQUE INDEX IF NOT EXISTS uq_auth_users_provider_subject
    ON public.auth_users (provider, provider_subject);

-- 邮箱查询索引
CREATE INDEX IF NOT EXISTS idx_auth_users_email
    ON public.auth_users (email);
```

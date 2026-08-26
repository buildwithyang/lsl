# LSL - Asset Service (Object Storage Abstraction)

Asset 是一个用于对象存储上传与访问解耦的项目。

核心目标：
数据库只存 `object_key`，上传走 Presigned URL，访问统一用 `ASSET_BASE_URL + object_key`。

## 核心设计原则

- DB 保存 `object_key`(相对路径, 最核心), `category`, `entity_id`, `filename`, `content_type`, 以及其他必要字段 创建时间, 更新时间等。
- 访问域名不入库，仅通过配置控制
- 写入使用 Presigned URL（客户端直传）
- 存储实现可插拔（`fake` / `oss`，后续可扩展 `s3` / `gcs`）
- 业务层不感知云厂商 SDK

## 架构概览

```text
Client
  |- 上传: Presigned PUT URL
  |- 访问: ASSET_BASE_URL + object_key

Backend
  |- AssetService
  |- StorageProvider (Protocol)
  |- Provider Factory
  |- FastAPI API

DB
  |- object_key
```

## 项目结构

```text
backend/src/lsl/
|- main.py                # FastAPI 入口
|- core/
|  |- config.py           # 配置定义
|- modules/
   |- asset/
      |- api.py           # FastAPI router
      |- service.py       # 业务层（key / upload_url / asset_url）
      |- repo.py          # 资产查询与持久化
      |- model.py         # ORM 映射
      |- schema.py        # Pydantic schema
      |- types.py         # 协议与领域类型
      |- providers.py     # fake / oss provider 与工厂
```

## 快速开始

### 1. 安装依赖（一次）

```bash
uv sync --locked
```

### 2. 配置 `.env`

```env
STORAGE_PROVIDER=oss
OSS_REGION=cn-hangzhou
OSS_BUCKET=your-real-bucket
OSS_ACCESS_KEY_ID=your-real-ak
OSS_ACCESS_KEY_SECRET='your-real-sk'
ASSET_BASE_URL=https://your-real-bucket.oss-cn-hangzhou.aliyuncs.com
DATABASE_URL=sqlite:///./data/lsl.sqlite3
DB_POOL_MIN_SIZE=1
DB_POOL_MAX_SIZE=10
DB_POOL_TIMEOUT=30
```

说明：
- `STORAGE_PROVIDER=oss` 时，`OSS_BUCKET/OSS_ACCESS_KEY_ID/OSS_ACCESS_KEY_SECRET` 必填。
- `ASSET_BASE_URL` 用于生成读 URL，可替换为 CDN 域名。
- `DATABASE_URL` 用于 `POST /assets/complete-upload` 入库。
- 默认本地运行使用 `SQLite`；如果要接 `PostgreSQL`，把 `DATABASE_URL` 改成 `postgresql://...`，正式依赖清单已包含 PostgreSQL 驱动。

### 3. PostgreSQL 手动建表（可选）

默认本地运行会通过 SQLAlchemy 自动建表；如果你要手动初始化 PostgreSQL，可执行下面这份 SQL：

连接到 `lsl` 数据库后执行：

```sql
-- 资产主表：保存 object_key 与文件元数据，不保存完整访问域名
CREATE TABLE IF NOT EXISTS public.asset_assets (
    id                BIGSERIAL PRIMARY KEY,                      -- 内部自增主键
    object_key        TEXT NOT NULL UNIQUE,                       -- 对象存储路径（业务唯一键）
    category          VARCHAR(64) NOT NULL,                       -- 业务分类（conversation/listening 等）
    entity_id         VARCHAR(128) NOT NULL,                      -- 业务实体 ID（如 user/session）
    filename          VARCHAR(255),                               -- 原始文件名
    content_type      VARCHAR(128),                               -- MIME 类型
    file_size         BIGINT,                                     -- 文件大小（字节）
    etag              VARCHAR(128),                               -- 对象存储返回的 ETag
    storage_provider  VARCHAR(16) NOT NULL DEFAULT 'oss',         -- 存储后端类型
    upload_status     SMALLINT NOT NULL DEFAULT 0,                -- 处理状态码
    created_at        TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP, -- 创建时间
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP -- 更新时间
);

-- 按业务分类/实体查询最近上传文件
CREATE INDEX IF NOT EXISTS idx_asset_assets_category_entity_created_at
    ON public.asset_assets (category, entity_id, created_at DESC);

-- 按创建时间倒序分页
CREATE INDEX IF NOT EXISTS idx_asset_assets_created_at
    ON public.asset_assets (created_at DESC);

-- 统一更新时间函数：每次 UPDATE 自动刷新 updated_at
CREATE OR REPLACE FUNCTION public.set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- 幂等创建触发器前先删除旧触发器
DROP TRIGGER IF EXISTS trg_asset_assets_set_updated_at ON public.asset_assets;

-- 更新前触发：自动维护 updated_at 字段
CREATE TRIGGER trg_asset_assets_set_updated_at
BEFORE UPDATE ON public.asset_assets
FOR EACH ROW
EXECUTE FUNCTION public.set_updated_at();
```

状态码约定：
- `0` uploaded
- `1` transcribing
- `2` analyzing
- `3` completed
- `4` failed

### 5. 健康检查

```bash
curl "http://127.0.0.1:8000/health"
```

## 上传接口

### `POST /assets/upload-url`

请求示例：

```bash
curl -X POST "http://127.0.0.1:8000/assets/upload-url" \
  -H "Content-Type: application/json" \
  -d '{
    "category": "conversation",
    "entity_id": "test_user",
    "filename": "log.txt",
    "content_type": "text/plain"
  }'
```

返回示例：

```json
{
  "code": 0,
  "message": "successful",
  "data": {
    "object_key": "listening/test_user/xxxx.txt",
    "upload_url": "https://bucket.oss-cn-hangzhou.aliyuncs.com/...",
    "asset_url": "https://cdn-or-bucket-domain/listening/test_user/xxxx.txt"
  }
}
```

### `POST /assets/complete-upload`

前端完成 OSS 上传后，调用此接口通知后端。
当前接口会将资产信息写入当前配置的数据库（默认是本地 `SQLite`，也可切到 `PostgreSQL`）。

请求示例：

```bash
curl -X POST "http://127.0.0.1:8000/assets/complete-upload" \
  -H "Content-Type: application/json" \
  -d '{
    "object_key": "listening/test_user/xxxx.txt",
    "category": "listening",
    "entity_id": "test_user",
    "filename": "log.txt",
    "content_type": "text/plain",
    "file_size": 12345,
    "etag": "optional-etag"
  }'
```

返回示例：

```json
{
  "code": 0,
  "message": "successful",
  "data": {
    "object_key": "listening/test_user/xxxx.txt",
    "asset_url": "https://cdn-or-bucket-domain/listening/test_user/xxxx.txt",
    "status": "acknowledged"
  }
}
```

### `GET /assets`

获取文件列表（按创建时间倒序）。

请求示例：

```bash
curl "http://127.0.0.1:8000/assets?limit=20&category=conversation&entity_id=web_user"
```

返回示例：

```json
{
  "code": 0,
  "message": "successful",
  "data": {
    "items": [
      {
        "object_key": "conversation/web_user/xxxx.wav",
        "category": "conversation",
        "entity_id": "web_user",
        "filename": "lesson.wav",
        "content_type": "audio/wav",
        "file_size": 1024,
        "etag": "optional-etag",
        "upload_status": 0,
        "created_at": "2026-02-20T00:00:00+00:00",
        "asset_url": "https://cdn-or-bucket-domain/conversation/web_user/xxxx.wav"
      }
    ]
  }
}
```

## 客户端直传示例（OSS）

```bash
curl -X PUT -T /path/to/log.txt \
  -H "Content-Type: text/plain" \
  "<upload_url>"
```
## 后续扩展

- S3 / MinIO / R2 provider
- GCS provider
- CDN 私有回源
- 上传策略校验（类型/大小/key 前缀）
- 单元测试与集成测试

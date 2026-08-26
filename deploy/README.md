# Deploy

这套部署文件默认面向一台 Linux x86 服务器，使用 Docker Compose 拉起：

- `web`: 前端静态文件 + Nginx 反代
- `backend`: FastAPI
- `postgres`: PostgreSQL 16
- `redis`: Redis 7

说明：
- 应用代码默认本地开发使用 `SQLite`。
- `deploy/` 这里仍然保留 `PostgreSQL + Redis` 版本，主要用于服务器上的集中部署。

## 目录说明

```text
deploy/
├── .env.example
├── app.env.example
├── backend.Dockerfile
├── backend.requirements.txt
├── docker-compose.yml
├── initdb/
│   └── 001-schema.sql
├── nginx/
│   └── default.conf
└── web.Dockerfile
```

## 1. 准备服务器

服务器需要 Linux x86、Docker 和 Docker Compose plugin。Ubuntu 可直接安装：

```bash
sudo apt update
sudo apt install -y docker.io docker-compose-plugin git
sudo systemctl enable --now docker
```

如果服务器防火墙开启了限制，至少放行 `HTTP_PORT` 对应端口，默认是 `80`。

## 2. 拉取代码

```bash
git clone https://github.com/buildwithyang/lsl.git
cd lsl
git checkout main
```

如果你是直接把当前工作区上传到服务器，确保服务器上执行命令的位置是仓库根目录。

## 3. 配置环境变量

```bash
cd deploy
cp .env.example .env
cp app.env.example app.env
```

### 3.1 基础运行配置

先改 `deploy/.env`：

```env
HTTP_PORT=80
POSTGRES_PASSWORD=<strong-password>
```

再改 `deploy/app.env`，保证数据库密码和 `POSTGRES_PASSWORD` 一致：

```env
DATABASE_URL=postgresql://lsl_user:<strong-password>@postgres:5432/lsl
```

### 3.2 线上能力配置

配置真实 OSS，否则上传链路不可用：

```env
STORAGE_PROVIDER=oss
ASSET_BASE_URL=https://your-bucket-or-cdn-domain
OSS_REGION=cn-hangzhou
OSS_BUCKET=your-bucket
OSS_ACCESS_KEY_ID=your-access-key-id
OSS_ACCESS_KEY_SECRET=your-access-key-secret
```

配置真实语音识别：

```env
ASR_PROVIDER=volc
VOLC_API_KEY=your-volc-api-key
```

配置真实 Revision、AI Script 和 Translation：

```env
REVISION_PROVIDER=llm
REVISION_LLM_API_KEY=your-llm-api-key
REVISION_LLM_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
REVISION_LLM_MODEL=doubao-seed-2-0-pro-260215

SCRIPT_PROVIDER=llm
TRANSLATION_PROVIDER=llm
```

`SCRIPT_LLM_*` 和 `TRANSLATION_LLM_*` 留空时，会复用 `REVISION_LLM_*` 的 key、base URL 和模型。

配置真实 TTS：

```env
TTS_PROVIDER=volc
TTS_VOLC_APP_ID=your-volc-tts-app-id
TTS_VOLC_ACCESS_KEY=your-volc-tts-access-key
```

## 4. 启动

```bash
docker compose up -d --build
```

查看状态：

```bash
docker compose ps
docker compose logs -f backend
docker compose logs -f web
```

## 5. 验证

健康检查：

```bash
curl http://127.0.0.1:${HTTP_PORT:-80}/health
```

页面入口：

```text
http://<your-server-ip>:<HTTP_PORT>
```

API 入口：

```text
http://<your-server-ip>:<HTTP_PORT>/api/...
```

如果健康检查失败，先看后端日志：

```bash
docker compose logs --tail=200 backend
```

常见问题：

- `DATABASE_URL` 密码和 `deploy/.env` 里的 `POSTGRES_PASSWORD` 不一致。
- `STORAGE_PROVIDER=oss` 但 OSS bucket 或 AK/SK 没配。
- `SCRIPT_PROVIDER=llm` 但没有配置可用的 LLM key。
- `ASR_PROVIDER=volc` 或 `TTS_PROVIDER=volc` 但火山凭证没配。
- 服务器安全组或防火墙没有放行 `HTTP_PORT`。

## 6. 数据库初始化

`postgres` 容器第一次启动时，会自动执行：

- `deploy/initdb/001-schema.sql`

如果你已经有旧的 `postgres-data` volume，初始化脚本不会自动再跑。需要手动执行：

```bash
cd deploy
docker compose exec -T postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" < initdb/001-schema.sql
```

已有小表结构需要增量更新时，执行对应的 PostgreSQL migration：

```bash
cd deploy
docker compose exec -T postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" < initdb/<migration>.sql
```

当前仓库只有 `001-schema.sql`，新部署不需要额外执行 migration。

## 7. 常用操作

重建服务：

```bash
cd deploy
docker compose up -d --build backend web
```

停止：

```bash
cd deploy
docker compose down
```

停止并删卷：

```bash
cd deploy
docker compose down -v
```

查看日志：

```bash
cd deploy
docker compose logs -f backend
docker compose logs -f web
```

## 8. 说明

- 前端通过同域名 `/api` 访问后端，避免额外处理 CORS。
- 后端固定单 worker，这和当前项目里 `revision` / `tts` 使用进程内线程池的实现更匹配。
- 这套文件默认在服务器上直接构建镜像。如果你在 Apple Silicon 本地构建后再推到 Linux x86 服务器，需要额外指定 `linux/amd64`。
- 当前 compose 只提供 HTTP。正式公网发布建议在外层接云厂商 HTTPS、Cloudflare、Caddy 或 Nginx TLS。
- `docker compose down -v` 会删除 PostgreSQL 和 Redis 数据卷，线上不要随便执行。

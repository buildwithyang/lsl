# 播客（Podcast）——从网页生成对话脚本

> Design doc · 2026-05-15

## 1. 范围

### 做什么

在 LSL 增加第三种 session 来源：网页 URL。用户给一个网址，系统抓取并抽取正文，喂给现有 `script` 生成器，产出带 CUE 的对话脚本。下游 revision / translation / TTS 全部复用现有管线。

用户面叫"播客（Podcast）"。后端模块叫 `material`。

### 不做什么（明确剔除）

- 不做 monologue / 文章式输出（v1 只生成对话）
- 不做 JS 渲染抓取 / 无头浏览器（v1 只支持静态 HTML）
- 不做 URL 缓存 / 历史记录（每次重新抓）
- 不做内容审核 / 版权检查
- 不做 PDF / YouTube / RSS 等其他来源（模块结构留接口，将来扩展）
- 应用层不做 SSRF / IP 黑名单 / 鉴权 / 速率限制——线上由网关处理

### 成功标准

- 用户在 CreateSession 选"播客"模式 → 填 URL + 必要参数 → 提交后看到一个生成中的 session
- 对话生成完毕进入 revise / TTS 流程，体验与现有 AI script 路径一致
- GitHub README、Wikipedia、典型博客 / 新闻页都能成功抽取并生成

## 2. 用户面流程（前端）

`CreateSession` 当前两个 Mode tab：`audio` / `ai_script`。新增第三个 `podcast`。

### Mode 改动

- `frontend/src/pages/CreateSession.tsx`：`mode` 类型扩展为 `'audio' | 'ai_script' | 'podcast'`
- i18n 文案加"播客"标签（中英双语）

### Podcast 表单字段

按从上到下的优先级：

1. **URL**（必填）—— placeholder 给示例（"粘贴一个网页地址，例如 `https://en.wikipedia.org/wiki/Cat`"）
2. **目标语言** target_language（必填，下拉）—— 复用现有 AI script 的下拉选项
3. **CUE 语言** cue_language（可选）—— **默认 = UI language**（前端传当前 UI 语言）
4. **可选指引** prompt（textarea，可选）—— "比如：用初学者的口吻，重点讲实用例子"
5. **难度** difficulty / **轮数** turn_count / **必含短语** must_include / **CUE 风格** cue_style —— 折叠在"高级选项"里
6. **标题 / 描述**：可选，若空则后端用网页 `<title>` 自动生成

### 提交行为

- 前端 POST `/materials/generate-session`
- 立即返回 `session + material_generation + job`，路由跳到 session 详情页（与现有 AI script 一致）
- Session 详情 / Revise 等待态复用现有 preview 显示组件
- 阶段提示新增 `extracting`（"正在抓取网页…"），之后切到 `planning` / `generating`

### 错误反馈

- URL 校验失败 / 必填缺失 → 表单内联报错，不提交
- 后端抓取失败 / 抽取为空 → 在 session 详情 / job 状态里显示原因（与现有 AI script 失败展示一致）

### 顺带统一改动

`cue_language` 默认值**从** "跟随 target_language" **改为** "= UI language"。改动覆盖：

- `ai_script` 现有路径（`/scripts/generate-session`）
- `podcast` 新路径

前端在两个表单都传当前 UI language 作为 `cue_language` 默认值。后端依旧保留"未传则跟随 target_language"作为最终兜底，但实际默认前端会一直传。

## 3. 后端模块结构（`material`）

按 `API → Service → Repository → DB` 约定，新模块布局：

```text
backend/src/lsl/modules/material/
├── __init__.py
├── README.md
├── api.py         # 路由 + HTTP 入口（禁止访问 DB）
├── service.py     # 编排：抽取 → 落 generation/job → 触发 script 生成
├── repo.py        # 只管持久化（material_generation 记录）
├── schema.py      # SQLAlchemy 表
├── model.py       # Pydantic 请求/响应 / 内部 dataclass
├── types.py       # 枚举（SourceType, MaterialStatus）
├── extractor/
│   ├── __init__.py
│   ├── base.py    # SourceExtractor 接口 + ExtractedContent
│   ├── factory.py # 根据 source.type 选 extractor
│   └── webpage.py # WebpageExtractor（trafilatura 实现）
└── job.py         # script_from_material job 的执行入口
```

### 核心接口

```python
@dataclass
class ExtractedContent:
    title: str | None
    main_text: str
    canonical_url: str | None
    meta: dict[str, Any]  # 备用扩展字段（作者、发布时间、语言等）

class SourceExtractor(Protocol):
    source_type: ClassVar[SourceType]

    def extract(self, payload: SourceExtractionInput) -> ExtractedContent: ...
```

`SourceExtractionInput` 是 discriminated union（`{type: "webpage", url: "..."}`），未来加 PDF 就是 `{type: "pdf", file_id: "..."}` 等。

### v1 唯一实现 `WebpageExtractor`

- 用 `trafilatura.fetch_url()` + `trafilatura.extract()`，内置 readability + 编码识别 + 主内容提取
- 失败回退：若返回空，二次尝试 `trafilatura.bare_extraction()`
- 输出 `title` 和正文，组装为 `ExtractedContent`

### 新依赖

- `trafilatura`（纯 Python，被 Common Crawl 等使用）
- 加到 `pyproject.toml`
- README 里更新 `uv pip install` 命令

### Job 类型

新增 `script_from_material`，由 `material/job.py` 注册到现有 job runner。Job 内三阶段：

1. `extracting` —— 调 extractor 抽取内容
2. `planning` + `generating` —— 直接复用现有 `script.generator`（import 调用，不复制代码）

### 数据库 · 新表 `material_generation`

字段：

- `id` PK
- `session_id` FK
- `source_type` TEXT（v1 只有 `"webpage"`）
- `source_payload_json` TEXT（保存原始输入，例如 URL）
- `extracted_title` TEXT NULL
- `extracted_text` TEXT NULL
- `extracted_meta_json` TEXT NULL
- `script_generation_id` FK NULL（指向后续 `script_generation` 记录）
- `status` TEXT（pending / extracting / extracted / completed / failed）
- `error_message` TEXT NULL
- `created_at` / `updated_at` TIMESTAMP

兼容 SQLite + PostgreSQL（按 AGENTS.md 要求，不引入仅 PostgreSQL 的默认值）。

### `script_generation` 表小改

- 新增可空列：`material_generation_id` FK NULL
- 来自网页路径的 script_generation 填这个字段；纯 AI script 路径继续为 NULL

### 模块边界

- `material` 可 import `script` 的 service（沿用 `script` 调 `session` / `transcript` 的现有方式）
- `core/` 不依赖 `material/`
- 非 `api.py` 文件不出现 HTTP 细节

## 4. 数据流（端到端时序）

### 同步阶段（毫秒级）

```text
Frontend            material.api        material.service     script.service        job runner
   │ POST /materials/    │                      │                   │                    │
   │ generate-session    │                      │                   │                    │
   ├────────────────────▶│                      │                   │                    │
   │                     │ create_from_url(req) │                   │                    │
   │                     ├─────────────────────▶│                   │                    │
   │                     │                      │ 1. URL 校验       │                    │
   │                     │                      │ 2. 创建 text      │                    │
   │                     │                      │    session        │                    │
   │                     │                      │    (f_type=2)     │                    │
   │                     │                      │ 3. 创建           │                    │
   │                     │                      │   material_       │                    │
   │                     │                      │   generation      │                    │
   │                     │                      │   (status=pending)│                    │
   │                     │                      │ 4. enqueue        │                    │
   │                     │                      │   script_from_    │                    │
   │                     │                      │   material job ──────────────────────▶ │
   │                     │ {session,            │                   │                    │
   │                     │  material_generation,│                   │                    │
   │                     │  job}                │                   │                    │
   │◀────────────────────┤                      │                   │                    │
```

API 立刻返回三件套，前端跳转 session 详情。

### 异步阶段（Job runner 内部）

```text
Phase 1 · extracting
  - material.service.extract_content(material_generation_id)
    → WebpageExtractor.extract({type: "webpage", url})
    → 写 extracted_title / extracted_text / extracted_meta_json
    → material_generation.status = "extracted"
    → job.progress 更新

Phase 2 · 调起 script 生成
  - material.service 调 script.service.start_generation_from_material(
      material_generation_id,
      extracted_content,
      script_options,
    )
  - script 模块创建 script_generation 记录
  - script_generation.material_generation_id ← material_generation.id
  - material_generation.script_generation_id ← script_generation.id

Phase 3 · planning + generating
  - 完全复用现有 script 流程:
    - 长内容 (turn > 16) 走章节规划，写 plan_sections_json
    - 逐轮生成,写 preview_items_json
    - 完成后写 transcript (source_type="ai_script") + revision (completed)
  - job 全程更新 preview
```

### 关键点

- 抽取出的网页正文以 prompt context 注入 script generator。具体注入方式为 prompt engineering 细节：service 将 `extracted_content.title` + `extracted_content.main_text` + 用户的 steering `prompt` 组合传给 generator。
- `transcript.source_type` 继续是 `"ai_script"`，**不新增枚举值**。`transcript.source_entity_id` 指向 `script_generation.id`（保持现有约定）。从 transcript 到 material 的追溯：`transcript → script_generation → material_generation → URL`。
- 长正文截断：v1 上限 50,000 字符。超过则取**前 45K 字符 + 末尾 5K 字符**拼接（合计 50K，保留开头与结论段），`meta.truncated=True`。两段之间插入一行占位符如 `\n\n[... omitted ...]\n\n`，标记位置但不计入 50K 总数（占位符长度极小）。

### 前端轮询体验

- Session 详情 / Revise 等待态轮询 `GET /materials/generations/{id}` 或现有 `GET /jobs/{id}`
- 阶段：`extracting` → `planning`（可选）→ `generating` → completed
- preview 接口在 `material_generation.status="extracted"` 后通过 `script_generation_id` 复用 `GET /scripts/generations/{id}/preview`

## 5. API 契约

### `POST /materials/generate-session`

请求体：

```json
{
  "source": {
    "type": "webpage",
    "url": "https://en.wikipedia.org/wiki/Domestic_cat"
  },
  "target_language": "en-US",
  "cue_language": "zh-CN",
  "prompt": "用初学者口吻，重点讲日常照护",
  "turn_count": 12,
  "speaker_count": 2,
  "difficulty": "intermediate",
  "cue_style": "自然口语、便于 TTS 演绎",
  "must_include": ["litter box", "vet"],
  "title": null,
  "description": null
}
```

字段类型（Pydantic）：

```python
SourceInput = Annotated[
    Union[WebpageSource],
    Field(discriminator="type"),
]

class WebpageSource(BaseModel):
    type: Literal["webpage"]
    url: HttpUrl
```

URL 必须是 http/https（Pydantic 校验）。

### 返回体

```json
{
  "session": { /* 现有 Session schema */ },
  "material_generation": {
    "id": "mat_xxx",
    "source_type": "webpage",
    "source_payload": { "url": "..." },
    "status": "pending",
    "extracted_title": null,
    "script_generation_id": null,
    "created_at": "..."
  },
  "job": { /* 现有 Job schema, job_type="script_from_material" */ }
}
```

### `GET /materials/generations/{id}`

返回 `material_generation` + 关联的 `script_generation`（若已创建）+ extracted_title 等。前端轮询用。

### Preview 接口

直接复用现有 `GET /scripts/generations/{script_generation_id}/preview`。前端先轮询 `/materials/generations/{id}` 拿到 `script_generation_id`，再查 preview。

### 错误码

| 码  | 场景                                                     |
| --- | -------------------------------------------------------- |
| 400 | URL 格式非法 / 协议非 http(s) / 必填缺失                 |
| 404 | GET 不存在的 generation id                               |
| 422 | 抽取出的正文为空 / 过短                                  |
| 502 | 抓取超时 / 抓取返回非 2xx（在 job error_message 中展示） |

### 模块边界

- `/scripts/generate-session` **不动**
- `script` 模块新暴露一个 service 级方法 `start_generation_from_material(...)` 给 `material` 调用，**不开新 HTTP 路由**

## 6. 错误处理 & 失败场景

### 同步阶段（API 直接拒绝）

- URL 格式非法 / 协议不是 http(s) → 400
- target_language 缺失 → 400

（SSRF 防护、IP 黑名单、DNS 重绑定防护、速率限制、鉴权——全部由线上网关处理，应用层不做。）

### 异步阶段（Job 失败，session 保留）

| 失败点          | 触发条件                                  | 处理                                                                      |
| --------------- | ----------------------------------------- | ------------------------------------------------------------------------- |
| 抓取超时        | HTTP 请求 > 15s                           | status=failed，error_message="抓取超时"                                   |
| HTTP 非 2xx     | 返回 4xx/5xx                              | status=failed，error_message 含状态码                                     |
| Body 过大       | 响应 > 5MB                                | 抓取截断，meta.body_truncated=true，继续抽取                              |
| 非 HTML 内容    | content-type 不是 text/html 或 text/plain | status=failed，error_message="不支持的内容类型: <type>"                   |
| 无可读正文      | 抽取出文本 < 200 字符                     | status=failed，error_message="未抽取到可读正文"                           |
| 正文过长        | > 50,000 字符                             | 截断为 50K（前 45K + 末 5K，中间放占位符），meta.truncated=true，不算失败 |
| script 生成失败 | 下游 LLM 报错                             | material_generation.status=failed，error 透传，session 保留               |

### 关键决策

- **失败时 session 保留**（不删除）。用户能看到失败原因、决定是否重新提交。和 AI script 失败语义一致。
- **不自动重试**。抓取 / 抽取 / 生成失败均不重试，由用户手动重新提交。
- `material_generation` 是失败排查的真相之源——存有 URL、错误信息、抽取出的内容（如果有）。

### 程序内部保护（非安全防护）

- 抓取超时 15s
- Body 上限 5MB
- 正文上限 50,000 字符
- 这些为 OOM / 死循环防护，与安全无关；安全由网关层负责

### 日志

- 不打印完整网页正文
- URL 可以打印（公开信息）
- 错误信息记录但不附带请求 body 中的敏感字段（遵循 AGENTS.md 规则）

## 7. 测试

### 单元测试（不打外部网络）

- `test_webpage_extractor.py`：
  - 标准博客页 HTML fixture → 干净正文 + 标题
  - GitHub README 风格页面 → 渲染后的内容
  - 几乎全是导航栏的页面 → 空正文（让 service 标记失败）
  - 编码异常（UTF-8 / GBK 混合）→ 不崩
  - 超长正文 → 截断 + meta.truncated=true
- `test_extractor_factory.py`：source.type 分发正确，未知类型抛 `ValueError`

### Service 测试（用 fake extractor + fake script provider）

- `test_material_service.py`：
  - `create_from_url` 同步路径：创建三件套
  - extractor 成功 → 触发 `script.service.start_generation_from_material` → 完成全流程
  - extractor 抛异常 → status=failed，错误透传
  - script 生成失败 → status=failed，session 保留
  - 抽取正文 < 200 → status=failed

### API 测试（TestClient）

- `test_material_api.py`：
  - POST 合法请求 → 200 + 三件套
  - URL 非法 → 400
  - 缺 target_language → 400
  - GET `/materials/generations/{id}` → 当前 status / extracted_title / script_generation_id
  - GET 不存在的 id → 404

### Job 测试

- `test_material_job.py`：
  - 注入 fake extractor + fake script provider，端到端跑 job
  - 各阶段 status 转换正确：pending → extracting → extracted → completed
  - 各阶段失败下 status 与 error_message 正确

### 集成测试（可选，标记 slow/network）

- 1-2 个公开稳定 URL（如 `https://example.com`、一个 GitHub README）做 smoke
- 默认不在 CI 跑，开发本地手动 verify

### Fake provider

- 通过 extractor 注入机制提供 `FakeWebpageExtractor`，无需新 env 变量
- 返回固定 `ExtractedContent`，便于联调

### Verify 命令

- 后端测试：`env PYTHONPATH=backend/src uv run pytest backend/tests`
- 导入检查：`env PYTHONPATH=backend/src uv run python -c "import lsl.main; print('main import ok')"`

## 8. 配置

新增 env（按现有模块约定）：

```env
# Material / Webpage extraction
MATERIAL_WEBPAGE_TIMEOUT_SECONDS=15
MATERIAL_WEBPAGE_MAX_BODY_BYTES=5242880   # 5 MB
MATERIAL_EXTRACTED_TEXT_MAX_CHARS=50000
```

无外部 API key（trafilatura 在本机运行）。Provider 模式按需：不引入新的 `MATERIAL_PROVIDER` env，extractor 注入靠工厂；测试通过 DI 替换 fake。

## 9. 后续扩展（不在 v1）

- 新 extractor：PDF、YouTube 字幕、RSS、Twitter/X 单推、Notion 公开页等
- URL 内容缓存（按 URL + content-hash）
- 自动重试 + 指数退避
- 用户级速率限制（依赖未来的用户系统）
- monologue / 文章式输出形态
- 已生成播客的"播客库"页面（按 source URL 聚合查看）

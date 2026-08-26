# LSL

[English](README.md)

把你自己的录音，或者 AI 按需求生成的脚本，变成一套真正贴合你目标的听力素材。

## 愿景

LSL 让每一个表达需求都被听见，也让语言学习回到真实场景，服务每个人具体的表达目标。

## LSL 是什么

LSL 是一个以 `CUE` 为核心生成对话的软件。这里的 `CUE` 指的是提示、信号和线索，用来引导对话如何生成、如何表达。例如：`[英语面试场景，候选人自然自信]` 就是一个 `CUE`，它会影响接下来生成的对话内容和说话方式。

LSL 的宗旨是：学习语言应该是 `listening -> speak -> listening`。先通过听输入语言，再尝试表达，然后带着更明确的问题回到听力训练里。

人在学习语言时，通常会对和自己生活相关的内容更感兴趣。例如你明天要参加一个英语面试，就可以用 LSL 根据你的背景生成一段面试对话，用它来练习听力，也练习表达。

你可以给内容加上明确的 `CUE`，例如说话场景、情绪、态度、关系、语气和节奏，让同一段内容更贴近你真正想练的听力场景。

素材来源有两种：

- 你自己的真实录音素材
- AI 根据你的需求生成的练习脚本

无论素材来自真实录音还是 AI 脚本，LSL 都会把它整理成可收听、可复盘、可继续练习的内容，而不是只给你一段一次性的文本或音频。

## 这对用户有什么价值

- 你不用再被动找现成听力素材，可以直接围绕自己要练的场景定制内容。例如你在去运营商那里办理套餐的之前可以先生成一个听力素材进行联系。
- 你自己的录音不会只停在“转写完成”这一步，AI 会对你的口语输出给出分数和者建议。可以继 revise 给出改写之后的脚本,然后生成新的听力材料。
- 如果你手里没有合适素材，可以直接让 AI 按场景、难度、轮次和关键词生成带 `CUE` 的练习脚本。
- `CUE` 直接写在句子里，控制力更细，不用把所有要求都塞进一大段抽象提示词里。

## 当前能做什么

- 上传语音文件（`mp3`、`wav`、`m4a`）并异步转写
- 手动创建文本 Session，或者根据提示词生成带 `CUE` 的 AI 对话脚本
- 对比原句和优化句，支持打分和草稿保存
- 在前端把带 `CUE` 的脚本作为单一字符串直接编辑
- 生成可直接进入 revise、听力、翻译和 TTS 链路的脚本数据
- 为 transcript 和 revision item 生成当前 UI 语言的译文，并支持异步状态、编辑后过期检测和重试
- 通过 TTS 生成完整听力音频，也可以预览单条 revision item
- 用统一 Job 基础设施承载 ASR、AI 脚本生成、Revision、Translation 和 TTS 的异步生命周期

## 一条典型练习链路

1. 先创建一个 Session。
2. 选择素材来源：1）上传一段真实录音；2）根据要求生成脚本，例如场景、关键内容、人员角色。
3. 如果是录音，ASR 生成 transcript；如果是脚本，LLM 生成带 `CUE` 的对话内容。
4. Revision 把内容转成更适合学习和复盘的表达。
5. Translation 可以在 Session Detail、Revise 和 Listening 页面提供当前 UI 语言的辅助译文，但不改变原始脚本。
6. TTS 把修订后的 `CUE` 脚本转成音频，用于反复听和反复说的训练。

## CUE 为什么强大

在 LSL 里，脚本不是纯文本，而是“正文 + 内嵌 `CUE`”的单一可编辑字符串。

- `CUE` 统一写成 `[...]`
- `CUE` 属于脚本本身，不拆成独立字段，所以编辑、预览、合成时看到的是同一份内容
- 你可以只改 `CUE`，不改正文，就快速做出不同风格的听力版本
- 前端编辑器可以直接高亮 `CUE`，修改时更直观
- 下游 TTS 可以先提取 `CUE`，再剥离出最终朗读正文，让“怎么说”和“说什么”同时被保留下来

`CUE` 的强大之处，不是多了一个标签，而是让脚本从“只有文字”变成“文字 + 表达方式”的组合。这样生成出来的素材更接近真实对话，也更适合做模仿、跟读和听感训练。

示例：

```text
[语气平稳、就事论事地回应] Interesting, innit?
[比较随意地附和] Yeah, right.
```

## 当前实现范围

- 已完成：对象存储上传模块（Asset Module）
- 已完成：通用异步 Job 模块（生命周期、状态查询、handler 分发）
- 已完成：Transcript 模块（统一 utterance stream）
- 已完成：ASR 模块（通过 Job 产出 transcript）
- 已完成：会话管理模块（Session Module，已支持录音 / 文本类型建模）
- 已完成：Revision 模块（utterance 级 revise、打分、草稿保存）
- 已完成：AI CUE 脚本生成（生成文本 Session + synthetic transcript + completed revision）
- 已完成：Translation 模块（transcript / revision 译文、异步生成、过期检测）
- 已完成：TTS 模块（TTS 设置、整段合成、单条预览、合成时间线）
- 已完成：模块化后端结构（`core` + `modules`）
- 尚未完成：鉴权

模块设计文档：

- `backend/src/lsl/modules/asset/README.md`
- `backend/src/lsl/modules/job/README.md`
- `backend/src/lsl/modules/transcript/README.md`
- `backend/src/lsl/modules/asr/README.md`
- `backend/src/lsl/modules/script/README.md`
- `backend/src/lsl/modules/session/README.md`
- `backend/src/lsl/modules/revision/README.md`
- `backend/src/lsl/modules/translation/`
- `backend/src/lsl/modules/tts/README.md`

## TODO

- [ ] 听写模式：可以边听边默写
- [ ] 相同说话人连续多句合并成一段，降低阅读碎片感
- [ ] 用户体系：登录、身份隔离、个人练习记录
- [ ] 对接 OpenAI API

## 总体架构（Web First）

```text
[ Web Frontend ]
  - 创建 Session（录音 / 文本）
  - 文件上传
  - CUE 脚本生成与编辑（高亮输入）
  - Job 管理（上传后异步转写、脚本生成、revision、translation、TTS）
  - 转写、修订和译文展示（Diff / 编辑 / 播放）
  - 听力 / TTS 链路

        v

[ Thin Backend ]
  - 文件服务（预签名上传）
  - Job 生命周期管理
  - Session 管理
  - Transcript / Revision / Translation 持久化
  - ASR / LLM / Translation / TTS 领域调度
  - 鉴权

        v

[ External Services ]
  - 音频存储（S3、OSS）
  - ASR / TTS 服务
  - LLM / 翻译服务
```

## 本地启动（当前后端原型）

### 1. 安装依赖

根目录的 `pyproject.toml` 是后端依赖的唯一来源，`uv.lock` 锁定本地和 Docker 使用的具体版本：

```bash
uv sync --locked
```

说明：

- `json-repair` 用于修复 revision 流程里大模型偶发返回的非严格 JSON。
- 本地开发默认已经切到 `SQLite`，不再要求先起 `PostgreSQL`。
- 部署使用同一份锁文件，因此 PostgreSQL 运行时依赖也已包含在正式清单里。
- `trafilatura` 用于把任意 HTML 网页抽取出干净的正文，是播客功能的基础依赖。
- 新增或更新后端依赖使用 `uv add <package>`，不要再维护独立的 requirements 文件。

### 2. 配置 `.env`

下面的示例按后端 `Settings` 分组，并列出真实 provider 会用到的变量。只做本地冒烟测试时可以使用 `fake` / `noop` provider；有真实凭证后再切到 `oss`、`volc` 或 `llm`。

```env
# 基本配置
DATABASE_URL=sqlite:///./data/lsl.sqlite3
DB_POOL_MIN_SIZE=1
DB_POOL_MAX_SIZE=10
DB_POOL_TIMEOUT=30
JOB_RUNNER_ENABLED=true
JOB_RUNNER_INTERVAL_SECONDS=1
JOB_RUNNER_BATCH_SIZE=10
JOB_RUNNER_MAX_WORKERS=4

# 文件存储
STORAGE_PROVIDER=oss
ASSET_BASE_URL=https://your-bucket.oss-cn-hangzhou.aliyuncs.com
ASSET_PUT_TIMEOUT=120
OSS_REGION=cn-hangzhou
OSS_BUCKET=your-bucket
OSS_ACCESS_KEY_ID=your-access-key-id
OSS_ACCESS_KEY_SECRET=your-access-key-secret

# ASR
ASR_PROVIDER=volc
VOLC_API_KEY=your-volc-api-key
VOLC_RESOURCE_ID=volc.seedasr.auc
VOLC_SUBMIT_URL=https://openspeech.bytedance.com/api/v3/auc/bigmodel/submit
VOLC_QUERY_URL=https://openspeech.bytedance.com/api/v3/auc/bigmodel/query
VOLC_MODEL_NAME=bigmodel
VOLC_UID=lsl_user
VOLC_HTTP_TIMEOUT=60

# Revision / LLM
REVISION_PROVIDER=fake
REVISION_LLM_API_KEY=
REVISION_LLM_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
REVISION_LLM_MODEL=doubao-1-5-pro-32k-250115
REVISION_LLM_HTTP_TIMEOUT=60
REVISION_LLM_DEBUG_FILE=

# AI Script / LLM
SCRIPT_PROVIDER=llm
SCRIPT_LLM_API_KEY=
SCRIPT_LLM_BASE_URL=
SCRIPT_LLM_MODEL=
SCRIPT_LLM_HTTP_TIMEOUT=60

# Translation / LLM
TRANSLATION_PROVIDER=fake
TRANSLATION_LLM_API_KEY=
TRANSLATION_LLM_BASE_URL=
TRANSLATION_LLM_MODEL=
TRANSLATION_LLM_HTTP_TIMEOUT=60
TRANSLATION_DEFAULT_TARGET_LANGUAGE=zh-CN

# TTS
TTS_PROVIDER=fake
TTS_REDIS_URL=redis://127.0.0.1:6379/0
TTS_CACHE_TTL_SECONDS=7200
TTS_VOLC_APP_ID=
TTS_VOLC_ACCESS_KEY=
TTS_VOLC_RESOURCE_ID=seed-tts-2.0
TTS_VOLC_URL=https://openspeech.bytedance.com/api/v3/tts/unidirectional
TTS_VOLC_HTTP_TIMEOUT=60
TTS_DEFAULT_FORMAT=mp3
TTS_DEFAULT_EMOTION_SCALE=4.0
TTS_DEFAULT_SPEECH_RATE=0.0
TTS_DEFAULT_LOUDNESS_RATE=0.0
```

如果你要使用 `PostgreSQL`，把 `DATABASE_URL` 改成：

```env
DATABASE_URL=postgresql://<user>:<password>@<host>:5432/lsl
```

部署到 `PostgreSQL` 时，请先按当前最新的建表 SQL 初始化数据库。

### 3. 启动服务（一键）

`./dev-start` 是一键启动脚本。不带参数时，它会把开发用域名指向本机局域网
IP（写入 `/etc/hosts`，可能会提示输入 `sudo` 密码），在前端依赖缺失时自动安装，
然后同时启动后端和前端。按 `Ctrl-C` 可一并停止。

```bash
./dev-start
```

其他命令：

```bash
./dev-start backend     # 写入 hosts + 仅启动后端
./dev-start frontend    # 写入 hosts + 仅启动前端
./dev-start apply       # 仅更新 /etc/hosts 记录
./dev-start show        # 查看当前 hosts 记录
./dev-start clear       # 移除 hosts 记录
```

域名（`dev.buildwithyang.com`）、端口（`8000` / `3000`）和网卡（`en0`）可分别通过
`DEV_HOST_NAME`、`DEV_BACKEND_PORT`、`DEV_FRONTEND_PORT`、`DEV_HOST_INTERFACE`
环境变量覆盖。运行 `./dev-start --help` 查看详情。

如果只想手动启动后端、不使用该脚本：

```bash
uv run uvicorn --app-dir backend/src lsl.main:app --reload --env-file .env
```
## 后端目录

```text
backend/
|
|- main.py
|
|- core/
|  |- db.py
|  |- config.py
|  `- logger.py
|
`- modules/
   |- asset/
   |- job/
   |- transcript/
   |- asr/
   |- session/
   |- revision/
   |- script/
   |- translation/
   `- tts/
```

当前仓库实际采用 `src layout`，实际代码位于 `backend/src/lsl/`。

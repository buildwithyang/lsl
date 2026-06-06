# LSL - Material Module

Material 模块负责把外部来源（v1 仅支持网页 URL）同步抽取为正文，并把用户确认的内容交给 `script` 模块生成对话脚本。用户面叫"播客（Podcast）"。

模块本身不写数据库——只暴露两个同步接口。所有持久化都落在下游 `session` + `script_generation`。

## 接口

### `POST /materials/extract`

同步抽取网页正文，立即返回给前端展示，不落库。

请求体：

```json
{
  "source": {"type": "webpage", "url": "https://en.wikipedia.org/wiki/Domestic_cat"}
}
```

响应（`ApiResponse[ExtractedContentData]`）：

```json
{
  "code": 0,
  "message": "successful",
  "data": {
    "title": "Domestic cat - Wikipedia",
    "main_text": "The domestic cat ...",
    "canonical_url": "https://en.wikipedia.org/wiki/Domestic_cat",
    "truncated": false,
    "char_count": 12345
  }
}
```

正文 `< 200` 字符即视为抽取失败，返回 400 `EXTRACTION_EMPTY` 语义。

### `POST /materials/create-session`

把前端用户在预览页确认后的正文 + 表单参数转交 `script_service.generate_session(...)`，一次性创建文本 session + script_generation + AI 脚本生成 job。

请求体携带前一步拿到的 `extracted_title` / `extracted_text`，以及播客设置（`turn_count` / `speaker_count` 等）。

`source` 是 discriminated union（`source.type` 当前必须是 `"webpage"`）；未来扩展加 PDF / YouTube 等只需新增 extractor + 新的 `type` 值。

## Prompt 组装

`MaterialService._build_prompt` 把以下信息拼成 script 模块的 `prompt`：

1. `Webpage title: ...`
2. `Source URL: ...`
3. 固定指令：生成两人播客对话
4. 用户额外 steering（可选）
5. `Webpage content:` + 正文

之后完全走现有 AI 脚本生成链路（plan → progressive generation → transcript → revision）。

## 失败语义

| 失败点 | HTTP 状态 |
|---|---|
| 抓取超时 / 失败 | 500 |
| 抽取正文 < 200 字符 | 400 |
| 下游 script 生成失败 | 由 `script` 模块上报 job 失败 |

`/extract` 不入库——失败后用户重试即可，不留痕迹。

## 安全

应用层只做最小校验（URL 格式、http/https 协议、超时 / 响应体积上限）。SSRF / IP 黑名单 / 鉴权 / 速率限制由线上网关层处理。

## 配置

```env
MATERIAL_WEBPAGE_TIMEOUT_SECONDS=15
MATERIAL_WEBPAGE_MAX_BODY_BYTES=5242880
MATERIAL_EXTRACTED_TEXT_MAX_CHARS=50000
```

依赖 `trafilatura`（纯 Python，本机运行，无 API key）。

## 与 transcript / script 的边界

- `transcript.source_type` 保持 `"ai_script"`，**不引入新枚举**。
- material 模块不再持久化，因此没有反向追溯链。如果未来需要"按来源 URL 反查 session"，应在 `script_generations` 里加 source 元数据，而不是恢复 material 表。

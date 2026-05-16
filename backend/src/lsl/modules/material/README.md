# LSL - Material Module

Material 模块负责把外部来源（v1 仅支持网页 URL）抽取为正文，并通过 `script` 模块产出带 CUE 的对话脚本。用户面叫"播客（Podcast）"。

## 当前接口

- `POST /materials/generate-session` 创建文本 session、material_generation 记录和异步 job（`job_type=script_from_material`）
- `GET /materials/generations/{generation_id}` 查询 material_generation 状态、抽取标题、关联的 `script_generation_id`

## 请求体

```json
{
  "source": {"type": "webpage", "url": "https://en.wikipedia.org/wiki/Domestic_cat"},
  "target_language": "en-US",
  "cue_language": "zh-CN",
  "prompt": "用初学者口吻，重点讲日常照护",
  "turn_count": 12,
  "speaker_count": 2,
  "difficulty": "intermediate",
  "must_include": ["litter box"],
  "title": null,
  "description": null
}
```

`source` 是 discriminated union（`source.type` 当前必须是 `"webpage"`）；未来扩展加 PDF / YouTube 等只需新增 extractor + 新的 `type` 值。

## 异步流程

Job 内三阶段：

1. `extracting`：调 `extractor.factory.build_extractor` 选 extractor 抽取正文；写 `extracted_title / extracted_text / extracted_meta_json`。
2. 调 `script_service.start_generation_from_material(...)` 创建 `script_generation` 记录，并把 `material_generation.script_generation_id` 写好。
3. 复用现有 `script` 流程完成对话生成、transcript、revision 写入。

抽取出的网页正文以 prompt context 注入 script generator：service 把 title + canonical URL + 用户 steering prompt + 正文按段拼接传给 `script.generator`。

## 失败语义

| 失败点 | error_code |
|---|---|
| 抓取超时 / 失败 | EXTRACTION_FAILED |
| 抽取正文 < 200 字符 | EXTRACTION_EMPTY |
| 下游 script 生成失败 | SCRIPT_GENERATION_FAILED |

失败时 session 保留、不自动重试。

## 安全

应用层只做最小校验（URL 格式、http/https 协议）。SSRF / IP 黑名单 / 鉴权 / 速率限制由线上网关层处理。

## 配置

```env
MATERIAL_WEBPAGE_TIMEOUT_SECONDS=15
MATERIAL_WEBPAGE_MAX_BODY_BYTES=5242880
MATERIAL_EXTRACTED_TEXT_MAX_CHARS=50000
```

依赖 `trafilatura`（纯 Python，本机运行，无 API key）。

## 与 transcript / script 的边界

- `transcript.source_type` 保持 `"ai_script"`，**不引入新枚举**。
- `script_generation.material_generation_id` 用作反向追溯。`transcript → script_generation → material_generation → URL` 是完整的追溯链。

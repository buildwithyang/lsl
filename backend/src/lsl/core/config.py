import os
from dataclasses import dataclass

from dotenv import load_dotenv


def _get_env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer, got: {raw!r}") from exc


def _get_env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be a number, got: {raw!r}") from exc


def _get_env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be a boolean, got: {raw!r}")


def _get_env_str(name: str, default: str) -> str:
    raw = os.getenv(name)
    if raw is None:
        return default
    value = raw.strip()
    if value == "":
        return default
    return value


@dataclass(frozen=True)
class Settings:
    # 文件存储 provider；运行服务时需配置为 fake 或 oss。
    STORAGE_PROVIDER: str = ""
    # 资源读取基础 URL，会与 object_key 拼成最终访问地址；可填 OSS bucket 域名或 CDN 域名。
    ASSET_BASE_URL: str = ""
    # 服务端上传文件到对象存储时的 HTTP 超时时间，单位秒。
    ASSET_PUT_TIMEOUT: float = 120.0

    # 数据库连接地址。默认使用 SQLite；PostgreSQL 使用 postgresql://...。
    DATABASE_URL: str = "sqlite:///./data/lsl.sqlite3"
    # PostgreSQL 连接池最小连接数；SQLite 不使用连接池。
    DB_POOL_MIN_SIZE: int = 1
    # PostgreSQL 连接池最大连接数；必须大于等于 DB_POOL_MIN_SIZE。
    DB_POOL_MAX_SIZE: int = 10
    # PostgreSQL 连接池获取连接的超时时间，单位秒。
    DB_POOL_TIMEOUT: float = 30.0

    # Auth / Casdoor
    # 1. 后端访问 Casdoor 的地址；Casdoor 在 Docker 中运行时不要用 localhost/127.0.0.1。
    CASDOOR_ENDPOINT: str = ""
    # 2. Casdoor 中 LSL 应用的 OAuth Client 配置。
    CASDOOR_CLIENT_ID: str = ""
    CASDOOR_CLIENT_SECRET: str = ""
    # 3. Casdoor / Google 登录成功后回调 LSL 后端的地址，必须和 Casdoor 应用 Redirect URLs 完全一致。
    CASDOOR_REDIRECT_URI: str = ""
    # 4. 后端完成 callback、写入登录 cookie 后，把浏览器重定向回这个前端地址。
    AUTH_FRONTEND_REDIRECT_URL: str = ""
    # 5. 后端用于签名 session cookie 的 HMAC secret；用于防篡改，不是加密。
    AUTH_SESSION_SECRET: str = "dev-session-secret-change-me"
    # 6. 本地 HTTP 开发为 false；HTTPS 部署时应为 true，否则浏览器不会发送 Secure cookie。
    AUTH_COOKIE_SECURE: bool = False
    # 7. 后端请求 Casdoor token/userinfo 接口的 HTTP 超时时间，单位秒。
    CASDOOR_HTTP_TIMEOUT: float = 15.0

    # 是否在 FastAPI lifespan 中启动后台 job runner。
    JOB_RUNNER_ENABLED: bool = True
    # job runner 轮询 due jobs 的间隔，单位秒。
    JOB_RUNNER_INTERVAL_SECONDS: float = 1.0
    # 每轮最多 claim 的 job 数。
    JOB_RUNNER_BATCH_SIZE: int = 10
    # job runner 同时执行 job 的最大线程数。
    JOB_RUNNER_MAX_WORKERS: int = 4

    # 阿里云 OSS region，例如 cn-hangzhou。
    OSS_REGION: str = "cn-hangzhou"
    # 阿里云 OSS bucket 名称。
    OSS_BUCKET: str = ""
    # 阿里云 OSS AccessKey ID；只用于服务端生成预签名上传地址。
    OSS_ACCESS_KEY_ID: str = ""
    # 阿里云 OSS AccessKey Secret；不要写入日志。
    OSS_ACCESS_KEY_SECRET: str = ""

    # ASR provider。本地可用 noop/fake；真实识别使用 volc。
    ASR_PROVIDER: str = "noop"
    # 火山 ASR App Key。
    VOLC_APP_KEY: str = ""
    # 火山 ASR Access Key。
    VOLC_ACCESS_KEY: str = ""
    # 火山 ASR resource id。
    VOLC_RESOURCE_ID: str = "volc.bigasr.auc"
    # 火山 ASR submit 接口地址。
    VOLC_SUBMIT_URL: str = "https://openspeech-direct.zijieapi.com/api/v3/auc/bigmodel/submit"
    # 火山 ASR query 接口地址。
    VOLC_QUERY_URL: str = "https://openspeech-direct.zijieapi.com/api/v3/auc/bigmodel/query"
    # 火山 ASR 模型名。
    VOLC_MODEL_NAME: str = "bigmodel"
    # 火山 ASR 请求使用的用户标识。
    VOLC_UID: str = "lsl_user"
    # 火山 ASR HTTP 超时时间，单位秒。
    VOLC_HTTP_TIMEOUT: float = 90.0

    # Revision provider。本地联调用 fake；真实改写使用 llm。
    REVISION_PROVIDER: str = "fake"
    # Revision LLM API Key。
    REVISION_LLM_API_KEY: str = ""
    # Revision LLM OpenAI-compatible base URL。
    REVISION_LLM_BASE_URL: str = "https://ark.cn-beijing.volces.com/api/v3"
    # Revision LLM 模型名。
    REVISION_LLM_MODEL: str = "doubao-1-5-pro-32k-250115"
    # Revision LLM HTTP 超时时间，单位秒。
    REVISION_LLM_HTTP_TIMEOUT: float = 90.0
    # Revision LLM 调试输出文件路径；空值表示不落盘。
    REVISION_LLM_DEBUG_FILE: str = ""

    # AI Script provider。本地联调用 fake；默认使用 llm 生成 CUE 脚本。
    SCRIPT_PROVIDER: str = "llm"
    # Script LLM API Key；未配置时复用 Revision LLM API Key。
    SCRIPT_LLM_API_KEY: str = ""
    # Script LLM base URL；未配置时复用 Revision LLM base URL。
    SCRIPT_LLM_BASE_URL: str = "https://ark.cn-beijing.volces.com/api/v3"
    # Script LLM 模型名；未配置时复用 Revision LLM 模型名。
    SCRIPT_LLM_MODEL: str = "doubao-1-5-pro-32k-250115"
    # Script LLM HTTP 超时时间，单位秒。
    SCRIPT_LLM_HTTP_TIMEOUT: float = 90.0

    # Material / Webpage extractor
    # 单次抓取 HTTP 超时，秒。
    MATERIAL_WEBPAGE_TIMEOUT_SECONDS: float = 15.0
    # 响应 Body 最大字节数，超过则截断。
    MATERIAL_WEBPAGE_MAX_BODY_BYTES: int = 5 * 1024 * 1024
    # 抽取出的正文最大字符数，超过则按 head+tail 截断。
    MATERIAL_EXTRACTED_TEXT_MAX_CHARS: int = 50_000

    # Translation provider。本地联调用 fake；真实翻译使用 llm。
    TRANSLATION_PROVIDER: str = "fake"
    # Translation LLM API Key；未配置时复用 Revision LLM API Key。
    TRANSLATION_LLM_API_KEY: str = ""
    # Translation LLM base URL；未配置时复用 Revision LLM base URL。
    TRANSLATION_LLM_BASE_URL: str = ""
    # Translation LLM 模型名；未配置时复用 Revision LLM 模型名。
    TRANSLATION_LLM_MODEL: str = ""
    # Translation LLM HTTP 超时时间，单位秒。
    TRANSLATION_LLM_HTTP_TIMEOUT: float = 90.0
    # 未显式传 target_language 时的默认翻译目标语言。
    TRANSLATION_DEFAULT_TARGET_LANGUAGE: str = "zh-CN"

    # TTS provider。本地联调用 fake/noop；真实合成使用 volc。
    TTS_PROVIDER: str = "fake"
    # TTS 单句试听缓存 Redis 地址；Redis 不可用时会回退进程内缓存。
    TTS_REDIS_URL: str = "redis://127.0.0.1:6379/0"
    # TTS 单句试听缓存 TTL，单位秒。
    TTS_CACHE_TTL_SECONDS: int = 7200
    # 火山 TTS App ID。
    TTS_VOLC_APP_ID: str = ""
    # 火山 TTS Access Key。
    TTS_VOLC_ACCESS_KEY: str = ""
    # 火山 TTS resource id。
    TTS_VOLC_RESOURCE_ID: str = "seed-tts-2.0"
    # 火山 TTS HTTP 接口地址。
    TTS_VOLC_URL: str = "https://openspeech.bytedance.com/api/v3/tts/unidirectional"
    # 火山 TTS HTTP 超时时间，单位秒。
    TTS_VOLC_HTTP_TIMEOUT: float = 90.0
    # 默认输出音频格式。
    TTS_DEFAULT_FORMAT: str = "mp3"
    # 默认情绪强度，火山 V3 取值范围 1 到 5。
    TTS_DEFAULT_EMOTION_SCALE: float = 4.0
    # 默认语速，火山 V3 取值范围 -50 到 100。
    TTS_DEFAULT_SPEECH_RATE: float = 0.0
    # 默认音量，火山 V3 取值范围 -50 到 100。
    TTS_DEFAULT_LOUDNESS_RATE: float = 0.0

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv(override=False)

        provider = os.getenv("STORAGE_PROVIDER", cls.STORAGE_PROVIDER).strip().lower()
        region = os.getenv("OSS_REGION", cls.OSS_REGION).strip()
        bucket = os.getenv("OSS_BUCKET", cls.OSS_BUCKET).strip()

        asset_base_url = os.getenv("ASSET_BASE_URL", cls.ASSET_BASE_URL).strip().rstrip("/")
        asset_put_timeout = _get_env_float("ASSET_PUT_TIMEOUT", cls.ASSET_PUT_TIMEOUT)
        database_url = _get_env_str("DATABASE_URL", cls.DATABASE_URL)
        db_pool_min_size = _get_env_int("DB_POOL_MIN_SIZE", cls.DB_POOL_MIN_SIZE)
        db_pool_max_size = _get_env_int("DB_POOL_MAX_SIZE", cls.DB_POOL_MAX_SIZE)
        db_pool_timeout = _get_env_float("DB_POOL_TIMEOUT", cls.DB_POOL_TIMEOUT)
        auth_cookie_secure = _get_env_bool("AUTH_COOKIE_SECURE", cls.AUTH_COOKIE_SECURE)
        casdoor_http_timeout = _get_env_float("CASDOOR_HTTP_TIMEOUT", cls.CASDOOR_HTTP_TIMEOUT)
        job_runner_enabled = _get_env_bool("JOB_RUNNER_ENABLED", cls.JOB_RUNNER_ENABLED)
        job_runner_interval_seconds = _get_env_float(
            "JOB_RUNNER_INTERVAL_SECONDS",
            cls.JOB_RUNNER_INTERVAL_SECONDS,
        )
        job_runner_batch_size = _get_env_int("JOB_RUNNER_BATCH_SIZE", cls.JOB_RUNNER_BATCH_SIZE)
        job_runner_max_workers = _get_env_int("JOB_RUNNER_MAX_WORKERS", cls.JOB_RUNNER_MAX_WORKERS)
        volc_http_timeout = _get_env_float("VOLC_HTTP_TIMEOUT", cls.VOLC_HTTP_TIMEOUT)
        revision_llm_http_timeout = _get_env_float(
            "REVISION_LLM_HTTP_TIMEOUT",
            cls.REVISION_LLM_HTTP_TIMEOUT,
        )
        script_llm_http_timeout = _get_env_float(
            "SCRIPT_LLM_HTTP_TIMEOUT",
            cls.SCRIPT_LLM_HTTP_TIMEOUT,
        )
        material_webpage_timeout_seconds = _get_env_float(
            "MATERIAL_WEBPAGE_TIMEOUT_SECONDS",
            cls.MATERIAL_WEBPAGE_TIMEOUT_SECONDS,
        )
        material_webpage_max_body_bytes = _get_env_int(
            "MATERIAL_WEBPAGE_MAX_BODY_BYTES",
            cls.MATERIAL_WEBPAGE_MAX_BODY_BYTES,
        )
        material_extracted_text_max_chars = _get_env_int(
            "MATERIAL_EXTRACTED_TEXT_MAX_CHARS",
            cls.MATERIAL_EXTRACTED_TEXT_MAX_CHARS,
        )
        translation_llm_http_timeout = _get_env_float(
            "TRANSLATION_LLM_HTTP_TIMEOUT",
            cls.TRANSLATION_LLM_HTTP_TIMEOUT,
        )
        tts_cache_ttl_seconds = _get_env_int("TTS_CACHE_TTL_SECONDS", cls.TTS_CACHE_TTL_SECONDS)
        tts_volc_http_timeout = _get_env_float("TTS_VOLC_HTTP_TIMEOUT", cls.TTS_VOLC_HTTP_TIMEOUT)
        tts_default_emotion_scale = _get_env_float("TTS_DEFAULT_EMOTION_SCALE", cls.TTS_DEFAULT_EMOTION_SCALE)
        tts_default_speech_rate = _get_env_float("TTS_DEFAULT_SPEECH_RATE", cls.TTS_DEFAULT_SPEECH_RATE)
        tts_default_loudness_rate = _get_env_float("TTS_DEFAULT_LOUDNESS_RATE", cls.TTS_DEFAULT_LOUDNESS_RATE)

        if asset_put_timeout <= 0:
            raise ValueError("ASSET_PUT_TIMEOUT must be greater than 0")
        if db_pool_min_size <= 0:
            raise ValueError("DB_POOL_MIN_SIZE must be greater than 0")
        if db_pool_max_size < db_pool_min_size:
            raise ValueError("DB_POOL_MAX_SIZE must be greater than or equal to DB_POOL_MIN_SIZE")
        if db_pool_timeout <= 0:
            raise ValueError("DB_POOL_TIMEOUT must be greater than 0")
        if casdoor_http_timeout <= 0:
            raise ValueError("CASDOOR_HTTP_TIMEOUT must be greater than 0")
        if job_runner_interval_seconds <= 0:
            raise ValueError("JOB_RUNNER_INTERVAL_SECONDS must be greater than 0")
        if job_runner_batch_size <= 0:
            raise ValueError("JOB_RUNNER_BATCH_SIZE must be greater than 0")
        if job_runner_max_workers <= 0:
            raise ValueError("JOB_RUNNER_MAX_WORKERS must be greater than 0")
        if volc_http_timeout <= 0:
            raise ValueError("VOLC_HTTP_TIMEOUT must be greater than 0")
        if revision_llm_http_timeout <= 0:
            raise ValueError("REVISION_LLM_HTTP_TIMEOUT must be greater than 0")
        if script_llm_http_timeout <= 0:
            raise ValueError("SCRIPT_LLM_HTTP_TIMEOUT must be greater than 0")
        if translation_llm_http_timeout <= 0:
            raise ValueError("TRANSLATION_LLM_HTTP_TIMEOUT must be greater than 0")
        if tts_cache_ttl_seconds <= 0:
            raise ValueError("TTS_CACHE_TTL_SECONDS must be greater than 0")
        if tts_volc_http_timeout <= 0:
            raise ValueError("TTS_VOLC_HTTP_TIMEOUT must be greater than 0")
        if not 1 <= tts_default_emotion_scale <= 5:
            raise ValueError("TTS_DEFAULT_EMOTION_SCALE must be between 1 and 5")
        if not -50 <= tts_default_speech_rate <= 100:
            raise ValueError("TTS_DEFAULT_SPEECH_RATE must be between -50 and 100")
        if not -50 <= tts_default_loudness_rate <= 100:
            raise ValueError("TTS_DEFAULT_LOUDNESS_RATE must be between -50 and 100")

        tts_volc_app_id = _get_env_str("TTS_VOLC_APP_ID", cls.TTS_VOLC_APP_ID)
        tts_volc_access_key = _get_env_str("TTS_VOLC_ACCESS_KEY", cls.TTS_VOLC_ACCESS_KEY)
        tts_provider = os.getenv("TTS_PROVIDER", cls.TTS_PROVIDER).strip().lower() or cls.TTS_PROVIDER
        revision_provider = os.getenv("REVISION_PROVIDER", cls.REVISION_PROVIDER).strip().lower() or cls.REVISION_PROVIDER
        revision_llm_api_key = _get_env_str("REVISION_LLM_API_KEY", cls.REVISION_LLM_API_KEY)
        revision_llm_base_url = _get_env_str("REVISION_LLM_BASE_URL", cls.REVISION_LLM_BASE_URL)
        revision_llm_model = _get_env_str("REVISION_LLM_MODEL", cls.REVISION_LLM_MODEL)

        script_provider_default = "llm" if revision_provider == "llm" else cls.SCRIPT_PROVIDER
        script_provider = os.getenv("SCRIPT_PROVIDER", script_provider_default).strip().lower() or script_provider_default
        script_llm_api_key = _get_env_str("SCRIPT_LLM_API_KEY", revision_llm_api_key or cls.SCRIPT_LLM_API_KEY)
        script_llm_base_url = _get_env_str("SCRIPT_LLM_BASE_URL", revision_llm_base_url or cls.SCRIPT_LLM_BASE_URL)
        script_llm_model = _get_env_str("SCRIPT_LLM_MODEL", revision_llm_model or cls.SCRIPT_LLM_MODEL)

        translation_provider_default = "llm" if revision_provider == "llm" else cls.TRANSLATION_PROVIDER
        translation_provider = os.getenv("TRANSLATION_PROVIDER", translation_provider_default).strip().lower() or translation_provider_default
        translation_llm_api_key = _get_env_str("TRANSLATION_LLM_API_KEY", revision_llm_api_key or cls.TRANSLATION_LLM_API_KEY)
        translation_llm_base_url = _get_env_str("TRANSLATION_LLM_BASE_URL", revision_llm_base_url or cls.TRANSLATION_LLM_BASE_URL)
        translation_llm_model = _get_env_str("TRANSLATION_LLM_MODEL", revision_llm_model or cls.TRANSLATION_LLM_MODEL)

        return cls(
            STORAGE_PROVIDER=provider,
            ASSET_BASE_URL=asset_base_url,
            ASSET_PUT_TIMEOUT=asset_put_timeout,
            DATABASE_URL=database_url,
            DB_POOL_MIN_SIZE=db_pool_min_size,
            DB_POOL_MAX_SIZE=db_pool_max_size,
            DB_POOL_TIMEOUT=db_pool_timeout,
            AUTH_SESSION_SECRET=_get_env_str("AUTH_SESSION_SECRET", cls.AUTH_SESSION_SECRET),
            AUTH_COOKIE_SECURE=auth_cookie_secure,
            AUTH_FRONTEND_REDIRECT_URL=_get_env_str(
                "AUTH_FRONTEND_REDIRECT_URL",
                cls.AUTH_FRONTEND_REDIRECT_URL,
            ),
            CASDOOR_ENDPOINT=_get_env_str("CASDOOR_ENDPOINT", cls.CASDOOR_ENDPOINT),
            CASDOOR_CLIENT_ID=_get_env_str("CASDOOR_CLIENT_ID", cls.CASDOOR_CLIENT_ID),
            CASDOOR_CLIENT_SECRET=_get_env_str("CASDOOR_CLIENT_SECRET", cls.CASDOOR_CLIENT_SECRET),
            CASDOOR_REDIRECT_URI=_get_env_str("CASDOOR_REDIRECT_URI", cls.CASDOOR_REDIRECT_URI),
            CASDOOR_HTTP_TIMEOUT=casdoor_http_timeout,
            JOB_RUNNER_ENABLED=job_runner_enabled,
            JOB_RUNNER_INTERVAL_SECONDS=job_runner_interval_seconds,
            JOB_RUNNER_BATCH_SIZE=job_runner_batch_size,
            JOB_RUNNER_MAX_WORKERS=job_runner_max_workers,
            OSS_REGION=region,
            OSS_BUCKET=bucket,
            OSS_ACCESS_KEY_ID=os.getenv("OSS_ACCESS_KEY_ID", cls.OSS_ACCESS_KEY_ID).strip(),
            OSS_ACCESS_KEY_SECRET=os.getenv("OSS_ACCESS_KEY_SECRET", cls.OSS_ACCESS_KEY_SECRET).strip(),
            ASR_PROVIDER=os.getenv("ASR_PROVIDER", cls.ASR_PROVIDER).strip().lower() or cls.ASR_PROVIDER,
            VOLC_APP_KEY=_get_env_str("VOLC_APP_KEY", cls.VOLC_APP_KEY),
            VOLC_ACCESS_KEY=_get_env_str("VOLC_ACCESS_KEY", cls.VOLC_ACCESS_KEY),
            VOLC_RESOURCE_ID=_get_env_str("VOLC_RESOURCE_ID", cls.VOLC_RESOURCE_ID),
            VOLC_SUBMIT_URL=_get_env_str("VOLC_SUBMIT_URL", cls.VOLC_SUBMIT_URL),
            VOLC_QUERY_URL=_get_env_str("VOLC_QUERY_URL", cls.VOLC_QUERY_URL),
            VOLC_MODEL_NAME=_get_env_str("VOLC_MODEL_NAME", cls.VOLC_MODEL_NAME),
            VOLC_UID=_get_env_str("VOLC_UID", cls.VOLC_UID),
            VOLC_HTTP_TIMEOUT=volc_http_timeout,
            REVISION_PROVIDER=revision_provider,
            REVISION_LLM_API_KEY=revision_llm_api_key,
            REVISION_LLM_BASE_URL=revision_llm_base_url,
            REVISION_LLM_MODEL=revision_llm_model,
            REVISION_LLM_HTTP_TIMEOUT=revision_llm_http_timeout,
            REVISION_LLM_DEBUG_FILE=_get_env_str("REVISION_LLM_DEBUG_FILE", cls.REVISION_LLM_DEBUG_FILE),
            SCRIPT_PROVIDER=script_provider,
            SCRIPT_LLM_API_KEY=script_llm_api_key,
            SCRIPT_LLM_BASE_URL=script_llm_base_url,
            SCRIPT_LLM_MODEL=script_llm_model,
            SCRIPT_LLM_HTTP_TIMEOUT=script_llm_http_timeout,
            MATERIAL_WEBPAGE_TIMEOUT_SECONDS=material_webpage_timeout_seconds,
            MATERIAL_WEBPAGE_MAX_BODY_BYTES=material_webpage_max_body_bytes,
            MATERIAL_EXTRACTED_TEXT_MAX_CHARS=material_extracted_text_max_chars,
            TRANSLATION_PROVIDER=translation_provider,
            TRANSLATION_LLM_API_KEY=translation_llm_api_key,
            TRANSLATION_LLM_BASE_URL=translation_llm_base_url,
            TRANSLATION_LLM_MODEL=translation_llm_model,
            TRANSLATION_LLM_HTTP_TIMEOUT=translation_llm_http_timeout,
            TRANSLATION_DEFAULT_TARGET_LANGUAGE=_get_env_str(
                "TRANSLATION_DEFAULT_TARGET_LANGUAGE",
                cls.TRANSLATION_DEFAULT_TARGET_LANGUAGE,
            ),
            TTS_PROVIDER=tts_provider,
            TTS_REDIS_URL=_get_env_str("TTS_REDIS_URL", cls.TTS_REDIS_URL),
            TTS_CACHE_TTL_SECONDS=tts_cache_ttl_seconds,
            TTS_VOLC_APP_ID=tts_volc_app_id,
            TTS_VOLC_ACCESS_KEY=tts_volc_access_key,
            TTS_VOLC_RESOURCE_ID=_get_env_str("TTS_VOLC_RESOURCE_ID", cls.TTS_VOLC_RESOURCE_ID),
            TTS_VOLC_URL=_get_env_str("TTS_VOLC_URL", cls.TTS_VOLC_URL),
            TTS_VOLC_HTTP_TIMEOUT=tts_volc_http_timeout,
            TTS_DEFAULT_FORMAT=_get_env_str("TTS_DEFAULT_FORMAT", cls.TTS_DEFAULT_FORMAT).lower(),
            TTS_DEFAULT_EMOTION_SCALE=tts_default_emotion_scale,
            TTS_DEFAULT_SPEECH_RATE=tts_default_speech_rate,
            TTS_DEFAULT_LOUDNESS_RATE=tts_default_loudness_rate,
        )

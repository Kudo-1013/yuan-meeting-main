"""应用配置管理"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """应用配置，从环境变量读取"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # 应用
    APP_NAME: str = "Yuan-Meet · 研发会议垂类 Agent"
    DEBUG: bool = True
    SERVER_PORT: int = 8787

    # SFU（mediasoup）服务地址，由 Step 1.3 启用
    SFU_BASE_URL: str = "http://localhost:4001"

    # 数据库
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5433/yuan_meet"
    DATABASE_ECHO: bool = False

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # LLM（通义千问，兼容 OpenAI 接口）
    OPENAI_API_KEY: str = ""
    OPENAI_BASE_URL: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    LLM_MODEL: str = "qwen-plus"
    VISION_MODEL: str = "qwen-vl-plus"
    EMBEDDING_MODEL: str = "text-embedding-v3"
    EMBEDDING_DIMENSIONS: int = 1024  # text-embedding-v3 维度

    # 音频转写：paraformer-v2 中文识别更优，whisper-1 作为兼容备选
    TRANSCRIPTION_MODEL: str = "paraformer-v2"
    # 转写 Provider：auto(默认,优先真实→降级Mock) / dashscope / mock
    TRANSCRIPTION_PROVIDER: str = "auto"

    # DashScope 原生录音识别 API（生产环境真实转写）
    # 文档：https://help.aliyun.com/zh/dashscope/developer-reference/paraformer-audio-file-recognition
    DASHSCOPE_API_KEY: str = ""  # 默认复用 OPENAI_API_KEY，留空则自动取
    DASHSCOPE_ASR_URL: str = "https://dashscope.aliyuncs.com/api/v1/services/audio/asr/transcription"
    DASHSCOPE_TASK_QUERY_URL: str = "https://dashscope.aliyuncs.com/api/v1/tasks"
    DASHSCOPE_ASR_MODEL: str = "paraformer-v2"

    # 阿里云 OSS（DashScope ASR 需要公网 URL，通过 OSS 中转）
    # 留空则禁用真实转写，自动降级 Mock
    OSS_ACCESS_KEY_ID: str = ""
    OSS_ACCESS_KEY_SECRET: str = ""
    OSS_ENDPOINT: str = ""  # 如 https://oss-cn-hangzhou.aliyuncs.com
    OSS_BUCKET_NAME: str = ""
    OSS_PREFIX: str = "audio/"  # 上传到 OSS 的目录前缀

    # 文件上传
    UPLOAD_DIR: str = "./uploads"
    MAX_UPLOAD_SIZE: int = 500 * 1024 * 1024  # 500MB

    # CORS
    CORS_ORIGINS: list[str] = ["http://localhost:5173"]


settings = Settings()

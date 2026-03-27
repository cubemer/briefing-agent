from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # API keys
    anthropic_api_key: str = ""
    newsapi_key: str = ""
    pinecone_api_key: str = ""
    pinecone_env: str = ""

    # Telegram
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    # Pinecone
    pinecone_index_name: str = "morning-brief"
    similarity_threshold: float = 0.85
    memory_ttl_days: int = 7

    # Pipeline
    max_retries: int = 2
    max_brief_bullets: int = 8
    relevance_threshold: float = 0.4

    # Models
    scoring_model: str = "claude-haiku-4-5-20250929"
    synthesis_model: str = "claude-sonnet-4-5-20250514"


settings = Settings()

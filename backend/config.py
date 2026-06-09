from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # OpenAI
    openai_api_key: str = ""
    openai_model: str = "gpt-4o"
    max_tokens: int = 2048
    max_context_chunks: int = 6

    # Document processing
    upload_max_mb: int = 50
    embed_model: str = "all-MiniLM-L6-v2"

    # Auth
    auth_username: str = "admin"
    auth_password: str = "changeme"
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 480  # 8 hours


settings = Settings()

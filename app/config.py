from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    openai_api_key: str = ""
    openai_model: str = "gpt-4o"
    max_tokens: int = 2048
    max_context_chunks: int = 6
    upload_max_mb: int = 50
    embed_model: str = "all-MiniLM-L6-v2"


settings = Settings()

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    database_url: str = ""
    supabase_url: str = ""
    supabase_anon_key: str = ""

    # SEC requires a descriptive User-Agent: "Company Name contact@email.com"
    edgar_user_agent: str = "pcIQ dev@pciq.io"

    anthropic_api_key: str = ""


settings = Settings()

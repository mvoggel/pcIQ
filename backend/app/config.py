from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    database_url: str = ""
    supabase_url: str = ""
    supabase_anon_key: str = ""

    # SEC requires a descriptive User-Agent: "Company Name contact@email.com"
    edgar_user_agent: str = "pcIQ dev@pciq.io"

    anthropic_api_key: str = ""

    # Comma-separated allowed CORS origins — extend via env var in prod
    allowed_origins: str = "http://localhost:3000,http://localhost:3001,http://localhost:3002"

    # Secret token for the /api/ingest/trigger endpoint (set in Railway env)
    ingest_secret: str = ""

    # Salesforce OAuth 2.0 (Connected App — set in Railway env)
    salesforce_client_id: str = ""
    salesforce_client_secret: str = ""
    salesforce_refresh_token: str = ""
    salesforce_instance_url: str = ""   # e.g. https://myorg.my.salesforce.com


settings = Settings()

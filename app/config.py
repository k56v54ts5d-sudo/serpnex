from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Database
    database_url: str = "postgresql+asyncpg://serpnex:serpnex@localhost:5432/serpnex"
    database_url_sync: str = "postgresql+psycopg2://serpnex:serpnex@localhost:5432/serpnex"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Security
    secret_key: str = "dev-secret-key-change-in-production"

    # Provider selection
    crawler_provider: str = "firecrawl"
    search_data_provider: str = "dataforseo"
    llm_provider: str = "anthropic"
    gsc_provider: str = "google"

    # Firecrawl
    firecrawl_api_key: str = ""

    # DataForSEO
    dataforseo_login: str = ""
    dataforseo_password: str = ""

    # Anthropic
    anthropic_api_key: str = ""

    # Google / GSC
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "http://localhost:8000/api/v1/auth/gsc/callback"


settings = Settings()

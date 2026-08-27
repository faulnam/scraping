from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache
from typing import Optional


class Settings(BaseSettings):
    # Parameter Database MySQL Terpisah
    DB_HOST: str = "localhost"
    DB_PORT: int = 3306
    DB_USER: str = "root"
    DB_PASSWORD: str = ""
    DB_NAME: str = "leadmaps_bi"

    # URL Lengkap (Opsional - jika diisi akan diprioritaskan)
    DATABASE_URL: Optional[str] = None

    # Google Places API Key (Official Google Cloud)
    GOOGLE_MAPS_API_KEY: Optional[str] = ""

    # SerpApi Key (Alternative live Google Maps search without credit card billing)
    SERPAPI_API_KEY: Optional[str] = ""

    # Pengaturan Aplikasi
    DEBUG: bool = True
    APP_NAME: str = "LeadMaps BI"
    APP_ENV: str = "development"
    SECRET_KEY: str = "leadmaps_bi_secret_key_default"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    def get_database_url(self) -> str:
        """
        Mengembalikan connection string SQLAlchemy MySQL.
        Prioritas:
        1. DATABASE_URL jika eksplisit diisi di .env
        2. Format dari DB_USER, DB_PASSWORD, DB_HOST, DB_PORT, DB_NAME
        """
        if self.DATABASE_URL and self.DATABASE_URL.strip():
            return self.DATABASE_URL.strip()

        pwd = f":{self.DB_PASSWORD}" if self.DB_PASSWORD else ""
        return f"mysql+pymysql://{self.DB_USER}{pwd}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"


@lru_cache()
def get_settings() -> Settings:
    return Settings()

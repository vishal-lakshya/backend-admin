from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8', extra='ignore')

    DATABASE_URL: str | None = None
    NEON_DATABASE_URL: str | None = None
    LOCAL_DATABASE_URL: str | None = None
    DB_HOST: str = 'localhost'
    DB_PORT: int = 5432
    DB_NAME: str = 'postgres'
    DB_USER: str = 'postgres'
    DB_PASSWORD: str = 'password'
    DB_SSL_MODE: str = 'prefer'  # prefer | require | disable

    @property
    def database_url(self) -> str:
        # Priority: explicit DATABASE_URL > provider-specific URLs > assembled from parts
        def _norm(url: str) -> str:
            normalized = url.replace('postgresql://', 'postgresql+psycopg2://', 1) if url.startswith('postgresql://') else url
            # psycopg2 doesn't support channel_binding param; strip if present
            normalized = normalized.replace('channel_binding=require', '')
            normalized = normalized.replace('&&', '&').replace('?&', '?')
            if normalized.endswith('&') or normalized.endswith('?'):
                normalized = normalized[:-1]
            return normalized

        if self.DATABASE_URL:
            return _norm(self.DATABASE_URL)
        if self.NEON_DATABASE_URL:
            return _norm(self.NEON_DATABASE_URL)
        if self.LOCAL_DATABASE_URL:
            return _norm(self.LOCAL_DATABASE_URL)
        return _norm(
            f"postgresql+psycopg2://{self.DB_USER}:{self.DB_PASSWORD}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
            f"?sslmode={self.DB_SSL_MODE}"
        )


@lru_cache
def get_database_url() -> str:
    return DatabaseSettings().database_url

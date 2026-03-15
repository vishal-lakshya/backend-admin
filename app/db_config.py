from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8', extra='ignore')

    NEON_DATABASE_URL: str | None = None

    @property
    def database_url(self) -> str:
        def _norm(url: str) -> str:
            normalized = url.replace('postgresql://', 'postgresql+psycopg2://', 1) if url.startswith('postgresql://') else url
            # psycopg2 doesn't support channel_binding param; strip if present
            normalized = normalized.replace('channel_binding=require', '')
            normalized = normalized.replace('&&', '&').replace('?&', '?')
            if normalized.endswith('&') or normalized.endswith('?'):
                normalized = normalized[:-1]
            return normalized

        if not self.NEON_DATABASE_URL:
            raise ValueError('NEON_DATABASE_URL is required.')
        return _norm(self.NEON_DATABASE_URL)


@lru_cache
def get_database_url() -> str:
    return DatabaseSettings().database_url

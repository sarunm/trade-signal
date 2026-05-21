from pydantic import ConfigDict
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = (
        "postgresql+asyncpg://tradesignal:tradesignal@db:5432/tradesignal"
    )
    database_url_sync: str = (
        "postgresql+psycopg2://tradesignal:tradesignal@db:5432/tradesignal"
    )

    model_config = ConfigDict(env_file=".env")


settings = Settings()

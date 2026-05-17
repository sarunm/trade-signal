from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = (
        "postgresql+asyncpg://tradesignal:tradesignal@db:5432/tradesignal"
    )
    database_url_sync: str = (
        "postgresql+psycopg2://tradesignal:tradesignal@db:5432/tradesignal"
    )

    class Config:
        env_file = ".env"


settings = Settings()

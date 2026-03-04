from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql+psycopg://ceo24:ceo24@localhost:5432/ceo24"
    SECRET_KEY: str = "change-me-in-production"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480
    IMPORT_INBOX_DIR: str = "/tmp/ceo24_inbox"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()

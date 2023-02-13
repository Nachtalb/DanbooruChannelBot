from pydantic import BaseSettings


class Config(BaseSettings):
    BOT_TOKEN: str

    WEBHOOK: bool
    WEBHOOK_LISTEN: str = "0.0.0.0"
    WEBHOOK_PORT: int = 80
    WEBHOOK_EXT_DOMAIN: str | None
    WEBHOOK_EXT_PATH: str | None

    DANBOORU_USERNAME: str
    DANBOORU_KEY: str

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ORBYTE_")

    database_url: str = "sqlite:///./orbyte.db"

settings = Settings()

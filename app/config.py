from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "sqlite:///./agentik.db"
    secret_key: str = "dev-secret-key-change-in-production"
    algorithm: str = "HS256"

    model_config = {"env_prefix": "AGENTIK_"}


settings = Settings()

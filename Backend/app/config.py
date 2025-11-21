from pydantic import BaseSettings, Field


class Settings(BaseSettings):
    # Database
    DATABASE_URL: str = Field("sqlite:///./dev.db", env="DATABASE_URL")

    # Redis / Celery
    REDIS_URL: str = Field("redis://localhost:6379/0", env="REDIS_URL")
    CELERY_BROKER_URL: str = Field(None, env="CELERY_BROKER_URL")

    # JWT
    JWT_SECRET_KEY: str = Field("replace-me-with-strong-secret", env="JWT_SECRET_KEY")
    JWT_ALGORITHM: str = Field("HS256", env="JWT_ALGORITHM")
    ACCESS_TOKEN_EXPIRE_SECONDS: int = Field(60 * 60 * 24 * 7, env="ACCESS_TOKEN_EXPIRE_SECONDS")

    # Other
    VERIFICATION_CACHE_TTL: int = Field(86400, env="VERIFICATION_CACHE_TTL")
    VERIFICATION_MAX_PER_DOMAIN: int = Field(2, env="VERIFICATION_MAX_PER_DOMAIN")
    RATE_LIMIT_REQUESTS: int = Field(120, env="RATE_LIMIT_REQUESTS")
    RATE_LIMIT_WINDOW: int = Field(60, env="RATE_LIMIT_WINDOW")

    # Third party
    STRIPE_SECRET_KEY: str = Field("", env="STRIPE_SECRET_KEY")
    PDL_API_KEY: str = Field("", env="PDL_API_KEY")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()


BULK_CHUNK_SIZE: int = 200
BULK_INPUT_FOLDER: str = "/tmp/bulk_inputs"
BULK_RESULTS_FOLDER: str = "/tmp/bulk_results"

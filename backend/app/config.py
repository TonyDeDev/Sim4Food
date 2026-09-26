from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # env_file is shared with the Next.js app's root .env, which carries
    # frontend-only keys (e.g. NEXT_PUBLIC_API_URL) - ignore what we don't
    # recognize instead of erroring on them.
    model_config = SettingsConfigDict(env_file=["../.env", ".env"], extra="ignore")

    postgres_user: str = "sim4food"
    postgres_password: str = "sim4food_dev"
    postgres_db: str = "sim4food"
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_sslmode: str = "prefer"
    # Full connection string (e.g. from Neon's dashboard). Takes priority over
    # the discrete postgres_* fields above when set.
    postgres_url: str | None = None
    cors_origins: str = "http://localhost:3000"

    @property
    def database_url(self) -> str:
        if self.postgres_url:
            return self.postgres_url
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
            f"?sslmode={self.postgres_sslmode}"
        )

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()

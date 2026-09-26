from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    postgres_user: str = "sim4food"
    postgres_password: str = "sim4food_dev"
    postgres_db: str = "sim4food"
    postgres_host: str = "localhost"
    postgres_port: int = 5432

    @property
    def database_url(self) -> str:
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    class Config:
        env_file = "../.env"


settings = Settings()

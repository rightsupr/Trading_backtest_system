from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")
    database_path: str = "data/trading.duckdb"
    api_port: int = 8000
    frontend_port: int = 5173
    default_commission: float = 0.0003
    log_level: str = "INFO"

    @property
    def db_path(self) -> Path:
        path = Path(self.database_path)
        return path if path.is_absolute() else ROOT / path


settings = Settings()

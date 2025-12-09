from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    api_token: str = "dev-token"
    whisper_model: str = "base"  # Modelos: tiny, base, small, medium, large
    whisper_device: str = "auto"  # auto, cuda, cpu
    ollama_model: str | None = "llama3.2"  # None para desabilitar Ollama
    ollama_url: str = "http://localhost:11434"  # URL do servidor Ollama
    data_dir: Path = Path("/data")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="APP_",
        case_sensitive=False,
    )

    @property
    def uploads_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def outputs_dir(self) -> Path:
        return self.data_dir / "outputs"

    def ensure_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.uploads_dir.mkdir(parents=True, exist_ok=True)
        self.outputs_dir.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_dirs()
    return settings


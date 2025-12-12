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
    cors_origins: str = "http://localhost:3000,http://localhost:3002,http://127.0.0.1:3000,http://127.0.0.1:3002,https://voxly.klapowsko.com,https://voxly-api.klapowsko.com,http://voxly.klapowsko.com,http://voxly-api.klapowsko.com"  # Origens permitidas para CORS (separadas por vírgula)
    transcription_parallel_chunks: bool = True  # Se True, processa chunks em paralelo (padrão: True)
    whisper_beam_size: int = 5  # Tamanho do beam search para melhor qualidade (padrão: 5)
    whisper_best_of: int = 5  # Número de tentativas para escolher melhor resultado (padrão: 5)
    whisper_condition_on_previous_text: bool = True  # Se True, usa contexto anterior (padrão: True, desabilitar para áudios longos)

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


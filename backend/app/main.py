from fastapi import FastAPI

from app.api.routes import router as api_router
from app.config import get_settings


settings = get_settings()

app = FastAPI(
    title="Audio Transcription API",
    description="API para upload de áudio, transcrição (Whisper) e geração de tópicos em Markdown.",
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(api_router, prefix="/api")



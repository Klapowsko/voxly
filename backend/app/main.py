from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router as api_router
from app.config import get_settings


settings = get_settings()

app = FastAPI(
    title="Audio Transcription API",
    description="API para upload de áudio, transcrição (Whisper) e geração de tópicos em Markdown.",
)

# Configuração CORS
# Permite qualquer subdomínio de klapowsko.com (HTTPS e HTTP) e localhost em qualquer porta
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"https?://.*\.klapowsko\.com|https?://klapowsko\.com|http://localhost:\d+|http://127\.0\.0\.1:\d+",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(api_router, prefix="/api")



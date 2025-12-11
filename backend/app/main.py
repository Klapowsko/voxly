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
# Lista explícita de origens permitidas
cors_origins = [
    "http://localhost:3000",
    "http://localhost:3002",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:3002",
    "https://voxly.klapowsko.com",
    "http://voxly.klapowsko.com",
    "https://voxly-api.klapowsko.com",
    "http://voxly-api.klapowsko.com",
    "https://klapowsko.com",
    "http://klapowsko.com",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(api_router, prefix="/api")



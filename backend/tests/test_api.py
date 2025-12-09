import io
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.deps import get_app_settings
from app.config import Settings


client = TestClient(app)


@pytest.fixture(autouse=True)
def override_settings(tmp_path: Path):
    settings = Settings(
        api_token="test-token",
        whisper_model="tiny",  # Modelo menor para testes mais rápidos
        data_dir=tmp_path,
    )
    settings.ensure_dirs()

    def _get_settings() -> Settings:
        return settings

    app.dependency_overrides[get_app_settings] = _get_settings
    yield
    app.dependency_overrides.clear()


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_transcribe_flow(monkeypatch: pytest.MonkeyPatch):
    async def fake_transcribe_file(path, settings):
        return "texto transcrito"

    async def fake_generate_topics_markdown(transcript, settings, request_id):
        output_path = settings.outputs_dir / f"{request_id}.md"
        output_path.write_text("# Markdown de teste", encoding="utf-8")
        return "# Markdown de teste", output_path

    monkeypatch.setattr("app.api.routes.transcribe_file", fake_transcribe_file)
    monkeypatch.setattr(
        "app.api.routes.generate_topics_markdown", fake_generate_topics_markdown
    )

    audio_content = io.BytesIO(b"dummy audio content")
    files = {"file": ("sample.wav", audio_content, "audio/wav")}
    headers = {"X-API-TOKEN": "test-token"}

    response = client.post("/api/transcribe", files=files, headers=headers)

    assert response.status_code == 200
    data = response.json()
    assert data["transcript"] == "texto transcrito"
    assert data["markdown"].startswith("# Markdown")
    assert data["markdown_file"].endswith(".md")
    assert data["download_url"].startswith("/api/files/")


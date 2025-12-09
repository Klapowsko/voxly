from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from app.audio.service import save_upload
from app.config import Settings
from app.deps import get_app_settings, verify_token
from app.topics.service import generate_topics_markdown
from app.transcription.service import transcribe_file
from app.utils.ids import new_request_id

router = APIRouter(dependencies=[Depends(verify_token)])


@router.post("/transcribe")
async def transcribe_audio(
    file: UploadFile = File(...),
    settings: Settings = Depends(get_app_settings),
) -> dict[str, Any]:
    if not file.content_type or not file.content_type.startswith("audio/"):
        raise HTTPException(status_code=400, detail="Arquivo enviado não é áudio.")

    request_id = new_request_id()
    audio_path = await save_upload(file, settings=settings, request_id=request_id)
    transcript_text = await transcribe_file(audio_path, settings=settings)
    markdown_content, markdown_path = await generate_topics_markdown(
        transcript_text, settings=settings, request_id=request_id
    )

    return {
        "request_id": request_id,
        "transcript": transcript_text,
        "markdown": markdown_content,
        "markdown_file": markdown_path.name,
        "download_url": f"/api/files/{markdown_path.name}",
    }


@router.get("/files/{filename}")
async def download_file(
    filename: str, settings: Settings = Depends(get_app_settings)
) -> FileResponse:
    safe_path = (settings.outputs_dir / filename).resolve()
    if settings.outputs_dir not in safe_path.parents and settings.outputs_dir != safe_path:
        raise HTTPException(status_code=400, detail="Caminho inválido.")
    if not safe_path.exists():
        raise HTTPException(status_code=404, detail="Arquivo não encontrado.")

    return FileResponse(
        safe_path,
        media_type="text/markdown",
        filename=Path(filename).name,
    )



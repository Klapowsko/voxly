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
from app.utils.status import set_status, get_status, clear_status

router = APIRouter(dependencies=[Depends(verify_token)])


@router.post("/transcribe")
async def transcribe_audio(
    file: UploadFile = File(...),
    settings: Settings = Depends(get_app_settings),
) -> dict[str, Any]:
    # Aceita tanto áudio quanto vídeo (Whisper pode processar ambos)
    # Verifica content_type e extensão do arquivo
    content_type = file.content_type or ""
    filename = file.filename or ""
    
    # Extensões de áudio e vídeo suportadas
    audio_extensions = {".mp3", ".wav", ".m4a", ".ogg", ".flac", ".aac", ".webm", ".opus"}
    video_extensions = {".mp4", ".webm", ".avi", ".mov", ".mkv", ".flv", ".wmv"}
    
    # Verifica se é áudio ou vídeo pelo content_type
    is_audio = content_type.startswith("audio/")
    is_video = content_type.startswith("video/")
    
    # Verifica pela extensão do arquivo
    file_ext = Path(filename).suffix.lower()
    is_audio_ext = file_ext in audio_extensions
    is_video_ext = file_ext in video_extensions
    
    if not (is_audio or is_video or is_audio_ext or is_video_ext):
        raise HTTPException(
            status_code=400,
            detail=f"Arquivo não suportado. Envie um arquivo de áudio ou vídeo. Tipo recebido: {content_type or 'desconhecido'}, extensão: {file_ext or 'nenhuma'}",
        )

    request_id = new_request_id()
    
    try:
        # Upload (10%)
        set_status(request_id, "uploading", 10, "Recebendo arquivo de áudio...")
        audio_path = await save_upload(file, settings=settings, request_id=request_id)
        
        # Transcrição (10-60%)
        set_status(request_id, "transcribing", 20, "Iniciando transcrição com Whisper...")
        transcript_text = await transcribe_file(audio_path, settings=settings, request_id=request_id)
        set_status(request_id, "transcribing", 60, f"Transcrição concluída: {len(transcript_text)} caracteres")
        
        # Geração de tópicos (60-95%)
        set_status(request_id, "generating", 65, "Iniciando geração de tópicos...")
        markdown_content, markdown_path = await generate_topics_markdown(
            transcript_text, settings=settings, request_id=request_id, request_id_status=request_id
        )
        set_status(request_id, "generating", 95, "Tópicos gerados com sucesso!")
        
        # Concluído (100%)
        set_status(request_id, "done", 100, "Processamento concluído")
        
        return {
            "request_id": request_id,
            "transcript": transcript_text,
            "markdown": markdown_content,
            "markdown_file": markdown_path.name,
            "download_url": f"/api/files/{markdown_path.name}",
        }
    except Exception as e:
        set_status(request_id, "error", 0, f"Erro: {str(e)}")
        raise
    finally:
        # Limpa status após 1 hora (opcional)
        pass


@router.get("/status/{request_id}")
async def get_request_status(
    request_id: str,
    settings: Settings = Depends(get_app_settings),
) -> dict[str, Any]:
    """Retorna o status de uma requisição."""
    status = get_status(request_id)
    if not status:
        raise HTTPException(status_code=404, detail="Requisição não encontrada")
    return status


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



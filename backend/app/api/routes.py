import asyncio
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse

from app.audio.service import save_upload
from app.config import Settings
from app.deps import get_app_settings, verify_token
from app.models.history_store import HistoryStore, TranscriptionRecord, build_preview, now_iso
from app.transcription.background import process_transcription_async
from app.utils.ids import new_request_id
from app.utils.status import clear_status, get_status, set_status

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
        # Upload e validação
        set_status(request_id, "uploading", 10, "Recebendo arquivo de áudio...")
        audio_path = await save_upload(file, settings=settings, request_id=request_id)
        
        # Cria registro no histórico com status "processing"
        store = HistoryStore(settings.data_dir)
        # Cria paths temporários (serão atualizados quando processamento terminar)
        transcript_path = settings.outputs_dir / f"{request_id}_transcript.txt"
        markdown_path = settings.outputs_dir / f"{request_id}_topics.md"
        
        store.add(
            TranscriptionRecord(
                id=request_id,
                filename=filename,
                created_at=now_iso(),
                audio_path=str(audio_path),
                transcript_path=str(transcript_path),
                markdown_path=str(markdown_path),
                transcript_preview=None,
                status="processing",
                language_detected=None,
                translated=False,
                transcript_original_path=None,
            )
        )
        
        # Inicia processamento em background
        asyncio.create_task(
            process_transcription_async(request_id, audio_path, filename, settings)
        )
        
        # Retorna imediatamente com status 202 Accepted
        return {
            "request_id": request_id,
            "status": "processing",
            "message": "Arquivo recebido. Processamento iniciado em background.",
        }
    except Exception as e:
        # Se erro no upload, atualiza histórico com status error
        store = HistoryStore(settings.data_dir)
        existing = store.get(request_id)
        if existing:
            existing.status = "error"
            existing.error_message = str(e)
            store.add(existing)
        else:
            # Se não existe registro, cria um com erro
            transcript_path = settings.outputs_dir / f"{request_id}_transcript.txt"
            markdown_path = settings.outputs_dir / f"{request_id}_topics.md"
            store.add(
                TranscriptionRecord(
                    id=request_id,
                    filename=filename or "unknown",
                    created_at=now_iso(),
                    audio_path="",
                    transcript_path=str(transcript_path),
                    markdown_path=str(markdown_path),
                    transcript_preview=None,
                    status="error",
                    language_detected=None,
                    translated=False,
                    transcript_original_path=None,
                    error_message=str(e),
                )
            )
        set_status(request_id, "error", 0, f"Erro: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


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


def _safe_resolve(path: Path, base_dir: Path) -> Path:
    resolved = path.resolve()
    if base_dir not in resolved.parents and resolved != base_dir:
        raise HTTPException(status_code=400, detail="Caminho inválido.")
    return resolved


def _delete_if_exists(path: Path) -> None:
    try:
        if path.exists():
            path.unlink()
    except Exception:
        # Melhor esforço: não interrompe fluxo por erro de remoção
        pass


@router.get("/history")
async def list_history(settings: Settings = Depends(get_app_settings)) -> list[dict[str, Any]]:
    store = HistoryStore(settings.data_dir)
    records = store.list()
    items: list[dict[str, Any]] = []
    for record in records:
        markdown_name = Path(record.markdown_path).name
        transcript_name = Path(record.transcript_path).name
        items.append(
            {
                "id": record.id,
                "filename": record.filename,
                "title": record.title or record.filename,  # Usa título se disponível, senão filename
                "created_at": record.created_at,
                "status": record.status,
                "transcript_preview": record.transcript_preview,
                "markdown_file": markdown_name,
                "transcript_file": transcript_name,
                "audio_file": Path(record.audio_path).name,
                "markdown_url": f"/api/files/{markdown_name}",
                "transcript_url": f"/api/files/{transcript_name}",
                "error_message": record.error_message,
            }
        )
    return items


@router.get("/history/{request_id}")
async def get_history_item(
    request_id: str, settings: Settings = Depends(get_app_settings)
) -> dict[str, Any]:
    store = HistoryStore(settings.data_dir)
    record = store.get(request_id)
    if not record:
        raise HTTPException(status_code=404, detail="Transcrição não encontrada")

    transcript_path = _safe_resolve(Path(record.transcript_path), settings.data_dir)
    markdown_path = _safe_resolve(Path(record.markdown_path), settings.data_dir)

    transcript_content = transcript_path.read_text(encoding="utf-8") if transcript_path.exists() else ""
    markdown_content = markdown_path.read_text(encoding="utf-8") if markdown_path.exists() else ""

    return {
        "id": record.id,
        "filename": record.filename,
        "title": record.title or record.filename,  # Usa título se disponível, senão filename
        "created_at": record.created_at,
        "status": record.status,
        "transcript": transcript_content,
        "markdown": markdown_content,
        "markdown_file": Path(record.markdown_path).name,
        "transcript_file": Path(record.transcript_path).name,
        "markdown_url": f"/api/files/{Path(record.markdown_path).name}",
        "transcript_url": f"/api/files/{Path(record.transcript_path).name}",
        "error_message": record.error_message,
    }


@router.delete("/history/{request_id}", status_code=204)
async def delete_history_item(
    request_id: str, settings: Settings = Depends(get_app_settings)
) -> None:
    store = HistoryStore(settings.data_dir)
    record = store.delete(request_id)
    if not record:
        raise HTTPException(status_code=404, detail="Transcrição não encontrada")

    # Remove arquivos associados
    data_dir = settings.data_dir
    audio_path = _safe_resolve(Path(record.audio_path), data_dir)
    transcript_path = _safe_resolve(Path(record.transcript_path), data_dir)
    markdown_path = _safe_resolve(Path(record.markdown_path), data_dir)

    _delete_if_exists(audio_path)
    _delete_if_exists(transcript_path)
    _delete_if_exists(markdown_path)

    clear_status(request_id)



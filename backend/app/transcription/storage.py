"""Gerenciamento de arquivos e histórico de transcrições."""
import logging
from pathlib import Path

from app.config import Settings
from app.models.history_store import HistoryStore, TranscriptionRecord, build_preview, now_iso
from app.utils.status import update_status_with_websocket

logger = logging.getLogger(__name__)


def salvar_arquivos(
    request_id: str,
    transcript_pt: str,
    transcript_original: str | None,
    translated: bool,
    settings: Settings,
) -> tuple[Path, Path | None]:
    """Salva arquivos de transcrição e original (se traduzido).
    
    Args:
        request_id: ID da requisição
        transcript_pt: Texto transcrito em português
        transcript_original: Texto original (se traduzido)
        translated: Se foi traduzido
        settings: Configurações da aplicação
        
    Returns:
        Tupla com (caminho_transcript, caminho_original_ou_none)
    """
    transcript_path = settings.outputs_dir / f"{request_id}_transcript.txt"
    transcript_path.write_text(transcript_pt, encoding="utf-8")
    logger.info(f"[{request_id}] Transcript salvo: {transcript_path}")
    
    transcript_original_path = None
    if translated and transcript_original:
        transcript_original_path = settings.outputs_dir / f"{request_id}_transcript_original.txt"
        transcript_original_path.write_text(transcript_original, encoding="utf-8")
        logger.info(f"[{request_id}] Transcript original salvo: {transcript_original_path}")
    
    return transcript_path, transcript_original_path


async def atualizar_historico(
    request_id: str,
    filename: str,
    audio_path: Path,
    transcript_path: Path,
    markdown_path: Path,
    transcript_pt: str,
    language_detected: str,
    translated: bool,
    transcript_original_path: Path | None,
    title: str,
    settings: Settings,
) -> None:
    """Atualiza o histórico com os dados da transcrição concluída.
    
    Args:
        request_id: ID da requisição
        filename: Nome do arquivo original
        audio_path: Caminho do arquivo de áudio
        transcript_path: Caminho do arquivo de transcrição
        markdown_path: Caminho do arquivo Markdown
        transcript_pt: Texto transcrito em português
        language_detected: Idioma detectado
        translated: Se foi traduzido
        transcript_original_path: Caminho do arquivo original (se traduzido)
        title: Título gerado
        settings: Configurações da aplicação
    """
    await update_status_with_websocket(
        request_id, "processing", 98, "Atualizando histórico..."
    )
    logger.info(f"[{request_id}] Atualizando histórico...")
    
    store = HistoryStore(settings.data_dir)
    store.add(
        TranscriptionRecord(
            id=request_id,
            filename=filename,
            created_at=now_iso(),
            audio_path=str(audio_path),
            transcript_path=str(transcript_path),
            markdown_path=str(markdown_path),
            transcript_preview=build_preview(transcript_pt),
            status="done",
            language_detected=language_detected,
            translated=translated,
            transcript_original_path=str(transcript_original_path) if transcript_original_path else None,
            title=title,
        )
    )
    logger.info(f"[{request_id}] Histórico atualizado")


async def tratar_erro(
    request_id: str,
    error: Exception,
    settings: Settings,
) -> None:
    """Trata erros durante o processamento.
    
    Args:
        request_id: ID da requisição
        error: Exceção ocorrida
        settings: Configurações da aplicação
    """
    logger.error(f"Erro ao processar transcrição {request_id}: {error}", exc_info=True)
    error_message = str(error)
    
    # Atualiza histórico com status "error"
    store = HistoryStore(settings.data_dir)
    existing = store.get(request_id)
    if existing:
        existing.status = "error"
        existing.error_message = error_message
        store.add(existing)
    
    # Notifica erro
    await update_status_with_websocket(
        request_id, "error", 0, f"Erro: {error_message}"
    )


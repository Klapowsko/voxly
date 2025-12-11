"""Processamento em background de transcrições."""
import asyncio
import logging
from pathlib import Path

from app.config import Settings
from app.models.history_store import HistoryStore, TranscriptionRecord, build_preview, now_iso
from app.topics.service import generate_topics_markdown
from app.transcription.service import transcribe_file
from app.transcription.translate import translate_en_to_pt
from app.utils.status import set_status
from app.websocket.manager import websocket_manager

logger = logging.getLogger(__name__)


async def process_transcription_async(
    request_id: str,
    audio_path: Path,
    filename: str,
    settings: Settings,
) -> None:
    """Processa transcrição em background de forma assíncrona."""
    try:
        # Notifica início do processamento
        await websocket_manager.notify_status_update(
            request_id, "processing", "Iniciando transcrição...", 10
        )
        set_status(request_id, "processing", 10, "Iniciando transcrição...")

        # Upload já foi feito, começa pela transcrição
        await websocket_manager.notify_status_update(
            request_id, "processing", "Transcrevendo áudio com Whisper...", 20
        )
        set_status(request_id, "transcribing", 20, "Iniciando transcrição com Whisper...")

        # Executa transcrição (já é async, mas Whisper roda em thread)
        transcription_result = await transcribe_file(audio_path, settings=settings, request_id=request_id)

        transcript_text = transcription_result.get("text", "") or ""
        language_detected = (transcription_result.get("language") or "unknown").lower()
        transcript_en = transcription_result.get("text_en") or ""

        await websocket_manager.notify_status_update(
            request_id,
            "processing",
            f"Transcrição ({language_detected}) concluída com {len(transcript_text)} caracteres",
            60,
        )
        set_status(
            request_id,
            "transcribing",
            60,
            f"Transcrição ({language_detected}) concluída com {len(transcript_text)} caracteres",
        )

        # Tradução automática para PT-BR se não for pt
        translated = False
        transcript_original = transcript_text
        transcript_pt = transcript_text

        if language_detected not in {"pt", "pt-br"}:
            translated = True
            text_to_translate = transcript_en if transcript_en else transcript_text
            if text_to_translate:
                await websocket_manager.notify_status_update(
                    request_id, "processing", "Traduzindo para PT-BR...", 62
                )
                set_status(request_id, "transcribing", 62, "Traduzindo para PT-BR...")
                transcript_pt = translate_en_to_pt(text_to_translate)
                if not transcript_pt or transcript_pt.strip() == text_to_translate.strip():
                    transcript_pt = transcript_text
                    translated = False

        # Geração de tópicos
        await websocket_manager.notify_status_update(
            request_id, "processing", "Iniciando geração de tópicos...", 65
        )
        set_status(request_id, "generating", 65, "Iniciando geração de tópicos...")

        markdown_content, markdown_path = await generate_topics_markdown(
            transcript_pt,
            settings=settings,
            request_id=request_id,
            request_id_status=request_id,
        )

        await websocket_manager.notify_status_update(
            request_id, "processing", "Tópicos gerados com sucesso!", 95
        )
        set_status(request_id, "generating", 95, "Tópicos gerados com sucesso!")
        logger.info(f"[{request_id}] Tópicos gerados, salvando arquivos...")

        # Salva arquivos
        transcript_path = settings.outputs_dir / f"{request_id}_transcript.txt"
        transcript_path.write_text(transcript_pt, encoding="utf-8")
        logger.info(f"[{request_id}] Transcript salvo: {transcript_path}")

        transcript_original_path = None
        if translated:
            transcript_original_path = settings.outputs_dir / f"{request_id}_transcript_original.txt"
            transcript_original_path.write_text(transcript_original, encoding="utf-8")
            logger.info(f"[{request_id}] Transcript original salvo: {transcript_original_path}")

        # Atualiza histórico com status "done"
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
            )
        )
        logger.info(f"[{request_id}] Histórico atualizado")

        # Notifica conclusão
        logger.info(f"[{request_id}] Enviando notificação de conclusão via WebSocket...")
        await websocket_manager.notify_status_update(
            request_id, "done", "Processamento concluído!", 100
        )
        set_status(request_id, "done", 100, "Processamento concluído")

        logger.info(f"[{request_id}] Processamento concluído para request_id: {request_id}")

    except Exception as e:
        logger.error(f"Erro ao processar transcrição {request_id}: {e}", exc_info=True)
        error_message = str(e)

        # Atualiza histórico com status "error"
        store = HistoryStore(settings.data_dir)
        existing = store.get(request_id)
        if existing:
            existing.status = "error"
            existing.error_message = error_message
            store.add(existing)

        # Notifica erro
        await websocket_manager.notify_status_update(
            request_id, "error", f"Erro: {error_message}", 0
        )
        set_status(request_id, "error", 0, f"Erro: {error_message}")




"""Orquestração do pipeline completo de processamento de transcrição."""
import logging

from pathlib import Path

from app.config import Settings
from app.transcription.pipeline import (
    processar_titulo,
    processar_topicos,
    processar_traducao,
    processar_transcricao,
)
from app.transcription.storage import atualizar_historico, salvar_arquivos, tratar_erro
from app.utils.status import update_status_with_websocket

logger = logging.getLogger(__name__)


async def process_transcription_async(
    request_id: str,
    audio_path: Path,
    filename: str,
    settings: Settings,
) -> None:
    """Processa transcrição em background de forma assíncrona.
    
    Args:
        request_id: ID da requisição
        audio_path: Caminho do arquivo de áudio
        filename: Nome do arquivo original
        settings: Configurações da aplicação
    """
    try:
        # Notifica início do processamento
        await update_status_with_websocket(
            request_id, "processing", 10, "Iniciando transcrição..."
        )
        
        # Etapa 1: Transcrição
        transcription_data = await processar_transcricao(request_id, audio_path, settings)
        transcript_text = transcription_data["text"]
        language_detected = transcription_data["language"]
        transcript_en = transcription_data["text_en"]
        
        # Etapa 2: Tradução (se necessário)
        transcript_pt, translated = await processar_traducao(
            request_id, transcript_text, transcript_en, language_detected
        )
        transcript_original = transcript_text if translated else None
        
        # Etapa 3: Geração de tópicos
        markdown_content, markdown_path = await processar_topicos(
            request_id, transcript_pt, settings
        )
        
        # Etapa 4: Geração de título
        title = await processar_titulo(request_id, transcript_pt, filename, settings)
        
        # Etapa 5: Salvamento de arquivos
        await update_status_with_websocket(
            request_id, "processing", 95, "Salvando arquivos..."
        )
        transcript_path, transcript_original_path = salvar_arquivos(
            request_id, transcript_pt, transcript_original, translated, settings
        )
        
        # Etapa 6: Atualização do histórico
        await atualizar_historico(
            request_id=request_id,
            filename=filename,
            audio_path=audio_path,
            transcript_path=transcript_path,
            markdown_path=markdown_path,
            transcript_pt=transcript_pt,
            language_detected=language_detected,
            translated=translated,
            transcript_original_path=transcript_original_path,
            title=title,
            settings=settings,
        )
        
        # Notifica conclusão
        logger.info(f"[{request_id}] Enviando notificação de conclusão via WebSocket...")
        await update_status_with_websocket(
            request_id, "done", 100, "Processamento concluído!"
        )
        
        logger.info(f"[{request_id}] Processamento concluído para request_id: {request_id}")
        
    except Exception as e:
        await tratar_erro(request_id, e, settings)

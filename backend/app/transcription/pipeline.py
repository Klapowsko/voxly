"""Etapas do pipeline de processamento de transcrição."""
import logging
from pathlib import Path

from app.config import Settings
from app.topics.service import generate_topics_markdown, generate_title
from app.transcription.service import transcribe_file
from app.transcription.translate import translate_en_to_pt
from app.utils.status import update_status_with_websocket

logger = logging.getLogger(__name__)


async def processar_transcricao(
    request_id: str,
    audio_path: Path,
    settings: Settings,
) -> dict[str, str]:
    """Processa a transcrição do áudio.
    
    Args:
        request_id: ID da requisição
        audio_path: Caminho do arquivo de áudio
        settings: Configurações da aplicação
        
    Returns:
        Dicionário com 'text', 'language' e 'text_en'
    """
    await update_status_with_websocket(
        request_id, "transcribing", 20, "Iniciando transcrição com Whisper..."
    )
    
    transcription_result = await transcribe_file(audio_path, settings=settings, request_id=request_id)
    
    transcript_text = transcription_result.get("text", "") or ""
    language_detected = (transcription_result.get("language") or "unknown").lower()
    transcript_en = transcription_result.get("text_en") or ""
    
    await update_status_with_websocket(
        request_id,
        "transcribing",
        60,
        f"Transcrição ({language_detected}) concluída com {len(transcript_text)} caracteres",
    )
    
    return {
        "text": transcript_text,
        "language": language_detected,
        "text_en": transcript_en,
    }


async def processar_traducao(
    request_id: str,
    transcript_text: str,
    transcript_en: str,
    language_detected: str,
) -> tuple[str, bool]:
    """Processa tradução para PT-BR se necessário.
    
    Args:
        request_id: ID da requisição
        transcript_text: Texto transcrito original
        transcript_en: Texto em inglês (se disponível)
        language_detected: Idioma detectado
        
    Returns:
        Tupla com (texto_pt, foi_traduzido)
    """
    translated = False
    transcript_pt = transcript_text
    
    if language_detected not in {"pt", "pt-br"}:
        translated = True
        text_to_translate = transcript_en if transcript_en else transcript_text
        if text_to_translate:
            await update_status_with_websocket(
                request_id, "processing", 62, "Traduzindo para PT-BR..."
            )
            transcript_pt = translate_en_to_pt(text_to_translate, request_id=request_id)
            if not transcript_pt or transcript_pt.strip() == text_to_translate.strip():
                transcript_pt = transcript_text
                translated = False
    
    return transcript_pt, translated


async def processar_topicos(
    request_id: str,
    transcript_pt: str,
    settings: Settings,
) -> tuple[str, Path]:
    """Gera tópicos em Markdown a partir do texto transcrito.
    
    Args:
        request_id: ID da requisição
        transcript_pt: Texto transcrito em português
        settings: Configurações da aplicação
        
    Returns:
        Tupla com (conteudo_markdown, caminho_arquivo)
    """
    await update_status_with_websocket(
        request_id, "generating", 70, "Iniciando geração de tópicos..."
    )
    
    markdown_content, markdown_path = await generate_topics_markdown(
        transcript_pt,
        settings=settings,
        request_id=request_id,
        request_id_status=request_id,
    )
    
    await update_status_with_websocket(
        request_id, "generating", 95, "Tópicos gerados com sucesso!"
    )
    logger.info(f"[{request_id}] Tópicos gerados, salvando arquivos...")
    
    return markdown_content, markdown_path


async def processar_titulo(
    request_id: str,
    transcript_pt: str,
    filename: str,
    settings: Settings,
) -> str:
    """Gera título descritivo para a transcrição.
    
    Args:
        request_id: ID da requisição
        transcript_pt: Texto transcrito em português
        filename: Nome do arquivo original
        settings: Configurações da aplicação
        
    Returns:
        Título gerado (ou filename se não conseguir gerar)
    """
    await update_status_with_websocket(
        request_id, "processing", 93, "Gerando título descritivo..."
    )
    logger.info(f"[{request_id}] Gerando título...")
    
    generated_title = generate_title(transcript_pt, settings=settings, request_id=request_id)
    
    # Se não gerou título ou está vazio, usa o filename como fallback
    title = generated_title.strip() if generated_title else filename
    
    # Limita tamanho do título
    if len(title) > 80:
        title = title[:77] + "..."
    
    logger.info(f"[{request_id}] Título gerado: {title}")
    return title


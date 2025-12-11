from __future__ import annotations

from functools import lru_cache
from typing import Optional

from transformers import pipeline


@lru_cache(maxsize=1)
def _get_en_to_pt_translator():
    # Modelo público EN -> PT; usa variante tc-big para reduzir risco de lookup inválido
    # https://huggingface.co/Helsinki-NLP/opus-mt-tc-big-en-pt
    return pipeline("translation_en_to_pt", model="Helsinki-NLP/opus-mt-tc-big-en-pt")


def _notify_status_sync(request_id: str | None, stage: str, progress: int, message: str) -> None:
    """Helper para notificar status via WebSocket em contexto síncrono."""
    if not request_id:
        return
    from app.utils.status import notify_status_from_thread
    notify_status_from_thread(request_id, stage, progress, message)


def translate_en_to_pt(text: str, request_id: str | None = None) -> str:
    """Traduz texto em inglês para PT-BR usando modelo Helsinki-NLP.
    
    Divide textos longos em chunks para evitar problemas de memória/tamanho.
    """
    if not text:
        return text
    
    _notify_status_sync(request_id, "transcribing", 62, "Carregando modelo de tradução...")
    
    translator = _get_en_to_pt_translator()
    
    _notify_status_sync(request_id, "transcribing", 63, "Dividindo texto em chunks para tradução...")
    
    # Divide em sentenças para traduzir em chunks menores (modelos têm limite ~512 tokens)
    import re
    sentences = re.split(r'([.!?]+(?:\s+|$))', text)
    chunks = []
    current_chunk = ""
    max_chunk_size = 400  # caracteres por chunk (conservador)
    
    for part in sentences:
        if len(current_chunk) + len(part) > max_chunk_size and current_chunk:
            chunks.append(current_chunk.strip())
            current_chunk = part
        else:
            current_chunk += part
    
    if current_chunk.strip():
        chunks.append(current_chunk.strip())
    
    if not chunks:
        chunks = [text]
    
    _notify_status_sync(request_id, "transcribing", 64, f"Traduzindo {len(chunks)} chunks...")
    
    translated_parts = []
    for i, chunk in enumerate(chunks):
        if not chunk.strip():
            continue
        try:
            # Atualiza progresso a cada chunk
            if request_id and len(chunks) > 1:
                progress = 64 + int((i + 1) / len(chunks) * 6)  # 64% a 70%
                _notify_status_sync(request_id, "transcribing", progress, f"Traduzindo chunk {i + 1}/{len(chunks)}...")
            
            outputs = translator(chunk, max_length=512, truncation=True)
            if outputs and isinstance(outputs, list):
                translated = outputs[0].get("translation_text", chunk)
                translated_parts.append(translated)
            else:
                translated_parts.append(chunk)
        except Exception as e:
            print(f"Erro ao traduzir chunk: {e}")
            # Em caso de erro em um chunk, mantém o original
            translated_parts.append(chunk)
    
    _notify_status_sync(request_id, "transcribing", 70, "Tradução concluída")
    
    result = " ".join(translated_parts)
    return result if result else text


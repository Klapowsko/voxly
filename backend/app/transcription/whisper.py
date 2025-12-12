"""Lógica de transcrição com Whisper."""
from pathlib import Path
from typing import Any

import torch
import whisper

from app.config import Settings
from app.transcription.model import get_cached_model
from app.transcription.utils import notify_status_sync

# Thresholds padronizados para Whisper (usados em múltiplas funções)
NO_SPEECH_THRESHOLD = 0.6  # Conservador - padrão do Whisper
LOGPROB_THRESHOLD = -0.5  # Restritivo para filtrar alucinações
COMPRESSION_RATIO_THRESHOLD = 2.2  # Detecta repetições/alucinações


def detectar_device(settings: Settings) -> str:
    """Detecta o device (cuda/cpu) a ser usado pelo Whisper.
    
    Args:
        settings: Configurações da aplicação
        
    Returns:
        String com o device ('cuda' ou 'cpu')
    """
    if settings.whisper_device == "auto":
        device = "cuda" if torch.cuda.is_available() else "cpu"
    else:
        device = settings.whisper_device
    
    if device == "cpu":
        print("Aviso: GPU não disponível, usando CPU (será mais lento para áudios longos)")
    
    return device


def criar_opcoes_whisper(device: str, condition_on_previous_text: bool = True) -> dict[str, Any]:
    """Cria dicionário de opções para o Whisper.
    
    Args:
        device: Device a ser usado ('cuda' ou 'cpu')
        condition_on_previous_text: Se deve usar contexto anterior
        
    Returns:
        Dicionário com opções do Whisper
    """
    return dict(
        fp16=True if device == "cuda" else False,
        temperature=0.0,  # Reduz criatividade e alucinações
        condition_on_previous_text=condition_on_previous_text,
        no_speech_threshold=NO_SPEECH_THRESHOLD,
        logprob_threshold=LOGPROB_THRESHOLD,
        compression_ratio_threshold=COMPRESSION_RATIO_THRESHOLD,
    )


def detectar_loop(result: dict[str, Any], request_id: str | None = None) -> bool:
    """Detecta sinais de loop/alucinação nos segmentos do resultado.
    
    Args:
        result: Resultado da transcrição do Whisper
        request_id: ID da requisição para logs
        
    Returns:
        True se detectou loop, False caso contrário
    """
    if "segments" not in result:
        return False
    
    segmentos_com_alta_compressao = 0
    for segmento in result["segments"]:
        compression_ratio = segmento.get("compression_ratio", 1.0)
        if compression_ratio >= COMPRESSION_RATIO_THRESHOLD:
            segmentos_com_alta_compressao += 1
    
    # Se mais de 30% dos segmentos têm alta compressão, provável loop
    if len(result["segments"]) > 0:
        percentual_alta_compressao = segmentos_com_alta_compressao / len(result["segments"])
        if percentual_alta_compressao > 0.3:
            print(f"[{request_id or 'N/A'}] Detectado possível loop: "
                  f"{percentual_alta_compressao:.1%} dos segmentos com alta compressão")
            return True
    
    return False


def executar_passada_whisper(
    model: whisper.Whisper,
    path: Path,
    options: dict[str, Any],
    request_id: str | None = None,
) -> dict[str, Any]:
    """Executa uma passada de transcrição com Whisper.
    
    Args:
        model: Modelo Whisper carregado
        path: Caminho do arquivo de áudio
        options: Opções de transcrição
        request_id: ID da requisição para logs
        
    Returns:
        Resultado da transcrição
    """
    return model.transcribe(str(path), **options)


def filtrar_segmentos(result: dict[str, Any], request_id: str | None = None) -> dict[str, Any]:
    """Filtra segmentos com alucinações do resultado.
    
    Args:
        result: Resultado da transcrição do Whisper
        request_id: ID da requisição para logs
        
    Returns:
        Resultado com texto filtrado (apenas segmentos válidos)
    """
    if "segments" not in result:
        return result
    
    segmentos_validos = []
    for segmento in result["segments"]:
        no_speech_prob = segmento.get("no_speech_prob", 0.0)
        avg_logprob = segmento.get("avg_logprob", -1.0)
        compression_ratio = segmento.get("compression_ratio", 1.0)
        
        # Usa os mesmos thresholds padronizados
        if (no_speech_prob < 0.7 and  # Mais conservador que no_speech_threshold
            avg_logprob > LOGPROB_THRESHOLD and  # Mesmo threshold
            compression_ratio < COMPRESSION_RATIO_THRESHOLD):  # Mesmo threshold
            segmentos_validos.append(segmento)
        else:
            print(f"[{request_id or 'N/A'}] Segmento filtrado (alucinação provável): "
                  f"no_speech={no_speech_prob:.2f}, logprob={avg_logprob:.2f}, "
                  f"compression={compression_ratio:.2f}, texto='{segmento.get('text', '')[:50]}...'")
    
    # Reconstrói o texto apenas com segmentos válidos
    if segmentos_validos:
        texto_filtrado = " ".join([s.get("text", "").strip() for s in segmentos_validos])
        result["text"] = texto_filtrado
        print(f"[{request_id or 'N/A'}] Filtrados {len(result['segments']) - len(segmentos_validos)} "
              f"segmentos de {len(result['segments'])} (possíveis alucinações)")
    else:
        print(f"[{request_id or 'N/A'}] AVISO: Todos os segmentos foram filtrados!")
    
    return result


def processar_traducao_whisper(
    model: whisper.Whisper,
    path: Path,
    language: str,
    options: dict[str, Any],
    request_id: str | None = None,
) -> str | None:
    """Processa tradução para inglês se necessário.
    
    Args:
        model: Modelo Whisper carregado
        path: Caminho do arquivo de áudio
        language: Idioma detectado
        options: Opções de transcrição
        request_id: ID da requisição para logs
        
    Returns:
        Texto traduzido para inglês ou None se não for necessário
    """
    if language and language not in {"pt", "pt-BR", "pt-br"}:
        notify_status_sync(request_id, "transcribing", 45, "Traduzindo para inglês (Whisper)...")
        translate_result = model.transcribe(str(path), task="translate", **options)
        return (translate_result.get("text") or "").strip()
    return None


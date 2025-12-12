"""Lógica de transcrição com Whisper."""
from pathlib import Path
from typing import Any

import torch
import whisper

from app.config import Settings
from app.transcription.model import get_cached_model
from app.transcription.utils import notify_status_sync

# Thresholds padronizados para Whisper (usados em múltiplas funções)
# Valores mais restritivos para reduzir alucinações
NO_SPEECH_THRESHOLD = 0.7  # Mais restritivo - filtra mais silêncio/alucinações
LOGPROB_THRESHOLD = -0.4  # Mais restritivo - exige maior confiança
COMPRESSION_RATIO_THRESHOLD = 2.0  # Mais restritivo - detecta repetições mais cedo


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


def criar_opcoes_whisper(
    device: str,
    condition_on_previous_text: bool = True,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Cria dicionário de opções para o Whisper.
    
    Args:
        device: Device a ser usado ('cuda' ou 'cpu')
        condition_on_previous_text: Se deve usar contexto anterior
        settings: Configurações da aplicação (opcional, para parâmetros adicionais)
        
    Returns:
        Dicionário com opções do Whisper
    """
    opcoes = dict(
        fp16=True if device == "cuda" else False,
        temperature=0.0,  # Reduz criatividade e alucinações
        condition_on_previous_text=condition_on_previous_text,
        no_speech_threshold=NO_SPEECH_THRESHOLD,
        logprob_threshold=LOGPROB_THRESHOLD,
        compression_ratio_threshold=COMPRESSION_RATIO_THRESHOLD,
    )
    
    # Adiciona parâmetros opcionais se disponíveis nas configurações
    if settings:
        # beam_size: melhora qualidade de decodificação (padrão: 5)
        beam_size = getattr(settings, 'whisper_beam_size', 5)
        if beam_size and beam_size > 0:
            opcoes['beam_size'] = beam_size
        
        # best_of: escolhe melhor resultado entre múltiplas tentativas (padrão: 5)
        best_of = getattr(settings, 'whisper_best_of', 5)
        if best_of and best_of > 0:
            opcoes['best_of'] = best_of
        
        # suppress_tokens: suprime tokens problemáticos (especiais, pontuação excessiva)
        # [-1] suprime tokens especiais que podem causar alucinações
        opcoes['suppress_tokens'] = [-1]
    
    return opcoes


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
    
    # Se mais de 20% dos segmentos têm alta compressão, provável loop (threshold reduzido)
    if len(result["segments"]) > 0:
        percentual_alta_compressao = segmentos_com_alta_compressao / len(result["segments"])
        if percentual_alta_compressao > 0.2:  # Reduzido de 0.3 para 0.2
            print(f"[{request_id or 'N/A'}] Detectado possível loop: "
                  f"{percentual_alta_compressao:.1%} dos segmentos com alta compressão")
            return True
    
    # Verifica repetição de frases completas (não apenas consecutivas)
    if "segments" in result and len(result["segments"]) > 5:
        textos_segmentos = [s.get("text", "").strip().lower() for s in result["segments"]]
        textos_unicos = set(textos_segmentos)
        # Se menos de 50% dos segmentos são únicos, provável repetição
        if len(textos_unicos) / len(textos_segmentos) < 0.5:
            print(f"[{request_id or 'N/A'}] Detectado possível loop: "
                  f"apenas {len(textos_unicos)} de {len(textos_segmentos)} segmentos únicos")
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
        
        # Usa thresholds mais restritivos para filtrar alucinações
        # no_speech_prob: mais restritivo (0.6 ao invés de 0.7)
        # avg_logprob: mais restritivo (-0.4 ao invés de -0.5)
        # compression_ratio: mais restritivo (2.0 ao invés de 2.2)
        if (no_speech_prob < 0.6 and  # Mais restritivo
            avg_logprob > -0.4 and  # Mais restritivo
            compression_ratio < 2.0):  # Mais restritivo
            # Verifica repetição de palavras dentro do segmento
            texto_segmento = segmento.get("text", "").strip()
            palavras = texto_segmento.split()
            if len(palavras) > 3:
                # Se mais de 50% das palavras são repetições, filtra
                palavras_unicas = len(set(palavra.lower() for palavra in palavras))
                if palavras_unicas / len(palavras) >= 0.5:
                    segmentos_validos.append(segmento)
                else:
                    print(f"[{request_id or 'N/A'}] Segmento filtrado (repetição interna): "
                          f"texto='{texto_segmento[:50]}...'")
            else:
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


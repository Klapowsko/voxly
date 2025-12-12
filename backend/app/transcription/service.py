"""Orquestração de transcrição usando Whisper."""
import time
from pathlib import Path

from anyio import to_thread

from app.config import Settings
from app.transcription.cleaning import aplicar_limpeza_condicional, detectar_anomalia_repeticao
from app.transcription.model import get_cached_model
from app.transcription.utils import notify_status_sync
from app.transcription.whisper import (
    criar_opcoes_whisper,
    detectar_device,
    detectar_loop,
    executar_passada_whisper,
    filtrar_segmentos,
    processar_traducao_whisper,
)


async def transcribe_file(path: Path, settings: Settings, request_id: str | None = None) -> dict[str, str | None]:
    """Transcreve áudio usando Whisper local.

    Retorna dict:
    - text: transcrição no idioma original
    - language: código ISO detectado (ex.: 'en', 'pt')
    - text_en: transcrição traduzida para inglês (via Whisper task=translate) se idioma != pt, senão None
    """

    def _run() -> dict[str, str | None]:
        # Detecta device
        device = detectar_device(settings)
        print(f"[{request_id or 'N/A'}] Iniciando transcrição com modelo {settings.whisper_model} em {device}...")
        start_time = time.time()
        
        # Atualiza status
        notify_status_sync(request_id, "transcribing", 10, "Preparando transcrição...")
        notify_status_sync(request_id, "transcribing", 15, "Carregando modelo Whisper...")
        
        # Carrega o modelo Whisper do cache
        model = get_cached_model(settings.whisper_model, device)
        print(f"[{request_id or 'N/A'}] Modelo carregado (do cache). Iniciando transcrição...")
        
        notify_status_sync(request_id, "transcribing", 35, "Modelo carregado, iniciando processamento...")
        notify_status_sync(request_id, "transcribing", 40, "Processando áudio com Whisper...")
        
        # Passada 1: Tenta com condition_on_previous_text=True (melhor para coerência)
        options_passada1 = criar_opcoes_whisper(device, condition_on_previous_text=True)
        options_passada2 = options_passada1.copy()  # Inicializa (será sobrescrito se houver loop)
        
        notify_status_sync(request_id, "transcribing", 40, "Primeira passada (com contexto)...")
        result = executar_passada_whisper(model, path, options_passada1, request_id)
        
        # Detecta sinais de loop/alucinação na primeira passada
        tem_loop = detectar_loop(result, request_id)
        
        # Se detectou loop, tenta segunda passada sem contexto
        if tem_loop:
            print(f"[{request_id or 'N/A'}] Tentando segunda passada sem contexto (condition_on_previous_text=False)...")
            notify_status_sync(request_id, "transcribing", 42, "Segunda passada (sem contexto, filtros mais rígidos)...")
            
            # Passada 2: Sem contexto
            options_passada2 = criar_opcoes_whisper(device, condition_on_previous_text=False)
            result_passada2 = executar_passada_whisper(model, path, options_passada2, request_id)
            
            # Compara resultados e escolhe o melhor
            texto_passada1 = result.get("text", "").strip()
            texto_passada2 = result_passada2.get("text", "").strip()
            
            # Prefere passada 2 se ela for significativamente mais curta (menos repetições)
            # ou se passada 1 tiver sinais claros de loop
            if len(texto_passada2) < len(texto_passada1) * 0.7 or detectar_anomalia_repeticao(texto_passada1):
                print(f"[{request_id or 'N/A'}] Usando resultado da segunda passada (sem contexto)")
                result = result_passada2
            else:
                print(f"[{request_id or 'N/A'}] Mantendo resultado da primeira passada (com contexto)")
        
        # Filtra alucinações baseado nos segmentos retornados
        result = filtrar_segmentos(result, request_id)
        
        # Log de tempo de processamento
        elapsed = time.time() - start_time
        duracao_audio = result.get("duration", 0)
        
        print(f"[{request_id or 'N/A'}] Transcrição concluída em {elapsed:.1f}s")
        if duracao_audio:
            print(f"[{request_id or 'N/A'}] Duração do áudio: {duracao_audio:.1f}s ({duracao_audio/60:.1f} minutos)")
            print(f"[{request_id or 'N/A'}] Velocidade: {duracao_audio/elapsed:.2f}x tempo real")
        
        texto = result.get("text", "").strip()
        language = (result.get("language") or "").strip()
        
        # Processa tradução se necessário
        options_traducao = options_passada2 if tem_loop else options_passada1
        texto_en = processar_traducao_whisper(model, path, language, options_traducao, request_id)
        
        if not texto:
            print(f"[{request_id or 'N/A'}] Aviso: Transcrição vazia!")
            notify_status_sync(request_id, "transcribing", 50, "Aviso: Transcrição vazia")
            return {"text": "", "language": language or "unknown", "text_en": None}
        
        print(f"[{request_id or 'N/A'}] Texto transcrito: {len(texto)} caracteres, ~{len(texto.split())} palavras")
        notify_status_sync(request_id, "transcribing", 50, f"Transcrição concluída ({len(texto)} caracteres)")
        
        # Aplica limpeza condicional
        texto_limpo = aplicar_limpeza_condicional(texto, request_id)
        
        # Limpa também o texto_en se existir (só se detectar anomalia)
        texto_en_limpo = None
        if texto_en:
            texto_en_limpo = aplicar_limpeza_condicional(texto_en, request_id)
        
        return {"text": texto_limpo, "language": language or "unknown", "text_en": texto_en_limpo}

    return await to_thread.run_sync(_run)

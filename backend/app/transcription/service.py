"""Orquestração de transcrição usando Whisper."""
import os
import shutil
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from anyio import to_thread

from app.config import Settings
from app.transcription.audio_utils import get_audio_duration, split_audio_into_chunks
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

# Duração mínima para dividir em chunks (10 minutos em segundos)
CHUNK_DURATION_SECONDS = 600


def _transcribe_single_chunk(
    chunk_path: Path,
    model,
    device: str,
    options: dict,
    chunk_index: int,
    total_chunks: int,
    request_id: str | None = None,
) -> dict:
    """Transcreve um único chunk de áudio.
    
    Args:
        chunk_path: Caminho do chunk
        model: Modelo Whisper carregado
        device: Device usado ('cuda' ou 'cpu')
        options: Opções do Whisper
        chunk_index: Índice do chunk (0-based)
        total_chunks: Total de chunks
        request_id: ID da requisição
        
    Returns:
        Dicionário com 'text' e 'language'
    """
    print(f"[{request_id or 'N/A'}] Processando chunk {chunk_index + 1}/{total_chunks}...")
    
    # Atualiza progresso proporcionalmente (40% a 50%)
    progress = 40 + int((chunk_index / total_chunks) * 10)
    notify_status_sync(
        request_id,
        "transcribing",
        progress,
        f"Processando chunk {chunk_index + 1}/{total_chunks}..."
    )
    
    # Executa transcrição do chunk
    result = executar_passada_whisper(model, chunk_path, options, request_id)
    
    # Filtra segmentos
    result = filtrar_segmentos(result, request_id)
    
    texto = result.get("text", "").strip()
    language = (result.get("language") or "").strip()
    
    return {"text": texto, "language": language}


def _transcribe_chunks_parallel(
    chunks: list[Path],
    model,
    device: str,
    options: dict,
    request_id: str | None = None,
    max_workers: int | None = None,
) -> list[dict]:
    """Processa chunks em paralelo usando ThreadPoolExecutor.
    
    Args:
        chunks: Lista de caminhos dos chunks
        model: Modelo Whisper carregado
        device: Device usado
        options: Opções do Whisper
        request_id: ID da requisição
        max_workers: Número máximo de workers (None = calcular automaticamente)
        
    Returns:
        Lista de resultados na ordem dos chunks
    """
    if max_workers is None:
        # Limita a 4 workers para não sobrecarregar
        max_workers = min(len(chunks), os.cpu_count() or 1, 4)
    
    print(f"[{request_id or 'N/A'}] Processando {len(chunks)} chunks em paralelo com {max_workers} workers...")
    
    # Cria dicionário para manter ordem dos resultados
    results_dict = {}
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submete todas as tarefas
        future_to_index = {
            executor.submit(
                _transcribe_single_chunk,
                chunk,
                model,
                device,
                options,
                i,
                len(chunks),
                request_id,
            ): i
            for i, chunk in enumerate(chunks)
        }
        
        # Coleta resultados conforme completam
        for future in as_completed(future_to_index):
            chunk_index = future_to_index[future]
            try:
                result = future.result()
                results_dict[chunk_index] = result
            except Exception as e:
                print(f"[{request_id or 'N/A'}] Erro ao processar chunk {chunk_index + 1}: {e}")
                # Em caso de erro, adiciona resultado vazio
                results_dict[chunk_index] = {"text": "", "language": "unknown"}
    
    # Retorna resultados na ordem correta
    return [results_dict[i] for i in range(len(chunks))]


def _transcribe_chunks_sequential(
    chunks: list[Path],
    model,
    device: str,
    options: dict,
    request_id: str | None = None,
) -> list[dict]:
    """Processa chunks sequencialmente.
    
    Args:
        chunks: Lista de caminhos dos chunks
        model: Modelo Whisper carregado
        device: Device usado
        options: Opções do Whisper
        request_id: ID da requisição
        
    Returns:
        Lista de resultados na ordem dos chunks
    """
    results = []
    for i, chunk in enumerate(chunks):
        result = _transcribe_single_chunk(
            chunk, model, device, options, i, len(chunks), request_id
        )
        results.append(result)
    return results


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
        
        # Verifica duração do áudio
        try:
            audio_duration = get_audio_duration(path)
            print(f"[{request_id or 'N/A'}] Duração do áudio: {audio_duration:.1f}s ({audio_duration/60:.1f} minutos)")
        except Exception as e:
            print(f"[{request_id or 'N/A'}] Aviso: Não foi possível obter duração do áudio: {e}")
            audio_duration = 0
        
        # Se áudio > 10 minutos, divide em chunks
        chunks_dir = None
        chunks = []
        use_chunks = audio_duration > CHUNK_DURATION_SECONDS
        
        if use_chunks:
            try:
                num_chunks = int(audio_duration / CHUNK_DURATION_SECONDS) + (1 if audio_duration % CHUNK_DURATION_SECONDS > 0 else 0)
                print(f"[{request_id or 'N/A'}] Detectado áudio longo ({audio_duration/60:.1f} minutos). Dividindo em {num_chunks} chunks de 10 minutos...")
                notify_status_sync(
                    request_id,
                    "transcribing",
                    15,
                    f"Dividindo áudio em {num_chunks} chunks de 10 minutos..."
                )
                
                # Cria diretório temporário para chunks
                chunks_dir = settings.uploads_dir / "chunks" / request_id if request_id else settings.uploads_dir / "chunks" / "temp"
                chunks_dir.mkdir(parents=True, exist_ok=True)
                
                # Divide áudio em chunks
                chunks = split_audio_into_chunks(
                    path,
                    CHUNK_DURATION_SECONDS,
                    chunks_dir,
                    request_id or "temp",
                )
                print(f"[{request_id or 'N/A'}] Áudio dividido em {len(chunks)} chunks")
            except Exception as e:
                print(f"[{request_id or 'N/A'}] Erro ao dividir áudio em chunks: {e}. Processando áudio completo...")
                use_chunks = False
                chunks = []
        
        try:
            notify_status_sync(request_id, "transcribing", 35, "Modelo carregado, iniciando processamento...")
            
            # Decide se usa condition_on_previous_text baseado na duração e configuração
            # Para áudios longos (>10min) ou chunks: False (evita repetições)
            # Para áudios curtos (<=10min): True (melhor coerência)
            # Mas respeita configuração global se definida
            use_condition = getattr(settings, 'whisper_condition_on_previous_text', True)
            if use_chunks:
                # Chunks sempre usam condition_on_previous_text=False para evitar repetições
                use_condition = False
                print(f"[{request_id or 'N/A'}] Usando condition_on_previous_text=False para chunks (evita repetições)")
            elif use_condition and audio_duration > 0:
                # Para áudios longos, desabilita condition_on_previous_text
                use_condition = audio_duration <= CHUNK_DURATION_SECONDS
                if audio_duration > CHUNK_DURATION_SECONDS:
                    print(f"[{request_id or 'N/A'}] Usando condition_on_previous_text=False para áudio longo ({audio_duration/60:.1f}min)")
                else:
                    print(f"[{request_id or 'N/A'}] Usando condition_on_previous_text={use_condition} para áudio curto")
            
            # Passada 1: Usa condition_on_previous_text baseado na duração
            options_passada1 = criar_opcoes_whisper(device, condition_on_previous_text=use_condition, settings=settings)
            options_passada2 = options_passada1.copy()  # Inicializa (será sobrescrito se houver loop)
            tem_loop = False  # Inicializa variável
            
            # Processa chunks ou áudio completo
            if use_chunks and chunks:
                # Processa chunks
                notify_status_sync(request_id, "transcribing", 40, f"Processando {len(chunks)} chunks...")
                
                # Decide se usa paralelismo (baseado em configuração ou padrão)
                use_parallel = getattr(settings, 'transcription_parallel_chunks', True)
                
                if use_parallel:
                    chunk_results = _transcribe_chunks_parallel(
                        chunks, model, device, options_passada1, request_id
                    )
                else:
                    chunk_results = _transcribe_chunks_sequential(
                        chunks, model, device, options_passada1, request_id
                    )
                
                # Junta transcrições na ordem
                notify_status_sync(request_id, "transcribing", 50, "Juntando transcrições...")
                chunk_texts = [r.get("text", "").strip() for r in chunk_results]
                texto_combinado = " ".join([t for t in chunk_texts if t])
                
                # Usa idioma do primeiro chunk (ou mais comum)
                languages = [r.get("language", "").strip() for r in chunk_results if r.get("language")]
                language = languages[0] if languages else "unknown"
                
                # Cria resultado combinado
                result = {
                    "text": texto_combinado,
                    "language": language,
                    "duration": audio_duration,
                }
            else:
                # Processa áudio completo normalmente
                notify_status_sync(request_id, "transcribing", 40, "Processando áudio com Whisper...")
                notify_status_sync(request_id, "transcribing", 40, "Primeira passada (com contexto)...")
                result = executar_passada_whisper(model, path, options_passada1, request_id)
            
            # Se não usou chunks, processa normalmente com detecção de loop
            if not use_chunks or not chunks:
                # Detecta sinais de loop/alucinação na primeira passada
                tem_loop = detectar_loop(result, request_id)
                
                # Se detectou loop, tenta segunda passada sem contexto
                if tem_loop:
                    print(f"[{request_id or 'N/A'}] Tentando segunda passada sem contexto (condition_on_previous_text=False)...")
                    notify_status_sync(request_id, "transcribing", 42, "Segunda passada (sem contexto, filtros mais rígidos)...")
                    
                    # Passada 2: Sem contexto (sempre False quando detecta loop)
                    options_passada2 = criar_opcoes_whisper(device, condition_on_previous_text=False, settings=settings)
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
            else:
                # Para chunks, já filtramos durante o processamento individual
                # Não precisa fazer segunda passada (chunks são pequenos)
                tem_loop = False
            
            # Log de tempo de processamento
            elapsed = time.time() - start_time
            duracao_audio = result.get("duration", 0)
            
            print(f"[{request_id or 'N/A'}] Transcrição concluída em {elapsed:.1f}s")
            if duracao_audio:
                print(f"[{request_id or 'N/A'}] Duração do áudio: {duracao_audio:.1f}s ({duracao_audio/60:.1f} minutos)")
                print(f"[{request_id or 'N/A'}] Velocidade: {duracao_audio/elapsed:.2f}x tempo real")
            
            texto = result.get("text", "").strip()
            language = (result.get("language") or "").strip()
            
            # Processa tradução se necessário (apenas para áudio completo, não para chunks)
            # Para chunks, processamos tradução depois de juntar tudo
            texto_en = None
            if not use_chunks or not chunks:
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
        finally:
            # Garante limpeza dos chunks temporários mesmo em caso de erro
            if chunks_dir and chunks_dir.exists():
                try:
                    shutil.rmtree(chunks_dir)
                    print(f"[{request_id or 'N/A'}] Chunks temporários removidos")
                except Exception as e:
                    print(f"[{request_id or 'N/A'}] Aviso: Erro ao remover chunks temporários: {e}")

    return await to_thread.run_sync(_run)

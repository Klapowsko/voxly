from pathlib import Path
import re
from functools import lru_cache
from typing import Dict, Any

from anyio import to_thread
import torch
import whisper

from app.config import Settings


# Cache global de modelos Whisper (evita recarregar a cada transcrição)
_model_cache: Dict[str, whisper.Whisper] = {}


def _get_cached_model(model_name: str, device: str) -> whisper.Whisper:
    """Retorna modelo Whisper do cache ou carrega se não existir."""
    cache_key = f"{model_name}_{device}"
    if cache_key not in _model_cache:
        print(f"Carregando modelo Whisper {model_name} em {device} (primeira vez)...")
        _model_cache[cache_key] = whisper.load_model(model_name, device=device)
        print(f"Modelo {model_name} carregado e cacheado.")
    return _model_cache[cache_key]


def _notify_status_sync(request_id: str | None, stage: str, progress: int, message: str) -> None:
    """Helper para notificar status via WebSocket em contexto síncrono."""
    if not request_id:
        return
    from app.utils.status import notify_status_from_thread
    notify_status_from_thread(request_id, stage, progress, message)


def _detectar_anomalia_repeticao(texto: str) -> bool:
    """Detecta se o texto tem sinais de repetição excessiva (alucinação)."""
    if not texto or len(texto) < 50:
        return False
    
    palavras = texto.split()
    if len(palavras) < 10:
        return False
    
    # Calcula razão de tokens únicos / tokens total
    tokens_unicos = len(set(palavra.lower() for palavra in palavras))
    tokens_total = len(palavras)
    razao_unicos = tokens_unicos / tokens_total if tokens_total > 0 else 0
    
    # Se menos de 30% dos tokens são únicos, provável alucinação
    if razao_unicos < 0.3:
        return True
    
    # Verifica se há n-grams repetidos excessivamente (3-5 palavras)
    for n in range(3, 6):
        ngrams = {}
        for i in range(len(palavras) - n + 1):
            ngram = " ".join(palavras[i:i+n]).lower()
            ngrams[ngram] = ngrams.get(ngram, 0) + 1
        
        # Se algum n-gram aparece mais de 10 vezes, é suspeito
        if ngrams and max(ngrams.values()) > 10:
            return True
    
    return False


def limpar_repeticoes(texto: str) -> str:
    """Remove repetições excessivas de frases do texto transcrito (incluindo alucinações)."""
    if not texto:
        return texto
    
    texto_limpo = texto
    max_iteracoes = 15  # Evita loop infinito
    iteracao = 0
    
    # Remove repetições iterativamente até não encontrar mais
    while iteracao < max_iteracoes:
        texto_anterior = texto_limpo
        palavras = texto_limpo.split()
        
        if len(palavras) < 3:
            break
        
        removido = False
        
        # Remove repetições de padrões de 1 até 12 palavras
        # Começa pelos padrões maiores (mais específicos) e vai diminuindo
        for tamanho_padrao in range(min(12, len(palavras) // 2), 0, -1):
            if tamanho_padrao > len(palavras):
                continue
                
            i = 0
            while i < len(palavras) - tamanho_padrao * 2:  # Precisa de pelo menos 2 repetições
                padrao = palavras[i:i + tamanho_padrao]
                padrao_texto = " ".join(padrao).lower().strip()
                
                # Ignora padrões muito curtos ou muito comuns (artigos, preposições isoladas)
                if tamanho_padrao == 1 and padrao_texto in {
                    "o", "a", "e", "de", "que", "em", "um", "uma", "é", "foi", 
                    "ser", "se", "para", "com", "por", "foi", "que", "o", "a"
                }:
                    i += 1
                    continue
                
                # Conta quantas vezes esse padrão se repete consecutivamente
                repeticoes = 1
                j = i + tamanho_padrao
                
                while j <= len(palavras) - tamanho_padrao:
                    proximo_padrao = " ".join(palavras[j:j + tamanho_padrao]).lower().strip()
                    if proximo_padrao == padrao_texto:
                        repeticoes += 1
                        j += tamanho_padrao
                    else:
                        break
                
                # Remove repetições excessivas (mais agressivo para alucinações)
                # Para padrões de 1-2 palavras: remove se repetir mais de 2 vezes
                # Para padrões de 3-5 palavras: remove se repetir mais de 2 vezes
                # Para padrões de 6+ palavras: remove se repetir mais de 1 vez
                if tamanho_padrao <= 2:
                    limite = 2
                elif tamanho_padrao <= 5:
                    limite = 2
                else:
                    limite = 1
                
                if repeticoes > limite:
                    # Mantém apenas 1 ocorrência do padrão
                    palavras = palavras[:i + tamanho_padrao] + palavras[i + tamanho_padrao * repeticoes:]
                    texto_limpo = " ".join(palavras)
                    removido = True
                    # Reinicia a busca do início após remoção
                    break
                
                i += 1
            
            if removido:
                break
        
        # Se não removeu nada nesta iteração, para
        if not removido or texto_limpo == texto_anterior:
            break
        
        iteracao += 1
    
    # Remove repetições de sentenças completas (com pontuação)
    sentencas = re.split(r"([.!?]+)", texto_limpo)
    
    # Reconstrói sentenças completas
    sentencas_completas = []
    buffer = ""
    for parte in sentencas:
        parte = parte.strip()
        if not parte:
            continue
        if re.search(r"[.!?]+", parte):
            if buffer:
                sentenca = (buffer + " " + parte).strip()
                if len(sentenca) > 5:
                    sentencas_completas.append(sentenca)
                buffer = ""
            else:
                if len(parte) > 5:
                    sentencas_completas.append(parte)
        else:
            buffer = (buffer + " " + parte).strip() if buffer else parte
    
    if buffer and len(buffer) > 5:
        sentencas_completas.append(buffer)
    
    # Remove repetições de sentenças completas (mantém no máximo 1 repetição)
    sentencas_limpas = []
    ultima_sentenca = None
    contador_repeticao = 0
    
    for sentenca in sentencas_completas:
        sentenca_normalizada = re.sub(r"\s+", " ", sentenca.lower().strip())
        
        if sentenca_normalizada == ultima_sentenca:
            contador_repeticao += 1
            # Mantém no máximo 1 repetição de sentenças completas
            if contador_repeticao <= 1:
                sentencas_limpas.append(sentenca)
        else:
            ultima_sentenca = sentenca_normalizada
            contador_repeticao = 1
            sentencas_limpas.append(sentenca)
    
    # Reconstrói o texto final
    texto_limpo = " ".join(sentencas_limpas)
    
    # Limpa espaços múltiplos e normaliza
    texto_limpo = re.sub(r"\s+", " ", texto_limpo).strip()
    
    return texto_limpo


async def transcribe_file(path: Path, settings: Settings, request_id: str | None = None) -> dict[str, str | None]:
    """Transcreve áudio usando Whisper local.

    Retorna dict:
    - text: transcrição no idioma original
    - language: código ISO detectado (ex.: 'en', 'pt')
    - text_en: transcrição traduzida para inglês (via Whisper task=translate) se idioma != pt, senão None
    """

    def _run() -> str:
        import time
        
        # Detecta device (auto, cuda ou cpu)
        if settings.whisper_device == "auto":
            device = "cuda" if torch.cuda.is_available() else "cpu"
        else:
            device = settings.whisper_device
        
        if device == "cpu":
            print("Aviso: GPU não disponível, usando CPU (será mais lento para áudios longos)")
        
        print(f"[{request_id or 'N/A'}] Iniciando transcrição com modelo {settings.whisper_model} em {device}...")
        start_time = time.time()
        
        # Atualiza status se request_id fornecido
        _notify_status_sync(request_id, "transcribing", 10, "Preparando transcrição...")
        _notify_status_sync(request_id, "transcribing", 15, "Carregando modelo Whisper...")
        
        # Carrega o modelo Whisper do cache
        model = _get_cached_model(settings.whisper_model, device)
        print(f"[{request_id or 'N/A'}] Modelo carregado (do cache). Iniciando transcrição...")
        
        _notify_status_sync(request_id, "transcribing", 35, "Modelo carregado, iniciando processamento...")
        _notify_status_sync(request_id, "transcribing", 40, "Processando áudio com Whisper...")
        
        # Thresholds padronizados (usados tanto no options quanto no filtro manual)
        NO_SPEECH_THRESHOLD = 0.6  # Conservador - padrão do Whisper
        LOGPROB_THRESHOLD = -0.5  # Restritivo para filtrar alucinações
        COMPRESSION_RATIO_THRESHOLD = 2.2  # Detecta repetições/alucinações
        
        # Passada 1: Tenta com condition_on_previous_text=True (melhor para coerência)
        options_passada1 = dict(
            fp16=True if device == "cuda" else False,
            temperature=0.0,  # Reduz criatividade e alucinações
            condition_on_previous_text=True,  # Usa contexto anterior
            no_speech_threshold=NO_SPEECH_THRESHOLD,
            logprob_threshold=LOGPROB_THRESHOLD,
            compression_ratio_threshold=COMPRESSION_RATIO_THRESHOLD,
        )
        
        # Inicializa options_passada2 com mesmo valor (será sobrescrito se houver loop)
        options_passada2 = options_passada1.copy()
        
        _notify_status_sync(request_id, "transcribing", 40, "Primeira passada (com contexto)...")
        result = model.transcribe(str(path), **options_passada1)
        
        # Detecta sinais de loop/alucinação na primeira passada
        tem_loop = False
        segmentos_com_alta_compressao = 0
        
        if "segments" in result:
            for segmento in result["segments"]:
                compression_ratio = segmento.get("compression_ratio", 1.0)
                if compression_ratio >= COMPRESSION_RATIO_THRESHOLD:
                    segmentos_com_alta_compressao += 1
            
            # Se mais de 30% dos segmentos têm alta compressão, provável loop
            if len(result["segments"]) > 0:
                percentual_alta_compressao = segmentos_com_alta_compressao / len(result["segments"])
                if percentual_alta_compressao > 0.3:
                    tem_loop = True
                    print(f"[{request_id or 'N/A'}] Detectado possível loop: "
                          f"{percentual_alta_compressao:.1%} dos segmentos com alta compressão")
        
        # Se detectou loop, tenta segunda passada sem contexto
        if tem_loop:
            print(f"[{request_id or 'N/A'}] Tentando segunda passada sem contexto (condition_on_previous_text=False)...")
            _notify_status_sync(request_id, "transcribing", 42, "Segunda passada (sem contexto, filtros mais rígidos)...")
            
            # Passada 2: Sem contexto e filtros mais rígidos
            options_passada2 = dict(
                fp16=True if device == "cuda" else False,
                temperature=0.0,
                condition_on_previous_text=False,  # Desliga contexto para quebrar loop
                no_speech_threshold=NO_SPEECH_THRESHOLD,
                logprob_threshold=LOGPROB_THRESHOLD,
                compression_ratio_threshold=COMPRESSION_RATIO_THRESHOLD,
            )
            
            result_passada2 = model.transcribe(str(path), **options_passada2)
            
            # Compara resultados e escolhe o melhor
            texto_passada1 = result.get("text", "").strip()
            texto_passada2 = result_passada2.get("text", "").strip()
            
            # Prefere passada 2 se ela for significativamente mais curta (menos repetições)
            # ou se passada 1 tiver sinais claros de loop
            if len(texto_passada2) < len(texto_passada1) * 0.7 or _detectar_anomalia_repeticao(texto_passada1):
                print(f"[{request_id or 'N/A'}] Usando resultado da segunda passada (sem contexto)")
                result = result_passada2
            else:
                print(f"[{request_id or 'N/A'}] Mantendo resultado da primeira passada (com contexto)")
        
        # Filtra alucinações baseado nos segmentos retornados (thresholds padronizados)
        if "segments" in result:
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
        
        elapsed = time.time() - start_time
        duracao_audio = result.get("duration", 0)
        
        print(f"[{request_id or 'N/A'}] Transcrição concluída em {elapsed:.1f}s")
        if duracao_audio:
            print(f"[{request_id or 'N/A'}] Duração do áudio: {duracao_audio:.1f}s ({duracao_audio/60:.1f} minutos)")
            print(f"[{request_id or 'N/A'}] Velocidade: {duracao_audio/elapsed:.2f}x tempo real")
        
        texto = result.get("text", "").strip()
        language = (result.get("language") or "").strip()

        texto_en = None
        if language and language not in {"pt", "pt-BR", "pt-br"}:
            # Usa a própria Whisper para traduzir para EN (task=translate)
            _notify_status_sync(request_id, "transcribing", 45, "Traduzindo para inglês (Whisper)...")
            # Usa as mesmas opções da passada final (sem contexto se houve loop)
            options_traducao = options_passada2 if tem_loop else options_passada1
            translate_result = model.transcribe(str(path), task="translate", **options_traducao)
            texto_en = (translate_result.get("text") or "").strip()
        
        if not texto:
            print(f"[{request_id or 'N/A'}] Aviso: Transcrição vazia!")
            _notify_status_sync(request_id, "transcribing", 50, "Aviso: Transcrição vazia")
            return {"text": "", "language": language or "unknown", "text_en": None}
        
        print(f"[{request_id or 'N/A'}] Texto transcrito: {len(texto)} caracteres, ~{len(texto.split())} palavras")
        
        _notify_status_sync(request_id, "transcribing", 50, f"Transcrição concluída ({len(texto)} caracteres)")
        
        # Limpa repetições APENAS se detectar anomalia (evita remover repetições legítimas)
        texto_limpo = texto
        if _detectar_anomalia_repeticao(texto):
            print(f"[{request_id or 'N/A'}] Detectada anomalia de repetição, aplicando limpeza...")
            _notify_status_sync(request_id, "transcribing", 55, "Limpando repetições detectadas...")
            texto_limpo = limpar_repeticoes(texto)
            
            if len(texto_limpo) != len(texto):
                removidos = len(texto) - len(texto_limpo)
                print(f"[{request_id or 'N/A'}] Texto limpo: {len(texto_limpo)} caracteres (removidos {removidos} caracteres de repetições)")
                _notify_status_sync(request_id, "transcribing", 58, f"Removidas {removidos} caracteres de repetições")
            else:
                _notify_status_sync(request_id, "transcribing", 58, "Limpeza concluída")
        else:
            print(f"[{request_id or 'N/A'}] Nenhuma anomalia detectada, pulando limpeza de repetições")
            _notify_status_sync(request_id, "transcribing", 58, "Validação concluída")
        
        # Limpa também o texto_en se existir (só se detectar anomalia)
        texto_en_limpo = None
        if texto_en:
            if _detectar_anomalia_repeticao(texto_en):
                texto_en_limpo = limpar_repeticoes(texto_en)
            else:
                texto_en_limpo = texto_en
        
        return {"text": texto_limpo, "language": language or "unknown", "text_en": texto_en_limpo}

    return await to_thread.run_sync(_run)
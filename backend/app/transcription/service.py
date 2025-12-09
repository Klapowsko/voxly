from pathlib import Path
import re

from anyio import to_thread
import torch
import whisper

from app.config import Settings


def limpar_repeticoes(texto: str) -> str:
    """Remove repetições excessivas de frases do texto transcrito."""
    if not texto:
        return texto
    
    # Divide o texto em sentenças
    sentencas = re.split(r"([.!?]+)", texto)
    
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
                if len(sentenca) > 5:  # Apenas sentenças significativas
                    sentencas_completas.append(sentenca)
                buffer = ""
            else:
                if len(parte) > 5:
                    sentencas_completas.append(parte)
        else:
            buffer = (buffer + " " + parte).strip() if buffer else parte
    
    if buffer and len(buffer) > 5:
        sentencas_completas.append(buffer)
    
    # Remove repetições excessivas
    # Se uma sentença aparecer mais de 3 vezes consecutivas, mantém apenas 1
    sentencas_limpas = []
    ultima_sentenca = None
    contador_repeticao = 0
    
    for sentenca in sentencas_completas:
        # Normaliza a sentença para comparação (remove espaços extras, lowercase)
        sentenca_normalizada = re.sub(r"\s+", " ", sentenca.lower().strip())
        
        if sentenca_normalizada == ultima_sentenca:
            contador_repeticao += 1
            # Se repetiu mais de 3 vezes, ignora
            if contador_repeticao <= 3:
                sentencas_limpas.append(sentenca)
        else:
            # Nova sentença, reseta contador
            ultima_sentenca = sentenca_normalizada
            contador_repeticao = 1
            sentencas_limpas.append(sentenca)
    
    # Reconstrói o texto
    texto_limpo = " ".join(sentencas_limpas)
    
    # Remove repetições de frases curtas muito comuns (ex: "eu sou o meu amigo")
    # Se uma frase curta (menos de 30 caracteres) aparecer mais de 5 vezes, remove as repetições
    palavras = texto_limpo.split()
    if len(palavras) > 10:
        # Verifica padrões repetitivos de 3-8 palavras
        for tamanho_padrao in range(8, 2, -1):  # De 8 até 3 palavras
            for i in range(len(palavras) - tamanho_padrao * 5):
                padrao = palavras[i:i + tamanho_padrao]
                padrao_texto = " ".join(padrao).lower()
                
                # Conta quantas vezes esse padrão se repete
                repeticoes = 0
                j = i
                while j < len(palavras) - tamanho_padrao + 1:
                    proximo_padrao = " ".join(palavras[j:j + tamanho_padrao]).lower()
                    if proximo_padrao == padrao_texto:
                        repeticoes += 1
                        j += tamanho_padrao
                    else:
                        break
                
                # Se repetiu mais de 5 vezes, remove as repetições extras
                if repeticoes > 5:
                    # Mantém apenas 1 ocorrência
                    palavras = palavras[:i + tamanho_padrao] + palavras[i + tamanho_padrao * repeticoes:]
                    texto_limpo = " ".join(palavras)
                    break
            else:
                continue
            break
    
    # Limpa espaços múltiplos
    texto_limpo = re.sub(r"\s+", " ", texto_limpo).strip()
    
    return texto_limpo


async def transcribe_file(path: Path, settings: Settings, request_id: str | None = None) -> str:
    """Transcreve áudio usando Whisper open source local. Suporta áudios longos (1h+)."""

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
        if request_id:
            from app.utils.status import set_status
            set_status(request_id, "transcribing", 30, "Carregando modelo Whisper...")
        
        # Carrega o modelo Whisper
        model = whisper.load_model(settings.whisper_model, device=device)
        print(f"[{request_id or 'N/A'}] Modelo carregado. Iniciando transcrição...")
        
        if request_id:
            set_status(request_id, "transcribing", 40, "Processando áudio com Whisper...")
        
        # Ajustes otimizados para melhor qualidade de transcrição
        options = dict(
            fp16=True if device == "cuda" else False,  # fp16 só funciona em GPU
            temperature=0.0,  # Mais determinístico para melhor qualidade
            condition_on_previous_text=True,  # Usa contexto anterior - melhora qualidade
            no_speech_threshold=0.6,  # Mais conservador - evita cortar fala válida
            logprob_threshold=-1.0,  # Aceita variações normais de fala
            compression_ratio_threshold=2.4,  # Detecta repetições (ajuda na limpeza)
            # Para áudios muito longos, o Whisper processa automaticamente em chunks
            # Não precisa configurar chunk_length manualmente
            # O Whisper gerencia automaticamente a memória para áudios longos
        )
        
        # Transcreve o arquivo (Whisper processa automaticamente áudios longos)
        # Para áudios > 30s, o Whisper divide automaticamente em segmentos
        result = model.transcribe(str(path), **options)
        
        elapsed = time.time() - start_time
        duracao_audio = result.get("duration", 0)
        
        print(f"[{request_id or 'N/A'}] Transcrição concluída em {elapsed:.1f}s")
        if duracao_audio:
            print(f"[{request_id or 'N/A'}] Duração do áudio: {duracao_audio:.1f}s ({duracao_audio/60:.1f} minutos)")
            print(f"[{request_id or 'N/A'}] Velocidade: {duracao_audio/elapsed:.2f}x tempo real")
        
        texto = result.get("text", "").strip()
        
        if not texto:
            print(f"[{request_id or 'N/A'}] Aviso: Transcrição vazia!")
            if request_id:
                set_status(request_id, "transcribing", 50, "Aviso: Transcrição vazia")
            return ""
        
        print(f"[{request_id or 'N/A'}] Texto transcrito: {len(texto)} caracteres, ~{len(texto.split())} palavras")
        
        if request_id:
            set_status(request_id, "transcribing", 55, f"Limpando repetições ({len(texto)} caracteres)...")
        
        # Limpa repetições excessivas
        print(f"[{request_id or 'N/A'}] Limpando repetições...")
        texto_limpo = limpar_repeticoes(texto)
        
        if len(texto_limpo) != len(texto):
            removidos = len(texto) - len(texto_limpo)
            print(f"[{request_id or 'N/A'}] Texto limpo: {len(texto_limpo)} caracteres (removidos {removidos} caracteres de repetições)")
            if request_id:
                set_status(request_id, "transcribing", 58, f"Removidas {removidos} repetições")
        
        return texto_limpo

    return await to_thread.run_sync(_run)

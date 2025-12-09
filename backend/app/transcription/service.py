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


async def transcribe_file(path: Path, settings: Settings) -> str:
    """Transcreve áudio usando Whisper open source local."""

    def _run() -> str:
        # Detecta device (auto, cuda ou cpu)
        if settings.whisper_device == "auto":
            device = "cuda" if torch.cuda.is_available() else "cpu"
        else:
            device = settings.whisper_device
        
        if device == "cpu":
            print("Aviso: GPU não disponível, usando CPU (será mais lento)")
        
        # Carrega o modelo Whisper
        model = whisper.load_model(settings.whisper_model, device=device)
        
        # Ajustes para acelerar inferência
        options = dict(
            fp16=True if device == "cuda" else False,  # fp16 só funciona em GPU
            temperature=0.0,
            condition_on_previous_text=False,
            no_speech_threshold=0.2,
            logprob_threshold=-1.0,
        )
        
        # Transcreve o arquivo
        result = model.transcribe(str(path), **options)
        
        texto = result.get("text", "").strip()
        
        # Limpa repetições excessivas
        texto_limpo = limpar_repeticoes(texto)
        
        return texto_limpo

    return await to_thread.run_sync(_run)

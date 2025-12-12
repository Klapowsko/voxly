"""Limpeza de texto: detecção e remoção de repetições/alucinações."""
import re

from app.transcription.utils import notify_status_sync


def detectar_anomalia_repeticao(texto: str) -> bool:
    """Detecta se o texto tem sinais de repetição excessiva (alucinação).
    
    Args:
        texto: Texto para analisar
        
    Returns:
        True se detectou anomalia, False caso contrário
    """
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


def _reconstruir_sentencas(texto: str) -> list[str]:
    """Reconstrói sentenças completas a partir de texto com pontuação.
    
    Args:
        texto: Texto com pontuação para processar
        
    Returns:
        Lista de sentenças completas
    """
    sentencas = re.split(r"([.!?]+)", texto)
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
    
    return sentencas_completas


def _remover_repeticoes_sentencas(sentencas: list[str]) -> list[str]:
    """Remove repetições de sentenças completas.
    
    Args:
        sentencas: Lista de sentenças para processar
        
    Returns:
        Lista de sentenças sem repetições excessivas (mantém no máximo 1 repetição)
    """
    sentencas_limpas = []
    ultima_sentenca = None
    contador_repeticao = 0
    
    for sentenca in sentencas:
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
    
    return sentencas_limpas


def _remover_repeticoes_padroes(texto: str) -> str:
    """Remove padrões repetitivos de palavras do texto.
    
    Args:
        texto: Texto para processar
        
    Returns:
        Texto sem padrões repetitivos
    """
    if not texto:
        return texto
    
    texto_limpo = texto
    max_iteracoes = 15  # Evita loop infinito
    iteracao = 0
    
    # Palavras comuns a ignorar quando isoladas
    PALAVRAS_IGNORAR = {
        "o", "a", "e", "de", "que", "em", "um", "uma", "é", "foi", 
        "ser", "se", "para", "com", "por"
    }
    
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
                if tamanho_padrao == 1 and padrao_texto in PALAVRAS_IGNORAR:
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
    
    return texto_limpo


def limpar_repeticoes(texto: str) -> str:
    """Remove repetições excessivas de frases do texto transcrito (incluindo alucinações).
    
    Args:
        texto: Texto para limpar
        
    Returns:
        Texto sem repetições excessivas
    """
    if not texto:
        return texto
    
    # Remove repetições de padrões de palavras
    texto_limpo = _remover_repeticoes_padroes(texto)
    
    # Reconstrói sentenças completas
    sentencas_completas = _reconstruir_sentencas(texto_limpo)
    
    # Remove repetições de sentenças completas
    sentencas_limpas = _remover_repeticoes_sentencas(sentencas_completas)
    
    # Reconstrói o texto final
    texto_limpo = " ".join(sentencas_limpas)
    
    # Limpa espaços múltiplos e normaliza
    texto_limpo = re.sub(r"\s+", " ", texto_limpo).strip()
    
    return texto_limpo


def aplicar_limpeza_condicional(
    texto: str,
    request_id: str | None = None,
) -> str:
    """Aplica limpeza de repetições apenas se detectar anomalia.
    
    Args:
        texto: Texto para processar
        request_id: ID da requisição para logs
        
    Returns:
        Texto limpo (ou original se não houver anomalia)
    """
    if detectar_anomalia_repeticao(texto):
        print(f"[{request_id or 'N/A'}] Detectada anomalia de repetição, aplicando limpeza...")
        notify_status_sync(request_id, "transcribing", 55, "Limpando repetições detectadas...")
        texto_limpo = limpar_repeticoes(texto)
        
        if len(texto_limpo) != len(texto):
            removidos = len(texto) - len(texto_limpo)
            print(f"[{request_id or 'N/A'}] Texto limpo: {len(texto_limpo)} caracteres (removidos {removidos} caracteres de repetições)")
            notify_status_sync(request_id, "transcribing", 58, f"Removidas {removidos} caracteres de repetições")
        else:
            notify_status_sync(request_id, "transcribing", 58, "Limpeza concluída")
        return texto_limpo
    else:
        print(f"[{request_id or 'N/A'}] Nenhuma anomalia detectada, pulando limpeza de repetições")
        notify_status_sync(request_id, "transcribing", 58, "Validação concluída")
        return texto


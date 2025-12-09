from pathlib import Path
import re

from anyio import to_thread

from app.config import Settings


PROMPT_TOPICOS = """Você é um especialista em análise e organização de conteúdo. Analise o seguinte texto transcrito de um áudio e crie uma estrutura de tópicos PROFUNDA, DETALHADA e COMPLETA, cobrindo TODOS os assuntos importantes mencionados.

INSTRUÇÕES DETALHADAS:

1. COMPREENSÃO COMPLETA DO CONTEÚDO:
   - Leia e compreenda COMPLETAMENTE todo o texto, sem pular partes
   - Identifique TODOS os principais temas, conceitos e ideias apresentados
   - Entenda o contexto e a mensagem central
   - Reconheça referências bíblicas, históricas ou culturais mencionadas
   - Identifique TODAS as transições de assunto e mudanças de tema
   - Não deixe nenhum assunto importante de fora

2. ORGANIZAÇÃO EM TÓPICOS (GERE TÓPICOS PARA TODOS OS ASSUNTOS):
   - Crie tópicos temáticos para CADA assunto importante mencionado
   - NÃO limite a quantidade de tópicos - crie quantos forem necessários para cobrir todo o conteúdo
   - Cada tópico deve ter um TÍTULO DESCRITIVO e específico que resume o conteúdo
   - NÃO agrupe assuntos diferentes em um único tópico - cada assunto importante deve ter seu próprio tópico
   - Agrupe apenas ideias MUITO relacionadas no mesmo tópico
   - Use subtópicos quando necessário para melhor organização
   - Identifique CADA mudança de assunto como um novo tópico
   - Seja generoso na criação de tópicos - é melhor ter mais tópicos bem organizados do que poucos tópicos genéricos

3. CONTEÚDO DETALHADO E COMPLETO (NÃO SEJA SUCINTO):
   - Cada tópico deve ter CONTEÚDO SUBSTANCIAL e completo
   - Inclua TODO o contexto relevante do que foi dito sobre aquele assunto
   - Adicione explicações e detalhes importantes
   - NÃO resuma demais - preserve TODAS as informações relevantes
   - Inclua citações diretas quando forem importantes
   - Desenvolva cada ideia com profundidade e completude
   - Certifique-se de que nenhuma informação importante seja perdida

4. COMENTÁRIOS E ANÁLISES DA IA:
   - Adicione uma seção de "💡 Análise" ou "📝 Comentários" no início de cada tópico
   - Forneça insights, interpretações e observações sobre o conteúdo
   - Destaque pontos-chave importantes e sua relevância
   - Adicione conexões entre ideias quando apropriado
   - Forneça contexto adicional quando necessário
   - Se houver referências bíblicas, explique seu significado e contexto
   - Adicione observações sobre a importância ou aplicação prática do conteúdo

5. FORMATAÇÃO:
   - Use parágrafos bem formatados (não tudo em uma linha)
   - Quebre o texto em parágrafos lógicos de 3-5 linhas
   - Use formatação Markdown apropriada (## para títulos, ** para ênfase, - para listas)
   - Adicione espaçamento adequado entre seções
   - Use emojis para destacar seções importantes (💡, 📝, ⚠️, etc.)

6. ESTRUTURA ESPERADA PARA CADA TÓPICO:
   ```
   ## [Título Descritivo e Específico do Tópico]
   
   💡 **Análise e Comentários:**
   [Sua análise completa, insights e comentários sobre este tópico - explique o que é importante, por que é relevante, e adicione contexto detalhado]
   
   **Conteúdo:**
   [Conteúdo completo e detalhado do tópico, com múltiplos parágrafos desenvolvendo TODAS as ideias relacionadas]
   
   [Mais parágrafos com detalhes adicionais e informações complementares]
   
   [Subtópicos se necessário para organizar melhor o conteúdo]
   ```

7. COBERTURA COMPLETA:
   - Analise TODO o texto, do início ao fim
   - Crie tópicos para TODOS os assuntos importantes mencionados
   - Não deixe nenhuma parte significativa do conteúdo sem um tópico correspondente
   - Adapte a quantidade de tópicos ao tamanho e complexidade do conteúdo
   - Para conteúdos longos (1 hora ou mais), crie tópicos suficientes para cobrir tudo
   - Para conteúdos mais curtos, ainda assim crie tópicos detalhados para cada assunto

TEXTO A ANALISAR:
{texto}

Gere os tópicos organizados seguindo EXATAMENTE as instruções acima. Seja MUITO detalhado, formatado, inteligente na organização e gere tópicos COMPLETOS para TODOS os assuntos importantes, sem deixar nada de fora. O objetivo é ter uma cobertura completa e detalhada de todo o conteúdo."""


def formatar_resultado_ia(texto: str) -> str:
    """Formata o resultado da IA para garantir qualidade."""
    # Remove espaços múltiplos
    texto = re.sub(r" +", " ", texto)
    # Garante quebra de linha após títulos
    texto = re.sub(r"(## .+?)([^\n])", r"\1\n\2", texto)
    # Garante parágrafos (quebra dupla após parágrafos longos)
    texto = re.sub(r"\. ([A-Z][^.!?]{50,})", r".\n\n\1", texto)
    return texto.strip()


def usar_ollama(texto: str, modelo: str = "llama3.2", ollama_url: str = "http://localhost:11434") -> str | None:
    """Usa Ollama para gerar tópicos (requer servidor Ollama rodando)."""
    try:
        import ollama
    except ImportError:
        return None
    
    # Usa o texto completo ou o máximo que o modelo suportar
    # Para modelos grandes, podemos usar textos muito longos
    # Limite aumentado significativamente para suportar áudios longos
    texto_limitado = texto[:100000] if len(texto) > 100000 else texto
    prompt = PROMPT_TOPICOS.format(texto=texto_limitado)
    
    try:
        # Tenta usar a biblioteca ollama
        response = ollama.chat(
            model=modelo,
            messages=[
                {
                    "role": "system",
                    "content": "Você é um especialista em análise de conteúdo, organização de informações e formatação de textos. Sempre siga as instruções detalhadamente. Gere MÚLTIPLOS tópicos com conteúdo substancial e comentários analíticos."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            options={
                "temperature": 0.4,  # Um pouco mais de criatividade para comentários
                "num_predict": 16000,  # Permite respostas muito longas para conteúdos extensos
            }
        )
        resultado = response["message"]["content"]
        return formatar_resultado_ia(resultado)
    except Exception:
        # Se falhar, tenta usar API HTTP diretamente
        try:
            import requests
            response = requests.post(
                f"{ollama_url}/api/chat",
                json={
                    "model": modelo,
                    "messages": [
                        {
                            "role": "system",
                            "content": "Você é um especialista em análise de conteúdo, organização de informações e formatação de textos. Sempre siga as instruções detalhadamente."
                        },
                        {"role": "user", "content": prompt}
                    ],
                    "stream": False,
                    "options": {
                        "temperature": 0.4,
                        "num_predict": 16000,
                    }
                },
                timeout=600  # 10 minutos
            )
            if response.status_code == 200:
                resultado = response.json()["message"]["content"]
                return formatar_resultado_ia(resultado)
        except Exception:
            pass
        
        return None


def usar_huggingface(texto: str) -> str | None:
    """Usa Hugging Face Transformers para análise e organização."""
    try:
        from transformers import pipeline
    except ImportError:
        return None
    
    try:
        # Usa um modelo de sumarização para extrair pontos-chave
        summarizer = pipeline(
            "summarization",
            model="facebook/bart-large-cnn",
            device=-1  # CPU
        )
        
        # Divide o texto em chunks menores para processar mais conteúdo
        # Chunks menores permitem mais tópicos
        palavras = texto.split()
        palavras_por_chunk = 400  # Chunks menores para mais granularidade
        num_chunks = max(10, len(palavras) // palavras_por_chunk)  # Mínimo 10 chunks, mais se necessário
        
        chunks = []
        for i in range(0, len(palavras), palavras_por_chunk):
            chunk = " ".join(palavras[i:i + palavras_por_chunk])
            if len(chunk.strip()) > 50:  # Apenas chunks significativos
                chunks.append(chunk)
        
        # Processa cada chunk e preserva conteúdo original
        topicos_com_conteudo = []
        
        for i, chunk in enumerate(chunks):
            try:
                # Gera resumo do chunk
                resultado = summarizer(
                    chunk,
                    max_length=200,  # Resumos maiores
                    min_length=80,   # Mínimo maior para mais detalhes
                    do_sample=False
                )
                resumo = resultado[0]["summary_text"]
                
                # Identifica tema automaticamente do chunk
                tema = identificar_tema_automatico(chunk, resumo)
                
                # Preserva parte do conteúdo original junto com o resumo
                topicos_com_conteudo.append({
                    "tema": tema,
                    "resumo": resumo,
                    "conteudo_original": chunk[:500],  # Primeiros 500 caracteres do conteúdo original
                    "indice": i
                })
            except Exception:
                continue
        
        if topicos_com_conteudo:
            return formatar_topicos_huggingface_melhorado(topicos_com_conteudo)
        
        return None
    except Exception:
        return None


def identificar_tema_automatico(conteudo_original: str, resumo: str) -> str:
    """Identifica o tema principal automaticamente baseado no conteúdo, sem usar lista fixa."""
    from collections import Counter
    
    # Combina conteúdo e resumo para análise
    texto_completo = (conteudo_original + " " + resumo).strip()
    
    # Extrai palavras-chave importantes (palavras com 4+ letras)
    palavras = re.findall(r"\b\w{4,}\b", texto_completo.lower())
    
    # Remove palavras comuns que não são informativas
    palavras_comuns = {
        "isso", "aqui", "onde", "quando", "como", "para", "com", "sobre",
        "mais", "muito", "pode", "será", "seria", "tempo", "momento", "pessoa",
        "pessoas", "coisa", "coisas", "tipo", "tipos", "forma", "maneira",
        "também", "ainda", "sempre", "nunca", "depois", "antes", "agora",
        "então", "assim", "dessa", "desse", "deste", "desta", "todo", "toda"
    }
    
    palavras_filtradas = [p for p in palavras if p not in palavras_comuns]
    
    # Conta frequência das palavras
    contador = Counter(palavras_filtradas)
    
    # Pega as palavras mais frequentes e significativas
    palavras_principais = [palavra for palavra, _ in contador.most_common(8)]
    
    # Tenta criar título inteligente baseado no conteúdo
    # Primeiro, tenta usar o início do resumo se for descritivo
    if resumo:
        primeira_frase = resumo.split(".")[0].strip()
        # Se a primeira frase for razoável (20-100 caracteres), usa ela
        if 20 <= len(primeira_frase) <= 100:
            # Limpa a frase removendo palavras muito comuns no início
            palavras_frase = primeira_frase.split()
            if len(palavras_frase) > 3:
                return primeira_frase
    
    # Se não, cria título baseado nas palavras principais
    if palavras_principais:
        # Pega as 2-3 palavras mais relevantes
        palavras_titulo = palavras_principais[:3]
        titulo = " ".join(palavras_titulo).title()
        
        # Se o título for muito curto, adiciona contexto
        if len(titulo) < 15:
            # Tenta pegar uma frase do conteúdo original
            primeira_sentenca = conteudo_original.split(".")[0].strip()
            if 30 <= len(primeira_sentenca) <= 80:
                return primeira_sentenca[:60]
        
        return titulo
    
    # Fallback: usa início do conteúdo
    primeira_parte = conteudo_original[:70].strip()
    if primeira_parte:
        # Remove pontuação final se houver
        primeira_parte = re.sub(r"[.!?]+$", "", primeira_parte)
        return primeira_parte
    
    return "Tópico do Conteúdo"


def formatar_topicos_huggingface_melhorado(topicos_com_conteudo: list) -> str:
    """Formata os tópicos do Hugging Face com conteúdo detalhado."""
    resultado = "# Tópicos Organizados da Transcrição\n\n"
    resultado += "*Análise realizada com Hugging Face Transformers*\n\n"
    
    # Agrupa tópicos por tema, mas mantém separados se forem temas diferentes
    topicos_agrupados = {}
    for topico in topicos_com_conteudo:
        tema = topico["tema"]
        if tema not in topicos_agrupados:
            topicos_agrupados[tema] = []
        topicos_agrupados[tema].append(topico)
    
    # Cria um tópico para cada grupo, mas se houver muitos do mesmo tema, divide
    indice = 1
    for tema, topicos_tema in topicos_agrupados.items():
        # Se houver muitos tópicos do mesmo tema, divide em subtópicos
        if len(topicos_tema) > 2:
            # Cria um tópico principal e subtópicos
            resultado += f"## {indice}. {tema}\n\n"
            resultado += "💡 **Análise:**\n"
            resultado += f"Este tema é abordado em {len(topicos_tema)} momentos diferentes do conteúdo, demonstrando sua importância.\n\n"
            resultado += "**Conteúdo:**\n\n"
            
            for sub_indice, topico in enumerate(topicos_tema, 1):
                resultado += f"### {indice}.{sub_indice} - {tema} (Parte {sub_indice})\n\n"
                resultado += f"**Resumo:** {topico['resumo']}\n\n"
                resultado += f"**Conteúdo detalhado:**\n\n"
                # Formata o conteúdo original em parágrafos
                conteudo = topico["conteudo_original"]
                sentencas = re.split(r"([.!?]+)", conteudo)
                paragrafo = []
                
                for j in range(0, len(sentencas) - 1, 2):
                    if j + 1 < len(sentencas):
                        sentenca = (sentencas[j] + sentencas[j + 1]).strip()
                        if sentenca and len(sentenca) > 20:
                            paragrafo.append(sentenca)
                            if len(paragrafo) >= 2:
                                resultado += " ".join(paragrafo) + "\n\n"
                                paragrafo = []
                
                if paragrafo:
                    resultado += " ".join(paragrafo) + "\n\n"
                
                resultado += "\n"
            
            resultado += "---\n\n"
            indice += 1
        else:
            # Tópicos únicos ou poucos - cria tópico individual
            for topico in topicos_tema:
                resultado += f"## {indice}. {tema}\n\n"
                resultado += "💡 **Análise:**\n"
                resultado += f"{topico['resumo']}\n\n"
                resultado += "**Conteúdo detalhado:**\n\n"
                
                # Formata o conteúdo original em parágrafos
                conteudo = topico["conteudo_original"]
                sentencas = re.split(r"([.!?]+)", conteudo)
                paragrafo = []
                
                for j in range(0, len(sentencas) - 1, 2):
                    if j + 1 < len(sentencas):
                        sentenca = (sentencas[j] + sentencas[j + 1]).strip()
                        if sentenca and len(sentenca) > 20:
                            paragrafo.append(sentenca)
                            if len(paragrafo) >= 2:
                                resultado += " ".join(paragrafo) + "\n\n"
                                paragrafo = []
                
                if paragrafo:
                    resultado += " ".join(paragrafo) + "\n\n"
                
                resultado += "---\n\n"
                indice += 1
    
    return resultado


def gerar_topicos_simples(texto: str) -> str:
    """Gera tópicos melhorados usando processamento de texto inteligente (fallback final)."""
    # Remove espaços múltiplos
    texto = re.sub(r"\s+", " ", texto).strip()
    
    # Calcula quantos tópicos criar baseado no tamanho do texto
    palavras = texto.split()
    num_palavras = len(palavras)
    # Adapta dinamicamente: aproximadamente 1 tópico a cada 200-300 palavras
    # Mas permite mais tópicos para conteúdos maiores
    palavras_por_topico = max(200, min(300, num_palavras // max(6, num_palavras // 500)))
    
    # Divide o texto em partes baseado em pontuação e tamanho
    partes = re.split(r"([.!?]+)", texto)
    
    # Reconstrói sentenças completas
    sentencas = []
    buffer = ""
    for parte in partes:
        parte = parte.strip()
        if not parte:
            continue
        
        # Se a parte tem pontuação ou é muito longa, finaliza sentença
        if re.search(r"[.!?]$", parte) or len(buffer) > 150:
            if buffer:
                sentenca_completa = (buffer + " " + parte).strip()
                if len(sentenca_completa) > 40:  # Apenas sentenças significativas
                    sentencas.append(sentenca_completa)
                buffer = ""
            else:
                if len(parte) > 40:
                    sentencas.append(parte)
        else:
            buffer = (buffer + " " + parte).strip()
    
    if buffer and len(buffer) > 40:
        sentencas.append(buffer)
    
    # Se ainda não tiver sentenças suficientes, divide por tamanho
    if len(sentencas) < palavras_por_topico:
        palavras = texto.split()
        tamanho_chunk = palavras_por_topico
        sentencas = []
        for i in range(0, len(palavras), tamanho_chunk):
            chunk = " ".join(palavras[i:i + tamanho_chunk])
            if len(chunk) > 40:
                sentencas.append(chunk)
    
    # Divide sentenças em grupos para criar tópicos dinamicamente
    # Cria múltiplos tópicos baseado no conteúdo - sem limite máximo rígido
    # Adapta ao tamanho: mais sentenças = mais tópicos possíveis
    num_topicos = max(6, len(sentencas) // 3)  # Mínimo 6, mas pode ser muito mais para conteúdos longos
    sentencas_por_topico = len(sentencas) // num_topicos if num_topicos > 0 else len(sentencas)
    
    # Cria tópicos dinamicamente com identificação automática de temas
    from collections import Counter
    
    resultado = "# Tópicos Organizados da Transcrição\n\n"
    resultado += "*Análise e organização inteligente do conteúdo*\n\n"
    
    for i in range(num_topicos):
        inicio = i * sentencas_por_topico
        fim = inicio + sentencas_por_topico if i < num_topicos - 1 else len(sentencas)
        sentencas_topo = sentencas[inicio:fim]
        
        if not sentencas_topo:
            continue
        
        # Identifica tema automaticamente baseado no conteúdo deste tópico
        conteudo_topo = " ".join(sentencas_topo)
        
        # Extrai palavras-chave do tópico
        palavras_topo = re.findall(r"\b\w{4,}\b", conteudo_topo.lower())
        palavras_comuns = {
            "isso", "aqui", "onde", "quando", "como", "para", "com", "sobre",
            "mais", "muito", "pode", "será", "seria", "tempo", "momento"
        }
        palavras_filtradas = [p for p in palavras_topo if p not in palavras_comuns]
        
        # Conta frequência
        contador = Counter(palavras_filtradas)
        palavras_principais = [palavra for palavra, _ in contador.most_common(5)]
        
        # Cria título baseado nas palavras principais ou primeira sentença
        if palavras_principais:
            titulo = " ".join(palavras_principais[:3]).title()
            if len(titulo) < 10:
                # Se título muito curto, usa primeira sentença
                primeira_sentenca = sentencas_topo[0].strip()
                if len(primeira_sentenca) > 20:
                    titulo = primeira_sentenca[:60].rstrip(".,!?")
        else:
            # Usa primeira sentença como título
            primeira_sentenca = sentencas_topo[0].strip()
            titulo = primeira_sentenca[:60].rstrip(".,!?") if len(primeira_sentenca) > 20 else f"Tópico {i + 1}"
        
        resultado += f"## {i + 1}. {titulo}\n\n"
        resultado += "💡 **Análise:**\n"
        if palavras_principais:
            resultado += f"Este tópico aborda aspectos relacionados a {', '.join(palavras_principais[:3])}. "
        else:
            resultado += "Este tópico aborda aspectos importantes do conteúdo apresentado. "
        resultado += "O conteúdo desenvolve ideias importantes sobre este tema.\n\n"
        resultado += "**Conteúdo:**\n\n"
        
        # Formata sentenças em parágrafos bem estruturados
        paragrafo = []
        for sentenca in sentencas_topo:
            # Adiciona pontuação se não tiver
            if not re.search(r"[.!?]$", sentenca):
                sentenca += "."
            
            paragrafo.append(sentenca)
            
            # Cria parágrafos de 2-3 sentenças
            if len(paragrafo) >= 2:
                texto_paragrafo = " ".join(paragrafo)
                resultado += texto_paragrafo + "\n\n"
                paragrafo = []
        
        # Adiciona parágrafo restante
        if paragrafo:
            texto_paragrafo = " ".join(paragrafo)
            if not re.search(r"[.!?]$", texto_paragrafo):
                texto_paragrafo += "."
            resultado += texto_paragrafo + "\n\n"
        
        resultado += "---\n\n"
    
    return resultado


async def generate_topics_markdown(
    transcript: str, settings: Settings, request_id: str
) -> tuple[str, Path]:
    """Gera conteúdo em Markdown usando modelos open source (Ollama/Hugging Face/método simples)."""
    output_path = settings.outputs_dir / f"{request_id}_topics.md"
    
    def _run() -> tuple[str, Path]:
        resultado = None
        
        # Tenta Ollama primeiro
        if settings.ollama_model:
            resultado = usar_ollama(transcript, settings.ollama_model, settings.ollama_url)
            if resultado:
                output_path.write_text(resultado, encoding="utf-8")
                return resultado, output_path
        
        # Se Ollama não funcionou, tenta Hugging Face
        if not resultado:
            resultado = usar_huggingface(transcript)
            if resultado:
                output_path.write_text(resultado, encoding="utf-8")
                return resultado, output_path
        
        # Fallback para método simples
        if not resultado or len(resultado.strip()) < 100:
            resultado = gerar_topicos_simples(transcript)
        
        # Garante que o resultado não está vazio
        if not resultado or len(resultado.strip()) < 50:
            resultado = gerar_topicos_simples(transcript)
        
        output_path.write_text(resultado, encoding="utf-8")
        return resultado, output_path
    
    return await to_thread.run_sync(_run)

from pathlib import Path
import re

from anyio import to_thread

from app.config import Settings


def _notify_status_sync(request_id: str | None, stage: str, progress: int, message: str) -> None:
    """Helper para notificar status via WebSocket em contexto síncrono."""
    if not request_id:
        return
    from app.utils.status import notify_status_from_thread
    notify_status_from_thread(request_id, stage, progress, message)


def formatar_resultado_ia(texto: str) -> str:
    """Formata o resultado da IA para garantir qualidade."""
    # Remove espaços múltiplos
    texto = re.sub(r" +", " ", texto)
    # Remove quebras de linha dentro de títulos (## T\nítulo -> ## Título)
    # Procura por ## seguido de qualquer coisa até encontrar uma quebra de linha, e depois mais texto na próxima linha (que não seja outro título ou espaço)
    texto = re.sub(r"(## [^\n]+)\n([^\n#\s])", r"\1 \2", texto)
    # Garante quebra de linha dupla após títulos completos (após o título terminar, antes de conteúdo)
    texto = re.sub(r"(## [^\n]+)\n+([A-Z])", r"\1\n\n\2", texto)
    # Garante parágrafos (quebra dupla após parágrafos longos)
    texto = re.sub(r"\. ([A-Z][^.!?]{50,})", r".\n\n\1", texto)
    # Remove múltiplas quebras de linha consecutivas (mais de 2)
    texto = re.sub(r"\n{3,}", r"\n\n", texto)
    return texto.strip()


def usar_spellbook(texto: str, spellbook_url: str, request_id: str | None = None) -> str | None:
    """Usa Spellbook (serviço externo) para gerar tópicos via API HTTP."""
    try:
        import requests
    except ImportError:
        print(f"[{request_id or 'N/A'}] Biblioteca requests não disponível")
        return None
    
    # Limita o texto para evitar requisições muito grandes
    # O Spellbook pode processar textos longos, mas vamos limitar para performance
    texto_limitado = texto[:50000] if len(texto) > 50000 else texto
    if len(texto) > 50000:
        print(f"[{request_id or 'N/A'}] Texto limitado para {len(texto_limitado)} caracteres (original: {len(texto)})")
    
    # Calcula número de tópicos baseado no tamanho do texto
    # Aproximadamente 1 tópico para cada 1000 palavras
    num_palavras = len(texto_limitado.split())
    count = max(10, min(30, num_palavras // 1000))  # Entre 10 e 30 tópicos
    
    # Garante que a URL não tenha barra final duplicada
    url_base = spellbook_url.rstrip('/')
    endpoint = f"{url_base}/topics"
    
    print(f"[{request_id or 'N/A'}] Enviando requisição para Spellbook ({endpoint}) - {len(texto_limitado)} caracteres, {count} tópicos...")
    
    try:
        response = requests.post(
            endpoint,
            json={
                "subject": texto_limitado,
                "count": count
            },
            headers={"Content-Type": "application/json"},
            timeout=120  # 2 minutos para requisições externas
        )
        
        if response.status_code == 200:
            data = response.json()
            topics = data.get("topics", [])
            
            if not topics:
                print(f"[{request_id or 'N/A'}] Spellbook retornou lista vazia de tópicos")
                return None
            
            print(f"[{request_id or 'N/A'}] Spellbook retornou {len(topics)} tópicos")
            
            # Converte lista de tópicos para markdown
            # Para cada tópico, busca conteúdo relacionado no texto original
            markdown_content = ""
            
            # Divide texto em sentenças uma vez (mais eficiente)
            sentencas = [s.strip() for s in re.split(r'[.!?]+', texto_limitado) if len(s.strip()) >= 20]
            
            for i, topic in enumerate(topics, 1):
                # Limpa o tópico (remove quebras de linha e espaços extras)
                # Remove todas as quebras de linha e substitui por espaços
                topic_limpo = re.sub(r'\s+', ' ', topic.strip())
                # Remove espaços no início e fim
                topic_limpo = topic_limpo.strip()
                
                # Adiciona o tópico como header (garantindo que não há quebras de linha no título)
                markdown_content += f"## {topic_limpo}\n\n"
                
                # Busca conteúdo relacionado no texto original
                # Extrai palavras-chave do tópico (palavras de 3+ letras para melhor matching)
                palavras_topic = set(re.findall(r"\b\w{3,}\b", topic_limpo.lower()))
                
                # Remove palavras muito comuns que não ajudam no matching
                palavras_comuns = {
                    "que", "com", "para", "uma", "uma", "sobre", "como", "mais", "muito",
                    "isso", "aqui", "onde", "quando", "será", "seria", "tempo", "pode",
                    "também", "ainda", "sempre", "nunca", "depois", "antes", "agora",
                    "então", "assim", "dessa", "desse", "deste", "desta", "todo", "toda",
                    "este", "esta", "esse", "essa", "aquele", "aquela", "são", "foi", "ser"
                }
                palavras_topic = {p for p in palavras_topic if p not in palavras_comuns and len(p) >= 3}
                
                # Encontra sentenças relacionadas ao tópico
                sentencas_relacionadas = []
                for sentenca in sentencas:
                    sentenca_lower = sentenca.lower()
                    # Extrai palavras da sentença (3+ letras)
                    palavras_sentenca = set(re.findall(r"\b\w{3,}\b", sentenca_lower))
                    palavras_sentenca = {p for p in palavras_sentenca if p not in palavras_comuns and len(p) >= 3}
                    
                    # Calcula interseção de palavras
                    palavras_comuns = palavras_topic & palavras_sentenca
                    
                    # Se houver pelo menos 1 palavra-chave em comum (mais permissivo)
                    # ou se o tópico contém palavras importantes da sentença
                    if len(palavras_comuns) >= 1:
                        # Calcula score de relevância (mais palavras em comum = mais relevante)
                        score = len(palavras_comuns)
                        sentencas_relacionadas.append((score, sentenca))
                
                # Ordena por relevância (maior score primeiro)
                sentencas_relacionadas.sort(key=lambda x: x[0], reverse=True)
                
                # Adiciona conteúdo relacionado (máximo 5 sentenças mais relevantes)
                if sentencas_relacionadas:
                    conteudo_sentencas = [s[1] for s in sentencas_relacionadas[:5]]
                    conteudo = " ".join(conteudo_sentencas)
                    if len(conteudo) > 800:
                        conteudo = conteudo[:797] + "..."
                    markdown_content += f"{conteudo}\n\n"
                else:
                    # Se não encontrar conteúdo relacionado, tenta uma busca mais ampla
                    # Procura por qualquer palavra do tópico no texto
                    palavras_importantes = [p for p in palavras_topic if len(p) >= 4][:3]
                    if palavras_importantes:
                        # Busca sentenças que contenham pelo menos uma palavra importante
                        sentencas_fallback = []
                        for sentenca in sentencas:
                            sentenca_lower = sentenca.lower()
                            if any(palavra in sentenca_lower for palavra in palavras_importantes):
                                sentencas_fallback.append(sentenca)
                        
                        if sentencas_fallback:
                            conteudo = " ".join(sentencas_fallback[:3])
                            if len(conteudo) > 500:
                                conteudo = conteudo[:497] + "..."
                            markdown_content += f"{conteudo}\n\n"
                        else:
                            markdown_content += f"*Conteúdo relacionado a este tópico no texto original.*\n\n"
                    else:
                        markdown_content += f"*Conteúdo relacionado a este tópico no texto original.*\n\n"
            
            resultado = markdown_content.strip()
            print(f"[{request_id or 'N/A'}] Markdown gerado: {len(resultado)} caracteres")
            return formatar_resultado_ia(resultado)
        else:
            print(f"[{request_id or 'N/A'}] Erro HTTP do Spellbook: {response.status_code} - {response.text[:200]}")
            return None
            
    except requests.exceptions.Timeout:
        print(f"[{request_id or 'N/A'}] Timeout ao chamar Spellbook (serviço pode estar lento)")
        return None
    except requests.exceptions.ConnectionError:
        print(f"[{request_id or 'N/A'}] Erro de conexão com Spellbook (serviço não disponível?)")
        return None
    except requests.exceptions.RequestException as e:
        print(f"[{request_id or 'N/A'}] Erro na requisição ao Spellbook: {e}")
        return None
    except Exception as e:
        print(f"[{request_id or 'N/A'}] Erro inesperado ao usar Spellbook: {e}")
        return None


def usar_huggingface(texto: str, request_id: str | None = None) -> str | None:
    """Usa Hugging Face Transformers para análise e organização."""
    try:
        from transformers import pipeline
    except ImportError:
        print(f"[{request_id or 'N/A'}] Hugging Face não disponível (biblioteca não instalada)")
        return None
    
    try:
        if request_id:
            _notify_status_sync(request_id, "generating", 72, "Carregando modelo Hugging Face (pode demorar na primeira vez)...")
        print(f"[{request_id or 'N/A'}] Carregando modelo Hugging Face (pode demorar na primeira vez)...")
        # Usa um modelo de sumarização para extrair pontos-chave
        summarizer = pipeline(
            "summarization",
            model="facebook/bart-large-cnn",
            device=-1  # CPU
        )
        print(f"[{request_id or 'N/A'}] Modelo Hugging Face carregado")
        if request_id:
            _notify_status_sync(request_id, "generating", 74, "Modelo Hugging Face carregado")
        
        # Divide o texto em chunks menores para processar mais conteúdo
        # Chunks menores permitem mais tópicos
        palavras = texto.split()
        palavras_por_chunk = 400  # Chunks menores para mais granularidade
        num_chunks = max(10, len(palavras) // palavras_por_chunk)  # Mínimo 10 chunks, mais se necessário
        print(f"[{request_id or 'N/A'}] Dividindo texto em {num_chunks} chunks...")
        if request_id:
            _notify_status_sync(request_id, "generating", 75, f"Dividindo texto em {num_chunks} chunks...")
        
        chunks = []
        for i in range(0, len(palavras), palavras_por_chunk):
            chunk = " ".join(palavras[i:i + palavras_por_chunk])
            if len(chunk.strip()) > 50:  # Apenas chunks significativos
                chunks.append(chunk)
        
        # Processa cada chunk e preserva conteúdo original
        topicos_com_conteudo = []
        
        for i, chunk in enumerate(chunks):
            try:
                # Atualiza progresso para cada chunk (mais frequente)
                if request_id:
                    progresso = 75 + int((i + 1) / len(chunks) * 15)
                    _notify_status_sync(request_id, "generating", progresso, f"Processando chunk {i + 1}/{len(chunks)}...")
                
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
            except Exception as e:
                print(f"[{request_id or 'N/A'}] Erro ao processar chunk {i + 1}: {e}")
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
        # Remove duplicatas e palavras muito similares
        palavras_unicas = []
        palavras_vistas = set()
        for palavra in palavras_principais:
            # Normaliza a palavra (remove variações)
            palavra_normalizada = palavra.lower().strip()
            # Evita palavras muito similares (ex: "amigo" e "amigos")
            if palavra_normalizada not in palavras_vistas:
                # Verifica se não é variação de palavra já vista
                is_variacao = any(
                    palavra_normalizada.startswith(p[:4]) or p.startswith(palavra_normalizada[:4])
                    for p in palavras_vistas
                )
                if not is_variacao:
                    palavras_unicas.append(palavra)
                    palavras_vistas.add(palavra_normalizada)
        
        # Pega as 2-3 palavras mais relevantes (únicas)
        palavras_titulo = palavras_unicas[:3]
        if palavras_titulo:
            titulo = " ".join(palavras_titulo).title()
            # Limpa espaços múltiplos
            titulo = re.sub(r"\s+", " ", titulo).strip()
            
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
            # Remove duplicatas e palavras muito similares
            palavras_unicas = []
            palavras_vistas = set()
            for palavra in palavras_principais:
                palavra_normalizada = palavra.lower().strip()
                # Evita palavras muito similares (ex: "amigo" e "amigos")
                if palavra_normalizada not in palavras_vistas:
                    is_variacao = any(
                        palavra_normalizada.startswith(p[:4]) or p.startswith(palavra_normalizada[:4])
                        for p in palavras_vistas
                    )
                    if not is_variacao:
                        palavras_unicas.append(palavra)
                        palavras_vistas.add(palavra_normalizada)
            
            if palavras_unicas:
                titulo = " ".join(palavras_unicas[:3]).title()
                # Limpa espaços múltiplos e caracteres estranhos
                titulo = re.sub(r"\s+", " ", titulo).strip()
                
                if len(titulo) < 10:
                    # Se título muito curto, usa primeira sentença
                    primeira_sentenca = sentencas_topo[0].strip()
                    if len(primeira_sentenca) > 20:
                        titulo = primeira_sentenca[:60].rstrip(".,!?")
                        titulo = re.sub(r"\s+", " ", titulo).strip()
            else:
                # Fallback se não houver palavras únicas
                primeira_sentenca = sentencas_topo[0].strip()
                titulo = primeira_sentenca[:60].rstrip(".,!?") if len(primeira_sentenca) > 20 else f"Tópico {i + 1}"
        else:
            # Usa primeira sentença como título
            primeira_sentenca = sentencas_topo[0].strip()
            titulo = primeira_sentenca[:60].rstrip(".,!?") if len(primeira_sentenca) > 20 else f"Tópico {i + 1}"
            titulo = re.sub(r"\s+", " ", titulo).strip()
        
        resultado += f"## {i + 1}. {titulo}\n\n"
        resultado += "💡 **Análise:**\n"
        # Cria análise mais inteligente baseada no conteúdo
        if palavras_principais and len(palavras_principais) > 0:
            # Remove duplicatas para a análise também
            palavras_analise = list(dict.fromkeys(palavras_principais[:3]))  # Mantém ordem, remove duplicatas
            if palavras_analise:
                resultado += f"Este tópico aborda aspectos relacionados a {', '.join(palavras_analise)}. "
            else:
                resultado += "Este tópico aborda aspectos importantes do conteúdo apresentado. "
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
    transcript: str, settings: Settings, request_id: str, request_id_status: str | None = None
) -> tuple[str, Path]:
    """Gera conteúdo em Markdown usando Spellbook (serviço externo) com fallback para Hugging Face e método simples."""
    output_path = settings.outputs_dir / f"{request_id}_topics.md"
    
    def _run() -> tuple[str, Path]:
        import time
        from app.utils.status import set_status
        
        resultado = None
        start_time = time.time()
        tamanho_texto = len(transcript)
        num_palavras = len(transcript.split())
        
        print(f"[{request_id_status or request_id}] Iniciando geração de tópicos...")
        print(f"[{request_id_status or request_id}] Tamanho do texto: {tamanho_texto} caracteres, ~{num_palavras} palavras")
        
        if request_id_status:
            _notify_status_sync(request_id_status, "generating", 70, f"Analisando texto ({num_palavras} palavras)...")
        
        # Tenta Spellbook primeiro (serviço externo)
        print(f"[{request_id_status or request_id}] Tentando usar Spellbook ({settings.spellbook_url})...")
        if request_id_status:
            _notify_status_sync(request_id_status, "generating", 72, "Conectando com Spellbook...")
            _notify_status_sync(request_id_status, "generating", 75, "Gerando tópicos com Spellbook...")
        
        resultado = usar_spellbook(transcript, settings.spellbook_url, request_id_status)
        if resultado:
            print(f"[{request_id_status or request_id}] ✓ Tópicos gerados com Spellbook ({len(resultado)} caracteres)")
            if request_id_status:
                _notify_status_sync(request_id_status, "generating", 90, f"Tópicos gerados com Spellbook ({len(resultado)} caracteres)")
            output_path.write_text(resultado, encoding="utf-8")
            return resultado, output_path
        else:
            print(f"[{request_id_status or request_id}] Spellbook não disponível ou falhou")
        
        # Se Spellbook não funcionou, tenta Hugging Face
        if not resultado:
            print(f"[{request_id_status or request_id}] Tentando usar Hugging Face...")
            if request_id_status:
                _notify_status_sync(request_id_status, "generating", 72, "Carregando modelo Hugging Face...")
                _notify_status_sync(request_id_status, "generating", 75, "Gerando tópicos com Hugging Face...")
            
            resultado = usar_huggingface(transcript, request_id_status)
            if resultado:
                print(f"[{request_id_status or request_id}] ✓ Tópicos gerados com Hugging Face ({len(resultado)} caracteres)")
                if request_id_status:
                    _notify_status_sync(request_id_status, "generating", 90, f"Tópicos gerados com Hugging Face ({len(resultado)} caracteres)")
                output_path.write_text(resultado, encoding="utf-8")
                return resultado, output_path
            else:
                print(f"[{request_id_status or request_id}] Hugging Face não disponível ou falhou")
        
        # Fallback para método simples
        if not resultado or len(resultado.strip()) < 100:
            print(f"[{request_id_status or request_id}] Usando método simples (fallback)...")
            if request_id_status:
                _notify_status_sync(request_id_status, "generating", 80, "Gerando tópicos com método simples...")
            
            resultado = gerar_topicos_simples(transcript)
            print(f"[{request_id_status or request_id}] ✓ Tópicos gerados com método simples ({len(resultado)} caracteres)")
        
        # Garante que o resultado não está vazio
        if not resultado or len(resultado.strip()) < 50:
            print(f"[{request_id_status or request_id}] Resultado muito curto, regenerando...")
            resultado = gerar_topicos_simples(transcript)
        
        elapsed = time.time() - start_time
        print(f"[{request_id_status or request_id}] Geração de tópicos concluída em {elapsed:.1f}s")
        print(f"[{request_id_status or request_id}] Resultado final: {len(resultado)} caracteres, ~{len(resultado.split())} palavras")
        
        if request_id_status:
            num_topicos = resultado.count("##")
            _notify_status_sync(request_id_status, "generating", 92, f"Tópicos formatados: {num_topicos} tópicos identificados")
        
        output_path.write_text(resultado, encoding="utf-8")
        return resultado, output_path
    
    return await to_thread.run_sync(_run)

PROMPT_TITULO = """Analise e interprete o seguinte texto transcrito de um áudio. Identifique o tema principal, a mensagem central e o contexto do conteúdo.

IMPORTANTE:
- NÃO copie pedaços do texto diretamente
- INTERPRETE o conteúdo e crie um título original que sintetize a ideia principal
- Analise TODO o conteúdo para entender o tema central
- Crie um título que seja uma síntese inteligente do que foi discutido

REQUISITOS:
- Título deve ter no máximo 60-80 caracteres
- Deve ser uma interpretação e síntese do conteúdo, não uma cópia
- Deve capturar o tema principal de forma criativa e descritiva
- Deve ser claro, objetivo e informativo
- Sem aspas ou formatação extra
- Em português brasileiro
- Apenas o título, sem explicações ou comentários adicionais

TEXTO:
{texto}

Analise o conteúdo completo, identifique o tema principal e gere um título original que sintetize a mensagem central. NÃO copie partes do texto."""


def usar_huggingface_titulo(texto: str, request_id: str | None = None) -> str | None:
    """Usa Hugging Face para gerar título através de sumarização e interpretação."""
    try:
        from transformers import pipeline
    except ImportError:
        print(f"[{request_id or 'N/A'}] Hugging Face não disponível para geração de título")
        return None
    
    try:
        print(f"[{request_id or 'N/A'}] Gerando título com Hugging Face (sumarização)...")
        # Usa modelo de sumarização para extrair ideia principal
        summarizer = pipeline(
            "summarization",
            model="facebook/bart-large-cnn",
            device=-1  # CPU
        )
        
        # Limita o texto para processamento (modelos têm limite de tokens)
        texto_limitado = texto[:2000] if len(texto) > 2000 else texto
        
        # Gera resumo muito curto (máximo 50 palavras) para extrair ideia principal
        resultado = summarizer(
            texto_limitado,
            max_length=50,  # Resumo bem curto
            min_length=10,  # Mínimo para ter conteúdo
            do_sample=False
        )
        
        resumo = resultado[0]["summary_text"].strip()
        
        # Processa o resumo para criar título
        # Remove pontuação final se houver
        import re
        resumo = re.sub(r'[.!?]+$', '', resumo)
        
        # Se o resumo for muito longo, tenta extrair a primeira sentença ou frase principal
        if len(resumo) > 80:
            # Pega primeira sentença ou primeiras palavras
            sentencas = re.split(r'[.!?]+', resumo)
            if sentencas:
                resumo = sentencas[0].strip()
        
        # Limita tamanho final
        if len(resumo) > 80:
            resumo = resumo[:77] + "..."
        
        # Remove aspas se houver
        resumo = resumo.strip('"').strip("'").strip()
        
        if resumo and len(resumo) > 10:
            print(f"[{request_id or 'N/A'}] ✓ Título gerado com Hugging Face: {resumo}")
            return resumo
        
        return None
    except Exception as e:
        print(f"[{request_id or 'N/A'}] Erro ao gerar título com Hugging Face: {e}")
        return None


def generate_title(transcript: str, settings: Settings, request_id: str | None = None) -> str:
    """Gera título descritivo para a transcrição usando IA.
    
    Sempre tenta interpretar o conteúdo ao invés de copiar pedaços do texto.
    Retorna o título gerado ou string vazia se falhar (para usar filename como fallback).
    """
    if not transcript or len(transcript.strip()) < 10:
        return ""
    
    print(f"[{request_id or 'N/A'}] Gerando título interpretando conteúdo...")
    
    # Tenta Hugging Face (sumarização)
    resultado = usar_huggingface_titulo(transcript, request_id)
    if resultado and len(resultado.strip()) > 5:
        print(f"[{request_id or 'N/A'}] ✓ Título gerado com Hugging Face: {resultado}")
        return resultado
    
    # Se nenhum método de IA funcionou, retorna string vazia
    # O fallback para filename será feito em background.py
    print(f"[{request_id or 'N/A'}] Não foi possível gerar título com IA, usando filename como fallback")
    return ""


from pathlib import Path
import re

from anyio import to_thread

from app.config import Settings


PROMPT_TOPICOS = """Você é um especialista em análise e organização de conteúdo. Analise o seguinte texto transcrito de um áudio e crie uma estrutura de tópicos PROFUNDA e BEM FORMATADA.

INSTRUÇÕES DETALHADAS:

1. COMPREENSÃO DO CONTEÚDO:
   - Leia e compreenda completamente o texto
   - Identifique os principais temas, conceitos e ideias
   - Entenda o contexto e a mensagem central
   - Reconheça referências bíblicas, históricas ou culturais mencionadas

2. ORGANIZAÇÃO EM TÓPICOS:
   - Crie tópicos temáticos (não apenas divisões aleatórias)
   - Cada tópico deve ter um TÍTULO DESCRITIVO que resume o conteúdo
   - Agrupe ideias relacionadas no mesmo tópico
   - Use subtópicos quando necessário para melhor organização

3. FORMATAÇÃO:
   - Use parágrafos bem formatados (não tudo em uma linha)
   - Quebre o texto em parágrafos lógicos de 3-5 linhas
   - Use formatação Markdown apropriada (## para títulos, ** para ênfase)
   - Adicione espaçamento adequado entre seções

4. INTERPRETAÇÃO E ANOTAÇÕES:
   - Adicione uma breve interpretação ou resumo no início de cada tópico
   - Destaque pontos-chave importantes
   - Se houver referências bíblicas, mencione-as claramente
   - Adicione notas explicativas quando o contexto ajudar

5. ESTRUTURA ESPERADA:
   ```
   ## [Título Descritivo do Tópico]
   
   [Breve interpretação/anotação do que este tópico aborda]
   
   [Conteúdo formatado em parágrafos claros e legíveis, não tudo em uma linha]
   
   [Subtópicos se necessário]
   ```

TEXTO A ANALISAR:
{texto}

Gere os tópicos organizados seguindo EXATAMENTE as instruções acima. Seja detalhado, formatado e inteligente na organização."""


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
    
    # Usa mais texto para melhor compreensão (mas limita para não exceder contexto)
    texto_limitado = texto[:12000] if len(texto) > 12000 else texto
    prompt = PROMPT_TOPICOS.format(texto=texto_limitado)
    
    try:
        # Tenta usar a biblioteca ollama
        response = ollama.chat(
            model=modelo,
            messages=[
                {
                    "role": "system",
                    "content": "Você é um especialista em análise de conteúdo, organização de informações e formatação de textos. Sempre siga as instruções detalhadamente."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            options={
                "temperature": 0.3,  # Menos criatividade, mais fidelidade
                "num_predict": 4000,  # Permite respostas mais longas
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
                        "temperature": 0.3,
                        "num_predict": 4000,
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
        
        # Divide o texto em chunks temáticos
        max_length = 800
        chunks = []
        palavras = texto.split()
        
        for i in range(0, len(palavras), max_length):
            chunk = " ".join(palavras[i:i + max_length])
            chunks.append(chunk)
        
        # Processa cada chunk e identifica temas
        resumos_por_tema = {}
        
        for i, chunk in enumerate(chunks[:6]):  # Limita a 6 chunks
            try:
                resultado = summarizer(
                    chunk,
                    max_length=150,
                    min_length=40,
                    do_sample=False
                )
                resumo = resultado[0]["summary_text"]
                
                # Identifica tema do chunk
                tema = identificar_tema(resumo)
                if tema not in resumos_por_tema:
                    resumos_por_tema[tema] = []
                resumos_por_tema[tema].append(resumo)
            except Exception:
                continue
        
        if resumos_por_tema:
            return formatar_topicos_huggingface(resumos_por_tema)
        
        return None
    except Exception:
        return None


def identificar_tema(texto: str) -> str:
    """Identifica o tema principal de um texto."""
    texto_lower = texto.lower()
    
    temas = {
        "Compromisso e Fé": ["compromisso", "fé", "deus", "cristo", "escolha"],
        "Espiritualidade": ["espiritualidade", "homens", "centralizada", "antropocêntrica"],
        "Exemplos Bíblicos": ["samuel", "paulo", "eli", "bíblia", "versículo"],
        "Prática da Palavra": ["palavra", "prática", "ouvem", "fundamento", "colocam"],
    }
    
    for tema, palavras_chave in temas.items():
        if any(palavra in texto_lower for palavra in palavras_chave):
            return tema
    
    return "Outros Assuntos"


def formatar_topicos_huggingface(resumos_por_tema: dict) -> str:
    """Formata os resumos do Hugging Face em tópicos organizados."""
    resultado = "# Tópicos Organizados da Transcrição\n\n"
    resultado += "*Análise realizada com Hugging Face Transformers*\n\n"
    
    for i, (tema, resumos) in enumerate(resumos_por_tema.items(), 1):
        resultado += f"## {i}. {tema}\n\n"
        resultado += f"*Resumo dos pontos principais sobre este tema:*\n\n"
        
        # Combina e formata os resumos
        conteudo = " ".join(resumos)
        # Quebra em parágrafos
        sentencas = re.split(r"([.!?]+)", conteudo)
        paragrafo = []
        
        for j in range(0, len(sentencas) - 1, 2):
            if j + 1 < len(sentencas):
                sentenca = (sentencas[j] + sentencas[j + 1]).strip()
                if sentenca:
                    paragrafo.append(sentenca)
                    if len(paragrafo) >= 2:
                        resultado += " ".join(paragrafo) + "\n\n"
                        paragrafo = []
        
        if paragrafo:
            resultado += " ".join(paragrafo) + "\n\n"
        
        resultado += "---\n\n"
    
    return resultado


def gerar_topicos_simples(texto: str) -> str:
    """Gera tópicos melhorados usando processamento de texto inteligente (fallback final)."""
    # Remove espaços múltiplos
    texto = re.sub(r"\s+", " ", texto).strip()
    
    # Divide o texto em partes baseado em pontuação
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
    if len(sentencas) < 3:
        palavras = texto.split()
        tamanho_chunk = max(50, len(palavras) // 4)
        sentencas = []
        for i in range(0, len(palavras), tamanho_chunk):
            chunk = " ".join(palavras[i:i + tamanho_chunk])
            if len(chunk) > 40:
                sentencas.append(chunk)
    
    # Identifica temas principais
    temas = {
        "1. Compromisso e Foco em Deus": {
            "palavras": ["compromisso", "deus", "escolha", "olhos", "fixos", "mirar", "salmo"],
            "descricao": "Aborda a importância de manter compromisso com Deus e fixar os olhos em Cristo."
        },
        "2. Espiritualidade Centralizada em Cristo": {
            "palavras": ["espiritualidade", "antropocêntrica", "homens", "cristo", "centralizada", "depender"],
            "descricao": "Discute a necessidade de centralizar a espiritualidade em Cristo, não em homens."
        },
        "3. Exemplos Bíblicos e Lições": {
            "palavras": ["samuel", "eli", "rófne", "paulo", "bíblia", "versículo", "capítulo", "livro"],
            "descricao": "Apresenta exemplos bíblicos e referências que ilustram os princípios discutidos."
        },
        "4. Fé Prática e Fundamentação": {
            "palavras": ["fé", "palavra", "prática", "fundamento", "ouvem", "colocam", "crucificado"],
            "descricao": "Trata sobre a importância de colocar a Palavra em prática e fundamentar a fé."
        },
    }
    
    # Agrupa sentenças por tema
    topicos_organizados = {}
    
    for sentenca in sentencas:
        sentenca_lower = sentenca.lower()
        melhor_tema = None
        melhor_score = 0
        
        # Encontra o tema mais relevante
        for tema_nome, tema_info in temas.items():
            score = sum(1 for palavra in tema_info["palavras"] if palavra in sentenca_lower)
            if score > melhor_score:
                melhor_score = score
                melhor_tema = tema_nome
        
        # Se não encontrou tema claro, tenta encontrar por contexto
        if melhor_score == 0:
            if any(palavra in sentenca_lower for palavra in ["deus", "cristo", "senhor"]):
                melhor_tema = "1. Compromisso e Foco em Deus"
            elif any(palavra in sentenca_lower for palavra in ["espiritualidade", "homem", "pessoa"]):
                melhor_tema = "2. Espiritualidade Centralizada em Cristo"
            elif any(palavra in sentenca_lower for palavra in ["samuel", "paulo", "bíblia", "versículo"]):
                melhor_tema = "3. Exemplos Bíblicos e Lições"
            else:
                melhor_tema = "4. Fé Prática e Fundamentação"
        
        if melhor_tema not in topicos_organizados:
            topicos_organizados[melhor_tema] = []
        
        topicos_organizados[melhor_tema].append(sentenca)
    
    # Formata os tópicos de forma elegante
    resultado = "# Tópicos Organizados da Transcrição\n\n"
    resultado += "*Análise e organização inteligente do conteúdo*\n\n"
    
    for tema_nome in temas.keys():
        if tema_nome not in topicos_organizados:
            continue
            
        sentencas_tema = topicos_organizados[tema_nome]
        tema_info = temas[tema_nome]
        
        resultado += f"## {tema_nome}\n\n"
        resultado += f"*{tema_info['descricao']}*\n\n"
        
        # Formata sentenças em parágrafos bem estruturados
        paragrafo = []
        for sentenca in sentencas_tema[:10]:  # Limita sentenças por tópico
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

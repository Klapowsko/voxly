# Voxly - Transcrição de Áudio com Whisper

Aplicação completa para gravar áudio, transcrever usando Whisper (open source) e gerar tópicos organizados em Markdown, ideal para uso com Obsidian.

**100% Open Source e Gratuito** - Usa modelos locais sem necessidade de APIs pagas.

## 🏗️ Arquitetura

- **Frontend**: Next.js 14 com TypeScript e Tailwind CSS
- **Backend**: FastAPI (Python) com arquitetura modular
  - `app/audio`: Gerenciamento de upload e armazenamento de áudios
  - `app/transcription`: Serviço de transcrição usando Whisper local (openai-whisper)
  - `app/topics`: Geração de tópicos em Markdown usando Ollama/Hugging Face/método simples
  - `app/api`: Rotas da API REST

A arquitetura modular permite fácil extração em microserviços no futuro.

## 📋 Pré-requisitos

- Docker e Docker Compose instalados
- Navegador moderno com suporte a MediaRecorder API
- (Opcional) Ollama instalado e rodando para melhor qualidade na geração de tópicos
- (Recomendado para áudios longos) GPU NVIDIA com CUDA para processamento mais rápido

## 🚀 Início Rápido

1. **Clone o repositório e configure as variáveis de ambiente:**

Os arquivos `.env` serão criados automaticamente pelo Makefile. Se preferir criar manualmente:

```bash
cp backend/env.example backend/.env
cp frontend/env.example frontend/.env
```

Edite os arquivos `.env` se necessário. Por padrão, usa modelos open source:
- Whisper local (openai-whisper) para transcrição
- Ollama (opcional) ou Hugging Face para geração de tópicos

**Opcional - Para melhor qualidade nos tópicos, instale Ollama:**
```bash
# Instale Ollama: https://ollama.ai
# Baixe um modelo:
ollama pull llama3.2
```

2. **Inicie os serviços:**

```bash
docker-compose up --build
```

Ou usando o Makefile:

```bash
make build
make up
```

3. **Acesse a aplicação:**

- Frontend: http://localhost:3000
- Backend API: http://localhost:8000
- Health check: http://localhost:8000/health

## 📖 Como Usar

### Gravação de Áudio

1. Clique em **"Gravar"** para iniciar a gravação
2. O timer mostra a duração da gravação
3. Clique em **"Concluir"** quando terminar
4. O sistema processará automaticamente:
   - Upload do áudio
   - Transcrição com Whisper
   - Geração de tópicos em Markdown

### Upload Manual

Alternativamente, você pode fazer upload de um arquivo de áudio clicando em **"Fazer Upload de Arquivo"**.

### Resultado

Após o processamento, você verá:
- A transcrição completa do áudio
- Os tópicos organizados em Markdown
- Um botão para baixar o arquivo `.md` (compatível com Obsidian)

### Áudios Longos

O sistema suporta áudios de qualquer duração, incluindo:
- **Palestras de 20-30 minutos**
- **Sermões de 1 hora ou mais**
- **Vídeos longos** (o Whisper extrai o áudio automaticamente)

**Notas importantes:**
- Áudios longos podem levar mais tempo para processar (especialmente em CPU)
- Com GPU, o processamento é significativamente mais rápido
- O Whisper processa automaticamente áudios longos em segmentos, **sem limite rígido de duração**
- Recomenda-se usar modelo `base` ou `small` para áudios muito longos (mais rápido)
- Modelos `medium` ou `large` oferecem melhor qualidade, mas são mais lentos
- O sistema remove automaticamente repetições excessivas da transcrição

## 🔧 Configuração

### Variáveis de Ambiente

#### Backend (`backend/.env`)

- `APP_API_TOKEN`: Token de autenticação para a API (padrão: `dev-token`)
- `APP_WHISPER_MODEL`: Modelo Whisper local a usar - `tiny`, `base`, `small`, `medium`, `large` (padrão: `base`)
- `APP_WHISPER_DEVICE`: Device para Whisper - `auto`, `cuda`, `cpu` (padrão: `auto`)
- `APP_OLLAMA_MODEL`: Modelo Ollama para tópicos, ou `None` para desabilitar (padrão: `llama3.2`)
- `APP_OLLAMA_URL`: URL do servidor Ollama (padrão: `http://localhost:11434`)
- `APP_DATA_DIR`: Diretório para armazenar arquivos (padrão: `/data`)

**Nota**: Se Ollama não estiver disponível, o sistema usa Hugging Face como fallback, e por último um método simples sem IA.

#### Frontend (`frontend/.env`)

- `NEXT_PUBLIC_API_URL`: URL da API backend (padrão: `http://localhost:8000`)
- `NEXT_PUBLIC_API_TOKEN`: Token de autenticação (deve corresponder ao backend)

### Volumes Docker

Os arquivos são armazenados no volume `./data`:
- `data/uploads/`: Áudios enviados
- `data/outputs/`: Arquivos Markdown gerados

## 🧪 Testes

Execute os testes do backend:

```bash
docker-compose run --rm backend pytest
```

Ou usando o Makefile:

```bash
make test
```

## 📁 Estrutura do Projeto

```
voxly/
├── backend/
│   ├── app/
│   │   ├── api/          # Rotas da API
│   │   ├── audio/        # Módulo de áudio
│   │   ├── transcription/# Módulo de transcrição
│   │   ├── topics/       # Módulo de geração de tópicos
│   │   ├── config.py     # Configurações
│   │   ├── deps.py       # Dependências FastAPI
│   │   └── main.py       # Aplicação principal
│   ├── tests/            # Testes
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/
│   ├── app/
│   │   ├── page.tsx      # Página principal
│   │   ├── layout.tsx
│   │   └── globals.css
│   ├── Dockerfile
│   └── package.json
├── data/                 # Volume de dados (criado automaticamente)
├── docker-compose.yml
└── README.md
```

## 🔐 Autenticação

A API usa autenticação simples via header `X-API-TOKEN`. Configure o mesmo token no frontend e backend.

## 🎯 Casos de Uso

- Gravar palestras e gerar notas estruturadas
- Transcrever sermões e criar resumos temáticos
- Processar reuniões e extrair pontos principais
- Qualquer situação onde você precisa transformar áudio em conteúdo organizado

## 🚧 Desenvolvimento

### Modo de Desenvolvimento

Os volumes estão configurados para hot-reload:
- Backend: alterações em `backend/app/` são refletidas automaticamente
- Frontend: alterações em `frontend/app/` são refletidas automaticamente

### Adicionar Novos Módulos

A arquitetura modular facilita a adição de novos módulos:

1. Crie uma nova pasta em `backend/app/`
2. Implemente o serviço com funções assíncronas
3. Importe e use no módulo `api/routes.py`

## 📝 Licença

Este projeto é de código aberto.

## 🤝 Contribuindo

Contribuições são bem-vindas! Sinta-se à vontade para abrir issues e pull requests.


.PHONY: build up down logs test clean help

backend/.env:
	@if [ ! -f backend/.env ]; then \
		echo "Criando backend/.env a partir do exemplo..."; \
		cp backend/env.example backend/.env; \
		echo "Arquivo backend/.env criado com sucesso!"; \
	fi

frontend/.env:
	@if [ ! -f frontend/.env ]; then \
		echo "Criando frontend/.env..."; \
		echo "NEXT_PUBLIC_API_URL=http://localhost:8000" > frontend/.env; \
		echo "NEXT_PUBLIC_API_TOKEN=dev-token" >> frontend/.env; \
		echo "Arquivo frontend/.env criado com sucesso!"; \
	fi

build: backend/.env frontend/.env
	docker compose build

up: backend/.env frontend/.env
	docker compose up -d

down:
	docker compose down

logs:
	docker compose logs -f

test:
	docker compose run --rm backend pytest

clean:
	docker compose down -v
	rm -rf data/

help:
	@echo "Comandos disponíveis:"
	@echo "  make build    - Constrói as imagens Docker"
	@echo "  make up       - Inicia os serviços em background"
	@echo "  make down     - Para os serviços"
	@echo "  make logs     - Mostra os logs dos serviços"
	@echo "  make test     - Executa os testes do backend"
	@echo "  make clean    - Remove containers, volumes e dados"
	@echo "  make help     - Mostra esta ajuda"


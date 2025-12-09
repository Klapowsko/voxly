.PHONY: build up down logs test clean help

build:
	docker compose build

up:
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


.PHONY: setup dev up down build logs ps restart test lint format lint-format clean

setup:
	uv sync --all-packages --all-groups --all-extras
	npm --prefix services/ui install

dev:
	docker compose up --build

up: dev

down:
	docker compose down

build:
	docker compose build

logs:
	docker compose logs -f --tail=200

ps:
	docker compose ps

restart:
	docker compose restart

test:
	uv run pytest

lint:
	uv run ruff check . --fix
	npm --prefix services/ui run lint

format:
	uv run ruff format .
	uv run isort .

lint-format:
	make format
	make lint

clean:
	docker compose down -v --remove-orphans
